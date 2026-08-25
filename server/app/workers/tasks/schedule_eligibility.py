"""Open manager-decision cases for expired schedule-blocking requirements.

This task intentionally never removes assignments. Managers decide removal or
provide an explicit, audited acknowledgement through the scheduling API.
"""
import asyncio
import logging
from datetime import date

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled
from app.matcha.services.scheduling.schedule_eligibility import (
    open_expired_eligibility_cases,
    open_expiring_eligibility_warnings,
)

logger = logging.getLogger(__name__)


async def _dispatch() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "schedule_eligibility", default=False):
            return {"opened": 0, "warned": 0, "skipped": True}
        companies = await conn.fetch("SELECT id FROM companies")
        opened = 0
        warned = 0
        for company in companies:
            # Warnings first: a credential that crosses from "inside its
            # warning window" to "expired" in the SAME run must still get
            # its removal_requested case (open_expired_eligibility_cases
            # promotes a same-run warning_open row rather than relying on
            # ON CONFLICT DO NOTHING, which would otherwise no-op it).
            warning_ids = await open_expiring_eligibility_warnings(conn, company["id"], as_of=date.today())
            warned += len(warning_ids)
            for case_id in warning_ids:
                await _send_expiry_warning_email(conn, case_id)
            case_ids = await open_expired_eligibility_cases(conn, company["id"], as_of=date.today())
            opened += len(case_ids)
            for case_id in case_ids:
                await _send_removal_requested_email(conn, case_id)
        return {"opened": opened, "warned": warned, "companies": len(companies)}
    finally:
        await conn.close()


async def _send_removal_requested_email(conn, case_id) -> None:
    """Notify company managers of a pending decision without claiming legal advice."""
    case = await conn.fetchrow(
        """SELECT c.employee_id, c.expires_at, e.first_name, e.last_name
           FROM schedule_eligibility_cases c JOIN employees e ON e.id=c.employee_id WHERE c.id=$1""", case_id)
    if not case:
        return
    recipients = await conn.fetch(
        """SELECT DISTINCT email, first_name FROM employees
           WHERE org_id=(SELECT company_id FROM schedule_eligibility_cases WHERE id=$1)
             AND COALESCE(employment_status, 'active')='active'
             AND (COALESCE(is_manager,false) OR COALESCE(is_supervisor,false))
             AND email IS NOT NULL""", case_id)
    if not recipients:
        return
    from app.core.services.email import get_email_service
    service = get_email_service()
    name = f"{case['first_name']} {case['last_name']}".strip()
    for recipient in recipients:
        await service.send_email(
            to_email=recipient['email'], to_name=recipient['first_name'],
            subject=f"Scheduling decision required: {name}",
            html_content=(f"<p>{name} has an expired schedule-blocking requirement "
                          f"({case['expires_at'].isoformat() if case['expires_at'] else 'expired'}).</p>"
                          "<p>Review the schedule eligibility case and choose removal or explicitly acknowledge retention.</p>"),
        )


async def _send_expiry_warning_email(conn, case_id) -> None:
    """Advance-warning notice for a credential entering its warning window —
    goes to both the subject employee and company managers, unlike the
    removal-requested email above (manager-only, fires only after expiry).
    Skips any recipient with no email on file rather than raising."""
    case = await conn.fetchrow(
        """SELECT c.company_id, c.employee_id, c.expires_at, e.first_name, e.last_name, e.email AS employee_email
           FROM schedule_eligibility_cases c JOIN employees e ON e.id=c.employee_id WHERE c.id=$1""", case_id)
    if not case:
        return
    managers = await conn.fetch(
        """SELECT DISTINCT email, first_name FROM employees
           WHERE org_id=$1 AND COALESCE(employment_status, 'active')='active'
             AND (COALESCE(is_manager,false) OR COALESCE(is_supervisor,false))
             AND email IS NOT NULL""", case["company_id"])
    recipients = list(managers)
    if case["employee_email"]:
        recipients.append({"email": case["employee_email"], "first_name": case["first_name"]})
    if not recipients:
        return
    from app.core.services.email import get_email_service
    service = get_email_service()
    name = f"{case['first_name']} {case['last_name']}".strip()
    expires = case['expires_at'].isoformat() if case['expires_at'] else "soon"
    for recipient in recipients:
        await service.send_email(
            to_email=recipient['email'], to_name=recipient['first_name'],
            subject=f"Credential expiring soon: {name}",
            html_content=(f"<p>{name}'s schedule-blocking credential expires {expires}.</p>"
                          "<p>A renewed credential must be on file by that date, or scheduling for "
                          "upcoming shifts will be blocked.</p>"),
        )


@celery_app.task(name="schedule_eligibility.run", bind=True, max_retries=1)
def run_schedule_eligibility(self):
    try:
        return asyncio.run(_dispatch())
    except Exception as exc:
        logger.exception("Schedule eligibility reconciliation failed")
        raise self.retry(exc=exc, countdown=60)
