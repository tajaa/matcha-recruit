"""Huume's agent loop — a bounded Gemini tool-calling loop, structurally
mirroring cappe's Merlin (`cappe/services/merlin_agent.py`): fixed bounds on
model calls and wall clock, force-finish with partial work on a bound hit,
a never-raises contract (only `RateLimitExceeded` escapes), and an async
generator of SSE-shaped frames the caller streams straight through.

Unlike Merlin, Huume's tools are DB-bound reads/writes rather than a
client-side-applied op log — nothing here is undo-able by the client, so
every write-shaped tool (`draft_offer_letter`) writes a non-terminal DRAFT
record, and every action with real consequences (`send_offer`,
`execute_approved_steps`) goes through the confirm-first envelope in
`actions.py` before it does anything. The loop itself never decides
authorization — it calls `actions.evaluate_*` and reports the verdict.

Contract with the caller (messaging.py's `_run_huume_dispatch`): this is an
async generator of dicts, `{"type": "status"|"step"|"error"|"huume_result"}`.
Exactly one `huume_result` frame is always emitted last, carrying whatever
was accomplished even if the loop failed partway.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Optional
from uuid import UUID

from google.genai import types

from app.core.services.ai_usage import feature_scope
from app.core.services.genai_client import get_genai_client
from app.core.services.rate_limiter import GeminiRateLimiter, RateLimitExceeded

from . import actions, onboarding_skill, store
from .prompt import build_system_prompt
from .tools import TOOLS_BY_NAME, tool_declarations

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.6-flash"
_MAX_MODEL_CALLS = 8
_WALL_CLOCK_SECONDS = 150.0
_CALL_TIMEOUT = 60.0
_MAX_HISTORY_MESSAGES = 20


class _StepRecorder:
    """Accumulates step dicts for the run's audit trail + the frames yielded
    to the caller. `seq` is 1-based and monotonic across the whole turn."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def record(self, *, tool: str, kind: str, label: str, status: str, detail: Optional[str] = None) -> dict[str, Any]:
        step = {"seq": len(self.steps) + 1, "tool": tool, "kind": kind, "label": label, "status": status}
        if detail:
            step["detail"] = detail
        self.steps.append(step)
        return step


def _to_contents(history: list[dict[str, Any]]) -> list[types.Content]:
    contents: list[types.Content] = []
    for msg in history[-_MAX_HISTORY_MESSAGES:]:
        role = "model" if msg.get("role") == "assistant" else "user"
        text = str(msg.get("content") or "").strip()
        if not text:
            continue
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    if not contents:
        contents.append(types.Content(role="user", parts=[types.Part(text="Hello.")]))
    return contents


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


