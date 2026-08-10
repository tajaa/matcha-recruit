"""Scheduled reconciliation for stranded Cappe domain registrations."""

import asyncio
import logging

from app.cappe.services.domain_register import finalize_domain_registration

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        setting = await scheduler_settings_row(conn, "cappe_domain_finalize")
        if not setting or not setting["enabled"]:
            return {"skipped": True}
        cap = setting["max_per_cycle"] or 20
        rows = await conn.fetch(
            "SELECT id FROM cappe_domains WHERE status = 'registering' "
            "AND updated_at < NOW() - INTERVAL '15 minutes' ORDER BY updated_at ASC LIMIT $1",
            cap,
        )
        for row in rows:
            await finalize_domain_registration(row["id"])
        return {"stranded": len(rows), "redriven": len(rows)}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_cappe_domain_finalize(self) -> dict:
    try:
        return {"status": "success", **asyncio.run(_run())}
    except Exception as exc:
        logger.exception("Cappe domain finalization failed")
        raise self.retry(exc=exc, countdown=60)
