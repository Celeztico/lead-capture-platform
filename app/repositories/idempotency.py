from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IdempotencyRecord


class IdempotencyResult:
    NEW = "new"
    REPLAY = "replay"
    CONFLICT = "conflict"


class IdempotencyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def claim_key(
        self,
        workspace_id: UUID,
        widget_id: UUID,
        idempotency_key: str,
        request_fingerprint: str,
        expires_at: datetime,
    ) -> tuple[str, IdempotencyRecord | None]:
        """
        Try to claim an idempotency key.
        Returns: (status, record)
        - (IdempotencyResult.NEW, None): key claimed, new record created
        - (IdempotencyResult.REPLAY, record): key exists with same fingerprint
        - (IdempotencyResult.CONFLICT, record): key exists with different fingerprint
        """
        # Try to insert new record
        stmt = pg_insert(IdempotencyRecord).values(
            workspace_id=workspace_id,
            widget_id=widget_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            expires_at=expires_at,
        )
        # On conflict, do nothing and return existing
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["widget_id", "idempotency_key"]
        )
        await self.session.execute(stmt)
        await self.session.flush()

        # Fetch the record (either newly created or existing)
        result = await self.session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.widget_id == widget_id,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        record = result.scalar_one_or_none()

        if record and record.request_fingerprint == request_fingerprint:
            return IdempotencyResult.REPLAY, record  # Existing with same fingerprint (replay)
        elif record:
            return IdempotencyResult.CONFLICT, record  # Existing with different fingerprint (conflict)
        else:
            # This shouldn't happen with the above logic, but handle anyway
            return IdempotencyResult.NEW, None

    async def set_submission_id(
        self, record: IdempotencyRecord, submission_id: UUID
    ) -> None:
        record.submission_id = submission_id
        await self.session.flush()

    async def get_by_key(
        self, widget_id: UUID, idempotency_key: str
    ) -> IdempotencyRecord | None:
        result = await self.session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.widget_id == widget_id,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()
