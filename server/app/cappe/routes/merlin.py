"""Merlin — AI chat editing for the Cappe page builder.

Open to every plan on the `lite` model tier; `regular`/`pro` need Pro/Business
(`is_premium_plan`, `services/design_gate.py`). Lite is cheap enough to run as
an upgrade funnel rather than something free users never see — the tier is
CLAMPED, not 403'd, so a stale client asking for pro degrades quietly.

Until the token wallet lands (phase B), the per-account hourly rate limit is
the only consumption guard, so free plans get a tighter one than paid.

Cappe's first Gemini integration. The PAGE is still never written here — the
client applies the returned ops to its own editor state and persists via the
existing page/site PUT routes when the user hits Save. What is written is the
TRANSCRIPT (`cappe_merlin_conversations` / `_messages`, migration zzzzcappe22,
owned by `services/merlin/store.py`), so a conversation survives a reload and a
page can hold several of them. See `services/merlin/turn.py` for the op
validation and prompt logic.

`/merlin/chat` (single-shot) and `/merlin/agent` (the loop, falling back to
single-shot on a non-agentic tier/plan) share one preamble — size gate, tier
routing, rate limit, attachment load, conversation resolution — via
`_prepare_turn`, so the two can't drift out of sync with each other the way
they once did as independently hand-maintained copies.
"""
import json
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ...core.services.rate_limiter import RateLimitExceeded
from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeMerlinChatRequest,
    CappeMerlinChatResponse,
    CappeMerlinConversation,
    CappeMerlinConversationCreate,
    CappeMerlinConversationDetail,
    CappeMerlinConversationUpdate,
    CappeMerlinResultsUpdate,
)
from ..services.design_gate import gate_content, gate_theme, is_premium_plan
from ..services.merlin import store as merlin_store
from ..services.merlin.agent_stream import stream_agent_turn
from ..services.merlin.turn import run_merlin_turn
from ..services.merlin.agent import AGENT_TIERS
from ..services.merlin.attachments import load_attachments
from ..services.merlin.ops import build_merlin_schema
from ..services.merlin.routing import route_tier
from ..services.render import render_site_html
from ._shared import get_owned_site, loads

router = APIRouter()


# The registry-derived op/block/design/theme vocabulary as one JSON document —
# the single source of truth the editor can read instead of hand-mirroring it in
# blockSchemas.ts. Built once on first request and cached: static per deploy, but
# built lazily (not at import) so a registry-data error degrades to a 500 on this
# one endpoint rather than failing the whole cappe router's import at boot.
_merlin_schema_cache: dict | None = None


@router.get("/merlin/schema")
async def merlin_schema(account: CappeAccount = Depends(require_cappe_account)):
    """The Merlin vocabulary (ops, block fields, design keys, theme keys, limits)
    generated from the server registries. Read-only; account-gated for parity
    with the chat route."""
    global _merlin_schema_cache
    if _merlin_schema_cache is None:
        _merlin_schema_cache = build_merlin_schema()
    return _merlin_schema_cache

# Turns per account per hour. Paid plans buy headroom; free is a taste.
_FREE_HOURLY_LIMIT = 10
_PAID_HOURLY_LIMIT = 60
# Agent turns are several Gemini calls + screenshots each, so they get their own
# tighter counter rather than sharing the single-shot allowance.
_AGENT_HOURLY_LIMIT = 20
# Serialized blocks+theme ceiling. Generous for a real page (a dense one is
# tens of KB) but far below nginx's 100MB body cap.
_MAX_SNAPSHOT_BYTES = 300_000


# ---------------------------------------------------------------------------
# Conversations (migration zzzzcappe22)
#
# The transcript lives server-side now; the ops still round-trip through the
# client, so none of this changes the client-state-is-truth contract.
# ---------------------------------------------------------------------------

