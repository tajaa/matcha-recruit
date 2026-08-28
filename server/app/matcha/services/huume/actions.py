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

from app.matcha.services.matcha_work.work_permissions import WorkCapability

logger = logging.getLogger(__name__)

# Only a business admin / platform admin may execute a Huume action or plan
# step. Employees/creators/etc. reaching a thread must never trigger a write.
_ALLOWED_ROLES = {"client", "admin"}


def _effective_capabilities(
    *,
    role: Optional[str],
    capabilities: Optional[set[WorkCapability] | frozenset[WorkCapability]],
) -> frozenset[WorkCapability]:
    """Use explicit Work access in production; retain role compatibility for
    direct skill-engine callers and existing pure tests during migration."""

    if capabilities is not None:
        return frozenset(capabilities)
    if (role or "").strip().lower() in _ALLOWED_ROLES:
        return frozenset(WorkCapability)
    return frozenset()

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
    "discipline_from_incident": "discipline",
    "discipline_decision": "discipline",
    # The incidents+role+status half of this gate is re-asserted per call in
    # ems_skill.execute_promote via ems.promote.evaluate_promote — this
    # registry is single-flag, same as every other entry here.
    "ems_promote": "ems",
    "inventory_movement": "inventory",
    "inventory_order_decision": "inventory",
    "inventory_item_create": "inventory",
    "inventory_item_archive": "inventory",
    "inventory_receipt": "inventory",
    "waste_movement": "inventory_waste",
    "waste_par_change": "inventory_waste",
    "waste_recipe_correction": "inventory_waste",
    "schedule_change": "employee_schedule",
    "schedule_week_draft": "employee_schedule",
    "schedule_note": "employee_schedule",
    "meal_break_waiver": "employee_schedule",
    "work_permit": "employee_schedule",
    "eligibility_case_decision": "employee_schedule",
}

# discipline_from_incident / discipline_decision — the incident-triggered
# discipline skill's two staged action types, routed to discipline_skill.py
# rather than hr_pilot_actions or hr_ops_skill (see execute_huume_action).
_DISCIPLINE_SKILL_ACTIONS = frozenset({"discipline_from_incident", "discipline_decision"})
_DISCIPLINE_TYPES = frozenset({"verbal_warning", "written_warning", "pip", "final_warning", "suspension"})
# Mirrors discipline_engine.VALID_SEVERITIES exactly — a narrower set here is
# silently lossy: an unrecognized value becomes None and then the executor's
# "moderate" default, downgrading the record without telling anyone.
_DISCIPLINE_SEVERITIES = frozenset({"minor", "moderate", "severe", "immediate_written"})
_DISCIPLINE_INFRACTION_TYPES = frozenset({"attendance", "performance", "safety", "policy_violation"})
_MIN_DENIAL_REASON_CHARS = 20
# Mirrors hr_pilot_actions._MAX_OCCURRENCE_DATES.
_MAX_OCCURRENCE_DATES = 30

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

# Staged types routed to huume's own inventory_skill executors.
_INVENTORY_ACTIONS = frozenset({
    "inventory_movement", "inventory_order_decision",
    "inventory_item_create", "inventory_item_archive", "inventory_receipt",
    "waste_movement", "waste_par_change", "waste_recipe_correction",
})
_INVENTORY_MOVEMENT_KINDS = frozenset({"out", "stockout", "adjust", "waste"})
_INVENTORY_RECEIVED_STEER_MESSAGE = (
    "Received stock needs provenance — receive it against its open order with "
    "decide_inventory_order(decision='receive'), or attach the invoice CSV and "
    "use stage_receipt_from_attachment."
)
_INVENTORY_ORDER_DECISIONS = frozenset({"approve", "receive", "cancel"})
_MAX_INVENTORY_NOTE_CHARS = 200
_MAX_INVENTORY_NAME_CHARS = 200
# Mirrors services.inventory.receipts.MAX_LINES — duplicated rather than
# imported so this module stays pure and import-light (same reasoning as the
# IR/ER vocab constants above).
_MAX_INVENTORY_RECEIPT_LINES = 200


def _is_positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _is_nonnegative_number(value: Any) -> bool:
    try:
        return float(value) >= 0
    except (TypeError, ValueError):
        return False


