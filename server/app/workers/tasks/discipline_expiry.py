"""Celery task: flip stale active discipline records to expired.

Runs once per worker startup (systemd restarts the worker every ~15
minutes); the dispatcher gates execution on `scheduler_settings.task_key
= 'discipline_expiry'` being enabled. Idempotent — operates only on rows
where `expires_at <= NOW() AND status = 'active'`.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection


async def _dispatch_discipline_expiry() -> dict:
    conn = await get_db_connection()
    try:
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled FROM scheduler_settings WHERE task_key = 'discipline_expiry'"
            )
        except Exception:
            sched_row = None

        if sched_row and not sched_row["enabled"]:
            print("[Discipline Expiry] Scheduler disabled, skipping.")
            return {"flipped": 0, "skipped": True}
    finally:
        await conn.close()

    from app.matcha.services import discipline_engine
    flipped = await discipline_engine.expire_stale_records()
    print(f"[Discipline Expiry] Flipped {flipped} record(s) to expired.")
    return {"flipped": flipped}


@celery_app.task(name="discipline.expire_stale", bind=True, max_retries=1)
def run_discipline_expiry(self):
    """Sweep active discipline records past their expires_at to expired."""
    try:
        result = asyncio.run(_dispatch_discipline_expiry())
        return result
    except Exception as e:
        print(f"[Discipline Expiry] Task failed: {e}")
        raise self.retry(exc=e, countdown=120)
