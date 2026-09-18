"""Celery task: send double-opt-in confirmations for imported Cappe contacts.

On-demand (`.delay(site_id)` from the client-import routes), not scheduled.

Why a worker and not a FastAPI BackgroundTask: a 5,000-row import is minutes of
paced sending, and an in-process task dies with the container on the next
blue/green deploy — the rows stay `pending_confirmation` forever with no mail
ever sent. Here every confirmation is **claimed before it is sent**
(`confirm_sent_at` stamped by a conditional UPDATE), so a re-dispatch, a retry,
or two overlapping runs never mail the same person twice, and anything a dead
worker left unclaimed is picked up by the next dispatch for that site.

A send that fails **releases its claim** (`confirm_sent_at` back to NULL), so
the next dispatch retries it; without that a transient provider outage stranded
the row `pending_confirmation` for ever, since only unclaimed rows are picked
up. The sender reports failure by returning False, not by raising, so the
return value is what is checked. A released row is skipped for the rest of this
run, and a run of consecutive failures ends it — that is an outage, not a bad
address, and hammering a dead provider helps nobody.

Failures are logged by subscriber id, never by address.
"""
import asyncio
import logging

from app.cappe.services.email import send_cappe_subscribe_confirm_email, subscribe_confirm_url

from ..celery_app import celery_app
from ..utils import get_db_connection

logger = logging.getLogger(__name__)

THROTTLE_SECONDS = 0.1
# One dispatch never sends more than this; the per-account daily cap in the
# route is what bounds how many rows can be waiting in the first place.
MAX_PER_RUN = 5000
# This many failures in a row means the provider is down; stop and let the
# released rows wait for the next dispatch.
MAX_CONSECUTIVE_FAILURES = 5


async def _run(site_id: str) -> dict:
    conn = await get_db_connection()
    try:
        site_name = await conn.fetchval("SELECT name FROM cappe_sites WHERE id = $1", site_id)
        if site_name is None:
            return {"skipped": True, "reason": "site_not_found"}

        sent = failed = 0
        consecutive = 0
        released: list = []  # failed this run — not re-claimed until the next one
        for _ in range(MAX_PER_RUN):
            # Claim exactly one row. SKIP LOCKED keeps two overlapping runs from
            # queueing behind each other on the same subscriber.
            row = await conn.fetchrow(
                """UPDATE cappe_subscribers SET confirm_sent_at = NOW()
                    WHERE id = (SELECT id FROM cappe_subscribers
                                 WHERE site_id = $1 AND status = 'pending_confirmation'
                                   AND confirm_token IS NOT NULL AND confirm_sent_at IS NULL
                                   AND id <> ALL($2::uuid[])
                                 ORDER BY created_at
                                 LIMIT 1 FOR UPDATE SKIP LOCKED)
                RETURNING id, email, name, confirm_token""",
                site_id, released,
            )
            if row is None:
                break
            try:
                ok = await send_cappe_subscribe_confirm_email(
                    row["email"], row["name"], site_name,
                    subscribe_confirm_url(str(row["confirm_token"])),
                )
            except Exception as exc:
                ok = False
                logger.warning(
                    "[Cappe Subscribe Confirm] send raised for subscriber %s (%s)",
                    row["id"], type(exc).__name__,
                )
            if ok:
                sent += 1
                consecutive = 0
            else:
                failed += 1
                consecutive += 1
                released.append(row["id"])
                await conn.execute(
                    "UPDATE cappe_subscribers SET confirm_sent_at = NULL "
                    "WHERE id = $1 AND status = 'pending_confirmation'",
                    row["id"],
                )
                logger.warning(
                    "[Cappe Subscribe Confirm] send failed for subscriber %s; claim released",
                    row["id"],
                )
                if consecutive >= MAX_CONSECUTIVE_FAILURES:
                    logger.error(
                        "[Cappe Subscribe Confirm] %d sends in a row failed for site %s; "
                        "stopping this run", consecutive, site_id,
                    )
                    break
            await asyncio.sleep(THROTTLE_SECONDS)
        return {"sent": sent, "failed": failed}
    finally:
        await conn.close()


@celery_app.task(bind=True, max_retries=0)
def run_cappe_subscribe_confirm(self, site_id: str) -> dict:
    """Mail pending double-opt-in confirmations for one site."""
    try:
        return {"status": "success", **asyncio.run(_run(site_id))}
    except Exception:
        logger.exception("[Cappe Subscribe Confirm] failed for site %s", site_id)
        raise
