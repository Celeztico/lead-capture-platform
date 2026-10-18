from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Widget, WidgetStatus
from app.repositories import WidgetRepository


class WidgetService:
    def __init__(self, session: AsyncSession):
        self.widget_repo = WidgetRepository(session)
        self.session = session

    async def create_widget(
        self,
        workspace_id: UUID,
        name: str,
        configuration: dict,
    ) -> Widget:
        # Generate public ID
        public_id = uuid4()

        widget = await self.widget_repo.create(
            workspace_id=workspace_id,
            name=name,
            configuration=configuration,
            public_id=public_id,
        )
        await self.session.flush()
        return widget

    async def get_widget(
        self, widget_id: UUID, workspace_id: UUID
    ) -> Widget | None:
        return await self.widget_repo.get_by_id(widget_id, workspace_id)

    async def get_widget_by_public_id(
        self, public_id: UUID
    ) -> Widget | None:
        return await self.widget_repo.get_by_public_id(public_id)

    async def get_active_widget_by_public_id(
        self, public_id: UUID
    ) -> Widget | None:
        return await self.widget_repo.get_active_by_public_id(public_id)

    async def list_widgets(
        self,
        workspace_id: UUID,
        limit: int = 20,
        offset: int = 0,
        status: WidgetStatus | None = None,
    ) -> Sequence[Widget]:
        return await self.widget_repo.list_for_workspace(
            workspace_id, limit, offset, status
        )

    async def count_widgets(
        self, workspace_id: UUID, status: WidgetStatus | None = None
    ) -> int:
        return await self.widget_repo.count_for_workspace(workspace_id, status)

    async def update_widget(
        self,
        widget_id: UUID,
        workspace_id: UUID,
        name: str | None = None,
        configuration: dict | None = None,
        status: WidgetStatus | None = None,
    ) -> Widget | None:
        widget = await self.widget_repo.get_by_id(widget_id, workspace_id)
        if not widget:
            return None

        if name is not None:
            widget.name = name
        if configuration is not None:
            widget.configuration = configuration
            widget.config_version += 1
        if status is not None:
            widget.status = status

        await self.widget_repo.update(widget)
        return widget

    async def delete_widget(self, widget_id: UUID, workspace_id: UUID) -> bool:
        widget = await self.widget_repo.get_by_id(widget_id, workspace_id)
        if not widget:
            return False
        await self.widget_repo.delete(widget)
        return True

    async def get_public_config(self, public_id: UUID) -> dict | None:
        """Get only public-safe configuration for widget embedding."""
        widget = await self.get_active_widget_by_public_id(public_id)
        if not widget:
            return None

        # Return only public-safe fields
        config = widget.configuration
        return {
            "public_widget_id": str(widget.public_id),
            "status": widget.status.value,
            "config_version": widget.config_version,
            "configuration": {
                "title": config.get("title", ""),
                "description": config.get("description", ""),
                "submit_label": config.get("submit_label", "Submit"),
                "success_message": config.get("success_message", "Thank you!"),
                "fields": config.get("fields", []),
            },
        }
