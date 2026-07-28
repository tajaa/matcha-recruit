"""Huume's confirm-first safety envelope + plan step executors.

Mirrors `services/pilots/hr_pilot_actions.py` exactly: a PURE, DB-free verdict
function carries every check that doesn't need the database (two-turn
confirm, role, feature flags, ordering, idempotency), and thin async
executors do the writes. The matcha-work skill engine does not feature- or
role-gate execution on its own — every guard a normal record write would get
must be re-asserted here.

Staged things live in `mw_threads.current_state`:
  - `huume_action` — a SINGLE staged action, one slot: `send_offer`,
    `discipline_draft`, `ir_report`, `er_case`, `training_assign` or
    `pto_decision`. Staging a new one replaces whatever was pending.
  - `huume_plans`  — onboarding plans staged after an offer is accepted,
    keyed by `offer_id` (a thread can be onboarding several candidates at
    once — each plan is independent).

Both follow the same two-turn rule: the model stages a proposal on one turn
and the loop executes it only after an explicit confirmation on a LATER turn
(never within the same turn that staged it) — see `resolve_plan_offer_id`'s
`built_this_turn` guard below for how that's enforced for plans specifically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

# Only a business admin / platform admin may execute a Huume action or plan
# step. Employees/creators/etc. reaching a thread must never trigger a write.
_ALLOWED_ROLES = {"client", "admin"}

# Every plan step Huume can propose, and the company feature flag (beyond
# `huume` + `matcha_work`) each one re-checks before executing. `None` means
# no extra flag — the step only needs `huume` + the ordering/idempotency
# checks below.
STEP_REQUIRED_FEATURE: dict[str, Optional[str]] = {
    "create_employee": "employees",
    "portal_invitation": "employees",
    "onboarding_tasks": "employees",
    "credential_requirements": "credential_templates",
    "training_assignment": "training",
    "google_workspace": None,   # gated on integration connection state instead
    "slack": None,              # gated on integration connection state instead
    "schedule_note": "employee_schedule",
    "benefits_note": "benefits_admin",
    "jurisdiction_packet_note": None,  # always available, read-only
}

# Steps that depend on the employee record existing before they can run.
_DEPENDS_ON_EMPLOYEE = {
    "portal_invitation", "onboarding_tasks", "credential_requirements",
    "training_assignment", "google_workspace", "slack",
    "schedule_note", "benefits_note", "jurisdiction_packet_note",
}

# Steps that need a connected integration (checked against the `integrations`
# dict passed to evaluate_plan_step: {provider: bool}).
_STEP_INTEGRATION_PROVIDER = {
    "google_workspace": "google_workspace",
    "slack": "slack",
}


@dataclass(frozen=True)
class HuumeVerdict:
    """Result of the pure safety envelope for a staged `huume_action`
    (any type in _HUUME_ACTION_REQUIRED_FEATURE). Mirrors HrActionVerdict — a
    would-be "clarify" (missing/invalid fields) collapses into "refuse"
    here since Huume's callers already treat `not verdict.ok` uniformly as
    a refusal message relayed to the model; a distinct kind would be
    unused.

    kind: "proceed" — cleared for the executor (see `action`).
          "stage"   — staged this turn; tell the admin to confirm.
          "refuse"  — a guard blocked it (includes field-validation and
                      hard-stop failures on the confirm turn).
    """
    kind: str
    message: str
    action: Optional[dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        return self.kind == "proceed"


# Feature flag each staged huume_action type requires beyond `huume` +
# `matcha_work` + role. Mirrors PILOT_TOOL_REQUIRED_FEATURE/STEP_REQUIRED_FEATURE.
_HUUME_ACTION_REQUIRED_FEATURE: dict[str, str] = {
    "send_offer": "offer_letters",
    "discipline_draft": "discipline",
    "ir_report": "incidents",
    "er_case": "er_copilot",
    "training_assign": "training",
    "pto_decision": "time_off",
    "amend_handbook": "handbook_pilot",
}

# Vocabularies the confirm-turn validators check against. Mirrors of the
# authoritative Literals — IRIncidentType/IRSeverity (models/ir_incident.py:10-11)
# and ERCaseCategory (models/er_case.py:11) — kept local so this module stays
# pure and import-light. A model-supplied value outside the set is DROPPED, not
# refused, for the optional classifier-inferred fields; a bad value in a
# required field refuses.
_IR_INCIDENT_TYPES = frozenset({"safety", "behavioral", "property", "near_miss", "other"})
_IR_SEVERITIES = frozenset({"critical", "high", "medium", "low"})
_ER_CATEGORIES = frozenset({
    "harassment", "discrimination", "safety", "retaliation",
    "policy_violation", "misconduct", "wage_hour", "other",
})
_PTO_DECISIONS = frozenset({"approve", "deny"})
# Staged types routed to huume's own hr_ops_skill executors (see
# execute_huume_action for why these don't reuse hr_pilot_actions').
_HR_OPS_ACTIONS = frozenset({"ir_report", "er_case", "training_assign", "pto_decision"})
_MAX_TRAINING_ASSIGNEES = 50
_MAX_PTO_NOTE_CHARS = 500


def evaluate_huume_action(
    *,
    staged_action: Any,
    features: dict[str, Any],
    role: Optional[str],
    thread_huume_mode: bool,
    this_turn_staged_new: bool,
) -> HuumeVerdict:
    """Pure, DB-free safety envelope for executing a staged `huume_action`
    (any type in _HUUME_ACTION_REQUIRED_FEATURE). Order: authz → confirm-first →
    something staged → per-type validation.

    Authz runs BEFORE the confirm-first stage branch — a caller who will
    ultimately fail the role/flag gate is refused immediately, not told
    "reply confirm" and only refused on the later confirm turn."""
    features = features or {}

    if not isinstance(staged_action, dict):
        return HuumeVerdict(kind="refuse", message="There's nothing staged to confirm yet.")
    action_type = str(staged_action.get("type") or "").strip()
    required_feature = _HUUME_ACTION_REQUIRED_FEATURE.get(action_type)
    if required_feature is None:
        return HuumeVerdict(kind="refuse", message="That action type isn't something I can execute.")

    if not thread_huume_mode:
        return HuumeVerdict(kind="refuse", message="Huume actions are only available in a Huume thread.")
    if not features.get("huume"):
        return HuumeVerdict(kind="refuse", message="Huume isn't enabled for this company.")
    if not features.get("matcha_work"):
        return HuumeVerdict(kind="refuse", message="Matcha Work isn't enabled for this company.")
    if not features.get(required_feature):
        return HuumeVerdict(
            kind="refuse",
            message=f"This action needs the {required_feature} feature, which isn't enabled for this company.",
        )
    if (role or "").strip().lower() not in _ALLOWED_ROLES:
        return HuumeVerdict(kind="refuse", message="Only a business admin can do this.")

    if this_turn_staged_new:
        return HuumeVerdict(
            kind="stage",
            message="I've drafted this for your review above. Reply \"confirm\" (or tell me what to change) and I'll do it.",
        )

    if staged_action.get("status") != "proposed":
        return HuumeVerdict(kind="refuse", message="That action isn't awaiting confirmation (it may already be done).")

    if action_type == "send_offer":
        offer_id = staged_action.get("offer_id")
        if not offer_id:
            return HuumeVerdict(kind="refuse", message="There's no offer to send.")
        return HuumeVerdict(kind="proceed", message="", action=dict(staged_action))

    if action_type == "discipline_draft":
        # Field validation + the hard-stop re-check only run on the CONFIRM
        # turn (mirrors hr_pilot_actions.evaluate_hr_action, which validates
        # discipline_draft fields the same way) — the stage turn above
        # already returned before reaching here.
        from app.matcha.services.pilots.hr_pilot_actions import validate_discipline_fields
        from app.matcha.services.pilots.hr_pilot_escalation import classify_message

        normalized, clarify_msg = validate_discipline_fields(staged_action)
        if clarify_msg:
            return HuumeVerdict(kind="refuse", message=clarify_msg)
        gate_text = " ".join([
            normalized["employee_name"], normalized["infraction_type"],
            normalized["description"], str(normalized.get("expected_improvement") or ""),
        ])
        gate = classify_message(gate_text)
        if gate.hard_stop:
            return HuumeVerdict(
                kind="refuse",
                message=gate.notice or "This needs to go to corporate HR rather than being filed here.",
            )
        return HuumeVerdict(kind="proceed", message="", action=normalized)

    if action_type == "ir_report":
        return _validate_ir_report(staged_action)

    if action_type == "er_case":
        return _validate_er_case(staged_action)

    if action_type == "training_assign":
        return _validate_training_assign(staged_action)

    if action_type == "pto_decision":
        return _validate_pto_decision(staged_action)

    if action_type == "amend_handbook":
        # No field validation needed beyond "there's a target" — ownership,
        # archived-status, and upload-vs-template refusal all happen inside
        # HandbookService.amend_handbook_sections, which every caller (this
        # one, the Handbook Pilot UI, and this same skill's non-amend path)
        # goes through regardless.
        if not staged_action.get("target_handbook_id"):
            return HuumeVerdict(kind="refuse", message="There's no handbook to amend.")
        return HuumeVerdict(kind="proceed", message="", action=dict(staged_action))

    return HuumeVerdict(kind="refuse", message="That action type isn't something I can execute.")


def _parse_iso_date(value: Any) -> Optional[date]:
    """Pure — a date, or None when unparseable. Accepts a full datetime and
    keeps its date part (the model sometimes answers a date question with a
    timestamp)."""
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00")).date()
    except (ValueError, TypeError, AttributeError):
        return None


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    """Pure — a datetime, or None when unparseable. A bare date parses to
    midnight, which is what `occurred_at` should mean when the admin gave a
    day but no time."""
    try:
        return datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None


def _is_uuid(value: Any) -> bool:
    """Pure — True when `value` parses as a UUID. Keeps the validators from
    handing a malformed id to a `WHERE id = $1` that would raise asyncpg's
    InvalidTextRepresentation instead of a relayable refusal."""
    try:
        UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _validate_ir_report(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for a staged incident report.

    NOTE the deliberate absence of a hard-stop classifier re-check here (unlike
    discipline_draft). An incident report's narrative contains safety/harassment
    language BY CONSTRUCTION — filing it IS the sanctioned channel for that
    content, exactly as hr_pilot_actions treats its _HANDOFF_ACTIONS. Running
    the gate would refuse precisely the reports the tool exists to file.
    """
    description = str(staged.get("description") or "").strip()
    if not description:
        return HuumeVerdict(kind="refuse", message="There's no description of what happened to file.")

    occurred_at = staged.get("occurred_at")
    if occurred_at not in (None, ""):
        if _parse_iso_datetime(occurred_at) is None:
            return HuumeVerdict(
                kind="refuse",
                message="I couldn't read that incident date/time — give me a specific date (and time if you have it).",
            )

    normalized: dict[str, Any] = {
        "type": "ir_report",
        "description": description,
        "occurred_at": occurred_at or None,
        "location": (str(staged.get("location") or "").strip() or None),
        "confirm_id": staged.get("confirm_id"),
    }
    # Unknown values for the classifier-inferred fields are dropped, not
    # refused — create_incident_core defaults them and the IR classifier
    # overrides only what the user didn't set.
    incident_type = str(staged.get("incident_type") or "").strip().lower()
    if incident_type in _IR_INCIDENT_TYPES:
        normalized["incident_type"] = incident_type
    severity = str(staged.get("severity") or "").strip().lower()
    if severity in _IR_SEVERITIES:
        normalized["severity"] = severity
    return HuumeVerdict(kind="proceed", message="", action=normalized)


