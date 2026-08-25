"""Durable, post-confirmation manager notifications for shift requests."""

from __future__ import annotations

from html import escape
from uuid import UUID

from app.core.services.email import get_email_service
from app.core.services.email._shared import _is_reserved_test_domain
from app.config import get_settings


async def send_manager_ready_notifications(conn, *, request_id: UUID) -> dict[str, int]:
    """Send each company reviewer one email after both employees confirm.

    The delivery row is claimed before sending. A failed provider call releases
    the claim, while an interrupted worker's stale claim is reclaimed by the
    recovery task. Request state is never changed by delivery success or failure.
    """
    request = await conn.fetchrow(
        """
        SELECT r.id, r.company_id, r.request_type, r.counterparty_confirmed_at,
               s.starts_at, s.ends_at,
               TRIM(COALESCE(owner.first_name, '') || ' ' || COALESCE(owner.last_name, '')) AS owner_name,
               TRIM(COALESCE(target.first_name, '') || ' ' || COALESCE(target.last_name, '')) AS target_name
        FROM schedule_requests r
        LEFT JOIN schedule_shifts s ON s.id=r.shift_id
        LEFT JOIN employees owner ON owner.id=r.employee_id
        LEFT JOIN employees target ON target.id=r.target_employee_id
        WHERE r.id=$1 AND r.status='awaiting_manager'
          AND r.counterparty_confirmed_at IS NOT NULL
        """,
        request_id,
    )
    if not request:
        return {"sent": 0, "skipped": 1}
    recipients = await conn.fetch(
        """
        SELECT DISTINCT u.id, u.email, COALESCE(NULLIF(c.name, ''), 'Manager') AS name
        FROM clients c
        JOIN users u ON u.id=c.user_id
        WHERE c.company_id=$1 AND u.role='client' AND u.is_active=true
          AND u.email IS NOT NULL AND u.email <> ''
        """,
        request["company_id"],
    )
    settings = get_settings()
    service = get_email_service()
    sent = 0
    for recipient in recipients:
        claimed = await conn.fetchval(
            """
            INSERT INTO schedule_request_notification_deliveries
                (company_id, request_id, recipient_user_id, event_type)
            VALUES ($1,$2,$3,'manager_ready')
            ON CONFLICT (request_id, recipient_user_id, event_type) DO UPDATE
               SET created_at=NOW()
             WHERE schedule_request_notification_deliveries.sent_at IS NULL
               AND schedule_request_notification_deliveries.created_at < NOW() - INTERVAL '5 minutes'
            RETURNING id
            """,
            request["company_id"], request["id"], recipient["id"],
        )
        if not claimed:
            continue
        email = recipient["email"].strip().lower()
        if not service.is_configured() or _is_reserved_test_domain(email):
            await conn.execute(
                "UPDATE schedule_request_notification_deliveries SET sent_at=NOW() WHERE id=$1", claimed,
            )
            continue
        owner = request["owner_name"] or "Employee"
        target = request["target_name"] or "Coworker"
        subject = "Shift request ready for manager approval"
        link = f"{settings.app_base_url.rstrip('/')}/ops/schedule?tab=requests&request={request['id']}"
        html = (
            f"<p>{escape(owner)} and {escape(target)} have confirmed a {escape(request['request_type'])} request.</p>"
            f"<p><a href=\"{escape(link, quote=True)}\">Review the request</a>. "
            "The schedule remains unchanged until you approve it.</p>"
        )
        try:
            delivered = await service.send_email(email, recipient["name"], subject, html)
        except Exception:
            delivered = False
        if delivered:
            await conn.execute(
                "UPDATE schedule_request_notification_deliveries SET sent_at=NOW() WHERE id=$1", claimed,
            )
            sent += 1
        else:
            await conn.execute("DELETE FROM schedule_request_notification_deliveries WHERE id=$1", claimed)
    return {"sent": sent, "recipients": len(recipients)}
