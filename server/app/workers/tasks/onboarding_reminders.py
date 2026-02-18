"""
Celery task for onboarding reminders and escalation emails.

Runs on worker startup when the onboarding_reminders scheduler is enabled.
"""

import asyncio
from datetime import datetime, timezone

from app.matcha.services.onboarding_reminder_logic import (
    DEFAULT_MAX_PER_CYCLE,
    ReminderSettings,
    _build_settings,
    _full_name,
    _is_business_day,
    _is_quiet_hour,
    _resolve_recipients,
    _resolve_timezone,
    _tier_column,
    determine_reminder_tier,
)
from ..celery_app import celery_app
from ..notifications import publish_task_complete, publish_task_error
from ..utils import get_db_connection

LOOKAHEAD_DAYS = 30

async def _fetch_hr_escalation_emails(conn, company_id) -> tuple[str, ...]:
    rows = await conn.fetch(
        """
        SELECT DISTINCT LOWER(TRIM(email_value)) AS email
        FROM (
            SELECT u.email AS email_value
            FROM clients c
            JOIN users u ON u.id = c.user_id
            WHERE c.company_id = $1

            UNION

            SELECT u2.email AS email_value
            FROM companies comp
            JOIN users u2 ON u2.id = comp.owner_id
            WHERE comp.id = $1
        ) emails
        WHERE email_value IS NOT NULL AND TRIM(email_value) <> ''
        """,
        company_id,
    )

    return tuple(sorted({row["email"] for row in rows if row["email"]}))


async def _load_company_settings(conn, company_id) -> ReminderSettings:
    try:
        row = await conn.fetchrow(
            """
            SELECT
                timezone,
                quiet_hours_start,
                quiet_hours_end,
                business_days,
                reminder_days_before_due,
                escalate_to_manager_after_days,
                escalate_to_hr_after_days,
                hr_escalation_emails,
                email_enabled
            FROM onboarding_notification_settings
            WHERE org_id = $1
            """,
            company_id,
        )
    except Exception:
        row = None
    return _build_settings(row)


async def _claim_tier_slot(conn, task_id, tier: str) -> bool:
    column = _tier_column(tier)
    claimed = await conn.fetchval(
        f"""
        UPDATE employee_onboarding_tasks
        SET {column} = NOW(), updated_at = NOW()
        WHERE id = $1 AND {column} IS NULL
        RETURNING id
        """,
        task_id,
    )
    return bool(claimed)


async def _release_tier_slot(conn, task_id, tier: str) -> None:
    column = _tier_column(tier)
    await conn.execute(
        f"""
        UPDATE employee_onboarding_tasks
        SET {column} = NULL, updated_at = NOW()
        WHERE id = $1
        """,
        task_id,
    )


