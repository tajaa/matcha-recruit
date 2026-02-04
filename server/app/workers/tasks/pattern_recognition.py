"""
Celery tasks for pattern recognition across jurisdictions.

This task runs on worker startup (triggered by systemd timer every 15 min)
and detects coordinated legislative changes across jurisdictions, flagging
stale jurisdictions that may need review.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection


async def _run_pattern_recognition() -> dict:
    """Run the pattern recognition cycle."""
    from app.core.services.pattern_recognition import run_pattern_recognition_cycle

    conn = await get_db_connection()
    try:
        return await run_pattern_recognition_cycle(conn)
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_pattern_recognition(self) -> dict:
    """
    Cross-jurisdiction pattern detection task.

    Detects coordinated changes (e.g., "5 states updated minimum wage on Jan 1")
    and flags jurisdictions that may need review. Creates 'review_recommended'
    alerts for affected business locations.

    Triggered on every worker startup via the worker_ready signal.
    """
    print("[Pattern Recognition] Starting pattern detection...")

    try:
        result = asyncio.run(_run_pattern_recognition())
        print(f"[Pattern Recognition] Completed: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Pattern Recognition] Failed: {e}")
        raise self.retry(exc=e, countdown=120)
