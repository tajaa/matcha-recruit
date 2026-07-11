"""Celery task for jurisdiction-data eval runs.

Routed here rather than to `BackgroundTasks` whenever a suite touches the network
(authority fetches every distinct citation URL) so a slow regulator host cannot
pin a uvicorn worker.

Scheduling note: there is no celery-beat in this repo — an hourly host cron
restarts the worker, which re-fires `@worker_ready`. The `scheduler_settings` row
is only an on/off switch, so a scheduled run must decline on its own if one
already completed recently. `MIN_SCHEDULED_INTERVAL_DAYS` is that guard; without
it, enabling the row would run a full network sweep every hour.
"""

import asyncio
from typing import List, Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error

MIN_SCHEDULED_INTERVAL_DAYS = 6
CHANNEL = "admin:compliance_evals"


async def _scheduled_run_is_due() -> bool:
    from app.workers.utils import get_db_connection

    conn = await get_db_connection()
    try:
        recent = await conn.fetchval(
            """
            SELECT 1 FROM compliance_eval_runs
            WHERE trigger_source = 'scheduled'
              AND status = 'completed'
              AND finished_at > NOW() - ($1 || ' days')::interval
            LIMIT 1
            """,
            str(MIN_SCHEDULED_INTERVAL_DAYS),
        )
        return recent is None
    except Exception:
        return False
    finally:
        await conn.close()


@celery_app.task(name="compliance_evals.run", max_retries=0, time_limit=3300)
def run_compliance_evals(
    suites: Optional[List[str]] = None,
    jurisdiction_ids: Optional[List[str]] = None,
    industries: Optional[List[str]] = None,
    triggered_by: Optional[str] = None,
    trigger_source: str = "manual",
    run_id: Optional[str] = None,
):
    """Execute eval suites and persist a scorecard."""
    from uuid import UUID

    from app.core.services.compliance_evals import run_evals

    async def _run():
        if trigger_source == "scheduled" and not await _scheduled_run_is_due():
            return {"status": "skipped", "reason": "a scheduled run completed recently"}
        rid = await run_evals(
            suites=suites,
            jurisdiction_ids=jurisdiction_ids,
            industries=industries,
            triggered_by=UUID(triggered_by) if triggered_by else None,
            trigger_source=trigger_source,
            run_id=UUID(run_id) if run_id else None,
        )
        return {"status": "completed", "run_id": str(rid)}

    try:
        result = asyncio.run(_run())
    except Exception as exc:
        publish_task_error(CHANNEL, "compliance_evals", run_id or "", str(exc))
        raise

    publish_task_complete(CHANNEL, "compliance_evals", result.get("run_id", run_id or ""), result)
    return result


@celery_app.task(name="compliance_evals.run_scheduled", max_retries=0, time_limit=3300)
def run_scheduled_compliance_evals():
    """Weekly sweep entrypoint — all deterministic suites over every jurisdiction."""
    return run_compliance_evals(
        suites=["completeness", "tagging", "golden", "authority", "baseline"],
        trigger_source="scheduled",
    )
