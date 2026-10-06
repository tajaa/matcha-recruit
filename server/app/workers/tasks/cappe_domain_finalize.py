"""Scheduled reconciliation for Cappe domain purchases.

Three jobs, all "something that should have happened in a request didn't":

1. **Stranded registrations.** `finalize_domain_registration` claims its row
   with an UPDATE that bumps `updated_at`, so the 15-minute predicate below
   means "no worker has touched this registration for 15 minutes" — i.e. the
   webhook's background task died mid-flight — rather than merely "it has been
   registering a while". Without the claim this task could re-enter a
   registration another process was still running.
2. **Refunds still owed.** A registration that failed after payment is
   refunded; if THAT failed the row is `refund_status='owed'` and is retried
   here until it lands (`refund_failed_registration`).
3. **Abandoned purchases.** A checkout started and never paid used to leave a
   `pending` row for ever. Past `PURCHASE_ABANDONED_AFTER` its Stripe session
   is closed and the row removed — or, if it turns out the buyer paid and the
   webhook was lost, registration is started (`reap_abandoned_purchase`).
"""

import asyncio
import logging

from app.cappe.services.domain_register import (
    PURCHASE_ABANDONED_AFTER,
    finalize_domain_registration,
    reap_abandoned_purchase,
    refund_failed_registration,
)

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        setting = await scheduler_settings_row(conn, "cappe_domain_finalize")
        if not setting or not setting["enabled"]:
            return {"skipped": True}
        cap = setting["max_per_cycle"] or 20
        rows = await conn.fetch(
            "SELECT id FROM cappe_domains WHERE status = 'registering' "
            "AND updated_at < NOW() - INTERVAL '15 minutes' ORDER BY updated_at ASC LIMIT $1",
            cap,
        )
        owed = await conn.fetch(
            "SELECT id, stripe_payment_intent FROM cappe_domains "
            "WHERE refund_status = 'owed' AND stripe_payment_intent IS NOT NULL "
            "ORDER BY updated_at ASC LIMIT $1",
            cap,
        )
        abandoned = await conn.fetch(
            f"SELECT id, stripe_session_id FROM cappe_domains "
            f"WHERE kind = 'register' AND status = 'pending' "
            f"AND created_at < NOW() - INTERVAL '{PURCHASE_ABANDONED_AFTER}' "
            f"ORDER BY created_at ASC LIMIT $1",
            cap,
        )
    finally:
        # Everything below makes network calls (Porkbun, Stripe, CloudFront) and
        # opens its own short-lived connections; none of it holds this one.
        await conn.close()

    for row in rows:
        await finalize_domain_registration(row["id"])

    refunded = 0
    for row in owed:
        refunded += bool(await refund_failed_registration(row["id"], row["stripe_payment_intent"]))

    reaped: dict[str, int] = {}
    for row in abandoned:
        try:
            outcome = await reap_abandoned_purchase(row["id"], row["stripe_session_id"])
        except Exception:
            logger.exception("cappe domain %s: abandoned-purchase reconcile failed", row["id"])
            outcome = "retry"
        reaped[outcome] = reaped.get(outcome, 0) + 1

    return {
        "stranded": len(rows), "redriven": len(rows),
        "refunds_owed": len(owed), "refunds_settled": refunded,
        "abandoned": reaped,
    }


@celery_app.task(bind=True, max_retries=1)
def run_cappe_domain_finalize(self) -> dict:
    try:
        return {"status": "success", **asyncio.run(_run())}
    except Exception as exc:
        logger.exception("Cappe domain finalization failed")
        raise self.retry(exc=exc, countdown=60)
