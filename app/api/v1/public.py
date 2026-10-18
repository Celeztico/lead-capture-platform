from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas import PublicWidgetConfig
from app.services.widget import WidgetService

router = APIRouter(tags=["public"])


@router.get("/public/v1/widgets/{public_id}/config", response_model=PublicWidgetConfig)
async def get_public_widget_config(public_id: UUID, db: AsyncSession = Depends(get_db)):
    service = WidgetService(db)
    config = await service.get_public_config(public_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Widget not found")
    return config