async def _assert_page_in_site(conn, page_id: UUID, site_id: UUID) -> None:
    """404 unless the page belongs to the (already ownership-checked) site."""
    if not await conn.fetchval(
        "SELECT 1 FROM cappe_pages WHERE id = $1 AND site_id = $2", page_id, site_id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")


@router.get(
    "/sites/{site_id}/pages/{page_id}/merlin/conversations",
    response_model=list[CappeMerlinConversation],
)
async def list_merlin_conversations(
    site_id: UUID,
    page_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
):
    """This page's Merlin conversations, most-recently-used first."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        await _assert_page_in_site(conn, page_id, site["id"])
        return await merlin_store.list_conversations(conn, page_id, account.id)


@router.post(
    "/sites/{site_id}/pages/{page_id}/merlin/conversations",
    response_model=CappeMerlinConversation,
    status_code=status.HTTP_201_CREATED,
)
async def create_merlin_conversation(
    site_id: UUID,
    page_id: UUID,
    body: CappeMerlinConversationCreate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        await _assert_page_in_site(conn, page_id, site["id"])
        return await merlin_store.create_conversation(
            conn,
            account_id=account.id,
            site_id=site["id"],
            page_id=page_id,
            title=body.title,
        )


@router.get(
    "/merlin/conversations/{conversation_id}",
    response_model=CappeMerlinConversationDetail,
)
async def get_merlin_conversation(
    conversation_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        convo = await merlin_store.get_owned_conversation(conn, conversation_id, account.id)
        messages = await merlin_store.get_messages(conn, conversation_id)
    return {**convo, "messages": messages}


@router.patch(
    "/merlin/conversations/{conversation_id}",
    response_model=CappeMerlinConversation,
)
async def rename_merlin_conversation(
    conversation_id: UUID,
    body: CappeMerlinConversationUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        convo = await merlin_store.get_owned_conversation(conn, conversation_id, account.id)
        await merlin_store.rename_conversation(conn, conversation_id, body.title)
        return {**convo, "title": body.title[:120]}


@router.delete("/merlin/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_merlin_conversation(
    conversation_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await merlin_store.get_owned_conversation(conn, conversation_id, account.id)
        await merlin_store.delete_conversation(conn, conversation_id)


def _recent_history_tail(history: list, n: int = 2) -> Optional[str]:
    """A short recap of the last few turns for the auto-router's classifier
    (`merlin.routing.route_tier`'s `history_tail` — previously never passed by
    either caller, so an ambiguous follow-up like "make it match the others"
    was classified with no idea what "it" or "the others" refers to).

    Built from `body.history` — the CLIENT-resent transcript — rather than the
    server-loaded conversation, because tier routing happens BEFORE the DB
    call that would resolve which conversation this is; the client always
    sends its own recent messages here regardless of whether `conversation_id`
    is set (see `useMerlin.ts`'s `send`), so this is available up front.
    Content is hard-truncated — this is a routing hint, not a replay."""
    recent = history[-n:]
    if not recent:
        return None
    lines = [f"{t.role}: {t.content[:200]}" for t in recent if t.content]
    return "\n".join(lines) or None


def _parse_page_id(raw: str) -> Optional[UUID]:
    """`page_id` rides in as a string on the chat request (it predates
    persistence). A non-UUID means we can't record the turn — that degrades to
    an unrecorded turn, not a 4xx, since the edit itself doesn't need it."""
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


async def _resolve_conversation(
    conn, *, body: CappeMerlinChatRequest, site, page_uuid: Optional[UUID], account: CappeAccount
) -> Optional[dict]:
    """The conversation this turn belongs to: the one the client named, else a
    fresh one titled from the message. None when it can't be recorded at all.

    A `conversation_id` the account doesn't own 404s (via
    `get_owned_conversation`) rather than silently opening a new conversation —
    a wrong id is a bug or a probe, and quietly writing elsewhere would hide it.
    Ownership alone isn't enough, though: it's scoped to the ACCOUNT, not the
    page this request is editing, so a conversation opened for page A carried
    over onto page B (a stale client ref, a hand-rolled request) would load
    page A's transcript as history for an edit to page B, and persist the
    turn there instead of anywhere page B's panel will ever show it. 404 the
    same way an unowned id does — both are "this id isn't valid here".

    A setup-kind conversation (`page_id IS NULL`) must also be rejected here
    even when the request's own `page_id` is absent/non-UUID (`page_uuid is
    None`) — otherwise this route would happily load the dashboard concierge's
    transcript as page-editor history and persist a page-editor turn into it.
    `kind` must be `'page'`, not just "id owned and page matches".
    """
    if body.conversation_id is not None:
        convo = await merlin_store.get_owned_conversation(
            conn, body.conversation_id, account.id
        )
        if convo.get("kind") != "page" or (page_uuid is not None and convo["page_id"] != page_uuid):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found"
            )
        return convo
    if page_uuid is None:
        return None
    if not await conn.fetchval(
        "SELECT 1 FROM cappe_pages WHERE id = $1 AND site_id = $2", page_uuid, site["id"]
    ):
        return None
    return await merlin_store.create_conversation(
        conn,
        account_id=account.id,
        site_id=site["id"],
        page_id=page_uuid,
        title=merlin_store.title_from_message(body.message),
    )


@dataclass
class _PreparedTurn:
    """Everything both turn routes need before calling into `services/merlin*`
    — the shared preamble `_prepare_turn` builds. `site` is a DB row (still a
    Record/Mapping, not a model) so callers keep indexing it the same way they
    already did."""
    site: Any
    conversation: Optional[dict]
    history: list[dict[str, Any]]
    attachments: list[dict[str, Any]]
    tier: str
    routed: bool
    agentic: bool


async def _prepare_turn(
    site_id: UUID, body: CappeMerlinChatRequest, account: CappeAccount, *, allow_agentic: bool,
) -> _PreparedTurn:
    """Shared preamble for `/merlin/chat` and `/merlin/agent`: size gate → tier
    routing → rate limit → attachment load → conversation resolution. The two
    routes used to hand-repeat this (drift risk — see the module docstring);
    this is the single copy.

    `allow_agentic` is what lets ONE function serve both callers' different
    rate-limit policy: `/merlin/agent` may run the agent loop (several Gemini
    calls + screenshots, its own tighter hourly counter) once `tier` resolves
    into an agent tier on a premium plan; `/merlin/chat` never runs the loop at
    all, so it passes `allow_agentic=False` and always draws from the single-
    shot counter, exactly as it did before this was shared.

    Order is preserved exactly: the size gate runs before any Gemini call OR
    any write; both rate-limit gates run before the transcript write, so a
    rejected turn never leaves an unanswered question in the history.
    """
    # Size gate BEFORE any Gemini call OR any write. Pydantic bounds the item
    # counts, but a 200-block page can still be megabytes of text, and the whole
    # snapshot is inlined into the prompt (twice, if the validation retry
    # fires). Merlin draws on the global `api_rate_limits` Gemini budget shared
    # with IR / compliance / ER, so an oversized page here degrades those too.
    snapshot_bytes = len(json.dumps(body.blocks)) + len(json.dumps(body.theme))
    if snapshot_bytes > _MAX_SNAPSHOT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="This page is too large for Merlin — edit it in Form or Canvas mode.",
        )

    premium = is_premium_plan(account.plan)
    tier, routed = await route_tier(
        body.model_tier, account.plan,
        message=body.message, has_selected_block=bool(body.selected_block),
        history_tail=_recent_history_tail(body.history),
    )
    agentic = allow_agentic and premium and tier in AGENT_TIERS
    # Cost guard until the token wallet exists: free plans get a smaller
    # hourly allowance than paid ones, keyed per account (not per IP). Runs
    # before the transcript write — a rejected turn shouldn't leave a
    # question in the history that never got an answer.
    if agentic:
        await check_rate_limit(str(account.id), "cappe_merlin_agent", _AGENT_HOURLY_LIMIT, 3600)
    else:
        hourly = _PAID_HOURLY_LIMIT if premium else _FREE_HOURLY_LIMIT
        await check_rate_limit(str(account.id), "cappe_merlin_chat", hourly, 3600)

    page_uuid = _parse_page_id(body.page_id)
    # Fetched before the DB block: it's an S3 round trip, not a DB one, and
    # doesn't need the connection. Never fetches an arbitrary URL — see
    # merlin/attachments.py:_is_own_storage.
    attachments = await load_attachments([a.model_dump() for a in body.attachments])
    attachment_meta = [{"url": a["url"], "mime": a["mime"]} for a in attachments]

    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        # Resolve the conversation BEFORE the model call: it's what history is
        # read from, and a client that sent none needs the id back even if the
        # turn itself degrades to a message-only response.
        conversation = await _resolve_conversation(
            conn, body=body, site=site, page_uuid=page_uuid, account=account
        )
        if conversation is not None:
            history = await merlin_store.load_history(conn, conversation["id"])
            await merlin_store.add_message(
                conn, conversation["id"], role="user", content=body.message,
                attachments=attachment_meta or None,
            )
        else:
            # Nothing to record against (no page row — deleted mid-session,
            # say). The turn still runs, falling back to the client's resent
            # transcript.
            history = [t.model_dump() for t in body.history]

    return _PreparedTurn(
        site=site, conversation=conversation, history=history, attachments=attachments,
        tier=tier, routed=routed, agentic=agentic,
    )


