"""Celery task: Cappe booking reminders.

Runs on worker startup when the `cappe_booking_reminders` scheduler row is
enabled (default off). Emails each customer a single reminder ~24h before a
confirmed booking. Claim-before-send (stamp reminder_sent_at, only send if the
claim won) so the 15-min re-dispatch never double-sends.
"""
import asyncio
from datetime import datetime, timezone

from app.cappe.services.email import (
    booking_manage_url,
    format_when,
    send_cappe_booking_reminder_email,
)
from app.cappe.services.reminders import reminder_due
from app.core.services.email._shared import _is_reserved_test_domain

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

REMINDER_WINDOW_HOURS = 24
DEFAULT_MAX_PER_CYCLE = 200


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        row = await scheduler_settings_row(conn, "cappe_booking_reminders")
        if not row:
            return {"skipped": True, "reason": "scheduler_not_registered"}
        if not row["enabled"]:
            print("[Cappe Booking Reminders] Scheduler disabled, skipping.")
            return {"skipped": True, "reason": "scheduler_disabled"}

        cap = row["max_per_cycle"] or DEFAULT_MAX_PER_CYCLE
        if cap <= 0:
            cap = DEFAULT_MAX_PER_CYCLE

        bookings = await conn.fetch(
            """SELECT b.id, b.access_token, b.status, b.starts_at, b.reminder_sent_at,
                      b.customer_email, b.customer_name,
                      bt.name AS type_name, s.name AS site_name, s.timezone
               FROM cappe_bookings b
               JOIN cappe_sites s ON s.id = b.site_id
               LEFT JOIN cappe_booking_types bt ON bt.id = b.booking_type_id
               WHERE b.status = 'confirmed' AND b.reminder_sent_at IS NULL
                 AND b.customer_email IS NOT NULL
                 AND b.starts_at > NOW()
                 AND b.starts_at <= NOW() + ($1 * INTERVAL '1 hour')
               ORDER BY b.starts_at ASC
               LIMIT $2""",
            REMINDER_WINDOW_HOURS, cap,
        )
        if not bookings:
            return {"checked": 0, "sent": 0, "skipped": 0}

        now_utc = datetime.now(timezone.utc)
        sent = 0
        skipped = 0
        for b in bookings:
            email = b["customer_email"]
            # Reserved/test domains never deliver — stamp so we stop re-scanning.
            if not email or _is_reserved_test_domain(email):
                await conn.execute(
                    "UPDATE cappe_bookings SET reminder_sent_at = NOW() WHERE id = $1", b["id"]
                )
                skipped += 1
                continue
            # Defensive re-check of the window (SQL already filters this).
            if not reminder_due(b["starts_at"], now_utc, b["status"], b["reminder_sent_at"], REMINDER_WINDOW_HOURS):
                skipped += 1
                continue
            # Claim: only the updater that flips NULL→NOW() may send.
            claimed = await conn.fetchval(
                "UPDATE cappe_bookings SET reminder_sent_at = NOW() "
                "WHERE id = $1 AND reminder_sent_at IS NULL RETURNING id",
                b["id"],
            )
            if not claimed:
                skipped += 1
                continue
            await send_cappe_booking_reminder_email(
                email, b["customer_name"], b["site_name"], b["type_name"] or "Booking",
                format_when(b["starts_at"], b["timezone"]), booking_manage_url(b["access_token"]),
            )
            sent += 1

        return {"checked": len(bookings), "sent": sent, "skipped": skipped}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_cappe_booking_reminders(self) -> dict:
    """Scan confirmed Cappe bookings and email pre-start reminders."""
    print("[Cappe Booking Reminders] Running scheduler...")
    try:
        result = asyncio.run(_run())
        print(f"[Cappe Booking Reminders] Completed: {result}")
        return {"status": "success", **result}
    except Exception as exc:
        print(f"[Cappe Booking Reminders] Failed: {exc}")
        raise self.retry(exc=exc, countdown=60)
