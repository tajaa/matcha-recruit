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
    from app.core.services.scope_registry.codify import propagate_drift_to_requirements

    async def _run():
        if trigger_source == "scheduled" and not await _scheduled_run_is_due():
            return {"status": "skipped", "reason": "an ingest completed recently"}
        conn = await get_db_connection()
        try:
            if index_slug:
                result = await ingest_by_slug(conn, index_slug)
                out = {"status": "completed", "results": [result.model_dump(mode="json")]}
            else:
                results, failures = await ingest_all(conn)
                out = {
                    "status": "completed_with_errors" if failures else "completed",
                    "results": [r.model_dump(mode="json") for r in results],
                    "failures": failures,
                }
            # Fan freshly-detected amended/removed drift out to the codified
            # requirement rows (change_status='needs_review'). Outside the ingest
            # transaction, idempotent — safe to run every ingest.
            out["propagation"] = await propagate_drift_to_requirements(conn)
            return out
        finally:
            await conn.close()

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        publish_task_error(CHANNEL, "scope_registry", index_slug or "all", str(exc))
        raise

    publish_task_complete(CHANNEL, "scope_registry", index_slug or "all", result)
    return result


@celery_app.task(name="scope_registry.fetch_authority_bodies", max_retries=0, time_limit=1800)
def fetch_authority_bodies(index_slug: str, triggered_by: Optional[str] = None):
    """Fetch the full statute/regulation text for one index's items.

    Admin-triggered — hits live regulator hosts (eCFR full-text XML / CA .gov),
    so it belongs on Celery, not a uvicorn worker. Idempotent (hash-skips
    unchanged bodies).
    """
    from app.workers.utils import get_db_connection
    from app.core.services.scope_registry.body_fetch import fetch_bodies_for_index

    async def _run():
        conn = await get_db_connection()
        try:
            return await fetch_bodies_for_index(conn, index_slug)
        finally:
            await conn.close()

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        publish_task_error(CHANNEL, "scope_registry_bodies", index_slug, str(exc))
        raise

    publish_task_complete(CHANNEL, "scope_registry_bodies", index_slug, result)
    return result


@celery_app.task(name="scope_registry.sync_all", max_retries=0, time_limit=1800)
def sync_all_authority_indexes():
    """Periodic sweep entrypoint — re-ingest every catalog index."""
    return ingest_authority_index(index_slug=None, trigger_source="scheduled")


@celery_app.task(name="scope_registry.classify_authority_index", max_retries=0, time_limit=1800)
def classify_authority_index(index_slug: str, triggered_by: Optional[str] = None):
    """Gemini pre-classification of one index's unclassified items.

    Admin-triggered only (authoring, not scheduled) — proposals land
    provisional and wait for human confirmation.
    """
    from app.workers.utils import get_db_connection
    from app.core.services.scope_registry.classify import classify_index

    async def _run():
        conn = await get_db_connection()
        try:
            return await classify_index(conn, index_slug)
        finally:
            await conn.close()

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        publish_task_error(CHANNEL, "scope_registry_classify", index_slug, str(exc))
        raise

    publish_task_complete(CHANNEL, "scope_registry_classify", index_slug, result)
    return result
