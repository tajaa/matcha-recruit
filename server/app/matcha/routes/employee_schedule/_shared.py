"""Shared helpers for the employee-schedule package.

Tenant resolution, audit logging, ownership guards, and shift serialization
(shifts enriched with their assignments + employee display names). All queries
are tenant-scoped: shifts/templates/requests on company_id, the roster on
employees.org_id (which holds the company id), locations on business_locations.
company_id.
"""

import json
import logging
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from ...dependencies import get_client_company_id
from ...services.scheduling.schedule_rules import (  # re-exported for the route modules
    INACTIVE_EMPLOYMENT_STATUSES, availability_detail, availability_violations,
    build_patch, conflict_detail, job_qualification_detail, location_mismatch_detail,
    shift_full_detail, shift_window_on_date, unlocated_employee_detail,
)
from ...services.scheduling.shift_writes import (  # noqa: F401 — re-exported for route modules + tests
    _iso, fetch_availability, find_conflicts, lock_scheduling_employees,
    log_audit, log_availability_override, shift_snapshot,
)
from ...services.scheduling.schedule_warning_events import reconcile_schedule_warning_events

logger = logging.getLogger(__name__)

_SHIFT_COLS = (
    "id, company_id, location_id, template_id, series_id, role, department, "
    "starts_at, ends_at, break_minutes, required_staff, color, notes, status, "
    "kind, training_requirement_id, job_id, published_at, created_at, updated_at"
)

# The one request-with-context projection, shared by the admin review router and
# the employee portal. serialize_request() indexes these keys directly, so the
# three surfaces that feed it must select the same columns.
REQUEST_SELECT = """
    SELECT r.id, r.employee_id, r.request_type, r.shift_id, r.target_employee_id,
           r.counter_shift_id, r.counterparty_confirmed_at,
           r.unavailable_start, r.unavailable_end, r.reason, r.status,
           r.review_notes, r.reviewed_at, r.created_at,
           e.first_name, e.last_name,
           te.first_name AS target_first_name, te.last_name AS target_last_name,
            s.starts_at AS shift_starts_at, s.ends_at AS shift_ends_at,
            s.role AS shift_role, s.department AS shift_department,
            cs.starts_at AS counter_shift_starts_at, cs.ends_at AS counter_shift_ends_at,
            cs.role AS counter_shift_role, cs.department AS counter_shift_department
    FROM schedule_requests r
    JOIN employees e ON e.id = r.employee_id
    LEFT JOIN employees te ON te.id = r.target_employee_id
    LEFT JOIN schedule_shifts s ON s.id = r.shift_id
    LEFT JOIN schedule_shifts cs ON cs.id = r.counter_shift_id
"""


async def reconcile_warning_events(conn, company_id: UUID, shift_ids: Optional[list[UUID]] = None) -> None:
    """Keep EMS warnings best-effort so an EMS outage never blocks scheduling."""
    try:
        await reconcile_schedule_warning_events(conn, company_id, shift_ids=shift_ids)
    except Exception:
        logger.exception("Could not reconcile schedule warning EMS events for %s", company_id)


