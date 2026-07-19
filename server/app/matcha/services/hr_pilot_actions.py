"""HR Pilot actions — the bounded, confirm-first "acting" layer on top of the
HR Pilot thread mode.

HR Pilot's default is to *answer* a supervisor's question, grounded in company
material. This module lets it *act* on a narrow, gated set of documented HR
tasks. The design mirrors the codebase's standing invariant for AI-touched
legal records ("AI proposes, a human confirms"): an action is staged into
thread state on one turn, and only an explicit confirmation on a *later* turn
executes it.

Two families of action:
- **Model-proposed** (`discipline_draft`, `pto_request`): the model stages the
  proposal from a supervisor's request. Discipline lands a `status='draft'`
  record (issuance/signatures stay in the discipline product); PTO lands a
  `status='pending'` request (admin approves via the existing PATCH).
- **Server-staged hand-offs** (`ir_report`, `er_case`): staged ONLY by the
  hard-stop block in messaging.py when a supervisor's message trips the safety
  or harassment gate — turning a dead-end "call HR" into a confirm-first filing
  into the real IR / ER case systems, prefilled from the supervisor's own words.

The split mirrors `discipline_compliance` / `schedule_rules`: a **pure, DB-free**
verdict function (`evaluate_hr_action`) plus pure helpers carry every check that
does not need the database, so the whole safety envelope is unit-testable
against plain dicts; thin async **executors** do the DB work.

The safety envelope is load-bearing: the matcha-work skill engine does NOT
feature- or role-gate execution (see routes/matcha_work/ai_turn.py), so every
guard a normal record write would get must be re-asserted here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID

from app.matcha.services.hr_pilot_escalation import classify_message

logger = logging.getLogger(__name__)

# Every action HR Pilot can file. Adding one means: an entry here + in
# _ACTION_REQUIRED_FEATURE, a validation branch in evaluate_hr_action, and an
# executor branch. Model-proposed actions must ALSO be in MODEL_STAGEABLE_HR_ACTIONS.
SUPPORTED_HR_ACTIONS = {"discipline_draft", "pto_request", "ir_report", "er_case"}

# Each action re-checks the tenant's own subsystem flag on top of `hr_pilot`.
_ACTION_REQUIRED_FEATURE = {
    "discipline_draft": "discipline",
    "pto_request": "time_off",
    "ir_report": "incidents",
    "er_case": "er_copilot",
}

# Only these are stageable by the MODEL (via `updates`). The hand-off types are
# staged ONLY by the server's hard-stop block — a model emitting one is dropped
# (filter_model_staged_hr_action), so it can neither mint a hand-off nor
# overwrite the narrative the server captured from the supervisor.
MODEL_STAGEABLE_HR_ACTIONS = {"discipline_draft", "pto_request"}
_HANDOFF_ACTIONS = {"ir_report", "er_case"}

# Hard-stop category → (hand-off action, required feature). Only safety and
# harassment have a clean structured destination; leave/medical and
# termination/legal stay notice-only (genuinely human-HR territory).
_HARD_STOP_HANDOFF = {
    "workplace_safety": ("ir_report", "incidents"),
    "harassment_discrimination": ("er_case", "er_copilot"),
}

# Only business admins / platform admins may execute. Employees/creators/etc.
# reaching a thread must never trigger a record write.
_ALLOWED_ROLES = {"client", "admin"}

# HR Pilot deliberately handles only the low-sensitivity, first-line infractions
# a supervisor documents day to day. Safety / harassment / gross_misconduct are
# hard-stop-adjacent — those route to corporate HR, never an AI-drafted write-up.
_HR_PILOT_INFRACTION_TYPES = ("attendance", "performance", "policy_violation")
_HR_PILOT_SEVERITIES = ("minor", "moderate", "severe")

# PTO-on-behalf covers only non-medical time off; sick/medical routes to HR/portal.
_PTO_ALLOWED_TYPES = ("vacation", "personal")

# A supervisor is describing a handful of dated occurrences, not a data feed.
_MAX_OCCURRENCE_DATES = 30
# One request shouldn't exceed this many hours — a sanity cap, not a policy.
_MAX_PTO_HOURS = 2000


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


# ---------------------------------------------------------------------------
# Pure helpers (DB-free, unit-testable)
# ---------------------------------------------------------------------------

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


def filter_model_staged_hr_action(updates: dict) -> dict:
    """Drop a model-emitted `hr_action` whose type isn't model-stageable.

    The hand-off types (ir_report/er_case) are staged only by the server's
    hard-stop block; a model that emits one — to mint a hand-off, or to
    overwrite the server-captured narrative on the confirm turn — is silently
    dropped. Everything else passes through. Pure."""
    if not isinstance(updates, dict):
        return updates
    action = updates.get("hr_action")
    if isinstance(action, dict):
        atype = str(action.get("type") or "").strip()
        if atype and atype not in MODEL_STAGEABLE_HR_ACTIONS:
            filtered = dict(updates)
            filtered.pop("hr_action", None)
            return filtered
    return updates


def should_stage_handoff(
    existing_hr_action: Any, category: Optional[str], features: dict[str, Any]
) -> Optional[str]:
    """Decide whether a hard-stop should stage a warm hand-off. Returns the
    hand-off action type (ir_report/er_case) or None. Pure.

    None when: the category has no structured destination; the required feature
    is off; or a hand-off is ALREADY staged (status 'proposed') — re-staging
    would overwrite the supervisor's original narrative with their confirm
    message. A staged *discipline* draft does NOT suppress a hand-off (safety
    outranks a pending write-up)."""
    mapping = _HARD_STOP_HANDOFF.get(category or "")
    if not mapping:
        return None
    handoff_type, required_feature = mapping
    if not (features or {}).get(required_feature):
        return None
    if (isinstance(existing_hr_action, dict)
            and existing_hr_action.get("type") in _HANDOFF_ACTIONS
            and existing_hr_action.get("status") == "proposed"):
        return None
    return handoff_type


def _validate_discipline_fields(staged: dict) -> tuple[Optional[dict], Optional[str]]:
    """Validate + normalize a discipline_draft proposal. Returns
    (normalized, None) when valid, else (None, clarify_message). Does NOT run
    the hard-stop re-check (a distinct verdict) — the caller does. Pure."""
    employee_name = str(staged.get("employee_name") or "").strip()
    if not employee_name:
        return None, "Which employee is this write-up for?"

    infraction_type = str(staged.get("infraction_type") or "").strip().lower()
    if infraction_type not in _HR_PILOT_INFRACTION_TYPES:
        return None, (
            "I can only draft write-ups for attendance, performance, or policy "
            "violations here. Anything involving safety, harassment, or misconduct "
            "needs to go to corporate HR."
        )

    severity = str(staged.get("severity") or "moderate").strip().lower()
    if severity not in _HR_PILOT_SEVERITIES:
        return None, "How severe is this — minor, moderate, or severe?"

    occ_dates, invalid = _parse_iso_dates(staged.get("occurrence_dates"))
    if invalid or not occ_dates:
        return None, "On which date(s) did this happen? Give me specific dates so the record is accurate."
    if len(occ_dates) > _MAX_OCCURRENCE_DATES:
        return None, "That's a lot of dates for one write-up — narrow it to the specific occurrences at issue."

    description = str(staged.get("description") or "").strip()
    if not description:
        return None, "Briefly, what happened? I need a description for the record."

    normalized = {
        "type": "discipline_draft",
        "employee_name": employee_name,
        "infraction_type": infraction_type,
        "severity": severity,
        "occurrence_dates": [d.isoformat() for d in occ_dates],
        "description": description,
        "expected_improvement": str(staged.get("expected_improvement") or "").strip() or None,
    }
    return normalized, None


def _validate_pto_fields(staged: dict) -> tuple[Optional[dict], Optional[str]]:
    """Validate + normalize a pto_request proposal. Returns (normalized, None)
    or (None, clarify_message). The past-date check is deferred to the executor
    (it depends on today()); everything here is time-independent. Pure."""
    employee_name = str(staged.get("employee_name") or "").strip()
    if not employee_name:
        return None, "Which employee is this time-off request for?"

    request_type = str(staged.get("request_type") or "vacation").strip().lower()
    if request_type not in _PTO_ALLOWED_TYPES:
        return None, (
            "I can only file vacation or personal time off here. Sick or medical "
            "leave has to go through corporate HR or the employee's own portal."
        )

    start_dates, s_invalid = _parse_iso_dates([staged.get("start_date")])
    end_dates, e_invalid = _parse_iso_dates([staged.get("end_date")])
    if s_invalid or e_invalid or not start_dates or not end_dates:
        return None, "What are the start and end dates? Give me specific dates (YYYY-MM-DD)."
    start_date, end_date = start_dates[0], end_dates[0]
    if start_date > end_date:
        return None, "The start date needs to be on or before the end date."

    try:
        hours = float(staged.get("hours"))
    except (TypeError, ValueError):
        return None, "How many hours of PTO is this? I need the hours for the record."
    if hours <= 0 or hours > _MAX_PTO_HOURS:
        return None, "How many hours of PTO is this? Give me a positive number of hours."

    normalized = {
        "type": "pto_request",
        "employee_name": employee_name,
        "request_type": request_type,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hours": hours,
        "reason": str(staged.get("reason") or "").strip() or None,
    }
    return normalized, None


def _slim_compliance_snapshot(verdict: dict) -> dict:
    """JSON-safe, reduced compliance verdict for storage in thread state / the
    discipline record. The raw verdict's blocks/advisories carry `date` objects
    and a full state_row; `apply_update` json.dumps's with no default, so every
    value here must be stringify-safe. Pure."""
    def _slim(items):
        out = []
        for it in items or []:
            row = {"code": str(it.get("code") or ""), "detail": str(it.get("detail") or "")}
            if it.get("statute"):
                row["statute"] = str(it["statute"])
            if it.get("state"):
                row["state"] = str(it["state"])
            out.append(row)
        return out
    return {
        "version": verdict.get("version"),
        "checked_at": str(verdict.get("checked_at") or ""),
        "work_state": verdict.get("work_state"),
        "blocks": _slim(verdict.get("blocks")),
        "advisories": _slim(verdict.get("advisories")),
    }


def _derive_er_title(narrative: str) -> str:
    """First line of the narrative, truncated, as an ER case title. Pure."""
    text = (narrative or "").strip()
    first = text.splitlines()[0].strip() if text else ""
    if len(first) > 80:
        first = first[:77].rstrip() + "..."
    return f"HR Pilot report: {first}" if first else "HR Pilot report"


# ---------------------------------------------------------------------------
# The pure safety envelope
# ---------------------------------------------------------------------------

def evaluate_hr_action(
    *,
    staged_action: Any,
    features: dict[str, Any],
    role: Optional[str],
    thread_hr_pilot_mode: bool,
    this_turn_has_new_action: bool,
) -> HrActionVerdict:
    """Pure, DB-free safety envelope for executing a staged HR action.

    Order: confirm-first (two-turn) → is there something to confirm → authz
    (thread mode, features, role) → per-type field validation → content safety
    (hard-stop re-check, discipline/PTO only). Employee resolution and the
    deterministic compliance gate are DB-bound and run in the executor.
    """
    features = features or {}

    # --- Confirm-first: only a proposal staged on a PRIOR turn is executable.
    # `this_turn_has_new_action` is computed from the update that actually
    # survived Phase A staging (post model-strip), so a model that restates a
    # (dropped) hand-off can't trap the user in a confirm loop.
    if this_turn_has_new_action:
        return HrActionVerdict(
            kind="stage",
            message=(
                "I've drafted this for your review above. Read it over and reply "
                "\"confirm\" (or tell me what to change) and I'll file it."
            ),
        )
    if not isinstance(staged_action, dict):
        return HrActionVerdict(
            kind="refuse",
            message="There's nothing staged to confirm yet. Tell me what you'd like to document.",
        )

    status = staged_action.get("status")
    if status == "blocked":
        return HrActionVerdict(
            kind="refuse",
            message=(
                staged_action.get("blocked_reason")
                or "I can't file this — it was blocked by a compliance check. This needs to go to corporate HR."
            ),
        )
    if status != "proposed":
        return HrActionVerdict(
            kind="refuse",
            message="That action isn't awaiting confirmation (it may already be filed).",
        )

    action_type = str(staged_action.get("type") or "").strip()
    if action_type not in SUPPORTED_HR_ACTIONS:
        return HrActionVerdict(kind="refuse", message="That action type isn't something I can file.")

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
        return HrActionVerdict(kind="refuse", message="Only a business admin can file this action.")

    # --- Per-type validation.
    if action_type == "discipline_draft":
        normalized, clarify_msg = _validate_discipline_fields(staged_action)
        if clarify_msg:
            return HrActionVerdict(kind="clarify", message=clarify_msg)
        return _apply_hard_stop_recheck(
            normalized,
            " ".join([normalized["employee_name"], normalized["infraction_type"],
                      normalized["description"], str(normalized.get("expected_improvement") or "")]),
        )

    if action_type == "pto_request":
        normalized, clarify_msg = _validate_pto_fields(staged_action)
        if clarify_msg:
            return HrActionVerdict(kind="clarify", message=clarify_msg)
        # Hard-stop re-check stays ON — "she's out on FMLA" in the reason must refuse.
        return _apply_hard_stop_recheck(
            normalized,
            " ".join([normalized["employee_name"], str(normalized.get("reason") or "")]),
        )

    if action_type in _HANDOFF_ACTIONS:
        # Server-staged only. The narrative contains hard-stop words BY
        # CONSTRUCTION (that's why it was stopped) — the payload hard-stop
        # re-check is deliberately NOT run; this action IS the sanctioned
        # channel for that content. Belt-and-braces: require the server-set
        # source marker (filter_model_staged_hr_action already drops any
        # model-emitted hand-off before it can reach state).
        if staged_action.get("source") != "hard_stop_handoff":
            return HrActionVerdict(kind="refuse", message="That report can't be filed from here.")
        narrative = str(staged_action.get("narrative") or "").strip()
        if not narrative:
            return HrActionVerdict(kind="refuse", message="There's no report description to file.")
        normalized = {
            "type": action_type,
            "narrative": narrative,
            "category": str(staged_action.get("category") or "").strip(),
            "escalation_id": staged_action.get("escalation_id"),
            "thread_id": staged_action.get("thread_id"),
        }
        return HrActionVerdict(kind="proceed", message="", action=normalized)

    return HrActionVerdict(kind="refuse", message="That action type isn't something I can file.")


def _apply_hard_stop_recheck(normalized: dict, gate_text: str) -> HrActionVerdict:
    """Run the deterministic hard-stop gate on an action's own text; a category
    hit refuses + escalates, otherwise proceed. Pure."""
    gate = classify_message(gate_text)
    if gate.hard_stop:
        return HrActionVerdict(
            kind="hard_stop",
            message=gate.notice or "This needs to go to corporate HR rather than being filed here.",
            escalate=True,
            category=gate.category,
            matched_terms=gate.matched_terms,
        )
    return HrActionVerdict(kind="proceed", message="", action=normalized)


# ---------------------------------------------------------------------------
# DB-bound: propose-time pre-check + executors
# ---------------------------------------------------------------------------

async def _resolve_employee(conn, company_id: UUID, name: str) -> tuple[Optional[dict], list[dict]]:
    """Resolve a free-text name to a single active employee (org_id-scoped).
    Returns (match, candidates): match set only on an unambiguous single hit."""
    status_filter = "employment_status IS NULL OR employment_status NOT IN ('terminated','offboarded')"

    rows = await conn.fetch(
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


def _clarify_employee(name: str, candidates: list[dict]) -> dict:
    if candidates:
        names = ", ".join(_full_name(c) for c in candidates)
        return {"status": "clarify",
                "message": f"I found more than one active employee matching \"{name}\": {names}. Which one?"}
    return {"status": "clarify",
            "message": f"I couldn't find an active employee named \"{name}\". Check the name and try again."}


def _coerce_uuid(value: Any) -> Optional[UUID]:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


async def _actor_identity(conn, actor_user_id: Any) -> tuple[str, Optional[str]]:
    """Resolve the acting user's display name + email for record authorship.
    Falls back to a generic 'Site supervisor' rather than guessing."""
    uid = _coerce_uuid(actor_user_id)
    if uid is None:
        return "Site supervisor", None
    row = await conn.fetchrow(
        """SELECT u.email, c.name AS client_name
           FROM users u LEFT JOIN clients c ON c.user_id = u.id
           WHERE u.id = $1""",
        uid,
    )
    if not row:
        return "Site supervisor", None
    email = row["email"]
    name = (row["client_name"] or "").strip() or (email.split("@")[0] if email else "") or "Site supervisor"
    return name, email


async def _link_escalation(conn, escalation_id: Any, company_id: UUID,
                           record_type: str, record_id: Any) -> None:
    """Best-effort: stamp the created record onto the originating escalation row
    so an HR reviewer sees 'already filed as …' and doesn't double-file."""
    eid = _coerce_uuid(escalation_id)
    rid = _coerce_uuid(record_id)
    if eid is None or rid is None:
        return
    try:
        await conn.execute(
            """UPDATE mw_escalated_queries
               SET linked_record_type = $3, linked_record_id = $4, updated_at = NOW()
               WHERE id = $1 AND company_id = $2""",
            eid, company_id, record_type, rid,
        )
    except Exception:
        logger.warning("hr_pilot: failed to link escalation %s → %s", escalation_id, record_id, exc_info=True)


