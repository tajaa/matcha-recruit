"""Scheduled sync for connected POS providers."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

from app.core.feature_flags import merge_company_features
from app.matcha.services.inventory.pos.sync import sync_pos_connection

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled


logger = logging.getLogger(__name__)


def previous_completed_business_date(timezone_name: str, now: datetime | None = None) -> date:
    """Return yesterday in the store's local timezone.

    Scheduled sync runs in UTC, but Square business dates are local to each
    bound location.  A naive test timestamp is treated as UTC for determinism.
    """
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:
        timezone = dt_timezone.utc
    if now is None:
        local_now = datetime.now(timezone)
    elif now.tzinfo is None:
        local_now = now.replace(tzinfo=dt_timezone.utc).astimezone(timezone)
    else:
        local_now = now.astimezone(timezone)
    return local_now.date() - timedelta(days=1)


async def _run() -> dict:
    conn = await get_db_connection()
    processed = 0
    failed = 0
    try:
        if not await scheduler_enabled(conn, "pos_sales_sync", default=False):
            return {"processed": 0, "failed": 0, "disabled": True}
        rows = await conn.fetch(
            """
            SELECT p.*, c.enabled_features, c.signup_source
            FROM inventory_pos_connections p
            JOIN companies c ON c.id=p.company_id
            WHERE p.status='connected' AND c.deleted_at IS NULL
            ORDER BY p.updated_at
            LIMIT 25
            """
        )
        for row in rows:
            features = merge_company_features(row["enabled_features"], row["signup_source"])
            if not (features.get("matcha_ops") and features.get("inventory") and features.get("sales_intake")):
                continue
            try:
                bindings = await conn.fetch(
                    """SELECT id, timezone FROM inventory_pos_location_bindings
                       WHERE connection_id=$1 AND company_id=$2 ORDER BY id""",
                    row["id"], row["company_id"],
                )
                if not bindings:
                    target_date = previous_completed_business_date("UTC")
                    await sync_pos_connection(
                        conn,
                        connection_id=row["id"],
                        company_id=row["company_id"],
                        start_date=target_date,
                        end_date=target_date,
                    )
                    processed += 1
                    continue
                for binding in bindings:
                    target_date = previous_completed_business_date(binding["timezone"])
                    await sync_pos_connection(
                        conn,
                        connection_id=row["id"],
                        company_id=row["company_id"],
                        start_date=target_date,
                        end_date=target_date,
                        binding_id=binding["id"],
                    )
                    processed += 1
            except Exception:
                failed += 1
                logger.exception("pos_sales_sync: connection %s failed", row["id"])
    finally:
        await conn.close()
    return {"processed": processed, "failed": failed}


@celery_app.task(bind=True, max_retries=3)
def run_pos_sales_sync(self):
    return asyncio.run(_run())
