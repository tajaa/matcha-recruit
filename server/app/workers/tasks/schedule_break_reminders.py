"""Break-start push reminders, swept every couple of minutes.

The worker has no beat: periodic tasks are dispatched once per hourly restart
(``celery_app.on_worker_ready``). A break reminder has to land within minutes,
so this task re-enqueues itself ``SWEEP_SECONDS`` out after every run.

Every restart dispatches another copy while the previous chain's countdown
message is still queued, so chains would multiply. Each run therefore first
claims ``scheduler_settings.last_run_at``: a run that finds a claim younger than
``_MIN_GAP`` ends WITHOUT re-enqueueing, and the extra chain dies out. A
disabled row ends the chain too; the next restart starts it again once the row
is re-enabled. Correctness never rests on this — each break is deduped in
``break_reminders.send_break_reminder`` — it only keeps the cadence single.
"""

import asyncio
import logging

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled, scheduler_settings_row

logger = logging.getLogger(__name__)

TASK_KEY = "schedule_break_reminders"


def _cadence():
    from app.matcha.services.scheduling.break_reminders import SWEEP_SECONDS

    # Shorter than the countdown so the live chain always re-claims, long
    # enough that a second chain landing inside it finds the slot taken.
    return SWEEP_SECONDS, int(SWEEP_SECONDS * 0.75)


async def _run() -> dict:
    _, min_gap = _cadence()
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, TASK_KEY, default=False):
            return {"skipped": True, "reason": "disabled", "reschedule": False}
        claimed = await conn.fetchval(
            """UPDATE scheduler_settings SET last_run_at = NOW()
               WHERE task_key = $1
                 AND (last_run_at IS NULL OR last_run_at < NOW() - make_interval(secs => $2))
               RETURNING true""",
            TASK_KEY, min_gap,
        )
        if not claimed:
            return {"skipped": True, "reason": "another_chain", "reschedule": False}
        settings = await scheduler_settings_row(conn, TASK_KEY)
        limit = max(1, min(int((settings["max_per_cycle"] if settings else None) or 500), 5_000))
        from app.matcha.services.scheduling.break_reminders import (
            send_due_break_reminders,
        )

        result = await send_due_break_reminders(conn, limit=limit)
        return {**result, "reschedule": True}
    finally:
        await conn.close()


def _reschedule(countdown: int) -> None:
    try:
        run_schedule_break_reminders.apply_async(countdown=countdown)
    except Exception:
        logger.exception("schedule_break_reminders could not re-enqueue; next worker restart resumes it")


@celery_app.task(name="schedule_break_reminders.sweep")
def run_schedule_break_reminders():
    sweep_seconds, _ = _cadence()
    try:
        result = asyncio.run(_run())
    except Exception:
        # A DB blip must not end the cadence until the next hourly restart.
        logger.exception("schedule_break_reminders sweep failed")
        _reschedule(sweep_seconds)
        raise
    if result.pop("reschedule", False):
        _reschedule(sweep_seconds)
    return result
