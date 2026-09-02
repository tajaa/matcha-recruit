"""Huume's agent loop — a bounded OpenAI Luna tool-calling loop, structurally
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
import re
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, AsyncIterator, Literal, Optional
from uuid import UUID, uuid4

from google.genai import types

from app.core.services.ai_usage import feature_scope
from app.core.services.rate_limiter import GeminiRateLimiter, RateLimitExceeded
from app.matcha.services.matcha_work.work_permissions import WorkAccess, WorkCapability

from . import (
    actions, assets, discipline_skill, er_skill, handbook_skill, inventory_skill, ir_skill,
    legal_skill, onboarding_skill, record_view, routing, store,
)
from .luna_client import get_luna_client
from .prompt import build_state_block, build_system_prompt
from .scope import HuumeSurfaceContext
from .tools import TOOLS_BY_NAME, tool_declarations

logger = logging.getLogger(__name__)

# Kept as an alias (not re-literaled) so stored token usage and any caller
# asking which model Huume uses track routing.py's canonical Luna catalog.
_MODEL = routing.LUNA
_MAX_MODEL_CALLS = 8
_MAX_SCHEDULE_PROPOSALS_PER_TURN = 1
_MAX_TURN_PROMPT_TOKENS = 100_000


def _turn_bound_reason(
    *,
    model_calls: int,
    elapsed_seconds: float,
    prompt_tokens: int,
) -> Optional[Literal["model_call_limit", "wall_clock_limit", "prompt_token_limit"]]:
    """Return the first outer-loop bound that has been reached."""
    if model_calls >= _MAX_MODEL_CALLS:
        return "model_call_limit"
    if elapsed_seconds >= _WALL_CLOCK_SECONDS:
        return "wall_clock_limit"
    if prompt_tokens >= _MAX_TURN_PROMPT_TOKENS:
        return "prompt_token_limit"
    return None


def _rate_limit_disposition(model_calls: int) -> str:
    """Pure decision for a mid-loop RateLimitExceeded (platform-wide Gemini
    capacity, not tenant quota): "raise" before any model call this turn —
    nothing to lose, the turn is unbilled — else "force_finish" — partial
    work + accumulated usage must survive, same as a _MAX_MODEL_CALLS/wall-
    clock bound hit. `model_calls` is incremented before each call (see the
    loop), so this covers both an RLE from the loop's own check_limit and
    one surfaced from inside a tool call."""
    return "raise" if model_calls == 0 else "force_finish"

# 300s, not the 150s the loop launched with: the pilot tools (ask_legal_pilot /
# draft_handbook_content / generate_legal_packet) each embed their own
# 90s-capped Gemini call, and a 150s budget could force-finish the turn before
# the model gets one call to report a result it already paid for. The bound
# still exists to stop runaway loops, not to race a single grounded analysis.
# Raised again from 240s when find_discipline_candidates landed: its batch
# check is internally bounded at 100s (discipline_skill._BATCH_BUDGET_SECONDS)
# — the single heaviest tool call in the loop today — and 240s left too
# little room for the model to still report the result afterward, especially
# on a deep-tier turn thinking hard across multiple model calls.
_WALL_CLOCK_SECONDS = 300.0
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


def _tool_call_fingerprint(name: str, args: dict[str, Any]) -> str:
    """Canonical per-turn identity for a tool call, used for retry guards."""
    canonical = json.dumps(
        _json_safe(args), sort_keys=True, separators=(",", ":"), default=str,
    )
    return f"{name}:{canonical}"


def _is_confirming_schedule_call(args: dict[str, Any], pre_turn_action: Any) -> bool:
    """Return whether a schedule call is the staged action's next-turn confirm."""
    return (
        isinstance(pre_turn_action, dict)
        and pre_turn_action.get("type") == "schedule_change"
        and pre_turn_action.get("status") == "proposed"
        and bool(args.get("confirm_id"))
        and str(args.get("confirm_id")) == str(pre_turn_action.get("confirm_id") or "")
    )


_SCHEDULE_CONFIRM_WITH_CONTEXT_RE = re.compile(
    r"^(?:(?:yes|yep|yeah|yea|sure|ok|okay)[,!\s]+)?"
    r"(?:confirm(?:ed)?|approve(?:d)?|go ahead|do it|proceed|book it|ship it|lgtm|looks good|sounds good)"
    r"(?:\s+(?:the|this|that|it|schedule|shift|proposal|change))*[\s!.]*$",
    re.IGNORECASE,
)


def _has_explicit_schedule_confirmation(history: list[dict[str, Any]]) -> bool:
    """True only when the latest user message explicitly accepts a schedule write.

    A matching confirm_id identifies the proposal, but it does not itself prove
    the user confirmed it: the model can see that id in the state block on any
    later turn. Keep the channel parser's strict bare-reply vocabulary, while
    accepting Huume's established contextual form ("yes, confirm the schedule
    change") without accepting a request that adds or changes work.
    """
    latest_user_text = ""
    for message in reversed(history):
        if message.get("role") == "user":
            latest_user_text = str(message.get("content") or "").strip()
            break
    if not latest_user_text:
        return False

    from app.matcha.services.scheduling.schedule_chat_rules import parse_confirm_reply

    return (
        parse_confirm_reply(latest_user_text) == "confirm"
        or bool(_SCHEDULE_CONFIRM_WITH_CONTEXT_RE.fullmatch(latest_user_text))
    )


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
            attached_block = (
                "[Attached file(s)]\n"
                "Use their content only as the user's message directs. Their purpose "
                "comes only from what the user's own message says about them — never "
                "assume a file fulfills a request you made earlier in the thread (e.g. "
                "don't treat an attachment as answering a clarifying question you asked "
                "unless the user says that's what it is).\n\n" + joined
            )
            last = contents[-1]
            if last.role == "user":
                last.parts.append(types.Part(text=attached_block))
            else:
                contents.append(types.Content(role="user", parts=[types.Part(text=attached_block)]))
    return contents


