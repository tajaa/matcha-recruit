"""Prune expired mobile sessions without touching live refresh tokens."""

import asyncio

from app.config import get_settings
from app.workers.celery_app import celery_app
from app.workers.utils import get_db_connection


_BATCH_SIZE = 1000


async def _prune_device_sessions() -> dict[str, int | bool]:
    settings = get_settings()
    # A token's absolute deadline is measured from its first login. Keep one
    # extra day for clock skew and the gap between row creation and JWT issue.
    retention_days = (settings.jwt_session_absolute_expire_hours + 23) // 24 + 1
    conn = await get_db_connection()
    try:
        # Worker startup may precede the application migration.
        if not await conn.fetchval("SELECT to_regclass('auth_device_sessions')"):
            return {"skipped": True, "deleted": 0}
        result = await conn.execute(
            """WITH expired AS (
                   SELECT id FROM auth_device_sessions
                    WHERE created_at < NOW() - ($1::integer * INTERVAL '1 day')
                    ORDER BY created_at
                    LIMIT $2
                    FOR UPDATE SKIP LOCKED
               )
               DELETE FROM auth_device_sessions AS ds
                USING expired
                WHERE ds.id = expired.id""",
            retention_days, _BATCH_SIZE,
        )
        return {"skipped": False, "deleted": int(result.split()[-1])}
    finally:
        await conn.close()


@celery_app.task(name="auth.prune_device_sessions")
def prune_device_sessions() -> dict[str, int | bool]:
    """Run one bounded cleanup batch on each hourly worker restart."""
    return asyncio.run(_prune_device_sessions())
