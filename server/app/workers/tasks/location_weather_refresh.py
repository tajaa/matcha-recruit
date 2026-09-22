"""Refresh daily forecasts for Autopilot-enabled business locations."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.core.feature_flags import merge_company_features
from app.core.services.weather.google_weather import fetch_daily_forecast
from app.matcha.services.scheduling.autopilot.weather_store import (
    ensure_location_coordinates,
    upsert_weather_days,
)

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)
MIN_INTERVAL_HOURS = 20
DEFAULT_BATCH = 50


async def _run(*, force: bool = False) -> dict:
    conn = await get_db_connection()
    try:
        settings = await scheduler_settings_row(conn, "location_weather_refresh")
        if not force and (not settings or not settings["enabled"]):
            return {"status": "disabled"}
        batch = int((settings and settings["max_per_cycle"]) or DEFAULT_BATCH)
        if not force:
            claimed = await conn.fetchval(
                """
                UPDATE scheduler_settings SET last_run_at=NOW()
                WHERE task_key='location_weather_refresh'
                  AND (last_run_at IS NULL OR last_run_at < NOW() - ($1 || ' hours')::interval)
                RETURNING TRUE
                """,
                str(MIN_INTERVAL_HOURS),
            )
            if not claimed:
                return {"status": "skipped", "reason": "a refresh ran recently"}
        else:
            await conn.execute(
                "UPDATE scheduler_settings SET last_run_at=NOW() WHERE task_key='location_weather_refresh'"
            )
        # Stalest first: every location needs a fresh forecast daily, so a
        # fixed created_at order would starve everything past the batch cap.
        rows = await conn.fetch(
            """
            SELECT l.id, l.company_id, l.timezone, c.enabled_features, c.signup_source
            FROM business_locations l
            JOIN companies c ON c.id=l.company_id
            LEFT JOIN LATERAL (
                SELECT MAX(w.fetched_at) AS last_fetched_at
                FROM schedule_weather_days w
                WHERE w.location_id=l.id
            ) w ON TRUE
            WHERE l.is_active IS NOT FALSE
              AND COALESCE(l.is_company_wide, false)=false
              AND c.deleted_at IS NULL
              AND COALESCE((c.enabled_features->>'schedule_autopilot')::boolean, false)
            ORDER BY w.last_fetched_at NULLS FIRST, l.created_at, l.id
            LIMIT $1
            """,
            batch,
        )

        counts = {
            "status": "ok", "candidates": len(rows), "processed": 0,
            "written": 0, "feature_disabled": 0, "no_timezone": 0,
            "no_coordinates": 0, "fetch_failed": 0,
        }
        async with httpx.AsyncClient(follow_redirects=True) as client:
            for row in rows:
                features = merge_company_features(row["enabled_features"], row["signup_source"])
                if not (features.get("employee_schedule") and features.get("schedule_autopilot")):
                    counts["feature_disabled"] += 1
                    continue
                if not row["timezone"]:
                    counts["no_timezone"] += 1
                    continue
                try:
                    today = datetime.now(ZoneInfo(row["timezone"])).date()
                except (KeyError, ValueError, ZoneInfoNotFoundError):
                    counts["no_timezone"] += 1
                    continue
                coords = await ensure_location_coordinates(
                    conn, client, company_id=row["company_id"], location_id=row["id"],
                )
                if not coords:
                    counts["no_coordinates"] += 1
                    continue
                forecast = await fetch_daily_forecast(lat=coords[0], lng=coords[1], days=10)
                if forecast is None:
                    counts["fetch_failed"] += 1
                    continue
                counts["written"] += await upsert_weather_days(
                    conn, company_id=row["company_id"], location_id=row["id"],
                    rows=forecast, today=today,
                )
                counts["processed"] += 1
        return counts
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=2)
def run_location_weather_refresh(self, force: bool = False):
    try:
        return asyncio.run(_run(force=force))
    except Exception as exc:
        logger.exception("Location weather refresh failed")
        raise self.retry(exc=exc, countdown=300)
