"""Shared published-week guard for employee time-off and availability paths."""
from datetime import date
from uuid import UUID


PUBLISHED_WEEK_TIME_OFF_DETAIL = (
    "Time-off requests cannot be submitted for a week with published shifts. "
    "Choose a different week."
)


PUBLISHED_WEEK_AVAILABILITY_DETAIL = (
    "Availability changes cannot start inside a week that already has published "
    "shifts. Pick a start date in a week that has not been published yet."
)


async def has_published_schedule_week(
    conn, company_id: UUID, start_date: date, end_date: date,
) -> bool:
    """Whether any published week overlaps the range.

    The week is anchored per shift on its OWN location's start day (joined,
    not a single company-wide constant): stores can start their weeks on
    different days, so one anchor would misjudge the overlap for all but one
    of them.
    """
    return bool(await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM schedule_shifts s
            LEFT JOIN schedule_location_profiles p
              ON p.location_id = s.location_id AND p.company_id = s.company_id
            WHERE s.company_id = $1
              AND s.status = 'published'
              AND s.starts_at::date - MOD(
                    EXTRACT(DOW FROM s.starts_at)::integer
                      - COALESCE(p.week_start_weekday, 0) + 7, 7) <= $3
              AND s.starts_at::date - MOD(
                    EXTRACT(DOW FROM s.starts_at)::integer
                      - COALESCE(p.week_start_weekday, 0) + 7, 7) + 6 >= $2
        )
        """,
        company_id, start_date, end_date,
    ))
