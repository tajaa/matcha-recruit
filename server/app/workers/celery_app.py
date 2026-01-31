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
    enqueue_scheduled_compliance_checks.delay()
    run_deadline_escalation.delay()
