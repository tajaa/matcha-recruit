"""The dashboard setup concierge's agent loop.

A sibling of `agent.py`'s `run_merlin_agent`, not a parameterization of it —
that loop is coupled to a page snapshot (working copy, screenshots,
render_html); this one is coupled to the SITE (staged server-row actions via
`setup_actions.py`). Two tools instead of five: `stage_action` proposes a
change (never writes), `execute_staged_action` is the chat-confirm path for
something the user just approved in THIS message (never the same turn it was
staged in — see `setup_actions.evaluate_setup_execute`). `finish` ends the
turn, optionally with deep-link buttons to existing UI (`shop`, `design`,
`settings`, …) for anything outside the action vocabulary.

Every plan gets this loop, including free — the setup surface is what drives
activation, and it draws from its own rate-limit key
(`routes/merlin_setup.py`'s `cappe_merlin_setup`), never `route_tier`/
`AGENT_TIERS` from the page editor.

Contract with the caller (`stream_setup_turn`): an async generator of
SSE-shaped dicts, `{"type": "status"|"step"|"staged_action"|"error"|"result"}`.
Raises only `RateLimitExceeded`; everything else degrades to an `error` frame
followed by a `result` frame with whatever was accomplished — same
never-raises contract as the page agent.
"""
import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator, Optional
from uuid import UUID

from google.genai import types

from ....core.services.ai_usage import feature_scope
from ....core.services.genai_client import get_genai_client
from ....core.services.rate_limiter import GeminiRateLimiter, RateLimitExceeded
from ....database import get_connection
from ..entitlements import resolve_entitlements
from ..readiness import compute_readiness
from . import store as merlin_store
from .agent_stream import _sse
from .catalog import MODEL_TIERS
from .setup_actions import (
    apply_outcome,
    append_entry,
    evaluate_setup_execute,
    evaluate_setup_stage,
    execute_setup_action,
    find_entry,
    new_staged_entry,
)
from .setup_context import build_setup_prompt

logger = logging.getLogger(__name__)

# One flat tier for every plan, unlike the page editor (see module docstring)
# — always MODEL_TIERS["regular"], never routed/clamped by plan.
_MODEL_CALLS = 6
_WALL_CLOCK = 90.0
_CALL_TIMEOUT = 60.0
_MAX_HISTORY_MESSAGES = 20

_LINK_TARGETS = frozenset({
    "shop", "subscribers", "campaigns", "bookings", "settings", "design", "pages", "billing", "publish",
})


def _valid_link_target(target: str) -> bool:
    return target in _LINK_TARGETS or (target.startswith("page:") and len(target) > len("page:"))


def _tool_declarations() -> list[types.FunctionDeclaration]:
    return [
        types.FunctionDeclaration(
            name="stage_action",
            description=(
                "Propose ONE setup action for the user to review and approve — this does NOT make "
                "the change. Use exactly one of the action types and payload shapes given in the "
                "instructions. Returns whether it validated (and, if not, why — fix and retry or "
                "explain the limitation to the user) and, on success, the staged action's id."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "type": types.Schema(type=types.Type.STRING, description="One of the action type names from the instructions."),
                    "payload": types.Schema(
                        type=types.Type.STRING,
                        description="A JSON object matching that action's payload shape from the instructions.",
                    ),
                },
                required=["type", "payload"],
            ),
        ),
        types.FunctionDeclaration(
            name="execute_staged_action",
            description=(
                "Run a previously-staged action NOW, because the user just confirmed it in THIS "
                "message (e.g. 'yes, do it' / 'go ahead'). Only for an action staged on an EARLIER "
                "message — one staged earlier in this same turn is refused; tell the user you'll "
                "run it once they confirm on their next message."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "action_id": types.Schema(type=types.Type.STRING),
                },
                required=["action_id"],
            ),
        ),
        types.FunctionDeclaration(
            name="finish",
            description="End the turn. Optionally offer deep-link buttons for things outside the action vocabulary.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "message": types.Schema(
                        type=types.Type.STRING,
                        description="One or two plain-language sentences for the user.",
                    ),
                    "links": types.Schema(
                        type=types.Type.ARRAY,
                        description=(
                            "Optional buttons. target must be one of: "
                            + ", ".join(sorted(_LINK_TARGETS))
                            + ", or 'page:<id>' for an existing page (use an id from the instructions)."
                        ),
                        items=types.Schema(
                            type=types.Type.OBJECT,
                            properties={
                                "target": types.Schema(type=types.Type.STRING),
                                "label": types.Schema(type=types.Type.STRING),
                            },
                            required=["target", "label"],
                        ),
                    ),
                },
                required=["message"],
            ),
        ),
    ]


def _history_text(history: list[dict[str, Any]]) -> Optional[str]:
    trimmed = history[-_MAX_HISTORY_MESSAGES:]
    if not trimmed:
        return None
    lines = []
    for turn in trimmed:
        if turn.get("role") == "assistant" and turn.get("ops_summary"):
            lines.append(f"assistant: {turn.get('content', '')} [{turn['ops_summary']}]")
        else:
            lines.append(f"{turn.get('role')}: {turn.get('content', '')}")
    return "Conversation so far:\n" + "\n".join(lines)


