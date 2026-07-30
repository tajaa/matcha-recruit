"""Idempotency ledger for Stripe webhook events, shared by every consumer.

Lifted out of `core/routes/billing/stripe_webhook.py` so that Cappe's webhooks
can reuse it — services are inside Cappe's allowed import boundary, another
router's private helpers are not.

**Why events are keyed by (consumer, event_id) and not event_id alone.**
Matcha core and Cappe share ONE Stripe platform account and one secret key.
Core's webhook handles `invoice.paid`, `invoice.payment_failed` and
`customer.subscription.deleted`; a Cappe subscription product needs the same
event types. With a single global key, both endpoints receive the identical
`evt_...` and whichever claims first wins — the loser reads the conflict as
"already processed" and skips every side effect, silently, with nothing logged.
The consumer scope makes the endpoints independent.
"""

from __future__ import annotations

import logging

from app.database import get_connection

logger = logging.getLogger(__name__)

# Known consumers. Each owns an independent dedupe namespace.
CONSUMER_CORE = "core"
CONSUMER_CAPPE_PLATFORM = "cappe_platform"
CONSUMER_CAPPE_CONNECT = "cappe_connect"


async def claim_stripe_event(
    event_id: str,
    event_type: str,
    *,
    consumer: str = CONSUMER_CORE,
) -> bool:
    """Record the event ID for this consumer. Returns True if this is the first
    time this consumer has seen the event, False if it's a retry already
    processed.

    Stripe retries webhook events on transient failures (or any non-2xx
    response). Without dedupe, a retried event would re-execute every side
    effect (feature flips, emails, subscription upserts). The primary key on
    (consumer, event_id) makes the INSERT idempotent — a duplicate inserts no
    row, so we return False. A genuine DB error is re-raised so the webhook
    fails closed and Stripe retries.
    """
    try:
        async with get_connection() as conn:
            inserted = await conn.fetchval(
                """
                INSERT INTO stripe_webhook_events (event_id, event_type, consumer)
                VALUES ($1, $2, $3)
                ON CONFLICT (consumer, event_id) DO NOTHING
                RETURNING event_id
                """,
                event_id,
                event_type,
                consumer,
            )
        return inserted is not None
    except Exception:
        # Fail CLOSED: a broken dedupe table (e.g. migration not yet applied)
        # must NOT let side effects run without a durable idempotency record,
        # or a Stripe retry double-processes the money path (double token
        # grants, duplicate feature flips). Surface the error so the webhook
        # returns 500 and Stripe retries — a delayed retry beats a double-spend.
        logger.exception(
            "stripe_webhook_events insert failed for %s (%s, consumer=%s) — failing closed",
            event_id,
            event_type,
            consumer,
        )
        raise


async def release_stripe_event(event_id: str, *, consumer: str = CONSUMER_CORE) -> None:
    """Delete the dedupe row so Stripe retries can re-process this event.

    Called when a handler raises after we've already claimed the event_id.
    Without this, the next Stripe retry would hit the dedupe gate and skip
    the handler — leaving the caller (paid customer) permanently in a
    half-activated state.
    """
    if not event_id:
        return
    try:
        async with get_connection() as conn:
            await conn.execute(
                "DELETE FROM stripe_webhook_events WHERE event_id = $1 AND consumer = $2",
                event_id,
                consumer,
            )
    except Exception as exc:
        logger.warning("stripe_webhook_events release failed: %s", exc)
