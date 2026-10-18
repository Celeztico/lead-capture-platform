from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SubmissionCreate(BaseModel):
    data: dict[str, Any] = Field(...)


class SubmissionResponse(BaseModel):
    id: UUID
    status: str = "accepted"
    message: str = "Your submission has been received."


class SubmissionItem(BaseModel):
    id: UUID
    widget_id: UUID
    created_at: datetime
    data: dict[str, Any]
    country_code: str | None = None
    country_name: str | None = None
    region: str | None = None
    city: str | None = None


class SubmissionListResponse(BaseModel):
    items: list[SubmissionItem]
    next_cursor: str | None = None


class AnalyticsSummary(BaseModel):
    workspace_id: UUID
    total_submissions: int
    by_widget: list[dict[str, Any]]
    daily: list[dict[str, Any]]
    by_country: list[dict[str, Any]]
