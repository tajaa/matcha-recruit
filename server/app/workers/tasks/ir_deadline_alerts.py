"""Celery task: IR deadline / SLA alerts.

The IR product was the only major domain without a deadline worker — compliance,
legal, grievance, leave, and discipline all have one. This adds the missing
piece: four best-effort sweeps that nudge owners/admins so nothing rots silently.

  1. CAPA due/overdue      — ir_corrective_actions past (or nearing) due_date.
  2. Stale critical/high   — critical/high incidents sitting untouched.
  3. Unclassified recordable — osha_recordable incidents with no classification
                               as the 300A/ITA deadline (Mar 2) approaches.
  4. OSHA emergency window — the 8/24hr fatality/hospitalization clock, promoted
                             from a static Copilot card to a tracked email.

Runs on the shared worker restart cadence; gated on
scheduler_settings.task_key = 'ir_deadline_alerts' (seeded DISABLED, migration
irdl01). Idempotent: CAPA dedupes on ir_corrective_actions.reminder_sent_at;
sweeps 2–4 dedupe via ir_deadline_alert_log (incident_id, alert_kind, sent_on).
"""

import asyncio
from datetime import date, timedelta

from ..celery_app import celery_app
from ..utils import get_db_connection
from app.core.services.company_contacts import get_company_admin_contacts

# CAPA: how many days ahead of due_date to start nudging.
CAPA_LOOKAHEAD_DAYS = 2
# ...and how often to re-nudge while the action stays open. Without a backoff a
# permanently-overdue action emails its owner every single morning forever,
# which is how the highest-volume sweep trains people to filter the alerts.
# 'immediate'-priority actions get the tighter cadence.
CAPA_REMINDER_INTERVAL_DAYS = 7
CAPA_REMINDER_INTERVAL_DAYS_IMMEDIATE = 3
# Stale-incident thresholds (days since reported AND since last update).
STALE_CRITICAL_DAYS = 3
STALE_HIGH_DAYS = 7
# Unclassified-recordable sweep only fires inside the 300A/ITA prep window
# (this many days before the next March 2 electronic-filing deadline) and at
# most once per this many days per incident.
RECORDABLE_WINDOW_DAYS = 90
RECORDABLE_REMINDER_INTERVAL_DAYS = 7


def _next_ita_deadline(today: date) -> date:
    """The upcoming March 2 (OSHA ITA electronic submission deadline)."""
    this_year = date(today.year, 3, 2)
    return this_year if today <= this_year else date(today.year + 1, 3, 2)




