"""Merlin — the dashboard SETUP CONCIERGE, distinct from the page editor's
`/merlin/chat`/`/merlin/agent` in `routes/merlin.py`.

Site-scoped (not page-scoped): conversations here carry `kind='setup'` and
`page_id=NULL` (migration zzzzcappe27) — `merlin_store.list_conversations`'s
`WHERE page_id = $1` already excludes them from the page editor's list with
no code change there, so the two surfaces can't cross-contaminate.

Every plan gets the full agent loop here, including free (see
`services/merlin/setup_agent.py`'s docstring) — this surface exists to drive
activation, so it is deliberately NOT behind `is_premium_plan`/`route_tier`.
Its own rate-limit key (`_SETUP_HOURLY_LIMIT`) is the only consumption guard.

Server-row writes (create a product, flip a promo banner) are confirm-first:
the agent only ever STAGES via the `stage_action` tool; nothing is written
until `POST .../actions/{id}/execute` (or the chat-confirm tool path) runs
`setup_actions.execute_setup_action`. See that module's docstring for the
full plan-then-approve shape.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeMerlinConversation,
    CappeMerlinConversationDetail,
    CappeMerlinSetupRequest,
    CappeSetupActionResult,
)
from ..services.entitlements import resolve_entitlements
from ..services.merlin import store as merlin_store
from ..services.merlin.setup_actions import (
    apply_outcome,
    dismiss_entry,
    evaluate_setup_execute,
    execute_setup_action,
    find_entry,
)
from ..services.merlin.setup_agent import stream_setup_turn
from ..services.merlin.setup_context import build_setup_context
from ..services.readiness import compute_readiness
from .render import invalidate_render_cache
from ._shared import get_owned_site

logger = logging.getLogger(__name__)
router = APIRouter()

# Every plan draws from this one counter — there is no free/paid split like
# the page editor's `_FREE_HOURLY_LIMIT`/`_PAID_HOURLY_LIMIT`, because every
# plan gets the same (agentic) tier here. Deliberately tighter than the page
# editor's `_AGENT_HOURLY_LIMIT` (20) would be generous for a surface a user
# mostly visits once per site to get set up, not per edit.
_SETUP_HOURLY_LIMIT = 20


@router.get(
    "/sites/{site_id}/merlin/setup/conversations",
    response_model=list[CappeMerlinConversation],
)
async def list_setup_conversations(
    site_id: UUID, account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        return await merlin_store.list_site_setup_conversations(conn, site["id"], account.id)


async def _resolve_setup_conversation(
    conn, *, conversation_id, site, account: CappeAccount, first_message: str,
):
    """Mirrors `routes/merlin.py:_resolve_conversation`'s ownership rule — a
    named id must be owned AND be this site's AND be a setup conversation, or
    404 (never silently open a new one against a stale/wrong id)."""
    if conversation_id is not None:
        convo = await merlin_store.get_owned_conversation(conn, conversation_id, account.id)
        if convo["site_id"] != site["id"] or convo.get("kind") != "setup":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        return convo
    return await merlin_store.create_conversation(
        conn, account_id=account.id, site_id=site["id"], page_id=None, kind="setup",
        title=merlin_store.title_from_message(first_message),
    )


@router.post("/sites/{site_id}/merlin/setup/agent")
async def merlin_setup_agent(
    site_id: UUID,
    body: CappeMerlinSetupRequest,
    account: CappeAccount = Depends(require_cappe_account),
):
    """One setup-concierge turn, streamed as SSE. See module docstring."""
    await check_rate_limit(str(account.id), "cappe_merlin_setup", _SETUP_HOURLY_LIMIT, 3600)

    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        conversation = await _resolve_setup_conversation(
            conn, conversation_id=body.conversation_id, site=site, account=account,
            first_message=body.message,
        )
        history = await merlin_store.load_history(conn, conversation["id"])
        await merlin_store.add_message(conn, conversation["id"], role="user", content=body.message)
        context = await build_setup_context(conn, site, account, conversation.get("staged_actions"))

    return StreamingResponse(
        stream_setup_turn(
            conversation_id=conversation["id"], message=body.message, history=history,
            context=context, site=site, account=account,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/merlin/setup/conversations/{conversation_id}",
    response_model=CappeMerlinConversationDetail,
)
async def get_setup_conversation(
    conversation_id: UUID, account: CappeAccount = Depends(require_cappe_account),
):
    """Setup conversations carry `staged_actions` on top of the ordinary
    conversation shape — this is the same read `routes/merlin.py`'s
    `get_merlin_conversation` does, kept as its own endpoint only because the
    response needs that extra field populated for every caller here, not
    conditionally."""
    async with get_connection() as conn:
        convo = await merlin_store.get_owned_conversation(conn, conversation_id, account.id)
        messages = await merlin_store.get_messages(conn, conversation_id)
    return {**convo, "messages": messages}


async def _apply_action_outcome(
    conn, *, conversation, site, account: CappeAccount, action_id: str, this_turn_staged_ids,
) -> CappeSetupActionResult:
    """Runs the whole confirm — re-check, write, status flip — inside ONE
    transaction holding a row lock on the conversation the entire time (see
    `merlin_store.lock_conversation_actions`'s docstring). Two concurrent
    confirmations for the same action now serialize: the second to acquire
    the lock re-reads a status that is no longer 'proposed' and refuses,
    instead of both performing the write."""
    async with conn.transaction():
        locked_actions = await merlin_store.lock_conversation_actions(conn, conversation["id"])
        entry = find_entry(locked_actions, action_id)
        if entry is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staged action not found")

        entitlements = await resolve_entitlements(account.plan, conn=conn)
        verdict = evaluate_setup_execute(
            entry, entitlements=entitlements, plan=account.plan, this_turn_staged_ids=this_turn_staged_ids,
        )
        if verdict.kind == "refuse":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=verdict.message)
        if verdict.kind == "blocked":
            outcome = {"ok": False, "status": "blocked", "message": verdict.message}
        else:
            outcome = await execute_setup_action(conn, site, account, entry)

        updated = await merlin_store.mutate_staged_actions(
            conn, conversation["id"], apply_outcome(action_id, outcome)
        )
        if outcome["ok"]:
            await merlin_store.add_message(
                conn, conversation["id"], role="assistant", content=outcome["message"],
            )
        readiness = await compute_readiness(conn, site["id"], site)

    if outcome["ok"]:
        # Products/pages/promos all reach a rendered page — cache invalidation
        # runs after the transaction commits, and lives in this routes-layer
        # function (not inside setup_actions.execute) because services/ must
        # never import routes/render.py.
        await invalidate_render_cache(site["id"])
    return {"action": find_entry(updated, action_id), "message": outcome["message"], "readiness": readiness}


@router.post(
    "/merlin/setup/conversations/{conversation_id}/actions/{action_id}/execute",
    response_model=CappeSetupActionResult,
)
async def execute_setup_staged_action(
    conversation_id: UUID, action_id: str, account: CappeAccount = Depends(require_cappe_account),
):
    """The Approve button. Never same-turn (that concept only exists inside
    one chat turn), so `this_turn_staged_ids` is always empty here — only
    `evaluate_setup_execute`'s status/idempotency check applies."""
    async with get_connection() as conn:
        conversation = await merlin_store.get_owned_conversation(conn, conversation_id, account.id)
        if conversation.get("kind") != "setup":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        site = await get_owned_site(conn, conversation["site_id"], account.id)
        return await _apply_action_outcome(
            conn, conversation=conversation, site=site, account=account,
            action_id=action_id, this_turn_staged_ids=set(),
        )


@router.post(
    "/merlin/setup/conversations/{conversation_id}/actions/{action_id}/dismiss",
    response_model=CappeMerlinConversationDetail,
)
async def dismiss_setup_staged_action(
    conversation_id: UUID, action_id: str, account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        convo = await merlin_store.get_owned_conversation(conn, conversation_id, account.id)
        if convo.get("kind") != "setup":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        updated = await merlin_store.mutate_staged_actions(conn, conversation_id, dismiss_entry(action_id))
        messages = await merlin_store.get_messages(conn, conversation_id)
    return {**convo, "staged_actions": updated, "messages": messages}
