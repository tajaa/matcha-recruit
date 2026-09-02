"""Celery application configuration."""

import logging
import os
from celery import Celery
from celery.signals import worker_ready, task_failure, worker_process_init
from dotenv import load_dotenv

# Load environment variables for worker process
load_dotenv()

logger = logging.getLogger(__name__)

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
        "app.workers.tasks.vertical_coverage_sweep",
        "app.workers.tasks.location_fips_backfill",
        "app.workers.tasks.risk_assessment",
        "app.workers.tasks.healthcare_research",
        "app.workers.tasks.research_browse",
        "app.workers.tasks.discipline_expiry",
        "app.workers.tasks.discipline_policy_sweep",
        "app.workers.tasks.auto_archive",
        "app.workers.tasks.newsletter_scheduler",
        "app.workers.tasks.hr_news_fetch",
        "app.workers.tasks.training_cadence",
        "app.workers.tasks.mention_email",
        "app.workers.tasks.handbook_audit",
        "app.workers.tasks.broker_risk_alerts",
        "app.workers.tasks.broker_milestones",
        "app.workers.tasks.benefit_eligibility_sync",
        "app.workers.tasks.benefit_enrollment_notifications",
        "app.workers.tasks.cappe_booking_reminders",
        "app.workers.tasks.cappe_campaign_send",
        "app.workers.tasks.cappe_collab_auto_approve",
        "app.workers.tasks.cappe_domain_finalize",
        "app.workers.tasks.cba_clause_extraction",
        "app.workers.tasks.grievance_deadline_alerts",
        "app.workers.tasks.ir_deadline_alerts",
        "app.workers.tasks.hr_proactive_push",
        "app.workers.tasks.scope_registry",
        "app.workers.tasks.source_snapshots",
        "app.workers.tasks.debug_error",
        "app.workers.tasks.huume_code",
        "app.workers.tasks.project_agent",
        "app.workers.tasks.sales_intake_poll",
        "app.workers.tasks.pos_sales_sync",
        "app.workers.tasks.schedule_eligibility",
        "app.workers.tasks.schedule_warning_events",
        "app.workers.tasks.schedule_break_refresh",
        "app.workers.tasks.schedule_daily_digest",
        "app.workers.tasks.schedule_request_notifications",
        "app.workers.tasks.schedule_auto_generation",
        "app.workers.tasks.inventory_waste_sweeps",
        "app.workers.tasks.tellus_shoutout_scan",
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


def _scheduler_flags(task_keys: list) -> dict:
    """Batch version of _is_scheduler_enabled — one round-trip for the whole
    worker-ready dispatch instead of one per task."""
    import asyncio
    from app.workers.utils import get_db_connection

    async def _check():
        conn = await get_db_connection()
        try:
            rows = await conn.fetch(
                "SELECT task_key, enabled FROM scheduler_settings WHERE task_key = ANY($1::text[])",
                task_keys,
            )
            return {row["task_key"]: row["enabled"] for row in rows}
        except Exception:
            return {}
        finally:
            await conn.close()

    return asyncio.run(_check())


