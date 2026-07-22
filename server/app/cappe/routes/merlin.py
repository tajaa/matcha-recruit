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
owned by `services/merlin_store.py`), so a conversation survives a reload and a
page can hold several of them. See `services/merlin.py` for the op validation
and prompt logic.
"""
import json
import logging
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
from ..services import merlin_store
from ..services.design_gate import gate_content, gate_theme, is_premium_plan
from ..services.merlin import run_merlin_turn
from ..services.merlin_agent import AGENT_TIERS, run_merlin_agent
from ..services.merlin_attachments import load_attachments
from ..services.merlin_ops import build_merlin_schema
from ..services.merlin_router import route_tier
from ..services.render import render_site_html
from ._shared import get_owned_site, loads

logger = logging.getLogger(__name__)

router = APIRouter()


def _sse(frame: dict[str, Any]) -> str:
    """One SSE frame. `default=str` so a UUID or datetime that reaches a frame
    serializes instead of killing the stream mid-flight."""
    return f"data: {json.dumps(frame, default=str)}\n\n"

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
    """
    if body.conversation_id is not None:
        return await merlin_store.get_owned_conversation(
            conn, body.conversation_id, account.id
        )
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
    )
    # Cost guard until the token wallet exists: free plans get a smaller
    # hourly allowance than paid ones, keyed per account (not per IP). Both
    # gates run before the transcript write — a rejected turn shouldn't leave a
    # question in the history that never got an answer.
    hourly = _PAID_HOURLY_LIMIT if premium else _FREE_HOURLY_LIMIT
    await check_rate_limit(str(account.id), "cappe_merlin_chat", hourly, 3600)

    page_uuid = _parse_page_id(body.page_id)
    # Fetched before the DB block: it's an S3 round trip, not a DB one, and
    # doesn't need the connection. Never fetches an arbitrary URL — see
    # merlin_attachments._is_own_storage.
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

    try:
        result = await run_merlin_turn(
            message=body.message,
            history=history,
            blocks=body.blocks,
            theme=body.theme,
            business_name=site["name"],
            model_tier=tier,
            plan=account.plan,
            selected_block=body.selected_block,
            attachments=attachments,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Merlin is at capacity right now ({exc.limit_type} limit reached). Try again shortly.",
        )

    result["routed"] = routed
    if conversation is not None:
        async with get_connection() as conn:
            stored = await merlin_store.add_message(
                conn,
                conversation["id"],
                role="assistant",
                content=result.get("message") or "",
                tier=result.get("tier"),
            )
        result["conversation_id"] = conversation["id"]
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
    critiques what it sees, and revises. See `services/merlin_agent.py`.

    Non-premium (or Lite) callers fall through to the single-shot path and get
    its result as one `result` frame, so the client has exactly one code path.
    The page itself is still never written here.
    """
    snapshot_bytes = len(json.dumps(body.blocks)) + len(json.dumps(body.theme))
    if snapshot_bytes > _MAX_SNAPSHOT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="This page is too large for Merlin — edit it in Form or Canvas mode.",
        )

    premium = is_premium_plan(account.plan)
    # `auto` (the client default) resolves here, BEFORE the agentic decision —
    # routing to `max` is exactly what turns a vague design ask into an agent
    # turn, so the router is what makes the loop reachable without the user
    # knowing the tiers exist.
    tier, routed = await route_tier(
        body.model_tier, account.plan,
        message=body.message, has_selected_block=bool(body.selected_block),
    )
    agentic = premium and tier in AGENT_TIERS
    # One agent turn is several Gemini calls plus screenshots, so it gets its
    # own (tighter) hourly counter rather than sharing the chat one.
    if agentic:
        await check_rate_limit(str(account.id), "cappe_merlin_agent", _AGENT_HOURLY_LIMIT, 3600)
    else:
        hourly = _PAID_HOURLY_LIMIT if premium else _FREE_HOURLY_LIMIT
        await check_rate_limit(str(account.id), "cappe_merlin_chat", hourly, 3600)

    page_uuid = _parse_page_id(body.page_id)
    attachments = await load_attachments([a.model_dump() for a in body.attachments])
    attachment_meta = [{"url": a["url"], "mime": a["mime"]} for a in attachments]

    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        nav_rows = await conn.fetch(
            "SELECT title, slug FROM cappe_pages WHERE site_id = $1 ORDER BY sort_order, created_at",
            site_id,
        )
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
            history = [t.model_dump() for t in body.history]

    nav = [{"slug": r["slug"], "title": r["title"]} for r in nav_rows] or [
        {"slug": "home", "title": "Home"}
    ]
    site_theme = loads(site["theme_config"])
    site_meta = loads(site["meta_config"])

    def render_html(work_blocks: list, work_theme: dict) -> str:
        """Render the agent's working copy exactly as the editor's own preview
        would — same call, same premium gating — so what the model looks at is
        what the user will see, not a more-permissive render."""
        site_dict = {
            "name": site["name"],
            "slug": site["slug"],
            "theme_config": gate_theme(work_theme or site_theme, account.plan),
            "meta_config": site_meta,
        }
        page = {
            "title": "Preview",
            "slug": "home",
            "content": gate_content({"blocks": work_blocks}, account.plan),
        }
        return render_site_html(site_dict, page, nav, preview=True)

    async def event_stream():
        result: dict | None = None
        try:
            if agentic:
                stream = run_merlin_agent(
                    message=body.message,
                    history=history,
                    blocks=body.blocks,
                    theme=body.theme,
                    render_html=render_html,
                    business_name=site["name"],
                    model_tier=tier,
                    plan=account.plan,
                    account_id=str(account.id),
                    selected_block=body.selected_block,
                    attachments=attachments,
                )
                async for frame in stream:
                    if frame.get("type") == "result":
                        result = frame["data"]
                    else:
                        yield _sse(frame)
            else:
                turn = await run_merlin_turn(
                    message=body.message,
                    history=history,
                    blocks=body.blocks,
                    theme=body.theme,
                    business_name=site["name"],
                    model_tier=tier,
                    plan=account.plan,
                    selected_block=body.selected_block,
                    attachments=attachments,
                )
                result = {**turn, "steps": []}
        except RateLimitExceeded as exc:
            # A stream can't 429 — the response has already begun — so the cap
            # is reported in-band and the client surfaces it as the error.
            yield _sse({
                "type": "error",
                "message": f"Merlin is at capacity right now ({exc.limit_type} limit reached). Try again shortly.",
            })
        except Exception as exc:  # noqa: BLE001 — a stream must always terminate cleanly
            logger.warning("Merlin agent stream failed: %s", exc, exc_info=True)
            yield _sse({"type": "error", "message": "Merlin failed to respond."})

        if result is not None:
            result["routed"] = routed
            if conversation is not None:
                async with get_connection() as conn:
                    stored = await merlin_store.add_message(
                        conn,
                        conversation["id"],
                        role="assistant",
                        content=result.get("message") or "",
                        steps=result.get("steps") or None,
                        tier=result.get("tier"),
                    )
                result["conversation_id"] = str(conversation["id"])
                result["message_id"] = str(stored["id"])
            yield _sse({"type": "result", "data": result})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
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
