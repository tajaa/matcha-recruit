"""Shared published-week guard for employee time-off request paths."""
from datetime import date
from uuid import UUID


PUBLISHED_WEEK_TIME_OFF_DETAIL = (
    "Time-off requests cannot be submitted for a week with published shifts. "
    "Choose a different week."
)


async def has_published_schedule_week(
    conn, company_id: UUID, start_date: date, end_date: date,
) -> bool:
    """Return whether any Sunday-starting published week overlaps the range."""
    return bool(await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM schedule_shifts s
            WHERE s.company_id = $1
              AND s.status = 'published'
              AND s.starts_at::date - EXTRACT(DOW FROM s.starts_at)::integer <= $3
              AND s.starts_at::date - EXTRACT(DOW FROM s.starts_at)::integer + 6 >= $2
        )
        """,
        company_id, start_date, end_date,
    ))
