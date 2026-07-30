"""Celery task: drop Cappe accounts whose comp has run out back to free.

`cappe_subscriptions.comped_until` is what makes a comp *temporary*, but nothing
reads it on the request path — `_materialize_plan` writes the comped tier onto
`cappe_accounts.plan` and every entitlement lookup reads that column. Without
this sweep a comp "until March" is a comp forever, which quietly turns every
goodwill grant into a permanent free plan.

Gated on `scheduler_settings.task_key = 'cappe_comp_expiry'`. Idempotent and
set-based: expiring a comp cancels its row, so the next run does not see it
again, and an account that has since started paying for real is skipped rather
than downgraded.
"""

import asyncio

from ..celery_app import celery_app
from ..utils import get_db_connection, scheduler_enabled


async def _dispatch_cappe_comp_expiry() -> dict:
    conn = await get_db_connection()
    try:
        if not await scheduler_enabled(conn, "cappe_comp_expiry", default=False):
            print("[Cappe Comps] Scheduler disabled, skipping.")
            return {"expired": 0, "skipped": True}

        # Imported lazily: the worker is pool-free and this module pulls in the
        # Stripe service chain, which the sweep itself does not need.
        from app.cappe.services.billing import expire_lapsed_comps

        expired = await expire_lapsed_comps(conn)
    finally:
        await conn.close()

    print(f"[Cappe Comps] expired={expired}")
    return {"expired": expired}


@celery_app.task(name="cappe.comp_expiry", bind=True, max_retries=1)
def run_cappe_comp_expiry(self):
    """Return accounts with a lapsed comp to the free plan."""
    try:
        return asyncio.run(_dispatch_cappe_comp_expiry())
    except Exception as e:
        print(f"[Cappe Comps] Task failed: {e}")
        raise self.retry(exc=e, countdown=300)
