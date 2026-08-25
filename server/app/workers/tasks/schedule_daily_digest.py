"""Idempotent daily break and shift-note delivery for schedule locations."""

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled, scheduler_settings_row

logger = logging.getLogger(__name__)


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "schedule_daily_digest", default=False):
            return {"sent": 0, "skipped": True}
        settings = await scheduler_settings_row(conn, "schedule_daily_digest")
        max_per_cycle = int((settings["max_per_cycle"] if settings else None) or 500)
        max_per_cycle = max(1, min(max_per_cycle, 5_000))
        await conn.execute(
            "DELETE FROM schedule_digest_deliveries WHERE digest_date < CURRENT_DATE - INTERVAL '90 days'"
        )
        from app.matcha.services.scheduling.daily_digest import send_location_daily_digest
        locations = await conn.fetch(
            """
            SELECT l.company_id, l.id, l.timezone
            FROM business_locations l
            JOIN companies c ON c.id = l.company_id
            WHERE l.is_active IS NOT FALSE
              AND COALESCE((c.enabled_features->>'employee_schedule')::boolean, false)
            ORDER BY l.company_id, l.id
            LIMIT $1
            """,
            max_per_cycle,
        )
        total = 0
        failures = 0
        for location in locations:
            try:
                result = await send_location_daily_digest(
                    conn,
                    company_id=location["company_id"],
                    location_id=location["id"],
                    digest_date=_location_date(location["timezone"]),
                )
            except Exception:
                logger.exception(
                    "schedule_daily_digest failed for company=%s location=%s",
                    location["company_id"], location["id"],
                )
                failures += 1
                continue
            total += result.get("sent", 0)
        return {"sent": total, "locations": len(locations), "failures": failures}
    finally:
        await conn.close()


def _location_date(timezone_name: str | None):
    try:
        zone = ZoneInfo(timezone_name or "UTC")
    except (KeyError, ValueError):
        zone = timezone.utc
    return datetime.now(zone).date()


@celery_app.task(name="schedule_daily_digest.send", bind=True, max_retries=1)
def send_schedule_daily_digest(self):
    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)
