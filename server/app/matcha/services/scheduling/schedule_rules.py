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


def unlocated_employee_detail(employee_id: UUID) -> dict:
    """422 body for scheduling someone with no work location. Deliberately
    NOT forceable (no ?force=true) — unlike conflict/shift_full/availability,
    this is missing data, not a judgement call."""
    return {
        "code": "employee_has_no_location",
        "message": "Assign this employee a work location before scheduling them",
        "employee_id": str(employee_id),
    }


def location_mismatch_detail(employee_id: UUID, employee_location_id, shift_location_id) -> dict:
    """422 body for scheduling someone at a different location than their
    own. Also not forceable."""
    return {
        "code": "employee_wrong_location",
        "message": "Employee's work location differs from this shift's location",
        "employee_id": str(employee_id),
        "employee_location_id": str(employee_location_id),
        "shift_location_id": str(shift_location_id),
    }


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


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def availability_violations(
    windows_by_weekday: dict[int, list[tuple[time, time]]],
    starts_at: datetime, ends_at: datetime,
) -> list[dict]:
    """Portions of [starts_at, ends_at) not covered by the employee's weekly
    availability. Empty dict = fully available (no availability logged) = [].
    Weekday keys are Sun=0..Sat=6, same as the template weekday mask. A
    window's end_time of 23:59 counts as covering through midnight, so
    '00:00-23:59' means all day. A day-segment must be covered by a SINGLE
    window (windows are validated non-overlapping at write time; contiguous-
    window stitching is deliberately out of scope). Times are the same UTC
    wall-clock convention as shift timestamps — no tz conversion."""
    if not windows_by_weekday:
        return []
    violations: list[dict] = []
    cursor = starts_at
    while cursor < ends_at:
        day_end = datetime.combine(
            cursor.date() + timedelta(days=1), time.min, tzinfo=cursor.tzinfo)
        seg_end = min(ends_at, day_end)
        seg_start_min = _minutes(cursor.time())
        seg_end_min = 24 * 60 if seg_end == day_end else _minutes(seg_end.time())
        weekday = sunday_indexed_weekday(cursor.date())
        windows = windows_by_weekday.get(weekday, [])
        covered = any(
            _minutes(w_start) <= seg_start_min
            and seg_end_min <= (24 * 60 if w_end >= time(23, 59) else _minutes(w_end))
            for (w_start, w_end) in windows
        )
        if not covered:
            desc = ", ".join(f"{str(s)[:5]}–{str(e)[:5]}" for s, e in windows) or "not available"
            violations.append({
                "date": cursor.date().isoformat(),
                "weekday": weekday,
                "message": f"{cursor.date().isoformat()}: outside logged availability ({desc})",
            })
        cursor = seg_end
    return violations


def availability_detail(employee_id: UUID, violations: list[dict]) -> dict:
    """409 body for scheduling outside availability — forceable, same shape
    family as conflict_detail/shift_full_detail."""
    return {
        "code": "outside_availability",
        "message": "Employee is not available during this time",
        "employee_id": str(employee_id),
        "violations": violations,
    }


def job_qualification_detail(employee_id: UUID, job_id: UUID, job_name: str) -> dict:
    """409 body for assigning someone not on a job's qualified list —
    forceable, same shape family as conflict_detail/shift_full_detail/
    availability_detail. Not a 422: this is a staffing judgement call, not a
    statutory bright line."""
    return {
        "code": "not_qualified_for_job",
        "message": f"Not on the qualified list for {job_name}",
        "employee_id": str(employee_id),
        "job_id": str(job_id),
        "job_name": job_name,
    }


def job_changed(patch: dict, existing) -> bool:
    """True only when a PATCH actually moves the shift to a different job.

    The schedule editor sends job_id on every save, so "the caller sent it" is
    not "it changed" — reading the two as the same re-runs the entire
    compliance pass (break minimum, conflicts, availability, Fair Workweek) on
    an edit that only touched the notes, and can 422/409 a save that used to
    go through silently.
    """
    return "job_id" in patch and patch["job_id"] != existing["job_id"]


def compliance_relevant_patch(
    patch: dict, existing, *, retimed: bool, auto_break_requested: bool,
) -> bool:
    """Whether a shift PATCH has to re-run the compliance pass.

    Retiming a staffed shift can double-book everyone on it; a break, location
    or job change moves the meal-break minimum, the jurisdiction, or who is
    qualified. `location_id` and `break_minutes` are deliberately still tested
    for PRESENCE, not for change — that is long-standing behaviour and the
    clients that send them only send them on edit.
    """
    return bool(
        auto_break_requested
        or retimed
        or "break_minutes" in patch
        or "location_id" in patch
        or job_changed(patch, existing)
    )


def shift_window_on_date(starts_at: datetime, ends_at: datetime, target: date) -> tuple[datetime, datetime]:
    """The same shift window re-anchored to `target`: preserves time-of-day
    and duration, so an overnight shift keeps its +1-day end. Pure day
    arithmetic on UTC wall-clock timestamps — no DST concerns."""
    shift_by = timedelta(days=(target - starts_at.date()).days)
    return starts_at + shift_by, ends_at + shift_by


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