async def precheck_discipline_proposal(*, company_id: UUID, staged_action: Any) -> dict:
    """Propose-time compliance pre-check. Runs the deterministic discipline gate
    as soon as a discipline_draft is staged, so the supervisor sees a
    statute-cited block/advisory BEFORE confirming. Returns:
        {"outcome": "blocked"|"advisory"|"ok"|"skip", "message"?, "compliance"?}
    Skips silently when fields are incomplete or the employee is ambiguous — the
    execute-time gate still runs regardless."""
    from app.database import get_connection
    from app.matcha.services.discipline_compliance import check_discipline_compliance

    if not isinstance(staged_action, dict) or staged_action.get("type") != "discipline_draft":
        return {"outcome": "skip"}
    normalized, clarify_msg = _validate_discipline_fields(staged_action)
    if clarify_msg or not normalized:
        return {"outcome": "skip"}

    occ_dates = [date.fromisoformat(d) for d in normalized["occurrence_dates"]]
    try:
        async with get_connection() as conn:
            match, _candidates = await _resolve_employee(conn, company_id, normalized["employee_name"])
            if match is None:
                return {"outcome": "skip"}
            verdict = await check_discipline_compliance(
                conn, company_id=company_id, employee_id=match["id"],
                infraction_type=normalized["infraction_type"], occurrence_dates=occ_dates,
            )
    except Exception:
        logger.warning("hr_pilot precheck failed for company %s", company_id, exc_info=True)
        return {"outcome": "skip"}

    snapshot = _slim_compliance_snapshot(verdict)
    if verdict.get("blocks"):
        details = " ".join(b.get("detail", "") for b in verdict["blocks"]).strip()
        return {
            "outcome": "blocked",
            "message": f"Heads up — I can't file this write-up: {details} This needs to go to corporate HR.",
            "compliance": snapshot,
        }
    advisories = verdict.get("advisories") or []
    if advisories:
        adv = " ".join(a.get("detail", "") for a in advisories).strip()
        return {"outcome": "advisory", "message": f"Before you confirm: {adv}", "compliance": snapshot}
    return {"outcome": "ok", "compliance": snapshot}


