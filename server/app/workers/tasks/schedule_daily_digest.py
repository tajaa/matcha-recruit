"""Idempotent daily break and shift-note delivery for schedule locations."""

import asyncio
from datetime import date

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "schedule_daily_digest", default=False):
            return {"sent": 0, "skipped": True}
        from app.matcha.services.scheduling.daily_digest import send_location_daily_digest
        locations = await conn.fetch(
            "SELECT company_id, id FROM business_locations WHERE is_active IS NOT FALSE ORDER BY company_id, id"
        )
        total = 0
        for location in locations:
            result = await send_location_daily_digest(
                conn, company_id=location["company_id"], location_id=location["id"], digest_date=date.today()
            )
            total += result.get("sent", 0)
        return {"sent": total, "locations": len(locations)}
    finally:
        await conn.close()


@celery_app.task(name="schedule_daily_digest.send", bind=True, max_retries=1)
def send_schedule_daily_digest(self):
    try:
        return asyncio.run(_run())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)
