"""Scheduling-compliance orchestration: DB assembly + enforcement.

The verdict logic is pure and lives in `services/schedule_compliance.py`; this
module does the I/O (resolve the shift's state, the employee's week hours, age,
adjacent-shift rest gap) and turns violations into the right HTTP response:

  - any BLOCK-severity violation  → 422 (non-overridable, even with force=true)
  - advisories + not force         → 409 (force=true proceeds + audit-logs)

`check_shift_compliance` returns the violation list (no raising) so the bulk
template path can collect warnings instead of raising per shift.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from ...services import schedule_compliance
from ...services.schedule_rules import compliance_warning_detail, compliance_block_detail


def _hours(starts_at: datetime, ends_at: datetime, break_minutes: int = 0) -> float:
    span = (ends_at - starts_at).total_seconds() / 3600.0
    return max(0.0, span - (break_minutes or 0) / 60.0)


def _week_window(d: datetime) -> tuple[datetime, datetime]:
    """Monday-anchored 7-day window containing `d` (UTC). An approximation of the
    employer workweek for the weekly-overtime advisory — no per-company workweek
    config exists to key off."""
    day = d.astimezone(timezone.utc).date()
    monday = day - timedelta(days=day.weekday())
    lo = datetime.combine(monday, datetime.min.time(), tzinfo=timezone.utc)
    return lo, lo + timedelta(days=7)


def _age_on(dob: Optional[date], on: date) -> Optional[int]:
    if not dob:
        return None
    years = on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))
    return years


async def _location_state(conn, company_id: UUID, location_id: Optional[UUID]) -> Optional[str]:
    if location_id is None:
        return None
    row = await conn.fetchrow(
        "SELECT state FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    return (row["state"] if row else None)


async def _employee_age(conn, company_id: UUID, employee_id: UUID, on: date) -> Optional[int]:
    """Age from the PII-segregated employee_demographics table. None when no DOB
    on file — the minor check then can't assert a violation (it skips, never
    blocks on unknown age)."""
    try:
        dob = await conn.fetchval(
            """
            SELECT ed.date_of_birth
            FROM employee_demographics ed
            JOIN employees e ON e.id = ed.employee_id
            WHERE ed.employee_id = $1 AND e.org_id = $2
            """,
            employee_id, company_id,
        )
    except Exception:
        return None
    return _age_on(dob, on)


async def _week_hours(conn, company_id: UUID, employee_id: UUID,
                      shift_start: datetime, this_shift_hours: float,
                      exclude_shift_id: Optional[UUID]) -> float:
    """This employee's total scheduled worked-hours for the week containing the
    shift, including the shift under evaluation."""
    lo, hi = _week_window(shift_start)
    rows = await conn.fetch(
        """
        SELECT s.starts_at, s.ends_at, s.break_minutes
        FROM schedule_shifts s
        JOIN schedule_shift_assignments a ON a.shift_id = s.id
        WHERE s.company_id = $1 AND a.employee_id = $2
          AND s.status <> 'cancelled'
          AND s.starts_at >= $3 AND s.starts_at < $4
          AND ($5::uuid IS NULL OR s.id <> $5)
        """,
        company_id, employee_id, lo, hi, exclude_shift_id,
    )
    total = sum(_hours(r["starts_at"], r["ends_at"], r["break_minutes"] or 0) for r in rows)
    return total + this_shift_hours


async def _min_rest_gap(conn, company_id: UUID, employee_id: UUID,
                        starts_at: datetime, ends_at: datetime,
                        exclude_shift_id: Optional[UUID]) -> Optional[float]:
    """Smallest gap (hours) to the employee's nearest shift before/after this one.
    None when they have no adjacent shift."""
    row = await conn.fetchrow(
        """
        SELECT
          (SELECT MIN($3 - s.ends_at) FROM schedule_shifts s
             JOIN schedule_shift_assignments a ON a.shift_id = s.id
             WHERE s.company_id = $1 AND a.employee_id = $2 AND s.status <> 'cancelled'
               AND s.ends_at <= $3 AND ($5::uuid IS NULL OR s.id <> $5)) AS before_gap,
          (SELECT MIN(s.starts_at - $4) FROM schedule_shifts s
             JOIN schedule_shift_assignments a ON a.shift_id = s.id
             WHERE s.company_id = $1 AND a.employee_id = $2 AND s.status <> 'cancelled'
               AND s.starts_at >= $4 AND ($5::uuid IS NULL OR s.id <> $5)) AS after_gap
        """,
        company_id, employee_id, starts_at, ends_at, exclude_shift_id,
    )
    gaps = [g for g in (row["before_gap"], row["after_gap"]) if g is not None]
    if not gaps:
        return None
    return min(g.total_seconds() / 3600.0 for g in gaps)


async def check_shift_compliance(
    conn,
    company_id: UUID,
    *,
    location_id: Optional[UUID],
    starts_at: datetime,
    ends_at: datetime,
    break_minutes: int,
    employee_id: Optional[UUID] = None,
    exclude_shift_id: Optional[UUID] = None,
) -> list[dict]:
    """Assemble context + evaluate. Returns violations (never raises). When
    `employee_id` is None (shift not yet assigned), only shift-intrinsic checks
    (meal break, daily OT, extreme-shift) run."""
    state = await _location_state(conn, company_id, location_id)
    worked = _hours(starts_at, ends_at, break_minutes)

    week_hours: Optional[float] = None
    min_rest: Optional[float] = None
    age: Optional[int] = None
    if employee_id is not None:
        week_hours = await _week_hours(conn, company_id, employee_id, starts_at, worked, exclude_shift_id)
        min_rest = await _min_rest_gap(conn, company_id, employee_id, starts_at, ends_at, exclude_shift_id)
        age = await _employee_age(conn, company_id, employee_id, starts_at.astimezone(timezone.utc).date())

    return schedule_compliance.evaluate_shift_for_employee(
        state=state,
        shift_hours=worked,
        break_minutes=break_minutes or 0,
        week_hours=week_hours,
        min_rest_gap_hours=min_rest,
        age=age,
    )


def raise_for_violations(violations: list[dict], *, force: bool) -> None:
    """Turn violations into the right HTTP error, or return quietly.

    BLOCK ⇒ 422 always (force can't override a bright-line minor-hour cap).
    Advisories ⇒ 409 unless force. Force on advisories returns quietly; the
    caller is responsible for audit-logging the override.
    """
    if not violations:
        return
    if schedule_compliance.has_block(violations):
        raise HTTPException(status_code=422, detail=compliance_block_detail(violations))
    if not force:
        raise HTTPException(status_code=409, detail=compliance_warning_detail(violations))