async def execute_hr_action(
    *, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any]
) -> dict[str, Any]:
    """Execute a validated HR action. Assumes `evaluate_hr_action` returned
    kind=="proceed". Returns {status, message, record_id?, record_label?,
    bg_tasks?} where status ∈ {"created","clarify","blocked","escalate","error"}
    and bg_tasks is a list of (fn, args, kwargs) tuples the caller schedules
    after commit."""
    atype = action.get("type")
    if atype == "discipline_draft":
        return await _execute_discipline_draft(company_id, actor_user_id, action)
    if atype == "pto_request":
        return await _execute_pto_request(company_id, actor_user_id, action)
    if atype == "ir_report":
        return await _execute_ir_report(company_id, actor_user_id, action)
    if atype == "er_case":
        return await _execute_er_case(company_id, actor_user_id, action)
    return {"status": "error", "message": "Unsupported action."}


async def _execute_discipline_draft(company_id, actor_user_id, action) -> dict:
    from app.database import get_connection
    from app.matcha.services.discipline_compliance import check_discipline_compliance
    from app.matcha.services.discipline_engine import (
        recommend_next_discipline,
        issue_discipline_with_supersede,
    )

    name = action["employee_name"]
    infraction_type = action["infraction_type"]
    severity = action["severity"]
    occ_dates = [date.fromisoformat(d) for d in action["occurrence_dates"]]

    async with get_connection() as conn:
        match, candidates = await _resolve_employee(conn, company_id, name)
        if match is None:
            return _clarify_employee(name, candidates)
        employee_id = match["id"]

        # Deterministic legal gate — a block is a hard refusal with no override.
        verdict = await check_discipline_compliance(
            conn, company_id=company_id, employee_id=employee_id,
            infraction_type=infraction_type, occurrence_dates=occ_dates,
        )
        if verdict.get("blocks"):
            details = " ".join(b.get("detail", "") for b in verdict["blocks"]).strip()
            return {"status": "blocked",
                    "message": f"I can't file this — {details} This needs to go to corporate HR.",
                    "compliance": verdict}

        rec = await recommend_next_discipline(
            conn, employee_id=employee_id, company_id=company_id,
            infraction_type=infraction_type, severity=severity,
        )

    # A final warning already on file means the next step is a termination
    # review — a hard-stop topic that must not be AI-drafted. Route it to HR.
    if rec.get("termination_review"):
        return {"status": "escalate",
                "message": (
                    f"{_full_name(match)} already has a final warning on file, so the next step is a "
                    "termination review — that has to go to corporate HR, not a write-up drafted here."
                ),
                "compliance": verdict}

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

    return {"status": "created", "message": msg, "record_id": str(row["id"]),
            "compliance": verdict, "bg_tasks": []}


