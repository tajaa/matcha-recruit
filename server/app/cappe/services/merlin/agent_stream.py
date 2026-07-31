"""SSE orchestration for `POST /sites/{site_id}/merlin/agent`.

Extracted from the route (`routes/merlin.py:merlin_agent`) — the route keeps
auth/ownership, request validation, rate limits, and tier resolution
(`_prepare_turn`); this module owns the actual streamed turn: running the
agent loop (or falling back to the single-shot turn), persisting the
assistant message (including the disconnect-recovery path), and cataloging
any images the agent generated.
"""
import asyncio
import json
import logging
from typing import Any, AsyncIterator, Callable
from uuid import UUID

from ....core.services.rate_limiter import RateLimitExceeded
from ....database import get_connection
from .. import cappe_assets
from . import store as merlin_store
from .agent import run_merlin_agent
from .turn import run_merlin_turn

logger = logging.getLogger(__name__)


def _sse(frame: dict[str, Any]) -> str:
    """One SSE frame. `default=str` so a UUID or datetime that reaches a frame
    serializes instead of killing the stream mid-flight."""
    return f"data: {json.dumps(frame, default=str)}\n\n"


async def stream_agent_turn(
    *,
    site_id: UUID,
    body,
    account,
    prep,
    render_html: Callable[[list, dict], str],
) -> AsyncIterator[str]:
    """The agentic turn, streamed as SSE.

    `body`/`account` are the route's `CappeMerlinChatRequest`/`CappeAccount`;
    `prep` is the route's `_PreparedTurn` (duck-typed here rather than
    imported, to keep this service module from importing the route module).
    `render_html` is the route's closure over the site/page/nav needed to
    render the agent's working copy — computing it there keeps this module
    free of any direct DB reads.
    """
    result: dict | None = None
    # Set once the assistant message has actually been written, so the
    # normal path and the disconnect-recovery path below can't both try
    # (and neither double-writes if, say, the normal path partially ran
    # before the disconnect landed between its own steps). `persist_lock`
    # makes the check-and-set atomic: both callers await `asyncio.shield`,
    # and a cancellation landing mid-shield lets the INNER shielded task
    # keep running detached — without the lock, the finally's own call
    # could start before that detached task sets `persisted`, and both
    # would write. The lock, not the flag alone, is what rules that out.
    persisted = False
    persist_lock = asyncio.Lock()

    async def persist(final_result: dict) -> None:
        """Write the assistant message — `ops` included, so a turn whose
        reply never reached the client is still something the panel can
        offer to apply on reopen (see CappeMerlinStoredMessage.ops).
        Wrapped in `asyncio.shield` by both callers below: a client
        disconnect is exactly what this exists to survive, and without
        shielding, the SAME disconnect that cancels the rest of this
        request would cancel this write too, the instant it hit its own
        first `await`."""
        nonlocal persisted
        async with persist_lock:
            if persisted:
                return
            persisted = True
            if prep.conversation is None:
                return
            async with get_connection() as conn:
                stored = await merlin_store.add_message(
                    conn,
                    prep.conversation["id"],
                    role="assistant",
                    content=final_result.get("message") or "",
                    steps=final_result.get("steps") or None,
                    ops=final_result.get("ops") or None,
                    tier=final_result.get("tier"),
                )
            final_result["conversation_id"] = str(prep.conversation["id"])
            final_result["message_id"] = str(stored["id"])

    try:
        try:
            if prep.agentic:
                stream = run_merlin_agent(
                    message=body.message,
                    history=prep.history,
                    blocks=body.blocks,
                    theme=body.theme,
                    render_html=render_html,
                    business_name=prep.site["name"],
                    model_tier=prep.tier,
                    plan=account.plan,
                    account_id=str(account.id),
                    selected_block=body.selected_block,
                    selection=body.selection.model_dump() if body.selection else None,
                    attachments=prep.attachments,
                )
                async for frame in stream:
                    if frame.get("type") == "result":
                        result = frame["data"]
                    else:
                        yield _sse(frame)
            else:
                single_shot = await run_merlin_turn(
                    message=body.message,
                    history=prep.history,
                    blocks=body.blocks,
                    theme=body.theme,
                    business_name=prep.site["name"],
                    model_tier=prep.tier,
                    plan=account.plan,
                    selected_block=body.selected_block,
                    selection=body.selection.model_dump() if body.selection else None,
                    attachments=prep.attachments,
                )
                result = {**single_shot, "steps": []}
        except RateLimitExceeded as exc:
            # A stream can't 429 — the response has already begun — so the
            # cap is reported in-band and the client surfaces it as the error.
            yield _sse({
                "type": "error",
                "message": f"Merlin is at capacity right now ({exc.limit_type} limit reached). Try again shortly.",
            })
        except Exception as exc:  # noqa: BLE001 — a stream must always terminate cleanly
            logger.warning("Merlin agent stream failed: %s", exc, exc_info=True)
            yield _sse({"type": "error", "message": "Merlin failed to respond."})

        if result is not None:
            result["routed"] = prep.routed
            await asyncio.shield(persist(result))
            # Catalog anything the agent generated this turn (do_generate_image
            # rides prompt/aspect/image_size on the step for exactly this).
            # Best-effort, same reasoning as the upload routes: a broken
            # catalog insert must never surface as a failed Merlin turn.
            image_steps = [
                s for s in (result.get("steps") or [])
                if s.get("kind") == "image" and s.get("image_url")
            ]
            if image_steps:
                try:
                    async with get_connection() as conn:
                        for s in image_steps:
                            await cappe_assets.record(
                                conn, account_id=account.id, site_id=site_id, kind="generated",
                                url=s["image_url"], prompt=s.get("prompt"),
                                aspect=s.get("aspect"), image_size=s.get("image_size"),
                            )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("cappe asset catalog insert failed (agent): %s", exc)
            yield _sse({"type": "result", "data": result})
        yield "data: [DONE]\n\n"
    finally:
        # Reached on a normal finish (where `persisted` is already True
        # and this is a no-op) AND on a client disconnect — the ASGI
        # server closes this generator (or cancels the task running it)
        # the moment it sees the socket go, which is exactly what used to
        # skip the `if result is not None:` block above whenever the
        # disconnect landed between the turn finishing and that block's
        # own `await`. `result` is only ever non-None once a turn (agent
        # or single-shot) actually completed — a disconnect mid-turn
        # still loses whatever the turn hadn't produced yet, same as
        # before; this recovers exactly the case the module docstring
        # describes, where the answer existed and the write to record it
        # never ran.
        if result is not None and not persisted:
            try:
                await asyncio.shield(persist(result))
            except asyncio.CancelledError:
                # The disconnect path: this await itself gets cancelled
                # (the shielded persist() task keeps running detached
                # regardless — the write still lands), but CancelledError
                # is a BaseException, not Exception, so it never reached
                # the branch below and this log line never fired on
                # exactly the path it exists to observe. Re-raise after
                # logging — this generator is being torn down and must
                # not swallow its own cancellation.
                logger.warning("Merlin post-disconnect persist failed: cancelled")
                raise
            except Exception as exc:  # noqa: BLE001 — best-effort recovery write
                logger.warning("Merlin post-disconnect persist failed: %s", exc)
