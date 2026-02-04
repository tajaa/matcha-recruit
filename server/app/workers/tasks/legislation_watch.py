"""
Celery tasks for legislation watch (RSS monitoring).

This task runs on worker startup (triggered by systemd timer every 15 min)
and processes RSS feeds from state DOL/legislature sites to detect
upcoming legislation changes.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection


async def _run_legislation_watch() -> dict:
    """Run the legislation watch cycle."""
    from app.core.services.legislation_watch import run_legislation_watch_cycle

    conn = await get_db_connection()
    try:
        return await run_legislation_watch_cycle(conn)
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_legislation_watch(self) -> dict:
    """
    RSS feed monitoring task for proactive legislation detection.

    Fetches active RSS feeds, scores items for relevance,
    and triggers Gemini analysis only for high-relevance items.
    Creates proactive alerts for detected legislation changes.

    Triggered on every worker startup via the worker_ready signal.
    """
    print("[Legislation Watch] Starting RSS monitoring...")

    try:
        result = asyncio.run(_run_legislation_watch())
        print(f"[Legislation Watch] Completed: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Legislation Watch] Failed: {e}")
        raise self.retry(exc=e, countdown=120)
