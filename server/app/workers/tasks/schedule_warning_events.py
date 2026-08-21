"""Reconcile schedule competency warnings into EMS."""

import asyncio
import logging

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled

logger = logging.getLogger(__name__)


async def _run_schedule_warning_sweep() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "schedule_warning_events", default=False):
            return {"created_or_updated": 0, "resolved": 0, "skipped": True}
        from app.matcha.services.scheduling.schedule_warning_events import (
            reconcile_schedule_warning_events,
        )

        rows = await conn.fetch(
            "SELECT DISTINCT company_id FROM schedule_shifts ORDER BY company_id"
        )
        totals = {"created_or_updated": 0, "resolved": 0, "companies": 0}
        for row in rows:
            result = await reconcile_schedule_warning_events(conn, row["company_id"])
            totals["created_or_updated"] += result["created_or_updated"]
            totals["resolved"] += result["resolved"]
            totals["companies"] += 1
        return totals
    finally:
        await conn.close()


@celery_app.task(name="schedule_warning_events.reconcile", bind=True, max_retries=1)
def reconcile_schedule_warning_events_task(self):
    try:
        return asyncio.run(_run_schedule_warning_sweep())
    except Exception as exc:
        logger.exception("Schedule warning EMS sweep failed")
        raise self.retry(exc=exc, countdown=120)