# (task_key, module_path, callable_name) — every entry is dispatched via
# `.delay()` when its scheduler_settings row is enabled. task_key is the
# scheduler_settings primary key; module/callable are imported lazily at
# dispatch time so a broken task module can't block the rest of the batch.
_SCHEDULED_TASKS = [
    ("schedule_eligibility", "app.workers.tasks.schedule_eligibility", "run_schedule_eligibility"),
    ("structured_data_fetch", "app.workers.tasks.structured_data_fetch", "fetch_structured_data_sources"),
    ("compliance_checks", "app.workers.tasks.compliance_checks", "enqueue_scheduled_compliance_checks"),
    ("deadline_escalation", "app.workers.tasks.compliance_checks", "run_deadline_escalation"),
    ("property_cat_refresh", "app.workers.tasks.property_cat_refresh", "refresh_property_cat"),
    ("legislation_watch", "app.workers.tasks.legislation_watch", "run_legislation_watch"),
    ("scope_registry_authority", "app.workers.tasks.scope_registry", "sync_all_authority_indexes"),
    ("scope_registry_research", "app.workers.tasks.scope_registry", "run_scheduled_research_cycle"),
    ("pattern_recognition", "app.workers.tasks.pattern_recognition", "run_pattern_recognition"),
    ("leave_deadline_checks", "app.workers.tasks.leave_deadline_checks", "check_leave_deadlines"),
    ("leave_agent_orchestration", "app.workers.tasks.leave_agent_tasks", "run_leave_agent_orchestration"),
    ("onboarding_reminders", "app.workers.tasks.onboarding_reminders", "run_onboarding_reminders"),
    ("compliance_action_reminders", "app.workers.tasks.compliance_action_reminders", "run_compliance_action_reminders"),
    ("legal_deadline_reminders", "app.workers.tasks.legal_deadline_reminders", "run_legal_deadline_reminders"),
    ("handbook_freshness", "app.workers.tasks.handbook_freshness", "run_handbook_freshness_checks"),
    ("coi_expiry", "app.workers.tasks.coi_expiry", "run_coi_expiry_sweep"),
    ("vertical_coverage_sweep", "app.workers.tasks.vertical_coverage_sweep", "run_vertical_coverage_sweep"),
    ("location_fips_backfill", "app.workers.tasks.location_fips_backfill", "run_location_fips_backfill"),
    ("risk_assessment", "app.workers.tasks.risk_assessment", "enqueue_scheduled_risk_assessments"),
    ("discipline_expiry", "app.workers.tasks.discipline_expiry", "run_discipline_expiry"),
    ("discipline_policy_sweep", "app.workers.tasks.discipline_policy_sweep", "run_discipline_policy_sweep"),
    ("grievance_deadline_alerts", "app.workers.tasks.grievance_deadline_alerts", "run_grievance_deadline_alerts"),
    ("hr_proactive_push", "app.workers.tasks.hr_proactive_push", "run_hr_proactive_push"),
    ("ir_deadline_alerts", "app.workers.tasks.ir_deadline_alerts", "run_ir_deadline_alerts"),
    # Fires on every worker restart; the task itself declines unless the last
    # scheduled run is older than MIN_SCHEDULED_INTERVAL_DAYS.
    ("compliance_evals", "app.workers.tasks.compliance_evals", "run_scheduled_compliance_evals"),
    ("auto_archive", "app.workers.tasks.auto_archive", "run_auto_archive"),
    ("newsletter_scheduler", "app.workers.tasks.newsletter_scheduler", "run_newsletter_scheduler"),
    ("hr_news_fetch", "app.workers.tasks.hr_news_fetch", "run_hr_news_fetch"),
    ("training_cadence", "app.workers.tasks.training_cadence", "run_training_cadence"),
    ("broker_risk_alerts", "app.workers.tasks.broker_risk_alerts", "run_broker_risk_alerts"),
    ("broker_milestones", "app.workers.tasks.broker_milestones", "run_broker_milestones"),
    ("benefit_eligibility_sync", "app.workers.tasks.benefit_eligibility_sync", "run_benefit_eligibility_sync"),
    ("benefit_enrollment_notifications", "app.workers.tasks.benefit_enrollment_notifications", "run_benefit_enrollment_notifications"),
    ("sales_intake_poll", "app.workers.tasks.sales_intake_poll", "run_sales_intake_poll"),
    ("pos_sales_sync", "app.workers.tasks.pos_sales_sync", "run_pos_sales_sync"),
    ("schedule_warning_events", "app.workers.tasks.schedule_warning_events", "reconcile_schedule_warning_events_task"),
    ("schedule_daily_digest", "app.workers.tasks.schedule_daily_digest", "send_schedule_daily_digest"),
    ("schedule_request_notifications", "app.workers.tasks.schedule_request_notifications", "recover_schedule_request_notifications"),
    ("inventory_expiry_sweep", "app.workers.tasks.inventory_waste_sweeps", "run_inventory_expiry_sweep"),
    ("inventory_waste_digest", "app.workers.tasks.inventory_waste_sweeps", "run_inventory_waste_digest"),
    ("inventory_par_sweep", "app.workers.tasks.inventory_waste_sweeps", "run_inventory_par_sweep"),
    ("tellus_shoutout_scan", "app.workers.tasks.tellus_shoutout_scan", "run_tellus_shoutout_scan"),
    ("cappe_booking_reminders", "app.workers.tasks.cappe_booking_reminders", "run_cappe_booking_reminders"),
    ("cappe_domain_renewals", "app.workers.tasks.cappe_domain_renewals", "run_cappe_domain_renewals"),
    ("cappe_comp_expiry", "app.workers.tasks.cappe_comp_expiry", "run_cappe_comp_expiry"),
    ("cappe_collab_auto_approve", "app.workers.tasks.cappe_collab_auto_approve", "run_cappe_collab_auto_approve"),
    ("cappe_domain_finalize", "app.workers.tasks.cappe_domain_finalize", "run_cappe_domain_finalize"),
]


