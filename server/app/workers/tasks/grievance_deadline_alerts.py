"""Celery task: alert on grievance steps nearing or past their deadline.

Runs once per worker startup (systemd restarts the worker ~every 15 min); the
dispatcher gates execution on `scheduler_settings.task_key =
'grievance_deadline_alerts'` being enabled (default off). Idempotent — only
touches active steps with `deadline_alert_sent = FALSE`. Emails the grievance's
HR owner + steward, flips truly-missed steps to `missed_deadline`, and marks the
alert as sent so a re-fire won't re-notify.
"""

import asyncio
import html as html_lib

from ..celery_app import celery_app
from ..utils import get_db_connection


async def _resolve_recipients(conn, row) -> list[tuple[str, str]]:
    """Return [(email, name)] for the grievance's HR owner + steward.

    Both lookups are scoped to the grievance's own company so a stale/cross-tenant
    assignee or steward id can never receive another company's grievance alert.
    """
    recipients: list[tuple[str, str]] = []
    seen: set[str] = set()
    company_id = row["company_id"]

    if row["assigned_to"]:
        owner = await conn.fetchrow(
            "SELECT u.email, COALESCE(c.name, u.email) AS name "
            "FROM users u JOIN clients c ON c.user_id = u.id "
            "WHERE u.id = $1 AND c.company_id = $2",
            row["assigned_to"], company_id,
        )
        if owner and owner["email"] and owner["email"] not in seen:
            recipients.append((owner["email"], owner["name"]))
            seen.add(owner["email"])

    if row["steward_employee_id"]:
        steward = await conn.fetchrow(
            "SELECT COALESCE(work_email, email) AS email, "
            "TRIM(COALESCE(first_name,'') || ' ' || COALESCE(last_name,'')) AS name "
            "FROM employees WHERE id = $1 AND org_id = $2",
            row["steward_employee_id"], company_id,
        )
        if steward and steward["email"] and steward["email"] not in seen:
            recipients.append((steward["email"], steward["name"] or steward["email"]))
            seen.add(steward["email"])

    return recipients


async def _dispatch() -> dict:
    conn = await get_db_connection()
    try:
        try:
            sched = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings "
                "WHERE task_key = 'grievance_deadline_alerts'"
            )
        except Exception:
            sched = None
        if not sched or not sched["enabled"]:
            print("[Grievance Deadlines] Scheduler disabled, skipping.")
            return {"alerts": 0, "skipped": True}

        limit = sched["max_per_cycle"] or 500
        rows = await conn.fetch(
            """
            SELECT s.id AS step_id, s.step_number, s.step_name, s.deadline_to_respond,
                   (s.deadline_to_respond < (NOW() AT TIME ZONE 'UTC')::date) AS is_overdue,
                   g.company_id, g.grievance_number, g.title, g.assigned_to,
                   g.steward_employee_id, g.steward_name_external
            FROM lr_grievance_steps s
            JOIN lr_grievances g ON g.id = s.grievance_id
            WHERE s.status = 'active' AND s.deadline_alert_sent = FALSE
              AND s.deadline_to_respond IS NOT NULL
              AND s.deadline_to_respond <= (NOW() AT TIME ZONE 'UTC')::date + INTERVAL '2 days'
            ORDER BY s.deadline_to_respond ASC
            LIMIT $1
            """,
            limit,
        )

        if not rows:
            return {"alerts": 0}

        from app.core.services.email import get_email_service
        email_service = get_email_service()
        sent = 0

        for row in rows:
            overdue = row["is_overdue"]
            when = "has PASSED" if overdue else "is approaching"
            # Escape every interpolated value — title + step_name are
            # user/AI-controlled (grievance title, CBA-parsed step names) and
            # land in the recipient's email client.
            gnum = html_lib.escape(str(row["grievance_number"]))
            gtitle = html_lib.escape(row["title"] or "")
            sname = html_lib.escape(row["step_name"] or "")
            deadline = html_lib.escape(str(row["deadline_to_respond"]))
            subject = f"Grievance {row['grievance_number']}: response deadline {('passed' if overdue else 'approaching')}"
            html = (
                f"<p>Grievance <strong>{gnum}</strong> — {gtitle}</p>"
                f"<p><strong>{sname}</strong> response deadline {when}: "
                f"<strong>{deadline}</strong>.</p>"
                f"<p>Review and respond, or advance the grievance, before the contractual window lapses.</p>"
            )
            recipients = await _resolve_recipients(conn, row)
            for email, name in recipients:
                try:
                    await email_service.send_email(
                        to_email=email, to_name=name, subject=subject, html_content=html,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[Grievance Deadlines] email to {email} failed: {exc}")

            # Mark alerted; flip truly-missed steps so the dashboard reflects it.
            if overdue:
                await conn.execute(
                    "UPDATE lr_grievance_steps SET deadline_alert_sent = TRUE, "
                    "status = 'missed_deadline', updated_at = NOW() WHERE id = $1",
                    row["step_id"],
                )
            else:
                await conn.execute(
                    "UPDATE lr_grievance_steps SET deadline_alert_sent = TRUE, updated_at = NOW() "
                    "WHERE id = $1",
                    row["step_id"],
                )
            sent += 1

        print(f"[Grievance Deadlines] Processed {sent} step alert(s).")
        return {"alerts": sent}
    finally:
        await conn.close()


@celery_app.task(name="labor.grievance_deadline_alerts", bind=True, max_retries=1)
def run_grievance_deadline_alerts(self):
    """Sweep active grievance steps near/past deadline; email + mark missed."""
    try:
        return asyncio.run(_dispatch())
    except Exception as e:
        print(f"[Grievance Deadlines] Task failed: {e}")
        raise self.retry(exc=e, countdown=120)
