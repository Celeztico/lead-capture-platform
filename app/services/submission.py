import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Submission
from app.repositories import (
    IdempotencyRepository,
    OutboxRepository,
    SubmissionRepository,
    WidgetRepository,
)
from app.repositories.idempotency import IdempotencyResult


class SubmissionService:
    def __init__(self, session: AsyncSession):
        self.widget_repo = WidgetRepository(session)
        self.submission_repo = SubmissionRepository(session)
        self.idempotency_repo = IdempotencyRepository(session)
        self.outbox_repo = OutboxRepository(session)
        self.session = session

    def _compute_fingerprint(self, data: dict) -> str:
        """Compute SHA-256 fingerprint of request data."""
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    async def submit(
        self,
        public_widget_id: UUID,
        data: dict,
        source_origin: str | None = None,
        idempotency_key: str | None = None,
        client_ip: str | None = None,
    ) -> tuple[Submission, str]:
        """
        Process a submission.
        Returns: (submission, status) where status is one of:
        - "created": new submission stored
        - "replay": idempotent replay of existing submission
        """
        # Resolve widget
        widget = await self.widget_repo.get_active_by_public_id(public_widget_id)
        if not widget:
            raise ValueError("Widget not found or not active")

        # Check idempotency
        if idempotency_key:
            fingerprint = self._compute_fingerprint(data)
            expires_at = datetime.now(UTC) + timedelta(hours=24)

            status, existing = await self.idempotency_repo.claim_key(
                workspace_id=widget.workspace_id,
                widget_id=widget.id,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                expires_at=expires_at,
            )

            if status == IdempotencyResult.REPLAY and existing and existing.submission_id:
                # Replay - return existing submission
                submission = await self.submission_repo.get_by_id(
                    existing.submission_id, widget.workspace_id
                )
                if submission:
                    return submission, "replay"

            if status == IdempotencyResult.CONFLICT:
                raise ValueError("IDEMPOTENCY_CONFLICT")

        # Validate data against widget configuration (basic validation)
        # In reality, this would be more thorough

        # Create submission
        submission = await self.submission_repo.create(
            workspace_id=widget.workspace_id,
            widget_id=widget.id,
            data=data,
            source_origin=source_origin,
        )

        # Store idempotency record link
        if idempotency_key:
            record = await self.idempotency_repo.get_by_key(widget.id, idempotency_key)
            if record:
                await self.idempotency_repo.set_submission_id(record, submission.id)

        # Enqueue async jobs
        await self.outbox_repo.create(
            event_type="submission.geolocate",
            payload={"submission_id": str(submission.id)},
            workspace_id=widget.workspace_id,
            submission_id=submission.id,
        )

        await self.outbox_repo.create(
            event_type="submission.send_notification",
            payload={"submission_id": str(submission.id)},
            workspace_id=widget.workspace_id,
            submission_id=submission.id,
        )

        await self.session.flush()
        return submission, "created"

    async def get_submission(
        self, submission_id: UUID, workspace_id: UUID
    ) -> Submission | None:
        return await self.submission_repo.get_by_id(submission_id, workspace_id)

    async def list_submissions(
        self,
        workspace_id: UUID,
        limit: int = 20,
        offset: int = 0,
        widget_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Sequence[Submission]:
        return await self.submission_repo.list_for_workspace(
            workspace_id, limit, offset, widget_id, date_from, date_to
        )

    async def get_analytics_summary(
        self,
        workspace_id: UUID,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        widget_id: UUID | None = None,
    ) -> dict:
        total = await self.submission_repo.count_for_workspace(
            workspace_id, widget_id, date_from, date_to
        )
        by_widget = await self.submission_repo.get_widget_submission_counts(workspace_id)

        # Provide default date range if not specified
        if date_from is None:
            date_from = datetime.now(UTC) - timedelta(days=30)
        if date_to is None:
            date_to = datetime.now(UTC)

        daily = await self.submission_repo.get_daily_counts(workspace_id, date_from, date_to)
        countries = await self.submission_repo.get_country_breakdown(workspace_id)

        return {
            "workspace_id": str(workspace_id),
            "total_submissions": total,
            "by_widget": [
                {"widget_id": str(wid), "count": count} for wid, count in by_widget
            ],
            "daily": [
                {"date": day.isoformat(), "count": count} for day, count in daily
            ],
            "by_country": [
                {"country_code": code, "count": count} for code, count in countries
            ],
        }