async def _already_sent(conn, incident_id, alert_kind, today) -> bool:
    """Has this (incident, alert_kind) already gone out today?

    Checked BEFORE sending. The ledger row is only written once an email
    actually lands (`_record_sent`) — writing it up-front meant a company with
    no reachable admins, or a transient SMTP failure, silently burned the day's
    alert with nothing delivered.
    """
    return await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1 FROM ir_deadline_alert_log
            WHERE incident_id = $1 AND alert_kind = $2 AND sent_on = $3
        )
        """,
        incident_id, alert_kind, today,
    )


async def _record_sent(conn, incident_id, company_id, alert_kind, today) -> None:
    """Stamp the dedupe ledger after a successful send."""
    await conn.execute(
        """
        INSERT INTO ir_deadline_alert_log (incident_id, company_id, alert_kind, sent_on)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (incident_id, alert_kind, sent_on) DO NOTHING
        """,
        incident_id, company_id, alert_kind, today,
    )


async def _sweep_capa(conn, email_service, today, limit) -> dict:
    """Nudge owners on corrective actions that are due soon or overdue."""
    lookahead = today + timedelta(days=CAPA_LOOKAHEAD_DAYS)
    # Re-nudge cutoffs: an action is eligible again only once its last reminder
    # is older than its priority's interval (never nudged → always eligible).
    standard_cutoff = today - timedelta(days=CAPA_REMINDER_INTERVAL_DAYS)
    immediate_cutoff = today - timedelta(days=CAPA_REMINDER_INTERVAL_DAYS_IMMEDIATE)
    rows = await conn.fetch(
        """
        SELECT ca.id AS action_id, ca.company_id, ca.description, ca.due_date,
               ca.assigned_to, ca.assignee_name,
               i.id AS incident_id, i.incident_number, i.title AS incident_title,
               comp.name AS company_name,
               u.email AS owner_email,
               COALESCE(NULLIF(cl.name, ''), split_part(u.email, '@', 1)) AS owner_name
        FROM ir_corrective_actions ca
        JOIN ir_incidents i ON i.id = ca.incident_id
        JOIN companies comp ON comp.id = ca.company_id
        LEFT JOIN users u ON u.id = ca.assigned_to
        LEFT JOIN clients cl ON cl.user_id = ca.assigned_to AND cl.company_id = ca.company_id
        WHERE ca.status IN ('open', 'in_progress')
          AND ca.due_date IS NOT NULL
          AND ca.due_date <= $1
          AND (
                ca.reminder_sent_at IS NULL
                OR ca.reminder_sent_at <= (CASE WHEN ca.priority = 'immediate'
                                                THEN $3::date ELSE $2::date END)
              )
        ORDER BY ca.due_date ASC
        LIMIT $4
        """,
        lookahead, standard_cutoff, immediate_cutoff, limit,
    )

    sent = 0
    for r in rows:
        due = r["due_date"]
        days_until = (due - today).days
        urgency = "today" if days_until == 0 else (
            f"{-days_until} day{'s' if -days_until != 1 else ''} overdue" if days_until < 0
            else f"in {days_until} day{'s' if days_until != 1 else ''}"
        )
        # Prefer the assigned owner; fall back to company admins.
        recipients = []
        if r["owner_email"]:
            recipients = [{"email": r["owner_email"], "name": r["owner_name"] or r["owner_email"]}]
        else:
            recipients = await get_company_admin_contacts(conn, r["company_id"])
        if not recipients:
            continue

        urgent = days_until <= 0
        detail = [
            ("Action", (r["description"] or "")[:200]),
            ("Incident", f"{r['incident_number']} — {r['incident_title']}"),
            ("Due", f"{due.strftime('%B %d, %Y')} ({urgency})"),
        ]
        any_ok = False
        for rc in recipients:
            try:
                ok = await email_service.send_ir_deadline_reminder(
                    to_email=rc["email"],
                    to_name=rc["name"],
                    company_name=r["company_name"] or "Your company",
                    subject=f"[{r['company_name']}] Corrective action due {urgency}",
                    headline=f"A corrective action is due {urgency}.",
                    detail_lines=detail,
                    incident_id=str(r["incident_id"]),
                    cta_label="Open Incident",
                    urgent=urgent,
                )
                any_ok = any_ok or bool(ok)
            except Exception as exc:  # noqa: BLE001
                print(f"[IR Deadline Alerts] CAPA email error to {rc['email']}: {exc}")
        if any_ok:
            await conn.execute(
                "UPDATE ir_corrective_actions SET reminder_sent_at = $1 WHERE id = $2",
                today, r["action_id"],
            )
            sent += 1
    return {"capa_sent": sent, "capa_checked": len(rows)}


async def _sweep_stale_incidents(conn, email_service, today, limit) -> dict:
    """Nudge admins on critical/high incidents sitting untouched."""
    rows = await conn.fetch(
        """
        SELECT i.id AS incident_id, i.company_id, i.incident_number, i.title,
               i.severity, i.status, i.reported_at, comp.name AS company_name,
               EXTRACT(DAY FROM (NOW() - i.reported_at))::int AS age_days
        FROM ir_incidents i
        JOIN companies comp ON comp.id = i.company_id
        WHERE i.severity IN ('critical', 'high')
          AND i.status IN ('reported', 'investigating', 'action_required')
          AND i.updated_at < NOW() - (
                CASE WHEN i.severity = 'critical'
                     THEN make_interval(days => $1)
                     ELSE make_interval(days => $2) END)
          AND i.reported_at < NOW() - (
                CASE WHEN i.severity = 'critical'
                     THEN make_interval(days => $1)
                     ELSE make_interval(days => $2) END)
        ORDER BY CASE i.severity WHEN 'critical' THEN 0 ELSE 1 END,
                 i.reported_at ASC
        LIMIT $3
        """,
        STALE_CRITICAL_DAYS, STALE_HIGH_DAYS, limit,
    )

    sent = 0
    for r in rows:
        if await _already_sent(conn, r["incident_id"], "stale_critical", today):
            continue
        recipients = await get_company_admin_contacts(conn, r["company_id"])
        if not recipients:
            continue
        detail = [
            ("Incident", f"{r['incident_number']} — {r['title']}"),
            ("Severity", (r["severity"] or "").title()),
            ("Status", (r["status"] or "").replace("_", " ").title()),
            ("Open for", f"{r['age_days']} days with no recent update"),
        ]
        any_ok = False
        for rc in recipients:
            try:
                ok = await email_service.send_ir_deadline_reminder(
                    to_email=rc["email"],
                    to_name=rc["name"],
                    company_name=r["company_name"] or "Your company",
                    subject=f"[{r['company_name']}] {r['severity'].title()} incident needs attention",
                    headline=f"A {r['severity']} incident has gone {r['age_days']} days without an update.",
                    detail_lines=detail,
                    incident_id=str(r["incident_id"]),
                    cta_label="Open Incident",
                    urgent=(r["severity"] == "critical"),
                )
                any_ok = any_ok or bool(ok)
            except Exception as exc:  # noqa: BLE001
                print(f"[IR Deadline Alerts] Stale email error to {rc['email']}: {exc}")
        if any_ok:
            await _record_sent(conn, r["incident_id"], r["company_id"], "stale_critical", today)
            sent += 1
    return {"stale_sent": sent, "stale_checked": len(rows)}


async def _sweep_unclassified_recordable(conn, email_service, today, limit) -> dict:
    """Warn admins about recordables with no OSHA classification before Mar 2."""
    deadline = _next_ita_deadline(today)
    if (deadline - today).days > RECORDABLE_WINDOW_DAYS:
        return {"recordable_sent": 0, "recordable_skipped": "outside_window"}

    interval_cutoff = today - timedelta(days=RECORDABLE_REMINDER_INTERVAL_DAYS)
    rows = await conn.fetch(
        """
        SELECT i.id AS incident_id, i.company_id, i.incident_number, i.title,
               comp.name AS company_name
        FROM ir_incidents i
        JOIN companies comp ON comp.id = i.company_id
        WHERE i.osha_recordable = true
          AND i.status <> 'closed'
          AND NOT EXISTS (
                SELECT 1 FROM ir_osha_case_details d
                WHERE d.incident_id = i.id AND d.classification IS NOT NULL)
          AND NOT EXISTS (
                SELECT 1 FROM ir_deadline_alert_log l
                WHERE l.incident_id = i.id
                  AND l.alert_kind = 'unclassified_recordable'
                  AND l.sent_on > $1)
        ORDER BY i.reported_at ASC
        LIMIT $2
        """,
        interval_cutoff, limit,
    )

    sent = 0
    for r in rows:
        if await _already_sent(conn, r["incident_id"], "unclassified_recordable", today):
            continue
        recipients = await get_company_admin_contacts(conn, r["company_id"])
        if not recipients:
            continue
        detail = [
            ("Incident", f"{r['incident_number']} — {r['title']}"),
            ("Missing", "OSHA case classification (days away / restricted / other)"),
            ("Deadline", f"300A posting Feb 1 · ITA electronic filing {deadline.strftime('%B %d, %Y')}"),
        ]
        any_ok = False
        for rc in recipients:
            try:
                ok = await email_service.send_ir_deadline_reminder(
                    to_email=rc["email"],
                    to_name=rc["name"],
                    company_name=r["company_name"] or "Your company",
                    subject=f"[{r['company_name']}] OSHA recordable not yet classified",
                    headline="A recordable injury still needs its OSHA classification before your 300A/ITA filing.",
                    detail_lines=detail,
                    incident_id=str(r["incident_id"]),
                    cta_label="Classify Incident",
                    urgent=False,
                )
                any_ok = any_ok or bool(ok)
            except Exception as exc:  # noqa: BLE001
                print(f"[IR Deadline Alerts] Recordable email error to {rc['email']}: {exc}")
        if any_ok:
            await _record_sent(conn, r["incident_id"], r["company_id"], "unclassified_recordable", today)
            sent += 1
    return {"recordable_sent": sent, "recordable_checked": len(rows)}


async def _sweep_osha_emergency(conn, email_service, today, limit) -> dict:
    """Track the OSHA 8/24hr emergency reporting window while it's still open."""
    rows = await conn.fetch(
        """
        SELECT i.id AS incident_id, i.company_id, i.incident_number, i.title,
               i.reported_at, comp.name AS company_name
        FROM ir_incidents i
        JOIN companies comp ON comp.id = i.company_id
        WHERE COALESCE((i.category_data->>'osha_emergency_alert_active')::boolean, false) = true
          AND i.reported_at > NOW() - INTERVAL '2 days'
        ORDER BY i.reported_at ASC
        LIMIT $1
        """,
        limit,
    )

    sent = 0
    for r in rows:
        if await _already_sent(conn, r["incident_id"], "osha_emergency", today):
            continue
        recipients = await get_company_admin_contacts(conn, r["company_id"])
        if not recipients:
            continue
        detail = [
            ("Incident", f"{r['incident_number']} — {r['title']}"),
            ("Requirement", "Report to OSHA — fatality within 8 hours; hospitalization/amputation/eye loss within 24 hours (29 CFR 1904.39)"),
            ("OSHA hotline", "1-800-321-6742"),
        ]
        any_ok = False
        for rc in recipients:
            try:
                ok = await email_service.send_ir_deadline_reminder(
                    to_email=rc["email"],
                    to_name=rc["name"],
                    company_name=r["company_name"] or "Your company",
                    subject=f"[{r['company_name']}] URGENT: OSHA reporting window open",
                    headline="This incident may require a report to OSHA within hours. Confirm it has been filed.",
                    detail_lines=detail,
                    incident_id=str(r["incident_id"]),
                    cta_label="Open Incident",
                    urgent=True,
                )
                any_ok = any_ok or bool(ok)
            except Exception as exc:  # noqa: BLE001
                print(f"[IR Deadline Alerts] OSHA emergency email error to {rc['email']}: {exc}")
        if any_ok:
            await _record_sent(conn, r["incident_id"], r["company_id"], "osha_emergency", today)
            sent += 1
    return {"osha_emergency_sent": sent, "osha_emergency_checked": len(rows)}


