"""Request/response shapes for the broker↔company chat.

The same conversation/message rows are surfaced to two audiences — a broker
member (via ``routes/broker/chat.py``) and a company user (via
``routes/broker_chat_company.py``) — so the response models are side-agnostic
and carry ``sender_side`` / ``created_by_side`` for the client to render "us"
vs "them".
"""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# Reference kinds a conversation/message may anchor to. Kept as a permissive
# Literal so a message can point at any shared record the two parties discuss.
ReferenceType = Literal[
    "claim",
    "loss_run",
    "document",
    "flagged_data",
    "incident",
    "submission",
    "policy",
    "general",
]

Side = Literal["broker", "company"]


class MessageReference(BaseModel):
    """A pointer to a shared record under discussion (a claim, doc, incident…)."""
    type: ReferenceType
    id: Optional[UUID] = None
    label: str = Field(..., min_length=1, max_length=200)


class ConversationCreate(BaseModel):
    # Broker side supplies company_id (which client to talk to). Company side
    # supplies broker_id only when the company is linked to more than one broker.
    company_id: Optional[UUID] = None
    broker_id: Optional[UUID] = None
    subject: Optional[str] = Field(default=None, max_length=200)
    reference: Optional[MessageReference] = None
    # Optional opening message so the thread isn't born empty.
    body: Optional[str] = Field(default=None, max_length=8000)


class MessageCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)
    reference: Optional[MessageReference] = None
    # Idempotency token — a retried send with the same value returns the
    # original message instead of duplicating it.
    client_message_id: Optional[UUID] = None


class MessageEdit(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)


class MarkReadRequest(BaseModel):
    # Newest message the caller has seen. Omit to mark the whole thread read.
    last_read_message_id: Optional[UUID] = None


class MessageOut(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_user_id: UUID
    sender_side: Side
    sender_name: str
    body: str
    reference: Optional[MessageReference] = None
    client_message_id: Optional[UUID] = None
    created_at: datetime
    edited_at: Optional[datetime] = None


class ConversationOut(BaseModel):
    id: UUID
    broker_id: UUID
    company_id: UUID
    company_name: Optional[str] = None
    broker_name: Optional[str] = None
    subject: Optional[str] = None
    status: Literal["open", "archived"]
    reference: Optional[MessageReference] = None
    created_by_side: Side
    last_message_at: Optional[datetime] = None
    last_message_preview: Optional[str] = None
    unread_count: int = 0
    created_at: datetime


class ConversationListOut(BaseModel):
    conversations: list[ConversationOut]
    total_unread: int = 0
