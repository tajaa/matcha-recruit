"""Celery task: import archive pictures into a Cappe site's library.

On-demand (`.delay(site_id)` from `routes/library.py` when an owner imports
pictures from Openverse, Smithsonian, The Met or NASA), not scheduled. Each
import is claimed before it is worked (`services/magazine/imports.py`), so a
re-dispatch or two overlapping runs never fetch the same picture twice, and
the owner's page re-dispatches anything a dead worker left behind.

Pool-free like every worker: one direct connection, no transaction held while
a picture downloads.
"""
import asyncio
import logging

from app.cappe.services.magazine import imports

from ..celery_app import celery_app
from ..utils import get_db_connection

logger = logging.getLogger(__name__)

# A request queues at most imports.MAX_PER_REQUEST; a run takes a couple of
# requests' worth and leaves the rest to the next dispatch.
MAX_PER_RUN = 50


async def _run(site_id: str) -> dict:
    conn = await get_db_connection()
    counts: dict[str, int] = {}
    try:
        for _ in range(MAX_PER_RUN):
            status = await imports.import_next(conn, site_id)
            if status is None:
                break
            counts[status] = counts.get(status, 0) + 1
    finally:
        await conn.close()
    return counts


@celery_app.task(bind=True, max_retries=0, soft_time_limit=540, time_limit=590)
def run_cappe_media_import(self, site_id: str) -> dict:
    """Work one site's queued picture imports."""
    try:
        return {"status": "success", **asyncio.run(_run(site_id))}
    except Exception:
        logger.exception("[Cappe Media Import] failed for site %s", site_id)
        raise
