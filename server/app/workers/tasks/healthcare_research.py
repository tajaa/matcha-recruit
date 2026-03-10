"""
Celery task for healthcare-specific jurisdiction research.

Runs the 8 healthcare compliance categories (HIPAA, billing integrity,
clinical safety, etc.) as a background job so the main SSE research
stream stays fast for the 12 general labor categories.

Categories are researched sequentially (concurrency=1) to maximise
accuracy and avoid Gemini rate-limit pressure.
"""

import asyncio
from uuid import UUID

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error, publish_task_progress
from ..utils import get_db_connection


async def _run_healthcare_research(jurisdiction_id: str) -> dict:
    """Research healthcare categories for a jurisdiction and upsert results."""
    from app.core.services.compliance_service import (
        _research_healthcare_requirements_for_jurisdiction,
    )

    jid = UUID(jurisdiction_id)
    conn = await get_db_connection()
    try:
        def _publish_progress(progress: int, total: int, message: str) -> None:
            publish_task_progress(
                channel="admin:healthcare_research",
                task_type="healthcare_research",
                entity_id=jurisdiction_id,
                progress=progress,
                total=total,
                message=message,
            )

        result = await _research_healthcare_requirements_for_jurisdiction(
            conn,
            jid,
            progress_callback=_publish_progress,
        )
        result.pop("requirements", None)
        return result

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1, time_limit=900, soft_time_limit=840)
def run_healthcare_research(self, jurisdiction_id: str) -> dict:
    """Research healthcare compliance categories for a jurisdiction.

    Each category is researched sequentially to maximise accuracy.
    Results are upserted additively into jurisdiction_requirements with
    applicable_industries=["healthcare"].
    """
    print(f"[Worker] Starting healthcare research for jurisdiction {jurisdiction_id}")

    try:
        result = asyncio.run(_run_healthcare_research(jurisdiction_id))

        publish_task_complete(
            channel=f"admin:healthcare_research",
            task_type="healthcare_research",
            entity_id=jurisdiction_id,
            result=result,
        )

        print(f"[Worker] Completed healthcare research for jurisdiction {jurisdiction_id}: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Worker] Failed healthcare research for jurisdiction {jurisdiction_id}: {e}")

        publish_task_error(
            channel=f"admin:healthcare_research",
            task_type="healthcare_research",
            entity_id=jurisdiction_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=180 * (self.request.retries + 1))
