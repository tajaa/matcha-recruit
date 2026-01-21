"""
Celery tasks for culture profile aggregation.

Aggregates culture data from multiple interviews into a unified company profile.
"""

import asyncio
import json
from typing import Any

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


async def _aggregate_culture(company_id: str) -> dict[str, Any]:
    """Aggregate culture data from interviews into company profile."""
    from app.matcha.services.culture_analyzer import CultureAnalyzer
    from app.config import load_settings

    settings = load_settings()
    analyzer = CultureAnalyzer(
        api_key=settings.gemini_api_key,
        vertex_project=settings.vertex_project,
        vertex_location=settings.vertex_location,
        model=settings.analysis_model,
    )

    conn = await get_db_connection()
    try:
        # Get all completed interviews with culture data
        rows = await conn.fetch(
            """
            SELECT raw_culture_data FROM interviews
            WHERE company_id = $1 AND status = 'completed' AND raw_culture_data IS NOT NULL
            ORDER BY created_at DESC
            """,
            company_id,
        )

        if not rows:
            return {"status": "error", "error": "No completed interviews with culture data"}

        # Parse culture data from each interview
        culture_data_list = []
        for row in rows:
            data = row["raw_culture_data"]
            if isinstance(data, str):
                data = json.loads(data)
            if data:
                culture_data_list.append(data)

        if not culture_data_list:
            return {"status": "error", "error": "No valid culture data to aggregate"}

        # Aggregate culture profiles
        aggregated = await analyzer.aggregate_culture_profiles(culture_data_list)

        # Upsert culture profile
        await conn.execute(
            """
            INSERT INTO culture_profiles (company_id, profile_data, interview_count)
            VALUES ($1, $2, $3)
            ON CONFLICT (company_id)
            DO UPDATE SET profile_data = $2, interview_count = $3, updated_at = NOW()
            """,
            company_id,
            json.dumps(aggregated),
            len(culture_data_list),
        )

        return {
            "status": "completed",
            "interview_count": len(culture_data_list),
            "profile": aggregated,
        }

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=3)
def aggregate_culture_async(
    self,
    company_id: str,
) -> dict[str, Any]:
    """
    Aggregate culture data from interviews into company profile in background.

    Args:
        company_id: UUID of the company
    """
    print(f"[Worker] Starting culture aggregation for company {company_id}")

    try:
        result = asyncio.run(_aggregate_culture(company_id=company_id))

        # Notify frontend via Redis pub/sub
        publish_task_complete(
            channel=f"company:{company_id}",
            task_type="culture_aggregation",
            entity_id=company_id,
            result={"interview_count": result.get("interview_count", 0)},
        )

        print(f"[Worker] Completed culture aggregation for company {company_id}")
        return result

    except Exception as e:
        print(f"[Worker] Failed culture aggregation for company {company_id}: {e}")

        publish_task_error(
            channel=f"company:{company_id}",
            task_type="culture_aggregation",
            entity_id=company_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
