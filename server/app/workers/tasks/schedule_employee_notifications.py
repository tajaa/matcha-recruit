"""Pool-free delivery and recovery for employee schedule events."""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection
from app.matcha.services.scheduling.employee_schedule_notifications import deliver_pending


async def _deliver():
    conn = await get_db_connection()
    try:
        return await deliver_pending(conn)
    finally:
        await conn.close()


@celery_app.task(name="schedule_employee_notifications.send", bind=True, max_retries=3)
def send_schedule_employee_notifications(self):
    try:
        return asyncio.run(_deliver())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(name="schedule_employee_notifications.recover", bind=True, max_retries=1)
def recover_schedule_employee_notifications(self):
    try:
        return asyncio.run(_deliver())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)
