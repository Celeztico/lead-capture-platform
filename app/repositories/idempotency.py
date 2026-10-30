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
        - (IdempotencyResult.NEW, record): key claimed by this call
        - (IdempotencyResult.REPLAY, record): key exists with same fingerprint
        - (IdempotencyResult.CONFLICT, record): key exists with different fingerprint
        """
        # Try to insert new record. RETURNING tells us whether this call
        # actually created the claim: no row comes back when a concurrent
        # request already inserted the same (widget_id, idempotency_key).
        stmt = pg_insert(IdempotencyRecord).values(
            workspace_id=workspace_id,
            widget_id=widget_id,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
            expires_at=expires_at,
        ).on_conflict_do_nothing(
            index_elements=["widget_id", "idempotency_key"]
        ).returning(IdempotencyRecord)
        inserted = (await self.session.execute(stmt)).scalar_one_or_none()
        await self.session.flush()

        if inserted is not None:
            return IdempotencyResult.NEW, inserted

        # Conflict: fetch the existing record to classify it.
        result = await self.session.execute(
            select(IdempotencyRecord).where(
                IdempotencyRecord.widget_id == widget_id,
                IdempotencyRecord.idempotency_key == idempotency_key,
            )
        )
        record = result.scalar_one_or_none()

        if record is None:
            # The conflicting transaction rolled back between our insert and
            # select; treat as a fresh claim so the caller proceeds.
            return IdempotencyResult.NEW, None
        if record.request_fingerprint == request_fingerprint:
            return IdempotencyResult.REPLAY, record
        return IdempotencyResult.CONFLICT, record

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
