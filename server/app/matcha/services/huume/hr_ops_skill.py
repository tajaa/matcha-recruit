"""Huume's HR-ops executors — incident reports, ER cases, training
assignments, PTO decisions.

Every function here assumes `actions.evaluate_huume_action` already returned
`kind == "proceed"`: the role/flag/two-turn envelope and all field validation
happened there, purely. This module only does the DB work, mirroring
`hr_pilot_actions`' executor half (same `{status, message, record_id?,
record_label?, bg_tasks?}` return shape, so `agent.py` relays them uniformly).

Why these don't reuse `hr_pilot_actions._execute_ir_report` / `_execute_er_case`:
those are hard-stop HAND-OFFS. They hardcode `occurred_at=now`,
`category="harassment"` and `source="hr_pilot"` because the supervisor never
chose any of it — the classifier did. An admin filing a report deliberately
supplies their own occurrence time, type, severity and category, so the
provenance and the field set both differ. The underlying writers are the same
shared `*_core` functions (`create_incident_core`, `create_case_core`), which
is where the real invariants live.

`bg_tasks` are `(fn, args, kwargs)` tuples the CALLER schedules after the
transaction commits — never awaited here.
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from app.matcha.services.employees.pto_decisions import decide_pto_request_core
from app.matcha.services.er.er_case_create import create_case_core
from app.matcha.services.ir.ir_incident_create import create_incident_core

logger = logging.getLogger(__name__)

# An ER case title derived from the narrative — the admin can rename it on the
# ER page. Mirrors hr_pilot_actions._derive_er_title minus its "HR Pilot
# report:" prefix, which would be wrong provenance here.
_ER_TITLE_MAX = 80


async def execute(*, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a validated staged HR-ops action to its executor."""
    atype = action.get("type")
    if atype == "ir_report":
        return await _execute_ir_report(company_id, actor_user_id, action)
    if atype == "er_case":
        return await _execute_er_case(company_id, actor_user_id, action)
    if atype == "training_assign":
        return await _execute_training_assign(company_id, actor_user_id, action)
    if atype == "pto_decision":
        return await _execute_pto_decision(company_id, actor_user_id, action)
    return {"status": "error", "message": "Unsupported action."}


def _derive_er_title(narrative: str) -> str:
    """First line of the narrative, truncated, as an ER case title. Pure."""
    text = (narrative or "").strip()
    first = text.splitlines()[0].strip() if text else ""
    if len(first) > _ER_TITLE_MAX:
        first = first[: _ER_TITLE_MAX - 3].rstrip() + "..."
    return first or "Employee relations case"


async def _execute_ir_report(company_id, actor_user_id, action) -> dict[str, Any]:
    from datetime import datetime, timezone

    from app.database import get_connection
    from app.matcha.services.huume.actions import _parse_iso_datetime
    from app.matcha.services.pilots.hr_pilot_actions import _actor_identity

    occurred_at = _parse_iso_datetime(action.get("occurred_at")) or datetime.now(timezone.utc)

    async with get_connection() as conn:
        async with conn.transaction():
            reporter_name, reporter_email = await _actor_identity(conn, actor_user_id)
            row, bg_tasks = await create_incident_core(
                conn,
                company_id=str(company_id),
                description=action["description"],
                occurred_at=occurred_at,
                reported_by_name=reporter_name,
                reported_by_email=reporter_email,
                # Absent keys stay absent: create_incident_core tracks whether
                # the caller passed type/severity explicitly and lets the
                # background classifier fill only what it didn't.
                **{k: action[k] for k in ("incident_type", "severity") if action.get(k)},
                location=action.get("location"),
                created_by=str(actor_user_id) if actor_user_id else None,
                actor_user_id=str(actor_user_id) if actor_user_id else None,
                actor_email=reporter_email,
            )

    label = row.get("incident_number") or row.get("title") or "the incident"
    return {
        "status": "created",
        "message": (
            f"Filed incident {label}. It's in Incidents now — the classifier will "
            "fill in type/severity if they weren't set, and the record stays editable there."
        ),
        "record_id": str(row.get("id")),
        "record_label": str(label),
        "bg_tasks": list(bg_tasks or []),
    }