async def _execute_pto_request(company_id, actor_user_id, action) -> dict:
    from app.database import get_connection

    name = action["employee_name"]
    request_type = action["request_type"]
    start_date = date.fromisoformat(action["start_date"])
    end_date = date.fromisoformat(action["end_date"])
    hours = float(action["hours"])

    if start_date < date.today():
        return {"status": "clarify",
                "message": "That start date is in the past — give me current or future dates."}

    async with get_connection() as conn:
        match, candidates = await _resolve_employee(conn, company_id, name)
        if match is None:
            return _clarify_employee(name, candidates)
        employee_id = match["id"]

        # Mirror the portal's overlap guard (employee_portal.py:441-451).
        overlap = await conn.fetchval(
            """SELECT COUNT(*) FROM pto_requests
               WHERE employee_id = $1 AND status IN ('pending','approved')
               AND ((start_date <= $2 AND end_date >= $2) OR
                    (start_date <= $3 AND end_date >= $3) OR
                    (start_date >= $2 AND end_date <= $3))""",
            employee_id, start_date, end_date,
        )
        if overlap and overlap > 0:
            return {"status": "clarify",
                    "message": f"{_full_name(match)} already has PTO booked overlapping those dates. Adjust and try again."}

        row = await conn.fetchrow(
            """INSERT INTO pto_requests
               (employee_id, start_date, end_date, hours, reason, request_type, status)
               VALUES ($1, $2, $3, $4, $5, $6, 'pending') RETURNING id""",
            employee_id, start_date, end_date, hours, action.get("reason"), request_type,
        )

    return {"status": "created",
            "message": (
                f"Filed a pending {request_type} PTO request for {_full_name(match)} "
                f"({start_date.isoformat()} → {end_date.isoformat()}, {hours:g}h). "
                "It's pending approval in the PTO admin queue."
            ),
            "record_id": str(row["id"]), "bg_tasks": []}


