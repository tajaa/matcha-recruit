"""Database loaders for the otherwise pure Schedule Autopilot engine."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .policy import POLICY_SALES_HISTORY_DAYS
from .weather_store import load_weather_days, refresh_location_weather

HISTORY_WEEKS = 8
# Google Weather daily forecasts reach 10 days (weather_store fetches days=10).
FORECAST_HORIZON_DAYS = 10
logger = logging.getLogger(__name__)


async def load_sales_by_day(
    conn, *, company_id: UUID, location_id: UUID, start: date, end: date,
) -> dict[date, Decimal]:
    rows = await conn.fetch(
        """
        SELECT si.business_date, SUM(sl.gross_sales) AS gross_sales
        FROM inventory_sales_lines sl
        JOIN inventory_sales_imports si ON si.id=sl.import_id
        WHERE si.company_id=$1 AND si.status='committed' AND si.location_id=$2
          AND si.business_date BETWEEN $3 AND $4
          AND sl.gross_sales IS NOT NULL
        GROUP BY si.business_date ORDER BY si.business_date
        """,
        company_id, location_id, start, end,
    )
    return {row["business_date"]: Decimal(str(row["gross_sales"])) for row in rows}


async def load_schedule_history(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    weeks: int = HISTORY_WEEKS,
) -> list[dict]:
    start = datetime.combine(week_start - timedelta(weeks=weeks), time.min, tzinfo=timezone.utc)
    end = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    rows = await conn.fetch(
        """
        SELECT s.starts_at, s.ends_at, s.job_id, s.break_minutes,
               s.required_staff, COUNT(a.id) AS assigned_count
        FROM schedule_shifts s
        LEFT JOIN schedule_shift_assignments a ON a.shift_id=s.id AND a.status <> 'declined'
        WHERE s.company_id=$1 AND s.location_id=$2
          AND s.status='published' AND s.kind='work'
          AND s.starts_at >= $3 AND s.starts_at < $4
        GROUP BY s.id ORDER BY s.starts_at, s.id LIMIT 2000
        """,
        company_id, location_id, start, end,
    )
    return [dict(row) for row in rows]


async def load_blended_hourly_rate(
    conn, *, company_id: UUID, location_id: UUID,
) -> Decimal | None:
    value = await conn.fetchval(
        """
        SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY pay_rate)
        FROM employees
        WHERE org_id=$1 AND work_location_id=$2 AND pay_rate IS NOT NULL
          AND COALESCE(pay_classification, 'hourly') <> 'exempt'
          AND COALESCE(employment_status, 'active') NOT IN ('terminated','offboarded')
        """,
        company_id, location_id,
    )
    if value is None:
        value = await conn.fetchval(
            """
            SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY default_hourly_rate)
            FROM schedule_jobs
            WHERE company_id=$1 AND (location_id=$2 OR location_id IS NULL)
              AND default_hourly_rate IS NOT NULL
            """,
            company_id, location_id,
        )
    return Decimal(str(value)) if value is not None else None


async def _fresh_weather(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    today: date | None = None,
) -> dict[date, dict]:
    """Stored forecast for the week, refreshed only when a refresh can help.

    Google forecasts 10 days out. A week wholly past that horizon (or already
    over) can never be filled, so it must not trigger a geocode + provider
    call on every build while this request holds a pooled connection.
    """
    end = week_start + timedelta(days=6)
    rows = await load_weather_days(
        conn, company_id=company_id, location_id=location_id, start=week_start, end=end,
    )
    if today is None:
        tz_name = await conn.fetchval(
            "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
            location_id, company_id,
        )
        try:
            today = datetime.now(ZoneInfo(tz_name)).date() if tz_name else None
        except (KeyError, ValueError, ZoneInfoNotFoundError):
            today = None
    if today is None:
        return rows
    first = max(week_start, today)
    last = min(end, today + timedelta(days=FORECAST_HORIZON_DAYS - 1))
    if first > last:
        return rows
    wanted = {first + timedelta(days=offset) for offset in range((last - first).days + 1)}
    newest = max((row.get("fetched_at") for row in rows.values() if row.get("fetched_at")), default=None)
    stale = newest is None or newest < datetime.now(timezone.utc) - timedelta(hours=24)
    if stale or not wanted <= set(rows):
        try:
            await refresh_location_weather(conn, company_id=company_id, location_id=location_id)
            rows = await load_weather_days(
                conn, company_id=company_id, location_id=location_id, start=week_start, end=end,
            )
        except Exception:
            logger.warning("Autopilot weather refresh failed for %s", location_id, exc_info=True)
    return rows


async def load_autopilot_inputs(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    roster: dict, profile_bundle: dict,
) -> dict:
    profile = dict(profile_bundle.get("profile") or {})
    profile["leader_job_ids"] = [job["id"] for job in profile_bundle.get("leader_jobs") or []]
    jobs_rows = await conn.fetch(
        """SELECT id, name, default_hourly_rate FROM schedule_jobs
           WHERE company_id=$1 AND (location_id=$2 OR location_id IS NULL)
           ORDER BY name, id""",
        company_id, location_id,
    )
    gated_rows = await conn.fetch(
        """SELECT DISTINCT job_id FROM schedule_job_employees
           WHERE company_id=$1 AND job_id=ANY($2::uuid[])""",
        company_id, [row["id"] for row in jobs_rows],
    ) if jobs_rows else []
    sales_start = week_start - timedelta(days=POLICY_SALES_HISTORY_DAYS)
    return {
        "week_start": week_start,
        "profile": profile,
        "jobs": [dict(row) for row in jobs_rows],
        "roster": roster,
        "gated_job_ids": {str(row["job_id"]) for row in gated_rows},
        "sales_by_day": await load_sales_by_day(
            conn, company_id=company_id, location_id=location_id,
            start=sales_start, end=week_start - timedelta(days=1),
        ),
        "weather_by_day": await _fresh_weather(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        ),
        "history_shifts": await load_schedule_history(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        ),
        "blended_hourly_rate": await load_blended_hourly_rate(
            conn, company_id=company_id, location_id=location_id,
        ),
        "anchor": week_start,
    }
