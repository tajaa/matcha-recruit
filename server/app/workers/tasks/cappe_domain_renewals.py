"""Celery task: renew Cappe domains by charging the tenant's saved card.

Domains we register via Porkbun are 1-year. Porkbun's own account-level
auto-renew keeps the registration alive (billing US); this task's job is to
RECOUP from the tenant before expiry, and to lapse + stop Porkbun auto-renew for
domains whose card fails so we stop paying for a domain nobody's paying us for.

Gated on `scheduler_settings.task_key = 'cappe_domain_renewals'`. Idempotent:
- a successful charge bumps expires_at +1yr → out of the window, no re-charge;
- the Stripe idempotency key (per domain + expiry) dedupes retries within 24h,
  so the hourly worker restart can't double-charge or hammer a declined card.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled

# Start attempting renewal this many days before expiry (the dunning window).
_RENEW_WINDOW_DAYS = 14


async def _dispatch_cappe_domain_renewals() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "cappe_domain_renewals", default=False):
            print("[Cappe Renewals] Scheduler disabled, skipping.")
            return {"renewed": 0, "skipped": True}

        rows = await conn.fetch(
            """SELECT id, domain, retail_cents, stripe_customer_id, expires_at,
                      (expires_at < NOW()) AS past_due,
                      to_char(expires_at, 'YYYY-MM-DD') AS expiry_key
                 FROM cappe_domains
                WHERE kind = 'register' AND status = 'active' AND auto_renew
                  AND expires_at IS NOT NULL
                  AND expires_at < NOW() + ($1 || ' days')::interval""",
            str(_RENEW_WINDOW_DAYS),
        )
    finally:
        await conn.close()

    if not rows:
        return {"renewed": 0, "failed": 0, "lapsed": 0}

    from app.cappe.services.stripe_connect import CappeStripeError, get_cappe_stripe
    from app.cappe.services.porkbun import PorkbunError, get_porkbun

    cs = get_cappe_stripe()
    renewed = failed = lapsed = 0

    for r in rows:
        if not r["stripe_customer_id"] or not r["retail_cents"]:
            print(f"[Cappe Renewals] {r['domain']}: no saved card/price, skipping.")
            continue
        try:
            await cs.charge_off_session(
                customer_id=r["stripe_customer_id"],
                amount_cents=int(r["retail_cents"]),
                currency="usd",
                metadata={"type": "cappe_domain_renewal", "domain_id": str(r["id"])},
                idempotency_key=f"cappe-renew-{r['id']}-{r['expiry_key']}",
            )
        except CappeStripeError as exc:
            failed += 1
            print(f"[Cappe Renewals] {r['domain']}: charge failed: {exc}")
            # Past expiry + still can't collect → lapse it and stop our Porkbun cost.
            if r["past_due"]:
                conn2 = await get_db_connection()
                try:
                    await conn2.execute(
                        "UPDATE cappe_domains SET status = 'expired', updated_at = NOW() WHERE id = $1",
                        r["id"],
                    )
                finally:
                    await conn2.close()
                try:
                    await get_porkbun().set_auto_renew(r["domain"], False)
                except PorkbunError:
                    pass
                lapsed += 1
            continue

        conn2 = await get_db_connection()
        try:
            await conn2.execute(
                "UPDATE cappe_domains SET expires_at = GREATEST(expires_at, NOW()) + INTERVAL '1 year', "
                "updated_at = NOW() WHERE id = $1",
                r["id"],
            )
        finally:
            await conn2.close()
        renewed += 1
        print(f"[Cappe Renewals] {r['domain']}: renewed +1yr.")

    print(f"[Cappe Renewals] renewed={renewed} failed={failed} lapsed={lapsed}")
    return {"renewed": renewed, "failed": failed, "lapsed": lapsed}


@celery_app.task(name="cappe.domain_renewals", bind=True, max_retries=1)
def run_cappe_domain_renewals(self):
    """Charge tenants for domains nearing expiry; lapse non-payers."""
    try:
        return asyncio.run(_dispatch_cappe_domain_renewals())
    except Exception as e:
        print(f"[Cappe Renewals] Task failed: {e}")
        raise self.retry(exc=e, countdown=300)