@router.post("/sites/{site_id}/merlin/chat", response_model=CappeMerlinChatResponse)
async def merlin_chat(
    site_id: UUID,
    body: CappeMerlinChatRequest,
    account: CappeAccount = Depends(require_cappe_account),
):
    """One Merlin turn: chat message + current editor snapshot in, a small
    validated op plan out. Client-state-is-truth — this never reads or writes
    `cappe_pages`/`cappe_sites`; it only confirms the caller owns the site.

    The transcript IS written (`cappe_merlin_*`, migration zzzzcappe22): the
    user message is stored before the Gemini call, the assistant message after,
    so a turn that fails mid-flight still leaves the question in the history.

    Shares its preamble (size gate, tier routing, rate limit, attachment load,
    conversation resolution) with `/merlin/agent` via `_prepare_turn` —
    `allow_agentic=False` because this route never runs the agent loop, so it
    always draws from the single-shot hourly counter regardless of tier.
    """
    turn = await _prepare_turn(site_id, body, account, allow_agentic=False)

    try:
        result = await run_merlin_turn(
            message=body.message,
            history=turn.history,
            blocks=body.blocks,
            theme=body.theme,
            business_name=turn.site["name"],
            model_tier=turn.tier,
            plan=account.plan,
            selected_block=body.selected_block,
            attachments=turn.attachments,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Merlin is at capacity right now ({exc.limit_type} limit reached). Try again shortly.",
        )

    result["routed"] = turn.routed
    if turn.conversation is not None:
        async with get_connection() as conn:
            stored = await merlin_store.add_message(
                conn,
                turn.conversation["id"],
                role="assistant",
                content=result.get("message") or "",
                tier=result.get("tier"),
            )
        result["conversation_id"] = turn.conversation["id"]
        # The client reports back which ops actually landed (it applies to live
        # state, so only it knows) via PATCH /merlin/messages/{id}/results.
        result["message_id"] = stored["id"]

    return result