def evaluate_huume_action(
    *,
    staged_action: Any,
    features: dict[str, Any],
    role: Optional[str] = None,
    capabilities: Optional[set[WorkCapability] | frozenset[WorkCapability]] = None,
    thread_huume_mode: bool,
    this_turn_staged_new: bool,
    schedule_surface: bool = False,
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
    # `matcha_work` is always required here regardless of surface — the message
    # never reaches this function unless it already passed through the
    # /matcha-work router, which is gated on that flag at the mount (twice:
    # routes/__init__.py and the package constructor). A schedule-only bypass
    # was tried and found unreachable/misleading; don't reintroduce one without
    # giving the schedule turn its own non-/matcha-work endpoint first.
    if not features.get("matcha_work"):
        return HuumeVerdict(kind="refuse", message="Matcha Work isn't enabled for this company.")
    if not features.get(required_feature):
        return HuumeVerdict(
            kind="refuse",
            message=f"This action needs the {required_feature} feature, which isn't enabled for this company.",
        )
    effective_capabilities = _effective_capabilities(role=role, capabilities=capabilities)
    required_capability = (
        WorkCapability.ACTION_PROPOSE
        if this_turn_staged_new
        else WorkCapability.ACTION_EXECUTE
    )
    schedule_manager_authorized = schedule_surface and role in {"admin", "client", "employee"}
    if required_capability not in effective_capabilities and not schedule_manager_authorized:
        return HuumeVerdict(
            kind="refuse",
            message=(
                "You can draft this action, but an authorized Work Operator "
                "must confirm it."
                if this_turn_staged_new
                else "Only an authorized Work Operator can execute this action."
            ),
        )

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
        recipient = staged_action.get("recipient_email")
        if recipient and ("@" not in recipient or "." not in recipient.rsplit("@", 1)[-1]):
            return HuumeVerdict(kind="refuse", message=f"'{recipient}' doesn't look like an email address.")
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

    if action_type == "discipline_from_incident":
        return _validate_discipline_from_incident(staged_action)

    if action_type == "discipline_decision":
        return _validate_discipline_decision(staged_action)

    if action_type == "ems_promote":
        return _validate_ems_promote(staged_action)

    if action_type == "amend_handbook":
        # No field validation needed beyond "there's a target" — ownership,
        # archived-status, and upload-vs-template refusal all happen inside
        # HandbookService.amend_handbook_sections, which every caller (this
        # one, the Handbook Pilot UI, and this same skill's non-amend path)
        # goes through regardless.
        if not staged_action.get("target_handbook_id"):
            return HuumeVerdict(kind="refuse", message="There's no handbook to amend.")
        return HuumeVerdict(kind="proceed", message="", action=dict(staged_action))

    if action_type == "inventory_movement":
        return _validate_inventory_movement(staged_action)

    if action_type == "inventory_order_decision":
        return _validate_inventory_order_decision(staged_action)

    if action_type == "inventory_item_create":
        return _validate_inventory_item_create(staged_action)

    if action_type == "inventory_item_archive":
        return _validate_inventory_item_archive(staged_action)

    if action_type == "inventory_receipt":
        return _validate_inventory_receipt(staged_action)
    if action_type == "waste_movement":
        staged = {**staged_action, "type": "inventory_movement", "kind": "waste"}
        verdict = _validate_inventory_movement(staged)
        return HuumeVerdict(verdict.kind, verdict.message, {**(verdict.action or {}), "type": "waste_movement"} if verdict.action else None)
    if action_type == "waste_par_change":
        if not _is_uuid(staged_action.get("run_id")) or not _is_uuid(staged_action.get("item_id")):
            return HuumeVerdict(kind="refuse", message="I need the forecast run and item ids for that par change.")
        return HuumeVerdict(kind="proceed", message="", action={"type": "waste_par_change", "run_id": str(staged_action["run_id"]), "item_id": str(staged_action["item_id"])})
    if action_type == "waste_recipe_correction":
        if not str(staged_action.get("sold_name") or "").strip() or not isinstance(staged_action.get("components"), list):
            return HuumeVerdict(kind="refuse", message="I need the sold name and recipe components.")
        return HuumeVerdict(kind="proceed", message="", action={"type": "waste_recipe_correction", "sold_name": str(staged_action["sold_name"])[:200], "components": staged_action["components"][:20], "location_id": staged_action.get("location_id")})

    if action_type == "schedule_change":
        # No further field validation needed here — schedule_skill.propose
        # already resolved the request into a real schedule_chat_proposals
        # row (conflict/availability/compliance dry-run included) on the
        # stage turn; proposal_id not surviving to the confirm turn is the
        # one thing that can go wrong, same "there's a target" shape as
        # amend_handbook.
        if not staged_action.get("proposal_id"):
            return HuumeVerdict(kind="refuse", message="There's no schedule change to apply.")
        return HuumeVerdict(kind="proceed", message="", action=dict(staged_action))

    if action_type == "schedule_week_draft":
        required = ("confirm_id", "generation_run_id", "location_id", "week_start")
        if any(not staged_action.get(field) for field in required):
            return HuumeVerdict(
                kind="refuse", message="There's no generated weekly schedule to apply."
            )
        try:
            UUID(str(staged_action["generation_run_id"]))
            UUID(str(staged_action["location_id"]))
            date.fromisoformat(str(staged_action["week_start"]))
        except (TypeError, ValueError):
            return HuumeVerdict(
                kind="refuse", message="The generated weekly schedule has invalid scope details."
            )
        return HuumeVerdict(kind="proceed", message="", action=dict(staged_action))

    if action_type in {"schedule_note", "meal_break_waiver", "work_permit"}:
        if not staged_action.get("confirm_id"):
            return HuumeVerdict(kind="refuse", message="There's no staged schedule action to apply.")
        required = {
            "schedule_note": ("location_id", "shift_id", "employee_id", "note"),
            "meal_break_waiver": ("location_id", "employee_id", "effective_from", "on_file"),
            "work_permit": ("employee_id", "location_id", "expires_at"),
        }[action_type]
        if any(
            staged_action.get(field) in (None, "")
            or (field == "note" and not str(staged_action.get(field) or "").strip())
            for field in required
        ):
            return HuumeVerdict(kind="refuse", message="The staged schedule action is missing required details.")
        try:
            UUID(str(staged_action["location_id"]))
            UUID(str(staged_action["employee_id"]))
            if action_type == "schedule_note":
                UUID(str(staged_action["shift_id"]))
            elif action_type == "meal_break_waiver":
                date.fromisoformat(str(staged_action["effective_from"]))
            elif action_type == "work_permit":
                expires = date.fromisoformat(str(staged_action["expires_at"]))
                issued = staged_action.get("issued_at")
                if issued and date.fromisoformat(str(issued)) > expires:
                    return HuumeVerdict(kind="refuse", message="The permit issue date is after its expiry date.")
        except (TypeError, ValueError):
            return HuumeVerdict(kind="refuse", message="One of the staged schedule identifiers or dates is invalid.")
        return HuumeVerdict(kind="proceed", message="", action=dict(staged_action))

    if action_type == "eligibility_case_decision":
        if (
            not staged_action.get("confirm_id")
            or not staged_action.get("case_id")
            or not staged_action.get("location_id")
        ):
            return HuumeVerdict(kind="refuse", message="There's no staged eligibility decision to apply.")
        if staged_action.get("decision") not in {"remove", "keep"}:
            return HuumeVerdict(kind="refuse", message="Eligibility decisions must be remove or keep.")
        try:
            UUID(str(staged_action["case_id"]))
            UUID(str(staged_action["location_id"]))
        except (TypeError, ValueError):
            return HuumeVerdict(kind="refuse", message="The eligibility case identifier is invalid.")
        if staged_action.get("decision") == "keep":
            if not staged_action.get("acknowledgement_confirmed"):
                return HuumeVerdict(
                    kind="refuse",
                    message="Keeping the employee requires explicit acknowledgement of the compliance risk.",
                )
            note = str(staged_action.get("acknowledgement_note") or "").strip()
            if len(note) < 20:
                return HuumeVerdict(
                    kind="refuse",
                    message="Keeping the employee requires a written acknowledgement of at least 20 characters.",
                )
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


def _validate_ems_promote(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for promoting a logged EMS event into an IR
    incident. No hard-stop classifier re-check, same reasoning as
    _validate_ir_report — an event's narrative already went through the
    sanctioned EMS intake channel; this only decides whether to promote it.

    occurred_at is parsed to a real datetime (not left as a string, unlike
    _validate_ir_report) because ems.promote.promote_event runs
    naive_occurred_at on it, which needs a datetime to check tzinfo against —
    a bare string would silently no-op that check."""
    event_id = str(staged.get("event_id") or "").strip()
    if not _is_uuid(event_id):
        return HuumeVerdict(
            kind="refuse",
            message="A valid event_id is required — get one from lookup_context(topic='events').",
        )

    occurred_at = None
    if staged.get("occurred_at") not in (None, ""):
        occurred_at = _parse_iso_datetime(staged["occurred_at"])
        if occurred_at is None:
            return HuumeVerdict(kind="refuse", message="occurred_at isn't a valid ISO datetime.")

    incident_type = str(staged.get("incident_type") or "").strip().lower()
    severity = str(staged.get("severity") or "").strip().lower()
    normalized: dict[str, Any] = {
        "type": "ems_promote",
        "event_id": event_id,
        "title": (str(staged.get("title") or "").strip() or None),
        "incident_type": incident_type if incident_type in _IR_INCIDENT_TYPES else None,
        "severity": severity if severity in _IR_SEVERITIES else None,
        "occurred_at": occurred_at,
        "location": (str(staged.get("location") or "").strip() or None),
    }
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


def _validate_inventory_movement(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for a staged stock movement. Exactly one of
    item_id/new_item_name; quantity required for out/adjust, ignored for
    stockout (it always zeroes the count regardless of what's passed).
    kind='in' is refused here as a confirm-turn backstop — the tool's schema
    enum (tools.py) already excludes it as the primary gate, since a bare
    chat-asserted receive has no audit trail (see inventory/CLAUDE.md's
    provenance invariant: an `in` movement must come from mark_received or
    commit_receipt_lines, never a raw movement write)."""
    kind = str(staged.get("kind") or "").strip().lower()
    if kind == "in":
        return HuumeVerdict(kind="refuse", message=_INVENTORY_RECEIVED_STEER_MESSAGE)
    if kind not in _INVENTORY_MOVEMENT_KINDS:
        return HuumeVerdict(
            kind="refuse",
            message="Tell me whether this is stock out, a stockout, or a count adjustment.",
        )

    item_id = staged.get("item_id")
    new_item_name = str(staged.get("new_item_name") or "").strip()
    if item_id and not _is_uuid(item_id):
        return HuumeVerdict(
            kind="refuse",
            message="That item id isn't valid — look it up with lookup_context(topic='inventory') first.",
        )
    if not item_id and not new_item_name:
        return HuumeVerdict(
            kind="refuse",
            message="I need either an existing item id (lookup_context(topic='inventory')) or a name for a new item.",
        )

    if kind == "waste" and not item_id:
        return HuumeVerdict(kind="refuse", message="Waste must be tied to an existing item — look it up first.")
    quantity = staged.get("quantity")
    if kind == "stockout":
        quantity = None
    elif kind == "adjust":
        if not _is_nonnegative_number(quantity):
            return HuumeVerdict(kind="refuse", message="What should the count be set to?")
        quantity = float(quantity)
    else:
        if not _is_positive_number(quantity):
            return HuumeVerdict(kind="refuse", message="How many, and of what unit?")
        quantity = float(quantity)

    location_id = staged.get("location_id")
    if location_id and not _is_uuid(location_id):
        return HuumeVerdict(
            kind="refuse",
            message="That location id isn't valid — look it up with lookup_context(topic='locations') first.",
        )

    note = str(staged.get("note") or "").strip() or None
    if note and len(note) > _MAX_INVENTORY_NOTE_CHARS:
        note = note[:_MAX_INVENTORY_NOTE_CHARS]

    waste_reason = str(staged.get("waste_reason") or "unknown").strip().lower()
    if kind == "waste" and waste_reason not in {
        "spoilage", "expired", "prep_error", "overproduction", "breakage", "contamination", "theft", "comp", "recall", "unknown",
    }:
        return HuumeVerdict(kind="refuse", message="Choose a valid waste reason, such as spoilage, expired, or breakage.")
    return HuumeVerdict(kind="proceed", message="", action={
        "type": "inventory_movement",
        "kind": kind,
        "item_id": str(item_id) if item_id else None,
        "new_item_name": new_item_name or None,
        "quantity": quantity,
        "location_id": str(location_id) if location_id else None,
        "note": note,
        "waste_reason": waste_reason if kind == "waste" else None,
    })


def _validate_inventory_order_decision(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for a staged order approve/receive/cancel."""
    order_id = staged.get("order_id")
    if not _is_uuid(order_id):
        return HuumeVerdict(
            kind="refuse",
            message="I need the order's id — check lookup_context(topic='inventory') for an item's open order.",
        )
    decision = str(staged.get("decision") or "").strip().lower()
    if decision not in _INVENTORY_ORDER_DECISIONS:
        return HuumeVerdict(kind="refuse", message="Tell me whether to approve, receive, or cancel it.")
    quantity = staged.get("quantity")
    if quantity not in (None, "") :
        if not _is_positive_number(quantity):
            return HuumeVerdict(kind="refuse", message="That quantity doesn't look right — what was actually delivered?")
        quantity = float(quantity)
    else:
        quantity = None
    return HuumeVerdict(kind="proceed", message="", action={
        "type": "inventory_order_decision",
        "order_id": str(order_id),
        "decision": decision,
        "quantity": quantity,
    })


def _validate_inventory_item_create(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for staging a brand-new inventory item."""
    name = str(staged.get("name") or "").strip()
    if not name:
        return HuumeVerdict(kind="refuse", message="What should the item be called?")
    name = name[:_MAX_INVENTORY_NAME_CHARS]

    unit = str(staged.get("unit") or "").strip() or None
    if unit and len(unit) > 40:
        unit = unit[:40]

    for field in ("initial_quantity", "low_stock_threshold"):
        value = staged.get(field)
        if value not in (None, "") and not _is_nonnegative_number(value):
            return HuumeVerdict(kind="refuse", message=f"That {field.replace('_', ' ')} doesn't look right.")

    location_id = staged.get("location_id")
    if location_id and not _is_uuid(location_id):
        return HuumeVerdict(
            kind="refuse",
            message="That location id isn't valid — look it up with lookup_context(topic='locations') first.",
        )

    return HuumeVerdict(kind="proceed", message="", action={
        "type": "inventory_item_create",
        "name": name,
        "unit": unit,
        "initial_quantity": float(staged["initial_quantity"]) if staged.get("initial_quantity") not in (None, "") else None,
        "low_stock_threshold": float(staged["low_stock_threshold"]) if staged.get("low_stock_threshold") not in (None, "") else None,
        "location_id": str(location_id) if location_id else None,
    })


def _validate_inventory_item_archive(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for archiving an inventory item."""
    item_id = staged.get("item_id")
    if not _is_uuid(item_id):
        return HuumeVerdict(
            kind="refuse",
            message="I need the item's id — look it up with lookup_context(topic='inventory') first.",
        )
    return HuumeVerdict(kind="proceed", message="", action={
        "type": "inventory_item_archive",
        "item_id": str(item_id),
    })


def _validate_inventory_receipt(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for committing a receipt parsed from a thread
    attachment. `lines` was populated server-side at STAGE time
    (agent.py's stage_receipt_from_attachment special-case, BEFORE this
    validator ever runs) — never supplied or editable by the model, so this
    only checks shape, not per-line semantics (commit_receipt_lines does
    that, same as the REST route)."""
    lines = staged.get("lines")
    if not isinstance(lines, list) or not lines:
        return HuumeVerdict(
            kind="refuse",
            message="There's nothing staged to commit — attach the invoice CSV again.",
        )
    if len(lines) > _MAX_INVENTORY_RECEIPT_LINES:
        return HuumeVerdict(kind="refuse", message="That receipt has too many lines to commit at once.")
    location_id = staged.get("location_id")
    if location_id and not _is_uuid(location_id):
        return HuumeVerdict(
            kind="refuse",
            message="That location id isn't valid — look it up with lookup_context(topic='locations') first.",
        )
    return HuumeVerdict(kind="proceed", message="", action={
        "type": "inventory_receipt",
        "lines": lines,
        "vendor": staged.get("vendor"),
        "invoice_number": staged.get("invoice_number"),
        "location_id": str(location_id) if location_id else None,
    })


def _validate_discipline_from_incident(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for a staged incident-triggered discipline draft.

    Hard-stop asymmetry, deliberate: the classifier re-runs ONLY on a STANDALONE
    draft (no incident_id). A draft sourced from a filed incident describes
    content that already reached the company through its sanctioned legal-record
    channel — the same reasoning `_validate_ir_report` relies on — and the
    supervisor-surface workplace_safety patterns (`injur*`, `accident`,
    `bleeding`, `hospital`, `OSHA`) match nearly every real safety incident's own
    narrative, so re-running the gate there would refuse the flagship
    incident->discipline path outright. Standalone drafts keep the full hard
    stop, identical to `discipline_draft`."""
    employee_id = staged.get("employee_id")
    if not _is_uuid(employee_id):
        return HuumeVerdict(
            kind="refuse",
            message="I need the employee's id — look it up with lookup_context(topic='roster') first.",
        )

    infraction_type = str(staged.get("infraction_type") or "").strip().lower()
    if infraction_type not in _DISCIPLINE_INFRACTION_TYPES:
        return HuumeVerdict(
            kind="refuse",
            message="I need an infraction type (attendance, performance, safety, or policy_violation).",
        )

    description = str(staged.get("description") or "").strip()
    if not description:
        return HuumeVerdict(kind="refuse", message="There's no factual account of what happened to draft from.")

    incident_id = staged.get("incident_id")
    if incident_id is not None and not _is_uuid(incident_id):
        return HuumeVerdict(kind="refuse", message="That incident id doesn't look valid.")

    severity = str(staged.get("severity") or "").strip().lower()
    discipline_type = str(staged.get("discipline_type") or "").strip().lower()
    template_id = staged.get("template_id")
    if template_id is not None and not _is_uuid(template_id):
        template_id = None

    raw_dates = staged.get("occurrence_dates")
    occurrence_dates: list[str] = []
    if isinstance(raw_dates, (list, tuple)):
        for value in raw_dates:
            parsed = _parse_iso_date(value)
            if parsed is None:
                return HuumeVerdict(kind="refuse", message="I couldn't read one of those occurrence dates — give me specific dates.")
            occurrence_dates.append(parsed.isoformat())
    if len(occurrence_dates) > _MAX_OCCURRENCE_DATES:
        return HuumeVerdict(
            kind="refuse",
            message="That's a lot of dates for one write-up — narrow it to the specific occurrences at issue.",
        )
    if incident_id is None and not occurrence_dates:
        # Only a standalone draft needs this refused here — an incident-sourced
        # draft falls back to the incident's own occurred_at in
        # discipline_skill._resolve_occurrence_dates, so it's never empty once
        # the incident resolves. Without a date here, check_discipline_compliance
        # has nothing to test against protected leave, so the statutory block
        # could silently never fire.
        return HuumeVerdict(
            kind="refuse",
            message="On which date(s) did this happen? Give me specific dates so the record is accurate.",
        )

    expected_improvement = str(staged.get("expected_improvement") or "").strip() or None

    if incident_id is None:
        # Standalone draft only — see the docstring for why an incident-sourced
        # one is exempt. Gate text is the narrative fields only, never the
        # infraction_type label.
        gate_text = " ".join([description, str(expected_improvement or "")])
        from app.matcha.services.pilots.hr_pilot_escalation import classify_message
        gate = classify_message(gate_text)
        if gate.hard_stop:
            return HuumeVerdict(
                kind="refuse",
                message=gate.notice or "This needs to go to corporate HR rather than being filed here.",
            )

    return HuumeVerdict(kind="proceed", message="", action={
        "type": "discipline_from_incident",
        "employee_id": str(employee_id),
        "incident_id": str(incident_id) if incident_id else None,
        "infraction_type": infraction_type,
        "severity": severity if severity in _DISCIPLINE_SEVERITIES else None,
        "discipline_type": discipline_type if discipline_type in _DISCIPLINE_TYPES else None,
        "occurrence_dates": occurrence_dates,
        "description": description,
        "expected_improvement": expected_improvement,
        "template_id": str(template_id) if template_id else None,
        "confirm_id": staged.get("confirm_id"),
    })


def _validate_discipline_decision(staged: dict[str, Any]) -> HuumeVerdict:
    """Confirm-turn validation for approving/denying/revising a pending
    discipline record. 'deny' and 'revise' both require a reason of at
    least _MIN_DENIAL_REASON_CHARS — mirrors DenyRequest in
    routes/employee_lifecycle/discipline.py (disposition='reject'/'revise'
    both carry the same `reason` field, same floor)."""
    record_id = staged.get("record_id")
    if not _is_uuid(record_id):
        return HuumeVerdict(
            kind="refuse",
            message="I need the discipline record's id — look it up with list_pending_approvals first.",
        )
    decision = str(staged.get("decision") or "").strip().lower()
    if decision not in ("approve", "deny", "revise"):
        return HuumeVerdict(kind="refuse", message="Tell me whether to approve, deny, or send it back for revision.")

    reason = str(staged.get("reason") or "").strip()
    if decision in ("deny", "revise") and len(reason) < _MIN_DENIAL_REASON_CHARS:
        verb = "denial" if decision == "deny" else "revision request"
        return HuumeVerdict(
            kind="refuse",
            message=f"A {verb} needs a written reason of at least {_MIN_DENIAL_REASON_CHARS} characters — ask the admin why.",
        )

    return HuumeVerdict(kind="proceed", message="", action={
        "type": "discipline_decision",
        "record_id": str(record_id),
        "decision": decision,
        "reason": reason or None,
    })


def evaluate_plan_execution(
    *,
    role: Optional[str] = None,
    capabilities: Optional[set[WorkCapability] | frozenset[WorkCapability]] = None,
    features: dict[str, Any],
) -> Optional[str]:
    """Pure. None if the caller may execute plan steps at all (independent of
    which plan/offer), else a refusal reason. Re-asserted on the chat tool
    path (`agent.py`'s execute_approved_steps handler) since the skill engine
    gates nothing itself — the REST route already has this via
    `require_admin_or_client`, so this mirrors that check for parity."""
    features = features or {}
    if WorkCapability.ACTION_EXECUTE not in _effective_capabilities(
        role=role, capabilities=capabilities
    ):
        return "Only a business admin or authorized Work Operator can run onboarding plan steps."
    if not features.get("huume"):
        return "Huume isn't enabled for this company."
    if not features.get("matcha_work"):
        return "Matcha Work isn't enabled for this company."
    return None


# Pilot-backed chat tools (Legal Pilot / Handbook Pilot skills) and the company
# feature flag(s) each one requires beyond `huume` + `matcha_work`. Mirrors
# STEP_REQUIRED_FEATURE: the registry the pure envelope below reads from.
# Value is a str for a single flag, or a tuple when more than one must be on —
# ask_ir_copilot/run_incident_analysis need BOTH: `ir_copilot` gates the
# Copilot feature itself, but it's default-True and deliberately absent from
# FEATURE_REQUIRES (see root CLAUDE.md), so it says nothing about whether the
# company's `incidents` (the paid Lite gate) is still on — a cancelled Lite
# sub only stores incidents=False, not ir_copilot=False.
PILOT_TOOL_REQUIRED_FEATURE: dict[str, str | tuple[str, ...]] = {
    "list_legal_matters": "legal_defense",
    "open_legal_matter": "legal_defense",
    "ask_legal_pilot": "legal_defense",
    "generate_legal_packet": "legal_defense",
    "draft_handbook_content": "handbook_pilot",
    "promote_handbook_drafts": "handbook_pilot",
    "er_case_brief": "er_copilot",
    "ask_er_copilot": "er_copilot",
    "ask_ir_copilot": ("ir_copilot", "incidents"),
    "run_incident_analysis": ("ir_copilot", "incidents"),
    # Not pilot-backed, but the same per-call envelope is what was missing:
    # send_offer is gated on `offer_letters` via _HUUME_ACTION_REQUIRED_FEATURE
    # below, but draft_offer_letter/check_offer_status ran ungated — a
    # flag-off company could still draft (INSERT a real offer_letters row)
    # and open the side panel's OfferLetterViewer, which then 403s forever
    # against the /offer-letters mount's own require_feature("offer_letters").
    "draft_offer_letter": "offer_letters",
    "check_offer_status": "offer_letters",
}

_PILOT_FEATURE_LABEL = {
    "legal_defense": "Legal Pilot", "handbook_pilot": "Handbook Pilot", "er_copilot": "ER Copilot",
    "ir_copilot": "IR Copilot", "incidents": "Incident Reporting", "offer_letters": "Offer Letters",
}


def evaluate_pilot_tool(
    *,
    tool: str,
    role: Optional[str] = None,
    capabilities: Optional[set[WorkCapability] | frozenset[WorkCapability]] = None,
    features: dict[str, Any],
) -> Optional[str]:
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
    if WorkCapability.SENSITIVE_RECORD_READ not in _effective_capabilities(
        role=role, capabilities=capabilities
    ):
        return "Only a business admin or authorized Work Reviewer can use this sensitive Huume tool."
    if not features.get("huume"):
        return "Huume isn't enabled for this company."
    if not features.get("matcha_work"):
        return "Matcha Work isn't enabled for this company."
    required_flags = (required,) if isinstance(required, str) else required
    for flag in required_flags:
        if not features.get(flag):
            label = _PILOT_FEATURE_LABEL.get(flag, flag)
            return f"{label} ('{flag}') isn't enabled for this company."
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
    actor_role: Optional[str] = None,
    week_start: Optional[date] = None,
    week_end: Optional[date] = None,
) -> dict[str, Any]:
    """Execute a validated staged huume_action. Assumes evaluate_huume_action
    returned kind=='proceed'.

    `thread_id`/`session_id`/`exclude_ids` are needed only by `amend_handbook`
    — turn-scoped context (which handbook-pilot session, which drafts THIS
    turn just proposed) that has no natural home on the persisted staged
    action dict, unlike every other action type here.

    Every branch falls through to the tail below, which registers the result
    in the asset registry (`assets.record_asset` — no-ops on anything that
    isn't a real `status="created"` row, never raises) before returning."""
    from app.matcha.services.huume import assets as huume_assets
    from app.matcha.services.huume import onboarding_skill

    if action.get("type") == "amend_handbook":
        from app.matcha.services.huume import handbook_skill
        result = await handbook_skill.promote(
            company_id=company_id, actor_user_id=actor_user_id, thread_id=thread_id,
            session_id=session_id, draft_ids=action.get("draft_ids"),
            exclude_ids=exclude_ids or set(),
            handbook_title=action.get("handbook_title"),
            target_handbook_id=action["target_handbook_id"],
        )
    elif action.get("type") == "send_offer":
        result = await onboarding_skill.execute_send_offer(
            company_id=company_id, actor_user_id=actor_user_id, offer_id=action["offer_id"],
            recipient_email=action.get("recipient_email"),
        )
    elif action.get("type") == "discipline_draft":
        # Delegates to the SAME executor HR Pilot uses — employee resolution,
        # the deterministic discipline_compliance gate (a statutory block
        # refuses, no override), and the status='draft' write. Its
        # "clarify"/"blocked"/"escalate" statuses all read as a plain refusal
        # to this caller; the message still explains why.
        from app.matcha.services.pilots.hr_pilot_actions import execute_hr_action
        result = await execute_hr_action(company_id=company_id, actor_user_id=actor_user_id, action=action)
    elif action.get("type") in _HR_OPS_ACTIONS:
        # Huume-own executors rather than hr_pilot_actions'. HR Pilot's
        # ir_report/er_case are hard-stop HAND-OFFS: they hardcode
        # occurred_at=now, category="harassment" and source="hr_pilot", which
        # is the wrong provenance and the wrong field set for an admin filing
        # a report deliberately. Same underlying *_core writers, though.
        from app.matcha.services.huume import hr_ops_skill
        result = await hr_ops_skill.execute(
            company_id=company_id, actor_user_id=actor_user_id, action=action,
        )
    elif action.get("type") in _DISCIPLINE_SKILL_ACTIONS:
        from app.matcha.services.huume import discipline_skill
        result = await discipline_skill.execute(
            company_id=company_id, actor_user_id=actor_user_id, action=action,
        )
    elif action.get("type") == "ems_promote":
        from app.matcha.services.huume import ems_skill
        result = await ems_skill.execute_promote(
            company_id=company_id, actor_user_id=actor_user_id, action=action,
        )
    elif action.get("type") in _INVENTORY_ACTIONS:
        from app.matcha.services.huume import inventory_skill
        result = await inventory_skill.execute(
            company_id=company_id, actor_user_id=actor_user_id, action=action,
        )
    elif action.get("type") == "schedule_change":
        from app.matcha.services.huume import schedule_skill
        result = await schedule_skill.execute(
            company_id=company_id, actor_user_id=actor_user_id, action=action,
            week_start=week_start, week_end=week_end,
        )
    elif action.get("type") == "schedule_week_draft":
        from app.matcha.services.scheduling.week_builder import apply_week_draft
        result = await apply_week_draft(
            company_id=company_id,
            actor_user_id=actor_user_id,
            generation_run_id=UUID(str(action["generation_run_id"])),
            location_id=UUID(str(action["location_id"])),
            week_start=date.fromisoformat(str(action["week_start"])),
        )
    elif action.get("type") in {"schedule_note", "meal_break_waiver", "work_permit"}:
        from app.matcha.services.scheduling import schedule_assistant_actions
        if action["type"] == "schedule_note":
            result = await schedule_assistant_actions.update_assignment_note_core(
                company_id=company_id, actor_user_id=actor_user_id,
                location_id=UUID(action["location_id"]), shift_id=UUID(action["shift_id"]),
                employee_id=UUID(action["employee_id"]), note=action.get("note"),
                visible_to_employee=bool(action.get("visible_to_employee", True)),
                include_in_location_digest=bool(action.get("include_in_location_digest", True)),
                send_employee_notice=bool(action.get("send_employee_notice", True)),
                week_start=week_start, week_end=week_end,
            )
        elif action["type"] == "meal_break_waiver":
            result = await schedule_assistant_actions.record_meal_break_waiver_core(
                company_id=company_id, actor_user_id=actor_user_id,
                location_id=UUID(action["location_id"]), employee_id=UUID(action["employee_id"]),
                on_file=bool(action["on_file"]),
                effective_from=date.fromisoformat(action["effective_from"]), note=action.get("note"),
            )
        else:
            result = await schedule_assistant_actions.record_work_permit_core(
                company_id=company_id, actor_user_id=actor_user_id,
                employee_id=UUID(action["employee_id"]), location_id=UUID(action["location_id"]),
                issued_at=date.fromisoformat(action["issued_at"]) if action.get("issued_at") else None,
                expires_at=date.fromisoformat(action["expires_at"]),
            )
    elif action.get("type") == "eligibility_case_decision":
        from app.matcha.services.scheduling.schedule_assistant_actions import decide_eligibility_case_core
        result = await decide_eligibility_case_core(
            company_id=company_id,
            actor_user_id=actor_user_id,
            actor_role=actor_role or "",
            case_id=UUID(action["case_id"]),
            location_id=UUID(action["location_id"]),
            decision=action["decision"],
            acknowledgement_confirmed=bool(action.get("acknowledgement_confirmed")),
            acknowledgement_note=action.get("acknowledgement_note"),
        )
    else:
        result = {"status": "error", "message": "Unsupported action."}

    await huume_assets.record_asset(
        company_id=company_id, thread_id=thread_id, actor_user_id=actor_user_id,
        action=action, result=result,
    )
    return result


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
