"""Durable employee schedule bell and APNs notifications.

Routes stage delivery rows in their own schedule-write transaction. Celery
processes those rows after commit; its recovery sweep finds broker misses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID

from app.core.services import apns_service


def wall_time(value: datetime | str | None) -> str | None:
    """Render the scheduler's UTC wall clock without device-local conversion."""
    if value is None:
        return None
    instant = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if instant.tzinfo is not None:
        instant = instant.astimezone(timezone.utc)
    hour = instant.hour % 12 or 12
    return f"{instant:%a %b} {instant.day}, {hour}:{instant.minute:02d} {'AM' if instant.hour < 12 else 'PM'}"


async def stage_request_event(
    conn, *, company_id: UUID, request_id: UUID, event_type: str,
    recipient_employee_ids: list[UUID], dedupe_key: str,
    decision: str | None = None,
) -> int:
    """Insert one durable delivery per recipient inside the caller's transaction."""
    if not recipient_employee_ids:
        return 0
    request = await conn.fetchrow(
        """SELECT r.shift_id, s.starts_at, s.role
           FROM schedule_requests r
           LEFT JOIN schedule_shifts s ON s.id=r.shift_id
           WHERE r.id=$1 AND r.company_id=$2""",
        request_id, company_id,
    )
    if not request:
        return 0
    recipients = await conn.fetch(
        """SELECT DISTINCT user_id FROM employees
           WHERE org_id=$1 AND id=ANY($2::uuid[]) AND user_id IS NOT NULL""",
        company_id, recipient_employee_ids,
    )
    payload = json.dumps({
        "request_id": str(request_id),
        "shift_id": str(request["shift_id"]) if request["shift_id"] else None,
        "starts_at": request["starts_at"].isoformat() if request["starts_at"] else None,
        "role": request["role"],
        "decision": decision,
    })
    for row in recipients:
        await conn.execute(
            """INSERT INTO schedule_employee_notification_deliveries
                   (company_id, recipient_user_id, event_type, dedupe_key, payload)
               VALUES ($1,$2,$3,$4,$5::jsonb)
               ON CONFLICT (recipient_user_id, event_type, dedupe_key) DO NOTHING""",
            company_id, row["user_id"], event_type, dedupe_key, payload,
        )
    return len(recipients)


async def stage_publish_events(
    conn, *, company_id: UUID, shift_ids: list[UUID], batch_id: UUID,
) -> int:
    """One publish notification per assigned employee for this publish call."""
    if not shift_ids:
        return 0
    rows = await conn.fetch(
        """SELECT e.user_id, count(DISTINCT s.id) AS shift_count,
                  min(s.starts_at) AS first_starts_at
           FROM schedule_shifts s
           JOIN schedule_shift_assignments a ON a.shift_id=s.id
           JOIN employees e ON e.id=a.employee_id AND e.org_id=$1
           WHERE s.company_id=$1 AND s.id=ANY($2::uuid[])
             AND e.user_id IS NOT NULL AND a.status <> 'declined'
           GROUP BY e.user_id""",
        company_id, shift_ids,
    )
    for row in rows:
        await conn.execute(
            """INSERT INTO schedule_employee_notification_deliveries
                   (company_id, recipient_user_id, event_type, dedupe_key, payload)
               VALUES ($1,$2,'schedule_published',$3,$4::jsonb)
               ON CONFLICT (recipient_user_id, event_type, dedupe_key) DO NOTHING""",
            company_id, row["user_id"], str(batch_id), json.dumps({
                "batch_id": str(batch_id), "shift_count": row["shift_count"],
                "starts_at": row["first_starts_at"].isoformat(),
            }),
        )
    return len(rows)


def _render(event_type: str, payload: dict) -> tuple[str, str, str]:
    when = wall_time(payload.get("starts_at"))
    context = f" on {when}" if when else ""
    request_id = payload.get("request_id")
    if event_type == "schedule_offer_received":
        return "Swap offer received", f"A coworker offered you a shift swap{context}.", f"matchaschedule://requests/{request_id}"
    if event_type == "schedule_request_accepted":
        return "Shift request accepted", f"Your coworker accepted your request{context}. It is ready for manager review.", f"matchaschedule://requests/{request_id}"
    if event_type == "schedule_request_withdrawn":
        return "Shift request withdrawn", f"Your coworker withdrew from your request{context}.", f"matchaschedule://requests/{request_id}"
    if event_type == "schedule_request_decided":
        decision = payload.get("decision") or "reviewed"
        return "Schedule request reviewed", f"Your request{context} was {decision}.", f"matchaschedule://requests/{request_id}"
    if event_type == "schedule_published":
        count = int(payload.get("shift_count") or 0)
        return "Schedule published", f"{count} new shift{'s' if count != 1 else ''} published. First shift: {when or 'see schedule'}.", "matchaschedule://schedule"
    raise ValueError(f"Unknown schedule notification event: {event_type}")


async def deliver_one(conn, delivery_id: UUID) -> bool:
    """Lock, create the bell row, send APNs, and mark delivered atomically."""
    async with conn.transaction():
        row = await conn.fetchrow(
            """SELECT id, company_id, recipient_user_id, event_type, dedupe_key, payload
               FROM schedule_employee_notification_deliveries
               WHERE id=$1 AND sent_at IS NULL FOR UPDATE SKIP LOCKED""",
            delivery_id,
        )
        if not row:
            return False
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        title, body, link = _render(row["event_type"], payload)
        metadata = {**payload, "link": link}
        await conn.execute(
            """INSERT INTO mw_notifications
                   (user_id, company_id, type, title, body, link, metadata)
               VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb)""",
            row["recipient_user_id"], row["company_id"], row["event_type"],
            title, body, link, json.dumps(metadata),
        )
        await apns_service.send_to_user(
            row["recipient_user_id"], title, body,
            {"type": row["event_type"], "link": link, "metadata": metadata},
            kind=row["event_type"], conn=conn,
        )
        await conn.execute(
            "UPDATE schedule_employee_notification_deliveries SET sent_at=NOW() WHERE id=$1",
            delivery_id,
        )
        return True


async def deliver_pending(conn, *, limit: int = 500) -> dict[str, int]:
    rows = await conn.fetch(
        """SELECT id FROM schedule_employee_notification_deliveries
           WHERE sent_at IS NULL ORDER BY created_at, id LIMIT $1""",
        limit,
    )
    sent = 0
    first_error = None
    for row in rows:
        try:
            sent += int(await deliver_one(conn, row["id"]))
        except Exception as exc:
            # One bad delivery must not hold the entire queue behind it.
            if first_error is None:
                first_error = exc
    if first_error is not None:
        raise first_error
    return {"sent": sent, "pending": len(rows)}


def dispatch_events() -> None:
    """Wake delivery after commit; the scheduled sweep covers broker outages."""
    from app.workers.tasks.schedule_employee_notifications import send_schedule_employee_notifications
    try:
        send_schedule_employee_notifications.delay()
    except Exception:
        pass
