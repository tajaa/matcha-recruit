"""Sym-chat request models (routes/matcha_work/sym_chat.py).

`config` stays a free-form dict here: its shape depends on `kind` and is
validated by `services/sym_chat/kinds.materialize_config`, which the route
turns into a 400 with the user-facing reason.
"""
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SymChatKind = Literal["schedule", "decide"]

MAX_TITLE_CHARS = 120
MAX_OBJECTIVE_CHARS = 500
MAX_MESSAGE_CHARS = 2000
MAX_INVITEES = 19  # + the organizer = 20 participants


class SymChatCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: SymChatKind
    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    objective: str = Field(default="", max_length=MAX_OBJECTIVE_CHARS)
    participant_ids: list[UUID] = Field(min_length=1, max_length=MAX_INVITEES)
    config: dict[str, Any] = Field(default_factory=dict)


class SymChatMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
