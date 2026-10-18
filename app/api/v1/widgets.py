from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_workspace_id
from app.core.database import get_db
from app.models import WidgetStatus
from app.schemas import (
    EmbedResponse,
    WidgetCreate,
    WidgetListResponse,
    WidgetResponse,
    WidgetUpdate,
)
from app.services.widget import WidgetService

router = APIRouter(prefix="/api/v1/widgets", tags=["widgets"])


@router.post("", response_model=WidgetResponse, status_code=status.HTTP_201_CREATED)
async def create_widget(
    widget_in: WidgetCreate,
    workspace_id: UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    # Verify the workspace_id matches the authenticated user's workspace
    if widget_in.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create widget in another workspace",
        )

    service = WidgetService(db)
    widget = await service.create_widget(
        workspace_id=workspace_id,
        name=widget_in.name,
        configuration=widget_in.configuration.model_dump(),
    )
    return widget


@router.get("", response_model=WidgetListResponse)
async def list_widgets(
    workspace_id: UUID = Depends(get_current_workspace_id),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: WidgetStatus | None = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
):
    service = WidgetService(db)
    widgets = await service.list_widgets(
        workspace_id=workspace_id,
        limit=limit,
        offset=offset,
        status=status_filter,
    )
    # Convert to response schema
    widget_responses = [WidgetResponse.model_validate(w) for w in widgets]
    return WidgetListResponse(items=widget_responses, next_cursor=None)


@router.get("/{widget_id}", response_model=WidgetResponse)
async def get_widget(
    widget_id: UUID,
    workspace_id: UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    service = WidgetService(db)
    widget = await service.get_widget(widget_id, workspace_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    return widget


@router.patch("/{widget_id}", response_model=WidgetResponse)
async def update_widget(
    widget_id: UUID,
    widget_in: WidgetUpdate,
    workspace_id: UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    service = WidgetService(db)
    widget = await service.update_widget(
        widget_id=widget_id,
        workspace_id=workspace_id,
        name=widget_in.name,
        configuration=widget_in.configuration.model_dump() if widget_in.configuration else None,
        status=WidgetStatus(widget_in.status) if widget_in.status else None,
    )
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    return widget


@router.delete("/{widget_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_widget(
    widget_id: UUID,
    workspace_id: UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    service = WidgetService(db)
    deleted = await service.delete_widget(widget_id, workspace_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Widget not found")


@router.get("/{widget_id}/embed", response_model=EmbedResponse)
async def get_embed_snippet(
    widget_id: UUID,
    workspace_id: UUID = Depends(get_current_workspace_id),
    db: AsyncSession = Depends(get_db),
):
    service = WidgetService(db)
    widget = await service.get_widget(widget_id, workspace_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found")

    # Generate embed snippet
    base_url = "http://localhost:8000"  # In production, this should come from config
    script_url = f"{base_url}/widget/v1/widget.1.js"
    snippet = (
        f'<div id="lead-capture-widget" data-widget-id="{widget.public_id}"></div>\n'
        f'<script src="{script_url}" defer></script>'
    )

    return EmbedResponse(snippet=snippet, script_url=script_url)
