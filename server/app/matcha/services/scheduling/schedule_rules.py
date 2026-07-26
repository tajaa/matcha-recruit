"""Pure scheduling rules for the employee-schedule feature.

No DB, no FastAPI — just the decisions the routes make: which employees are
schedulable, what a week's bounds are, how a template materializes into shift
windows, how a PATCH becomes SQL, and the shape of the two 409s the frontend can
force through. The route layer (routes/employee_schedule/) does the I/O and
raises; everything here is a function of its arguments, so it can be tested
without a database.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

# employees.employment_status values that take someone off the schedule. The
# writable vocabulary lives in routes/employees/crud.py:VALID_EMPLOYMENT_STATUSES
# — 'inactive' is NOT one of them, so filtering on it silently keeps offboarded
# people in the assignment picker.
INACTIVE_EMPLOYMENT_STATUSES = ("terminated", "offboarded")


def week_bounds(start: date) -> tuple[datetime, datetime]:
    """[start 00:00 UTC, +7 days) — the window the weekly grid renders."""
    lo = datetime.combine(start, time.min, tzinfo=timezone.utc)
    return lo, lo + timedelta(days=7)


def summarize_shifts(shifts: list[dict]) -> dict:
    published = sum(1 for s in shifts if s["status"] == "published")
    draft = sum(1 for s in shifts if s["status"] == "draft")
    open_shifts = sum(
        1 for s in shifts
        if s["status"] != "cancelled" and len(s["assignments"]) < s["required_staff"]
    )
    assigned = sum(len(s["assignments"]) for s in shifts)
    return {
        "total_shifts": len(shifts),
        "published": published,
        "draft": draft,
        "open_shifts": open_shifts,
        "assigned": assigned,
    }


def sunday_indexed_weekday(d: date) -> int:
    """date.weekday() is Mon=0..Sun=6; the template mask is Sun=0..Sat=6."""
    return (d.weekday() + 1) % 7


def template_windows(
    start_date: date,
    end_date: date,
    day_set: set[int],
    start_time: time,
    end_time: time,
) -> tuple[list[datetime], list[datetime]]:
    """One (starts_at, ends_at) pair per matching weekday in [start_date, end_date].

    An overnight template (end <= start) rolls ends_at to the next calendar day.
    Times are UTC wall-clock: what the admin typed is what the employee sees.
    """
    overnight = end_time <= start_time
    starts: list[datetime] = []
    ends: list[datetime] = []
    d = start_date
    while d <= end_date:
        if sunday_indexed_weekday(d) in day_set:
            starts.append(datetime.combine(d, start_time, tzinfo=timezone.utc))
            end_day = d + timedelta(days=1) if overnight else d
            ends.append(datetime.combine(end_day, end_time, tzinfo=timezone.utc))
        d += timedelta(days=1)
    return starts, ends


def build_patch(
    values: dict[str, Any],
    *,
    first_param: int,
    casts: Optional[dict[str, str]] = None,
) -> tuple[str, list[Any]]:
    """SET-clause fragments for a true PATCH, numbered from $first_param.

    Only the keys the caller passed are written, so an explicitly-sent null
    CLEARS a nullable column. COALESCE(col, $n) could never express that — it
    reads "unset" and "clear me" identically, so a role or location could be set
    but never removed. `casts` maps a column to a Postgres type suffix
    (e.g. {"days_of_week": "jsonb"} → `days_of_week = $4::jsonb`).

    Returns ("col = $n, col2 = $n+1", [params]) with params in key order.
    """
    casts = casts or {}
    fragments: list[str] = []
    params: list[Any] = []
    for column, value in values.items():
        params.append(value)
        placeholder = f"${first_param + len(params) - 1}"
        if column in casts:
            placeholder += f"::{casts[column]}"
        fragments.append(f"{column} = {placeholder}")
    return ", ".join(fragments), params


def conflict_detail(employee_id: UUID, conflicts: list[dict]) -> dict:
    """409 body for a double-booking. `code` is what the frontend keys on to
    offer the force-override prompt."""
    return {
        "code": "schedule_conflict",
        "message": "Employee is already scheduled during this time",
        "employee_id": str(employee_id),
        "conflicts": conflicts,
    }


def shift_full_detail(assigned: int, required_staff: int) -> dict:
    """409 body for assigning past a shift's headcount — forceable, same as a conflict."""
    return {
        "code": "shift_full",
        "message": f"Shift already has {assigned} of {required_staff} required staff assigned",
        "assigned": assigned,
        "required_staff": required_staff,
    }


def compliance_warning_detail(violations: list[dict]) -> dict:
    """409 body for advisory scheduling-compliance flags — forceable, same shape
    family as conflict/shift_full. The frontend keys on `code` to offer the
    'Schedule anyway' override; `violations` carries the cited advisories."""
    return {
        "code": "schedule_compliance",
        "message": "This shift may not comply with scheduling law — review before proceeding",
        "violations": violations,
    }


def compliance_block_detail(violations: list[dict]) -> dict:
    """422 body for a bright-line scheduling-compliance BLOCK (minor-hour caps).
    Distinct code so the frontend renders a hard error with NO override — there
    is no force path (mirrors the discipline_compliance non-overridable block)."""
    return {
        "code": "schedule_compliance_block",
        "message": "This shift violates a hard scheduling-law limit and cannot be scheduled",
        "violations": [v for v in violations if v.get("severity") == "block"],
    }