async def run_huume_turn(
    *,
    thread_id: UUID,
    company_id: UUID,
    user_id: Optional[UUID],
    user_role: Optional[str],
    history: list[dict[str, Any]],
    current_state: dict[str, Any],
    company_name: str,
) -> AsyncIterator[dict[str, Any]]:
    """Run one Huume turn. Yields `status`/`step`/`error` frames, then
    exactly one final `huume_result` frame:
        {"message": str, "steps": [...], "token_usage": {...}, "state_updates": {...}}
    `state_updates` is applied by the caller via matcha_work_document.apply_update
    — this module never writes mw_threads itself.
    """
    rate_limiter = GeminiRateLimiter()
    recorder = _StepRecorder()
    state_updates: dict[str, Any] = {}
    final_message: Optional[str] = None
    model_calls = 0
    started = time.monotonic()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def elapsed() -> float:
        return time.monotonic() - started

    features, integrations = await store.get_thread_features_and_integrations(company_id)

    # Frozen at turn start — the two-turn confirm check for `send_offer`
    # compares against THIS snapshot, never against state a tool call in
    # this same turn just wrote.
    pre_turn_action = current_state.get("huume_action")
    pre_turn_plan = current_state.get("huume_plan")

    async def call_tool(name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (function_response payload, step dict)."""
        try:
            if name == "lookup_context":
                result = await onboarding_skill.lookup_context(
                    company_id=company_id, topic=str(args.get("topic") or ""), query=args.get("query"),
                )
                step = recorder.record(tool=name, kind="read", label=f"Looked up {args.get('topic')}", status="ok")
                return _json_safe(result), step

            if name == "draft_offer_letter":
                fields = {k: v for k, v in args.items() if k != "offer_id"}
                result = await onboarding_skill.draft_offer_letter(
                    company_id=company_id, thread_id=thread_id, offer_id=args.get("offer_id"), **fields,
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_offer"] = {"offer_id": result["offer_id"], "status": "draft"}
                step = recorder.record(
                    tool=name, kind="write",
                    label="Drafted offer letter" if ok else "Could not draft offer letter",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "check_offer_status":
                result = await onboarding_skill.check_offer_status(company_id=company_id, offer_id=str(args.get("offer_id") or ""))
                step = recorder.record(tool=name, kind="read", label="Checked offer status", status="ok" if result.get("status") != "error" else "error")
                return _json_safe(result), step

            if name == "send_offer":
                offer_id = str(args.get("offer_id") or "")
                existing = pre_turn_action
                confirming = (
                    isinstance(existing, dict) and existing.get("type") == "send_offer"
                    and existing.get("offer_id") == offer_id and existing.get("status") == "proposed"
                )
                staged = existing if confirming else {"type": "send_offer", "offer_id": offer_id, "status": "proposed"}
                verdict = actions.evaluate_huume_action(
                    staged_action=staged, features=features, role=user_role,
                    thread_huume_mode=True, this_turn_staged_new=not confirming,
                )
                if verdict.kind == "stage":
                    state_updates["huume_action"] = staged
                    step = recorder.record(tool=name, kind="staged", label="Staged: send offer to candidate", status="ok", detail=verdict.message)
                    return {"status": "staged", "message": verdict.message}, step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="staged", label="Send offer refused", status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                result = await actions.execute_huume_action(company_id=company_id, actor_user_id=user_id, action=verdict.action)
                state_updates["huume_action"] = {**staged, "status": "sent" if result.get("status") == "created" else "failed"}
                step = recorder.record(
                    tool=name, kind="write", label="Sent offer to candidate" if result.get("status") == "created" else "Failed to send offer",
                    status="ok" if result.get("status") == "created" else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "build_onboarding_plan":
                result = await onboarding_skill.build_plan_for_offer(company_id=company_id, offer_id=str(args.get("offer_id") or ""))
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_plan"] = result["plan"]
                step = recorder.record(
                    tool=name, kind="staged", label="Built onboarding plan" if ok else "Could not build onboarding plan",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "execute_approved_steps":
                plan = state_updates.get("huume_plan") or pre_turn_plan
                if not isinstance(plan, dict) or not plan.get("steps"):
                    step = recorder.record(tool=name, kind="write", label="No onboarding plan is staged", status="rejected")
                    return {"status": "refused", "message": "There's no onboarding plan staged yet — build one first."}, step
                step_keys = args.get("step_keys") or None
                approved_plan = actions.mark_steps_approved(plan, step_keys)
                exec_result = await actions.execute_plan_steps(
                    company_id=company_id, actor_user_id=user_id, plan=approved_plan,
                    features=features, integrations=integrations,
                )
                state_updates["huume_plan"] = exec_result.plan
                summary = "; ".join(exec_result.summaries) if exec_result.summaries else "No steps were approved to run."
                step = recorder.record(tool=name, kind="write", label="Executed onboarding plan steps", status="ok", detail=summary)
                return {"status": "ok", "summary": summary, "plan": _json_safe(exec_result.plan)}, step

            step = recorder.record(tool=name, kind="write", label=f"Unknown tool '{name}'", status="error")
            return {"error": f"unknown tool '{name}'"}, step
        except Exception:
            logger.exception("huume tool %s failed for thread %s", name, thread_id)
            step = recorder.record(tool=name, kind="write", label=f"{name} failed", status="error", detail="unexpected error")
            return {"error": "unexpected error"}, step

    client = get_genai_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=tool_declarations())],
        system_instruction=build_system_prompt(company_name=company_name or "your company", today=date.today().isoformat()),
    )
    contents = _to_contents(history)

    try:
        while True:
            if model_calls >= _MAX_MODEL_CALLS or elapsed() >= _WALL_CLOCK_SECONDS:
                logger.info("Huume agent hit its bound (calls=%s, elapsed=%.1fs)", model_calls, elapsed())
                yield {"type": "status", "message": "Wrapping up…"}
                break

            await rate_limiter.check_limit("huume", "agent")
            model_calls += 1
            call_timeout = min(_CALL_TIMEOUT, max(1.0, _WALL_CLOCK_SECONDS - elapsed()))
            try:
                with feature_scope("matcha.huume.loop"):
                    response = await asyncio.wait_for(
                        client.aio.models.generate_content(model=_MODEL, contents=contents, config=config),
                        timeout=call_timeout,
                    )
            finally:
                await rate_limiter.record_call("huume", "agent")

            usage = getattr(response, "usage_metadata", None)
            if usage:
                total_usage["prompt_tokens"] += getattr(usage, "prompt_token_count", 0) or 0
                total_usage["completion_tokens"] += getattr(usage, "candidates_token_count", 0) or 0
                total_usage["total_tokens"] += getattr(usage, "total_token_count", 0) or 0

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

            for call in calls:
                name = call.name
                args = dict(call.args or {})
                if name == "finish":
                    finish_message = str(args.get("message") or "").strip() or None
                    finished = True
                    recorder.record(tool="finish", kind="finish", label="Done", status="ok")
                    continue

                tool = TOOLS_BY_NAME.get(name)
                if tool and tool.kind == "staged":
                    yield {"type": "status", "message": f"Proposing: {name.replace('_', ' ')}…"}
                elif tool and tool.kind == "write":
                    yield {"type": "status", "message": f"Working on: {name.replace('_', ' ')}…"}

                payload, step = await call_tool(name, args)
                if step:
                    yield {"type": "step", "data": step}
                response_parts.append(types.Part.from_function_response(name=name, response=payload))

            if finished:
                final_message = finish_message
                break

            contents.append(types.Content(role="user", parts=response_parts))

    except RateLimitExceeded:
        raise
    except Exception as exc:
        logger.warning("Huume agent turn failed: %s", exc, exc_info=True)
        yield {"type": "error", "message": "Huume hit a problem mid-turn — keeping what worked."}

    if not final_message:
        final_message = "I wasn't able to finish that — nothing was changed." if not recorder.steps else "Done for now — see the steps above."

    total_usage["model"] = _MODEL
    total_usage["estimated"] = False

    yield {
        "type": "huume_result",
        "data": {
            "message": final_message,
            "steps": recorder.steps,
            "token_usage": total_usage,
            "state_updates": state_updates,
            "model_calls": model_calls,
        },
    }
