"""Reconcile schedule-blocking credential expiry cases.

Most requirements open manager-review cases. Credential types explicitly
configured for automatic enforcement (food-handler cards) also remove future
assignments at expiry and remain blocked until a renewed credential is approved.
"""
import asyncio
import logging
from datetime import datetime, timezone

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled
from app.core.feature_flags import get_company_features
from app.matcha.services.scheduling.schedule_eligibility import (
    open_expired_eligibility_cases,
    open_expired_job_credential_cases,
    open_expiring_eligibility_warnings,
    resolve_recovered_eligibility_cases,
)
from app.matcha.services.scheduling.schedule_eligibility_events import (
    reconcile_schedule_eligibility_events,
)
from app.matcha.services.scheduling.job_credential_requirements import (
    reconcile_company_job_requirements,
)

logger = logging.getLogger(__name__)


async def _dispatch() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "schedule_eligibility", default=False):
            return {"opened": 0, "warned": 0, "skipped": True}
        companies = await conn.fetch("SELECT id FROM companies")
        run_at = datetime.now(timezone.utc)
        opened = 0
        warned = 0
        recovered = 0
        for company in companies:
            features = await get_company_features(company["id"], conn=conn)
            if not features.get("employee_schedule"):
                continue
            # Warnings first, then expirations, on every run. A credential
            # already past its warning threshold on a PRIOR run may cross
            # into expired on this one — its warning_open row still needs
            # promoting to removal_requested, which open_expired_eligibility_cases
            # does explicitly (a plain INSERT would silently no-op via
            # ON CONFLICT DO NOTHING). Same-run crossing is not possible:
            # the warning query requires expires_at >= as_of and the expired
            # path requires expires_at < as_of.
            async with conn.transaction():
                # Workers use the direct Celery connection (never a request
                # asyncpg pool). Materialize before evaluating expiry so a
                # newly configured job rule is visible on this run.
                await reconcile_company_job_requirements(conn, company_id=company["id"])
                warning_ids = await open_expiring_eligibility_warnings(conn, company["id"], now=run_at)
                case_ids = await open_expired_eligibility_cases(conn, company["id"], now=run_at)
                case_ids.extend(await open_expired_job_credential_cases(conn, company["id"], now=run_at))
                newly_recovered = await resolve_recovered_eligibility_cases(conn, company["id"], now=run_at)
                await reconcile_schedule_eligibility_events(conn, company["id"])
            warned += len(warning_ids)
            for case_id in warning_ids:
                await _send_expiry_warning_email(conn, case_id)
            opened += len(case_ids)
            for case_id in case_ids:
                await _send_removal_requested_email(conn, case_id)
            recovered += newly_recovered
        return {"opened": opened, "warned": warned, "recovered": recovered, "companies": len(companies)}
    finally:
        await conn.close()


async def _location_scoped_recipients(conn, *, company_id, location_id, exclude_email=None) -> list[dict]:
    """Managers/supervisors at the case's location (plus its operational
    mailboxes) when the case is location-scoped; whole-company managers for
    an unscoped case — mirrors EligibilityManagerScope.permits(). Always
    deduped by email so a manager who is also the subject employee, or who
    appears in more than one source, gets exactly one email."""
    if location_id is not None:
        managers = await conn.fetch(
            """SELECT DISTINCT email, first_name FROM employees
               WHERE org_id=$1 AND work_location_id=$2
                 AND COALESCE(employment_status, 'active')='active'
                 AND (COALESCE(is_manager,false) OR COALESCE(is_supervisor,false))
                 AND email IS NOT NULL""", company_id, location_id)
        operational = await conn.fetch(
            """SELECT email, display_name AS first_name FROM schedule_location_notification_recipients
               WHERE company_id=$1 AND location_id=$2 AND is_active""", company_id, location_id)
        candidates = list(managers) + list(operational)
    else:
        candidates = await conn.fetch(
            """SELECT DISTINCT email, first_name FROM employees
               WHERE org_id=$1 AND COALESCE(employment_status, 'active')='active'
                 AND (COALESCE(is_manager,false) OR COALESCE(is_supervisor,false))
                 AND email IS NOT NULL""", company_id)
    exclude = (exclude_email or "").strip().lower()
    seen: set[str] = set()
    deduped = []
    for row in candidates:
        email = (row["email"] or "").strip().lower()
        if not email or email == exclude or email in seen:
            continue
        seen.add(email)
        deduped.append(row)
    return deduped


async def _send_removal_requested_email(conn, case_id) -> None:
    """Notify location managers when expiry has affected the schedule."""
    case = await conn.fetchrow(
        """SELECT c.company_id, c.employee_id, c.location_id, c.expires_at, c.blocking_reason_code,
                  e.first_name, e.last_name
           FROM schedule_eligibility_cases c JOIN employees e ON e.id=c.employee_id WHERE c.id=$1""", case_id)
    if not case:
        return
    recipients = await _location_scoped_recipients(
        conn, company_id=case["company_id"], location_id=case["location_id"],
    )
    if not recipients:
        return
    from app.core.services.email import get_email_service
    service = get_email_service()
    name = f"{case['first_name']} {case['last_name']}".strip()
    automatically_removed = str(case["blocking_reason_code"] or "").endswith("_auto_unassigned")
    subject = (
        f"Scheduling blocked: {name}"
        if automatically_removed else f"Scheduling decision required: {name}"
    )
    body = (
        "<p>Future shifts were removed automatically. New assignments remain blocked until a renewed credential is approved.</p>"
        if automatically_removed else "<p>Review the schedule eligibility case and choose removal or explicitly acknowledge retention.</p>"
    )
    for recipient in recipients:
        await service.send_email(
            to_email=recipient['email'], to_name=recipient['first_name'],
            subject=subject,
            html_content=(f"<p>{name} has an expired schedule-blocking requirement "
                          f"({case['expires_at'].isoformat() if case['expires_at'] else 'expired'}).</p>"
                          f"{body}"),
        )


async def _send_expiry_warning_email(conn, case_id) -> None:
    """Advance-warning notice for a credential entering its warning window —
    goes to both the subject employee and the case's location managers,
    unlike the removal-requested email above (manager-only, fires only
    after expiry). Skips any recipient with no email on file rather than
    raising, and never double-sends to a manager who is also the subject."""
    case = await conn.fetchrow(
        """SELECT c.company_id, c.employee_id, c.location_id, c.expires_at, e.first_name, e.last_name, e.email AS employee_email
           FROM schedule_eligibility_cases c JOIN employees e ON e.id=c.employee_id WHERE c.id=$1""", case_id)
    if not case:
        return
    managers = await _location_scoped_recipients(
        conn, company_id=case["company_id"], location_id=case["location_id"],
        exclude_email=case["employee_email"],
    )
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
