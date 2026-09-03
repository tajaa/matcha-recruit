"""Read-only, deterministic context used by the schedule Huume surface."""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from app.database import get_connection

from .schedule_eligibility import _credential_problem, local_date_at


def _iso(value):
    return value.isoformat() if value is not None else None


async def get_schedule_overview(
    *, company_id: UUID, location_id: UUID, week_start: date
) -> dict:
    """Return a bounded overview for one location and one editor week.

    This is intentionally deterministic. Huume may summarize it, but the
    source of truth for staffing, notes, and break guidance stays SQL/domain
    logic rather than a model-generated schedule snapshot.
    """
    start = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=7)
    async with get_connection() as conn:
        location = await conn.fetchrow(
            """
            SELECT id, name, address, city, state, zipcode
            FROM business_locations
            WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE
            """,
            location_id,
            company_id,
        )
        if not location:
            return {"status": "not_found", "message": "That location is not available."}
        shifts = await conn.fetch(
            """
            WITH bounded_shifts AS (
                SELECT s.id, s.role, s.department, s.starts_at, s.ends_at,
                       s.required_staff, s.status, s.kind, s.notes,
                       COUNT(*) OVER () AS total_shift_count
                FROM schedule_shifts s
                WHERE s.company_id=$1 AND s.location_id=$2
                  AND s.status <> 'cancelled'
                  AND s.starts_at >= $3 AND s.starts_at < $4
                ORDER BY s.starts_at, s.id
                LIMIT 500
            )
            SELECT b.id, b.role, b.department, b.starts_at, b.ends_at,
                   b.required_staff, b.status, b.kind, b.notes,
                   b.total_shift_count,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'employee_id', a.employee_id,
                               'name', TRIM(COALESCE(e.first_name, '') || ' ' || COALESCE(e.last_name, '')),
                               'status', a.status,
                               'manager_note', a.manager_note,
                               'manager_note_visible_to_employee', a.manager_note_visible_to_employee,
                               'compliance_guidance', a.compliance_guidance
                           ) ORDER BY e.first_name, e.last_name, a.employee_id
                       ) FILTER (WHERE a.employee_id IS NOT NULL),
                       '[]'::json
                   ) AS assignments
            FROM bounded_shifts b
            LEFT JOIN schedule_shift_assignments a ON a.shift_id=b.id
            LEFT JOIN employees e ON e.id=a.employee_id
            GROUP BY b.id, b.role, b.department, b.starts_at, b.ends_at,
                     b.required_staff, b.status, b.kind, b.notes, b.total_shift_count
            ORDER BY b.starts_at, b.id
            """,
            company_id,
            location_id,
            start,
            end,
        )
    by_shift: dict[str, dict] = {}
    for row in shifts:
        key = str(row["id"])
        assignments = row["assignments"]
        if isinstance(assignments, str):
            try:
                assignments = json.loads(assignments)
            except (TypeError, ValueError):
                assignments = []
        item = by_shift.setdefault(key, {
            "id": key,
            "role": row["role"],
            "department": row["department"],
            "starts_at": _iso(row["starts_at"]),
            "ends_at": _iso(row["ends_at"]),
            "required_staff": row["required_staff"],
            "status": row["status"],
            "kind": row["kind"],
            "notes": row["notes"],
            "assignments": [],
        })
        item["assignments"] = [
            {
                **assignment,
                "employee_id": str(assignment["employee_id"]),
            }
            for assignment in assignments
            if isinstance(assignment, dict) and assignment.get("employee_id")
        ]
    result = list(by_shift.values())
    total_shift_count = int(shifts[0]["total_shift_count"]) if shifts else 0
    return {
        "status": "ok",
        "location": dict(location),
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=6)).isoformat(),
        "shift_count": len(result),
        "total_shift_count": total_shift_count,
        "truncated": total_shift_count > len(result),
        "open_staffing_count": sum(
            max(0, (s["required_staff"] or 0) - len(s["assignments"])) for s in result
        ),
        "shifts": result,
    }


async def list_schedule_eligibility_cases(*, company_id: UUID, location_id: UUID) -> dict:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT c.id, c.employee_id, c.requirement_type, c.status,
                   c.expires_at AS case_expires_at, c.blocking_reason_code,
                   c.legal_basis, c.next_escalation_at,
                   e.first_name, e.last_name,
                   ct.label AS credential_label, ct.has_expiration,
                   ecr.status AS current_credential_status,
                   ecr.expires_at AS current_credential_expires_at,
                   location.timezone
            FROM schedule_eligibility_cases c
            JOIN employees e ON e.id=c.employee_id
            LEFT JOIN employee_credential_requirements ecr
              ON c.requirement_type='credential' AND ecr.id=c.requirement_id
            LEFT JOIN scoped_credential_types ct ON ct.id=ecr.credential_type_id
            LEFT JOIN business_locations location ON location.id=c.location_id
            WHERE c.company_id=$1 AND c.location_id=$2
              AND c.status IN ('warning_open','removal_requested','keep_acknowledged')
            ORDER BY c.next_escalation_at NULLS FIRST, c.expires_at
            LIMIT 200
            """,
            company_id, location_id,
        )
    cases = []
    instant = datetime.now(timezone.utc)
    for row in rows:
        current_problem = None
        if row["requirement_type"] == "credential" and row["current_credential_status"] is not None:
            current_problem = _credential_problem(
                {
                    "label": row["credential_label"],
                    "has_expiration": row["has_expiration"],
                    "status": row["current_credential_status"],
                    "expires_at": row["current_credential_expires_at"],
                },
                as_of=local_date_at(instant, row["timezone"]),
            )
        cases.append({
            "id": str(row["id"]), "employee_id": str(row["employee_id"]),
            "employee_name": " ".join(filter(None, [row["first_name"], row["last_name"]])),
            "requirement_type": row["requirement_type"], "status": row["status"],
            "blocking_reason_code": row["blocking_reason_code"],
            # This is the historical date that opened the case, not a claim
            # about the current credential. Give it an unambiguous name so a
            # model cannot relabel it as the live expiration.
            "case_expired_on": _iso(row["case_expires_at"]),
            "credential_label": row["credential_label"],
            "current_credential_status": row["current_credential_status"],
            "current_credential_expires_at": _iso(row["current_credential_expires_at"]),
            "currently_blocks_scheduling": (
                current_problem is not None
                if row["requirement_type"] == "credential"
                else None
            ),
            "current_block_reason": current_problem[1] if current_problem else None,
            "legal_basis": row["legal_basis"],
            "next_escalation_at": _iso(row["next_escalation_at"]),
        })
    return {
        "status": "ok",
        "policy": (
            "An eligibility case is a remediation record, not an independent assignment block. "
            "For credentials, currently_blocks_scheduling and current_block_reason come from the "
            "canonical requirement; case_expired_on is historical. Assignment confirmation still "
            "rechecks the canonical requirement for each shift."
        ),
        "cases": cases,
    }
