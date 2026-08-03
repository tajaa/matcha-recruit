"""Celery task for refreshing HR news RSS feeds.

Wraps app.core.services.hr_news_service.refresh_feeds() so the periodic
worker can pull fresh items in addition to the on-demand admin trigger.
"""

import asyncio
import logging

from ..celery_app import celery_app
from ..utils import get_db_connection

logger = logging.getLogger(__name__)


async def _run_refresh() -> dict:
    from app.core.services.hr_news_service import refresh_feeds

    conn = await get_db_connection()
    try:
        return await refresh_feeds(conn)
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_hr_news_fetch(self) -> dict:
    """Pull latest items from configured HR news RSS feeds."""
    print("[HR News Fetch] Starting refresh...")
    try:
        result = asyncio.run(_run_refresh())
        print(f"[HR News Fetch] Completed: {result}")
        return {"status": "success", **result}
    except Exception as e:
        logger.exception("[HR News Fetch] Failed")
        raise self.retry(exc=e, countdown=120)
