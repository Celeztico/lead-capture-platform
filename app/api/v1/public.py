import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import check_rate_limit
from app.schemas import PublicWidgetConfig, SubmissionResponse
from app.schemas.widget import WidgetConfiguration
from app.services.submission import SubmissionService
from app.services.submission_validation import (
    SubmissionValidationError,
    validate_body_size,
    validate_submission,
)
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


@router.post(
    "/public/v1/widgets/{public_id}/submissions",
    response_model=SubmissionResponse,
    status_code=201,
)
async def submit_lead(
    public_id: UUID,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Accept a visitor submission for an enabled widget.

    Validates input server-side, applies rate limiting and spam controls,
    persists the submission, and enqueues optional enrichment/notification
    jobs. Optional geolocation, email, and webhook failures do not invalidate
    a committed submission.
    """
    # --- Request body size limit -----------------------------------------
    body = await request.body()
    try:
        validate_body_size(body)
    except SubmissionValidationError as e:
        raise HTTPException(status_code=413, detail=e.message) from None

    # --- Parse JSON -------------------------------------------------------
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed JSON") from None

    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object")

    data = payload.get("data", {})
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Field 'data' must be a JSON object")

    # --- Client IP for rate limiting --------------------------------------
    client_ip = request.client.host if request.client else "unknown"

    # --- Rate limiting: per IP -------------------------------------------
    ip_allowed, ip_retry = check_rate_limit(f"ip:{client_ip}", 10, 60)
    if not ip_allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(ip_retry)},
        )

    # --- Resolve widget (active only) ------------------------------------
    widget_service = WidgetService(db)
    widget = await widget_service.get_active_widget_by_public_id(public_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found or not active")

    # --- Rate limiting: per widget ----------------------------------------
    widget_allowed, widget_retry = check_rate_limit(
        f"widget:{widget.id}", 30, 60
    )
    if not widget_allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for this widget. Try again later.",
            headers={"Retry-After": str(widget_retry)},
        )

    # --- Build widget configuration for validation ------------------------
    try:
        widget_config = WidgetConfiguration(**widget.configuration)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid widget configuration") from None

    # --- Validate submission fields ---------------------------------------
    submission_service = SubmissionService(db)
    try:
        validate_submission(data, widget_config, widget)
    except SubmissionValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=e.message,
        ) from None

    # --- Idempotency key --------------------------------------------------
    idempotency_key = request.headers.get("Idempotency-Key")

    # --- Source origin ----------------------------------------------------
    source_origin = request.headers.get("origin")

    # --- Persist submission -----------------------------------------------
    try:
        submission, status = await submission_service.submit(
            public_widget_id=public_id,
            data=data,
            source_origin=source_origin,
            idempotency_key=idempotency_key,
            client_ip=client_ip,
        )
    except ValueError as e:
        if str(e) == "IDEMPOTENCY_CONFLICT":
            raise HTTPException(
                status_code=409,
                detail="Idempotency key reused with different payload",
            ) from None
        raise HTTPException(status_code=400, detail=str(e)) from None

    # --- Return stable response -------------------------------------------
    return SubmissionResponse(
        id=submission.id,
        status="accepted",
        message="Your submission has been received.",
    )
