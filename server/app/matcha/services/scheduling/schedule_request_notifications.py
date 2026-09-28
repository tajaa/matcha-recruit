"""Durable, post-confirmation manager notifications for shift requests."""

from __future__ import annotations

import json
from html import escape
from uuid import UUID

from app.core.services.email import get_email_service
from app.core.services.email._shared import _is_reserved_test_domain
from app.config import get_settings


# A reviewer address that keeps failing is parked after this many sends
# (empsched27) instead of being retried by every sweep forever.
MAX_MANAGER_DELIVERY_ATTEMPTS = 5


async def mark_manager_ready_notifications_resolved(
    conn, *, company_id: UUID, request_id: UUID,
) -> int:
    """Clear unread manager alerts once a request leaves the approval queue."""
    result = await conn.execute(
        """
        UPDATE mw_notifications
        SET is_read = TRUE
        WHERE company_id = $1
          AND type = 'schedule_request_pending'
          AND is_read = FALSE
          AND metadata->>'request_id' = $2
        """,
        company_id, str(request_id),
    )
    return int(result.split()[-1])


async def reset_manager_ready_deliveries(
    conn, *, company_id: UUID, request_id: UUID,
) -> int:
    """Forget that managers were told about a request that left their queue
    and may return to it.

    Deliveries are keyed (request, recipient, event) and a sent row is never
    re-claimed, so a pickup that goes back to awaiting a coworker and is then
    accepted by someone else would otherwise reach the queue silently: no bell,
    no email, and the recovery sweep counts it as already delivered.
    """
    result = await conn.execute(
        """DELETE FROM schedule_request_notification_deliveries
           WHERE company_id = $1 AND request_id = $2
             AND event_type IN ('manager_ready', 'manager_ready_in_app')""",
        company_id, request_id,
    )
    return int(result.split()[-1])


async def send_manager_ready_notifications(conn, *, request_id: UUID) -> dict[str, int]:
    """Send each company reviewer one email for a manager-ready request.

    The delivery row is claimed before sending. A failed provider call counts
    an attempt (re-claimable after five minutes, parked at
    MAX_MANAGER_DELIVERY_ATTEMPTS), while an interrupted worker's stale claim is
    reclaimed by the recovery task. Request state is never changed by delivery
    success or failure.
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
          AND (r.counterparty_confirmed_at IS NOT NULL
               OR r.request_type IN ('drop', 'unavailable', 'availability', 'claim'))
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
        link = f"/ops/schedule?tab=requests&request={request['id']}"
        in_app_claimed = await conn.fetchval(
            """
            INSERT INTO schedule_request_notification_deliveries
                (company_id, request_id, recipient_user_id, event_type)
            VALUES ($1,$2,$3,'manager_ready_in_app')
            ON CONFLICT (request_id, recipient_user_id, event_type) DO UPDATE
               SET created_at=NOW()
             WHERE schedule_request_notification_deliveries.sent_at IS NULL
               AND schedule_request_notification_deliveries.failed_at IS NULL
               AND schedule_request_notification_deliveries.created_at < NOW() - INTERVAL '5 minutes'
            RETURNING id
            """,
            request["company_id"], request["id"], recipient["id"],
        )
        if in_app_claimed:
            owner = request["owner_name"] or "Employee"
            target = request["target_name"] or "Coworker"
            request_type = request["request_type"]
            summary = (
                f"{owner} and {target} confirmed a {request_type} request."
                if request["counterparty_confirmed_at"] else
                f"{owner} submitted a {request_type} request."
            )
            # One statement commits the bell row and its outbox receipt together,
            # preventing retry recovery from creating duplicate manager alerts.
            await conn.execute(
                """
                WITH notification AS (
                    INSERT INTO mw_notifications (user_id, company_id, type, title, body, link, metadata)
                    VALUES ($1, $2, 'schedule_request_pending', $3, $4, $5, $6::jsonb)
                )
                UPDATE schedule_request_notification_deliveries
                SET sent_at=NOW() WHERE id=$7
                """,
                recipient["id"], request["company_id"],
                f"Shift {request_type} request awaiting approval",
                f"{summary} Review it to approve or deny it.",
                link,
                json.dumps({"request_id": str(request["id"])}),
                in_app_claimed,
            )
        claimed = await conn.fetchval(
            """
            INSERT INTO schedule_request_notification_deliveries
                (company_id, request_id, recipient_user_id, event_type)
            VALUES ($1,$2,$3,'manager_ready')
            ON CONFLICT (request_id, recipient_user_id, event_type) DO UPDATE
               SET created_at=NOW()
             WHERE schedule_request_notification_deliveries.sent_at IS NULL
               AND schedule_request_notification_deliveries.failed_at IS NULL
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
        summary = (
            f"{owner} and {target} confirmed a {request['request_type']} request."
            if request["counterparty_confirmed_at"] else
            f"{owner} submitted a {request['request_type']} request."
        )
        subject = "Shift request ready for manager approval"
        email_link = f"{settings.app_base_url.rstrip('/')}{link}"
        html = (
            f"<p>{escape(summary)}</p>"
            f"<p><a href=\"{escape(email_link, quote=True)}\">Review the request</a>. "
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
            # Keep the row (re-claimable after the 5-minute window) and count
            # the attempt; park it at the cap so a bouncing address cannot hold
            # a place in every sweep.
            await conn.execute(
                """UPDATE schedule_request_notification_deliveries
                   SET attempts = attempts + 1,
                       failed_at = CASE WHEN attempts + 1 >= $2 THEN NOW() ELSE failed_at END
                   WHERE id = $1""",
                claimed, MAX_MANAGER_DELIVERY_ATTEMPTS,
            )
    return {"sent": sent, "recipients": len(recipients)}