async def require_company_id(current_user) -> UUID:
    """Resolve the caller's company, 403 if they have none (mirrors driver_risk)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    return company_id


async def assert_employee_in_company(conn, company_id: UUID, employee_id: UUID) -> None:
    """Employees are tenant-scoped on org_id (not company_id).

    Also rejects employees who have left: scheduling a terminated/offboarded
    person makes a shift read as covered when nobody will work it.
    """
    row = await conn.fetchrow(
        """
        SELECT COALESCE(employment_status, 'active') AS employment_status
        FROM employees WHERE id = $1 AND org_id = $2
        """,
        employee_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Employee not found")
    if row["employment_status"] in INACTIVE_EMPLOYMENT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Employee is {row['employment_status']} and cannot be scheduled",
        )


async def assert_employee_schedulable_at(
    conn, company_id: UUID, employee_id: UUID, location_id: Optional[UUID]
) -> None:
    """422 if the employee has no work location, or has one that isn't this
    shift's. Separate from assert_employee_in_company on purpose:
    availability.py calls that one too, and editing availability must keep
    working for a locationless employee — only the write paths that actually
    assign someone to a shift call this.

    No-ops when location_id is None — a locationless shift stays assignable
    by anyone, matching fetch_shifts' NULL-inclusive rule.
    """
    if location_id is None:
        return
    row = await conn.fetchrow(
        "SELECT work_location_id FROM employees WHERE id = $1 AND org_id = $2",
        employee_id, company_id,
    )
    if not row or row["work_location_id"] is None:
        raise HTTPException(status_code=422, detail=unlocated_employee_detail(employee_id))
    if row["work_location_id"] != location_id:
        raise HTTPException(
            status_code=422,
            detail=location_mismatch_detail(employee_id, row["work_location_id"], location_id),
        )


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


# Sentinel for assert_job_in_company's location_id: distinguishes "this caller
# has no location to check against" (omitted) from "the row being written has
# no location" (passed as None). The second case still has to reject a
# location-scoped job — otherwise a company-wide shift is a way to smuggle
# another store's job in.
UNSCOPED_LOCATION: Any = object()


async def assert_job_in_company(
    conn, company_id: UUID, job_id: Optional[UUID], *,
    location_id: Any = UNSCOPED_LOCATION, lock: bool = False,
):
    """404 unless the job is this company's; 422 unless it is available at the
    row's location. Returns the job row (name + location_id) so callers can
    write the job's current name as the canonical role label.

    A job with location_id NULL is company-wide and available everywhere. A
    location-scoped job is available only at its own location — including
    against a location-less shift, which is why `location_id=None` is a real
    constraint and not the same as omitting the argument.

    lock=True takes FOR SHARE, which is what actually closes the read/write
    race: without it a concurrent rename can still commit between this SELECT
    and the caller's INSERT, and the stale name gets persisted as the role.
    Only meaningful inside the caller's write transaction.
    """
    if job_id is None:
        return None
    row = await conn.fetchrow(
        "SELECT name, location_id FROM schedule_jobs WHERE id = $1 AND company_id = $2"
        + (" FOR SHARE" if lock else ""),
        job_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if (
        location_id is not UNSCOPED_LOCATION
        and row["location_id"] is not None
        and row["location_id"] != location_id
    ):
        raise HTTPException(status_code=422, detail="Job is not available at this location")
    return row


async def fetch_shifts(
    conn,
    company_id: UUID,
    start: datetime,
    end: datetime,
    *,
    status: Optional[str] = None,
    employee_id: Optional[UUID] = None,
    location_id: Optional[UUID] = None,
    starts_within: bool = False,
) -> list[dict]:
    """Shifts overlapping [start, end) for a company, each with its assignments.

    When employee_id is given, only shifts that employee is assigned to are
    returned (the portal "my schedule" view). status filters the shift status.

    starts_within=True matches on the shift's START instead of overlap. The week
    grid needs this: it buckets shifts into day columns by start date, and
    publish_range only publishes shifts starting in the window — so an
    overlap-matched shift that began before the window would be counted in the
    summary and publish button but rendered in no column and published by
    nothing. The portal's "my schedule" keeps overlap semantics (a shift already
    in progress is still yours).
    """
    params: list[Any] = [company_id, start, end]
    where = (
        ["s.company_id = $1", "s.starts_at >= $2", "s.starts_at < $3"]
        if starts_within
        else ["s.company_id = $1", "s.starts_at < $3", "s.ends_at > $2"]
    )
    if status is not None:
        params.append(status)
        where.append(f"s.status = ${len(params)}")
    if employee_id is not None:
        params.append(employee_id)
        where.append(
            f"EXISTS (SELECT 1 FROM schedule_shift_assignments a2 "
            f"WHERE a2.shift_id = s.id AND a2.employee_id = ${len(params)})"
        )
    if location_id is not None:
        params.append(location_id)
        # location_id IS NULL means a shift with no assigned location (never
        # cleared, or its location was later deleted) — keep those visible
        # from every location's view rather than orphaning them entirely.
        where.append(f"(s.location_id = ${len(params)} OR s.location_id IS NULL)")

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
               a.manager_note, a.manager_note_visible_to_employee,
               a.manager_note_include_in_location_digest,
               a.manager_note_send_employee_notice,
               a.compliance_guidance,
               e.first_name, e.last_name, e.job_title
        FROM schedule_shift_assignments a
        JOIN employees e ON e.id = a.employee_id
        WHERE a.shift_id = ANY($1::uuid[])
        ORDER BY e.first_name, e.last_name
        """,
        shift_ids,
    )
    override_rows = await conn.fetch(
        """
        SELECT entity_id, details, created_at
        FROM schedule_audit_log
        WHERE company_id = $1 AND entity_type = 'assignment'
          AND action = 'assignment.availability_override'
          AND entity_id = ANY($2::uuid[])
        ORDER BY created_at DESC
        """,
        company_id, shift_ids,
    )
    overrides: dict[tuple[str, str], dict] = {}
    for row in override_rows:
        details = row["details"]
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except json.JSONDecodeError:
                details = {}
        employee_id = details.get("employee_id")
        if employee_id:
            overrides.setdefault(
                (str(row["entity_id"]), str(employee_id)),
                {"at": _iso(row["created_at"]), "violations": details.get("violations", [])},
            )
    by_shift: dict[str, list[dict]] = {}
    for r in assign_rows:
        assignment = {
                "employee_id": str(r["employee_id"]),
                "name": _display_name(r["first_name"], r["last_name"]),
                "job_title": r["job_title"],
                "status": r["status"],
                "availability_overridden": (
                    str(r["shift_id"]), str(r["employee_id"])
                ) in overrides,
                "availability_override_at": overrides.get(
                    (str(r["shift_id"]), str(r["employee_id"])), {}
                ).get("at"),
            }
        # Portal calls pass employee_id, so never expose another employee's
        # private note or individualized compliance guidance. Admin responses
        # include note delivery controls so the editor can update them.
        if employee_id is None or r["employee_id"] == employee_id:
            assignment["manager_note"] = (
                r["manager_note"] if r["manager_note_visible_to_employee"] else None
            )
            assignment["compliance_guidance"] = r["compliance_guidance"]
        if employee_id is None:
            assignment["manager_note_visible_to_employee"] = r["manager_note_visible_to_employee"]
            assignment["manager_note_include_in_location_digest"] = r["manager_note_include_in_location_digest"]
            assignment["manager_note_send_employee_notice"] = r["manager_note_send_employee_notice"]
        by_shift.setdefault(str(r["shift_id"]), []).append(assignment)
    for s in shifts:
        s["assignments"] = by_shift.get(s["id"], [])
    return shifts


