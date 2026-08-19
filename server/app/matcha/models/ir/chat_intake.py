"""Conversational chat-intake request/response models.

POST /ir/incidents/chat/turn is stateless: the client holds the transcript and
the accumulated fields, echoing both each turn. Consumed by
services/ir/ir_chat_intake.py and routes/ir_incidents/chat_intake.py.
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field

# Keep in lockstep with services/ir/ir_chat_intake.py:MAX_TURNS (12) — a
# transcript is a pair of messages per turn.
MAX_TRANSCRIPT_MESSAGES = 24


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
