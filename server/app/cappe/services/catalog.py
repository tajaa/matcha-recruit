"""The Cappe plan/add-on lineup, as the API presents it.

One builder for both readers — the tenant billing page (`GET /billing/catalog`)
and the anonymous marketing page (`GET /public/pricing`). They must never show
different numbers: a landing page that advertises a price or a $1 intro that
checkout then refuses to charge is the exact bug this module exists to prevent.
"""

from __future__ import annotations

from ..models.cappe import CappeAddon, CappePlan, CappePlanPrice
from .entitlements import decode_features


def _prices_for(rows, code: str) -> list[CappePlanPrice]:
    return [
        CappePlanPrice(
            interval=r["interval"],
            unit_amount_cents=r["unit_amount_cents"],
            currency=r["currency"],
            # Nothing is purchasable until the seed script mints the Stripe
            # Price; surfacing that beats a checkout that 400s.
            purchasable=bool(r["stripe_price_id"]),
        )
        for r in rows
        if r["product_code"] == code and r["role"] == "standard"
    ]


async def build_catalog(conn) -> tuple[list[CappePlan], list[CappeAddon]]:
    """Active plans and add-ons with their current prices. Legacy tiers are
    excluded — they are honoured for existing accounts, never sold."""
    products = await conn.fetch(
        "SELECT * FROM cappe_billing_products WHERE status = 'active' ORDER BY sort_order, code"
    )
    prices = await conn.fetch(
        "SELECT * FROM cappe_billing_prices WHERE is_current AND active"
    )

    intro_by_code = {r["product_code"]: r for r in prices if r["role"] == "intro"}
    plans: list[CappePlan] = []
    addons: list[CappeAddon] = []
    for p in products:
        if p["kind"] == "plan":
            # Only surface the intro if its Stripe Price actually exists —
            # `_prices_for` already withholds `purchasable` for un-minted
            # standard prices, but intro_price_cents/intro_days carried no such
            # flag. Before the seed script has run, the catalog would advertise
            # "$1 for 30 days" while start_checkout silently drops the intro
            # (its own stripe_price_id check) and charges full price — the
            # customer sees a different amount on Stripe's page than the one
            # they clicked.
            intro_row = intro_by_code.get(p["code"])
            intro = intro_row if intro_row and intro_row["stripe_price_id"] else None
            plans.append(
                CappePlan(
                    code=p["code"],
                    name=p["name"],
                    description=p["description"],
                    status=p["status"],
                    sort_order=p["sort_order"],
                    can_sell=p["can_sell"],
                    platform_fee_bps=p["platform_fee_bps"],
                    allowed_fulfillment=list(p["allowed_fulfillment"] or []),
                    site_limit=p["site_limit"],
                    mailbox_quota_included=p["mailbox_quota_included"],
                    features=decode_features(p["features"]),
                    prices=_prices_for(prices, p["code"]),
                    intro_price_cents=intro["unit_amount_cents"] if intro else None,
                    intro_days=intro["intro_days"] if intro else None,
                )
            )
        else:
            addons.append(
                CappeAddon(
                    code=p["code"],
                    name=p["name"],
                    description=p["description"],
                    unit_label=p["unit_label"],
                    max_quantity=p["max_quantity"],
                    prices=_prices_for(prices, p["code"]),
                )
            )
    return plans, addons