async def _run_onboarding_reminders() -> dict:
    from app.core.services.email import EmailService

    conn = await get_db_connection()
    try:
        try:
            scheduler_row = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = 'onboarding_reminders'"
            )
        except Exception:
            scheduler_row = None

        if not scheduler_row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not scheduler_row["enabled"]:
            print("[Onboarding Reminders] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        max_per_cycle = scheduler_row["max_per_cycle"] or DEFAULT_MAX_PER_CYCLE
        if max_per_cycle <= 0:
            max_per_cycle = DEFAULT_MAX_PER_CYCLE

        task_rows = await conn.fetch(
            """
            SELECT
                eot.id,
                eot.title,
                eot.due_date,
                eot.is_employee_task,
                eot.assignee_reminded_at,
                eot.manager_reminded_at,
                eot.hr_reminded_at,
                e.org_id,
                c.name AS company_name,
                e.first_name AS employee_first_name,
                e.last_name AS employee_last_name,
                e.email AS employee_work_email,
                e.personal_email AS employee_personal_email,
                mgr.first_name AS manager_first_name,
                mgr.last_name AS manager_last_name,
                mgr.email AS manager_work_email,
                mgr.personal_email AS manager_personal_email
            FROM employee_onboarding_tasks eot
            JOIN employees e ON e.id = eot.employee_id
            JOIN companies c ON c.id = e.org_id
            LEFT JOIN employees mgr ON mgr.id = e.manager_id
            WHERE eot.status = 'pending'
              AND eot.due_date IS NOT NULL
              AND eot.due_date <= CURRENT_DATE + ($1 * INTERVAL '1 day')
            ORDER BY eot.due_date ASC, eot.created_at ASC
            LIMIT $2
            """,
            LOOKAHEAD_DAYS,
            max_per_cycle,
        )

        if not task_rows:
            return {"checked": 0, "sent": 0, "failed": 0, "skipped": 0}

        email_service = EmailService()
        now_utc = datetime.now(timezone.utc)
        company_settings_cache = {}
        hr_email_cache = {}

        sent = 0
        failed = 0
        skipped = 0
        checked = 0

        for row in task_rows:
            checked += 1
            company_id = row["org_id"]

            if company_id not in company_settings_cache:
                company_settings_cache[company_id] = await _load_company_settings(conn, company_id)
            settings = company_settings_cache[company_id]

            if not settings.email_enabled:
                skipped += 1
                continue

            local_now = now_utc.astimezone(_resolve_timezone(settings.timezone_name))
            if not _is_business_day(local_now, settings.business_days):
                skipped += 1
                continue
            if _is_quiet_hour(local_now, settings.quiet_hours_start, settings.quiet_hours_end):
                skipped += 1
                continue

            tier = determine_reminder_tier(row["due_date"], local_now.date(), settings)
            if not tier:
                skipped += 1
                continue

            tier_column = _tier_column(tier)
            if row[tier_column] is not None:
                skipped += 1
                continue

            hr_emails = settings.hr_escalation_emails
            if tier == "hr" and not hr_emails:
                if company_id not in hr_email_cache:
                    hr_email_cache[company_id] = await _fetch_hr_escalation_emails(conn, company_id)
                hr_emails = hr_email_cache[company_id]

            recipients = _resolve_recipients(row, tier, hr_emails)
            if not recipients:
                skipped += 1
                continue

            claimed = await _claim_tier_slot(conn, row["id"], tier)
            if not claimed:
                skipped += 1
                continue

            task_sent_count = 0
            employee_name = _full_name(
                row["employee_first_name"],
                row["employee_last_name"],
                "Employee",
            )
            overdue_days = max((local_now.date() - row["due_date"]).days, 0)

            try:
                for recipient_email, recipient_name in recipients:
                    if tier == "assignee":
                        delivered = await email_service.send_task_reminder(
                            to_email=recipient_email,
                            to_name=recipient_name,
                            company_name=row["company_name"],
                            employee_name=employee_name,
                            task_title=row["title"],
                            due_date=row["due_date"],
                        )
                    else:
                        delivered = await email_service.send_task_escalation(
                            to_email=recipient_email,
                            to_name=recipient_name,
                            company_name=row["company_name"],
                            employee_name=employee_name,
                            task_title=row["title"],
                            due_date=row["due_date"],
                            escalation_target=tier,
                            overdue_days=overdue_days,
                        )

                    if delivered:
                        task_sent_count += 1
            except Exception as exc:
                await _release_tier_slot(conn, row["id"], tier)
                failed += 1
                publish_task_error(
                    channel=f"company:{company_id}",
                    task_type="onboarding_reminders",
                    entity_id=str(row["id"]),
                    error=str(exc),
                )
                continue

            if task_sent_count == 0:
                await _release_tier_slot(conn, row["id"], tier)
                failed += 1
                continue

            sent += task_sent_count
            publish_task_complete(
                channel=f"company:{company_id}",
                task_type="onboarding_reminders",
                entity_id=str(row["id"]),
                result={
                    "tier": tier,
                    "recipients": task_sent_count,
                    "due_date": str(row["due_date"]),
                    "title": row["title"],
                },
            )

        return {
            "checked": checked,
            "sent": sent,
            "failed": failed,
            "skipped": skipped,
        }
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_onboarding_reminders(self) -> dict:
    """Scan onboarding tasks and deliver reminder/escalation notifications."""
    print("[Onboarding Reminders] Running scheduler...")

    try:
        result = asyncio.run(_run_onboarding_reminders())
        print(f"[Onboarding Reminders] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[Onboarding Reminders] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
