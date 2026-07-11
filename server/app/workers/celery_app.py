"""Celery application configuration."""

import os
from celery import Celery
from celery.signals import worker_ready, task_failure, worker_process_init
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
        "app.workers.tasks.er_document_processing",
        "app.workers.tasks.er_analysis",
        "app.workers.tasks.compliance_checks",
        "app.workers.tasks.legislation_watch",
        "app.workers.tasks.pattern_recognition",
        "app.workers.tasks.structured_data_fetch",
        "app.workers.tasks.leave_deadline_checks",
        "app.workers.tasks.leave_agent_tasks",
        "app.workers.tasks.onboarding_reminders",
        "app.workers.tasks.compliance_action_reminders",
        "app.workers.tasks.legal_deadline_reminders",
        "app.workers.tasks.handbook_freshness",
        "app.workers.tasks.coi_expiry",
        "app.workers.tasks.risk_assessment",
        "app.workers.tasks.healthcare_research",
        "app.workers.tasks.research_browse",
        "app.workers.tasks.discipline_expiry",
        "app.workers.tasks.auto_archive",
        "app.workers.tasks.newsletter_scheduler",
        "app.workers.tasks.hr_news_fetch",
        "app.workers.tasks.training_cadence",
        "app.workers.tasks.mention_email",
        "app.workers.tasks.handbook_audit",
        "app.workers.tasks.broker_risk_alerts",
        "app.workers.tasks.broker_milestones",
        "app.workers.tasks.benefit_eligibility_sync",
        "app.workers.tasks.cappe_booking_reminders",
        "app.workers.tasks.cappe_campaign_send",
        "app.workers.tasks.cba_clause_extraction",
        "app.workers.tasks.grievance_deadline_alerts",
        "app.workers.tasks.scope_registry",
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
    from app.workers.tasks.er_document_processing import reset_stale_er_documents
    from app.workers.tasks.legislation_watch import run_legislation_watch
    from app.workers.tasks.leave_agent_tasks import run_leave_agent_orchestration
    from app.workers.tasks.onboarding_reminders import run_onboarding_reminders
    from app.workers.tasks.pattern_recognition import run_pattern_recognition
    from app.workers.tasks.structured_data_fetch import fetch_structured_data_sources

    # Not scheduler-gated: a single cheap, idempotent UPDATE that repairs rows
    # a previous worker death stranded in 'processing'. Gating it behind a
    # default-disabled scheduler_settings row would defeat its purpose.
    reset_stale_er_documents.delay()

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

    if _is_scheduler_enabled("property_cat_refresh"):
        from app.workers.tasks.property_cat_refresh import refresh_property_cat
        refresh_property_cat.delay()
    else:
        print("[Worker] Property cat refresh scheduler is disabled, skipping.")

    if _is_scheduler_enabled("legislation_watch"):
        run_legislation_watch.delay()
    else:
        print("[Worker] Legislation watch scheduler is disabled, skipping.")

    if _is_scheduler_enabled("scope_registry_authority"):
        from app.workers.tasks.scope_registry import sync_all_authority_indexes
        sync_all_authority_indexes.delay()
    else:
        print("[Worker] Scope registry authority sync scheduler is disabled, skipping.")

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

    if _is_scheduler_enabled("onboarding_reminders"):
        run_onboarding_reminders.delay()
    else:
        print("[Worker] Onboarding reminders scheduler is disabled, skipping.")

    from app.workers.tasks.compliance_action_reminders import run_compliance_action_reminders

    if _is_scheduler_enabled("compliance_action_reminders"):
        run_compliance_action_reminders.delay()
    else:
        print("[Worker] Compliance action reminders scheduler is disabled, skipping.")

    from app.workers.tasks.legal_deadline_reminders import run_legal_deadline_reminders

    if _is_scheduler_enabled("legal_deadline_reminders"):
        run_legal_deadline_reminders.delay()
    else:
        print("[Worker] Legal deadline reminders scheduler is disabled, skipping.")

    from app.workers.tasks.handbook_freshness import run_handbook_freshness_checks

    if _is_scheduler_enabled("handbook_freshness"):
        run_handbook_freshness_checks.delay()
    else:
        print("[Worker] Handbook freshness checks scheduler is disabled, skipping.")

    from app.workers.tasks.coi_expiry import run_coi_expiry_sweep

    if _is_scheduler_enabled("coi_expiry"):
        run_coi_expiry_sweep.delay()
    else:
        print("[Worker] COI expiry scheduler is disabled, skipping.")

    from app.workers.tasks.risk_assessment import enqueue_scheduled_risk_assessments

    if _is_scheduler_enabled("risk_assessment"):
        enqueue_scheduled_risk_assessments.delay()
    else:
        print("[Worker] Risk assessment scheduler is disabled, skipping.")

    from app.workers.tasks.discipline_expiry import run_discipline_expiry

    if _is_scheduler_enabled("discipline_expiry"):
        run_discipline_expiry.delay()
    else:
        print("[Worker] Discipline expiry scheduler is disabled, skipping.")

    from app.workers.tasks.grievance_deadline_alerts import run_grievance_deadline_alerts

    if _is_scheduler_enabled("grievance_deadline_alerts"):
        run_grievance_deadline_alerts.delay()
    else:
        print("[Worker] Grievance deadline alerts scheduler is disabled, skipping.")

    from app.workers.tasks.compliance_evals import run_scheduled_compliance_evals

    # Fires on every worker restart (hourly cron); the task itself declines unless
    # the last scheduled run is older than MIN_SCHEDULED_INTERVAL_DAYS.
    if _is_scheduler_enabled("compliance_evals"):
        run_scheduled_compliance_evals.delay()
    else:
        print("[Worker] Compliance evals scheduler is disabled, skipping.")

    from app.workers.tasks.auto_archive import run_auto_archive

    if _is_scheduler_enabled("auto_archive"):
        run_auto_archive.delay()
    else:
        print("[Worker] Auto-archive scheduler is disabled, skipping.")

    from app.workers.tasks.newsletter_scheduler import run_newsletter_scheduler

    if _is_scheduler_enabled("newsletter_scheduler"):
        run_newsletter_scheduler.delay()
    else:
        print("[Worker] Newsletter scheduler is disabled, skipping.")

    from app.workers.tasks.hr_news_fetch import run_hr_news_fetch

    if _is_scheduler_enabled("hr_news_fetch"):
        run_hr_news_fetch.delay()
    else:
        print("[Worker] HR news fetch scheduler is disabled, skipping.")

    from app.workers.tasks.training_cadence import run_training_cadence

    if _is_scheduler_enabled("training_cadence"):
        run_training_cadence.delay()
    else:
        print("[Worker] Training cadence scheduler is disabled, skipping.")

    from app.workers.tasks.broker_risk_alerts import run_broker_risk_alerts

    if _is_scheduler_enabled("broker_risk_alerts"):
        run_broker_risk_alerts.delay()
    else:
        print("[Worker] Broker risk alerts scheduler is disabled, skipping.")

    from app.workers.tasks.broker_milestones import run_broker_milestones

    if _is_scheduler_enabled("broker_milestones"):
        run_broker_milestones.delay()
    else:
        print("[Worker] Broker milestones scheduler is disabled, skipping.")

    from app.workers.tasks.benefit_eligibility_sync import run_benefit_eligibility_sync

    if _is_scheduler_enabled("benefit_eligibility_sync"):
        run_benefit_eligibility_sync.delay()
    else:
        print("[Worker] Benefit eligibility sync scheduler is disabled, skipping.")

    from app.workers.tasks.cappe_booking_reminders import run_cappe_booking_reminders

    if _is_scheduler_enabled("cappe_booking_reminders"):
        run_cappe_booking_reminders.delay()
    else:
        print("[Worker] Cappe booking reminders scheduler is disabled, skipping.")

    from app.workers.tasks.cappe_domain_renewals import run_cappe_domain_renewals

    if _is_scheduler_enabled("cappe_domain_renewals"):
        run_cappe_domain_renewals.delay()
    else:
        print("[Worker] Cappe domain renewals scheduler is disabled, skipping.")


