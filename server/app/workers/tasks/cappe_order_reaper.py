"""Release inventory held by abandoned Cappe storefront orders.

`create_public_order` decrements `cappe_products.inventory` inside the order
transaction, while the order is still `pending` — so an anonymous buyer who
opens Stripe Checkout and walks away holds that stock indefinitely. Until the
2026-09 audit the only restock path was an owner manually transitioning the
order to cancelled/refunded, which means an abandoned cart ate a tenant's stock
until someone noticed, and an attacker could zero a storefront for free.

Stripe's own `checkout.session.expired` webhook is the primary release
(`routes/payments.py`); this task is the backstop for the deliveries that never
arrive — a webhook dropped while the container was swapped, an endpoint that was
not subscribed to the event, a session created before that handler shipped.

Idempotent and conservative:
  * only orders that actually went to Stripe (`stripe_session_id IS NOT NULL`)
    are touched — an owner-created or manual pending order is left alone;
  * `created_at < NOW() - INTERVAL '2 hours'` is well past a real checkout but
    well inside Stripe's own 24-hour session expiry, so a buyer who is still
    paying is never cancelled out from under;
  * the status flip is guarded on `status = 'pending'` and the restock runs in
    the same transaction, so a concurrent webhook and this task cannot both
    restock the same order.
"""

import asyncio
import logging

from app.cappe.services.inventory import restock_order

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

# Stripe Checkout sessions live 24h; 2h is "the buyer is long gone" without
# racing a slow but real checkout.
ABANDONED_AFTER = "2 hours"


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        setting = await scheduler_settings_row(conn, "cappe_order_reaper")
        if not setting or not setting["enabled"]:
            return {"skipped": True}
        cap = setting["max_per_cycle"] or 100

        candidates = await conn.fetch(
            f"""SELECT id, site_id FROM cappe_orders
                 WHERE status = 'pending'
                   AND stripe_session_id IS NOT NULL
                   AND created_at < NOW() - INTERVAL '{ABANDONED_AFTER}'
                 ORDER BY created_at ASC
                 LIMIT $1""",
            cap,
        )

        released = 0
        for cand in candidates:
            # One transaction per order: a restock failure on a single order
            # must not roll back the ones already released this cycle.
            try:
                async with conn.transaction():
                    row = await conn.fetchrow(
                        "UPDATE cappe_orders SET status = 'cancelled', updated_at = NOW() "
                        "WHERE id = $1 AND status = 'pending' RETURNING id, site_id",
                        cand["id"],
                    )
                    if row is None:
                        continue  # a webhook got there first
                    await restock_order(
                        conn, site_id=row["site_id"], order_id=row["id"], reason="restock"
                    )
                released += 1
                logger.info(
                    "cappe order %s cancelled + restocked (abandoned checkout)", cand["id"]
                )
            except Exception:
                logger.exception(
                    "cappe order reaper: failed to release order %s", cand["id"]
                )

        return {"candidates": len(candidates), "released": released}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=1)
def run_cappe_order_reaper(self) -> dict:
    """Cancel + restock Cappe storefront orders abandoned at Stripe Checkout."""
    try:
        return {"status": "success", **asyncio.run(_run())}
    except Exception as exc:
        logger.exception("Cappe order reaper failed")
        raise self.retry(exc=exc, countdown=60)
