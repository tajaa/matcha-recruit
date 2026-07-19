"""Merlin — AI chat editing for the Cappe page builder.

Open to every plan on the `lite` model tier; `regular`/`pro` need Pro/Business
(`is_premium_plan`, `services/design_gate.py`). Lite is cheap enough to run as
an upgrade funnel rather than something free users never see — the tier is
CLAMPED, not 403'd, so a stale client asking for pro degrades quietly.

Until the token wallet lands (phase B), the per-account hourly rate limit is
the only consumption guard, so free plans get a tighter one than paid.

This is Cappe's first Gemini integration: no rows are written here — the client
applies the returned ops to its own editor state and persists via the existing
page/site PUT routes when the user hits Save. See `services/merlin.py` for the
op validation and prompt logic.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.services.rate_limiter import RateLimitExceeded
from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeMerlinChatRequest, CappeMerlinChatResponse
from ..services.design_gate import is_premium_plan
from ..services.merlin import resolve_model_tier, run_merlin_turn
from ..services.merlin_ops import build_merlin_schema
from ._shared import get_owned_site

router = APIRouter()

# The registry-derived op/block/design/theme vocabulary as one JSON document —
# the single source of truth the editor can read instead of hand-mirroring it in
# blockSchemas.ts. Static per deploy; cheap to build, so no caching needed.
_MERLIN_SCHEMA = build_merlin_schema()


@router.get("/merlin/schema")
async def merlin_schema(account: CappeAccount = Depends(require_cappe_account)):
    """The Merlin vocabulary (ops, block fields, design keys, theme keys, limits)
    generated from the server registries. Read-only; account-gated for parity
    with the chat route."""
    return _MERLIN_SCHEMA

# Turns per account per hour. Paid plans buy headroom; free is a taste.
_FREE_HOURLY_LIMIT = 10
_PAID_HOURLY_LIMIT = 60
# Serialized blocks+theme ceiling. Generous for a real page (a dense one is
# tens of KB) but far below nginx's 100MB body cap.
_MAX_SNAPSHOT_BYTES = 300_000


@router.post("/sites/{site_id}/merlin/chat", response_model=CappeMerlinChatResponse)
async def merlin_chat(
    site_id: UUID,
    body: CappeMerlinChatRequest,
    account: CappeAccount = Depends(require_cappe_account),
):
    """One Merlin turn: chat message + current editor snapshot in, a small
    validated op plan out. Client-state-is-truth — this never reads or writes
    `cappe_pages`/`cappe_sites`; it only confirms the caller owns the site."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)

    # Size gate BEFORE any Gemini call. Pydantic bounds the item counts, but a
    # 200-block page can still be megabytes of text, and the whole snapshot is
    # inlined into the prompt (twice, if the validation retry fires). Merlin
    # draws on the global `api_rate_limits` Gemini budget shared with IR /
    # compliance / ER, so an oversized page here degrades those too.
    snapshot_bytes = len(json.dumps(body.blocks)) + len(json.dumps(body.theme))
    if snapshot_bytes > _MAX_SNAPSHOT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="This page is too large for Merlin — edit it in Form or Canvas mode.",
        )

    premium = is_premium_plan(account.plan)
    tier = resolve_model_tier(body.model_tier, account.plan)
    # Cost guard until the token wallet exists: free plans get a smaller
    # hourly allowance than paid ones, keyed per account (not per IP).
    hourly = _PAID_HOURLY_LIMIT if premium else _FREE_HOURLY_LIMIT
    await check_rate_limit(str(account.id), "cappe_merlin_chat", hourly, 3600)

    try:
        result = await run_merlin_turn(
            message=body.message,
            history=[t.model_dump() for t in body.history],
            blocks=body.blocks,
            theme=body.theme,
            business_name=site["name"],
            model_tier=tier,
            plan=account.plan,
            selected_block=body.selected_block,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Merlin is at capacity right now ({exc.limit_type} limit reached). Try again shortly.",
        )

    return result
