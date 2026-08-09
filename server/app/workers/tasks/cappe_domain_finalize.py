"""Re-drive Cappe domain finalization for stranded paid registrations."""
import asyncio
import logging
from app.cappe.services.domain_register import finalize_domain_registration
from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

async def _run() -> dict:
    conn = await get_db_connection()
    try:
        row = await scheduler_settings_row(conn, "cappe_domain_finalize")
        if not row or not row["enabled"]:
            return {"skipped": True, "reason": "scheduler_disabled" if row else "scheduler_not_registered"}
        cap = row["max_per_cycle"] or 20
        stranded = await conn.fetch("SELECT id FROM cappe_domains WHERE status='registering' AND updated_at < NOW() - (15 * INTERVAL '1 minute') ORDER BY updated_at ASC LIMIT $1", cap)
        for domain in stranded:
            await finalize_domain_registration(domain["id"])
        return {"stranded": len(stranded), "redriven": len(stranded)}
    finally:
        await conn.close()

@celery_app.task(bind=True, max_retries=1)
def run_cappe_domain_finalize(self):
    try:
        return {"status": "success", **asyncio.run(_run())}
    except Exception as exc:
        logger.exception("Cappe domain finalization failed")
        raise self.retry(exc=exc, countdown=60)
