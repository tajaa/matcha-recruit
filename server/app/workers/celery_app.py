"""Celery application configuration."""

import os
from celery import Celery
from celery.signals import worker_ready
from dotenv import load_dotenv

# Load environment variables for worker process
load_dotenv()

# Get Redis URL from environment
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
celery_broker_url = os.getenv("CELERY_BROKER_URL", redis_url)
celery_result_backend = os.getenv("CELERY_RESULT_BACKEND", redis_url)

celery_app = Celery(
    "matcha",
    broker=celery_broker_url,
    backend=celery_result_backend,
    include=[
        "app.workers.tasks.interview_analysis",
        "app.workers.tasks.matching",
        "app.workers.tasks.culture_aggregation",
        "app.workers.tasks.er_document_processing",
        "app.workers.tasks.er_analysis",
        "app.workers.tasks.compliance_checks",
        "app.workers.tasks.legislation_watch",
        "app.workers.tasks.pattern_recognition",
        "app.workers.tasks.structured_data_fetch",
        "app.workers.tasks.leave_deadline_checks",
        "app.workers.tasks.leave_agent_tasks",
        "app.workers.tasks.resume_screening",
        "app.workers.tasks.project_close",
    ],
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # Soft limit 9 minutes

    # Worker settings
    worker_prefetch_multiplier=1,  # Process one task at a time
    task_acks_late=True,  # Acknowledge after completion for reliability

    # Result settings
    result_expires=3600,  # Results expire after 1 hour

    # Retry settings
    task_default_retry_delay=60,  # 1 minute between retries
    task_max_retries=3,
)


def _is_scheduler_enabled(task_key: str) -> bool:
    """Check if a scheduler task is enabled in the database.

    Returns False if no row exists or table doesn't exist (safe default).
    Tasks must be explicitly enabled in scheduler_settings after migration.
    """
    import asyncio
    from app.workers.utils import get_db_connection

    async def _check():
        conn = await get_db_connection()
        try:
            row = await conn.fetchrow(
                "SELECT enabled FROM scheduler_settings WHERE task_key = $1",
                task_key,
            )
            # Default to disabled if no row (table may not exist or not seeded)
            return row["enabled"] if row else False
        except Exception:
            # Table doesn't exist or other DB error - default to disabled
            return False
        finally:
            await conn.close()

    return asyncio.run(_check())


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Auto-dispatch scheduled compliance checks on every worker startup.

    The systemd timer restarts the worker every 15 minutes, so this
    effectively runs the dispatcher on a 15-minute schedule without
    needing celery-beat infrastructure.
    """
    from app.workers.tasks.compliance_checks import (
        enqueue_scheduled_compliance_checks,
        run_deadline_escalation,
    )
    from app.workers.tasks.legislation_watch import run_legislation_watch
    from app.workers.tasks.leave_agent_tasks import run_leave_agent_orchestration
    from app.workers.tasks.pattern_recognition import run_pattern_recognition
    from app.workers.tasks.structured_data_fetch import fetch_structured_data_sources

    if _is_scheduler_enabled("structured_data_fetch"):
        fetch_structured_data_sources.delay()
    else:
        print("[Worker] Structured data fetch scheduler is disabled, skipping.")

    if _is_scheduler_enabled("compliance_checks"):
        enqueue_scheduled_compliance_checks.delay()
    else:
        print("[Worker] Compliance checks scheduler is disabled, skipping.")

    if _is_scheduler_enabled("deadline_escalation"):
        run_deadline_escalation.delay()
    else:
        print("[Worker] Deadline escalation scheduler is disabled, skipping.")

    if _is_scheduler_enabled("legislation_watch"):
        run_legislation_watch.delay()
    else:
        print("[Worker] Legislation watch scheduler is disabled, skipping.")

    if _is_scheduler_enabled("pattern_recognition"):
        run_pattern_recognition.delay()
    else:
        print("[Worker] Pattern recognition scheduler is disabled, skipping.")

    from app.workers.tasks.leave_deadline_checks import check_leave_deadlines

    if _is_scheduler_enabled("leave_deadline_checks"):
        check_leave_deadlines.delay()
    else:
        print("[Worker] Leave deadline checks scheduler is disabled, skipping.")

    if _is_scheduler_enabled("leave_agent_orchestration"):
        run_leave_agent_orchestration.delay()
    else:
        print("[Worker] Leave agent orchestration scheduler is disabled, skipping.")

    from app.workers.tasks.project_close import check_project_deadlines

    if _is_scheduler_enabled("project_deadline_checks"):
        check_project_deadlines.delay()
    else:
        print("[Worker] Project deadline checks scheduler is disabled, skipping.")
