from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobStatus, OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        event_type: str,
        payload: dict,
        workspace_id: UUID | None = None,
        submission_id: UUID | None = None,
        max_attempts: int = 5,
        available_at: datetime | None = None,
    ) -> OutboxEvent:
        event = OutboxEvent(
            workspace_id=workspace_id,
            submission_id=submission_id,
            event_type=event_type,
            payload=payload,
            max_attempts=max_attempts,
            available_at=available_at or datetime.now(UTC),
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def claim_jobs(
        self, worker_id: str, limit: int = 10
    ) -> Sequence[OutboxEvent]:
        now = datetime.now(UTC)
        # Atomically claim jobs
        result = await self.session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.status == JobStatus.PENDING,
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.available_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        jobs = result.scalars().all()

        for job in jobs:
            job.status = JobStatus.RUNNING
            job.locked_at = now
            job.locked_by = worker_id
            job.attempt_count += 1

        await self.session.flush()
        return jobs

    async def complete_job(self, job: OutboxEvent) -> None:
        job.status = JobStatus.SUCCEEDED
        job.locked_at = None
        job.locked_by = None
        job.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def fail_job(
        self, job: OutboxEvent, error_code: str, retry: bool = True
    ) -> None:
        now = datetime.now(UTC)
        job.last_error_code = error_code
        job.updated_at = now

        if retry and job.attempt_count < job.max_attempts:
            # Exponential backoff: 5s, 15s, 45s, 2min, 5min
            backoff_seconds = [5, 15, 45, 120, 300]
            delay = backoff_seconds[min(job.attempt_count, len(backoff_seconds) - 1)]
            job.status = JobStatus.RETRYING
            job.available_at = now + timedelta(seconds=delay)
        else:
            job.status = JobStatus.DEAD_LETTER
            job.locked_at = None
            job.locked_by = None

        await self.session.flush()

    async def get_dead_letter_count(self) -> int:
        result = await self.session.execute(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.status == JobStatus.DEAD_LETTER
            )
        )
        return result.scalar_one()

    async def get_oldest_pending_age_seconds(self) -> float | None:
        result = await self.session.execute(
            select(
                func.extract("epoch", datetime.now(UTC) - OutboxEvent.available_at)
            ).where(OutboxEvent.status.in_([JobStatus.PENDING, JobStatus.RETRYING]))
        )
        return result.scalar_one_or_none()

    async def release_stale_locks(self, stale_threshold_seconds: int = 300) -> int:
        """Release jobs that have been locked too long (worker crashed)."""
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_threshold_seconds)
        result = await self.session.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.status == JobStatus.RUNNING,
                OutboxEvent.locked_at < cutoff,
            )
            .values(
                status=JobStatus.PENDING,
                locked_at=None,
                locked_by=None,
                available_at=datetime.now(UTC),
            )
        )
        await self.session.flush()
        return result.rowcount