async def run_setup_agent(
    *,
    message: str,
    history: list[dict[str, Any]],
    context: dict[str, Any],
    site: dict[str, Any],
    account: Any,
    conversation_id: UUID,
) -> AsyncIterator[dict[str, Any]]:
    """Run one setup-concierge turn, yielding SSE-shaped frames.

    `context` is `setup_context.build_setup_context`'s already-fetched dict
    (the route builds it once before streaming starts, same separation as
    the page agent's `render_html` closure). `site`/`account` are passed
    through to `execute_setup_action` for the tool calls that actually write.
    """
    tier_cfg = MODEL_TIERS["regular"]
    rate_limiter = GeminiRateLimiter()

    # Ids staged DURING this turn — an execute_staged_action call naming one
    # of them is structurally refused (evaluate_setup_execute), not just
    # discouraged by the prompt.
    staged_this_turn: set[str] = set()
    steps: list[dict[str, Any]] = []
    results_log: list[dict[str, Any]] = []
    final_message: Optional[str] = None
    final_links: list[dict[str, str]] = []

    model_calls = 0
    started = time.monotonic()

    def elapsed() -> float:
        return time.monotonic() - started

    def record_step(step: dict[str, Any]) -> dict[str, Any]:
        steps.append(step)
        return {"type": "step", **step}

    async def do_stage_action(args: dict[str, Any]) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        action_type = str(args.get("type") or "")
        raw_payload = args.get("payload")
        try:
            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else (raw_payload or {})
        except (json.JSONDecodeError, TypeError):
            return {"error": "payload was not valid JSON"}, None
        async with get_connection() as conn:
            entitlements = await resolve_entitlements(account.plan, conn=conn)
            verdict = evaluate_setup_stage(action_type, payload, entitlements=entitlements, plan=account.plan)
            if verdict.kind != "stage":
                results_log.append({"ok": False, "summary": f"{action_type}: {verdict.message}"})
                return {"staged": False, "reason": verdict.message}, None
            entry = new_staged_entry(action_type, verdict.payload, verdict.message)
            await merlin_store.mutate_staged_actions(conn, conversation_id, append_entry(entry))
        staged_this_turn.add(entry["id"])
        results_log.append({"ok": True, "summary": f"Proposed: {entry['summary']}"})
        return {"staged": True, "action_id": entry["id"], "summary": entry["summary"]}, entry

    async def do_execute_staged_action(args: dict[str, Any]) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
        action_id = str(args.get("action_id") or "")
        async with get_connection() as conn:
            convo = await merlin_store.get_owned_conversation(conn, conversation_id, account.id)
            entry = find_entry(convo.get("staged_actions"), action_id)
            if entry is None:
                return {"error": "no staged action with that id"}, None
            entitlements = await resolve_entitlements(account.plan, conn=conn)
            verdict = evaluate_setup_execute(
                entry, entitlements=entitlements, plan=account.plan, this_turn_staged_ids=staged_this_turn
            )
            if verdict.kind != "proceed":
                results_log.append({"ok": False, "summary": f"{entry['type']}: {verdict.message}"})
                return {"executed": False, "reason": verdict.message}, None
            outcome = await execute_setup_action(conn, site, account, entry)
            updated = await merlin_store.mutate_staged_actions(
                conn, conversation_id, apply_outcome(action_id, outcome)
            )
            readiness = await compute_readiness(conn, site["id"], site)
        results_log.append({"ok": outcome["ok"], "summary": outcome["message"]})
        return (
            {"executed": outcome["ok"], "message": outcome["message"], "readiness_ready": readiness.get("ready")},
            find_entry(updated, action_id),
        )

    client = get_genai_client()
    system_instruction = build_setup_prompt(context)
    history_text = _history_text(history)
    if history_text:
        system_instruction += "\n\n" + history_text
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=_tool_declarations())],
        thinking_config=types.ThinkingConfig(thinking_level=tier_cfg.thinking_level),
        system_instruction=system_instruction,
    )
    contents: list[types.Content] = [types.Content(role="user", parts=[types.Part(text=message)])]

    try:
        while True:
            if model_calls >= _MODEL_CALLS or elapsed() >= _WALL_CLOCK:
                logger.info("Merlin setup agent hit its bound (calls=%s elapsed=%.1f)", model_calls, elapsed())
                yield {"type": "status", "message": "Wrapping up…"}
                break

            await rate_limiter.check_limit("cappe_merlin", "agent")
            model_calls += 1
            call_timeout = min(_CALL_TIMEOUT, max(1.0, _WALL_CLOCK - elapsed()))
            try:
                with feature_scope("cappe.merlin_setup.loop"):
                    response = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=tier_cfg.model, contents=contents, config=config
                        ),
                        timeout=call_timeout,
                    )
            finally:
                await rate_limiter.record_call("cappe_merlin", "setup")

            # See agent.py's identical comment: thought_signature must be
            # echoed back verbatim on a thinking model or later calls 400.
            call_parts = [
                part
                for candidate in (response.candidates or [])
                for part in (candidate.content.parts or [] if candidate.content else [])
                if getattr(part, "function_call", None)
            ]
            calls = [p.function_call for p in call_parts]

            if not calls:
                final_message = (getattr(response, "text", None) or "").strip() or None
                break

            contents.append(types.Content(role="model", parts=call_parts))

            response_parts: list[types.Part] = []
            finished = False
            finish_message: Optional[str] = None

            # Same reasoning as the page agent: run every non-finish call in
            # the batch before honoring finish, so a [finish, stage_action]
            # batch doesn't drop the stage.
            for call in calls:
                name = call.name
                args = dict(call.args or {})

                if name == "finish":
                    finish_message = str(args.get("message") or "").strip() or None
                    links = args.get("links")
                    if isinstance(links, list):
                        for link in links:
                            if isinstance(link, dict) and _valid_link_target(str(link.get("target") or "")):
                                final_links.append({
                                    "target": str(link["target"]),
                                    "label": str(link.get("label") or link["target"]),
                                })
                    finished = True
                    continue

                if name == "stage_action":
                    yield {"type": "status", "message": "Working on it…"}
                    payload, entry = await do_stage_action(args)
                    if entry is not None:
                        yield {"type": "staged_action", "action": entry}
                    record_step({"kind": "stage", "label": payload.get("summary") or payload.get("reason") or "Staged"})
                elif name == "execute_staged_action":
                    yield {"type": "status", "message": "Making that change…"}
                    payload, entry = await do_execute_staged_action(args)
                    if entry is not None:
                        yield {"type": "staged_action", "action": entry}
                    record_step({"kind": "execute", "label": payload.get("message") or payload.get("reason") or "Executed"})
                else:
                    payload = {"error": f"unknown tool '{name}'"}

                response_parts.append(types.Part.from_function_response(name=name, response=payload))

            if finished:
                final_message = finish_message
                break

            contents.append(types.Content(role="user", parts=response_parts))
    except RateLimitExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 — never-raises past rate limiting
        logger.warning("Merlin setup agent turn failed: %s", exc, exc_info=True)
        yield {"type": "error", "message": "Merlin hit a problem mid-setup — keeping what worked."}

    if not final_message:
        final_message = "Here's where things stand." if results_log else "I couldn't do that — nothing changed."

    yield {
        "type": "result",
        "data": {
            "message": final_message,
            "links": final_links,
            "tier": "regular",
            "steps": steps,
            "results": results_log,
        },
    }