async def _execute_ir_report(company_id, actor_user_id, action) -> dict:
    from datetime import datetime, timezone
    from app.database import get_connection
    from app.matcha.routes.ir_incidents import create_incident_core

    narrative = action["narrative"]
    escalation_id = action.get("escalation_id")

    async with get_connection() as conn:
        async with conn.transaction():
            reporter_name, reporter_email = await _actor_identity(conn, actor_user_id)
            row, bg_tasks = await create_incident_core(
                conn,
                company_id=str(company_id),
                description=narrative,
                occurred_at=datetime.now(timezone.utc),
                reported_by_name=reporter_name,
                reported_by_email=reporter_email,
                created_by=str(actor_user_id) if actor_user_id else None,
                actor_user_id=str(actor_user_id) if actor_user_id else None,
                actor_email=reporter_email,
            )
        await _link_escalation(conn, escalation_id, company_id, "ir_incident", row.get("id"))

    label = row.get("incident_number") or row.get("title") or "the incident"
    return {"status": "created",
            "message": (
                f"Filed this as a safety/incident report ({label}). Corporate HR and your incident "
                "process have it now — the record is editable in Incidents if details need adding."
            ),
            "record_id": str(row.get("id")), "record_label": str(label),
            "bg_tasks": list(bg_tasks or [])}


