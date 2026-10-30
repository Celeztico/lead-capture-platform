from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.schemas import PublicWidgetConfig
from app.services.widget import WidgetService

router = APIRouter(tags=["public"])

settings = get_settings()


def _normalize_etag(etag: str) -> str:
    """Strip the weak validator prefix for weak comparison (RFC 9110)."""
    return etag[2:] if etag.startswith("W/") else etag


def if_none_match_matches(header_value: str, etag: str) -> bool:
    """Evaluate an If-None-Match header against the current ETag (weak compare)."""
    if not header_value:
        return False
    current = _normalize_etag(etag)
    for candidate in header_value.split(","):
        candidate = candidate.strip()
        if candidate == "*" or _normalize_etag(candidate) == current:
            return True
    return False


@router.get("/public/v1/widgets/{public_id}/config", response_model=PublicWidgetConfig)
async def get_public_widget_config(
    public_id: UUID,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    service = WidgetService(db)
    config = await service.get_public_config(public_id)
    if config is None:
        raise HTTPException(status_code=404, detail="Widget not found")

    # Weak ETag based on config_version for cache invalidation
    etag = 'W/"{}"'.format(config["config_version"])

    # Cache headers: short revalidation interval
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    # Vary by Origin to prevent cross-tenant cache sharing
    response.headers["Vary"] = "Origin"

    # Conditional request: return 304 if the client's ETag still matches
    if if_none_match_matches(request.headers.get("if-none-match", ""), etag):
        response.status_code = 304
        return response

    return config
