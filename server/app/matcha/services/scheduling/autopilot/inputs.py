"""Database loaders for the otherwise pure Schedule Autopilot engine."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.feature_flags import get_company_features
from app.database import connection_or_direct

from .holidays import holidays_between
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


def weather_refresh_needed(
    rows: dict[date, dict], *, week_start: date, today: date, now: datetime | None = None,
) -> bool:
    """Whether a provider call could improve the stored week.

    Google forecasts 10 days out. A week wholly past that horizon (or already
    over) can never be filled, so it must not trigger a geocode + provider
    call on every build.
    """
    end = week_start + timedelta(days=6)
    first = max(week_start, today)
    last = min(end, today + timedelta(days=FORECAST_HORIZON_DAYS - 1))
    if first > last:
        return False
    wanted = {first + timedelta(days=offset) for offset in range((last - first).days + 1)}
    newest = max((row.get("fetched_at") for row in rows.values() if row.get("fetched_at")), default=None)
    now = now or datetime.now(timezone.utc)
    return newest is None or newest < now - timedelta(hours=24) or not wanted <= set(rows)


def _location_today(tz_name: str | None) -> date | None:
    try:
        return datetime.now(ZoneInfo(tz_name)).date() if tz_name else None
    except (KeyError, ValueError, ZoneInfoNotFoundError):
        return None


async def ensure_autopilot_weather(
    *, company_id: UUID, location_id: UUID, week_start: date, today: date | None = None,
) -> None:
    """Refresh the stored forecast when it can help, holding NO connection
    across the provider calls.

    The build used to refresh from inside `propose_week_draft`'s connection,
    parking a pooled connection on a Census geocode plus two 10-second Google
    pages. Called before the build acquires its own; best effort — a failure
    leaves the stored rows and the build goes on without them.
    """
    try:
        async with connection_or_direct() as conn:
            features = await get_company_features(company_id, conn=conn)
            if not features.get("schedule_autopilot"):
                return
            rows = await load_weather_days(
                conn, company_id=company_id, location_id=location_id,
                start=week_start, end=week_start + timedelta(days=6),
            )
            if today is None:
                today = _location_today(await conn.fetchval(
                    "SELECT timezone FROM business_locations WHERE id=$1 AND company_id=$2",
                    location_id, company_id,
                ))
        if today is None or not weather_refresh_needed(rows, week_start=week_start, today=today):
            return
        await refresh_location_weather(company_id=company_id, location_id=location_id)
    except Exception:
        logger.warning("Autopilot weather refresh failed for %s", location_id, exc_info=True)


async def load_location_holidays(
    conn, *, company_id: UUID, location_id: UUID, start: date, end: date,
) -> dict[date, str]:
    """US demand holidays in [start, end] for a US (or unknown-country) store.

    A store outside the US gets none rather than the wrong country's calendar.
    """
    country = await conn.fetchval(
        "SELECT country_code FROM business_locations WHERE id=$1 AND company_id=$2",
        location_id, company_id,
    )
    if country not in (None, "", "US", "USA"):
        return {}
    return holidays_between(start, end)


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
        # Read only: `ensure_autopilot_weather` refreshed it before this
        # connection was taken.
        "weather_by_day": await load_weather_days(
            conn, company_id=company_id, location_id=location_id,
            start=week_start, end=week_start + timedelta(days=6),
        ),
        "history_shifts": await load_schedule_history(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        ),
        "blended_hourly_rate": await load_blended_hourly_rate(
            conn, company_id=company_id, location_id=location_id,
        ),
        "holidays": await load_location_holidays(
            conn, company_id=company_id, location_id=location_id,
            start=sales_start, end=week_start + timedelta(days=6),
        ),
        "anchor": week_start,
    }
