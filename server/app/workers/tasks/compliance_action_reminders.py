"""
Celery task for compliance action reminders.

Runs daily; emails assigned owners when their compliance action due date is approaching.
"""

import asyncio
from datetime import date, timedelta

from ..celery_app import celery_app
from ..utils import get_db_connection

# How many days ahead to look for upcoming deadlines
REMINDER_LOOKAHEAD_DAYS = 2


async def _run_compliance_action_reminders() -> dict:
    from app.core.services.email import EmailService
    from app.config import get_settings

    conn = await get_db_connection()
    try:
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = 'compliance_action_reminders'"
            )
        except Exception:
            sched_row = None

        if not sched_row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not sched_row["enabled"]:
            print("[Compliance Action Reminders] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        max_per_cycle = sched_row["max_per_cycle"] or 100

        today = date.today()
        lookahead = today + timedelta(days=REMINDER_LOOKAHEAD_DAYS)

        # Find compliance alerts with an assigned owner and approaching action_due_date
        # metadata->>'action_due_date' and metadata->>'action_owner_id' are stored in JSONB
        rows = await conn.fetch(
            """
            SELECT
                ca.id AS alert_id,
                ca.metadata,
                ca.company_id,
                comp.name AS company_name,
                u.email AS owner_email,
                COALESCE(cl.name, u.email) AS owner_name,
                leg.title AS legislation_title,
                bl.name AS location_name
            FROM compliance_alerts ca
            JOIN companies comp ON comp.id = ca.company_id
            LEFT JOIN business_locations bl ON bl.id = ca.location_id
            LEFT JOIN compliance_legislation leg ON leg.id = ca.legislation_id
            LEFT JOIN users u ON u.id = (ca.metadata->>'action_owner_id')::uuid
            LEFT JOIN clients cl ON cl.user_id = u.id AND cl.company_id = ca.company_id
            WHERE ca.status != 'actioned'
              AND (ca.metadata->>'action_owner_id') IS NOT NULL
              AND (ca.metadata->>'action_due_date') IS NOT NULL
              AND (ca.metadata->>'action_due_date')::date >= $1
              AND (ca.metadata->>'action_due_date')::date <= $2
              AND (
                ca.metadata->>'reminder_sent_at' IS NULL
                OR (ca.metadata->>'reminder_sent_at')::date < $1
              )
            ORDER BY (ca.metadata->>'action_due_date')::date ASC
            LIMIT $3
            """,
            today,
            lookahead,
            max_per_cycle,
        )

        if not rows:
            return {"checked": 0, "sent": 0}

        settings = get_settings()
        email_service = EmailService(settings)

        sent = 0
        failed = 0

        for row in rows:
            if not row["owner_email"]:
                continue

            due_date_str = row["metadata"].get("action_due_date") if row["metadata"] else None
            if not due_date_str:
                continue

            try:
                action_due = date.fromisoformat(due_date_str)
            except ValueError:
                continue

            days_until = (action_due - today).days

            try:
                ok = await email_service.send_compliance_action_reminder(
                    to_email=row["owner_email"],
                    to_name=row["owner_name"] or row["owner_email"],
                    company_name=row["company_name"] or "Your Company",
                    legislation_title=row["legislation_title"] or "Compliance requirement",
                    location_name=row["location_name"] or "Unknown location",
                    action_due_date=action_due,
                    days_until_due=days_until,
                )
                if ok:
                    # Stamp reminder_sent_at so we don't re-send today
                    await conn.execute(
                        """
                        UPDATE compliance_alerts
                        SET metadata = jsonb_set(
                            COALESCE(metadata, '{}'::jsonb),
                            '{reminder_sent_at}',
                            to_jsonb($1::text)
                        )
                        WHERE id = $2
                        """,
                        today.isoformat(),
                        row["alert_id"],
                    )
                    sent += 1
                else:
                    failed += 1
            except Exception as exc:
                print(f"[Compliance Action Reminders] Error sending to {row['owner_email']}: {exc}")
                failed += 1

        return {"checked": len(rows), "sent": sent, "failed": failed}

    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_compliance_action_reminders(self) -> dict:
    """Scan compliance alerts and send reminders to assigned owners near their deadline."""
    print("[Compliance Action Reminders] Running...")

    try:
        result = asyncio.run(_run_compliance_action_reminders())
        print(f"[Compliance Action Reminders] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[Compliance Action Reminders] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
