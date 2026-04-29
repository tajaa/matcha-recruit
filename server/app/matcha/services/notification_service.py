"""Matcha Work notification service.

Creates, queries, and manages notifications for users. Also sends emails
for important events using the existing email service.
"""

import logging
from typing import Optional
from uuid import UUID

from ...database import get_connection

logger = logging.getLogger(__name__)

# Notification types
TYPES = {
    "project_invite": "Project Invite",
    "project_invite_accepted": "Invite Accepted",
    "project_invite_declined": "Invite Declined",
    "channel_added": "Added to Channel",
    "channel_message": "Channel Message",
    "inbox_message": "New Message",
    "mention": "Mentioned",
    "channel_inactivity_warning": "Inactivity Warning",
    "channel_removed_for_inactivity": "Removed for Inactivity",
    "channel_payment_failed": "Payment Failed",
    "channel_tip_received": "Tip Received",
    "job_posting_invite": "Job Posting Invitation",
    "job_application_received": "Application Received",
    "job_application_status_changed": "Application Updated",
    "job_posting_payment_failed": "Job Posting Payment Failed",
    "discipline_issued": "Discipline Record Issued",
    "discipline_signature_requested": "Discipline Signature Requested",
    "discipline_signed": "Discipline Signed",
    "discipline_refused": "Discipline Signature Refused",
    "discipline_physical_uploaded": "Discipline Signature Uploaded",
}


async def create_notification(
    *,
    user_id: UUID,
    company_id: UUID,
    type: str,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    metadata: Optional[dict] = None,
    send_email: bool = False,
    email_subject: Optional[str] = None,
) -> dict:
    """Create a notification for a user. Optionally send an email."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO mw_notifications (user_id, company_id, type, title, body, link, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
            RETURNING id, user_id, company_id, type, title, body, link, metadata, is_read, created_at
            """,
            user_id, company_id, type, title, body, link,
            __import__("json").dumps(metadata or {}),
        )

    if send_email:
        try:
            await _send_notification_email(user_id, email_subject or title, title, body, link)
        except Exception as e:
            logger.warning("Failed to send notification email to %s: %s", user_id, e)

    return dict(row)


async def get_notifications(
    user_id: UUID,
    *,
    company_id: UUID | None = None,
    unread_only: bool = False,
    limit: int = 30,
    offset: int = 0,
) -> list[dict]:
    """Get notifications for a user, newest first. Scoped to company if provided."""
    where = "WHERE user_id = $1"
    params: list = [user_id]
    if company_id is not None:
        params.append(company_id)
        where += f" AND (company_id = ${len(params)} OR company_id IS NULL)"
    if unread_only:
        where += " AND is_read = FALSE"

    params.extend([limit, offset])
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT id, user_id, company_id, type, title, body, link, metadata, is_read, created_at
            FROM mw_notifications
            {where}
            ORDER BY created_at DESC
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
    return [dict(r) for r in rows]


async def get_unread_count(user_id: UUID, company_id: UUID | None = None) -> int:
    async with get_connection() as conn:
        if company_id is not None:
            return await conn.fetchval(
                "SELECT COUNT(*) FROM mw_notifications WHERE user_id = $1 AND is_read = FALSE AND (company_id = $2 OR company_id IS NULL)",
                user_id, company_id,
            )
        return await conn.fetchval(
            "SELECT COUNT(*) FROM mw_notifications WHERE user_id = $1 AND is_read = FALSE",
            user_id,
        )


async def mark_read(user_id: UUID, notification_ids: list[UUID]) -> int:
    """Mark specific notifications as read. Returns count updated."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE mw_notifications SET is_read = TRUE WHERE user_id = $1 AND id = ANY($2::uuid[])",
            user_id, notification_ids,
        )
    return int(result.split()[-1])


async def mark_all_read(user_id: UUID) -> int:
    """Mark all notifications as read for a user."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE mw_notifications SET is_read = TRUE WHERE user_id = $1 AND is_read = FALSE",
            user_id,
        )
    return int(result.split()[-1])


async def _send_notification_email(
    user_id: UUID, subject: str, title: str, body: Optional[str], link: Optional[str]
) -> None:
    """Send a simple notification email to the user."""
    from ...core.services.email import get_email_service

    email_svc = get_email_service()
    if not email_svc.is_configured():
        return

    async with get_connection() as conn:
        user = await conn.fetchrow("SELECT email, name FROM users WHERE id = $1", user_id)
    if not user:
        return

    html_body = f"<h3>{title}</h3>"
    if body:
        html_body += f"<p>{body}</p>"
    if link:
        full_link = link if link.startswith("http") else f"https://matcharecruit.com{link}"
        html_body += f'<p><a href="{full_link}">View in Matcha Work</a></p>'

    await email_svc.send_email(
        to_email=user["email"],
        to_name=user.get("name"),
        subject=subject,
        html_content=html_body,
    )
