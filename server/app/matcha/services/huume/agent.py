"""Huume's agent loop — a bounded Gemini tool-calling loop, structurally
mirroring cappe's Merlin (`cappe/services/merlin/agent.py`): fixed bounds on
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
import json
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator, Optional
from uuid import UUID, uuid4

from google.genai import types

from app.core.services.ai_usage import feature_scope
from app.core.services.genai_client import get_genai_client
from app.core.services.rate_limiter import GeminiRateLimiter, RateLimitExceeded

from . import actions, handbook_skill, legal_skill, onboarding_skill, record_view, store
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
# Per-message cap in history — one long pilot answer in an earlier turn
# shouldn't inflate the prompt of every subsequent model call this turn (and
# every later turn, since it stays in history until it ages out).
_MAX_MESSAGE_CHARS = 6_000
# Cap on a tool's args/result before it lands in the huume_steps audit row —
# a large pilot payload (citation records, evidence maps) shouldn't balloon
# the table indefinitely.
_STEP_PAYLOAD_CAP_CHARS = 4_000
# How often to emit a heartbeat status frame while a single tool call is
# still pending (ask_legal_pilot/draft_handbook_content/generate_legal_packet
# each embed their own ~90s-capped Gemini call with no frames of their own).
_TOOL_HEARTBEAT_SECONDS = 15.0


class _StepRecorder:
    """Accumulates step dicts for the run's audit trail + the frames yielded
    to the caller. `seq` is 1-based and monotonic across the whole turn."""

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def record(
        self, *, tool: str, kind: str, label: str, status: str, detail: Optional[str] = None,
        args: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        step = {"seq": len(self.steps) + 1, "tool": tool, "kind": kind, "label": label, "status": status}
        if detail:
            step["detail"] = detail
        if args is not None:
            step["args"] = _cap_payload(args)
        self.steps.append(step)
        return step


_ATTACHMENT_TEXT_CAP = 20_000


def is_sole_finish(call_names: list[str]) -> bool:
    """True when `finish` is the ONLY call in a batch — the only case where it
    may end the turn. Batched alongside other tools it must be deferred: those
    tools still run, and their results have to reach the model before it
    summarizes, or the summary describes work whose outcome it never saw. Pure."""
    return len(call_names) == 1 and call_names[0] == "finish"


def _cap_payload(value: Any) -> Any:
    """Bound a value before it's stored on a step's args/result — returns it
    unchanged when already small, else a truncated preview. Pure."""
    if value is None:
        return None
    safe = _json_safe(value)
    try:
        encoded = json.dumps(safe, default=str)
    except Exception:
        return {"_note": "unserializable"}
    if len(encoded) <= _STEP_PAYLOAD_CAP_CHARS:
        return safe
    return {"_truncated": True, "preview": encoded[:_STEP_PAYLOAD_CAP_CHARS]}


def _accumulate_usage(total: dict[str, int], usage: Any) -> None:
    """Fold one response's usage_metadata into the turn total. thoughts/cached
    were silently dropped before 2026-07 — total_token_count includes thoughts,
    so without them prompt+completion never equalled total in the stored blob."""
    for key, attr in (
        ("prompt_tokens", "prompt_token_count"),
        ("completion_tokens", "candidates_token_count"),
        ("total_tokens", "total_token_count"),
        ("thinking_tokens", "thoughts_token_count"),
        ("cached_tokens", "cached_content_token_count"),
    ):
        total[key] = total.get(key, 0) + (getattr(usage, attr, 0) or 0)


_MAX_IMAGE_PARTS = 6
_MAX_IMAGE_BYTES_TOTAL = 4 * 1024 * 1024


def _to_contents(history: list[dict[str, Any]], attachment_texts: Optional[list[str]] = None) -> list[types.Content]:
    contents: list[types.Content] = []
    image_budget = _MAX_IMAGE_PARTS
    image_bytes_used = 0
    for msg in history[-_MAX_HISTORY_MESSAGES:]:
        role = "model" if msg.get("role") == "assistant" else "user"
        text = str(msg.get("content") or "").strip()
        if len(text) > _MAX_MESSAGE_CHARS:
            text = text[:_MAX_MESSAGE_CHARS] + "\n…[truncated]"

        parts: list[types.Part] = []
        # Multimodal: attach any pre-fetched image bytes on user turns only
        # (messaging.py's fetch_image_parts_for_messages already fetched
        # these before dispatch — same convention as matcha_work_ai's
        # non-Huume prompt builder). Capped so one attachment-heavy turn
        # can't blow the loop's per-call token/size budget.
        if role == "user" and image_budget > 0:
            for image_bytes, mime in (msg.get("image_parts") or []):
                if not image_bytes or image_budget <= 0:
                    continue
                if image_bytes_used + len(image_bytes) > _MAX_IMAGE_BYTES_TOTAL:
                    continue
                parts.append(types.Part.from_bytes(data=image_bytes, mime_type=mime))
                image_budget -= 1
                image_bytes_used += len(image_bytes)

        if not text and not parts:
            continue
        if text or not parts:
            parts.append(types.Part(text=text))
        contents.append(types.Content(role=role, parts=parts))
    if not contents:
        contents.append(types.Content(role="user", parts=[types.Part(text="Hello.")]))

    # Attached file TEXT (from `messaging.py`'s file_context_parts, e.g. an
    # uploaded PDF/doc's extracted text) rides as an extra Part on the final
    # user turn. Distinct from image_parts above, which is inline image
    # bytes on the messages that carried them, not just the last one.
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


# The four HR-ops staged tools are structurally identical to send_offer:
# build a staged dict → evaluate → stage / refuse / execute. Only the payload,
# the id the confirm turn must echo, and the wording differ, so they're a table
# rather than four near-identical if-blocks. `match_key` is the field
# `pre_turn_action` is compared on to tell "confirming the staged one" from
# "staging a new one"; for the two that have no natural persisted id at stage
# time, a server-minted confirm_id plays that role (same as draft_discipline).
_HR_OPS_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "report_incident": {
        "action_type": "ir_report",
        "match_key": "confirm_id",
        "mints_confirm_id": True,
        "fields": ("description", "occurred_at", "incident_type", "severity", "location"),
        "staged_label": "Staged: incident report",
        "refused_label": "Incident report refused",
        "done_label": "Filed incident report",
        "failed_label": "Incident report not filed",
        "done_status": "filed",
    },
    "open_er_case": {
        "action_type": "er_case",
        "match_key": "confirm_id",
        "mints_confirm_id": True,
        "fields": ("description", "title", "category"),
        "staged_label": "Staged: ER case",
        "refused_label": "ER case refused",
        "done_label": "Opened ER case",
        "failed_label": "ER case not opened",
        "done_status": "opened",
    },
    "assign_training": {
        "action_type": "training_assign",
        "match_key": "requirement_id",
        "mints_confirm_id": False,
        "fields": ("requirement_id", "employee_ids", "due_date"),
        "staged_label": "Staged: training assignment",
        "refused_label": "Training assignment refused",
        "done_label": "Assigned training",
        "failed_label": "Training not assigned",
        "done_status": "assigned",
    },
    "decide_pto_request": {
        "action_type": "pto_decision",
        "match_key": "request_id",
        "mints_confirm_id": False,
        "fields": ("request_id", "decision", "note"),
        "staged_label": "Staged: PTO decision",
        "refused_label": "PTO decision refused",
        "done_label": "Applied PTO decision",
        "failed_label": "PTO decision not applied",
        "done_status": "decided",
    },
}


def _build_hr_ops_staged(spec: dict[str, Any], args: dict[str, Any], existing: Any) -> tuple[dict[str, Any], bool]:
    """Pure. Returns (staged_action, confirming) for an HR-ops tool call:
    reuse the pre-turn staged dict when this call echoes its match_key, else
    build a fresh proposal. Comparing against the TURN-START snapshot is what
    makes the two-turn rule structural — an action staged earlier in this same
    turn isn't in it, so it can't be confirmed by the same turn that made it."""
    match_key = spec["match_key"]
    echoed = args.get(match_key)
    echoed = str(echoed).strip() if echoed not in (None, "") else None
    confirming = (
        isinstance(existing, dict)
        and existing.get("type") == spec["action_type"]
        and existing.get("status") == "proposed"
        and echoed is not None
        and str(existing.get(match_key) or "") == echoed
    )
    if confirming:
        return existing, True
    staged: dict[str, Any] = {"type": spec["action_type"], "status": "proposed"}
    if spec["mints_confirm_id"]:
        staged["confirm_id"] = uuid4().hex[:8]
    for field in spec["fields"]:
        value = args.get(field)
        if field == "employee_ids":
            value = [str(v) for v in (value or [])]
        staged[field] = value
    return staged, False


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
    features: Optional[dict[str, Any]] = None,
    integrations: Optional[dict[str, bool]] = None,
    run_id: Optional[UUID] = None,
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

    `features`/`integrations`: pass the dispatcher's already-fetched values
    to skip a second identical `get_thread_features_and_integrations` query
    every turn. Omit only for callers (e.g. tests) with no cheaper source.

    `run_id`: the dispatcher's `huume_runs` row id for this turn, stamped
    onto each entry's `opened_at` in `current_state.huume_records` on a
    successful `show_record` — a nonce the frontend uses to refocus the panel
    on a repeat show_record for the SAME record (record_type+record_id alone
    is an unchanged key then). Optional so existing test callers with no run
    row don't need updating; `opened_at` is simply absent in that case.
    """
    rate_limiter = GeminiRateLimiter()
    recorder = _StepRecorder()
    state_updates: dict[str, Any] = {}
    final_message: Optional[str] = None
    turn_error: Optional[str] = None
    model_calls = 0
    started = time.monotonic()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                   "thinking_tokens": 0, "cached_tokens": 0}

    def elapsed() -> float:
        return time.monotonic() - started

    if features is None or integrations is None:
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
                    features=features, days=args.get("days"),
                )
                step = recorder.record(tool=name, kind="read", label=f"Looked up {args.get('topic')}", status="ok")
                return _json_safe(result), step

            if name == "show_record":
                record_type = str(args.get("record_type") or "")
                raw_ids = args.get("record_ids")
                if not isinstance(raw_ids, list):
                    raw_ids = [raw_ids] if raw_ids not in (None, "") else []
                record_ids = [str(r) for r in raw_ids if str(r).strip()]
                result = await record_view.show_records_for_model(
                    company_id=company_id, record_type=record_type, record_ids=record_ids, features=features,
                )
                ok = result.get("status") == "ok"
                n = len(result.get("records") or [])
                step = recorder.record(
                    tool=name, kind="read",
                    label=(f"Opened {n} {record_type.replace('_', ' ')} record{'s' if n != 1 else ''}" if ok else "Could not open record(s)"),
                    status="ok" if ok else ("rejected" if result.get("status") in ("refused", "not_found") else "error"),
                    detail=result.get("message"),
                )
                if ok:
                    # Locked mid-turn write, NOT state_updates — there are now
                    # two writers of huume_records (this tool and the panel's
                    # close button), and apply_update's wholesale top-level
                    # merge has no lock between a concurrent read and write.
                    # Same reasoning as plan writes going through
                    # store.update_huume_plan instead of state_updates.
                    entries = [
                        {
                            "record_type": result["record_type"],
                            "record_id": r["record_id"],
                            "label": r.get("label"),
                            # A per-turn nonce, not a timestamp to display —
                            # lets the panel tell "re-opened the same record"
                            # apart from "nothing changed", since
                            # record_type+record_id alone is an unchanged key
                            # on a repeat show_record for the same id.
                            "opened_at": str(run_id) if run_id else None,
                        }
                        for r in result["records"]
                    ]
                    await store.update_huume_records(
                        thread_id, lambda current, _entries=entries: record_view.merge_open_records(current, _entries),
                    )
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

            if name == "draft_discipline":
                # No natural persisted id like offer_id exists at stage time
                # (nothing is written to the DB until confirm) — a server-
                # minted confirm_id plays that role instead, echoed to the
                # model via the state block and the staged response.
                existing = pre_turn_action
                confirm_id = str(args.get("confirm_id") or "").strip() or None
                confirming = (
                    isinstance(existing, dict) and existing.get("type") == "discipline_draft"
                    and existing.get("status") == "proposed"
                    and confirm_id is not None and existing.get("confirm_id") == confirm_id
                )
                if confirming:
                    staged = existing
                else:
                    staged = {
                        "type": "discipline_draft", "status": "proposed", "confirm_id": uuid4().hex[:8],
                        "employee_name": args.get("employee_name"), "infraction_type": args.get("infraction_type"),
                        "severity": args.get("severity"), "occurrence_dates": list(args.get("occurrence_dates") or []),
                        "description": args.get("description"), "expected_improvement": args.get("expected_improvement"),
                    }
                verdict = actions.evaluate_huume_action(
                    staged_action=staged, features=features, role=user_role,
                    thread_huume_mode=True, this_turn_staged_new=not confirming,
                )
                if verdict.kind == "stage":
                    state_updates["huume_action"] = staged
                    step = recorder.record(tool=name, kind="staged", label="Staged: discipline write-up", status="ok", detail=verdict.message)
                    return {"status": "staged", "confirm_id": staged["confirm_id"], "message": verdict.message}, step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="staged", label="Discipline draft refused", status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                result = await actions.execute_huume_action(company_id=company_id, actor_user_id=user_id, action=verdict.action)
                filed = result.get("status") == "created"
                state_updates["huume_action"] = {**staged, "status": "filed" if filed else "failed"}
                # hr_pilot_actions' executors hand back post-commit enrichment
                # work as (fn, args, kwargs) tuples for the caller to schedule
                # (the HR Pilot route does the same in ai_turn.py). Pop them
                # before the payload goes to the model — they're callables, not
                # data — and run them best-effort: enrichment failing must not
                # fail a write that already committed.
                for _bg in (result.pop("bg_tasks", None) or []):
                    try:
                        _fn, _args, _kwargs = _bg
                        await _fn(*_args, **_kwargs)
                    except Exception:
                        logger.warning("huume: discipline_draft bg task failed", exc_info=True)
                step = recorder.record(
                    tool=name, kind="write", label="Filed discipline write-up" if filed else "Discipline write-up not filed",
                    status="ok" if filed else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name in _HR_OPS_TOOL_SPECS:
                # Incident report / ER case / training assignment / PTO
                # decision — one flow, table-driven (see _HR_OPS_TOOL_SPECS).
                spec = _HR_OPS_TOOL_SPECS[name]
                staged, confirming = _build_hr_ops_staged(spec, args, pre_turn_action)
                verdict = actions.evaluate_huume_action(
                    staged_action=staged, features=features, role=user_role,
                    thread_huume_mode=True, this_turn_staged_new=not confirming,
                )
                if verdict.kind == "stage":
                    state_updates["huume_action"] = staged
                    step = recorder.record(tool=name, kind="staged", label=spec["staged_label"], status="ok", detail=verdict.message)
                    response = {"status": "staged", "message": verdict.message}
                    # Echo whichever id the confirm turn has to pass back.
                    response[spec["match_key"]] = staged.get(spec["match_key"])
                    return _json_safe(response), step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="staged", label=spec["refused_label"], status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                result = await actions.execute_huume_action(company_id=company_id, actor_user_id=user_id, action=verdict.action)
                done = result.get("status") == "created"
                state_updates["huume_action"] = {**staged, "status": spec["done_status"] if done else "failed"}
                # Post-commit enrichment the executors hand back as
                # (fn, args, kwargs); same best-effort contract as
                # draft_discipline above — a failed enrichment must not fail a
                # write that already committed.
                for _bg in (result.pop("bg_tasks", None) or []):
                    try:
                        _fn, _args, _kwargs = _bg
                        await _fn(*_args, **_kwargs)
                    except Exception:
                        logger.warning("huume: %s bg task failed", name, exc_info=True)
                step = recorder.record(
                    tool=name, kind="write", label=spec["done_label"] if done else spec["failed_label"],
                    status="ok" if done else "error", detail=result.get("message"),
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
                    step = recorder.record(tool=name, kind="staged", label="Cancelled staged action", status="ok")
                    if staged.get("type") == "send_offer":
                        cancel_msg = "Cancelled — that offer will not be sent."
                    elif staged.get("type") == "amend_handbook":
                        cancel_msg = "Cancelled — that handbook will not be amended."
                    else:
                        cancel_msg = "Cancelled — that write-up will not be filed."
                    return {"status": "ok", "message": cancel_msg}, step

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

                target_handbook_id = args.get("target_handbook_id") or None
                if target_handbook_id:
                    # Amending an existing (possibly published) handbook edits
                    # its live sections in place — destructive/irreversible,
                    # unlike promoting to a brand-new draft handbook (which is
                    # just deleted if wrong). Route through the same
                    # stage/confirm envelope as send_offer/discipline_draft
                    # instead of executing on the first ask.
                    existing = pre_turn_action
                    confirming = (
                        isinstance(existing, dict) and existing.get("type") == "amend_handbook"
                        and existing.get("status") == "proposed"
                        and existing.get("target_handbook_id") == target_handbook_id
                    )
                    staged = existing if confirming else {
                        "type": "amend_handbook", "status": "proposed",
                        "target_handbook_id": target_handbook_id,
                        "draft_ids": requested,
                        "handbook_title": args.get("handbook_title"),
                    }
                    verdict = actions.evaluate_huume_action(
                        staged_action=staged, features=features, role=user_role,
                        thread_huume_mode=True, this_turn_staged_new=not confirming,
                    )
                    if verdict.kind == "stage":
                        state_updates["huume_action"] = staged
                        step = recorder.record(tool=name, kind="staged", label="Staged: amend handbook", status="ok", detail=verdict.message)
                        return {"status": "staged", "message": verdict.message}, step
                    if not verdict.ok:
                        step = recorder.record(tool=name, kind="staged", label="Amend handbook refused", status="rejected", detail=verdict.message)
                        return {"status": "refused", "message": verdict.message}, step
                    result = await actions.execute_huume_action(
                        company_id=company_id, actor_user_id=user_id, action=verdict.action,
                        thread_id=thread_id, session_id=session_id, exclude_ids=handbook_drafts_this_turn,
                    )
                    ok = result.get("status") == "ok"
                    state_updates["huume_action"] = {**staged, "status": "amended" if ok else "failed"}
                    if ok:
                        state_updates["huume_handbook"] = {
                            "session_id": result["session_id"],
                            "pending_drafts": result.get("pending_drafts") or [],
                        }
                    step = recorder.record(
                        tool=name, kind="write",
                        label="Amended handbook" if ok else "Amend handbook not applied",
                        status="ok" if ok else ("rejected" if result.get("status") == "refused" else "error"),
                        detail=result.get("message"),
                    )
                    return _json_safe(result), step

                result = await handbook_skill.promote(
                    company_id=company_id, actor_user_id=user_id, thread_id=thread_id,
                    session_id=session_id, draft_ids=requested,
                    exclude_ids=handbook_drafts_this_turn, handbook_title=args.get("handbook_title"),
                    target_handbook_id=None,
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
                _accumulate_usage(total_usage, usage)

            all_parts = [
                part
                for candidate in (response.candidates or [])
                for part in (candidate.content.parts or [] if candidate.content else [])
            ]
            call_parts = [part for part in all_parts if getattr(part, "function_call", None)]
            calls = [p.function_call for p in call_parts]

            if not calls:
                final_message = (getattr(response, "text", None) or "").strip() or None
                break

            # ALL parts, not just the function-call ones — a response mixing
            # reasoning text with tool calls used to drop the text from
            # history between iterations.
            contents.append(types.Content(role="model", parts=all_parts))

            response_parts: list[types.Part] = []
            finished = False
            finish_message: Optional[str] = None
            # `finish` only ends the turn when it's the SOLE call in this
            # batch. If the model calls finish alongside other tools, those
            # tools still need to run and their results still need to reach
            # the model before it actually finishes — otherwise the summary
            # describes work whose outcome the model never saw.
            sole_finish_call = is_sole_finish([c.name for c in calls])

            for call in calls:
                name = call.name
                args = dict(call.args or {})
                if name == "finish":
                    if not sole_finish_call:
                        recorder.record(
                            tool="finish", kind="finish", label="Finish deferred (other tools pending)",
                            status="ok", args=args,
                        )
                        response_parts.append(types.Part.from_function_response(
                            name=name,
                            response={
                                "status": "deferred",
                                "message": "Other tool calls this turn haven't reported back yet — "
                                           "call finish again once you've reviewed their results.",
                            },
                        ))
                        continue
                    finish_message = str(args.get("message") or "").strip() or None
                    finished = True
                    recorder.record(tool="finish", kind="finish", label="Done", status="ok", args=args)
                    continue

                tool = TOOLS_BY_NAME.get(name)
                if tool and tool.kind == "staged":
                    yield {"type": "status", "message": f"Proposing: {name.replace('_', ' ')}…"}
                elif tool and tool.kind == "write":
                    yield {"type": "status", "message": f"Working on: {name.replace('_', ' ')}…"}

                # Bounded by whatever's left of the overall wall clock — a
                # hung provisioning call or pilot Gemini call can no longer
                # stall the stream past the turn's own bound. A heartbeat
                # status frame ticks every _TOOL_HEARTBEAT_SECONDS so the
                # client (and any proxy) sees the connection is still alive.
                task = asyncio.ensure_future(call_tool(name, args))
                remaining = max(1.0, _WALL_CLOCK_SECONDS - elapsed())
                timed_out = False
                while True:
                    wait_for = min(_TOOL_HEARTBEAT_SECONDS, remaining)
                    done, _pending = await asyncio.wait({task}, timeout=wait_for)
                    if task in done:
                        break
                    remaining -= wait_for
                    if remaining <= 0:
                        timed_out = True
                        task.cancel()
                        break
                    yield {"type": "status", "message": f"Still working on: {name.replace('_', ' ')}…"}

                if timed_out:
                    step = recorder.record(
                        tool=name, kind=(tool.kind if tool else "write"),
                        label=f"{name.replace('_', ' ')} timed out", status="error",
                        detail="Timed out waiting for a response.", args=args,
                    )
                    payload = {"error": "timed out"}
                else:
                    payload, step = task.result()
                    if step is not None:
                        step.setdefault("args", _cap_payload(args))
                        step.setdefault("result", _cap_payload(payload))
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
        turn_error = "Huume hit a problem mid-turn — keeping what worked."
        yield {"type": "error", "message": turn_error}

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
    # Set when the turn crashed mid-loop — the dispatcher marks the run
    # `failed` (with this reason) instead of `completed`, which the bare
    # `error` SSE frame above never surfaced to huume_runs on its own.
    if turn_error:
        result_data["error"] = turn_error
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
