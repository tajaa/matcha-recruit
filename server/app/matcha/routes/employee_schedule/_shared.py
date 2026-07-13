"""Shared helpers for the employee-schedule package.

Tenant resolution, audit logging, ownership guards, and shift serialization
(shifts enriched with their assignments + employee display names). All queries
are tenant-scoped: shifts/templates/requests on company_id, the roster on
employees.org_id (which holds the company id), locations on business_locations.
company_id.
"""

import json
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from ...dependencies import get_client_company_id

_SHIFT_COLS = (
    "id, company_id, location_id, template_id, series_id, role, department, "
    "starts_at, ends_at, break_minutes, required_staff, color, notes, status, "
    "published_at, created_at, updated_at"
)


async def require_company_id(current_user) -> UUID:
    """Resolve the caller's company, 403 if they have none (mirrors driver_risk)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    return company_id


async def log_audit(
    conn,
    company_id: UUID,
    entity_type: str,
    entity_id: Optional[UUID],
    actor_user_id: Optional[UUID],
    action: str,
    details: Optional[dict] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO schedule_audit_log
            (company_id, entity_type, entity_id, actor_user_id, action, details)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        company_id, entity_type, entity_id, actor_user_id, action,
        json.dumps(details or {}),
    )


async def assert_employee_in_company(conn, company_id: UUID, employee_id: UUID) -> None:
    """Employees are tenant-scoped on org_id (not company_id)."""
    row = await conn.fetchrow(
        "SELECT 1 FROM employees WHERE id = $1 AND org_id = $2",
        employee_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found")


async def assert_location_in_company(
    conn, company_id: UUID, location_id: Optional[UUID]
) -> None:
    if location_id is None:
        return
    row = await conn.fetchrow(
        "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Location not found")


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return str(value)


async def fetch_shifts(
    conn,
    company_id: UUID,
    start: datetime,
    end: datetime,
    *,
    status: Optional[str] = None,
    employee_id: Optional[UUID] = None,
) -> list[dict]:
    """Shifts overlapping [start, end) for a company, each with its assignments.

    When employee_id is given, only shifts that employee is assigned to are
    returned (the portal "my schedule" view). status filters the shift status.
    """
    params: list[Any] = [company_id, start, end]
    where = ["s.company_id = $1", "s.starts_at < $3", "s.ends_at > $2"]
    if status is not None:
        params.append(status)
        where.append(f"s.status = ${len(params)}")
    if employee_id is not None:
        params.append(employee_id)
        where.append(
            f"EXISTS (SELECT 1 FROM schedule_shift_assignments a2 "
            f"WHERE a2.shift_id = s.id AND a2.employee_id = ${len(params)})"
        )

    shift_rows = await conn.fetch(
        f"""
        SELECT {_SHIFT_COLS}
        FROM schedule_shifts s
        WHERE {' AND '.join(where)}
        ORDER BY s.starts_at ASC, s.created_at ASC
        """,
        *params,
    )
    shifts = [_shift_row_to_dict(r) for r in shift_rows]
    if not shifts:
        return []

    shift_ids = [s["id"] for s in shifts]
    assign_rows = await conn.fetch(
        """
        SELECT a.shift_id, a.employee_id, a.status,
               e.first_name, e.last_name, e.job_title
        FROM schedule_shift_assignments a
        JOIN employees e ON e.id = a.employee_id
        WHERE a.shift_id = ANY($1::uuid[])
        ORDER BY e.first_name, e.last_name
        """,
        shift_ids,
    )
    by_shift: dict[str, list[dict]] = {}
    for r in assign_rows:
        by_shift.setdefault(str(r["shift_id"]), []).append(
            {
                "employee_id": str(r["employee_id"]),
                "name": _display_name(r["first_name"], r["last_name"]),
                "job_title": r["job_title"],
                "status": r["status"],
            }
        )
    for s in shifts:
        s["assignments"] = by_shift.get(s["id"], [])
    return shifts


async def find_conflicts(
    conn,
    company_id: UUID,
    employee_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    *,
    exclude_shift_id: Optional[UUID] = None,
) -> list[dict]:
    """Non-cancelled shifts this employee is already on that overlap the window.

    Used to block accidental double-booking on the assignment paths; callers
    expose a `force` override for deliberate back-to-back/overlap scheduling.
    """
    rows = await conn.fetch(
        """
        SELECT s.id, s.starts_at, s.ends_at, s.role, s.status
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id
        WHERE s.company_id = $1 AND a.employee_id = $2
          AND s.status <> 'cancelled'
          AND s.starts_at < $4 AND s.ends_at > $3
          AND ($5::uuid IS NULL OR s.id <> $5)
        ORDER BY s.starts_at
        """,
        company_id, employee_id, starts_at, ends_at, exclude_shift_id,
    )
    return [
        {
            "shift_id": str(r["id"]),
            "starts_at": _iso(r["starts_at"]),
            "ends_at": _iso(r["ends_at"]),
            "role": r["role"],
            "status": r["status"],
        }
        for r in rows
    ]


def raise_conflict(employee_id: UUID, conflicts: list[dict]) -> None:
    """409 with structured detail the frontend can render / offer to force."""
    raise HTTPException(
        status_code=409,
        detail={
            "code": "schedule_conflict",
            "message": "Employee is already scheduled during this time",
            "employee_id": str(employee_id),
            "conflicts": conflicts,
        },
    )


async def fetch_shift_by_id(conn, company_id: UUID, shift_id: UUID) -> Optional[dict]:
    """A single serialized shift (with assignments), tenant-scoped, or None."""
    row = await conn.fetchrow(
        f"SELECT {_SHIFT_COLS} FROM schedule_shifts WHERE id = $1 AND company_id = $2",
        shift_id, company_id,
    )
    if not row:
        return None
    shift = _shift_row_to_dict(row)
    assign_rows = await conn.fetch(
        """
        SELECT a.employee_id, a.status, e.first_name, e.last_name, e.job_title
        FROM schedule_shift_assignments a
        JOIN employees e ON e.id = a.employee_id
        WHERE a.shift_id = $1
        ORDER BY e.first_name, e.last_name
        """,
        shift_id,
    )
    shift["assignments"] = [
        {
            "employee_id": str(r["employee_id"]),
            "name": _display_name(r["first_name"], r["last_name"]),
            "job_title": r["job_title"],
            "status": r["status"],
        }
        for r in assign_rows
    ]
    return shift


def _shift_row_to_dict(r) -> dict:
    return {
        "id": str(r["id"]),
        "location_id": str(r["location_id"]) if r["location_id"] else None,
        "template_id": str(r["template_id"]) if r["template_id"] else None,
        "series_id": str(r["series_id"]) if r["series_id"] else None,
        "role": r["role"],
        "department": r["department"],
        "starts_at": _iso(r["starts_at"]),
        "ends_at": _iso(r["ends_at"]),
        "break_minutes": r["break_minutes"],
        "required_staff": r["required_staff"],
        "color": r["color"],
        "notes": r["notes"],
        "status": r["status"],
        "published_at": _iso(r["published_at"]),
        "assignments": [],
    }


def _display_name(first: Optional[str], last: Optional[str]) -> str:
    name = f"{(first or '').strip()} {(last or '').strip()}".strip()
    return name or "Unnamed"


def serialize_template(r) -> dict:
    days = r["days_of_week"]
    if isinstance(days, str):
        try:
            days = json.loads(days)
        except json.JSONDecodeError:
            days = []
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "role": r["role"],
        "department": r["department"],
        "location_id": str(r["location_id"]) if r["location_id"] else None,
        "start_time": r["start_time"].isoformat() if r["start_time"] else None,
        "end_time": r["end_time"].isoformat() if r["end_time"] else None,
        "break_minutes": r["break_minutes"],
        "required_staff": r["required_staff"],
        "days_of_week": days if isinstance(days, list) else [],
        "color": r["color"],
        "notes": r["notes"],
    }


def serialize_request(r) -> dict:
    return {
        "id": str(r["id"]),
        "employee_id": str(r["employee_id"]),
        "employee_name": _display_name(r.get("first_name"), r.get("last_name")),
        "request_type": r["request_type"],
        "shift_id": str(r["shift_id"]) if r["shift_id"] else None,
        "shift_starts_at": _iso(r["shift_starts_at"]) if "shift_starts_at" in r else None,
        "shift_ends_at": _iso(r["shift_ends_at"]) if "shift_ends_at" in r else None,
        "target_employee_id": str(r["target_employee_id"]) if r["target_employee_id"] else None,
        "unavailable_start": _iso(r["unavailable_start"]),
        "unavailable_end": _iso(r["unavailable_end"]),
        "reason": r["reason"],
        "status": r["status"],
        "review_notes": r["review_notes"],
        "reviewed_at": _iso(r["reviewed_at"]),
        "created_at": _iso(r["created_at"]),
    }


async def fetch_roster(conn, company_id: UUID) -> list[dict]:
    """Active employees for the assignment picker."""
    rows = await conn.fetch(
        """
        SELECT id, first_name, last_name, job_title, department
        FROM employees
        WHERE org_id = $1
          AND COALESCE(employment_status, 'active') NOT IN ('terminated', 'inactive')
        ORDER BY first_name, last_name
        """,
        company_id,
    )
    return [
        {
            "id": str(r["id"]),
            "name": _display_name(r["first_name"], r["last_name"]),
            "job_title": r["job_title"],
            "department": r["department"],
        }
        for r in rows
    ]
