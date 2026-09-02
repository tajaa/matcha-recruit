"""Shared schedule writers used by both REST and Huume confirmation paths."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from app.database import get_connection

from .schedule_eligibility_authorization import (
    eligibility_case_decision_error,
    require_eligibility_case_access,
)
from .schedule_guidance import refresh_assignment_break_guidance_and_minimum
from .shift_writes import log_audit


async def update_assignment_note_core(
    *, company_id: UUID, actor_user_id: UUID, location_id: UUID,
    shift_id: UUID, employee_id: UUID, note: str | None,
    visible_to_employee: bool = True,
    include_in_location_digest: bool = True,
    send_employee_notice: bool = True,
    week_start: date | None = None,
    week_end: date | None = None,
) -> dict[str, Any]:
    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchrow(
                """
                SELECT a.manager_note, a.manager_note_visible_to_employee,
                       a.manager_note_include_in_location_digest,
                       a.manager_note_send_employee_notice, s.location_id,
                       s.starts_at
                FROM schedule_shift_assignments a
                JOIN schedule_shifts s ON s.id=a.shift_id
                WHERE a.shift_id=$1 AND a.employee_id=$2 AND s.company_id=$3
                FOR UPDATE
                """,
                shift_id, employee_id, company_id,
            )
            if not existing:
                return {"status": "refused", "message": "That employee is not assigned to this shift."}
            if existing["location_id"] != location_id:
                return {"status": "refused", "message": "That shift is outside this schedule workspace."}
            if week_start is not None:
                selected_week_end = week_end or (week_start + timedelta(days=6))
                if not week_start <= existing["starts_at"].date() <= selected_week_end:
                    return {"status": "refused", "message": "That shift is outside this schedule workspace."}
            after = {
                "note": note.strip() if note else None,
                "visible_to_employee": visible_to_employee,
                "include_in_location_digest": include_in_location_digest,
                "send_employee_notice": send_employee_notice,
            }
            await conn.execute(
                """
                UPDATE schedule_shift_assignments
                SET manager_note=$1, manager_note_visible_to_employee=$2,
                    manager_note_include_in_location_digest=$3,
                    manager_note_send_employee_notice=$4,
                    manager_note_updated_by=$5, manager_note_updated_at=NOW()
                WHERE shift_id=$6 AND employee_id=$7
                """,
                after["note"], visible_to_employee, include_in_location_digest,
                send_employee_notice, actor_user_id, shift_id, employee_id,
            )
            await log_audit(
                conn, company_id, "assignment", shift_id, actor_user_id,
                "assignment.note.update",
                {
                    "employee_id": str(employee_id),
                    "before": {
                        "note": existing["manager_note"],
                        "visible_to_employee": existing["manager_note_visible_to_employee"],
                        "include_in_location_digest": existing["manager_note_include_in_location_digest"],
                        "send_employee_notice": existing["manager_note_send_employee_notice"],
                    },
                    "after": after,
                },
            )
    return {"status": "created", "message": "The shift note was updated.", "record_id": str(shift_id)}


async def record_meal_break_waiver_core(
    *, company_id: UUID, actor_user_id: UUID, employee_id: UUID,
    location_id: UUID, on_file: bool, effective_from: date, note: str | None,
) -> dict[str, Any]:
    async with get_connection() as conn:
        async with conn.transaction():
            location = await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2", location_id, company_id,
            )
            employee = await conn.fetchrow(
                "SELECT work_location_id FROM employees WHERE id=$1 AND org_id=$2", employee_id, company_id,
            )
            if not employee or not location:
                return {"status": "refused", "message": "Employee or location not found."}
            if employee["work_location_id"] != location_id:
                assigned_here = await conn.fetchval(
                    """SELECT EXISTS(
                           SELECT 1 FROM schedule_shift_assignments a
                           JOIN schedule_shifts s ON s.id=a.shift_id
                           WHERE a.company_id=$1 AND a.employee_id=$2 AND s.location_id=$3
                             AND s.status <> 'cancelled'
                       )""",
                    company_id, employee_id, location_id,
                )
                if not assigned_here:
                    return {"status": "refused", "message": "That employee is not assigned to this schedule location."}
            row = await conn.fetchrow(
                """
                INSERT INTO employee_compliance_attestations
                    (company_id, employee_id, attestation_type, value, effective_from, confirmed_by, note)
                VALUES ($1, $2, 'meal_break_waiver_on_file', $3, $4, $5, $6)
                RETURNING id, value, effective_from, confirmed_at, note
                """,
                company_id, employee_id, on_file, effective_from, actor_user_id,
                note.strip() if note else None,
            )
            # Company-wide by design — a waiver is an employee-level fact,
            # not a location-scoped one.  Every affected future shift must be
            # refreshed so guidance and the persisted minimum stay aligned.
            assignments = await conn.fetch(
                """
                SELECT s.id AS shift_id
                FROM schedule_shift_assignments a JOIN schedule_shifts s ON s.id=a.shift_id
                WHERE a.company_id=$1 AND a.employee_id=$2 AND s.status <> 'cancelled'
                  AND s.starts_at::date >= GREATEST($3, CURRENT_DATE)
                ORDER BY s.id
                """,
                company_id, employee_id, effective_from,
            )
            for assignment in assignments:
                await refresh_assignment_break_guidance_and_minimum(
                    conn, company_id, shift_id=assignment["shift_id"],
                    employee_id=employee_id, actor_user_id=actor_user_id,
                    source="meal_break_waiver_update",
                )
            await log_audit(
                conn, company_id, "employee", employee_id, actor_user_id,
                "employee.meal_break_waiver.update",
                {
                    "location_id": str(location_id),
                    "on_file": on_file,
                    "effective_from": effective_from.isoformat(),
                    "note": note.strip() if note else None,
                    "attestation_id": str(row["id"]),
                },
            )
    return {
        "status": "created", "record_id": str(row["id"]),
        "message": f"Meal-break waiver marked {'on file' if on_file else 'not on file'} effective {row['effective_from'].isoformat()}.",
    }


async def record_work_permit_core(
    *, company_id: UUID, actor_user_id: UUID, employee_id: UUID,
    location_id: UUID, issued_at: date | None, expires_at: date,
) -> dict[str, Any]:
    if issued_at and issued_at > expires_at:
        return {"status": "refused", "message": "The permit issue date must be on or before its expiry date."}
    async with get_connection() as conn:
        async with conn.transaction():
            employee = await conn.fetchrow(
                "SELECT work_location_id FROM employees WHERE id=$1 AND org_id=$2",
                employee_id, company_id,
            )
            location = await conn.fetchval("SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2", location_id, company_id)
            if not employee or not location:
                return {"status": "refused", "message": "Employee or location not found."}
            if employee["work_location_id"] != location_id:
                assigned_here = await conn.fetchval(
                    """SELECT EXISTS(
                           SELECT 1 FROM schedule_shift_assignments a
                           JOIN schedule_shifts s ON s.id=a.shift_id
                           WHERE a.company_id=$1 AND a.employee_id=$2 AND s.location_id=$3
                             AND s.status <> 'cancelled'
                       )""",
                    company_id, employee_id, location_id,
                )
                if not assigned_here:
                    return {"status": "refused", "message": "That employee is not assigned to this schedule location."}
            previous = await conn.fetchval(
                """SELECT id FROM employee_work_permits
                   WHERE company_id=$1 AND employee_id=$2 AND location_id=$3 AND status='active'
                   ORDER BY created_at DESC LIMIT 1 FOR UPDATE""",
                company_id, employee_id, location_id,
            )
            if previous:
                await conn.execute("UPDATE employee_work_permits SET status='superseded', updated_at=NOW() WHERE id=$1", previous)
            permit = await conn.fetchrow(
                """INSERT INTO employee_work_permits
                   (company_id, employee_id, location_id, issued_at, expires_at, status,
                    confirmed_on_file, confirmed_by, confirmed_at, supersedes_id)
                   VALUES ($1,$2,$3,$4,$5,'active',true,$6,NOW(),$7)
                   RETURNING id, expires_at""",
                company_id, employee_id, location_id, issued_at, expires_at, actor_user_id, previous,
            )
            await log_audit(
                conn, company_id, "employee", employee_id, actor_user_id,
                "employee.work_permit.record",
                {
                    "location_id": str(location_id),
                    "permit_id": str(permit["id"]),
                    "issued_at": issued_at.isoformat() if issued_at else None,
                    "expires_at": expires_at.isoformat(),
                    "supersedes_id": str(previous) if previous else None,
                },
            )
    return {"status": "created", "record_id": str(permit["id"]), "message": "Work permit recorded and confirmed on file."}


async def decide_eligibility_case_core(
    *, company_id: UUID, actor_user_id: UUID, actor_role: str, case_id: UUID,
    location_id: UUID, decision: str, acknowledgement_confirmed: bool,
    acknowledgement_note: str | None,
) -> dict[str, Any]:
    """Apply one manager's location-scoped eligibility decision.

    This is the same confirm-first operation used by the REST case endpoint,
    kept in a service so Huume and the frontend cannot drift on the legal
    acknowledgement or assignment-removal rules.
    """
    if decision not in {"remove", "keep"}:
        return {"status": "refused", "message": "Eligibility decisions must be remove or keep."}
    note = acknowledgement_note.strip() if acknowledgement_note else None
    if decision == "keep" and (not acknowledgement_confirmed or not note or len(note) < 20):
        return {
            "status": "refused",
            "message": "Keeping the employee requires a confirmed written acknowledgement of at least 20 characters.",
        }
    async with get_connection() as conn:
        async with conn.transaction():
            case, _scope = await require_eligibility_case_access(
                conn,
                company_id=company_id,
                case_id=case_id,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                lock=True,
            )
            if case["location_id"] != location_id:
                return {"status": "refused", "message": "That eligibility case is outside this schedule workspace."}
            decision_error = eligibility_case_decision_error(case)
            if decision_error:
                return {"status": "refused", "message": decision_error}
            if decision == "keep":
                await conn.execute(
                    """UPDATE schedule_eligibility_cases
                       SET status='keep_acknowledged', manager_decision_by=$1,
                           manager_decision_at=NOW(), manager_acknowledged_by=$1,
                           manager_acknowledged_at=NOW(), acknowledgement_note=$2,
                           updated_at=NOW()
                       WHERE id=$3""",
                    actor_user_id, note, case_id,
                )
                await conn.execute(
                    """UPDATE schedule_eligibility_case_assignments
                       SET action_status='retained', acted_at=NOW()
                       WHERE case_id=$1 AND action_status='pending'""",
                    case_id,
                )
                await log_audit(
                    conn, company_id, "eligibility_case", case_id, actor_user_id,
                    "eligibility_case.keep_acknowledged",
                    {"location_id": str(location_id), "legal_basis": case["legal_basis"], "note": note},
                )
                return {"status": "created", "decision": "keep", "record_id": str(case_id),
                        "message": "The employee was retained and the manager acknowledgement was recorded."}

            assignments = await conn.fetch(
                """SELECT a.shift_id, a.employee_id
                   FROM schedule_eligibility_case_assignments a
                   JOIN schedule_shifts s ON s.id=a.shift_id
                   WHERE a.case_id=$1 AND a.action_status='pending'
                     AND s.location_id=$2
                   FOR UPDATE""",
                case_id, location_id,
            )
            removed = 0
            for assignment in assignments:
                deleted = await conn.fetchval(
                    """DELETE FROM schedule_shift_assignments a USING schedule_shifts s
                       WHERE a.shift_id=$1 AND a.employee_id=$2 AND a.shift_id=s.id
                         AND s.company_id=$3 AND s.location_id=$4
                       RETURNING a.shift_id""",
                    assignment["shift_id"], assignment["employee_id"], company_id, location_id,
                )
                action_status = "removed" if deleted else "no_longer_assigned"
                if deleted:
                    removed += 1
                    await log_audit(
                        conn, company_id, "assignment", assignment["shift_id"], actor_user_id,
                        "assignment.delete",
                        {"source": "schedule_eligibility_case", "case_id": str(case_id),
                         "employee_id": str(assignment["employee_id"])},
                    )
                await conn.execute(
                    """UPDATE schedule_eligibility_case_assignments
                       SET action_status=$1, acted_at=NOW()
                       WHERE case_id=$2 AND shift_id=$3 AND employee_id=$4""",
                    action_status, case_id, assignment["shift_id"], assignment["employee_id"],
                )
            await conn.execute(
                """UPDATE schedule_eligibility_cases
                   SET status='removal_completed', manager_decision_by=$1,
                       manager_decision_at=NOW(), resolved_at=NOW(), updated_at=NOW()
                   WHERE id=$2""",
                actor_user_id, case_id,
            )
            return {"status": "created", "decision": "remove", "record_id": str(case_id),
                    "removed_assignments": removed,
                    "message": f"Eligibility case confirmed; removed {removed} future assignment(s)."}
