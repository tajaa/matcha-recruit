"""Who can read a magazine's paid stories.

A reader (a `cappe_shoppers` row on the magazine's site) has paid access
while they hold a magazine subscription that Stripe still counts as paying
(`active`, `trialing`, or `past_due` while Stripe retries the card), or a comp
from the writer that is neither revoked nor expired. A subscription set to
end at the period's close stays `active` until then, so a reader who cancels
keeps the month they paid for.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

PAYING_STATUSES = ("active", "trialing", "past_due")


async def has_paid_access(conn, site_id: UUID, shopper_id: UUID) -> bool:
    return bool(await conn.fetchval(
        """SELECT 1 FROM cappe_shopper_subscriptions
            WHERE site_id = $1 AND shopper_id = $2 AND kind = 'magazine' AND status = ANY($3::text[])
           UNION ALL
           SELECT 1 FROM cappe_magazine_comps
            WHERE site_id = $1 AND shopper_id = $2 AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
           LIMIT 1""",
        site_id, shopper_id, list(PAYING_STATUSES),
    ))


async def reader_status(conn, site_id: UUID, shopper_id: UUID) -> dict:
    """What a signed-in reader holds here: their latest live subscription and
    their comp, for the paywall and the account page."""
    sub = await conn.fetchrow(
        """SELECT id, status, current_period_end, cancel_at_period_end, total_cents, currency
             FROM cappe_shopper_subscriptions
            WHERE site_id = $1 AND shopper_id = $2 AND kind = 'magazine' AND status = ANY($3::text[])
            ORDER BY created_at DESC LIMIT 1""",
        site_id, shopper_id, list(PAYING_STATUSES),
    )
    comp = await conn.fetchrow(
        """SELECT expires_at FROM cappe_magazine_comps
            WHERE site_id = $1 AND shopper_id = $2 AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())""",
        site_id, shopper_id,
    )
    subscription: Optional[dict] = dict(sub) if sub else None
    return {
        "has_access": bool(sub or comp),
        "subscription": subscription,
        "comp": {"expires_at": comp["expires_at"]} if comp else None,
    }
