"""Durable, post-confirmation manager notifications for shift requests."""

from __future__ import annotations

import json
import logging
from html import escape
from uuid import UUID

from app.core.services import apns_service
from app.core.services.email import get_email_service
from app.core.services.email._shared import _is_reserved_test_domain
from app.config import get_settings
from app.matcha.services.scheduling.schedule_manager_scope import store_manager_recipients_sql

logger = logging.getLogger(__name__)


# A reviewer address that keeps failing is parked after this many sends
# (empsched27) instead of being retried by every sweep forever.
MAX_MANAGER_DELIVERY_ATTEMPTS = 5

# Employees flagged is_manager/is_supervisor who run every store this request
# touches (bell + push; email stays with business admins). Shared with the
# recovery sweep, which passes its own request column.
STORE_MANAGER_RECIPIENTS_SQL = store_manager_recipients_sql("$1")

# A `schedule_*` kind reaches the Matcha Schedule app and never Werk/Espresso
# (apns_service.APP_BUNDLES).
PUSH_KIND = "schedule_request_pending"


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


async def _claim_and_post_in_app(conn, request, recipient_id: UUID, title: str, body: str, link: str) -> bool:
    """Claim the in-app delivery and write its bell row; True only on a fresh
    claim, so a retry never posts (or pushes) twice."""
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
        request["company_id"], request["id"], recipient_id,
    )
    if not in_app_claimed:
        return False
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
        recipient_id, request["company_id"], title, body, link,
        json.dumps({"request_id": str(request["id"])}),
        in_app_claimed,
    )
    return True


async def _push_to_manager(conn, recipient_id: UUID, title: str, body: str, request_id: UUID) -> None:
    """Best-effort: the bell row is the durable record and the app's approvals
    badge catches anything a phone missed, so a push failure never fails the
    delivery."""
    link = f"matchaschedule://manage/requests/{request_id}"
    try:
        await apns_service.send_to_user(
            recipient_id, title, body,
            {"type": PUSH_KIND, "link": link, "metadata": {"request_id": str(request_id), "link": link}},
            kind=PUSH_KIND, conn=conn,
        )
    except Exception:  # noqa: BLE001
        logger.warning("manager push failed for request %s", request_id, exc_info=True)


async def send_manager_ready_notifications(conn, *, request_id: UUID) -> dict[str, int]:
    """Tell every reviewer about a manager-ready request.

    Business admins get the bell row and one email; store managers (employees
    flagged is_manager/is_supervisor who run every store the request touches)
    get the bell row only. Each fresh bell row also pushes to the Matcha
    Schedule app. The delivery row is claimed before sending. A failed email
    counts an attempt (re-claimable after five minutes, parked at
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
    store_managers = await conn.fetch(STORE_MANAGER_RECIPIENTS_SQL, request["id"])
    settings = get_settings()
    service = get_email_service()
    owner = request["owner_name"] or "Employee"
    target = request["target_name"] or "Coworker"
    request_type = request["request_type"]
    summary = (
        f"{owner} and {target} confirmed a {request_type} request."
        if request["counterparty_confirmed_at"] else
        f"{owner} submitted a {request_type} request."
    )
    title = f"Shift {request_type} request awaiting approval"
    body = f"{summary} Review it to approve or deny it."
    link = f"/ops/schedule?tab=requests&request={request['id']}"
    # Disjoint from `recipients`: store managers are role 'employee'.
    for manager in store_managers:
        if await _claim_and_post_in_app(conn, request, manager["id"], title, body, link):
            await _push_to_manager(conn, manager["id"], title, body, request["id"])
    sent = 0
    for recipient in recipients:
        if await _claim_and_post_in_app(conn, request, recipient["id"], title, body, link):
            await _push_to_manager(conn, recipient["id"], title, body, request["id"])
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
    return {"sent": sent, "recipients": len(recipients), "store_managers": len(store_managers)}