@router.post("/sites/{site_id}/merlin/agent")
async def merlin_agent(
    site_id: UUID,
    body: CappeMerlinChatRequest,
    account: CappeAccount = Depends(require_cappe_account),
):
    """The agentic turn, streamed as SSE.

    Same inputs and same output contract as `/merlin/chat` — a validated op list
    the client applies — but the model gets tools: it folds ops onto a
    server-side working copy of the snapshot, renders and screenshots that copy,
    critiques what it sees, and revises. See `services/merlin/agent.py`.

    Non-premium (or Lite) callers fall through to the single-shot path and get
    its result as one `result` frame, so the client has exactly one code path.
    The page itself is still never written here.

    Shares its preamble with `/merlin/chat` via `_prepare_turn`
    (`allow_agentic=True` — `auto` resolving into an agent tier on a premium
    plan is exactly what makes the loop reachable without the user knowing
    the tiers exist, so this route is the one that can actually trip it).
    """
    prep = await _prepare_turn(site_id, body, account, allow_agentic=True)

    # nav_rows isn't part of the shared preamble — only the agent path's
    # render_html needs it (to render other-page links in the preview nav),
    # so it's its own connection rather than something every turn pays for.
    async with get_connection() as conn:
        nav_rows = await conn.fetch(
            "SELECT title, slug FROM cappe_pages WHERE site_id = $1 ORDER BY sort_order, created_at",
            site_id,
        )

    nav = [{"slug": r["slug"], "title": r["title"]} for r in nav_rows] or [
        {"slug": "home", "title": "Home"}
    ]
    site_theme = loads(prep.site["theme_config"])
    site_meta = loads(prep.site["meta_config"])

    def render_html(work_blocks: list, work_theme: dict) -> str:
        """Render the agent's working copy exactly as the editor's own preview
        would — same call, same premium gating — so what the model looks at is
        what the user will see, not a more-permissive render."""
        site_dict = {
            "name": prep.site["name"],
            "slug": prep.site["slug"],
            "theme_config": gate_theme(work_theme or site_theme, account.plan),
            "meta_config": site_meta,
        }
        page = {
            "title": "Preview",
            "slug": "home",
            "content": gate_content({"blocks": work_blocks}, account.plan),
        }
        # block_anchors — NOT editable — tags each section with data-cz-block
        # so the agent's render_screenshot tool can scroll to the one it's
        # judging, without also emitting the canvas editor runtime editable
        # would (see render_site_html / _apply_design).
        return render_site_html(site_dict, page, nav, preview=True, block_anchors=True)

    return StreamingResponse(
        stream_agent_turn(
            site_id=site_id, body=body, account=account, prep=prep, render_html=render_html,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.patch("/merlin/messages/{message_id}/results", status_code=status.HTTP_204_NO_CONTENT)
async def set_merlin_message_results(
    message_id: UUID,
    body: CappeMerlinResultsUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Record what the client actually applied for one assistant message.

    Fire-and-forget from the panel's point of view: a failure here costs the
    result chips on a reload and the `ops_summary` context of later turns, not
    the edit itself.
    """
    async with get_connection() as conn:
        owned = await conn.fetchval(
            """
            SELECT 1 FROM cappe_merlin_messages m
            JOIN cappe_merlin_conversations c ON c.id = m.conversation_id
            WHERE m.id = $1 AND c.account_id = $2
            """,
            message_id,
            account.id,
        )
        if not owned:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Message not found"
            )
        await conn.execute(
            "UPDATE cappe_merlin_messages SET results = $2 WHERE id = $1",
            message_id,
            json.dumps(body.results),
        )
