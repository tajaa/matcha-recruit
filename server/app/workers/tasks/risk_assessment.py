"""
Celery tasks for scheduled risk assessments.

These tasks compute risk scores across 5 dimensions for companies on a
schedule. The dispatcher finds companies due for reassessment and enqueues
individual tasks. Unlike manual runs, scheduled assessments skip the
expensive Gemini recommendations call.
"""

import asyncio
import json
from dataclasses import asdict
from typing import Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


_WEIGHT_KEYS = {"compliance", "incidents", "er_cases", "workforce", "legislative"}


async def _get_weights(conn) -> dict[str, float]:
    """Load risk assessment weights from platform_settings."""
    from app.matcha.services.risk_assessment_service import DEFAULT_WEIGHTS

    row = await conn.fetchval(
        "SELECT value FROM platform_settings WHERE key = 'risk_assessment_weights'"
    )
    if row:
        raw = json.loads(row) if isinstance(row, str) else row
        if isinstance(raw, dict):
            return {**DEFAULT_WEIGHTS, **{k: float(v) for k, v in raw.items() if k in _WEIGHT_KEYS}}
    return dict(DEFAULT_WEIGHTS)


async def _run_assessment(company_id: str) -> dict:
    """Compute and store a risk assessment for a single company (no recommendations)."""
    from uuid import UUID
    from app.matcha.services.risk_assessment_service import compute_risk_assessment

    conn = await get_db_connection()
    try:
        weights = await _get_weights(conn)
    finally:
        await conn.close()

    cid = UUID(company_id)
    result = await compute_risk_assessment(cid, weights=weights)

    dims_json = json.dumps(
        {key: asdict(dim) for key, dim in result.dimensions.items()},
        default=str,
    )

    conn = await get_db_connection()
    try:
        # Insert into history
        await conn.execute(
            """
            INSERT INTO risk_assessment_history
                (company_id, overall_score, overall_band, dimensions, weights, source, computed_at)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, 'scheduled', $6)
            """,
            cid,
            result.overall_score,
            result.overall_band,
            dims_json,
            json.dumps(weights),
            result.computed_at,
        )

        # Upsert snapshot — update scores but preserve existing report/recommendations
        await conn.execute(
            """
            INSERT INTO risk_assessment_snapshots
                (company_id, overall_score, overall_band, dimensions, weights, computed_at)
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
            ON CONFLICT (company_id) DO UPDATE SET
                overall_score  = EXCLUDED.overall_score,
                overall_band   = EXCLUDED.overall_band,
                dimensions     = EXCLUDED.dimensions,
                weights        = EXCLUDED.weights,
                computed_at    = EXCLUDED.computed_at
            """,
            cid,
            result.overall_score,
            result.overall_band,
            dims_json,
            json.dumps(weights),
            result.computed_at,
        )

        # next_risk_assessment is already advanced by the dispatcher (claim-before-enqueue).
        # Manual runs via the route handle their own advancement.
    finally:
        await conn.close()

    return {
        "company_id": company_id,
        "overall_score": result.overall_score,
        "overall_band": result.overall_band,
    }


async def _enqueue_due_assessments() -> dict:
    """Find companies due for risk assessment and enqueue individual tasks."""
    conn = await get_db_connection()
    try:
        # Check if risk_assessment scheduler is enabled and get max_per_cycle
        # Guard against scheduler_settings table not existing yet (deploy ordering)
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = 'risk_assessment'"
            )
        except Exception:
            sched_row = None

        if sched_row and not sched_row["enabled"]:
            print("[Risk Assessment Scheduler] Scheduler disabled, skipping.")
            return {"enqueued": 0}

        limit = (sched_row["max_per_cycle"] if sched_row and sched_row["max_per_cycle"] and sched_row["max_per_cycle"] > 0 else 3)

        # Claim due companies by advancing next_risk_assessment before enqueueing.
        # This prevents duplicate enqueues if the dispatcher runs again before tasks finish.
        rows = await conn.fetch(
            """
            UPDATE companies
            SET next_risk_assessment = NOW() + INTERVAL '1 day' * COALESCE(risk_assessment_interval_days, 7)
            WHERE id IN (
                SELECT id FROM companies
                WHERE next_risk_assessment IS NULL OR next_risk_assessment <= NOW()
                ORDER BY next_risk_assessment ASC NULLS FIRST
                LIMIT $1
            )
            RETURNING id
            """,
            limit,
        )

        enqueued = 0
        for row in rows:
            comp_id = str(row["id"])

            try:
                run_risk_assessment_task.delay(comp_id)
            except Exception as e:
                print(f"[Risk Assessment Scheduler] Failed to enqueue assessment for company {comp_id}: {e}")
                continue

            enqueued += 1
            print(f"[Risk Assessment Scheduler] Enqueued assessment for company {comp_id}")

        return {"enqueued": enqueued}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=2)
def run_risk_assessment_task(self, company_id: str) -> dict:
    """
    Compute and store a risk assessment for a single company.

    This task is enqueued by the dispatcher or can be called directly.
    It computes scores across all 5 dimensions, stores the result in
    risk_assessment_history and upserts risk_assessment_snapshots.
    Does NOT call generate_recommendations (expensive Gemini call).
    """
    print(f"[Worker] Starting risk assessment for company {company_id}")

    try:
        result = asyncio.run(_run_assessment(company_id))

        publish_task_complete(
            channel=f"company:{company_id}",
            task_type="risk_assessment",
            entity_id=company_id,
            result=result,
        )

        print(f"[Worker] Completed risk assessment for company {company_id}: score={result['overall_score']} band={result['overall_band']}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Worker] Failed risk assessment for company {company_id}: {e}")

        publish_task_error(
            channel=f"company:{company_id}",
            task_type="risk_assessment",
            entity_id=company_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=120 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=1)
def enqueue_scheduled_risk_assessments(self) -> dict:
    """
    Dispatcher task: find companies due for risk assessment and enqueue individual tasks.

    Triggered on every worker startup via the worker_ready signal.
    Limits to 3 companies per dispatch by default (configurable via scheduler_settings).
    """
    print("[Risk Assessment Scheduler] Checking for due risk assessments...")

    try:
        result = asyncio.run(_enqueue_due_assessments())
        print(f"[Risk Assessment Scheduler] Enqueued {result['enqueued']} assessments")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Risk Assessment Scheduler] Failed to enqueue assessments: {e}")
        raise self.retry(exc=e, countdown=60)
