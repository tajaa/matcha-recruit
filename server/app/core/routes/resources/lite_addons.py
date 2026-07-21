"""lite_addons routes (L9 split)."""
import html as _html
import json as _json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.models.auth import CurrentUser
from app.core.dependencies import get_optional_user
from app.matcha.dependencies import require_client, get_client_company_id
from app.core.services.redis_cache import check_rate_limit, client_ip

from app.core.routes.resources._shared import *  # noqa: F401,F403  (router objects + shared models/consts)
logger = logging.getLogger(__name__)



@router.get("/matcha-lite/pricing", response_model=MatchaLitePricingResponse)
async def get_matcha_lite_pricing_public(product_code: str = "matcha_lite"):
    """Public — current pricing for `product_code` ('matcha_lite',
    'matcha_lite_essentials', or 'matcha_compliance'), for the signup calculator
    + pending-subscription screen."""
    from app.core.services.matcha_lite_pricing import PRODUCT_CODES, get_matcha_lite_pricing

    if product_code not in PRODUCT_CODES:
        raise HTTPException(status_code=400, detail=f"Unknown product_code — must be one of {PRODUCT_CODES}")

    pricing = await get_matcha_lite_pricing(product_code=product_code)
    return MatchaLitePricingResponse(
        price_per_block_cents=pricing.price_per_block_cents,
        block_size=pricing.block_size,
        effective_price_per_block_cents=pricing.effective_price_per_block_cents,
        sale_active=pricing.sale_active,
        min_headcount=pricing.min_headcount,
        max_headcount=pricing.max_headcount,
    )




@router.get("/lite-addons", response_model=list[LiteAddonInfo])
async def list_lite_addons(current_user: CurrentUser = Depends(require_client)):
    """Add-ons for the caller's Lite-family company, with live PEPM pricing.

    Not-lite companies get an empty list rather than a 403 — the panel simply
    doesn't render for them.
    """
    from app.matcha.services import billing_service
    from app.core.services.lite_addons import LITE_ADDONS, addon_pack_id
    from app.core.services.matcha_lite_pricing import compute_matcha_lite_price_cents, get_matcha_lite_pricing

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    ctx = await _lite_company_context(company_id)
    if ctx["signup_source"] not in ("matcha_lite", "matcha_lite_essentials"):
        return []

    active_subs = await billing_service.list_active_subscriptions(company_id)
    active_pack_ids = {s["pack_id"] for s in active_subs}

    out: list[LiteAddonInfo] = []
    for addon in LITE_ADDONS.values():
        has_sub = addon_pack_id(addon.key) in active_pack_ids
        is_active = bool(ctx["features"].get(addon.feature)) or has_sub
        eligible = ctx["signup_source"] in addon.allowed_sources and all(
            ctx["features"].get(f) for f in addon.requires_features
        )
        pricing = await get_matcha_lite_pricing(product_code=addon.product_code)
        out.append(
            LiteAddonInfo(
                key=addon.key,
                name=addon.name,
                description=addon.description,
                status="active" if is_active else ("available" if eligible else "not_eligible"),
                monthly_price_cents=(
                    compute_matcha_lite_price_cents(pricing, ctx["headcount"]) if ctx["headcount"] >= 1 else None
                ),
                cancellable=has_sub,
            )
        )
    return out




@router.post("/lite-addons/{addon_key}/cancel")
async def cancel_lite_addon(
    addon_key: str,
    current_user: CurrentUser = Depends(require_client),
):
    """Cancel an add-on subscription at period end.

    Deliberately does NOT mark the mw_subscriptions row canceled here — the
    row must stay 'active' so the eventual customer.subscription.deleted
    webhook passes its `if canceled:` gate and un-flips the feature flag when
    the period actually ends.
    """
    from app.matcha.services import billing_service
    from app.core.services.lite_addons import LITE_ADDONS, addon_pack_id
    from app.core.services.stripe_service import StripeService, StripeServiceError

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    addon = LITE_ADDONS.get(addon_key)
    if addon is None:
        raise HTTPException(status_code=404, detail="Unknown add-on")

    sub = await billing_service.get_active_subscription(company_id, pack_ids=(addon_pack_id(addon.key),))
    if sub is None:
        raise HTTPException(status_code=404, detail="No active subscription for this add-on")

    try:
        await StripeService().cancel_subscription(sub["stripe_subscription_id"])
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    logger.info("Lite add-on cancel scheduled: company=%s addon=%s sub=%s", company_id, addon.key, sub["stripe_subscription_id"])
    return {"canceled": True, "message": f"{addon.name} will not renew at the end of the current period."}