async def _execute_er_case(company_id, actor_user_id, action) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.models.er.case import ERCaseCreate

    description = action["description"]
    case = ERCaseCreate(
        title=(action.get("title") or _derive_er_title(description))[:255],
        description=description,
        category=action.get("category"),
        intake_context={"source": "huume"},
        involved_employees=[],  # never inferred from free text
    )
    async with get_connection() as conn:
        async with conn.transaction():
            row, bg_callables = await create_case_core(
                conn,
                company_id=company_id,
                created_by=str(actor_user_id) if actor_user_id else None,
                case=case,
            )

    label = row.get("case_number") or "the case"
    return {
        "status": "created",
        "message": (
            f"Opened ER case {label}. Add the involved employees and any documents "
            "on the ER Copilot page — I don't infer those from the description."
        ),
        "record_id": str(row.get("id")),
        "record_label": str(label),
        "bg_tasks": list(bg_callables or []),
    }


async def _execute_training_assign(company_id, actor_user_id, action) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.services.huume.actions import _parse_iso_date
    from app.matcha.services.scheduling.schedule_rules import INACTIVE_EMPLOYMENT_STATUSES
    from app.matcha.services.training.training_assignment import assign_training

    requirement_id = UUID(action["requirement_id"])
    employee_ids = [UUID(e) for e in action["employee_ids"]]
    due_date = _parse_iso_date(action.get("due_date"))

    async with get_connection() as conn:
        requirement = await conn.fetchrow(
            """SELECT id, title, training_type, frequency_months
               FROM training_requirements
               WHERE id = $1 AND company_id = $2 AND is_active = true""",
            requirement_id, company_id,
        )
        if not requirement:
            return {"status": "error",
                    "message": "I couldn't find that training requirement — look it up again with lookup_context(topic='training')."}

        # Tenant + employability scoping. Assigning training to someone who has
        # left is noise on a compliance report, and an id from another tenant
        # must never resolve.
        rows = await conn.fetch(
            """SELECT id, first_name, last_name FROM employees
               WHERE id = ANY($1::uuid[]) AND org_id = $2
                 AND (employment_status IS NULL OR employment_status <> ALL($3::text[]))""",
            employee_ids, company_id, list(INACTIVE_EMPLOYMENT_STATUSES),
        )
        valid_ids = [r["id"] for r in rows]
        if not valid_ids:
            return {"status": "error",
                    "message": "None of those employee ids match an active employee here — look them up again with lookup_context(topic='roster')."}
        dropped = len(employee_ids) - len(valid_ids)

        async with conn.transaction():
            result = await assign_training(
                conn, company_id, dict(requirement), valid_ids,
                # `source_type` is a closed vocabulary (VALID_SOURCE_TYPES);
                # an admin asking in chat is a manual assignment, and the note
                # is what makes the provenance legible on the record.
                source_type="manual",
                source_note="Assigned via Huume chat",
                due_date=due_date,
                assigned_by=actor_user_id,
            )

    counts = result.as_dict()
    parts = [f"{counts['assigned_count']} assigned"]
    if counts["accelerated_count"]:
        parts.append(f"{counts['accelerated_count']} pulled earlier (already open)")
    if counts["already_open_count"]:
        parts.append(f"{counts['already_open_count']} already open, unchanged")
    if dropped:
        parts.append(f"{dropped} skipped (not an active employee here)")
    return {
        "status": "created",
        "message": f"{requirement['title']}: " + ", ".join(parts) + ".",
        "record_id": str(requirement_id),
        "record_label": str(requirement["title"]),
        "bg_tasks": [],
    }


async def _execute_pto_decision(company_id, actor_user_id, action) -> dict[str, Any]:
    from app.database import get_connection

    request_id = UUID(action["request_id"])
    async with get_connection() as conn:
        async with conn.transaction():
            result = await decide_pto_request_core(
                conn,
                company_id=company_id,
                request_id=request_id,
                decision=action["decision"],
                actor_user_id=actor_user_id,
                note=action.get("note"),
            )

    if result["status"] != "ok":
        # not_found / invalid_status / reason_required all read as a plain
        # refusal to the model; the core's message already says which.
        return {"status": "error", "message": result["message"]}
    return {
        "status": "created",
        "message": result["message"] + ".",
        "record_id": str(request_id),
        "record_label": result["decision"],
        "bg_tasks": [],
    }
