"""Submission validation for the public submission endpoint.

Enforces server-side validation rules that the client cannot be trusted to
enforce:

* Honeypot field must be empty (spam control)
* Field count bounded (max 20)
* Per-field string length bounded (max 2000 chars)
* Required fields present and non-empty
* Unknown fields rejected against widget configuration

All validation errors raise ``SubmissionValidationError`` with a stable
error code and human-readable message.
"""

from typing import Any

from app.models import Widget
from app.schemas.widget import WidgetConfiguration


class SubmissionValidationError(Exception):
    """Raised when a submission fails validation.

    Attributes:
        code: Stable machine-readable error code.
        message: Safe human-readable message.
        details: Optional list of field-level validation details.
    """

    def __init__(
        self,
        code: str,
        message: str,
        details: list[dict[str, str]] | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or []


# Honeypot field name — must be empty for legitimate submissions.
HONEYPOT_FIELD = "website_url"

# Configuration limits
MAX_FIELD_COUNT = 20
MAX_FIELD_LENGTH = 2000


def validate_submission(
    data: dict[str, Any],
    config: WidgetConfiguration,
    widget: Widget,
) -> None:
    """Validate a submission against widget configuration and abuse rules.

    Args:
        data: The submitted field data (the ``data`` object from the request).
        config: The widget's validated public configuration.
        widget: The widget model (used for workspace scoping).

    Raises:
        SubmissionValidationError: If validation fails.
    """
    # --- Honeypot check --------------------------------------------------
    # A hidden field that legitimate users never see/fill. Bots often fill
    # every field they encounter. If present and non-empty, reject.
    honeypot_value = data.get(HONEYPOT_FIELD)
    if honeypot_value is not None and str(honeypot_value).strip() != "":
        raise SubmissionValidationError(
            code="SPAM_DETECTED",
            message="Submission rejected by spam filter.",
        )

    # --- Field count limit ----------------------------------------------
    field_names = list(data.keys())
    if len(field_names) > MAX_FIELD_COUNT:
        raise SubmissionValidationError(
            code="TOO_MANY_FIELDS",
            message=f"Maximum {MAX_FIELD_COUNT} fields allowed.",
            details=[
                {"field": "__body__", "reason": f"Field count {len(field_names)} exceeds limit {MAX_FIELD_COUNT}."}
            ],
        )

    # Build a lookup of allowed field names from widget configuration.
    allowed_fields = {f.name for f in config.fields}
    required_fields = {f.name for f in config.fields if f.required}

    # --- Validate each submitted field ----------------------------------
    for name, value in data.items():
        # Unknown field rejection
        if name not in allowed_fields:
            raise SubmissionValidationError(
                code="UNKNOWN_FIELD",
                message=f"Field '{name}' is not supported by this widget.",
                details=[{"field": name, "reason": "Unknown field."}],
            )

        # Type/length validation
        field_config = next(f for f in config.fields if f.name == name)

        if isinstance(value, str):
            if len(value) > MAX_FIELD_LENGTH:
                raise SubmissionValidationError(
                    code="FIELD_TOO_LONG",
                    message=f"Field '{name}' exceeds maximum length.",
                    details=[
                        {
                            "field": name,
                            "reason": f"Length {len(value)} exceeds limit {MAX_FIELD_LENGTH}.",
                        }
                    ],
                )

        # Required fields must be present and non-empty (for strings)
        if name in required_fields:
            if value is None or (isinstance(value, str) and value.strip() == ""):
                raise SubmissionValidationError(
                    code="MISSING_REQUIRED_FIELD",
                    message=f"Required field '{name}' is missing or empty.",
                    details=[{"field": name, "reason": "Required field is missing or empty."}],
                )


def validate_body_size(body_bytes: bytes, max_bytes: int = 1_000_000) -> None:
    """Validate request body size.

    Args:
        body_bytes: Raw request body bytes.
        max_bytes: Maximum allowed body size (default 1 MB).

    Raises:
        SubmissionValidationError: If body exceeds the limit.
    """
    if len(body_bytes) > max_bytes:
        raise SubmissionValidationError(
            code="PAYLOAD_TOO_LARGE",
            message=f"Request body exceeds {max_bytes // 1_000_000} MB limit.",
            details=[
                {
                    "field": "__body__",
                    "reason": f"Body size {len(body_bytes)} bytes exceeds limit {max_bytes} bytes.",
                }
            ],
        )