"""Transactional validation helpers for bilateral employee shift requests."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable
from uuid import UUID


def schedule_day_bounds(value: datetime | date) -> tuple[datetime, datetime]:
    """Return the UTC wall-clock day containing ``value`` as a half-open range."""
    day = value.date() if isinstance(value, datetime) else value
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


async def find_same_day_assignments(
    conn,
    company_id: UUID,
    employee_id: UUID,
    schedule_day: datetime | date,
    *,
    exclude_shift_ids: Iterable[UUID] = (),
) -> list[dict]:
    """Find every non-cancelled assignment overlapping a calendar day.

    This deliberately checks the full day rather than only overlapping shift
    windows: a person working an unrelated morning shift cannot pick up an
    afternoon offer on the same date.  ``exclude_shift_ids`` is used for a
    swap, where the employee is giving up the outgoing shift in the same
    approval transaction.
    """
    day_start, day_end = schedule_day_bounds(schedule_day)
    excluded = list(exclude_shift_ids)
    rows = await conn.fetch(
        """
        SELECT s.id AS shift_id, s.starts_at, s.ends_at, a.employee_id
        FROM schedule_shift_assignments a
        JOIN schedule_shifts s ON s.id = a.shift_id
        WHERE a.company_id = $1
          AND a.employee_id = $2
          AND a.status <> 'declined'
          AND s.status <> 'cancelled'
          AND s.starts_at < $4
          AND s.ends_at > $3
          AND (cardinality($5::uuid[]) = 0 OR s.id <> ALL($5::uuid[]))
        ORDER BY s.starts_at, s.id
        FOR UPDATE OF a, s
        """,
        company_id,
        employee_id,
        day_start,
        day_end,
        excluded,
    )
    return [dict(row) for row in rows]


def same_day_conflict_detail(employee_id: UUID, rows: list[dict]) -> dict:
    """Stable API error payload used by portal acceptance and manager review."""
    return {
        "code": "same_day_assignment",
        "employee_id": str(employee_id),
        "conflicting_shift_ids": [str(row["shift_id"]) for row in rows],
        "message": "Employee already has a shift on this day",
    }
