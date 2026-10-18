import logging
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)


async def send_email_notification(
    submission_id: UUID,
    workspace_id: UUID,
    to_email: str,
    subject: str,
    body: str,
) -> bool:
    """
    Send email notification for a new lead.
    Stub implementation - logs only for internship MVP.
    """
    settings = get_settings()
    if not settings.smtp_host:
        logger.info(
            "Email notification skipped (no SMTP configured)",
            extra={"submission_id": str(submission_id)},
        )
        return True  # Don't fail the job

    # TODO: Implement actual SMTP sending
    logger.info(
        "Would send email notification",
        extra={
            "submission_id": str(submission_id),
            "to": to_email,
            "subject": subject,
        },
    )
    return True


async def deliver_webhook(
    submission_id: UUID,
    workspace_id: UUID,
    url: str,
    payload: dict,
    secret: str | None = None,
) -> bool:
    """
    Deliver webhook for a new lead.
    Stub implementation - logs only for internship MVP.
    """
    # TODO: Implement actual webhook delivery with HMAC signature
    logger.info(
        "Would deliver webhook",
        extra={
            "submission_id": str(submission_id),
            "url": url,
            "payload_keys": list(payload.keys()),
        },
    )
    return True