async def _execute_er_case(company_id, actor_user_id, action) -> dict:
    from app.database import get_connection
    from app.matcha.models.er_case import ERCaseCreate
    from app.matcha.routes.er_copilot import create_case_core

    narrative = action["narrative"]
    escalation_id = action.get("escalation_id")
    thread_id = action.get("thread_id")

    case = ERCaseCreate(
        title=_derive_er_title(narrative),
        description=narrative,
        category="harassment",
        intake_context={
            "source": "hr_pilot",
            "thread_id": str(thread_id) if thread_id else None,
            "escalation_id": str(escalation_id) if escalation_id else None,
        },
        involved_employees=[],  # never inferred from free text
    )
    async with get_connection() as conn:
        async with conn.transaction():
            row, bg_callables = await create_case_core(
                conn, company_id=company_id,
                created_by=str(actor_user_id) if actor_user_id else None,
                case=case,
            )
        await _link_escalation(conn, escalation_id, company_id, "er_case", row.get("id"))

    label = row.get("case_number") or "the case"
    return {"status": "created",
            "message": (
                f"Opened an ER case ({label}) for corporate HR to investigate. It's in the ER queue now."
            ),
            "record_id": str(row.get("id")), "record_label": str(label),
            "bg_tasks": list(bg_callables or [])}
