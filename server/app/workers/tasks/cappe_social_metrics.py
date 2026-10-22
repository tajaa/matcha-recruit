"""Refresh follower counts and recent-post reach for connected social accounts.

Scheduled (hourly restart dispatch), gated by the `cappe_social_metrics`
scheduler row (seeded off). Read-only against Meta; a token the network now
refuses marks its connection `expired`, which the page shows as "reconnect".
"""
import asyncio
import logging

from app.cappe.services.social import metrics
from app.cappe.services.social.providers.meta import MetaConfig

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

TASK_KEY = "cappe_social_metrics"


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        setting = await scheduler_settings_row(conn, TASK_KEY)
        if not setting or not setting["enabled"]:
            return {"skipped": True}
        cfg = MetaConfig.from_settings()
        if cfg is None:
            return {"skipped": True, "reason": "meta_not_configured"}
        limit = max(1, min(int(setting["max_per_cycle"] or 50), 500))
        return await metrics.refresh_all(conn, cfg, limit=limit)
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_cappe_social_metrics(self) -> dict:
    """Refresh social follower counts and per-post metrics."""
    try:
        return {"status": "success", **asyncio.run(_run())}
    except Exception as exc:
        logger.exception("Cappe social metrics failed")
        raise self.retry(exc=exc, countdown=300)