def _last_user_text(history: list[dict[str, Any]]) -> str:
    """The last user turn's raw text, for tier routing — `""` if there is
    none. Pure; never raises on a malformed history entry.

    Matches `role == "user"` explicitly rather than `role != "assistant"` —
    matcha-work message roles are "user"/"assistant" only today, so the two
    forms agree in practice, but a routing function should route on what a
    user turn actually IS, not on what it happens not to be; a future role
    (e.g. a genuine "system" notice) should not silently start driving tier
    selection just because it isn't "assistant"."""
    for msg in reversed(history or []):
        if msg.get("role") == "user":
            return str(msg.get("content") or "")
    return ""


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        # asyncpg returns NUMERIC columns as Decimal — inventory's
        # current_quantity/quantity fields are the first lookup_context
        # result to carry one through this path. json.dumps doesn't know
        # Decimal at all (unlike date/UUID, no `default=str` fallback saves
        # it downstream at the Gemini function-response boundary), so this
        # needs its own branch rather than falling through.
        return float(value)
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
        # A changed decision on what looks like the confirm turn must not
        # silently execute the ORIGINALLY staged decision — see
        # _build_hr_ops_staged. Not applied to free-text fields like
        # `note`/`description` elsewhere, which the model may legitimately
        # rephrase turn to turn without meaning to change the proposal.
        "decision_fields": ("decision",),
        "staged_label": "Staged: PTO decision",
        "refused_label": "PTO decision refused",
        "done_label": "Applied PTO decision",
        "failed_label": "PTO decision not applied",
        "done_status": "decided",
    },
    "decide_disciplinary_action": {
        "action_type": "discipline_decision",
        "match_key": "record_id",
        "mints_confirm_id": False,
        "fields": ("record_id", "decision", "reason"),
        "decision_fields": ("decision",),
        "staged_label": "Staged: discipline approval decision",
        "refused_label": "Discipline decision refused",
        "done_label": "Discipline decision recorded",
        "failed_label": "Discipline decision not recorded",
        "done_status": "decided",
    },
    "promote_ems_event": {
        "action_type": "ems_promote",
        "match_key": "event_id",
        "mints_confirm_id": False,
        "fields": ("event_id", "title", "incident_type", "severity", "occurred_at", "location"),
        # incident_type/severity are the enum classifier fields the admin can
        # override on the confirm turn ("yes, but mark it critical") — must
        # force a fresh proposal like `decision` does elsewhere, or the
        # changed value is silently dropped in favor of the originally
        # staged one (match_key still matches on event_id). title/location/
        # occurred_at stay excluded, same as free-text description/note.
        "decision_fields": ("incident_type", "severity"),
        "staged_label": "Staged: promote event to incident",
        "refused_label": "Event promotion refused",
        "done_label": "Promoted event to incident",
        "failed_label": "Event not promoted",
        "done_status": "promoted",
    },
    "record_stock_movement": {
        "action_type": "inventory_movement",
        "match_key": "confirm_id",
        "mints_confirm_id": True,
        "fields": ("kind", "item_id", "new_item_name", "quantity", "location_id", "note"),
        # A changed kind or quantity on what looks like the confirm turn must
        # not silently record the ORIGINALLY staged numbers.
        "decision_fields": ("kind", "quantity"),
        "staged_label": "Staged: stock movement",
        "refused_label": "Stock movement refused",
        "done_label": "Recorded stock movement",
        "failed_label": "Stock movement not recorded",
        "done_status": "recorded",
    },
    "record_waste_movement": {
        "action_type": "waste_movement", "match_key": "confirm_id", "mints_confirm_id": True,
        "fields": ("item_id", "quantity", "waste_reason", "note", "location_id"),
        "decision_fields": ("quantity", "waste_reason"), "staged_label": "Staged: waste movement",
        "refused_label": "Waste movement refused", "done_label": "Recorded waste",
        "failed_label": "Waste not recorded", "done_status": "recorded",
    },
    "apply_waste_par_change": {
        "action_type": "waste_par_change", "match_key": "item_id", "mints_confirm_id": False,
        "fields": ("run_id", "item_id"), "staged_label": "Staged: par change",
        "refused_label": "Par change refused", "done_label": "Applied par change", "failed_label": "Par not changed", "done_status": "applied",
    },
    "correct_waste_recipe": {
        "action_type": "waste_recipe_correction", "match_key": "confirm_id", "mints_confirm_id": True,
        "fields": ("sold_name", "components", "location_id"), "staged_label": "Staged: recipe correction",
        "refused_label": "Recipe correction refused", "done_label": "Saved recipe correction", "failed_label": "Recipe not saved", "done_status": "saved",
    },
    "decide_inventory_order": {
        "action_type": "inventory_order_decision",
        "match_key": "order_id",
        "mints_confirm_id": False,
        "fields": ("order_id", "decision", "quantity"),
        "decision_fields": ("decision",),
        "staged_label": "Staged: order decision",
        "refused_label": "Order decision refused",
        "done_label": "Applied order decision",
        "failed_label": "Order decision not applied",
        "done_status": "decided",
    },
    "create_inventory_item": {
        "action_type": "inventory_item_create",
        "match_key": "confirm_id",
        "mints_confirm_id": True,
        "fields": ("name", "unit", "initial_quantity", "low_stock_threshold", "location_id"),
        "staged_label": "Staged: new inventory item",
        "refused_label": "New item refused",
        "done_label": "Added inventory item",
        "failed_label": "Item not added",
        "done_status": "created",
    },
    "archive_inventory_item": {
        "action_type": "inventory_item_archive",
        "match_key": "item_id",
        "mints_confirm_id": False,
        "fields": ("item_id",),
        "staged_label": "Staged: archive inventory item",
        "refused_label": "Archive refused",
        "done_label": "Archived inventory item",
        "failed_label": "Item not archived",
        "done_status": "archived",
    },
    "stage_receipt_from_attachment": {
        "action_type": "inventory_receipt",
        "match_key": "confirm_id",
        "mints_confirm_id": True,
        "fields": ("location_id",),
        "staged_label": "Staged: receipt commit",
        "refused_label": "Receipt commit refused",
        "done_label": "Committed receipt",
        "failed_label": "Receipt not committed",
        "done_status": "committed",
    },
    "propose_schedule_change": {
        "action_type": "schedule_change",
        "match_key": "confirm_id",
        "mints_confirm_id": True,
        # The raw args are kept on the staged dict for the model's own
        # reference (what it asked for), but the real state that execute()
        # reads is proposal_id, merged in below by schedule_skill.propose —
        # not reconstructed from these on the confirm turn.
        "fields": (
            "kind", "changes", "all_vacant_shifts", "location_name", "target_shift_id",
            "target_employee_name", "target_date", "target_time_hint",
            "target_staffing_hint", "target_role_hint",
            "to_employee_name", "second_employee_name", "second_date", "second_time_hint", "second_role_hint",
            "new_date", "new_start_time", "new_end_time", "shift_by_minutes",
            "label", "date", "start_time", "end_time", "count", "employee_names",
        ),
        "staged_label": "Staged: schedule change",
        "refused_label": "Schedule change refused",
        "done_label": "Schedule updated",
        "failed_label": "Schedule change not applied",
        "done_status": "applied",
    },
    "build_week_schedule": {
        "action_type": "schedule_week_draft",
        "match_key": "confirm_id",
        "mints_confirm_id": True,
        "fields": (
            "source_mode", "week_template_id", "exclude_employee_ids",
            "employee_hour_caps",
        ),
        "staged_label": "Staged: generated week",
        "refused_label": "Generated week refused",
        "done_label": "Applied generated week",
        "failed_label": "Generated week not applied",
        "done_status": "applied",
    },
}


