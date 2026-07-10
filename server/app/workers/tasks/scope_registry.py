"""Celery task for scope-registry authority ingest.

Routed to Celery (not BackgroundTasks) because the federal parts each hit the
live eCFR API — a slow regulator host must not pin a uvicorn worker.

Scheduling: no celery-beat here. The hourly worker restart re-fires
`@worker_ready`, which dispatches `sync_all_authority_indexes` iff the
`scope_registry_authority` scheduler_settings row is enabled (seeded disabled by
`scoperg01`). A scheduled sweep declines on its own if one completed recently,
so enabling the row doesn't re-crawl .gov every hour.
"""
import asyncio
from typing import Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error

MIN_SCHEDULED_INTERVAL_DAYS = 6
CHANNEL = "admin:scope_registry"


async def _scheduled_run_is_due() -> bool:
    """Decline the scheduled sweep if ANY ingest landed recently.

    Deliberately keyed on last_ingested_at rather than a scheduled-only marker
    (compliance_evals' approach): a manual ingest days ago makes a full
    re-crawl of .gov redundant, and an admin can always trigger one manually.
    """
    from app.workers.utils import get_db_connection

    conn = await get_db_connection()
    try:
        recent = await conn.fetchval(
            """
            SELECT MAX(last_ingested_at) FROM authority_indexes
            WHERE last_ingested_at > NOW() - ($1 || ' days')::interval
            """,
            str(MIN_SCHEDULED_INTERVAL_DAYS),
        )
        return recent is None
    except Exception:
        return False
    finally:
        await conn.close()


@celery_app.task(name="scope_registry.ingest_authority_index", max_retries=0, time_limit=1800)
def ingest_authority_index(index_slug: Optional[str] = None, trigger_source: str = "manual"):
    """Ingest one authority index by slug, or the whole catalog when slug is None."""
    from app.workers.utils import get_db_connection
    from app.core.services.scope_registry.authority_ingest import (
        ingest_all,
        ingest_by_slug,
    )

    async def _run():
        if trigger_source == "scheduled" and not await _scheduled_run_is_due():
            return {"status": "skipped", "reason": "an ingest completed recently"}
        conn = await get_db_connection()
        try:
            if index_slug:
                result = await ingest_by_slug(conn, index_slug)
                return {"status": "completed", "results": [result.model_dump(mode="json")]}
            results, failures = await ingest_all(conn)
            return {
                "status": "completed_with_errors" if failures else "completed",
                "results": [r.model_dump(mode="json") for r in results],
                "failures": failures,
            }
        finally:
            await conn.close()

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        publish_task_error(CHANNEL, "scope_registry", index_slug or "all", str(exc))
        raise

    publish_task_complete(CHANNEL, "scope_registry", index_slug or "all", result)
    return result


@celery_app.task(name="scope_registry.sync_all", max_retries=0, time_limit=1800)
def sync_all_authority_indexes():
    """Periodic sweep entrypoint — re-ingest every catalog index."""
    return ingest_authority_index(index_slug=None, trigger_source="scheduled")
