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
    employee_id: UUID | None = None,
) -> bool:
    """Whether any published week overlaps the range.

    The week is anchored per shift on its OWN location's start day (joined,
    not a single company-wide constant): stores can start their weeks on
    different days, so one anchor would misjudge the overlap for all but one
    of them.

    With ``employee_id`` only shifts that employee could work count: their own
    store's, plus locationless shifts. Another store publishing its week must
    not lock this employee out of asking for time off.
    """
    params: list = [company_id, start_date, end_date]
    store_clause = ""
    if employee_id is not None:
        params.append(employee_id)
        store_clause = (
            "AND (s.location_id IS NULL OR s.location_id = ("
            "SELECT e.work_location_id FROM employees e "
            "WHERE e.id = $4 AND e.org_id = s.company_id))"
        )
    return bool(await conn.fetchval(
        f"""
        SELECT EXISTS (
            SELECT 1
            FROM schedule_shifts s
            LEFT JOIN schedule_location_profiles p
              ON p.location_id = s.location_id AND p.company_id = s.company_id
            WHERE s.company_id = $1
              AND s.status = 'published'
              {store_clause}
              AND s.starts_at::date - MOD(
                    EXTRACT(DOW FROM s.starts_at)::integer
                      - COALESCE(p.week_start_weekday, 0) + 7, 7) <= $3
              AND s.starts_at::date - MOD(
                    EXTRACT(DOW FROM s.starts_at)::integer
                      - COALESCE(p.week_start_weekday, 0) + 7, 7) + 6 >= $2
        )
        """,
        *params,
    ))


async def employee_local_today(conn, employee_id: UUID) -> date:
    """Today's date on the employee's store clock (UTC when they have none).

    A date picked in the app is the employee's calendar day. The server's own
    date rolls over at 5 PM Pacific, so comparing against it rejected "today"
    every evening.
    """
    today = await conn.fetchval(
        """SELECT (NOW() AT TIME ZONE COALESCE(bl.timezone, 'UTC'))::date
           FROM employees e
           LEFT JOIN business_locations bl ON bl.id = e.work_location_id
           WHERE e.id = $1""",
        employee_id,
    )
    if today is None:
        today = await conn.fetchval("SELECT CURRENT_DATE")
    return today
