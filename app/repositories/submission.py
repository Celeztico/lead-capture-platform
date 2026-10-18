from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Submission


class SubmissionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        workspace_id: UUID,
        widget_id: UUID,
        data: dict,
        source_origin: str | None = None,
    ) -> Submission:
        submission = Submission(
            workspace_id=workspace_id,
            widget_id=widget_id,
            data=data,
            source_origin=source_origin,
        )
        self.session.add(submission)
        await self.session.flush()
        return submission

    async def get_by_id(self, submission_id: UUID, workspace_id: UUID) -> Submission | None:
        result = await self.session.execute(
            select(Submission).where(
                Submission.id == submission_id, Submission.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        limit: int = 20,
        offset: int = 0,
        widget_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> Sequence[Submission]:
        query = select(Submission).where(Submission.workspace_id == workspace_id)
        if widget_id:
            query = query.where(Submission.widget_id == widget_id)
        if date_from:
            query = query.where(Submission.created_at >= date_from)
        if date_to:
            query = query.where(Submission.created_at <= date_to)
        query = query.order_by(desc(Submission.created_at)).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_for_workspace(
        self,
        workspace_id: UUID,
        widget_id: UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> int:
        query = select(func.count(Submission.id)).where(
            Submission.workspace_id == workspace_id
        )
        if widget_id:
            query = query.where(Submission.widget_id == widget_id)
        if date_from:
            query = query.where(Submission.created_at >= date_from)
        if date_to:
            query = query.where(Submission.created_at <= date_to)
        result = await self.session.execute(query)
        return result.scalar_one()

    async def get_widget_submission_counts(
        self, workspace_id: UUID
    ) -> Sequence[tuple[UUID, int]]:
        result = await self.session.execute(
            select(Submission.widget_id, func.count(Submission.id))
            .where(Submission.workspace_id == workspace_id)
            .group_by(Submission.widget_id)
        )
        rows: Sequence[Row[tuple[UUID, int]]] = result.all()
        return [(row[0], row[1]) for row in rows]

    async def get_daily_counts(
        self,
        workspace_id: UUID,
        date_from: datetime,
        date_to: datetime,
    ) -> Sequence[tuple[datetime, int]]:
        result = await self.session.execute(
            select(
                func.date_trunc("day", Submission.created_at).label("day"),
                func.count(Submission.id),
            )
            .where(
                Submission.workspace_id == workspace_id,
                Submission.created_at >= date_from,
                Submission.created_at < date_to,
            )
            .group_by("day")
            .order_by("day")
        )
        rows: Sequence[Row[tuple[datetime, int]]] = result.all()
        return [(row[0], row[1]) for row in rows]

    async def get_country_breakdown(self, workspace_id: UUID) -> Sequence[tuple[str, int]]:
        result = await self.session.execute(
            select(Submission.country_code, func.count(Submission.id))
            .where(
                Submission.workspace_id == workspace_id,
                Submission.country_code.is_not(None),
            )
            .group_by(Submission.country_code)
            .order_by(func.count(Submission.id).desc())
        )
        rows: Sequence[Row[tuple[str | None, int]]] = result.all()
        return [(row[0] or "", row[1]) for row in rows]

    async def update_enrichment(
        self,
        submission_id: UUID,
        country_code: str | None = None,
        country_name: str | None = None,
        region: str | None = None,
        city: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        enrichment_status: str | None = None,
    ) -> Submission | None:
        submission = await self.get_by_id(submission_id, UUID("00000000-0000-0000-0000-000000000000"))
        if not submission:
            # Try without workspace_id for internal updates
            result = await self.session.execute(
                select(Submission).where(Submission.id == submission_id)
            )
            submission = result.scalar_one_or_none()
        if submission:
            if country_code is not None:
                submission.country_code = country_code
            if country_name is not None:
                submission.country_name = country_name
            if region is not None:
                submission.region = region
            if city is not None:
                submission.city = city
            if latitude is not None:
                submission.latitude = latitude
            if longitude is not None:
                submission.longitude = longitude
            if enrichment_status is not None:
                submission.enrichment_status = enrichment_status
            await self.session.flush()
        return submission
