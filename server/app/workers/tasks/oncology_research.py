"""
Celery task for oncology-specific jurisdiction research.

Runs the 5 oncology compliance categories (radiation safety, chemotherapy
handling, tumor registry, etc.) as a background job, following the same
pattern as healthcare_research.py.

Categories are researched sequentially (concurrency=1) to maximise
accuracy and avoid Gemini rate-limit pressure.
"""

import asyncio
from uuid import UUID

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error, publish_task_progress
from ..utils import get_db_connection


async def _run_oncology_research(jurisdiction_id: str) -> dict:
    """Research oncology categories for a jurisdiction and upsert results."""
    from app.core.services.compliance_service import (
        _research_oncology_requirements_for_jurisdiction,
    )

    jid = UUID(jurisdiction_id)
    conn = await get_db_connection()
    try:
        def _publish_progress(progress: int, total: int, message: str) -> None:
            publish_task_progress(
                channel="admin:oncology_research",
                task_type="oncology_research",
                entity_id=jurisdiction_id,
                progress=progress,
                total=total,
                message=message,
            )

        result = await _research_oncology_requirements_for_jurisdiction(
            conn,
            jid,
            progress_callback=_publish_progress,
        )
        result.pop("requirements", None)
        return result

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1, time_limit=900, soft_time_limit=840)
def run_oncology_research(self, jurisdiction_id: str) -> dict:
    """Research oncology compliance categories for a jurisdiction.

    Each category is researched sequentially to maximise accuracy.
    Results are upserted additively into jurisdiction_requirements with
    applicable_industries=["healthcare:oncology"].
    """
    print(f"[Worker] Starting oncology research for jurisdiction {jurisdiction_id}")

    try:
        result = asyncio.run(_run_oncology_research(jurisdiction_id))

        publish_task_complete(
            channel="admin:oncology_research",
            task_type="oncology_research",
            entity_id=jurisdiction_id,
            result=result,
        )

        print(f"[Worker] Completed oncology research for jurisdiction {jurisdiction_id}: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Worker] Failed oncology research for jurisdiction {jurisdiction_id}: {e}")

        publish_task_error(
            channel="admin:oncology_research",
            task_type="oncology_research",
            entity_id=jurisdiction_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=180 * (self.request.retries + 1))
