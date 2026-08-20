"""Conversational chat-intake request/response models.

POST /ir/incidents/chat/turn is stateless: the client holds the transcript and
the accumulated fields, echoing both each turn. Consumed by
services/ir/ir_chat_intake.py and routes/ir_incidents/chat_intake.py.
"""
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

# Keep in lockstep with services/ir/ir_chat_intake.py:MAX_TURNS (12) — a
# transcript is a pair of messages per turn.
MAX_TRANSCRIPT_MESSAGES = 24
MAX_PUBLIC_CHAT_BODY_BYTES = 8 * 1024
MAX_PUBLIC_CHAT_MESSAGES = 24
MAX_PUBLIC_CHAT_MESSAGE_CHARS = 600


class ChatIntakeMessage(BaseModel):
    role: Literal["assistant", "user"]
    content: str = Field(..., max_length=2000)


class ChatIntakeFields(BaseModel):
    reported_by_name: Optional[str] = None
    occurred_at_text: Optional[str] = None
    location_id: Optional[str] = None
    description: Optional[str] = None
    witnesses: list[dict] = Field(default_factory=list)  # [{"name": str}]


class ChatIntakeTurnRequest(BaseModel):
    transcript: list[ChatIntakeMessage] = Field(..., max_length=MAX_TRANSCRIPT_MESSAGES)
    known_fields: ChatIntakeFields = Field(default_factory=ChatIntakeFields)


class ChatIntakeTurnResponse(BaseModel):
    assistant_message: str
    fields: ChatIntakeFields
    complete: bool
    turn_count: int
    error: bool = False


class PublicChatIntakeMessage(BaseModel):
    """A deliberately smaller public-chat message than the signed-in flow."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["assistant", "user"]
    content: str = Field(..., min_length=1, max_length=MAX_PUBLIC_CHAT_MESSAGE_CHARS)


class PublicChatIntakeFields(BaseModel):
    """Union of the anonymous and location-link report fields.

    Each public route only uses the fields appropriate to its report type; this
    shared shape lets the browser hold a stateless draft between chat turns.
    """

    model_config = ConfigDict(extra="forbid")

    reported_by_name: Optional[str] = Field(None, max_length=255)
    occurred_at_text: Optional[str] = Field(None, max_length=255)
    location: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=10_000)
    witnesses: list[dict] = Field(default_factory=list, max_length=50)
    involved_parties: Optional[str] = Field(None, max_length=2_000)
    contact_info: Optional[str] = Field(None, max_length=255)
    corrective_actions: Optional[str] = Field(None, max_length=10_000)


class PublicChatIntakeTurnRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcript: list[PublicChatIntakeMessage] = Field(
        ..., min_length=1, max_length=MAX_PUBLIC_CHAT_MESSAGES,
    )
    known_fields: PublicChatIntakeFields = Field(default_factory=PublicChatIntakeFields)


class PublicChatIntakeTurnResponse(BaseModel):
    assistant_message: str
    fields: PublicChatIntakeFields
    complete: bool
    turn_count: int
    error: bool = False
