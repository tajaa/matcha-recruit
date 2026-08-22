"""Default-disabled, spend-capped Tell-Us shoutout radar scheduler."""
import asyncio
import logging

from ...tellus.services.shoutout.scan_service import scan_brand
from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled

logger = logging.getLogger(__name__)
_TASK_KEY = "tellus_shoutout_scan"


async def _dispatch() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, _TASK_KEY, default=False):
            return {"status": "disabled", "scanned": 0}
        claimed = await conn.fetchrow(
            """UPDATE scheduler_settings SET last_run_at=NOW()
               WHERE task_key=$1 AND (last_run_at IS NULL OR last_run_at < NOW() - INTERVAL '6 hours')
               RETURNING max_per_cycle""", _TASK_KEY,
        )
        if claimed is None:
            return {"status": "not_due", "scanned": 0}
        rows = await conn.fetch(
            """SELECT c.brand_id FROM tellus_shoutout_configs c
               JOIN tellus_brands b ON b.id=c.brand_id
               WHERE c.is_enabled AND b.plan_status='active'
                 AND (c.next_scan_after IS NULL OR c.next_scan_after <= NOW())
               ORDER BY c.next_scan_after NULLS FIRST LIMIT $1""",
            min(int(claimed["max_per_cycle"] or 10), 10),
        )
    finally:
        await conn.close()
    scanned, failed = 0, 0
    for row in rows:
        conn = await get_db_connection()
        try:
            await scan_brand(conn, row["brand_id"])
            scanned += 1
        except Exception:
            failed += 1
            logger.exception("Tell-Us shoutout scan failed for brand %s", row["brand_id"])
        finally:
            await conn.close()
    return {"status": "completed", "scanned": scanned, "failed": failed}


@celery_app.task(name="tellus_shoutout_scan.run_tellus_shoutout_scan", max_retries=0)
def run_tellus_shoutout_scan():
    return asyncio.run(_dispatch())
