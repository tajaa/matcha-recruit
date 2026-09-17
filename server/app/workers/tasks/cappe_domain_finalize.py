"""Scheduled reconciliation for stranded Cappe domain registrations.

`finalize_domain_registration` now claims its row with an UPDATE that bumps
`updated_at`, so the 15-minute predicate below means "no worker has touched this
registration for 15 minutes" — i.e. the webhook's background task died mid-flight
— rather than merely "it has been registering a while". Without the claim this
task could re-enter a registration another process was still running.
"""

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