def _send_offer_confirming(
    existing: Any, *, offer_id: str, candidate_name: str, recipient_override: Optional[str],
) -> bool:
    """Pure. True iff this send_offer call is confirming the pre-turn staged
    proposal (not staging a fresh one).

    Omission-tolerant on offer_id/candidate_name AND on recipient_email — a
    bare "confirm" repeats neither and still matches the staged offer. But a
    DIFFERENT candidate_name ("send Bob's offer" while Maria's is staged)
    must NOT silently reuse Maria's staged proposal: it has to compare
    against `existing["candidate_name"]`, not just check that some name was
    given. Missing that comparison meant any non-empty candidate_name text
    matched, so "send Bob's offer" right after staging Maria's would confirm
    and send MARIA's offer, skipping resolve_offer_for_send for Bob entirely."""
    if not (isinstance(existing, dict) and existing.get("type") == "send_offer" and existing.get("status") == "proposed"):
        return False
    if offer_id:
        target_matches = existing.get("offer_id") == offer_id
    else:
        existing_candidate_name = str(existing.get("candidate_name") or "")
        target_matches = not candidate_name or candidate_name.lower() in existing_candidate_name.lower()
    if not target_matches:
        return False
    return recipient_override is None or recipient_override == existing.get("recipient_email")


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
        # A changed decision-bearing field on the "confirm" turn (e.g. admin
        # says "no, deny it instead" and the model calls with decision=deny)
        # must NOT silently execute the ORIGINALLY staged decision just
        # because match_key still matches — re-stage fresh instead, so the
        # new decision needs its own confirm turn like any other proposal.
        # An omitted field on the confirm turn (None/"") is not a change.
        # Scoped to `decision_fields` (decision/status enums), not every
        # field in `fields` — a free-text field like description/note may be
        # legitimately rephrased by the model between turns without the
        # proposal itself having changed.
        for field in spec.get("decision_fields") or ():
            new_value = args.get(field)
            if new_value in (None, ""):
                continue
            if str(existing.get(field) or "") != str(new_value):
                confirming = False
                break
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
    work_access: WorkAccess | None = None,
    history: list[dict[str, Any]],
    current_state: dict[str, Any],
    company_name: str,
    attachment_texts: Optional[list[str]] = None,
    features: Optional[dict[str, Any]] = None,
    integrations: Optional[dict[str, bool]] = None,
    run_id: Optional[UUID] = None,
    surface_context: HuumeSurfaceContext | None = None,
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
    schedule_proposal_attempts = 0
    schedule_proposal_fingerprints: set[str] = set()
    executed_schedule_action_confirm_ids: set[str] = set()
    duplicate_tool_calls_blocked = 0
    tool_retry_limit_blocks = 0
    tool_rejections = 0
    stop_reason: Optional[str] = None
    terminal_message: Optional[str] = None
    # Last refusal/error a tool call returned this turn — used only as a
    # fallback final_message when the model's NEXT response has neither a
    # tool call nor text (a reasoning-only response), which otherwise
    # discarded the real reason and reported the generic "nothing was
    # changed" string even though a tool actually explained what went wrong.
    last_tool_issue: Optional[str] = None

    def elapsed() -> float:
        return time.monotonic() - started

    if features is None or integrations is None:
        features, integrations = await store.get_thread_features_and_integrations(company_id)

    if surface_context is None:
        surface_context = HuumeSurfaceContext()
    allowed_tool_names = surface_context.allowed_tools

    # Production callers provide target-company access. Direct skill-engine
    # tests and legacy callers may omit it temporarily and retain the old role
    # compatibility path inside actions.evaluate_*.
    work_capabilities = work_access.capabilities if work_access is not None else None

    # Frozen at turn start — the two-turn confirm check for `send_offer`
    # compares against THIS snapshot, never against state a tool call in
    # this same turn just wrote. `pre_turn_plans` gives the same guarantee
    # for execute_approved_steps: a plan built earlier in this same turn is
    # absent here, so `actions.resolve_plan_offer_id` structurally can't
    # resolve it to something executable this turn.
    pre_turn_action = current_state.get("huume_action")
    pre_turn_plans: dict[str, dict[str, Any]] = dict(current_state.get("huume_plans") or {})
    built_this_turn: set[str] = set()
    # `huume_action` is one persisted slot. Before this guard, each staged
    # branch could report success and overwrite state_updates in the same
    # turn; the model truthfully saw several "staged" responses while only
    # the last survived. The first newly staged action now owns the slot for
    # the rest of this turn. Later staged tools are skipped with an explicit
    # deferral; read tools and confirmations still proceed.
    staged_action_this_turn: Optional[dict[str, Any]] = None

    def _action_label(action_type: Any) -> str:
        return {
            "send_offer": "offer send",
            "discipline_from_incident": "disciplinary action",
            "discipline_draft": "discipline write-up",
            "schedule_change": "schedule change",
            "schedule_week_draft": "generated weekly schedule",
            "schedule_note": "assignment note",
            "meal_break_waiver": "meal-break waiver",
            "work_permit": "work permit",
            "eligibility_case_decision": "eligibility decision",
            "amend_handbook": "handbook amendment",
        }.get(str(action_type or ""), str(action_type or "action").replace("_", " "))

    def _defer_staged_tool(
        tool_name: str, requested_action_type: Any,
    ) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
        if staged_action_this_turn is None:
            return None
        active = _action_label(staged_action_this_turn.get("type"))
        requested = _action_label(requested_action_type)
        message = (
            f"I kept the {active} staged. I did not stage the {requested}; "
            f"confirm or cancel the pending {active} first, then ask me to stage the {requested}."
        )
        step = recorder.record(
            tool=tool_name, kind="staged", label=f"Deferred: {requested}",
            status="skipped", detail=message,
        )
        return {"status": "deferred", "message": message}, step

    def _claim_staged_action(
        tool_name: str, staged: dict[str, Any],
    ) -> Optional[tuple[dict[str, Any], dict[str, Any]]]:
        nonlocal staged_action_this_turn
        deferred = _defer_staged_tool(tool_name, staged.get("type"))
        if deferred is not None:
            return deferred
        staged_action_this_turn = staged
        state_updates["huume_action"] = staged
        return None

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

    def _state_er() -> dict[str, Any]:
        val = state_updates.get("huume_er") or current_state.get("huume_er")
        return val if isinstance(val, dict) else {}

    def _state_ir() -> dict[str, Any]:
        val = state_updates.get("huume_ir") or current_state.get("huume_ir")
        return val if isinstance(val, dict) else {}

    def _collect_citations(result: dict[str, Any]) -> None:
        for rec in result.pop("citation_records", []) or []:
            if isinstance(rec, dict) and rec.get("cid"):
                turn_citations[rec["cid"]] = rec
        turn_dropped.extend(result.get("dropped_citations") or [])

    async def call_tool(name: str, args: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Returns (function_response payload, step dict)."""
        try:
            if allowed_tool_names is not None and name not in allowed_tool_names:
                step = recorder.record(
                    tool=name, kind="read", label=f"Tool unavailable: {name}",
                    status="rejected", detail="Tool is outside this Huume surface.",
                )
                return {"status": "refused", "message": "That capability is not available in this assistant."}, step

            if name == "lookup_context":
                topic = str(args.get("topic") or "")
                if surface_context.is_schedule:
                    allowed_topics = surface_context.allowed_lookup_topics or frozenset()
                    if topic not in allowed_topics:
                        step = recorder.record(
                            tool=name, kind="read", label="Lookup topic unavailable", status="rejected",
                        )
                        return {"status": "refused", "message": "That lookup is outside this schedule workspace."}, step
                result = await onboarding_skill.lookup_context(
                    company_id=company_id, topic=topic, query=args.get("query"),
                    features=features, days=args.get("days"),
                )
                step = recorder.record(tool=name, kind="read", label=f"Looked up {args.get('topic')}", status="ok")
                return _json_safe(result), step

            if name == "get_schedule_overview":
                from app.matcha.services.scheduling.schedule_assistant_context import get_schedule_overview
                if not surface_context.is_schedule or not surface_context.location_id or not surface_context.week_start:
                    step = recorder.record(tool=name, kind="read", label="Schedule context unavailable", status="rejected")
                    return {"status": "refused", "message": "This tool requires a scoped schedule workspace."}, step
                result = await get_schedule_overview(
                    company_id=company_id,
                    location_id=surface_context.location_id,
                    week_start=surface_context.week_start,
                )
                ok = result.get("status") == "ok"
                step = recorder.record(
                    tool=name, kind="read", label="Reviewed schedule overview",
                    status="ok" if ok else "rejected", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "get_week_build_readiness":
                from app.matcha.services.scheduling.week_builder import get_week_build_readiness
                if not surface_context.is_schedule or not surface_context.location_id or not surface_context.week_start:
                    step = recorder.record(
                        tool=name, kind="read", label="Schedule context unavailable", status="rejected",
                    )
                    return {"status": "refused", "message": "This tool requires a scoped schedule workspace."}, step
                result = await get_week_build_readiness(
                    company_id=company_id,
                    location_id=surface_context.location_id,
                    week_start=surface_context.week_start,
                )
                step = recorder.record(
                    tool=name, kind="read", label="Checked week-building readiness",
                    status="ok" if result.get("status") == "ok" else "rejected",
                    detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "list_schedule_eligibility_cases":
                from app.matcha.services.scheduling.schedule_assistant_context import list_schedule_eligibility_cases
                if not surface_context.is_schedule or not surface_context.location_id:
                    step = recorder.record(tool=name, kind="read", label="Eligibility context unavailable", status="rejected")
                    return {"status": "refused", "message": "This tool requires a scoped schedule workspace."}, step
                result = await list_schedule_eligibility_cases(
                    company_id=company_id, location_id=surface_context.location_id,
                )
                step = recorder.record(tool=name, kind="read", label="Reviewed schedule eligibility cases", status="ok")
                return _json_safe(result), step

            if name == "list_assets":
                # Labels only (type + number level) — per-type detail still
                # flows through show_record, which re-checks that type's own
                # feature flag. This tool has no single extra domain flag of
                # its own (it spans every skill), so the gate here is just
                # role + huume + matcha_work — no PILOT_TOOL_REQUIRED_FEATURE
                # entry, unlike every single-domain pilot tool.
                if (
                    WorkCapability.SENSITIVE_RECORD_READ not in work_capabilities
                    if work_capabilities is not None
                    else (user_role or "").strip().lower() not in ("client", "admin")
                ):
                    step = recorder.record(tool=name, kind="read", label="Assets unavailable", status="rejected")
                    return {"status": "refused", "message": "Only a business admin can list assets."}, step
                if not (features.get("huume") and features.get("matcha_work")):
                    step = recorder.record(tool=name, kind="read", label="Assets unavailable", status="rejected")
                    return {"status": "refused", "message": "Huume isn't enabled for this company."}, step
                scope = str(args.get("scope") or "thread")
                try:
                    limit = int(args.get("limit") or 25)
                except (TypeError, ValueError):
                    limit = 25
                result_assets = await assets.list_assets(
                    company_id=company_id,
                    thread_id=None if scope == "company" else thread_id,
                    asset_type=args.get("asset_type"), limit=limit,
                )
                step = recorder.record(tool=name, kind="read", label=f"Listed {len(result_assets)} assets", status="ok")
                return _json_safe({"status": "ok", "assets": result_assets}), step

            if name == "show_record":
                if (
                    WorkCapability.SENSITIVE_RECORD_READ not in work_capabilities
                    if work_capabilities is not None
                    else (user_role or "").strip().lower() not in ("client", "admin")
                ):
                    step = recorder.record(tool=name, kind="read", label="Record unavailable", status="rejected")
                    return {"status": "refused", "message": "Only an authorized Work Reviewer can view sensitive records."}, step
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
                # send_offer is gated on `offer_letters` via evaluate_huume_action
                # below; drafting must be gated the same way — an ungated draft
                # still INSERTs a real offer_letters row and opens the side
                # panel's OfferLetterViewer, which then 403s forever against
                # the /offer-letters mount's own require_feature("offer_letters").
                refusal = actions.evaluate_pilot_tool(tool=name, role=user_role, capabilities=work_capabilities, features=features)
                if refusal:
                    step = recorder.record(tool=name, kind="write", label="Offer letter drafting unavailable", status="rejected", detail=refusal)
                    return {"status": "refused", "message": refusal}, step
                fields = {k: v for k, v in args.items() if k != "offer_id"}
                result = await onboarding_skill.draft_offer_letter(
                    company_id=company_id, thread_id=thread_id, offer_id=args.get("offer_id"), **fields,
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_offer"] = {"offer_id": result["offer_id"], "status": "draft"}
                    await assets.record_offer_draft_asset(
                        company_id=company_id, thread_id=thread_id, actor_user_id=user_id,
                        offer_id=result["offer_id"],
                        candidate_name=str(fields.get("candidate_name") or ""),
                        position_title=str(fields.get("position_title") or ""),
                    )
                step = recorder.record(
                    tool=name, kind="write",
                    label="Drafted offer letter" if ok else "Could not draft offer letter",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "check_offer_status":
                refusal = actions.evaluate_pilot_tool(tool=name, role=user_role, capabilities=work_capabilities, features=features)
                if refusal:
                    step = recorder.record(tool=name, kind="read", label="Offer status unavailable", status="rejected", detail=refusal)
                    return {"status": "refused", "message": refusal}, step
                result = await onboarding_skill.check_offer_status(company_id=company_id, offer_id=str(args.get("offer_id") or ""))
                step = recorder.record(tool=name, kind="read", label="Checked offer status", status="ok" if result.get("status") != "error" else "error")
                return _json_safe(result), step

            if name == "send_offer":
                offer_id = str(args.get("offer_id") or "")
                candidate_name = str(args.get("candidate_name") or "").strip()
                recipient_override = str(args.get("recipient_email") or "").strip() or None
                existing = pre_turn_action

                # Confirm match is omission-tolerant on purpose: a confirm
                # turn that doesn't repeat recipient_email confirms the
                # STAGED recipient; a DIFFERENT recipient_email re-stages
                # (new proposal, fresh confirm) rather than silently
                # switching who gets the email. Strict-echo matching is the
                # schedule_change silent-mismatch bug this avoids.
                confirming = _send_offer_confirming(
                    existing, offer_id=offer_id, candidate_name=candidate_name, recipient_override=recipient_override,
                )

                if not confirming:
                    deferred = _defer_staged_tool(name, "send_offer")
                    if deferred is not None:
                        return deferred

                if confirming:
                    staged = existing
                elif not offer_id and not candidate_name:
                    step = recorder.record(tool=name, kind="staged", label="Send offer needs a target", status="rejected")
                    return {"status": "error", "message": "Name the candidate or pass an offer_id."}, step
                else:
                    resolved = await onboarding_skill.resolve_offer_for_send(
                        company_id=company_id, candidate_name=candidate_name or None, offer_id=offer_id or None,
                    )
                    if resolved["status"] != "ok":
                        step = recorder.record(
                            tool=name, kind="staged", label="Send offer needs disambiguation",
                            status="rejected", detail=resolved.get("message"),
                        )
                        return _json_safe(resolved), step
                    offer = resolved["offer"]
                    recipient_email = recipient_override or offer.get("candidate_email")
                    if not recipient_email:
                        step = recorder.record(tool=name, kind="staged", label="Send offer has no recipient", status="rejected")
                        return {"status": "error", "message": "This offer has no candidate email — give me the address to send it to."}, step
                    staged = {
                        "type": "send_offer", "offer_id": str(offer["id"]), "status": "proposed",
                        "candidate_name": offer.get("candidate_name"), "recipient_email": recipient_email,
                    }

                verdict = actions.evaluate_huume_action(
                    staged_action=staged, features=features, role=user_role, capabilities=work_capabilities,
                    thread_huume_mode=True, this_turn_staged_new=not confirming,
                    schedule_surface=surface_context.is_schedule,
                )
                if verdict.kind == "stage":
                    deferred = _claim_staged_action(name, staged)
                    if deferred is not None:
                        return deferred
                    msg = f"Sends the sign link to {staged['recipient_email']}. {verdict.message}"
                    step = recorder.record(
                        tool=name, kind="staged", label=f"Staged: send offer to {staged['recipient_email']}",
                        status="ok", detail=msg,
                    )
                    return {"status": "staged", "message": msg, "recipient_email": staged["recipient_email"]}, step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="staged", label="Send offer refused", status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                result = await actions.execute_huume_action(
                    company_id=company_id, actor_user_id=user_id, action=verdict.action, thread_id=thread_id,
                )
                state_updates["huume_action"] = {**staged, "status": "sent" if result.get("status") == "created" else "failed"}
                step = recorder.record(
                    tool=name, kind="write", label="Sent offer to candidate" if result.get("status") == "created" else "Failed to send offer",
                    status="ok" if result.get("status") == "created" else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "find_discipline_candidates":
                try:
                    days = int(args.get("days") or 30)
                except (TypeError, ValueError):
                    days = 30
                try:
                    limit = int(args.get("limit") or 5)
                except (TypeError, ValueError):
                    limit = 5
                result = await discipline_skill.find_candidates(
                    company_id=company_id, days=days, limit=limit, recheck=bool(args.get("recheck")),
                )
                ok = result.get("status") == "ok"
                n = len(result.get("candidates") or []) if ok else 0
                step = recorder.record(
                    tool=name, kind="read",
                    label=f"Scanned closed incidents — {n} with possible policy matches" if ok else "Could not scan incidents",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "check_incident_policy":
                result = await discipline_skill.check_incident_policy(
                    company_id=company_id, incident_id=str(args.get("incident_id") or ""),
                )
                step = recorder.record(
                    tool=name, kind="read",
                    label="Checked incident against policy" if result.get("status") == "ok" else "Could not check incident policy",
                    status="ok" if result.get("status") == "ok" else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "list_pending_approvals":
                result = await discipline_skill.list_pending(company_id=company_id)
                step = recorder.record(tool=name, kind="read", label="Listed pending discipline approvals", status="ok")
                return _json_safe(result), step

            if name == "draft_disciplinary_action":
                # Same shape as draft_discipline just below — a server-minted
                # confirm_id plays the role offer_id plays for send_offer,
                # since nothing is written to the DB until confirm.
                existing = pre_turn_action
                confirm_id = str(args.get("confirm_id") or "").strip() or None
                confirming = (
                    isinstance(existing, dict) and existing.get("type") == "discipline_from_incident"
                    and existing.get("status") == "proposed"
                    and confirm_id is not None and existing.get("confirm_id") == confirm_id
                )
                if not confirming:
                    deferred = _defer_staged_tool(name, "discipline_from_incident")
                    if deferred is not None:
                        return deferred
                if confirming:
                    staged = existing
                else:
                    staged = {
                        "type": "discipline_from_incident", "status": "proposed", "confirm_id": uuid4().hex[:8],
                        "employee_id": args.get("employee_id"), "incident_id": args.get("incident_id"),
                        "infraction_type": args.get("infraction_type"), "severity": args.get("severity"),
                        "discipline_type": args.get("discipline_type"),
                        "occurrence_dates": list(args.get("occurrence_dates") or []),
                        "description": args.get("description"), "expected_improvement": args.get("expected_improvement"),
                        "template_id": args.get("template_id"),
                    }
                    if isinstance(staged.get("employee_id"), str) and staged.get("infraction_type") and staged.get("description"):
                        try:
                            from app.database import get_connection
                            async with get_connection() as conn:
                                staged = await discipline_skill.stage_enrichment(conn, company_id=company_id, staged=staged)
                        except Exception:
                            logger.warning("huume: draft_disciplinary_action stage_enrichment failed", exc_info=True)
                verdict = actions.evaluate_huume_action(
                    staged_action=staged, features=features, role=user_role, capabilities=work_capabilities,
                    thread_huume_mode=True, this_turn_staged_new=not confirming,
                    schedule_surface=surface_context.is_schedule,
                )
                if verdict.kind == "stage":
                    deferred = _claim_staged_action(name, staged)
                    if deferred is not None:
                        return deferred
                    step = recorder.record(tool=name, kind="staged", label="Staged: disciplinary action from incident", status="ok", detail=verdict.message)
                    return {"status": "staged", "confirm_id": staged["confirm_id"], "message": verdict.message}, step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="staged", label="Disciplinary action refused", status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                result = await actions.execute_huume_action(
                    company_id=company_id, actor_user_id=user_id, action=verdict.action, thread_id=thread_id,
                )
                filed = result.get("status") == "created"
                state_updates["huume_action"] = {**staged, "status": "filed" if filed else "failed"}
                for _bg in (result.pop("bg_tasks", None) or []):
                    try:
                        _fn, _args, _kwargs = _bg
                        await _fn(*_args, **_kwargs)
                    except Exception:
                        logger.warning("huume: draft_disciplinary_action bg task failed", exc_info=True)
                step = recorder.record(
                    tool=name, kind="write",
                    label="Staged disciplinary action for HR approval" if filed else "Disciplinary action not staged",
                    status="ok" if filed else "error", detail=result.get("message"),
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
                if not confirming:
                    deferred = _defer_staged_tool(name, "discipline_draft")
                    if deferred is not None:
                        return deferred
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
                    staged_action=staged, features=features, role=user_role, capabilities=work_capabilities,
                    thread_huume_mode=True, this_turn_staged_new=not confirming,
                    schedule_surface=surface_context.is_schedule,
                )
                if verdict.kind == "stage":
                    deferred = _claim_staged_action(name, staged)
                    if deferred is not None:
                        return deferred
                    step = recorder.record(tool=name, kind="staged", label="Staged: discipline write-up", status="ok", detail=verdict.message)
                    return {"status": "staged", "confirm_id": staged["confirm_id"], "message": verdict.message}, step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="staged", label="Discipline draft refused", status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                result = await actions.execute_huume_action(
                    company_id=company_id, actor_user_id=user_id, action=verdict.action, thread_id=thread_id,
                )
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

            if name in {
                "propose_assignment_note", "propose_meal_break_waiver", "propose_work_permit",
                "propose_eligibility_case_decision",
            }:
                if not surface_context.is_schedule or not surface_context.location_id:
                    step = recorder.record(tool=name, kind="staged", label="Schedule action unavailable", status="rejected")
                    return {"status": "refused", "message": "This action requires a scoped schedule workspace."}, step
                action_type = {
                    "propose_assignment_note": "schedule_note",
                    "propose_meal_break_waiver": "meal_break_waiver",
                    "propose_work_permit": "work_permit",
                    "propose_eligibility_case_decision": "eligibility_case_decision",
                }[name]
                confirm_id = str(args.get("confirm_id") or "").strip()
                confirming = (
                    isinstance(pre_turn_action, dict)
                    and pre_turn_action.get("type") == action_type
                    and pre_turn_action.get("status") == "proposed"
                    and confirm_id
                    and pre_turn_action.get("confirm_id") == confirm_id
                )
                if not confirming:
                    deferred = _defer_staged_tool(name, action_type)
                    if deferred is not None:
                        return deferred
                if confirming:
                    staged = pre_turn_action
                else:
                    if action_type == "schedule_note":
                        try:
                            shift_uuid = UUID(str(args.get("shift_id") or ""))
                            employee_uuid = UUID(str(args.get("employee_id") or ""))
                        except (TypeError, ValueError):
                            step = recorder.record(
                                tool=name, kind="staged", label="Assignment note refused",
                                status="rejected", detail="The shift or employee identifier is invalid.",
                            )
                            return {"status": "refused", "message": "The shift or employee identifier is invalid."}, step
                        from app.database import get_connection
                        async with get_connection() as _conn:
                            assignment_exists = await _conn.fetchval(
                                """
                                SELECT EXISTS(
                                    SELECT 1
                                    FROM schedule_shift_assignments a
                                    JOIN schedule_shifts s ON s.id=a.shift_id
                                    WHERE a.shift_id=$1 AND a.employee_id=$2
                                      AND s.company_id=$3 AND s.location_id=$4
                                      AND s.status <> 'cancelled'
                                )
                                """,
                                shift_uuid, employee_uuid, company_id, surface_context.location_id,
                            )
                        if not assignment_exists:
                            step = recorder.record(
                                tool=name, kind="staged", label="Assignment note refused",
                                status="rejected", detail="That employee is not assigned to this schedule shift.",
                            )
                            return {"status": "refused", "message": "That employee is not assigned to this schedule shift."}, step
                        staged = {
                            "type": action_type, "status": "proposed", "confirm_id": uuid4().hex[:8],
                            "location_id": str(surface_context.location_id),
                            "shift_id": args.get("shift_id"), "employee_id": args.get("employee_id"),
                            "note": args.get("note"),
                            "visible_to_employee": bool(args.get("visible_to_employee", True)),
                            "include_in_location_digest": bool(args.get("include_in_location_digest", True)),
                            "send_employee_notice": bool(args.get("send_employee_notice", True)),
                        }
                    elif action_type == "meal_break_waiver":
                        try:
                            employee_uuid = UUID(str(args.get("employee_id") or ""))
                        except (TypeError, ValueError):
                            step = recorder.record(
                                tool=name, kind="staged", label="Meal-break waiver refused",
                                status="rejected", detail="The employee identifier is invalid.",
                            )
                            return {"status": "refused", "message": "The employee identifier is invalid."}, step
                        from app.database import get_connection
                        async with get_connection() as _conn:
                            employee_exists = await _conn.fetchval(
                                """
                                SELECT EXISTS(
                                    SELECT 1
                                    FROM employees e
                                    JOIN business_locations l ON l.id=$3
                                    WHERE e.id=$1 AND e.org_id=$2 AND l.company_id=$2
                                      AND l.is_active IS NOT FALSE
                                      AND (
                                          e.work_location_id=$3
                                          OR EXISTS(
                                              SELECT 1
                                              FROM schedule_shift_assignments a
                                              JOIN schedule_shifts s ON s.id=a.shift_id
                                              WHERE a.company_id=$2 AND a.employee_id=e.id
                                                AND s.location_id=$3 AND s.status <> 'cancelled'
                                          )
                                      )
                                )
                                """,
                                employee_uuid, company_id, surface_context.location_id,
                            )
                        if not employee_exists:
                            step = recorder.record(
                                tool=name, kind="staged", label="Meal-break waiver refused",
                                status="rejected", detail="That employee is not in this schedule workspace.",
                            )
                            return {"status": "refused", "message": "That employee is not in this schedule workspace."}, step
                        staged = {
                            "type": action_type, "status": "proposed", "confirm_id": uuid4().hex[:8],
                            "location_id": str(surface_context.location_id),
                            "employee_id": args.get("employee_id"), "on_file": bool(args.get("on_file")),
                            "effective_from": args.get("effective_from") or date.today().isoformat(),
                            "note": args.get("note"),
                        }
                    else:
                        if action_type == "eligibility_case_decision":
                            case_id = str(args.get("case_id") or "").strip()
                            if not case_id:
                                step = recorder.record(tool=name, kind="staged", label="Eligibility decision refused", status="rejected")
                                return {"status": "refused", "message": "Tell me which eligibility case to decide."}, step
                            try:
                                case_uuid = UUID(case_id)
                            except ValueError:
                                step = recorder.record(tool=name, kind="staged", label="Eligibility decision refused", status="rejected")
                                return {"status": "refused", "message": "That eligibility case identifier is invalid."}, step
                            if args.get("decision") not in {"remove", "keep"}:
                                step = recorder.record(tool=name, kind="staged", label="Eligibility decision refused", status="rejected")
                                return {"status": "refused", "message": "Choose remove or keep for the eligibility case."}, step
                            from app.database import get_connection
                            async with get_connection() as _conn:
                                case = await _conn.fetchrow(
                                    """SELECT id, employee_id, requirement_type, status, expires_at, legal_basis
                                       FROM schedule_eligibility_cases
                                       WHERE id=$1 AND company_id=$2 AND location_id=$3""",
                                    case_uuid, company_id, surface_context.location_id,
                                )
                            if not case:
                                step = recorder.record(tool=name, kind="staged", label="Eligibility case not found", status="rejected")
                                return {"status": "refused", "message": "That eligibility case is not in this schedule workspace."}, step
                            staged = {
                                "type": action_type, "status": "proposed", "confirm_id": uuid4().hex[:8],
                                "location_id": str(surface_context.location_id), "case_id": str(case["id"]),
                                "employee_id": str(case["employee_id"]), "requirement_type": case["requirement_type"],
                                "case_status": case["status"],
                                "expires_at": case["expires_at"].isoformat() if case["expires_at"] else None,
                                "legal_basis": case["legal_basis"], "decision": args.get("decision"),
                                "acknowledgement_confirmed": bool(args.get("acknowledgement_confirmed", False)),
                                "acknowledgement_note": args.get("acknowledgement_note"),
                            }
                        else:
                            staged = {
                                "type": action_type, "status": "proposed", "confirm_id": uuid4().hex[:8],
                                "employee_id": args.get("employee_id"), "location_id": str(surface_context.location_id),
                                "issued_at": args.get("issued_at"), "expires_at": args.get("expires_at"),
                            }
                verdict = actions.evaluate_huume_action(
                    staged_action=staged, features=features, role=user_role, capabilities=work_capabilities,
                    thread_huume_mode=True, this_turn_staged_new=not confirming,
                    schedule_surface=True,
                )
                if verdict.kind == "stage":
                    deferred = _claim_staged_action(name, staged)
                    if deferred is not None:
                        return deferred
                    step = recorder.record(tool=name, kind="staged", label=f"Staged: {name.replace('_', ' ')}", status="ok", detail=verdict.message)
                    return {"status": "staged", "confirm_id": staged["confirm_id"], "message": verdict.message}, step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="staged", label=f"{name.replace('_', ' ').title()} refused", status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                # Gemini can emit the same confirming call twice in one batch
                # (parallel function calls); pre_turn_action is frozen for the
                # whole turn so both calls would otherwise see status=="proposed"
                # and both execute, writing the record twice. One confirm_id
                # executes at most once per turn.
                if staged["confirm_id"] in executed_schedule_action_confirm_ids:
                    step = recorder.record(
                        tool=name, kind="staged", label="Duplicate confirmation blocked",
                        status="rejected", detail="This action was already executed this turn.",
                    )
                    return {"status": "refused", "message": "That was already confirmed and executed this turn."}, step
                executed_schedule_action_confirm_ids.add(staged["confirm_id"])
                result = await actions.execute_huume_action(
                    company_id=company_id, actor_user_id=user_id, action=verdict.action, thread_id=thread_id,
                    actor_role=user_role,
                    week_start=surface_context.week_start, week_end=surface_context.week_end,
                )
                ok = result.get("status") == "created"
                state_updates["huume_action"] = {**staged, "status": "applied" if ok else "failed"}
                step = recorder.record(tool=name, kind="write", label=name.replace("propose_", "").replace("_", " ").title(), status="ok" if ok else "error", detail=result.get("message"))
                return _json_safe(result), step

            if name == "find_shift_coverage":
                from app.matcha.services.huume import schedule_skill
                if not surface_context.is_schedule or not surface_context.location_id:
                    step = recorder.record(
                        tool=name, kind="read", label="Coverage lookup unavailable",
                        status="rejected", detail="This tool requires a scoped schedule workspace.",
                    )
                    return {"status": "refused", "message": "This tool requires a scoped schedule workspace."}, step
                result = await schedule_skill.find_coverage(
                    company_id=company_id, role=user_role, features=features,
                    date_str=str(args.get("date") or ""),
                    role_hint=args.get("role_hint"),
                    location_id=surface_context.location_id,
                    schedule_surface=surface_context.is_schedule,
                )
                ok = "error" not in result
                step = recorder.record(
                    tool=name, kind="read",
                    label="Found shift coverage" if ok else "Coverage lookup refused",
                    status="ok" if ok else "rejected", detail=result.get("error"),
                )
                return _json_safe(result), step

            if name == "stage_inventory_order":
                # No confirm needed — queuing IS the staging step, mirroring
                # the channel `@huume` tool of the same name. Unlike the
                # channel version, thread collaborators are a broader/less-
                # trusted population than channel members, so stage_order
                # itself also enforces the client/admin-only gate the other
                # staged inventory tools use, on top of `inventory`'s own
                # feature check.
                result = await inventory_skill.stage_order(
                    company_id=company_id, actor_user_id=user_id, role=user_role, features=features,
                    item_id=args.get("item_id"), new_item_name=args.get("new_item_name"),
                    quantity=args.get("quantity"), location_id_str=args.get("location_id"),
                )
                ok = result.get("status") == "created"
                step = recorder.record(
                    tool=name, kind="write", label="Queued inventory order" if ok else "Order not queued",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name in _HR_OPS_TOOL_SPECS:
                # Incident report / ER case / training assignment / PTO
                # decision — one flow, table-driven (see _HR_OPS_TOOL_SPECS).
                spec = _HR_OPS_TOOL_SPECS[name]
                staged, confirming = _build_hr_ops_staged(spec, args, pre_turn_action)
                if (
                    name in {"propose_schedule_change", "build_week_schedule"}
                    and confirming
                    and not _has_explicit_schedule_confirmation(history)
                ):
                    message = (
                        "That schedule proposal is still waiting for your explicit confirmation. "
                        "Reply \"confirm\" to apply it, or tell me what to change."
                    )
                    step = recorder.record(
                        tool=name, kind="staged", label="Schedule confirmation required",
                        status="rejected", detail=message,
                    )
                    return {"status": "refused", "message": message}, step
                if not confirming:
                    deferred = _defer_staged_tool(name, spec["action_type"])
                    if deferred is not None:
                        return deferred
                if name == "stage_receipt_from_attachment" and not confirming:
                    # Lines ride the staged dict itself, resolved server-side
                    # NOW so the confirm turn commits exactly what was parsed
                    # — the model never sees or retypes line items.
                    parsed = await inventory_skill.parse_attachment_for_staging(
                        attachment_texts, company_id, args.get("location_id"),
                    )
                    if parsed.get("error"):
                        step = recorder.record(
                            tool=name, kind="staged", label="Receipt not staged",
                            status="rejected", detail=parsed["error"],
                        )
                        return {"status": "refused", "message": parsed["error"]}, step
                    staged.update({k: v for k, v in parsed.items() if k != "error"})
                if name == "propose_schedule_change" and not confirming:
                    # Same shape as the receipt special-case above: resolve
                    # the request into a real proposal row NOW (dry-run
                    # checks + advisory lines included), so the confirm turn
                    # executes exactly what was resolved rather than
                    # re-parsing the model's args a second time.
                    from app.matcha.services.huume import schedule_skill
                    from app.database import get_connection as _get_connection
                    async with _get_connection() as _conn:
                        proposed = await schedule_skill.propose(
                            _conn, company_id=company_id, actor_user_id=user_id, args=args,
                            location_id=surface_context.location_id if surface_context.is_schedule else None,
                            week_start=surface_context.week_start if surface_context.is_schedule else None,
                            week_end=surface_context.week_end if surface_context.is_schedule else None,
                        )
                    proposal_status = proposed.get("status")
                    if proposal_status != "ready":
                        message = str(proposed.get("message") or "That schedule change could not be staged.")
                        step = recorder.record(
                            tool=name, kind="staged", label="Schedule change not staged",
                            status="rejected", detail=message,
                        )
                        return {
                            "status": proposal_status or "refused",
                            "message": message,
                        }, step
                    staged.update({k: v for k, v in proposed.items() if k != "status"})
                if name == "build_week_schedule" and not confirming:
                    from app.matcha.services.scheduling.week_builder import propose_week_draft
                    if not surface_context.is_schedule or not surface_context.location_id or not surface_context.week_start:
                        message = "Building a whole week requires a scoped schedule workspace."
                        step = recorder.record(
                            tool=name, kind="staged", label="Generated week not staged",
                            status="rejected", detail=message,
                        )
                        return {"status": "refused", "message": message}, step
                    proposed = await propose_week_draft(
                        company_id=company_id,
                        actor_user_id=user_id,
                        thread_id=thread_id,
                        location_id=surface_context.location_id,
                        week_start=surface_context.week_start,
                        source_mode=str(args.get("source_mode") or "auto"),
                        week_template_id=args.get("week_template_id"),
                        exclude_employee_ids=args.get("exclude_employee_ids"),
                        employee_hour_caps=args.get("employee_hour_caps"),
                    )
                    proposal_status = proposed.get("status")
                    if proposal_status != "ready":
                        message = str(proposed.get("message") or "That week could not be built.")
                        step = recorder.record(
                            tool=name, kind="staged", label="Generated week not staged",
                            status="rejected", detail=message,
                        )
                        response = {"status": proposal_status or "refused", "message": message}
                        if proposed.get("week_templates") is not None:
                            response["week_templates"] = proposed["week_templates"]
                        return _json_safe(response), step
                    if (
                        isinstance(pre_turn_action, dict)
                        and pre_turn_action.get("type") == "schedule_week_draft"
                        and pre_turn_action.get("status") == "proposed"
                        and pre_turn_action.get("generation_run_id")
                    ):
                        from app.matcha.services.scheduling.week_builder import cancel_week_draft
                        await cancel_week_draft(
                            company_id=company_id,
                            generation_run_id=UUID(str(pre_turn_action["generation_run_id"])),
                        )
                    staged.update({
                        key: value for key, value in proposed.items() if key != "status"
                    })
                    staged["location_id"] = str(surface_context.location_id)
                    staged["week_start"] = surface_context.week_start.isoformat()
                verdict = actions.evaluate_huume_action(
                    staged_action=staged, features=features, role=user_role, capabilities=work_capabilities,
                    thread_huume_mode=True, this_turn_staged_new=not confirming,
                    schedule_surface=surface_context.is_schedule,
                )
                if verdict.kind == "stage":
                    deferred = _claim_staged_action(name, staged)
                    if deferred is not None:
                        return deferred
                    step = recorder.record(tool=name, kind="staged", label=spec["staged_label"], status="ok", detail=verdict.message)
                    response = {"status": "staged", "message": verdict.message}
                    # Echo whichever id the confirm turn has to pass back.
                    response[spec["match_key"]] = staged.get(spec["match_key"])
                    if name == "stage_receipt_from_attachment":
                        # Surface what was actually parsed THIS turn — the
                        # model has no other way to see the line count/vendor/
                        # dup warning before the state block renders next turn.
                        response["vendor"] = staged.get("vendor")
                        response["invoice_number"] = staged.get("invoice_number")
                        response["line_count"] = len(staged.get("lines") or [])
                        response["dup_warning"] = staged.get("dup_warning")
                    if name == "build_week_schedule":
                        response["summary"] = staged.get("summary")
                        response["metrics"] = staged.get("metrics")
                        response["unfilled"] = staged.get("unfilled")
                        response["schedule_preview"] = staged.get("schedule_preview")
                        response["preview_truncated"] = staged.get("preview_truncated")
                    return _json_safe(response), step
                if not verdict.ok:
                    step = recorder.record(tool=name, kind="staged", label=spec["refused_label"], status="rejected", detail=verdict.message)
                    return {"status": "refused", "message": verdict.message}, step
                result = await actions.execute_huume_action(
                    company_id=company_id, actor_user_id=user_id, action=verdict.action, thread_id=thread_id,
                    week_start=surface_context.week_start, week_end=surface_context.week_end,
                )
                done = result.get("status") == "created"
                state_updates["huume_action"] = {**staged, "status": spec["done_status"] if done else "failed"}
                # Promote hands the incident to the IR bridge: "now run the
                # pilot on it" resolves without the model re-asking for an id.
                if done and spec["action_type"] == "ems_promote" and result.get("record_id"):
                    state_updates["huume_ir"] = {
                        "incident_id": result["record_id"],
                        "incident_number": result.get("record_label"),
                    }
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
                reason = actions.evaluate_plan_execution(role=user_role, capabilities=work_capabilities, features=features)
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
                    elif staged.get("type") == "discipline_from_incident":
                        cancel_msg = "Cancelled — that disciplinary action will not be filed."
                    elif staged.get("type") == "discipline_decision":
                        cancel_msg = "Cancelled — no approval decision was recorded."
                    elif staged.get("type") == "schedule_week_draft":
                        from app.matcha.services.scheduling.week_builder import cancel_week_draft
                        await cancel_week_draft(
                            company_id=company_id,
                            generation_run_id=UUID(str(staged["generation_run_id"])),
                        )
                        cancel_msg = "Cancelled — that generated week will not be applied."
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
                refusal = actions.evaluate_pilot_tool(tool=name, role=user_role, capabilities=work_capabilities, features=features)
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

            if name == "er_case_brief":
                result = await er_skill.case_brief(company_id=company_id, case_id=str(args.get("case_id") or ""))
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_er"] = {"case_id": result["case_id"], "case_number": result.get("case_number")}
                step = recorder.record(
                    tool=name, kind="read",
                    label="Opened ER case brief" if ok else "Could not brief that ER case",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "ask_er_copilot":
                result = await er_skill.ask_case(
                    company_id=company_id, actor_user_id=user_id,
                    case_id=args.get("case_id"), state_case_id=_state_er().get("case_id"),
                    question=str(args.get("question") or ""),
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_er"] = {"case_id": result["case_id"], "case_number": result.get("case_number")}
                    _collect_citations(result)
                step = recorder.record(
                    tool=name, kind="write",
                    label="Ran ER Copilot analysis" if ok else "ER Copilot analysis failed",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "ask_ir_copilot":
                result = await ir_skill.ask_copilot(
                    company_id=company_id, actor_user_id=user_id,
                    incident_id=args.get("incident_id"), state_incident_id=_state_ir().get("incident_id"),
                    question=str(args.get("question") or ""),
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_ir"] = {"incident_id": result["incident_id"], "incident_number": result.get("incident_number")}
                step = recorder.record(
                    tool=name, kind="write",
                    label="Ran IR Copilot" if ok else "IR Copilot failed",
                    status="ok" if ok else "error", detail=result.get("message"),
                )
                return _json_safe(result), step

            if name == "run_incident_analysis":
                result = await ir_skill.run_analysis(
                    company_id=company_id, actor_user_id=user_id,
                    incident_id=args.get("incident_id"), state_incident_id=_state_ir().get("incident_id"),
                    analysis_type=str(args.get("analysis_type") or ""),
                    refresh=bool(args.get("refresh")),
                )
                ok = result.get("status") == "ok"
                if ok:
                    state_updates["huume_ir"] = {"incident_id": result["incident_id"], "incident_number": result.get("incident_number")}
                step = recorder.record(
                    tool=name, kind="write",
                    label="Ran incident analysis" if ok else "Incident analysis failed",
                    status="ok" if ok else "error", detail=result.get("message"),
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
                    if not confirming:
                        deferred = _defer_staged_tool(name, "amend_handbook")
                        if deferred is not None:
                            return deferred
                    staged = existing if confirming else {
                        "type": "amend_handbook", "status": "proposed",
                        "target_handbook_id": target_handbook_id,
                        "draft_ids": requested,
                        "handbook_title": args.get("handbook_title"),
                    }
                    verdict = actions.evaluate_huume_action(
                        staged_action=staged, features=features, role=user_role, capabilities=work_capabilities,
                        thread_huume_mode=True, this_turn_staged_new=not confirming,
                        schedule_surface=surface_context.is_schedule,
                    )
                    if verdict.kind == "stage":
                        deferred = _claim_staged_action(name, staged)
                        if deferred is not None:
                            return deferred
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

    tier_name = routing.resolve_tier(_last_user_text(history), current_state=current_state)
    tier = routing.TIERS[tier_name]

    client = get_luna_client()
    _system_instruction = build_system_prompt(
        company_name=company_name or "your company", today=date.today().isoformat(),
        state_block=build_state_block(current_state, schedule_surface=surface_context.is_schedule),
        surface_context=surface_context,
    )
    _tools_arg = [types.Tool(function_declarations=tool_declarations(allowed_names=allowed_tool_names))]
    # Two configs retain the planner/executor call boundary. Luna is pinned
    # for both calls; the adapter converts the Gemini-shaped tool contract to
    # Responses API function calls without sending any traffic to Gemini.
    planner_config = types.GenerateContentConfig(
        tools=_tools_arg, system_instruction=_system_instruction,
    )
    executor_config = types.GenerateContentConfig(
        tools=_tools_arg, system_instruction=_system_instruction,
    )
    contents = _to_contents(history, attachment_texts)

    if tier_name == "deep":
        yield {"type": "status", "message": "Thinking hard…"}

    try:
        while True:
            bound_reason = _turn_bound_reason(
                model_calls=model_calls,
                elapsed_seconds=elapsed(),
                prompt_tokens=total_usage["prompt_tokens"],
            )
            if bound_reason:
                stop_reason = bound_reason
                logger.info(
                    "Huume agent hit its bound (reason=%s calls=%s elapsed=%.1fs prompt_tokens=%s)",
                    bound_reason, model_calls, elapsed(), total_usage["prompt_tokens"],
                )
                yield {"type": "status", "message": "Wrapping up…"}
                if bound_reason == "prompt_token_limit":
                    final_message = (
                        "I reached this turn's AI budget, so I stopped before making "
                        "another request. See the completed steps above."
                    )
                break

            is_first_call = model_calls == 0
            model_calls += 1
            call_model = tier.planner_model if is_first_call else tier.executor_model
            call_config = planner_config if is_first_call else executor_config
            call_timeout = min(_CALL_TIMEOUT, max(1.0, _WALL_CLOCK_SECONDS - elapsed()))
            with feature_scope("matcha.huume.loop"):
                response = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=call_model,
                        contents=contents,
                        config=call_config,
                        timeout_seconds=call_timeout,
                        before_request=lambda: rate_limiter.check_limit("huume", "agent"),
                        after_request=lambda: rate_limiter.record_call("huume", "agent"),
                    ),
                    timeout=call_timeout,
                )

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
                # A reasoning-only response (no function call, no text) used
                # to silently fall through to the generic "nothing was
                # changed" string even when a tool called earlier this turn
                # already explained exactly why — surface that instead.
                final_message = (getattr(response, "text", None) or "").strip() or last_tool_issue or None
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
                # Enforce the surface allow-list before any control-flow or
                # bookkeeping special case. `call_tool` keeps the same guard
                # for direct callers, but an unlisted function must not be
                # able to finish a turn or consume a schedule retry slot.
                if allowed_tool_names is not None and name not in allowed_tool_names:
                    step = recorder.record(
                        tool=name, kind="read", label=f"Tool unavailable: {name}",
                        status="rejected", detail="Tool is outside this Huume surface.", args=args,
                    )
                    refusal = {"status": "refused", "message": "That capability is not available in this assistant."}
                    last_tool_issue = refusal["message"]
                    yield {"type": "step", "data": step}
                    response_parts.append(types.Part.from_function_response(name=name, response=refusal))
                    continue
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

                if name == "propose_schedule_change" and not _is_confirming_schedule_call(args, pre_turn_action):
                    fingerprint = _tool_call_fingerprint(name, args)
                    if fingerprint in schedule_proposal_fingerprints:
                        duplicate_tool_calls_blocked += 1
                        step = recorder.record(
                            tool=name, kind="staged", label="Schedule change retry blocked",
                            status="rejected", detail="The same schedule proposal was already attempted this turn.",
                            args=args,
                        )
                        payload = {
                            "status": "refused",
                            "message": "I already tried that exact schedule change this turn. "
                                       "Please provide a different shift detail in your next message.",
                        }
                        tool_rejections += 1
                        terminal_message = payload["message"]
                        stop_reason = "schedule_duplicate_blocked"
                        yield {"type": "step", "data": step}
                        response_parts.append(types.Part.from_function_response(name=name, response=payload))
                        break
                    if schedule_proposal_attempts >= _MAX_SCHEDULE_PROPOSALS_PER_TURN:
                        tool_retry_limit_blocks += 1
                        step = recorder.record(
                            tool=name, kind="staged", label="Schedule change retry blocked",
                            status="rejected", detail="Only one schedule proposal is allowed per turn.",
                            args=args,
                        )
                        payload = {
                            "status": "refused",
                            "message": "I can only attempt one schedule proposal per turn. "
                                       "Please provide the missing shift detail in your next message.",
                        }
                        tool_rejections += 1
                        terminal_message = payload["message"]
                        stop_reason = "schedule_retry_limit"
                        yield {"type": "step", "data": step}
                        response_parts.append(types.Part.from_function_response(name=name, response=payload))
                        break
                    schedule_proposal_attempts += 1
                    schedule_proposal_fingerprints.add(fingerprint)

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
                    last_tool_issue = f"{name.replace('_', ' ')} timed out."
                else:
                    payload, step = task.result()
                    if step is not None:
                        step.setdefault("args", _cap_payload(args))
                        step.setdefault("result", _cap_payload(payload))
                    if isinstance(payload, dict) and (
                        payload.get("status") in {"refused", "error", "clarify", "deferred"} or payload.get("error")
                    ):
                        issue = payload.get("message") or payload.get("error")
                        if issue:
                            last_tool_issue = str(issue)
                if step:
                    yield {"type": "step", "data": step}
                response_parts.append(types.Part.from_function_response(name=name, response=payload))

                if name == "propose_schedule_change" and payload.get("status") in {"clarify", "refused"}:
                    tool_rejections += 1
                    terminal_message = str(payload.get("message") or "The schedule change could not be completed.")
                    stop_reason = (
                        "schedule_clarification"
                        if payload.get("status") == "clarify"
                        else "schedule_refused"
                    )
                    break

            if terminal_message:
                final_message = terminal_message
                break

            if finished:
                final_message = finish_message
                break

            contents.append(types.Content(role="user", parts=response_parts))

    except RateLimitExceeded:
        # Platform-wide AI capacity (the shared rate limiter), not this
        # tenant's own quota. Before the first model call there is nothing
        # to lose — re-raise so the dispatcher reports a clean capacity
        # error and the turn is never billed (see turn_pipeline._run_
        # huume_dispatch). Mid-loop, partial work already exists (tool DB
        # writes have happened, usage is accumulated in total_usage): force-
        # finish exactly like a _MAX_MODEL_CALLS/wall-clock bound hit
        # instead of discarding it — this is the "force-finish with partial
        # work on a bound hit" contract from the module docstring, now
        # covering this bound too. Falls through to the final_message
        # fallback + huume_result yield below with NO further model call.
        if _rate_limit_disposition(model_calls) == "raise":
            raise
        logger.info("Huume agent hit the platform AI limit mid-turn (calls=%s)", model_calls)
        yield {"type": "status", "message": "Hit the AI capacity limit — wrapping up with what's done."}
        # Persisted message must say why it's truncated — otherwise the
        # generic final_message fallback below reads as a normal finish and
        # a reload gives no indication capacity was hit.
        final_message = (
            "I hit the AI capacity limit mid-task — here's what finished before stopping."
            if recorder.steps
            else "I hit the AI capacity limit before completing anything — nothing was changed."
        )
    except Exception as exc:
        logger.warning("Huume agent turn failed: %s", exc, exc_info=True)
        # User-facing text stays generic (no provider internals in the chat),
        # but `turn_error` — persisted to `huume_runs.error` — keeps the real
        # exception so a run can be diagnosed from the DB alone instead of
        # cross-referencing `ai_usage_log` by timestamp (2026-08-26 incident:
        # every failed run's `error` column read the same generic sentence
        # while the actual cause, an OpenAI 400, sat only in usage logging).
        yield {"type": "error", "message": "Huume hit a problem mid-turn — keeping what worked."}
        turn_error = f"{type(exc).__name__}: {exc}"[:1000]

    if not final_message:
        final_message = last_tool_issue or (
            "I wasn't able to finish that — nothing was changed." if not recorder.steps else "Done for now — see the steps above."
        )

    total_usage["model"] = tier.planner_model
    total_usage["tier"] = tier_name
    total_usage["estimated"] = False
    if stop_reason:
        total_usage["stop_reason"] = stop_reason
    total_usage["schedule_proposal_attempts"] = schedule_proposal_attempts
    total_usage["duplicate_tool_calls_blocked"] = duplicate_tool_calls_blocked
    total_usage["tool_retry_limit_blocks"] = tool_retry_limit_blocks
    total_usage["tool_rejections"] = tool_rejections

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
