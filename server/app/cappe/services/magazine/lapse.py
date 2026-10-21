"""Stopping a magazine's paid subscriptions, without taking what readers paid for.

Paid subscriptions stop when the writer turns them off (`PUT /sites/{id}/
magazine`) or when the owner can no longer have them — the plan lost
`magazine_paid`, or the account isn't active. Either way the magazine gets
`paid_enabled = false` and `lapsed_at`, and this sweep then sets each reader's
subscription to end with the month they already paid for, and tells them.
The magazine itself stays up for `magazines.GRACE_DAYS` after `lapsed_at`
even without the plan, so those readers can read what they paid for.

Run from the hourly `cappe_comp_expiry` worker task (pool-free: everything
here uses the connection it is given). No Stripe call is made inside a
transaction; a subscription Stripe couldn't update is simply picked up again
on the next run.
"""
from __future__ import annotations

import logging

from ..entitlements import resolve_entitlements
from ..shopper_auth import BILLING_STATUSES

logger = logging.getLogger(__name__)

BATCH = 200


async def _plan_takes_paid(conn, plan, seen: dict) -> bool:
    if plan not in seen:
        seen[plan] = (await resolve_entitlements(plan, conn=conn)).has("magazine_paid")
    return seen[plan]


async def mark_lapsed(conn) -> int:
    """Stop paid subscriptions on magazines whose owner can't have them now."""
    rows = await conn.fetch(
        "SELECT m.site_id, a.plan, a.status FROM cappe_magazines m JOIN cappe_sites s ON s.id = m.site_id "
        "JOIN cappe_accounts a ON a.id = s.account_id WHERE m.paid_enabled"
    )
    seen: dict = {}
    marked = 0
    for r in rows:
        if r["status"] == "active" and await _plan_takes_paid(conn, r["plan"], seen):
            continue
        marked += bool(await conn.fetchval(
            "UPDATE cappe_magazines SET paid_enabled = false, lapsed_at = NOW(), updated_at = NOW() "
            "WHERE site_id = $1 AND paid_enabled RETURNING site_id",
            r["site_id"],
        ))
    return marked


async def wind_down(conn, *, limit: int = BATCH) -> dict:
    """Set the renewing reader subscriptions of stopped magazines to end at
    the period's close, and email each reader once (when Stripe confirms)."""
    from ..email import send_cappe_magazine_ending_email, store_reply_to
    from ..common import site_public_origin
    from ..recurring import sync_subscription
    from ..stripe_connect import CappeStripeError, get_cappe_stripe

    subs = await conn.fetch(
        """SELECT sub.*, s.name AS site_name, s.subdomain, s.custom_domain, s.meta_config,
                  a.email AS owner_email, sh.email AS reader_email, sh.name AS reader_name
             FROM cappe_shopper_subscriptions sub
             JOIN cappe_magazines m ON m.site_id = sub.site_id AND m.lapsed_at IS NOT NULL AND NOT m.paid_enabled
             JOIN cappe_sites s ON s.id = sub.site_id
             JOIN cappe_accounts a ON a.id = s.account_id
             LEFT JOIN cappe_shoppers sh ON sh.id = sub.shopper_id
            WHERE sub.kind = 'magazine' AND sub.stripe_subscription_id IS NOT NULL
              AND NOT sub.cancel_at_period_end AND sub.status = ANY($1::text[])
            ORDER BY sub.created_at LIMIT $2""",
        list(BILLING_STATUSES), limit,
    )
    stopped = failed = 0
    for sub in subs:
        try:
            remote = await get_cappe_stripe().modify_connected_subscription(
                account_id=sub["stripe_account_id"], subscription_id=sub["stripe_subscription_id"],
                cancel_at_period_end=True,
            )
        except CappeStripeError:
            failed += 1
            continue
        async with conn.transaction():
            await conn.fetchval("SELECT id FROM cappe_shopper_subscriptions WHERE id = $1 FOR UPDATE", sub["id"])
            await sync_subscription(conn, sub, remote, None)
        stopped += 1
        if sub["reader_email"]:
            origin = site_public_origin(sub)
            await send_cappe_magazine_ending_email(
                sub["reader_email"], sub["reader_name"], sub["site_name"], sub["current_period_end"],
                origin or None, reply_to=store_reply_to(sub["meta_config"], sub["owner_email"]),
            )
    return {"stopped": stopped, "failed": failed}


async def sweep(conn) -> dict:
    marked = await mark_lapsed(conn)
    result = await wind_down(conn)
    if marked or result["stopped"] or result["failed"]:
        logger.info("magazine lapse sweep: marked=%s stopped=%s failed=%s", marked, result["stopped"],
                    result["failed"])
    return {"marked": marked, **result}
