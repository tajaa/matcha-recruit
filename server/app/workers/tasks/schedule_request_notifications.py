"""Pool-free Celery delivery for bilateral request manager notifications."""

import asyncio
from uuid import UUID

from ..celery_app import celery_app
from ..utils import get_db_connection
from app.matcha.services.scheduling.schedule_request_notifications import send_manager_ready_notifications


async def _send(request_id: UUID) -> dict[str, int]:
    conn = await get_db_connection()
    try:
        return await send_manager_ready_notifications(conn, request_id=request_id)
    finally:
        await conn.close()


async def _send_pending() -> dict[str, int]:
    """Recover notifications if the broker was unavailable after commit."""
    conn = await get_db_connection()
    try:
        rows = await conn.fetch(
            """
            SELECT r.id
            FROM schedule_requests r
            WHERE r.status='awaiting_manager' AND r.counterparty_confirmed_at IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM schedule_request_notification_deliveries d
                  WHERE d.request_id=r.id AND d.event_type='manager_ready'
              )
            ORDER BY r.updated_at ASC
            LIMIT 500
            """
        )
        sent = 0
        for row in rows:
            result = await send_manager_ready_notifications(conn, request_id=row["id"])
            sent += result.get("sent", 0)
        return {"sent": sent, "requests": len(rows)}
    finally:
        await conn.close()


@celery_app.task(name="schedule_request_notifications.send", bind=True, max_retries=3)
def send_schedule_request_notifications(self, request_id: str):
    try:
        return asyncio.run(_send(UUID(request_id)))
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="schedule_request_notifications.recover", bind=True, max_retries=1)
def recover_schedule_request_notifications(self):
    try:
        return asyncio.run(_send_pending())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)
