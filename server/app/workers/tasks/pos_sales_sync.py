"""Scheduled sync for connected POS providers."""

import asyncio
import logging
from datetime import date, timedelta

from app.core.feature_flags import merge_company_features
from app.matcha.services.inventory.pos.sync import sync_pos_connection

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled


logger = logging.getLogger(__name__)


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
        target_date = date.today() - timedelta(days=1)
        for row in rows:
            features = merge_company_features(row["enabled_features"], row["signup_source"])
            if not (features.get("matcha_ops") and features.get("inventory") and features.get("sales_intake")):
                continue
            try:
                await sync_pos_connection(
                    conn,
                    connection_id=row["id"],
                    company_id=row["company_id"],
                    start_date=target_date,
                    end_date=target_date,
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
