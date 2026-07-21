"""Celery task — auto-assign CA SB 1343 training records.

Two queries:
  (a) Initial assignment for CA employees past their 6-month new-hire window
      who have no active record.
  (b) Renewal for completed records expiring within 60 days.

Gated on `scheduler_settings.training_cadence.enabled` (default false from
schema migration). Re-dispatched by celery_app.@worker_ready every 15 minutes
via the systemd timer.

After each insert batch, fans out assignment emails (best-effort).
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row


async def _send_assignment_email(employee_email: str, employee_name: str, training_title: str, due_date) -> None:
    from app.config import get_settings
    from app.core.services.email import get_email_service

    settings = get_settings()
    base_url = getattr(settings, "frontend_url", None) or "https://hey-matcha.com"
    login_url = f"{base_url.rstrip('/')}/portal/training"

    email_svc = get_email_service()
    if not email_svc.is_configured():
        return
    try:
        await email_svc.send_training_assignment_email(
            to_email=employee_email,
            to_name=employee_name,
            training_title=training_title,
            due_date=due_date,
            login_url=login_url,
        )
    except Exception as exc:
        print(f"[Training Cadence] Email failed for {employee_email}: {exc}")


async def _dispatch_training_cadence() -> dict:
    conn = await get_db_connection()
    inserted_initial = 0
    inserted_renewal = 0
    notifications_sent = 0
    try:
        sched_row = await scheduler_settings_row(conn, "training_cadence")

        if sched_row and not sched_row["enabled"]:
            print("[Training Cadence] Scheduler disabled, skipping.")
            return {"initial_assigned": 0, "renewals": 0}

        limit = (
            sched_row["max_per_cycle"]
            if sched_row and sched_row["max_per_cycle"] and sched_row["max_per_cycle"] > 0
            else 200
        )

        # (a) Initial assignment for CA new-hires past 6mo without an active record
        initial_rows = await conn.fetch(
            """
            WITH eligible AS (
                SELECT e.id AS employee_id, e.org_id, e.is_supervisor,
                       e.email, e.first_name, e.last_name, e.start_date
                FROM employees e
                JOIN companies c ON c.id = e.org_id
                WHERE e.work_state = 'CA'
                  AND e.termination_date IS NULL
                  AND e.start_date IS NOT NULL
                  AND e.start_date <= CURRENT_DATE - INTERVAL '6 months'
                  AND COALESCE((c.enabled_features->>'training')::boolean, FALSE) = TRUE
            )
            INSERT INTO training_records
              (company_id, employee_id, requirement_id, title, training_type,
               assigned_date, due_date, status)
            SELECT e.org_id, e.employee_id, tr.id, tr.title, tr.training_type,
                   CURRENT_DATE,
                   e.start_date + INTERVAL '6 months',
                   'assigned'
            FROM eligible e
            JOIN training_requirements tr
              ON tr.company_id = e.org_id
             AND tr.is_active = TRUE
             AND tr.training_type = 'harassment_prevention'
             AND tr.jurisdiction = 'CA'
             AND ((e.is_supervisor AND tr.applies_to = 'supervisor')
                  OR (NOT e.is_supervisor AND tr.applies_to = 'nonsupervisor'))
            WHERE NOT EXISTS (
                SELECT 1 FROM training_records r
                WHERE r.employee_id = e.employee_id
                  AND r.requirement_id = tr.id
                  AND r.status IN ('assigned','in_progress','completed')
                  AND (r.expiration_date IS NULL OR r.expiration_date > CURRENT_DATE)
            )
            LIMIT $1
            RETURNING employee_id, title, due_date,
                      (SELECT email FROM employees WHERE id = employee_id) AS email,
                      (SELECT first_name FROM employees WHERE id = employee_id) AS first_name,
                      (SELECT last_name FROM employees WHERE id = employee_id) AS last_name
            """,
            limit,
        )
        inserted_initial = len(initial_rows)

        # (b) Renewal — completed records with expiration within 60 days, no follow-up record
        renewal_rows = await conn.fetch(
            """
            INSERT INTO training_records
              (company_id, employee_id, requirement_id, title, training_type,
               assigned_date, due_date, status)
            SELECT r.company_id, r.employee_id, r.requirement_id, r.title, r.training_type,
                   CURRENT_DATE, r.expiration_date, 'assigned'
            FROM training_records r
            WHERE r.status = 'completed'
              AND r.expiration_date BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '60 days'
              AND NOT EXISTS (
                  SELECT 1 FROM training_records r2
                  WHERE r2.employee_id = r.employee_id
                    AND r2.requirement_id = r.requirement_id
                    AND r2.id != r.id
                    AND r2.assigned_date > r.completed_date
              )
            LIMIT $1
            RETURNING employee_id, title, due_date,
                      (SELECT email FROM employees WHERE id = employee_id) AS email,
                      (SELECT first_name FROM employees WHERE id = employee_id) AS first_name,
                      (SELECT last_name FROM employees WHERE id = employee_id) AS last_name
            """,
            limit,
        )
        inserted_renewal = len(renewal_rows)

        # Best-effort notifications (won't roll back DB inserts on email failure)
        all_assignments = [*initial_rows, *renewal_rows]
        for r in all_assignments:
            email = r["email"]
            if not email:
                continue
            try:
                full_name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
                await _send_assignment_email(
                    employee_email=email,
                    employee_name=full_name or None,
                    training_title=r["title"],
                    due_date=r["due_date"],
                )
                notifications_sent += 1
            except Exception as exc:
                print(f"[Training Cadence] Notify error: {exc}")

    finally:
        await conn.close()

    summary = {
        "initial_assigned": inserted_initial,
        "renewals": inserted_renewal,
        "notifications_sent": notifications_sent,
    }
    print(f"[Training Cadence] {summary}")
    return summary


@celery_app.task(name="training_cadence.run_training_cadence", bind=True, max_retries=1)
def run_training_cadence(self):
    """Dispatch CA SB 1343 cadence assignments."""
    try:
        return asyncio.run(_dispatch_training_cadence())
    except Exception as e:
        print(f"[Training Cadence] Task failed: {e}")
        raise self.retry(exc=e, countdown=120)
