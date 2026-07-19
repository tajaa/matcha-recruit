"""HR Pilot actions — the bounded, confirm-first "acting" layer on top of the
HR Pilot thread mode.

HR Pilot's default is to *answer* a supervisor's question, grounded in company
material. This module lets it *act* on a narrow, gated set of documented HR
tasks — currently only drafting a progressive-discipline record. The design
mirrors the codebase's standing invariant for AI-touched legal records ("AI
proposes, a human confirms"): the model stages a proposed action into thread
state on one turn, and only an explicit confirmation on a *later* turn executes
it. Nothing here ever issues a final record — a discipline action lands as a
`status='draft'` row that a human still reviews and issues through the
discipline product with its own signature flow.

The split mirrors `discipline_compliance` / `schedule_rules`: a **pure,
DB-free** verdict function (`evaluate_hr_action`) carries every check that does
not need the database, so the whole safety envelope is unit-testable against
plain dicts; a thin async **executor** (`execute_hr_action`) does the DB work
(employee resolution, the deterministic compliance gate, the draft write).

The safety envelope is load-bearing: the matcha-work skill engine does NOT
feature- or role-gate execution (see routes/matcha_work/ai_turn.py), so every
guard a normal discipline write would get must be re-asserted here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID

from app.matcha.services.hr_pilot_escalation import classify_message

logger = logging.getLogger(__name__)

# The only action HR Pilot can take today. Adding one means: a new entry here +
# in _ACTION_REQUIRED_FEATURE, a validation/normalization branch in
# evaluate_hr_action, and an execute branch in execute_hr_action.
SUPPORTED_HR_ACTIONS = {"discipline_draft"}

# Each action re-checks the tenant's own subsystem flag on top of `hr_pilot`.
_ACTION_REQUIRED_FEATURE = {"discipline_draft": "discipline"}

# Only business admins / platform admins may execute. Employees/creators/etc.
# reaching a thread must never trigger a record write.
_ALLOWED_ROLES = {"client", "admin"}

# Employees who have left are never a valid discipline target (mirrors the
# schedule feature's INACTIVE_EMPLOYMENT_STATUSES; the vocabulary lives in
# employees/crud.py:VALID_EMPLOYMENT_STATUSES).
_INACTIVE_EMPLOYMENT_STATUSES = ("terminated", "offboarded")

# HR Pilot deliberately handles only the low-sensitivity, first-line infractions
# a supervisor documents day to day. Safety / harassment / gross_misconduct are
# hard-stop-adjacent (and the keyword gate already refuses most of that wording)
# — those route to corporate HR, never an AI-drafted write-up.
_HR_PILOT_INFRACTION_TYPES = ("attendance", "performance", "policy_violation")
_HR_PILOT_SEVERITIES = ("minor", "moderate", "severe")

# A supervisor is describing a handful of dated occurrences, not a data feed.
_MAX_OCCURRENCE_DATES = 30


@dataclass(frozen=True)
class HrActionVerdict:
    """Result of the pure safety envelope.

    kind: "proceed" — cleared for the executor (see `action`).
          "stage"   — staged this turn; tell the supervisor to confirm.
          "clarify" — need more/valid detail before proceeding.
          "refuse"  — a guard blocked it (authz, wrong thread, etc.).
          "hard_stop" — a sensitive topic; route to corporate HR + escalate.
    """
    kind: str
    message: str
    action: Optional[dict[str, Any]] = None
    escalate: bool = False
    category: Optional[str] = None
    matched_terms: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return self.kind == "proceed"


def _parse_iso_dates(raw: Any) -> tuple[list[date], list[str]]:
    """Strictly parse a list of ISO (YYYY-MM-DD) date strings. Returns
    (parsed, invalid_tokens). Anything not a clean ISO date is invalid — we
    never guess a date for a legal record."""
    parsed: list[date] = []
    invalid: list[str] = []
    if not isinstance(raw, list):
        return parsed, ["<not a list>"]
    for item in raw:
        if isinstance(item, date):
            parsed.append(item)
            continue
        token = str(item).strip()
        try:
            parsed.append(date.fromisoformat(token))
        except (ValueError, TypeError):
            invalid.append(token or "<empty>")
    return parsed, invalid


def evaluate_hr_action(
    *,
    staged_action: Any,
    features: dict[str, Any],
    role: Optional[str],
    thread_hr_pilot_mode: bool,
    this_turn_has_new_action: bool,
) -> HrActionVerdict:
    """Pure, DB-free safety envelope for executing a staged HR action.

    Order: is there something to confirm → confirm-first (two-turn) → authz
    (thread mode, features, role) → field validation → content safety
    (hard-stop). Employee resolution and the deterministic compliance gate are
    DB-bound and run in the executor.
    """
    features = features or {}

    # --- Confirm-first: only a proposal staged on a PRIOR turn is executable.
    if this_turn_has_new_action:
        # The proposal was staged into thread state this same turn (Phase A of
        # the dispatcher). Refuse execution now so a human sees it first.
        return HrActionVerdict(
            kind="stage",
            message=(
                "I've drafted this for your review above. Read it over and reply "
                "\"confirm\" (or tell me what to change) and I'll file it as a draft."
            ),
        )
    if not isinstance(staged_action, dict):
        return HrActionVerdict(
            kind="refuse",
            message="There's no drafted action to confirm yet. Tell me what you'd like to document.",
        )
    if staged_action.get("status") != "proposed":
        return HrActionVerdict(
            kind="refuse",
            message="That action isn't awaiting confirmation (it may already be filed).",
        )

    action_type = str(staged_action.get("type") or "").strip()
    if action_type not in SUPPORTED_HR_ACTIONS:
        return HrActionVerdict(
            kind="refuse",
            message="That action type isn't something I can file.",
        )

    # --- Authz (the engine gates none of this itself).
    if not thread_hr_pilot_mode:
        return HrActionVerdict(kind="refuse", message="HR Pilot actions are only available in an HR Pilot thread.")
    if not features.get("hr_pilot"):
        return HrActionVerdict(kind="refuse", message="HR Pilot isn't enabled for this company.")
    required_feature = _ACTION_REQUIRED_FEATURE.get(action_type)
    if required_feature and not features.get(required_feature):
        return HrActionVerdict(
            kind="refuse",
            message=f"This action needs the {required_feature} feature, which isn't enabled for this company.",
        )
    if (role or "").strip().lower() not in _ALLOWED_ROLES:
        return HrActionVerdict(
            kind="refuse",
            message="Only a business admin can file this action.",
        )

    # --- Field validation (discipline_draft). Model-emitted strings only —
    # unparseable input becomes a clarify, never a guessed value.
    if action_type == "discipline_draft":
        employee_name = str(staged_action.get("employee_name") or "").strip()
        if not employee_name:
            return HrActionVerdict(kind="clarify", message="Which employee is this write-up for?")

        infraction_type = str(staged_action.get("infraction_type") or "").strip().lower()
        if infraction_type not in _HR_PILOT_INFRACTION_TYPES:
            return HrActionVerdict(
                kind="clarify",
                message=(
                    "I can only draft write-ups for attendance, performance, or policy "
                    "violations here. Anything involving safety, harassment, or misconduct "
                    "needs to go to corporate HR."
                ),
            )

        severity = str(staged_action.get("severity") or "moderate").strip().lower()
        if severity not in _HR_PILOT_SEVERITIES:
            return HrActionVerdict(
                kind="clarify",
                message="How severe is this — minor, moderate, or severe?",
            )

        occ_dates, invalid = _parse_iso_dates(staged_action.get("occurrence_dates"))
        if invalid or not occ_dates:
            return HrActionVerdict(
                kind="clarify",
                message="On which date(s) did this happen? Give me specific dates so the record is accurate.",
            )
        if len(occ_dates) > _MAX_OCCURRENCE_DATES:
            return HrActionVerdict(
                kind="clarify",
                message="That's a lot of dates for one write-up — narrow it to the specific occurrences at issue.",
            )

        description = str(staged_action.get("description") or "").strip()
        if not description:
            return HrActionVerdict(kind="clarify", message="Briefly, what happened? I need a description for the record.")

        # --- Content safety: re-run the deterministic hard-stop gate on the
        # action's own text, so a sensitive topic can't be smuggled through an
        # action even if it cleared the message-level gate.
        gate_text = " ".join([employee_name, infraction_type, description,
                              str(staged_action.get("expected_improvement") or "")])
        verdict = classify_message(gate_text)
        if verdict.hard_stop:
            return HrActionVerdict(
                kind="hard_stop",
                message=verdict.notice or "This needs to go to corporate HR rather than being filed here.",
                escalate=True,
                category=verdict.category,
                matched_terms=verdict.matched_terms,
            )

        normalized = {
            "type": "discipline_draft",
            "employee_name": employee_name,
            "infraction_type": infraction_type,
            "severity": severity,
            "occurrence_dates": [d.isoformat() for d in occ_dates],
            "description": description,
            "expected_improvement": str(staged_action.get("expected_improvement") or "").strip() or None,
        }
        return HrActionVerdict(kind="proceed", message="", action=normalized)

    return HrActionVerdict(kind="refuse", message="That action type isn't something I can file.")


async def _resolve_employee(conn, company_id: UUID, name: str) -> tuple[Optional[dict], list[dict]]:
    """Resolve a free-text name to a single active employee (org_id-scoped).
    Returns (match, candidates): match set only on an unambiguous single hit;
    candidates populated when the caller should disambiguate."""
    status_filter = "employment_status IS NULL OR employment_status NOT IN ('terminated','offboarded')"

    exact = await conn.fetch(
        f"""
        SELECT id, first_name, last_name, employment_status
        FROM employees
        WHERE org_id = $1
          AND ({status_filter})
          AND lower(trim(coalesce(first_name,'') || ' ' || coalesce(last_name,''))) = lower(trim($2))
        ORDER BY first_name, last_name
        """,
        company_id, name,
    )
    rows = exact
    if not rows:
        rows = await conn.fetch(
            f"""
            SELECT id, first_name, last_name, employment_status
            FROM employees
            WHERE org_id = $1
              AND ({status_filter})
              AND (coalesce(first_name,'') || ' ' || coalesce(last_name,'')) ILIKE '%' || $2 || '%'
            ORDER BY first_name, last_name
            LIMIT 6
            """,
            company_id, name,
        )
    if len(rows) == 1:
        return dict(rows[0]), []
    return None, [dict(r) for r in rows]


def _full_name(row: dict) -> str:
    return f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip() or "this employee"


async def execute_hr_action(
    *,
    company_id: UUID,
    actor_user_id: Optional[UUID],
    action: dict[str, Any],
) -> dict[str, Any]:
    """Execute a validated HR action. Assumes `evaluate_hr_action` already
    returned kind=="proceed". Returns a result dict:
        {status, message, record_id?, compliance?}
    where status ∈ {"created","clarify","blocked","escalate","error"}.
    """
    # Lazy imports — keep the pure verdict layer importable without the
    # discipline/db machinery, and avoid import cycles.
    from app.database import get_connection
    from app.matcha.services.discipline_compliance import check_discipline_compliance
    from app.matcha.services.discipline_engine import (
        recommend_next_discipline,
        issue_discipline_with_supersede,
    )

    if action.get("type") != "discipline_draft":
        return {"status": "error", "message": "Unsupported action."}

    name = action["employee_name"]
    infraction_type = action["infraction_type"]
    severity = action["severity"]
    occ_dates = [date.fromisoformat(d) for d in action["occurrence_dates"]]

    async with get_connection() as conn:
        match, candidates = await _resolve_employee(conn, company_id, name)
        if match is None:
            if candidates:
                names = ", ".join(_full_name(c) for c in candidates)
                return {"status": "clarify",
                        "message": f"I found more than one active employee matching \"{name}\": {names}. Which one?"}
            return {"status": "clarify",
                    "message": f"I couldn't find an active employee named \"{name}\". Check the name and try again."}

        employee_id = match["id"]

        # Deterministic legal gate — a block is a hard refusal with no override.
        verdict = await check_discipline_compliance(
            conn,
            company_id=company_id,
            employee_id=employee_id,
            infraction_type=infraction_type,
            occurrence_dates=occ_dates,
        )
        if verdict.get("blocks"):
            details = " ".join(b.get("detail", "") for b in verdict["blocks"]).strip()
            return {
                "status": "blocked",
                "message": (
                    f"I can't file this — {details} This needs to go to corporate HR."
                ),
                "compliance": verdict,
            }

        rec = await recommend_next_discipline(
            conn,
            employee_id=employee_id,
            company_id=company_id,
            infraction_type=infraction_type,
            severity=severity,
        )

    # A final warning already on file means the next step is a termination
    # review — a hard-stop topic that must not be AI-drafted (see the discipline
    # ladder). Route it to HR instead.
    if rec.get("termination_review"):
        return {
            "status": "escalate",
            "message": (
                f"{_full_name(match)} already has a final warning on file, so the next step is a "
                "termination review — that has to go to corporate HR, not a write-up drafted here."
            ),
            "compliance": verdict,
        }

    discipline_type = rec.get("recommended_level") or "verbal_warning"

    row = await issue_discipline_with_supersede(
        actor_user_id=actor_user_id,
        company_id=company_id,
        employee_id=employee_id,
        infraction_type=infraction_type,
        severity=severity,
        discipline_type=discipline_type,
        issued_date=date.today(),
        description=action["description"],
        expected_improvement=action.get("expected_improvement"),
        occurrence_dates=occ_dates,
        situation_narrative=action.get("description"),
        compliance_check=verdict,
    )

    level_label = discipline_type.replace("_", " ")
    msg = (
        f"Filed a draft {level_label} for {_full_name(match)} ({infraction_type}). "
        "It's a draft — review and issue it from Discipline when you're ready."
    )
    advisories = verdict.get("advisories") or []
    if advisories:
        adv_text = " ".join(a.get("detail", "") for a in advisories).strip()
        msg += f"\n\nHeads up before you issue it: {adv_text}"

    return {
        "status": "created",
        "message": msg,
        "record_id": str(row["id"]),
        "compliance": verdict,
    }
