"""
Celery tasks for scheduled LeaveAgent orchestration.

This scheduler runs periodic return-to-work and accommodation stall checks.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection


async def _run_leave_agent_orchestration() -> dict:
    """Run the LeaveAgent periodic orchestration cycle."""
    from app.matcha.services.leave_agent import get_leave_agent

    conn = await get_db_connection()
    try:
        # Guard against scheduler table not existing during deploy ordering.
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = 'leave_agent_orchestration'"
            )
        except Exception:
            sched_row = None

        if sched_row and not sched_row["enabled"]:
            print("[Leave Agent] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        max_per_cycle = (
            sched_row["max_per_cycle"]
            if sched_row and sched_row["max_per_cycle"] and sched_row["max_per_cycle"] > 0
            else 20
        )
    finally:
        await conn.close()

    leave_agent = get_leave_agent()
    return await leave_agent.run_scheduled_orchestration(max_per_cycle=max_per_cycle)


@celery_app.task(bind=True, max_retries=1)
def run_leave_agent_orchestration(self) -> dict:
    """Run scheduled leave/accommodation orchestration checks."""
    print("[Leave Agent] Running scheduled orchestration...")

    try:
        result = asyncio.run(_run_leave_agent_orchestration())
        print(f"[Leave Agent] Completed: {result}")
        return {"status": "success", **result}

    except Exception as e:
        print(f"[Leave Agent] Failed: {e}")
        raise self.retry(exc=e, countdown=60)