def raise_conflict(employee_id: UUID, conflicts: list[dict]) -> None:
    """409 with structured detail the frontend can render / offer to force."""
    raise HTTPException(status_code=409, detail=conflict_detail(employee_id, conflicts))


def raise_shift_full(assigned: int, required_staff: int) -> None:
    """409 the frontend can force through, same shape as raise_conflict."""
    raise HTTPException(
        status_code=409, detail=shift_full_detail(assigned, required_staff)
    )


def raise_outside_availability(employee_id: UUID, violations: list[dict]) -> None:
    """409 the frontend can force through, same shape as raise_conflict."""
    raise HTTPException(status_code=409, detail=availability_detail(employee_id, violations))


async def check_job_qualification(
    conn, company_id: UUID, employee_id: UUID, job_id,
    *, starts_at: datetime,
) -> Optional[dict]:
    """None when the shift carries no job (ungated — every pre-empsched04
    shift), when the job has no qualified roster at all, or when the employee
    is on that roster. Otherwise the 409 detail dict, for the caller to raise
    (unforced) or force past + audit (same pattern as availability_violations
    below — compute once, decide what to do with it at the call site).

    An EMPTY roster means ungated, and that is load-bearing. Picking a job is
    now mandatory on the manual create form, so without this rule every
    company that defines jobs but has not filled in the per-job qualified
    lists (a separate tab, and a common state) would get a forceable 409 on
    literally every assignment. Gating is opted into by naming who is
    qualified, not by the mere existence of a job.

    A dangling job_id (the job itself was deleted between read and write, or
    never existed) degrades to ungated rather than a hard error — deleting a
    job SET NULLs its shifts' job_id at the DB level, so this only matters for
    a stale in-flight request."""
    if job_id is None:
        return None
    row = await conn.fetchrow(
        """
        SELECT j.name,
               EXISTS (
                   SELECT 1 FROM schedule_job_employees je
                   WHERE je.job_id = j.id AND je.employee_id = $3
                     AND je.company_id = $2
                     AND je.qualification_status = 'active'
                     AND (je.qualified_from IS NULL OR je.qualified_from <= $4)
                     AND (je.qualified_until IS NULL OR je.qualified_until >= $4)
               ) AS qualified,
               EXISTS (
                   SELECT 1 FROM schedule_job_employees any_je
                   WHERE any_je.job_id = j.id AND any_je.company_id = $2
               ) AS has_roster
        FROM schedule_jobs j WHERE j.id = $1 AND j.company_id = $2
        """,
        job_id, company_id, employee_id, starts_at.date(),
    )
    if row is None or row["qualified"] or not row["has_roster"]:
        return None
    return job_qualification_detail(employee_id, job_id, row["name"])