# ── Server error reporter integration ───────────────────────────────────────
# Every Celery worker installs the root-logger DB handler so logger.error/exception
# calls inside task code persist to server_error_reports. task_failure captures
# task exceptions with full traceback + task id context.

@worker_process_init.connect
def _install_error_reporter(**kwargs):
    # Bootstrap settings for the worker process BEFORE anything else.
    # Without this, the first task that touches get_settings() (storage,
    # gemini client, stripe service, etc.) raises
    # "Settings not initialized. Call load_settings() first." — the failure
    # mode customers see on the handbook audit result page when the worker
    # dies mid-task (storage.get_storage() runs before any per-task
    # load_settings() fallback can fire).
    try:
        from app.config import load_settings
        load_settings()
        print("[Worker] Settings loaded")
    except Exception as e:
        print(f"[Worker] Failed to load settings: {e}")

    # NOTE: deliberately do NOT call app.database.init_pool() here.
    # Celery tasks each run via asyncio.run() which creates a NEW event
    # loop per task; an asyncpg pool bound to one loop can't be reused
    # from another, and the next task would fail with
    # "another operation is in progress" or hang. Worker tasks that need
    # DB access should use workers/utils.get_db_connection (raw asyncpg
    # connection opened inside the task's own loop). The pool stays
    # process-level for FastAPI's lifespan; workers stay pool-free.

    try:
        from app.core.services.error_reporter import install_error_logging
        install_error_logging(source="celery")
        print("[Worker] Server error reporter installed")
    except Exception as e:
        print(f"[Worker] Failed to install error reporter: {e}")


@task_failure.connect
def _on_task_failure(
    sender=None, task_id=None, exception=None, args=None, kwargs=None, traceback=None, einfo=None, **_
):
    try:
        from app.core.services.error_reporter import report_server_error
        task_name = getattr(sender, "name", "unknown")
        tb_str = str(einfo) if einfo else None
        report_server_error(
            kind="celery_task",
            message=f"{task_name} failed: {exception}",
            exception=exception if isinstance(exception, BaseException) else None,
            traceback_str=tb_str,
            source="celery",
            logger_name=task_name,
            context={
                "task_id": task_id,
                "task_name": task_name,
                "args": args,
                "kwargs": kwargs,
            },
        )
    except Exception as e:
        print(f"[Worker] Failed to report task failure: {e}")
