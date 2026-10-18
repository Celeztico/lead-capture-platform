from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Widget, WidgetStatus


class WidgetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        workspace_id: UUID,
        name: str,
        configuration: dict,
        public_id: UUID | None = None,
    ) -> Widget:
        widget = Widget(
            workspace_id=workspace_id,
            name=name,
            configuration=configuration,
            public_id=public_id,
        )
        self.session.add(widget)
        await self.session.flush()
        return widget

    async def get_by_id(self, widget_id: UUID, workspace_id: UUID) -> Widget | None:
        result = await self.session.execute(
            select(Widget).where(
                Widget.id == widget_id, Widget.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_public_id(self, public_id: UUID) -> Widget | None:
        result = await self.session.execute(
            select(Widget).where(Widget.public_id == public_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_public_id(self, public_id: UUID) -> Widget | None:
        result = await self.session.execute(
            select(Widget).where(
                Widget.public_id == public_id, Widget.status == WidgetStatus.ACTIVE
            )
        )
        return result.scalar_one_or_none()

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        limit: int = 20,
        offset: int = 0,
        status: WidgetStatus | None = None,
    ) -> Sequence[Widget]:
        query = select(Widget).where(Widget.workspace_id == workspace_id)
        if status:
            query = query.where(Widget.status == status)
        query = query.order_by(desc(Widget.created_at)).limit(limit).offset(offset)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_for_workspace(
        self, workspace_id: UUID, status: WidgetStatus | None = None
    ) -> int:
        query = select(func.count(Widget.id)).where(Widget.workspace_id == workspace_id)
        if status:
            query = query.where(Widget.status == status)
        result = await self.session.execute(query)
        return result.scalar_one()

    async def update(self, widget: Widget) -> Widget:
        await self.session.flush()
        return widget

    async def delete(self, widget: Widget) -> None:
        await self.session.delete(widget)
        await self.session.flush()