async def _run_ir_deadline_alerts() -> dict:
    from app.core.services.email import EmailService
    from app.config import get_settings

    conn = await get_db_connection()
    try:
        try:
            sched_row = await conn.fetchrow(
                "SELECT enabled, max_per_cycle FROM scheduler_settings WHERE task_key = 'ir_deadline_alerts'"
            )
        except Exception:
            sched_row = None

        if not sched_row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not sched_row["enabled"]:
            print("[IR Deadline Alerts] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        limit = sched_row["max_per_cycle"] or 200
        today = date.today()

        settings = get_settings()
        email_service = EmailService(settings)
        if not email_service.is_configured():
            return {"skipped": True, "reason": "email_not_configured"}

        result = {}
        result.update(await _sweep_capa(conn, email_service, today, limit))
        result.update(await _sweep_stale_incidents(conn, email_service, today, limit))
        result.update(await _sweep_unclassified_recordable(conn, email_service, today, limit))
        result.update(await _sweep_osha_emergency(conn, email_service, today, limit))
        return result
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_ir_deadline_alerts(self) -> dict:
    """Scan IR incidents + corrective actions and send deadline/SLA reminders."""
    print("[IR Deadline Alerts] Running...")
    try:
        result = asyncio.run(_run_ir_deadline_alerts())
        print(f"[IR Deadline Alerts] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[IR Deadline Alerts] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
