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

Onboarding plans are keyed by `offer_id` (`current_state.huume_plans`), so a
thread can be mid-onboarding for several candidates at once. Plan writes
(`build_onboarding_plan`, `execute_approved_steps`, `cancel_staged` on a
plan) go through `store.update_huume_plan`/`store.execute_plan_locked`
directly — NOT through `state_updates` — because `state_updates` is merged
into `current_state` wholesale at the END of the turn (see
`_run_huume_dispatch`'s `apply_update` call), which would let two plans (or
a plan build racing a plan execute) clobber each other. Everything else
(`huume_action`, `huume_offer`) still flows through `state_updates` as
before.

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

from . import actions, handbook_skill, legal_skill, onboarding_skill, store
from .prompt import build_state_block, build_system_prompt
from .tools import TOOLS_BY_NAME, tool_declarations

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.6-flash"
_MAX_MODEL_CALLS = 8
# 240s, not the 150s the loop launched with: the pilot tools (ask_legal_pilot /
# draft_handbook_content / generate_legal_packet) each embed their own
# 90s-capped Gemini call, and a 150s budget could force-finish the turn before
# the model gets one call to report a result it already paid for. The bound
# still exists to stop runaway loops, not to race a single grounded analysis.
_WALL_CLOCK_SECONDS = 240.0
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


_ATTACHMENT_TEXT_CAP = 20_000


