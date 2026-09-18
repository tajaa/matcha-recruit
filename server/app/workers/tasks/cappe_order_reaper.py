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
  * **the Stripe session is closed before the order is released.** A Checkout
    Session stays payable for 24 hours, far longer than the 2-hour window here,
    so cancelling the order alone would leave a live payment page pointing at an
    order we had thrown away — the buyer pays, the order stays cancelled.
    `expire_checkout_session` closes it and reports the outcome:
      - `expired`  → nobody can pay it any more; release the order;
      - `complete` → the buyer DID finish checkout. Either the webhook is late or
        it is a delayed method (ACH, SEPA) that settles days later. The order
        stays pending; `async_payment_succeeded/failed` decides it.
      - Stripe unreachable → leave the order for the next cycle;
  * the status flip is guarded on `status = 'pending'` and the restock + booking
    release run in the same transaction, so a concurrent webhook and this task
    cannot both release the same order.
"""

import asyncio
import logging

from app.cappe.services.inventory import release_order_bookings, restock_order
from app.cappe.services.stripe_connect import CappeStripeError, get_cappe_stripe

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_settings_row

logger = logging.getLogger(__name__)

# "The buyer is long gone." Safe well inside Stripe's 24h session lifetime only
# because the session is expired before the order is touched (see above).
ABANDONED_AFTER = "2 hours"


async def _run() -> dict:
    conn = await get_db_connection()
    try:
        setting = await scheduler_settings_row(conn, "cappe_order_reaper")
        if not setting or not setting["enabled"]:
            return {"skipped": True}
        cap = setting["max_per_cycle"] or 100

        candidates = await conn.fetch(
            f"""SELECT o.id, o.site_id, o.stripe_session_id, a.stripe_account_id
                  FROM cappe_orders o
                  JOIN cappe_sites s ON s.id = o.site_id
                  JOIN cappe_accounts a ON a.id = s.account_id
                 WHERE o.status = 'pending'
                   AND o.stripe_session_id IS NOT NULL
                   AND o.created_at < NOW() - INTERVAL '{ABANDONED_AFTER}'
                 ORDER BY o.created_at ASC
                 LIMIT $1""",
            cap,
        )

        stripe_client = get_cappe_stripe()
        released = 0
        settling = 0
        for cand in candidates:
            # Close the payment page first. Only an order nobody can pay any
            # more is safe to release.
            if not cand["stripe_account_id"]:
                logger.warning(
                    "cappe order reaper: order %s has no connected account; skipped", cand["id"]
                )
                continue
            try:
                state = await stripe_client.expire_checkout_session(
                    cand["stripe_account_id"], cand["stripe_session_id"]
                )
            except CappeStripeError as exc:
                logger.warning(
                    "cappe order reaper: could not close session for order %s (%s); will retry",
                    cand["id"], exc,
                )
                continue
            if state != "expired":
                # 'complete': checkout finished — paid, or a delayed method
                # still settling. The webhook owns this order's fate.
                settling += 1
                continue

            # One transaction per order: a release failure on a single order
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
                    await release_order_bookings(conn, order_id=row["id"])
                released += 1
                logger.info(
                    "cappe order %s cancelled + released (abandoned checkout)", cand["id"]
                )
            except Exception:
                logger.exception(
                    "cappe order reaper: failed to release order %s", cand["id"]
                )

        return {"candidates": len(candidates), "released": released, "settling": settling}
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
