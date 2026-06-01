"""Celery task: daily benefits eligibility + renewal-risk sync.

Periodic (re-dispatched on every ~15-min worker startup, gated by the
`benefit_eligibility_sync` row in scheduler_settings — seeded DISABLED). For
each company with the benefits feature on (or linked to a broker), it:

  1. Ingests the latest roster from Finch (if connected; CSV uploads land
     out-of-band via the upload endpoints).
  2. Detects Scope-1 eligibility exceptions (new-hire enrollment gaps +
     terminated-but-still-deducted premium leaks).
  3. Recomputes Scope-2 renewal-risk rows (turnover × incident trend).

The heavy lifting is in ``services/benefits_eligibility.py`` so it can be unit
tested without a worker.
"""
import asyncio
import logging

from ..celery_app import celery_app
from ..utils import get_db_connection
from app.matcha.services import benefits_eligibility as be

logger = logging.getLogger(__name__)


async def _run() -> dict:
    conn = await get_db_connection()
    processed = 0
    failed = 0
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT c.id
            FROM companies c
            WHERE COALESCE(c.enabled_features->>'benefits_admin', 'false') = 'true'
               OR EXISTS (
                   SELECT 1 FROM broker_company_links l
                   WHERE l.company_id = c.id AND l.status IN ('active', 'grace')
               )
            """
        )
        for r in rows:
            try:
                await be.run_for_company(conn, r["id"], use_finch=True)
                processed += 1
            except Exception as exc:  # noqa: BLE001 — one bad client shouldn't stop the run
                failed += 1
                logger.warning("benefit_eligibility_sync: company %s failed: %s", r["id"], exc)
    finally:
        await conn.close()
    summary = {"processed": processed, "failed": failed}
    logger.info("benefit_eligibility_sync complete: %s", summary)
    return summary


@celery_app.task(bind=True, max_retries=3)
def run_benefit_eligibility_sync(self):
    """Entry point dispatched by ``@worker_ready`` when the scheduler row is enabled."""
    return asyncio.run(_run())