def _to_contents(history: list[dict[str, Any]], attachment_texts: Optional[list[str]] = None) -> list[types.Content]:
    contents: list[types.Content] = []
    for msg in history[-_MAX_HISTORY_MESSAGES:]:
        role = "model" if msg.get("role") == "assistant" else "user"
        text = str(msg.get("content") or "").strip()
        if not text:
            continue
        contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
    if not contents:
        contents.append(types.Content(role="user", parts=[types.Part(text="Hello.")]))

    # Attached file text (from `messaging.py`'s file_context_parts) rides as
    # an extra Part on the final user turn — images are out of scope here
    # (unlike the normal skill engine, which gets multimodal image parts via
    # fetch_image_parts_for_messages; Huume's tool-calling loop doesn't wire
    # that path yet).
    if attachment_texts:
        joined = "\n\n".join(t for t in attachment_texts if t)[:_ATTACHMENT_TEXT_CAP]
        if joined:
            last = contents[-1]
            if last.role == "user":
                last.parts.append(types.Part(text=f"[Attached file(s)]\n{joined}"))
            else:
                contents.append(types.Content(role="user", parts=[types.Part(text=f"[Attached file(s)]\n{joined}")]))
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
    attachment_texts: Optional[list[str]] = None,
) -> AsyncIterator[dict[str, Any]]:
    """Run one Huume turn. Yields `status`/`step`/`error` frames, then
    exactly one final `huume_result` frame:
        {"message": str, "steps": [...], "token_usage": {...}, "state_updates": {...}}
    `state_updates` (only ever `huume_action`/`huume_offer`) is applied by
    the caller via matcha_work_document.apply_update. Onboarding plan writes
    (`huume_plans[offer_id]`) go straight through `store.update_huume_plan`/
    `store.execute_plan_locked` mid-turn instead — see the module docstring
    for why. The caller re-reads `current_state` after the turn to pick up
    those mid-turn writes.
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
    # this same turn just wrote. `pre_turn_plans` gives the same guarantee
    # for execute_approved_steps: a plan built earlier in this same turn is
    # absent here, so `actions.resolve_plan_offer_id` structurally can't
    # resolve it to something executable this turn.
    pre_turn_action = current_state.get("huume_action")
    pre_turn_plans: dict[str, dict[str, Any]] = dict(current_state.get("huume_plans") or {})
    built_this_turn: set[str] = set()

    # Pilot-skill turn state: handbook drafts proposed THIS turn (the two-turn
    # promote guard, mirroring built_this_turn), plus the citation records the
    # pilot tools resolved — accumulated across the turn and attached to the
    # final message metadata so the client renders verifiable sources.
    handbook_drafts_this_turn: set[str] = set()
    turn_citations: dict[str, dict[str, Any]] = {}
    turn_dropped: list[str] = []

    def _state_legal() -> dict[str, Any]:
        val = state_updates.get("huume_legal") or current_state.get("huume_legal")
        return val if isinstance(val, dict) else {}

    def _state_handbook() -> dict[str, Any]:
        val = state_updates.get("huume_handbook") or current_state.get("huume_handbook")
        return val if isinstance(val, dict) else {}

    def _collect_citations(result: dict[str, Any]) -> None:
        for rec in result.pop("citation_records", []) or []:
            if isinstance(rec, dict) and rec.get("cid"):
                turn_citations[rec["cid"]] = rec
        turn_dropped.extend(result.get("dropped_citations") or [])

    async def call_tool(name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (function_response payload, step dict)."""
        try:
            if name == "lookup_context":
                result = await onboarding_skill.lookup_context(
                    company_id=company_id, topic=str(args.get("topic") or ""), query=args.get("query"),
                    features=features,
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
                    plan = result["plan"]
                    offer_id = plan["offer_id"]
                    # Locked per-offer write, NOT state_updates — a second
                    # candidate's plan (built later this same turn or by a
                    # concurrent turn) must never clobber this one via the
                    # turn-end wholesale apply_update merge.
                    await store.update_huume_plan(thread_id, offer_id, lambda _cur, _plan=plan: _plan)
                    built_this_turn.add(offer_id)
                    state_updates["huume_offer"] = {"offer_id": offer_id, "status": "accepted"}
                step = recorder.record(
                    tool=name, kind="staged", label="Built onboarding plan" if ok else "Could not build onboarding plan",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "execute_approved_steps":
                reason = actions.evaluate_plan_execution(role=user_role, features=features)
                if reason:
                    step = recorder.record(tool=name, kind="staged", label="Execute refused", status="rejected", detail=reason)
                    return {"status": "refused", "message": reason}, step

                offer_id, err = actions.resolve_plan_offer_id(pre_turn_plans, args.get("offer_id"), built_this_turn)
                if err:
                    step = recorder.record(tool=name, kind="staged", label="Execute refused", status="rejected", detail=err)
                    return {"status": "refused", "message": err}, step

                exec_result = await store.execute_plan_locked(
                    thread_id=thread_id, company_id=company_id, actor_user_id=user_id, offer_id=offer_id,
                    features=features, integrations=integrations, approve_steps=(args.get("step_keys") or []),
                )
                summary = "; ".join(exec_result.summaries) if exec_result.summaries else "No steps were approved to run."
                step = recorder.record(tool=name, kind="write", label="Executed onboarding plan steps", status="ok", detail=summary)
                return {"status": "ok", "summary": summary, "offer_id": offer_id, "plan": _json_safe(exec_result.plan)}, step

            if name == "cancel_staged":
                target = str(args.get("target") or "")
                if target == "action":
                    staged = state_updates.get("huume_action") or pre_turn_action
                    if not isinstance(staged, dict) or staged.get("status") != "proposed":
                        step = recorder.record(tool=name, kind="staged", label="Nothing to cancel", status="rejected")
                        return {"status": "refused", "message": "There's nothing staged to cancel."}, step
                    state_updates["huume_action"] = {**staged, "status": "cancelled"}
                    step = recorder.record(tool=name, kind="staged", label="Cancelled staged send", status="ok")
                    return {"status": "ok", "message": "Cancelled — that offer will not be sent."}, step

                if target == "plan":
                    offer_id, err = actions.resolve_plan_offer_id(pre_turn_plans, args.get("offer_id"), built_this_turn)
                    if err:
                        step = recorder.record(tool=name, kind="staged", label="Cancel refused", status="rejected", detail=err)
                        return {"status": "refused", "message": err}, step

                    refusal: Optional[str] = None

                    def _mutator(current, _offer_id=offer_id):
                        nonlocal refusal
                        reason = actions.evaluate_cancel_plan(current)
                        if reason:
                            refusal = reason
                            return current
                        return None

                    await store.update_huume_plan(thread_id, offer_id, _mutator)
                    if refusal:
                        step = recorder.record(tool=name, kind="staged", label="Cancel refused", status="rejected", detail=refusal)
                        return {"status": "refused", "message": refusal}, step
                    step = recorder.record(tool=name, kind="staged", label="Cancelled onboarding plan", status="ok")
                    return {"status": "ok", "message": "Discarded that onboarding plan."}, step

                step = recorder.record(tool=name, kind="write", label=f"Unknown cancel target '{target}'", status="error")
                return {"error": f"unknown target '{target}'"}, step

            if name in actions.PILOT_TOOL_REQUIRED_FEATURE:
                # Legal Pilot / Handbook Pilot skills — the routes' mount gates
                # (require_admin_or_client + require_feature) re-asserted here,
                # since the loop itself never decides authorization.
                refusal = actions.evaluate_pilot_tool(tool=name, role=user_role, features=features)
                if refusal:
                    kind = TOOLS_BY_NAME[name].kind
                    step = recorder.record(tool=name, kind=kind, label=f"{name.replace('_', ' ')} unavailable", status="rejected", detail=refusal)
                    return {"status": "refused", "message": refusal}, step

            if name == "list_legal_matters":
                result = await legal_skill.list_matters(company_id=company_id)
                step = recorder.record(tool=name, kind="read", label="Listed legal matters", status="ok")
                return _json_safe(result), step

            if name == "open_legal_matter":
                result = await legal_skill.open_matter(
                    company_id=company_id, actor_user_id=user_id, thread_id=thread_id,
                    title=str(args.get("title") or ""), matter_type=args.get("matter_type"),
                    allegation=args.get("allegation"), jurisdiction_state=args.get("jurisdiction_state"),
                    evidence_start=args.get("evidence_start"), evidence_end=args.get("evidence_end"),
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_legal"] = {"matter_id": result["matter_id"], "title": result.get("title")}
                step = recorder.record(
                    tool=name, kind="write",
                    label="Opened legal matter" if ok else "Could not open legal matter",
                    status="ok" if ok else "error", detail=result.get("title") if ok else result.get("message"),
                )
                return _json_safe(result), step

            if name == "ask_legal_pilot":
                result = await legal_skill.ask_matter(
                    company_id=company_id, actor_user_id=user_id, thread_id=thread_id,
                    matter_id=args.get("matter_id"), state_matter_id=_state_legal().get("matter_id"),
                    question=str(args.get("question") or ""), features=features,
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_legal"] = {"matter_id": result["matter_id"], "title": result.get("title")}
                    _collect_citations(result)
                step = recorder.record(
                    tool=name, kind="write",
                    label="Ran Legal Pilot analysis" if ok else "Legal Pilot analysis failed",
                    status="ok" if ok else "error", detail=result.get("title") if ok else result.get("message"),
                )
                return _json_safe(result), step

            if name == "generate_legal_packet":
                result = await legal_skill.generate_packet(
                    company_id=company_id, actor_user_id=user_id, thread_id=thread_id,
                    matter_id=args.get("matter_id"), state_matter_id=_state_legal().get("matter_id"),
                    kind=str(args.get("kind") or "both"), features=features,
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_legal"] = {"matter_id": result["matter_id"], "title": result.get("title")}
                step = recorder.record(
                    tool=name, kind="write",
                    label="Generated legal packet" if ok else "Could not generate legal packet",
                    status="ok" if ok else ("rejected" if result.get("status") == "refused" else "error"),
                    detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "draft_handbook_content":
                session = await handbook_skill.ensure_session(
                    company_id=company_id, actor_user_id=user_id, thread_id=thread_id,
                    session_id=_state_handbook().get("session_id"),
                )
                result = await handbook_skill.draft_content(
                    company_id=company_id, actor_user_id=user_id, thread_id=thread_id,
                    session=session, request_text=str(args.get("request") or ""),
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_handbook"] = {
                        "session_id": result["session_id"],
                        "pending_drafts": result.get("pending_drafts") or [],
                    }
                    for d in result.get("drafts") or []:
                        handbook_drafts_this_turn.add(d["draft_id"])
                    _collect_citations(result)
                n = len(result.get("drafts") or [])
                step = recorder.record(
                    tool=name, kind="write",
                    label=(f"Proposed {n} handbook draft{'s' if n != 1 else ''}" if ok else "Handbook drafting failed"),
                    status="ok" if ok else ("rejected" if result.get("status") == "refused" else "error"),
                    detail=None if ok else result.get("message"),
                )
                return _json_safe(result), step

            if name == "promote_handbook_drafts":
                session_id = _state_handbook().get("session_id")
                if not session_id:
                    step = recorder.record(tool=name, kind="write", label="Promote refused", status="rejected",
                                           detail="No handbook drafts have been proposed in this thread yet.")
                    return {"status": "refused", "message": "No handbook drafts have been proposed in this thread yet."}, step
                requested, err = actions.filter_promotable_drafts(
                    list(args.get("draft_ids") or []) or None, handbook_drafts_this_turn,
                )
                if err:
                    step = recorder.record(tool=name, kind="write", label="Promote refused", status="rejected", detail=err)
                    return {"status": "refused", "message": err}, step
                result = await handbook_skill.promote(
                    company_id=company_id, actor_user_id=user_id, thread_id=thread_id,
                    session_id=session_id, draft_ids=requested,
                    exclude_ids=handbook_drafts_this_turn, handbook_title=args.get("handbook_title"),
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_handbook"] = {
                        "session_id": result["session_id"],
                        "pending_drafts": result.get("pending_drafts") or [],
                    }
                n = result.get("promoted") or 0
                step = recorder.record(
                    tool=name, kind="write",
                    label=(f"Promoted {n} draft{'s' if n != 1 else ''}" if ok else "Promote refused"),
                    status="ok" if ok else ("rejected" if result.get("status") == "refused" else "error"),
                    detail=result.get("message"),
                )
                return _json_safe(result), step

            step = recorder.record(tool=name, kind="write", label=f"Unknown tool '{name}'", status="error")
            return {"error": f"unknown tool '{name}'"}, step
        except Exception:
            logger.exception("huume tool %s failed for thread %s", name, thread_id)
            step = recorder.record(tool=name, kind="write", label=f"{name} failed", status="error", detail="unexpected error")
            return {"error": "unexpected error"}, step

    client = get_genai_client()
    config = types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=tool_declarations())],
        system_instruction=build_system_prompt(
            company_name=company_name or "your company", today=date.today().isoformat(),
            state_block=build_state_block(current_state),
        ),
    )
    contents = _to_contents(history, attachment_texts)

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

    result_data: dict[str, Any] = {
        "message": final_message,
        "steps": recorder.steps,
        "token_usage": total_usage,
        "state_updates": state_updates,
        "model_calls": model_calls,
    }
    # Citation records the pilot tools resolved this turn — the dispatcher
    # stores them on the assistant message metadata, where MessageBubble's
    # CitationSources renders them (same shape HR Pilot uses). Only ids that
    # survived the pilots' own validate_citations gate ever reach here.
    if turn_citations:
        result_data["citations"] = list(turn_citations.values())
    if turn_dropped:
        result_data["dropped_citations"] = sorted(set(turn_dropped))

    yield {
        "type": "huume_result",
        "data": result_data,
    }
