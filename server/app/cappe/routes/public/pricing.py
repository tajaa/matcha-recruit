"""Cappe public pricing — the plan lineup for the anonymous marketing page.

The gummfit.com landing page quotes real prices, so it reads them from the same
builder the tenant billing page uses (`services/catalog.build_catalog`) instead
of hardcoding numbers that drift the first time an admin edits the catalog.

Stricter than the tenant catalog in one way: a price is only shown if it can
actually be bought. The tenant page can render an unpurchasable price as
disabled; a marketing page has no such affordance, so an un-minted price (and a
paid plan left with none) is simply omitted. A plan with no price rows at all
is the free tier and stays.
"""

from fastapi import Request

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import (
    CappeAddon,
    CappePlan,
    CappePublicAddon,
    CappePublicPlan,
    CappePublicPricing,
)
from ...services.catalog import build_catalog

from ._body_limit import limited_public_router

router = limited_public_router()

# One fetch per landing-page view; generous enough for a shared office NAT.
_RATE_LIMIT_CALLS = 60
_RATE_LIMIT_WINDOW_S = 60


def _public_plan(plan: CappePlan) -> CappePublicPlan | None:
    buyable = [p for p in plan.prices if p.purchasable]
    if plan.prices and not buyable:
        return None
    return CappePublicPlan(
        code=plan.code,
        name=plan.name,
        description=plan.description,
        sort_order=plan.sort_order,
        platform_fee_bps=plan.platform_fee_bps,
        allowed_fulfillment=plan.allowed_fulfillment,
        site_limit=plan.site_limit,
        mailbox_quota_included=plan.mailbox_quota_included,
        prices=buyable,
        # build_catalog already drops an intro whose Stripe Price isn't minted.
        intro_price_cents=plan.intro_price_cents if buyable else None,
        intro_days=plan.intro_days if buyable else None,
    )


def _public_addon(addon: CappeAddon) -> CappePublicAddon | None:
    buyable = [p for p in addon.prices if p.purchasable]
    if not buyable:
        return None
    return CappePublicAddon(
        code=addon.code,
        name=addon.name,
        description=addon.description,
        unit_label=addon.unit_label,
        prices=buyable,
    )


@router.get("/public/pricing", response_model=CappePublicPricing)
async def public_pricing(request: Request):
    await check_rate_limit(
        client_ip(request), "cappe_pub_pricing", _RATE_LIMIT_CALLS, _RATE_LIMIT_WINDOW_S
    )
    async with get_connection() as conn:
        plans, addons = await build_catalog(conn)
    return CappePublicPricing(
        plans=[p for p in map(_public_plan, plans) if p is not None],
        addons=[a for a in map(_public_addon, addons) if a is not None],
    )
