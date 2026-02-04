"""
Celery task for fetching Tier 1 structured data sources.

This task runs on worker startup (triggered by systemd timer every 15 min)
and fetches data from authoritative structured sources (CSV, HTML tables)
for the highest-trust compliance data layer.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection


async def _run_structured_data_fetch() -> dict:
    """Run the structured data fetch cycle."""
    from app.core.services.structured_data import StructuredDataService

    conn = await get_db_connection()
    try:
        service = StructuredDataService()
        return await service.fetch_all_due_sources(conn)
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=2)
def fetch_structured_data_sources(self) -> dict:
    """
    Fetch all structured data sources that are due for refresh.

    This task populates the structured_data_cache table with fresh data
    from authoritative sources like UC Berkeley Labor Center, DOL, EPI, and NCSL.

    The cached data becomes the Tier 1 (highest trust) source for compliance checks,
    allowing the system to skip Gemini research when authoritative data is available.

    Triggered on every worker startup via the worker_ready signal.
    """
    print("[Structured Data Fetch] Starting Tier 1 data refresh...")

    try:
        result = asyncio.run(_run_structured_data_fetch())
        print(f"[Structured Data Fetch] Completed: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Structured Data Fetch] Failed: {e}")
        raise self.retry(exc=e, countdown=300)  # Retry in 5 minutes