@worker_ready.connect
def on_worker_ready(**kwargs):
    """Auto-dispatch scheduled compliance checks on every worker startup.

    The systemd timer restarts the worker every 15 minutes, so this
    effectively runs the dispatcher on a 15-minute schedule without
    needing celery-beat infrastructure.
    """
    import importlib

    from app.workers.tasks.er_document_processing import reset_stale_er_documents

    # Not scheduler-gated: a single cheap, idempotent UPDATE that repairs rows
    # a previous worker death stranded in 'processing'. Gating it behind a
    # default-disabled scheduler_settings row would defeat its purpose.
    reset_stale_er_documents.delay()
    # A killed worker is not redelivered (acks_late without reject-on-lost), so
    # leave a clear terminal audit row rather than permanently blocking a
    # project from another @huume attempt.
    try:
        from app.workers.tasks.huume_code import reconcile_stale_runs
        reconcile_stale_runs.delay()
    except Exception:
        logger.exception("[Worker] Failed to enqueue Huume-code reconciliation")
    try:
        from app.workers.tasks.project_agent import reconcile_stale_runs as reconcile_project_agent_runs
        reconcile_project_agent_runs.delay()
    except Exception:
        logger.exception("[Worker] Failed to enqueue project-agent reconciliation")
    try:
        from app.workers.tasks.schedule_break_refresh import recover_stale_employee_schedule_breaks
        recover_stale_employee_schedule_breaks.delay()
    except Exception:
        logger.exception("[Worker] Failed to enqueue schedule-break recovery")

    task_keys = [key for key, _, _ in _SCHEDULED_TASKS]
    flags = _scheduler_flags(task_keys)

    dispatched, disabled, failed = [], [], []
    for task_key, module_path, callable_name in _SCHEDULED_TASKS:
        if not flags.get(task_key, False):
            disabled.append(task_key)
            continue
        try:
            module = importlib.import_module(module_path)
            getattr(module, callable_name).delay()
            dispatched.append(task_key)
        except Exception:
            failed.append(task_key)
            logger.exception("[Worker] Failed to dispatch scheduled task %s", task_key)

    logger.info(
        "[Worker] scheduler dispatch — dispatched=%s disabled=%s failed=%s",
        ",".join(dispatched) or "none",
        ",".join(disabled) or "none",
        ",".join(failed) or "none",
    )


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
        logger.info("[Worker] Settings loaded")
    except Exception:
        logger.exception("[Worker] Failed to load settings")

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
        logger.info("[Worker] Server error reporter installed")
    except Exception:
        # Can't rely on the DB handler here — it's what failed to install.
        logger.exception("[Worker] Failed to install error reporter")


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
    except Exception:
        logger.exception("[Worker] Failed to report task failure")
