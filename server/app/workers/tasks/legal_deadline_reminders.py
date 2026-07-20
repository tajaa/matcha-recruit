"""
Celery task for Legal Pilot matter response-deadline reminders.

EEOC position statements, subpoena returns, and audit responses carry hard
due dates. Nudges the matter owner at 14/7/3/1 days out. Deduped via
`legal_matter_audit_log` `deadline_reminder` rows (details carry the day
bucket) — no new table. Gated by the `legal_deadline_reminders`
scheduler_settings row, default disabled (repo convention).
"""

import asyncio
import json
from datetime import date

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

# "Within N days" buckets, narrowest first. One reminder per bucket per
# matter: a matter due in 6 days gets the 7-day nudge (even if the worker
# was down on day 7 exactly), then nothing until it crosses 3.
REMINDER_BUCKETS = (1, 3, 7, 14)


def bucket_for(days_until: int) -> int | None:
    """Smallest bucket covering days_until; None when overdue or beyond 14.
    Pure (unit-tested)."""
    if days_until < 0:
        return None
    for b in REMINDER_BUCKETS:
        if days_until <= b:
            return b
    return None


async def _run_legal_deadline_reminders() -> dict:
    from app.config import get_settings
    from app.core.services.email import EmailService

    conn = await get_db_connection()
    try:
        sched_row = await scheduler_settings_row(conn, "legal_deadline_reminders")

        if not sched_row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not sched_row["enabled"]:
            print("[Legal Deadline Reminders] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        max_per_cycle = sched_row["max_per_cycle"] or 100
        today = date.today()

        rows = await conn.fetch(
            """
            SELECT m.id, m.title, m.matter_type, m.response_deadline, m.deadline_note,
                   comp.name AS company_name, u.email AS owner_email
            FROM legal_matters m
            JOIN companies comp ON comp.id = m.company_id
            LEFT JOIN users u ON u.id = m.created_by
            WHERE m.status = 'active'
              AND m.response_deadline IS NOT NULL
              AND m.response_deadline >= $1
              AND m.response_deadline <= $1 + 14
            ORDER BY m.response_deadline ASC
            LIMIT $2
            """,
            today, max_per_cycle,
        )
        if not rows:
            return {"checked": 0, "sent": 0}

        email_service = EmailService(get_settings())
        sent = 0
        failed = 0

        for row in rows:
            if not row["owner_email"]:
                continue
            days_until = (row["response_deadline"] - today).days
            bucket = bucket_for(days_until)
            if bucket is None:
                continue

            # Dedupe on (bucket, deadline) — keying on bucket alone would
            # permanently silence a bucket after the deadline is moved.
            already = await conn.fetchrow(
                """SELECT 1 FROM legal_matter_audit_log
                    WHERE matter_id = $1 AND action = 'deadline_reminder'
                      AND details->>'bucket' = $2 AND details->>'deadline' = $3""",
                row["id"], str(bucket), row["response_deadline"].isoformat(),
            )
            if already:
                continue

            try:
                ok = await email_service.send_legal_deadline_reminder(
                    to_email=row["owner_email"],
                    matter_title=row["title"] or "Legal matter",
                    matter_type=row["matter_type"] or "other",
                    deadline=row["response_deadline"],
                    days_until=days_until,
                    note=row["deadline_note"],
                )
                if ok:
                    await conn.execute(
                        """INSERT INTO legal_matter_audit_log (matter_id, action, details)
                           VALUES ($1, 'deadline_reminder', $2)""",
                        row["id"],
                        json.dumps({"bucket": str(bucket), "days_until": days_until,
                                    "deadline": row["response_deadline"].isoformat(),
                                    "sent_to": row["owner_email"]}),
                    )
                    sent += 1
                else:
                    failed += 1
            except Exception as exc:
                print(f"[Legal Deadline Reminders] Error sending to {row['owner_email']}: {exc}")
                failed += 1

        return {"checked": len(rows), "sent": sent, "failed": failed}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_legal_deadline_reminders(self) -> dict:
    """Scan active legal matters and nudge owners near their response deadline."""
    print("[Legal Deadline Reminders] Running...")
    try:
        result = asyncio.run(_run_legal_deadline_reminders())
        print(f"[Legal Deadline Reminders] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[Legal Deadline Reminders] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
