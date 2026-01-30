from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel


class ConversationCreate(BaseModel):
    title: Optional[str] = None


class ConversationResponse(BaseModel):
    id: UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str


class AttachmentResponse(BaseModel):
    url: str
    filename: str
    content_type: str
    size: int


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime
    attachments: List[AttachmentResponse] = []


class ConversationDetail(BaseModel):
    id: UUID
    title: Optional[str]
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]
