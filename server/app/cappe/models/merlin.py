"""Pydantic shapes — Merlin AI chat editing (see services/merlin/turn.py + merlin/catalog.py)."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

class CappeMerlinHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)
    # Compact recap of what an assistant turn changed (e.g. "set hero.heading;
    # added faq at 3"), sent instead of raw ops to keep the transcript cheap.
    ops_summary: Optional[str] = Field(default=None, max_length=4000)


class CappeMerlinAttachment(BaseModel):
    """One user-attached image. `url` must be this deployment's own storage —
    `services/merlin/attachments.py:_is_own_storage` enforces that server-side;
    an arbitrary URL is dropped rather than fetched (SSRF guard)."""
    url: str = Field(max_length=2000)
    mime: Optional[str] = None


class CappeMerlinChatRequest(BaseModel):
    """Client state is the source of truth — Merlin auto-applies to editor
    state client-side and nothing persists until the user hits Save, so the
    server never reads blocks/theme from the DB for this endpoint.

    The one thing that IS persisted is the transcript (`conversation_id`,
    migration zzzzcappe22): the ops still round-trip through the client, but the
    conversation itself lives server-side so it survives a reload.
    """
    page_id: str
    # Omitted on the first turn — the route opens a conversation titled from
    # the message and returns its id on the response.
    conversation_id: Optional[UUID] = None
    message: str = Field(min_length=1, max_length=2000)
    # The whole snapshot is serialized into the prompt (twice, if the
    # validation retry fires) and Merlin shares the GLOBAL Gemini budget, so
    # every list here is bounded. The byte-size of blocks+theme is additionally
    # capped in the route — item counts alone don't bound a page's content.
    # Fallback only: when `conversation_id` is set the server loads the
    # transcript from the DB and ignores this. Kept so a client mid-deploy
    # (or the very first turn of a new conversation) still has context.
    history: list[CappeMerlinHistoryTurn] = Field(default_factory=list, max_length=20)
    blocks: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    theme: dict[str, Any] = Field(default_factory=dict)
    # Clamped server-side to what the plan allows — an unknown or over-plan
    # tier degrades to 'lite' rather than 403ing (see merlin.resolve_model_tier).
    # 'auto' (the client default) is resolved per request by
    # `services/merlin/routing.py:route_tier`.
    model_tier: Literal["auto", "lite", "regular", "max"] = "auto"
    # The block the user currently has selected in the editor, so "this
    # section" resolves to something instead of being guessed at.
    selected_block: Optional[str] = Field(default=None, max_length=100)
    # Images the user attached to THIS message. Capped well above
    # merlin.attachments.MAX_ATTACHMENTS (4) — the module drops the excess
    # rather than 422ing a slightly-over request.
    attachments: list[CappeMerlinAttachment] = Field(default_factory=list, max_length=8)


class CappeMerlinRejection(BaseModel):
    op: dict[str, Any]
    reason: str


class CappeMerlinChatResponse(BaseModel):
    message: str
    ops: list[dict[str, Any]]
    rejected: list[CappeMerlinRejection] = Field(default_factory=list)
    # The tier actually used — may differ from the request if it was clamped
    # or picked by the auto router.
    tier: Literal["lite", "regular", "max"] = "lite"
    # True when `auto` chose this tier, so the panel can say "Auto → Max"
    # instead of leaving the user unable to tell whether Auto does anything.
    routed: bool = False
    # The conversation this turn was recorded in — echoed back so a client that
    # sent none can adopt the one the route opened.
    conversation_id: Optional[UUID] = None
    # The stored assistant message, so the client can report back what it
    # actually applied (see CappeMerlinResultsUpdate).
    message_id: Optional[UUID] = None


# --- Conversation persistence (migration zzzzcappe22) -----------------------

class CappeMerlinConversation(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class CappeMerlinStoredMessage(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    # Op-result chips as the panel rendered them ({ok, summary}).
    results: Optional[list[dict[str, Any]]] = None
    # Agent tool-loop trace (phase 2) and chat image uploads (phase 4).
    steps: Optional[list[dict[str, Any]]] = None
    attachments: Optional[list[dict[str, Any]]] = None
    # The validated op log for an ASSISTANT message (migration zzzzcappe24) —
    # set alongside `results` when the client reported back what it applied,
    # but ALSO set (with `results` still None) when a disconnect meant the
    # client never got the chance to apply anything. That combination is what
    # the panel reads as "this turn's changes were never applied — offer to
    # apply them now" rather than a normal completed turn.
    ops: Optional[list[dict[str, Any]]] = None
    tier: Optional[str] = None
    created_at: datetime


class CappeMerlinConversationDetail(CappeMerlinConversation):
    messages: list[CappeMerlinStoredMessage] = Field(default_factory=list)


class CappeMerlinConversationCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=120)


class CappeMerlinConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class CappeMerlinResultsUpdate(BaseModel):
    """What the client actually applied, reported back after the fact.

    The server returns ops; only the CLIENT knows which of them landed (it
    applies to live editor state, which may have drifted during the round
    trip). It owns the human-readable summaries too, so it reports them here
    instead of the server guessing — the stored chips are the same ones the
    panel rendered, and they become the `ops_summary` context of later turns.
    """
    results: list[dict[str, Any]] = Field(default_factory=list, max_length=60)


__all__ = [
    "CappeMerlinHistoryTurn",
    "CappeMerlinAttachment",
    "CappeMerlinChatRequest",
    "CappeMerlinRejection",
    "CappeMerlinChatResponse",
    "CappeMerlinConversation",
    "CappeMerlinStoredMessage",
    "CappeMerlinConversationDetail",
    "CappeMerlinConversationCreate",
    "CappeMerlinConversationUpdate",
    "CappeMerlinResultsUpdate",
]
