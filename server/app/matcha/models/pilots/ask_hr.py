"""Request/response shapes for the employee "Ask HR" portal surface."""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AskHrSessionCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class AskHrSessionResponse(BaseModel):
    id: UUID
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AskHrMessageResponse(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "system"]
    content: str
    # citations / dropped_citations / hard_stop_category
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime


class AskHrChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
