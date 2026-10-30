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
    MAX_BODY_BYTES,
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


MAX_IDEMPOTENCY_KEY_LENGTH = 255  # matches IdempotencyRecord.idempotency_key


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
    # --- Rate limiting: per IP -------------------------------------------
    # Checked before any body read or parsing so oversized or malformed
    # floods cannot bypass the limit.
    # Proxy note: request.client is the TCP peer. Behind a reverse proxy
    # that is the proxy address unless the ASGI server is configured with
    # explicit trusted-proxy headers; forwarded client headers are not
    # read here because trusting them blindly would allow spoofing.
    client_ip = request.client.host if request.client else "unknown"
    ip_allowed, ip_retry = check_rate_limit(
        f"ip:{client_ip}",
        settings.rate_limit_per_minute_ip,
        60,
    )
    if not ip_allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(ip_retry)},
        )

    # --- Request body size limit -----------------------------------------
    # Reject on the declared Content-Length before reading, then bound the
    # streamed read so chunked uploads cannot buffer unbounded data.
    content_length = request.headers.get("content-length", "")
    if content_length.isdigit() and int(content_length) > MAX_BODY_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Request body exceeds {MAX_BODY_BYTES // 1_000_000} MB limit.",
        )
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            break
    try:
        validate_body_size(bytes(body))
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

    # --- Idempotency key --------------------------------------------------
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key is not None and (
        not idempotency_key or len(idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH
    ):
        raise HTTPException(
            status_code=400,
            detail=f"Idempotency-Key must be 1-{MAX_IDEMPOTENCY_KEY_LENGTH} characters.",
        )

    # --- Resolve widget (active only) ------------------------------------
    widget_service = WidgetService(db)
    widget = await widget_service.get_active_widget_by_public_id(public_id)
    if widget is None:
        raise HTTPException(status_code=404, detail="Widget not found or not active")

    # --- Rate limiting: per widget ----------------------------------------
    widget_allowed, widget_retry = check_rate_limit(
        f"widget:{widget.id}",
        settings.rate_limit_per_minute_widget,
        60,
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
        error_status = 400 if e.code == "SPAM_DETECTED" else 422
        raise HTTPException(status_code=error_status, detail=e.message) from None

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
        if str(e) == "IDEMPOTENCY_IN_PROGRESS":
            raise HTTPException(
                status_code=409,
                detail="Submission with this idempotency key is still in progress",
            ) from None
        raise HTTPException(status_code=400, detail=str(e)) from None

    # --- Return stable response -------------------------------------------
    return SubmissionResponse(
        id=submission.id,
        status="accepted",
        message="Your submission has been received.",
    )