def _validate_er_case(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for a staged ER case. Same no-classifier
    reasoning as _validate_ir_report — an ER case is the sanctioned channel
    for exactly the content the hard-stop gate exists to route away from chat.
    """
    description = str(staged.get("description") or "").strip()
    if not description:
        return HuumeVerdict(kind="refuse", message="There's no description of the complaint or dispute to open a case with.")

    normalized: dict[str, Any] = {
        "type": "er_case",
        "description": description,
        "title": (str(staged.get("title") or "").strip() or None),
        "confirm_id": staged.get("confirm_id"),
    }
    category = str(staged.get("category") or "").strip().lower()
    if category in _ER_CATEGORIES:
        normalized["category"] = category
    return HuumeVerdict(kind="proceed", message="", action=normalized)


def _validate_training_assign(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for a staged training assignment. Ids only —
    the tool description sends the model to lookup_context for them, so a
    name here is a bug, not something to resolve fuzzily."""
    requirement_id = staged.get("requirement_id")
    if not _is_uuid(requirement_id):
        return HuumeVerdict(
            kind="refuse",
            message="I need the training requirement's id — look it up with lookup_context(topic='training') first.",
        )

    raw_ids = staged.get("employee_ids")
    if not isinstance(raw_ids, (list, tuple)) or not raw_ids:
        return HuumeVerdict(
            kind="refuse",
            message="I need at least one employee id — look them up with lookup_context(topic='roster') first.",
        )
    if len(raw_ids) > _MAX_TRAINING_ASSIGNEES:
        return HuumeVerdict(
            kind="refuse",
            message=f"That's more than {_MAX_TRAINING_ASSIGNEES} employees at once — use the Training page for a company-wide assignment.",
        )
    employee_ids: list[str] = []
    for value in raw_ids:
        if not _is_uuid(value):
            return HuumeVerdict(
                kind="refuse",
                message="One of those employee ids isn't valid — look them up with lookup_context(topic='roster') first.",
            )
        employee_ids.append(str(value))

    due_date = staged.get("due_date")
    if due_date not in (None, "") and _parse_iso_date(due_date) is None:
        return HuumeVerdict(kind="refuse", message="I couldn't read that due date — give me a specific date.")

    return HuumeVerdict(kind="proceed", message="", action={
        "type": "training_assign",
        "requirement_id": str(requirement_id),
        "employee_ids": employee_ids,
        "due_date": due_date or None,
    })


def _validate_pto_decision(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for a staged PTO approve/deny."""
    request_id = staged.get("request_id")
    if not _is_uuid(request_id):
        return HuumeVerdict(
            kind="refuse",
            message="I need the PTO request's id — look it up with lookup_context(topic='pto_leave') first.",
        )
    decision = str(staged.get("decision") or "").strip().lower()
    if decision not in _PTO_DECISIONS:
        return HuumeVerdict(kind="refuse", message="Tell me whether to approve or deny it.")
    note = str(staged.get("note") or "").strip() or None
    if note and len(note) > _MAX_PTO_NOTE_CHARS:
        note = note[:_MAX_PTO_NOTE_CHARS]
    # A denial's reason is stored on the record (pto_requests.denial_reason) and
    # the core refuses without one — catch it here so the model gets a
    # relayable "ask them why" instead of a failed execute.
    if decision == "deny" and not note:
        return HuumeVerdict(
            kind="refuse",
            message="A denial needs a reason on the record — ask the admin why it's being denied.",
        )
    return HuumeVerdict(kind="proceed", message="", action={
        "type": "pto_decision",
        "request_id": str(request_id),
        "decision": decision,
        "note": note,
    })


def evaluate_plan_execution(*, role: Optional[str], features: dict[str, Any]) -> Optional[str]:
    """Pure. None if the caller may execute plan steps at all (independent of
    which plan/offer), else a refusal reason. Re-asserted on the chat tool
    path (`agent.py`'s execute_approved_steps handler) since the skill engine
    gates nothing itself — the REST route already has this via
    `require_admin_or_client`, so this mirrors that check for parity."""
    features = features or {}
    if (role or "").strip().lower() not in _ALLOWED_ROLES:
        return "Only a business admin can run onboarding plan steps."
    if not features.get("huume"):
        return "Huume isn't enabled for this company."
    if not features.get("matcha_work"):
        return "Matcha Work isn't enabled for this company."
    return None


# Pilot-backed chat tools (Legal Pilot / Handbook Pilot skills) and the company
# feature flag each one requires beyond `huume` + `matcha_work`. Mirrors
# STEP_REQUIRED_FEATURE: the registry the pure envelope below reads from.
PILOT_TOOL_REQUIRED_FEATURE: dict[str, str] = {
    "list_legal_matters": "legal_defense",
    "open_legal_matter": "legal_defense",
    "ask_legal_pilot": "legal_defense",
    "generate_legal_packet": "legal_defense",
    "draft_handbook_content": "handbook_pilot",
    "promote_handbook_drafts": "handbook_pilot",
}

_PILOT_FEATURE_LABEL = {"legal_defense": "Legal Pilot", "handbook_pilot": "Handbook Pilot"}


def evaluate_pilot_tool(*, tool: str, role: Optional[str], features: dict[str, Any]) -> Optional[str]:
    """Pure. None if this pilot-backed tool may run, else a refusal reason.

    Same envelope order as evaluate_plan_execution — the skill engine gates
    nothing itself, and the pilot routes' `require_admin_or_client` +
    `require_feature(...)` mount gates must be re-asserted on the chat path.
    The flag check makes the tools three-state like `lookup_context` topics:
    a company without the pilot gets a plain refusal, not an error."""
    features = features or {}
    required = PILOT_TOOL_REQUIRED_FEATURE.get(tool)
    if required is None:
        return f"Unknown pilot tool '{tool}'."
    if (role or "").strip().lower() not in _ALLOWED_ROLES:
        return "Only a business admin can use the pilot tools."
    if not features.get("huume"):
        return "Huume isn't enabled for this company."
    if not features.get("matcha_work"):
        return "Matcha Work isn't enabled for this company."
    if not features.get(required):
        label = _PILOT_FEATURE_LABEL.get(required, required)
        return f"{label} ('{required}') isn't enabled for this company."
    return None


def filter_promotable_drafts(
    requested: Optional[list[str]], created_this_turn: set[str],
) -> tuple[Optional[list[str]], Optional[str]]:
    """Pure two-turn guard for promote_handbook_drafts, mirroring
    resolve_plan_offer_id: a draft proposed THIS turn cannot be promoted THIS
    turn, even if the admin's message asked for both. Returns
    (requested_ids_or_None, error) — None ids means "all pending", which the
    skill then narrows by excluding `created_this_turn` itself (the DB knows
    what's pending; this function only owns the explicit-id refusal)."""
    created = created_this_turn or set()
    if requested:
        blocked = [d for d in requested if str(d) in created]
        if blocked:
            return None, (
                "Those drafts were just proposed this turn — review them and "
                "promote on your next message."
            )
        return [str(d) for d in requested], None
    return None, None


_ACTIVE_PLAN_STATUSES = {"proposed", "approved", "executing"}


def resolve_plan_offer_id(
    pre_turn_plans: dict[str, dict[str, Any]],
    requested: Optional[str],
    built_this_turn: set[str],
) -> tuple[Optional[str], Optional[str]]:
    """Pure. Returns (offer_id, error). `pre_turn_plans` is the turn-start
    snapshot (frozen before any tool call ran) — a plan built earlier in
    THIS turn is deliberately absent from it, so requesting execution of one
    always fails the lookup here rather than needing a separate check. This
    mirrors send_offer's `pre_turn_action` freeze: nothing staged this turn
    can be executed this turn.
    """
    if requested:
        if requested in built_this_turn:
            return None, (
                "That plan was just built this turn — review the steps and "
                "approve/execute on your next message."
            )
        if requested not in pre_turn_plans:
            return None, f"No onboarding plan is staged for offer {requested}."
        return requested, None

    active = [
        oid for oid, plan in pre_turn_plans.items()
        if isinstance(plan, dict) and plan.get("status") in _ACTIVE_PLAN_STATUSES
    ]
    if not active:
        return None, "There's no onboarding plan staged yet — build one first."
    if len(active) > 1:
        names = ", ".join(
            f"{oid} ({(pre_turn_plans[oid].get('employee') or {}).get('first_name') or 'candidate'})"
            for oid in active
        )
        return None, f"More than one plan is active — say which offer: {names}."
    return active[0], None


def evaluate_cancel_plan(plan: Optional[dict[str, Any]]) -> Optional[str]:
    """Pure. None if `plan` may be discarded, else a refusal reason."""
    if not isinstance(plan, dict):
        return "There's no plan staged for that offer."
    if plan.get("status") in ("executing", "done"):
        return "That plan has already run (in full or in part) — there's nothing left to cancel."
    return None


def merge_executed_steps(base_plan: Optional[dict[str, Any]], executed_plan: dict[str, Any]) -> dict[str, Any]:
    """Pure. Overlay `executed_plan`'s steps onto whatever `base_plan` looks
    like RIGHT NOW, by step key — but keep the base copy of any step the
    executed run left `proposed` (untouched by this execution), so a
    concurrent approve that landed between the unlocked read and this
    locked write isn't clobbered. This is the merge both the REST route and
    the chat tool path share via `store.execute_plan_locked`."""
    base = dict(base_plan) if isinstance(base_plan, dict) and base_plan.get("steps") else executed_plan
    executed_by_key = {s.get("key"): s for s in executed_plan.get("steps", [])}
    merged_steps = []
    for step in base.get("steps", []):
        touched = executed_by_key.get(step.get("key"))
        if touched and touched.get("status") != "proposed":
            merged_steps.append(touched)
        else:
            merged_steps.append(step)
    merged = {
        **base,
        "steps": merged_steps,
        "employee_id": executed_plan.get("employee_id") or base.get("employee_id"),
    }
    if all(s.get("status") in ("done", "skipped", "failed") for s in merged_steps):
        merged["status"] = "done"
    else:
        merged["status"] = "executing"
    return merged


def evaluate_plan_step(
    step: dict[str, Any],
    *,
    features: dict[str, Any],
    integrations: dict[str, bool],
    employee_id: Optional[str],
) -> Optional[str]:
    """Pure. Returns None if `step` may execute now, else a skip/refuse
    reason string. Re-run at execute time (not just at plan-build time) so a
    flag flip or an already-done step between turns is caught."""
    features = features or {}
    integrations = integrations or {}
    key = step.get("key")

    if step.get("record_id"):
        return "already done"
    if step.get("status") == "skipped":
        return step.get("reason") or "skipped"

    # Feature/integration checks come BEFORE the employee-dependency check —
    # at plan-build time employee_id is always None (the employee doesn't
    # exist yet), so if the employee check ran first every dependent step
    # would report "waiting on create_employee" and mask its real reason
    # (missing feature flag / unconnected integration) from the admin.
    required = STEP_REQUIRED_FEATURE.get(key)
    if required and not features.get(required):
        return f"{required} isn't enabled for this company"

    provider = _STEP_INTEGRATION_PROVIDER.get(key)
    if provider and not integrations.get(provider):
        return f"{provider.replace('_', ' ').title()} isn't connected"

    if key in _DEPENDS_ON_EMPLOYEE and not employee_id:
        return "waiting on create_employee to run first"

    return None


# ---------------------------------------------------------------------------
# DB-bound: staged action executor
# ---------------------------------------------------------------------------

async def execute_huume_action(
    *, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any],
    thread_id: Optional[UUID] = None, session_id: Optional[str] = None,
    exclude_ids: Optional[set[str]] = None,
) -> dict[str, Any]:
    """Execute a validated staged huume_action. Assumes evaluate_huume_action
    returned kind=='proceed'.

    `thread_id`/`session_id`/`exclude_ids` are needed only by `amend_handbook`
    — turn-scoped context (which handbook-pilot session, which drafts THIS
    turn just proposed) that has no natural home on the persisted staged
    action dict, unlike every other action type here."""
    from app.matcha.services.huume import onboarding_skill

    if action.get("type") == "amend_handbook":
        from app.matcha.services.huume import handbook_skill
        return await handbook_skill.promote(
            company_id=company_id, actor_user_id=actor_user_id, thread_id=thread_id,
            session_id=session_id, draft_ids=action.get("draft_ids"),
            exclude_ids=exclude_ids or set(),
            handbook_title=action.get("handbook_title"),
            target_handbook_id=action["target_handbook_id"],
        )
    if action.get("type") == "send_offer":
        return await onboarding_skill.execute_send_offer(
            company_id=company_id, actor_user_id=actor_user_id, offer_id=action["offer_id"],
        )
    if action.get("type") == "discipline_draft":
        # Delegates to the SAME executor HR Pilot uses — employee resolution,
        # the deterministic discipline_compliance gate (a statutory block
        # refuses, no override), and the status='draft' write. Its
        # "clarify"/"blocked"/"escalate" statuses all read as a plain refusal
        # to this caller; the message still explains why.
        from app.matcha.services.pilots.hr_pilot_actions import execute_hr_action
        return await execute_hr_action(company_id=company_id, actor_user_id=actor_user_id, action=action)
    if action.get("type") in _HR_OPS_ACTIONS:
        # Huume-own executors rather than hr_pilot_actions'. HR Pilot's
        # ir_report/er_case are hard-stop HAND-OFFS: they hardcode
        # occurred_at=now, category="harassment" and source="hr_pilot", which
        # is the wrong provenance and the wrong field set for an admin filing
        # a report deliberately. Same underlying *_core writers, though.
        from app.matcha.services.huume import hr_ops_skill
        return await hr_ops_skill.execute(
            company_id=company_id, actor_user_id=actor_user_id, action=action,
        )
    return {"status": "error", "message": "Unsupported action."}


# ---------------------------------------------------------------------------
# DB-bound: plan step executors
# ---------------------------------------------------------------------------

@dataclass
class PlanExecutionResult:
    plan: dict[str, Any]
    summaries: list[str] = field(default_factory=list)


def mark_steps_approved(plan: dict[str, Any], step_keys: Optional[list[str]]) -> dict[str, Any]:
    """Pure. Flips matching `proposed` steps to `approved` in place on a copy.
    Empty/None `step_keys` approves every step still `proposed` (an admin
    saying "approve everything"). A step already skipped/done/failed/executing
    is left untouched — this never resurrects or re-queues one."""
    plan = dict(plan)
    steps = [dict(s) for s in (plan.get("steps") or [])]
    wanted = set(step_keys) if step_keys else None
    for step in steps:
        if step.get("status") != "proposed":
            continue
        if wanted is not None and step.get("key") not in wanted:
            continue
        step["status"] = "approved"
    plan["steps"] = steps
    if plan.get("status") == "proposed":
        plan["status"] = "approved"
    return plan


async def execute_plan_steps(
    *, company_id: UUID, actor_user_id: Optional[UUID], plan: dict[str, Any],
    features: dict[str, Any], integrations: dict[str, bool],
) -> PlanExecutionResult:
    """Run every `approved` step in `plan["steps"]` sequentially. Skip-and-
    report: one step failing does not abort the batch. `create_employee`
    always runs first regardless of list order so its `employee_id` is
    available to every dependent step in the same execution."""
    from app.matcha.services.huume import onboarding_skill

    steps = list(plan.get("steps") or [])
    steps.sort(key=lambda s: 0 if s.get("key") == "create_employee" else 1)

    employee_id = plan.get("employee_id")
    summaries: list[str] = []

    for step in steps:
        if step.get("status") != "approved":
            continue
        reason = evaluate_plan_step(
            step, features=features, integrations=integrations, employee_id=employee_id,
        )
        if reason:
            step["status"] = "skipped"
            step["reason"] = reason
            summaries.append(f"Skipped {step.get('label', step.get('key'))}: {reason}")
            continue

        step["status"] = "executing"
        try:
            result = await onboarding_skill.execute_plan_step(
                key=step["key"], company_id=company_id, actor_user_id=actor_user_id,
                plan=plan, employee_id=employee_id,
            )
        except Exception:
            logger.exception("huume plan step %s failed for company %s", step.get("key"), company_id)
            step["status"] = "failed"
            step["error"] = "unexpected error"
            summaries.append(f"Failed {step.get('label', step.get('key'))}: unexpected error")
            continue

        if result.get("status") == "created":
            step["status"] = "done"
            step["record_id"] = result.get("record_id")
            summaries.append(result.get("message") or f"Completed {step.get('label', step.get('key'))}")
            if step["key"] == "create_employee" and result.get("record_id"):
                employee_id = result["record_id"]
                plan["employee_id"] = employee_id
        elif result.get("status") == "skipped":
            step["status"] = "skipped"
            step["reason"] = result.get("message") or "skipped"
            summaries.append(f"Skipped {step.get('label', step.get('key'))}: {step['reason']}")
        else:
            step["status"] = "failed"
            step["error"] = result.get("message") or "failed"
            summaries.append(f"Failed {step.get('label', step.get('key'))}: {step['error']}")

    plan["steps"] = steps
    if all(s.get("status") in ("done", "skipped", "failed") for s in steps):
        plan["status"] = "done"
    else:
        plan["status"] = "executing"
    return PlanExecutionResult(plan=plan, summaries=summaries)
