"""Read-only, deterministic context used by the schedule Huume surface."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from app.database import get_connection


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
            SELECT id, name, address, city, state, postal_code
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
            SELECT s.id, s.role, s.department, s.starts_at, s.ends_at,
                   s.required_staff, s.status, s.kind, s.notes,
                   a.employee_id, a.status AS assignment_status,
                   a.manager_note, a.manager_note_visible_to_employee,
                   a.compliance_guidance,
                   e.first_name, e.last_name
            FROM schedule_shifts s
            LEFT JOIN schedule_shift_assignments a ON a.shift_id=s.id
            LEFT JOIN employees e ON e.id=a.employee_id
            WHERE s.company_id=$1 AND s.location_id=$2
              AND s.starts_at >= $3 AND s.starts_at < $4
            ORDER BY s.starts_at, e.first_name, e.last_name
            LIMIT 500
            """,
            company_id,
            location_id,
            start,
            end,
        )
    by_shift: dict[str, dict] = {}
    for row in shifts:
        key = str(row["id"])
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
        if row["employee_id"]:
            item["assignments"].append({
                "employee_id": str(row["employee_id"]),
                "name": " ".join(filter(None, [row["first_name"], row["last_name"]])),
                "status": row["assignment_status"],
                # Huume is operating in the manager's scoped workspace, so it
                # may see the manager note even when that note is intentionally
                # hidden from the employee. Preserve the visibility bit so it
                # can describe what the employee will receive accurately.
                "manager_note": row["manager_note"],
                "manager_note_visible_to_employee": row["manager_note_visible_to_employee"],
                "compliance_guidance": row["compliance_guidance"],
            })
    result = list(by_shift.values())
    return {
        "status": "ok",
        "location": dict(location),
        "week_start": week_start.isoformat(),
        "week_end": (week_start + timedelta(days=6)).isoformat(),
        "shift_count": len(result),
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
                   c.expires_at, c.legal_basis, c.next_escalation_at,
                   e.first_name, e.last_name
            FROM schedule_eligibility_cases c
            JOIN employees e ON e.id=c.employee_id
            WHERE c.company_id=$1 AND c.location_id=$2
              AND c.status IN ('warning_open','removal_requested','keep_acknowledged')
            ORDER BY c.next_escalation_at NULLS FIRST, c.expires_at
            LIMIT 200
            """,
            company_id, location_id,
        )
    return {
        "status": "ok",
        "cases": [
            {
                "id": str(row["id"]), "employee_id": str(row["employee_id"]),
                "employee_name": " ".join(filter(None, [row["first_name"], row["last_name"]])),
                "requirement_type": row["requirement_type"], "status": row["status"],
                "expires_at": _iso(row["expires_at"]),
                "legal_basis": row["legal_basis"],
                "next_escalation_at": _iso(row["next_escalation_at"]),
            }
            for row in rows
        ],
    }