def raise_not_qualified(detail: dict) -> None:
    """409 the frontend can force through, same shape as raise_conflict."""
    raise HTTPException(status_code=409, detail=detail)


async def fetch_shift_for_write(conn, company_id: UUID, shift_id: UUID):
    """The single read every assignment path takes before mutating a shift.

    Carries the window (conflict check), the status (a cancelled shift takes no
    assignments), the staffing counts (headcount cap), and the role/kind/
    training_requirement_id/job_id (training-lapse gate + scheduled-role
    rules + training-as-shift assignment + job-qualification gate). 404s if
    the shift isn't this company's.
    """
    row = await conn.fetchrow(
        """
        SELECT s.id, s.starts_at, s.ends_at, s.status, s.required_staff,
               s.location_id, s.break_minutes, s.role, s.kind,
               s.training_requirement_id, s.job_id,
               (SELECT COUNT(*) FROM schedule_shift_assignments a
                WHERE a.shift_id = s.id) AS assigned_count
        FROM schedule_shifts s
        WHERE s.id = $1 AND s.company_id = $2
        FOR UPDATE
        """,
        shift_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Shift not found")
    return row


async def fetch_locked_shift_pair(conn, company_id: UUID, *shift_ids: UUID) -> dict[str, Any]:
    """Fetch one or more tenant-owned shifts under row locks in deterministic order."""
    if not shift_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT s.id, s.starts_at, s.ends_at, s.status, s.required_staff,
               s.location_id, s.break_minutes, s.role, s.kind,
               s.training_requirement_id, s.job_id, s.published_at,
               (SELECT COUNT(*) FROM schedule_shift_assignments a
                WHERE a.shift_id = s.id) AS assigned_count
        FROM schedule_shifts s
        WHERE s.company_id = $1 AND s.id = ANY($2::uuid[])
        ORDER BY s.id
        FOR UPDATE
        """,
        company_id, sorted(set(shift_ids)),
    )
    return {str(row["id"]): row for row in rows}


def assert_shift_open_for_assignment(shift) -> None:
    """A cancelled shift is terminal — assigning to it would staff a dead shift."""
    if shift["status"] == "cancelled":
        raise HTTPException(
            status_code=409, detail="Cannot assign employees to a cancelled shift"
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
        SELECT a.employee_id, a.status, a.manager_note,
               a.manager_note_visible_to_employee, a.compliance_guidance,
               e.first_name, e.last_name, e.job_title
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
            "manager_note": r["manager_note"],
            "manager_note_visible_to_employee": r["manager_note_visible_to_employee"],
            "compliance_guidance": r["compliance_guidance"],
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
        "kind": r["kind"],
        "training_requirement_id": str(r["training_requirement_id"]) if r["training_requirement_id"] else None,
        "job_id": str(r["job_id"]) if r["job_id"] else None,
        "published_at": _iso(r["published_at"]),
        "assignments": [],
    }


def _display_name(first: Optional[str], last: Optional[str]) -> str:
    name = f"{(first or '').strip()} {(last or '').strip()}".strip()
    return name or "Unnamed"


def serialize_block(r) -> dict:
    """A schedule_shift_templates row — standalone (week_template_id is None,
    the shape schedule_chat.py still writes directly) or a week template's
    child block."""
    days = r["days_of_week"]
    if isinstance(days, str):
        try:
            days = json.loads(days)
        except json.JSONDecodeError:
            days = []
    return {
        "id": str(r["id"]),
        "week_template_id": str(r["week_template_id"]) if r["week_template_id"] else None,
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
        "job_id": str(r["job_id"]) if r["job_id"] else None,
    }


def serialize_week_template(r, blocks: list[dict]) -> dict:
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "location_id": str(r["location_id"]) if r["location_id"] else None,
        "color": r["color"],
        "notes": r["notes"],
        "blocks": blocks,
    }


def serialize_job(r, employee_ids: list[str], credential_requirements: list[dict] | None = None) -> dict:
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "location_id": str(r["location_id"]) if r["location_id"] else None,
        "color": r["color"],
        "notes": r["notes"],
        "employee_ids": employee_ids,
        "credential_grace_days": r.get("credential_grace_days"),
        "credential_requirements": credential_requirements or [],
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
        "shift_role": r.get("shift_role"),
        "shift_department": r.get("shift_department"),
        "target_employee_id": str(r["target_employee_id"]) if r["target_employee_id"] else None,
        "target_employee_name": _display_name(r.get("target_first_name"), r.get("target_last_name")),
        "counter_shift_id": str(r["counter_shift_id"]) if r.get("counter_shift_id") else None,
        "counterparty_confirmed_at": _iso(r["counterparty_confirmed_at"]) if r.get("counterparty_confirmed_at") else None,
        "counter_shift_starts_at": _iso(r["counter_shift_starts_at"]) if r.get("counter_shift_starts_at") else None,
        "counter_shift_ends_at": _iso(r["counter_shift_ends_at"]) if r.get("counter_shift_ends_at") else None,
        "counter_shift_role": r.get("counter_shift_role"),
        "counter_shift_department": r.get("counter_shift_department"),
        "unavailable_start": _iso(r["unavailable_start"]),
        "unavailable_end": _iso(r["unavailable_end"]),
        "reason": r["reason"],
        "status": r["status"],
        "review_notes": r["review_notes"],
        "reviewed_at": _iso(r["reviewed_at"]),
        "created_at": _iso(r["created_at"]),
    }


async def fetch_roster(conn, company_id: UUID, location_id: Optional[UUID] = None) -> list[dict]:
    """Active employees for the assignment picker.

    `location_id` scopes to that location's staff. STRICT — an employee with
    no work_location_id is deliberately EXCLUDED, not NULL-included the way
    fetch_shifts treats locationless shifts: an employee not tied to a
    location cannot be scheduled at all (see assert_employee_schedulable_at).
    """
    params: list[Any] = [company_id, list(INACTIVE_EMPLOYMENT_STATUSES)]
    where = "org_id = $1 AND COALESCE(employment_status, 'active') <> ALL($2::text[])"
    if location_id is not None:
        params.append(location_id)
        where += f" AND work_location_id = ${len(params)}"
    rows = await conn.fetch(
        f"""
        SELECT id, first_name, last_name, job_title, department
        FROM employees
        WHERE {where}
        ORDER BY first_name, last_name
        """,
        *params,
    )
    job_ids_by_employee: dict[str, list[str]] = {}
    job_qualifications_by_employee: dict[str, list[dict]] = {}
    if rows:
        job_rows = await conn.fetch(
            """
            SELECT je.employee_id, je.job_id, je.qualified_from, je.qualified_until,
                   (je.qualified_from IS NULL OR je.qualified_from <= CURRENT_DATE)
                   AND (je.qualified_until IS NULL OR je.qualified_until >= CURRENT_DATE)
                     AS currently_effective
            FROM schedule_job_employees je
            WHERE je.company_id = $1 AND je.employee_id = ANY($2::uuid[])
              AND je.qualification_status = 'active'
            """,
            company_id, [r["id"] for r in rows],
        )
        for jr in job_rows:
            employee_key = str(jr["employee_id"])
            if jr["currently_effective"]:
                job_ids_by_employee.setdefault(employee_key, []).append(str(jr["job_id"]))
            job_qualifications_by_employee.setdefault(employee_key, []).append({
                "job_id": str(jr["job_id"]),
                "qualified_from": jr["qualified_from"].isoformat() if jr["qualified_from"] else None,
                "qualified_until": jr["qualified_until"].isoformat() if jr["qualified_until"] else None,
            })
    return [
        {
            "id": str(r["id"]),
            "name": _display_name(r["first_name"], r["last_name"]),
            "job_title": r["job_title"],
            "department": r["department"],
            "job_ids": job_ids_by_employee.get(str(r["id"]), []),
            "job_qualifications": job_qualifications_by_employee.get(str(r["id"]), []),
        }
        for r in rows
    ]
