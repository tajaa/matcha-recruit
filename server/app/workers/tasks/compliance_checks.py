"""
Celery tasks for scheduled compliance checks.

These tasks run compliance checks on a schedule via the systemd timer
that restarts the Celery worker every 15 minutes. The worker_ready signal
triggers the dispatcher, which enqueues individual checks for due locations.
"""

import asyncio
from typing import Optional

from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection


async def _run_check(location_id: str, company_id: str, check_type: str = "scheduled") -> dict:
    """Run a compliance check for a single location."""
    from uuid import UUID
    from app.core.services.compliance_service import run_compliance_check_background

    result = await run_compliance_check_background(
        location_id=UUID(location_id),
        company_id=UUID(company_id),
        check_type=check_type,
        allow_live_research=False,
    )
    return result


async def _enqueue_due_checks() -> dict:
    """Find locations due for auto-check and enqueue individual tasks."""
    conn = await get_db_connection()
    try:
        # Check if compliance_checks scheduler is enabled and get max_per_cycle
        # Guard against scheduler_settings table not existing yet (deploy ordering)
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = 'compliance_checks'"
            )
        except Exception:
            sched_row = None

        if sched_row and not sched_row["enabled"]:
            print("[Compliance Scheduler] Scheduler disabled, skipping.")
            return {"enqueued": 0}

        limit = (sched_row["max_per_cycle"] if sched_row and sched_row["max_per_cycle"] and sched_row["max_per_cycle"] > 0 else 2)

        rows = await conn.fetch(
            """
            SELECT bl.id AS location_id, bl.company_id, bl.auto_check_interval_days
            FROM business_locations bl
            WHERE bl.auto_check_enabled = true
              AND bl.is_active = true
              AND (bl.next_auto_check IS NULL OR bl.next_auto_check <= NOW())
            ORDER BY bl.last_compliance_check ASC NULLS FIRST
            LIMIT $1
            """,
            limit,
        )

        enqueued = 0
        for row in rows:
            loc_id = str(row["location_id"])
            comp_id = str(row["company_id"])
            interval = row["auto_check_interval_days"] or 7

            # Enqueue the individual check task, then advance next_auto_check
            try:
                run_compliance_check_task.delay(loc_id, comp_id, "scheduled")
            except Exception as e:
                print(f"[Compliance Scheduler] Failed to enqueue check for location {loc_id}: {e}")
                continue

            await conn.execute(
                """
                UPDATE business_locations
                SET next_auto_check = NOW() + INTERVAL '1 day' * $1
                WHERE id = $2
                """,
                interval, row["location_id"],
            )
            enqueued += 1
            print(f"[Compliance Scheduler] Enqueued check for location {loc_id}")

        return {"enqueued": enqueued}
    finally:
        await conn.close()


async def _run_escalation() -> dict:
    """Run deadline escalation for all companies with upcoming legislation."""
    from uuid import UUID
    from app.core.services.compliance_service import escalate_upcoming_deadlines

    conn = await get_db_connection()
    try:
        # Get distinct company IDs with active upcoming legislation
        company_rows = await conn.fetch(
            """
            SELECT DISTINCT company_id FROM upcoming_legislation
            WHERE current_status NOT IN ('effective', 'dismissed')
              AND expected_effective_date IS NOT NULL
            """,
        )

        total_escalated = 0
        for row in company_rows:
            escalated = await escalate_upcoming_deadlines(conn, row["company_id"])
            total_escalated += escalated
            if escalated > 0:
                publish_task_complete(
                    channel=f"company:{row['company_id']}",
                    task_type="compliance_escalation",
                    entity_id=str(row["company_id"]),
                    result={"escalated": escalated},
                )

        return {"companies_checked": len(company_rows), "total_escalated": total_escalated}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=2)
def run_compliance_check_task(
    self,
    location_id: str,
    company_id: str,
    check_type: str = "scheduled",
) -> dict:
    """
    Run a compliance check for a single location.

    This task is enqueued by the dispatcher or can be called directly.
    It runs the full compliance check flow including:
    - Sync from jurisdiction repository
    - Change detection and verification
    - Upcoming legislation scan from repository-backed data
    - Deadline escalation
    """
    print(f"[Worker] Starting compliance check for location {location_id} (type: {check_type})")

    try:
        result = asyncio.run(_run_check(location_id, company_id, check_type))

        # Notify frontend via Redis pub/sub
        publish_task_complete(
            channel=f"company:{company_id}",
            task_type="compliance_check",
            entity_id=location_id,
            result=result,
        )

        print(f"[Worker] Completed compliance check for location {location_id}: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Worker] Failed compliance check for location {location_id}: {e}")

        publish_task_error(
            channel=f"company:{company_id}",
            task_type="compliance_check",
            entity_id=location_id,
            error=str(e),
        )

        raise self.retry(exc=e, countdown=120 * (self.request.retries + 1))


@celery_app.task(bind=True, max_retries=1)
def enqueue_scheduled_compliance_checks(self) -> dict:
    """
    Dispatcher task: find locations due for auto-check and enqueue individual tasks.

    Triggered on every worker startup via the worker_ready signal.
    Limits to 2 locations per dispatch to stay within the 5-minute worker window.
    """
    print("[Compliance Scheduler] Checking for due compliance checks...")

    try:
        result = asyncio.run(_enqueue_due_checks())
        print(f"[Compliance Scheduler] Enqueued {result['enqueued']} checks")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Compliance Scheduler] Failed to enqueue checks: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True, max_retries=1)
def run_deadline_escalation(self) -> dict:
    """
    Lightweight task: re-evaluate deadline severities for upcoming legislation.

    No Gemini calls — just DB queries to update alert severities based on
    how close effective dates are. Runs on every worker startup.
    """
    print("[Compliance Escalation] Running deadline escalation...")

    try:
        result = asyncio.run(_run_escalation())
        print(f"[Compliance Escalation] Escalated {result['total_escalated']} deadlines across {result['companies_checked']} companies")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Compliance Escalation] Failed: {e}")
        raise self.retry(exc=e, countdown=60)