# ---------------------------------------------------------------------------
# SSE orchestration — a sibling of agent_stream.py's stream_agent_turn, same
# disconnect-recovery shape (see that module's docstring for the reasoning
# behind the shield/lock dance). Reuses its `_sse` framing helper rather than
# duplicating a five-line function.
# ---------------------------------------------------------------------------

async def stream_setup_turn(
    *,
    conversation_id: UUID,
    message: str,
    history: list[dict[str, Any]],
    context: dict[str, Any],
    site: Any,
    account: Any,
) -> AsyncIterator[str]:
    result: Optional[dict[str, Any]] = None
    persisted = False
    persist_lock = asyncio.Lock()

    async def persist(final_result: dict[str, Any]) -> None:
        nonlocal persisted
        async with persist_lock:
            if persisted:
                return
            persisted = True
            async with get_connection() as conn:
                stored = await merlin_store.add_message(
                    conn, conversation_id, role="assistant",
                    content=final_result.get("message") or "",
                    steps=final_result.get("steps") or None,
                    results=final_result.get("results") or None,
                    tier=final_result.get("tier"),
                )
            final_result["conversation_id"] = str(conversation_id)
            final_result["message_id"] = str(stored["id"])

    try:
        try:
            stream = run_setup_agent(
                message=message, history=history, context=context, site=site, account=account,
                conversation_id=conversation_id,
            )
            async for frame in stream:
                if frame.get("type") == "result":
                    result = frame["data"]
                else:
                    yield _sse(frame)
        except RateLimitExceeded as exc:
            yield _sse({
                "type": "error",
                "message": f"Merlin is at capacity right now ({exc.limit_type} limit reached). Try again shortly.",
            })
        except Exception as exc:  # noqa: BLE001 — a stream must always terminate cleanly
            logger.warning("Merlin setup stream failed: %s", exc, exc_info=True)
            yield _sse({"type": "error", "message": "Merlin failed to respond."})

        if result is not None:
            await asyncio.shield(persist(result))
            yield _sse({"type": "result", "data": result})
        yield "data: [DONE]\n\n"
    finally:
        # See agent_stream.stream_agent_turn's identical finally block for
        # the full reasoning — this recovers the same disconnect-between-
        # finish-and-persist window for the setup surface.
        if result is not None and not persisted:
            try:
                await asyncio.shield(persist(result))
            except asyncio.CancelledError:
                logger.warning("Merlin setup post-disconnect persist failed: cancelled")
                raise
            except Exception as exc:  # noqa: BLE001 — best-effort recovery write
                logger.warning("Merlin setup post-disconnect persist failed: %s", exc)
