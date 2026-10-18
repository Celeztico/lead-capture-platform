from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class WidgetField(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    type: Literal["text", "email", "textarea"]
    label: str = Field(..., min_length=1, max_length=100)
    required: bool = True
    placeholder: str | None = Field(None, max_length=200)


class WidgetConfiguration(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=500)
    submit_label: str = Field("Submit", min_length=1, max_length=50)
    success_message: str = Field("Thank you for your submission!", min_length=1, max_length=300)
    fields: list[WidgetField] = Field(..., min_length=1, max_length=20)


class WidgetCreate(BaseModel):
    workspace_id: UUID
    name: str = Field(..., min_length=1, max_length=160)
    configuration: WidgetConfiguration


class WidgetUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    configuration: WidgetConfiguration | None = None
    status: str | None = Field(None, pattern="^(active|disabled|archived)$")


class WidgetResponse(BaseModel):
    id: UUID
    public_id: UUID
    workspace_id: UUID
    name: str
    status: str
    configuration: WidgetConfiguration
    config_version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WidgetListResponse(BaseModel):
    items: list[WidgetResponse]
    next_cursor: str | None = None


class PublicWidgetConfig(BaseModel):
    public_widget_id: UUID
    status: str
    config_version: int
    configuration: WidgetConfiguration


class EmbedResponse(BaseModel):
    snippet: str
    script_url: str
