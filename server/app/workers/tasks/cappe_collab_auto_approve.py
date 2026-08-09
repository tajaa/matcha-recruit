"""Reconcile overdue active Cappe collab deliverables."""
import asyncio
import logging
from app.cappe.services import collab as collab_svc
from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

async def _run() -> dict:
    conn = await get_db_connection()
    try:
        row = await scheduler_settings_row(conn, "cappe_collab_auto_approve")
        if not row or not row["enabled"]:
            return {"skipped": True, "reason": "scheduler_disabled" if row else "scheduler_not_registered"}
        cap = row["max_per_cycle"] or 50
        offers = await conn.fetch("SELECT o.*, ba.name AS brand_name FROM cappe_collab_offers o JOIN cappe_accounts ba ON ba.id=o.brand_account_id WHERE o.status='active' ORDER BY o.last_action_at ASC LIMIT $1", cap)
        approved = 0
        for offer in offers:
            result = await collab_svc.auto_approve_overdue(conn, offer["id"])
            if result["deliverables"] or result["fired_payments"]:
                await collab_svc.notify_auto_approve(conn, offer["id"], offer, result)
                approved += 1
        return {"checked": len(offers), "auto_approved": approved}
    finally:
        await conn.close()

@celery_app.task(bind=True, max_retries=1)
def run_cappe_collab_auto_approve(self):
    try:
        return {"status": "success", **asyncio.run(_run())}
    except Exception as exc:
        logger.exception("Cappe collab auto-approve failed")
        raise self.retry(exc=exc, countdown=60)
