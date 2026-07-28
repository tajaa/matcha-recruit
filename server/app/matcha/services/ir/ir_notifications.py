"""IR lifecycle + info-request email notifications.

Moved from routes/ir_incidents/_shared.py (refactor round 2, stage 3).
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from app.core.services.email import get_email_service
from app.database import connection_or_direct

logger = logging.getLogger(__name__)


async def _get_company_admin_contacts(company_id: str) -> tuple[str, list[dict[str, str]]]:
    """Return company display name and company-admin/client email recipients.

    Uses `connection_or_direct` rather than `get_connection` — this is a
    services-layer function (moved from routes/ir_incidents/_shared.py) that
    `create_incident_core` schedules as a background callable, and that function
    is now imported at module level by `huume/hr_ops_skill.py` and
    `pilots/hr_pilot_actions.py`. Nothing calls this from a pool-free Celery
    worker today, but the next caller that does gets a real connection instead
    of a confusing pool-not-initialized failure. See root CLAUDE.md: "Workers
    are pool-free — shared service code must not assume a pool."
    """
    async with connection_or_direct() as conn:
        company_name = await conn.fetchval(
            "SELECT name FROM companies WHERE id = $1",
            company_id,
        ) or "Your company"

        rows = await conn.fetch(
            """
            SELECT DISTINCT
                u.email,
                COALESCE(NULLIF(c.name, ''), split_part(u.email, '@', 1)) AS name
            FROM clients c
            JOIN users u ON u.id = c.user_id
            WHERE c.company_id = $1
              AND u.is_active = true
              AND u.email IS NOT NULL
            ORDER BY u.email
            """,
            company_id,
        )

    contacts = [
        {"email": row["email"], "name": row["name"] or row["email"]}
        for row in rows
    ]
    return company_name, contacts


async def send_ir_notifications_task(
    *,
    company_id: str,
    incident_id: str,
    incident_number: str,
    incident_title: str,
    event_type: str,
    current_status: str,
    changed_by_email: Optional[str] = None,
    previous_status: Optional[str] = None,
    location_name: Optional[str] = None,
    occurred_at: Optional[datetime] = None,
):
    """Send IR lifecycle notifications to company admins in the background."""
    email_service = get_email_service()
    if not email_service.is_configured():
        logger.info("[IR] Email service not configured - skipping IR notifications")
        return

    company_name, contacts = await _get_company_admin_contacts(company_id)
    if not contacts:
        logger.info(f"[IR] No admin/client contacts found for company {company_id}")
        return

    tasks = [
        email_service.send_ir_incident_notification_email(
            to_email=contact["email"],
            to_name=contact.get("name"),
            company_name=company_name,
            incident_id=incident_id,
            incident_number=incident_number,
            incident_title=incident_title,
            event_type=event_type,
            current_status=current_status,
            changed_by_email=changed_by_email,
            previous_status=previous_status,
            location_name=location_name,
            occurred_at=occurred_at,
        )
        for contact in contacts
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    sent_count = 0
    for contact, result in zip(contacts, results):
        if isinstance(result, Exception):
            logger.warning(f"[IR] Failed to notify {contact['email']}: {result}")
            continue
        if result:
            sent_count += 1

    if sent_count:
        logger.info(f"[IR] Sent {sent_count}/{len(contacts)} IR notification email(s)")
    else:
        logger.warning("[IR] IR notifications attempted but no emails were sent successfully")


async def send_ir_info_request_notification_task(
    *,
    company_id: str,
    incident_id: str,
    incident_number: str,
    respondent_name: str,
):
    """Notify company admins that a "Request More Info" form was submitted."""
    email_service = get_email_service()
    if not email_service.is_configured():
        logger.info("[IR] Email service not configured - skipping info-request notification")
        return

    company_name, contacts = await _get_company_admin_contacts(company_id)
    if not contacts:
        logger.info(f"[IR] No admin/client contacts found for company {company_id}")
        return

    incident_url = f"{email_service.settings.app_base_url}/app/ir/{incident_id}"

    tasks = [
        email_service.send_ir_info_request_response_email(
            to_email=contact["email"],
            to_name=contact.get("name"),
            company_name=company_name,
            incident_number=incident_number,
            respondent_name=respondent_name,
            link=incident_url,
        )
        for contact in contacts
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)
    sent_count = sum(1 for r in results if r and not isinstance(r, Exception))
    if sent_count:
        logger.info(f"[IR] Sent {sent_count}/{len(contacts)} info-request notification email(s)")
    else:
        logger.warning("[IR] Info-request notification attempted but no emails were sent successfully")
