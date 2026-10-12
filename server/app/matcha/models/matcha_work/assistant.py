"""Request shapes for the Espresso assistant and its Google connection."""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class GoogleConnectRequest(BaseModel):
    # Assistant abilities to ask Google for on top of the base Gmail access
    # ("email_organize", "calendar"). Unknown names add nothing.
    abilities: list[str] = Field(default_factory=list, max_length=8)


class AbilityEnableRequest(BaseModel):
    # The version of the disclosure the person read and accepted. Must match
    # the current one for abilities that have a disclosure.
    consent_version: str | None = Field(default=None, max_length=64)
    settings: dict[str, Any] = Field(default_factory=dict)


class AssistantConversationRequest(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=100)
    # Reusing a client-generated key makes retrying a timed-out create safe.
    request_id: UUID


class AssistantConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class EmailFetchRequest(BaseModel):
    mailbox: Literal["unread", "read", "all"] = "unread"
    page_token: str | None = Field(default=None, min_length=1, max_length=2048)
