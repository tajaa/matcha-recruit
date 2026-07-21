"""checkout routes (L9 split)."""
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



@router.post("/upgrade/ir/checkout", response_model=UpgradeCheckoutResponse)
async def create_ir_upgrade_checkout(
    body: UpgradeCheckoutRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Open a Stripe checkout for upgrading the caller's company to Matcha IR.

    The webhook handler (in stripe_webhook.py) listens for
    `checkout.session.completed` with `metadata.type == 'matcha_ir_upgrade'`
    and flips the company features so the slim IR sidebar takes over.
    """
    from app.matcha.dependencies import get_client_company_id
    from app.core.services.stripe_service import StripeService, StripeServiceError

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_ir_upgrade_checkout(
            company_id=company_id,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe checkout did not return expected fields")

    logger.info("IR upgrade checkout opened: company=%s session=%s", company_id, stripe_session_id)
    return UpgradeCheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)




@router.post("/checkout/lite", response_model=UpgradeCheckoutResponse)
async def create_lite_checkout(
    body: LiteCheckoutRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Open a Stripe subscription checkout for Matcha Lite.

    Pricing is admin-configurable (server/app/core/services/matcha_lite_pricing.py),
    read from the headcount stored at registration time. Headcount outside the
    configured min/max is rejected — must contact sales.
    The webhook activates incidents on successful payment (employees is granted
    at signup; Lite has no discipline).
    Only callable by matcha_lite companies.
    """
    from app.core.services.stripe_service import StripeService, StripeServiceError
    from app.core.services.matcha_lite_pricing import get_matcha_lite_pricing, compute_matcha_lite_price_cents

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.signup_source, COALESCE(chp.headcount, 0) AS headcount
            FROM companies c
            LEFT JOIN company_handbook_profiles chp ON chp.company_id = c.id
            WHERE c.id = $1
            """,
            company_id,
        )
        if not row or row["signup_source"] not in ("matcha_lite", "matcha_lite_essentials"):
            raise HTTPException(status_code=403, detail="This endpoint is only available for Matcha Lite accounts")
        pricing = await get_matcha_lite_pricing(conn, product_code=row["signup_source"])

    headcount = int(row["headcount"])
    if headcount < 1:
        raise HTTPException(status_code=400, detail="Company headcount not set — please contact support")
    if headcount < pricing.min_headcount:
        raise HTTPException(
            status_code=400,
            detail=f"Headcount under {pricing.min_headcount} — please contact us for pricing",
        )

    amount_cents = compute_matcha_lite_price_cents(pricing, headcount)
    if amount_cents is None:
        raise HTTPException(
            status_code=400,
            detail=f"Headcount over {pricing.max_headcount} — please contact us for pricing",
        )

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_matcha_lite_checkout(
            company_id=company_id,
            headcount=headcount,
            amount_cents=amount_cents,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            is_essentials=(row["signup_source"] == "matcha_lite_essentials"),
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe checkout did not return expected fields")

    logger.info("Lite checkout opened: company=%s headcount=%d session=%s", company_id, headcount, stripe_session_id)
    return UpgradeCheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)




@router.post("/checkout/product", response_model=UpgradeCheckoutResponse)
async def create_custom_product_checkout(
    body: LiteCheckoutRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Open a Stripe subscription checkout for the caller's admin-composed product.

    The product is resolved from the company's own signup_source
    ('product:<slug>'), never from the request body — a caller can only ever
    buy the product it signed up for. Pricing comes from the product row
    (per_seat / block / flat); free + contact_sales products have no checkout.
    """
    from app.core.services.stripe_service import StripeService, StripeServiceError
    from app.core.services.product_definitions import (
        ProductDefinitionError,
        compute_product_price_cents,
        get_product_by_signup_source,
    )

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.signup_source, COALESCE(chp.headcount, 0) AS headcount
            FROM companies c
            LEFT JOIN company_handbook_profiles chp ON chp.company_id = c.id
            WHERE c.id = $1
            """,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")
        # published_only=False: a company mid-checkout on a product we just
        # archived must still be able to finish paying for it.
        product = await get_product_by_signup_source(
            conn, row["signup_source"], published_only=False
        )

    if product is None:
        raise HTTPException(
            status_code=403,
            detail="This endpoint is only available for companies on a custom product",
        )
    if not product.is_paid:
        raise HTTPException(
            status_code=400,
            detail=f"{product.name} is not billed through Stripe",
        )

    headcount = int(row["headcount"])
    if headcount < 1:
        raise HTTPException(status_code=400, detail="Company headcount not set — please contact support")

    try:
        amount_cents = compute_product_price_cents(product, headcount)
    except ProductDefinitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_custom_product_checkout(
            company_id=company_id,
            product_slug=product.slug,
            product_name=product.name,
            product_description=product.description,
            headcount=headcount,
            amount_cents=amount_cents or 0,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe checkout did not return expected fields")

    logger.info(
        "Custom product checkout opened: company=%s product=%s headcount=%d session=%s",
        company_id, product.slug, headcount, stripe_session_id,
    )
    return UpgradeCheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)


@router.post("/checkout/lite-addon", response_model=UpgradeCheckoutResponse)
async def create_lite_addon_checkout(
    body: LiteAddonCheckoutRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Open a Stripe subscription checkout for a Lite add-on.

    Requires an active self-purchased base Lite sub (pack_id='matcha_lite') —
    broker-paid Lite companies have no sub row here, so their add-ons are
    admin-toggled instead. The webhook flips the add-on's feature flag on
    `checkout.session.completed` (metadata.type='matcha_lite_addon').
    """
    from app.matcha.services import billing_service
    from app.core.services.lite_addons import LITE_ADDONS, addon_pack_id
    from app.core.services.matcha_lite_pricing import compute_matcha_lite_price_cents, get_matcha_lite_pricing
    from app.core.services.stripe_service import StripeService, StripeServiceError

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    addon = LITE_ADDONS.get(body.addon_key)
    if addon is None:
        raise HTTPException(status_code=404, detail="Unknown add-on")

    ctx = await _lite_company_context(company_id)
    if ctx["signup_source"] not in addon.allowed_sources:
        raise HTTPException(status_code=403, detail=f"{addon.name} is not available on your plan")

    base_sub = await billing_service.get_active_subscription(company_id, pack_ids=("matcha_lite",))
    if base_sub is None:
        raise HTTPException(
            status_code=402,
            detail="An active Matcha Lite subscription is required before purchasing add-ons",
        )

    missing = [f for f in addon.requires_features if not ctx["features"].get(f)]
    if missing:
        raise HTTPException(status_code=403, detail=f"{addon.name} requires features your plan doesn't include")

    existing_addon_sub = await billing_service.get_active_subscription(
        company_id, pack_ids=(addon_pack_id(addon.key),)
    )
    if ctx["features"].get(addon.feature) or existing_addon_sub is not None:
        raise HTTPException(status_code=409, detail=f"{addon.name} is already active on your account")

    headcount = ctx["headcount"]
    if headcount < 1:
        raise HTTPException(status_code=400, detail="Company headcount not set — please contact support")

    pricing = await get_matcha_lite_pricing(product_code=addon.product_code)
    if headcount < pricing.min_headcount:
        raise HTTPException(
            status_code=400,
            detail=f"Headcount under {pricing.min_headcount} — please contact us for pricing",
        )
    amount_cents = compute_matcha_lite_price_cents(pricing, headcount)
    if amount_cents is None:
        raise HTTPException(
            status_code=400,
            detail=f"Headcount over {pricing.max_headcount} — please contact us for pricing",
        )

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_lite_addon_checkout(
            company_id=company_id,
            addon_key=addon.key,
            addon_name=addon.name,
            addon_description=addon.description,
            headcount=headcount,
            amount_cents=amount_cents,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe checkout did not return expected fields")

    logger.info(
        "Lite add-on checkout opened: company=%s addon=%s headcount=%d session=%s",
        company_id, addon.key, headcount, stripe_session_id,
    )
    return UpgradeCheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)




# ---------------------------------------------------------------------------
# Essentials → Lite self-serve upgrade (checkout-first; the webhook flips
# signup_source and cancels the old Essentials sub on completion).
# ---------------------------------------------------------------------------


@router.post("/checkout/lite-upgrade", response_model=UpgradeCheckoutResponse)
async def create_lite_upgrade_checkout(
    body: LiteCheckoutRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Open a Stripe checkout upgrading an Essentials company to standard Lite.

    Only callable while signup_source == 'matcha_lite_essentials' (a completed
    upgrade flips it to 'matcha_lite', which also blocks double-upgrades).
    Priced at the standard matcha_lite rate for the stored headcount. Nothing
    changes until checkout.session.completed lands — abandoning is a no-op.
    """
    from app.matcha.services import billing_service
    from app.core.services.matcha_lite_pricing import compute_matcha_lite_price_cents, get_matcha_lite_pricing
    from app.core.services.stripe_service import StripeService, StripeServiceError

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    ctx = await _lite_company_context(company_id)
    if ctx["signup_source"] != "matcha_lite_essentials":
        raise HTTPException(status_code=403, detail="This upgrade is only available for Matcha Lite Essentials accounts")

    base_sub = await billing_service.get_active_subscription(company_id, pack_ids=("matcha_lite",))
    if base_sub is None:
        raise HTTPException(
            status_code=402,
            detail="An active Essentials subscription is required before upgrading",
        )

    headcount = ctx["headcount"]
    if headcount < 1:
        raise HTTPException(status_code=400, detail="Company headcount not set — please contact support")

    pricing = await get_matcha_lite_pricing(product_code="matcha_lite")
    if headcount < pricing.min_headcount:
        raise HTTPException(
            status_code=400,
            detail=f"Headcount under {pricing.min_headcount} — please contact us for pricing",
        )
    amount_cents = compute_matcha_lite_price_cents(pricing, headcount)
    if amount_cents is None:
        raise HTTPException(
            status_code=400,
            detail=f"Headcount over {pricing.max_headcount} — please contact us for pricing",
        )

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_lite_essentials_upgrade_checkout(
            company_id=company_id,
            headcount=headcount,
            amount_cents=amount_cents,
            old_subscription_id=base_sub["stripe_subscription_id"],
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe checkout did not return expected fields")

    logger.info(
        "Essentials→Lite upgrade checkout opened: company=%s headcount=%d session=%s",
        company_id, headcount, stripe_session_id,
    )
    return UpgradeCheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)




# ---------------------------------------------------------------------------
# Matcha-X — headcount-based subscription checkout (mid tier; clone of Lite)
# ---------------------------------------------------------------------------


@router.post("/checkout/x", response_model=UpgradeCheckoutResponse)
async def create_matcha_x_checkout(
    body: LiteCheckoutRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Open a Stripe subscription checkout for Matcha-X (mid tier).

    Clone of /checkout/lite. Headcount read from registration time; > 300 is
    rejected (contact sales). The webhook (metadata.type == 'matcha_x')
    activates incidents on payment; employees/discipline come from the tier
    overlay. Only callable by matcha_x companies.
    """
    from app.core.services.stripe_service import StripeService, StripeServiceError

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.signup_source, COALESCE(chp.headcount, 0) AS headcount
            FROM companies c
            LEFT JOIN company_handbook_profiles chp ON chp.company_id = c.id
            WHERE c.id = $1
            """,
            company_id,
        )

    if not row or row["signup_source"] != "matcha_x":
        raise HTTPException(status_code=403, detail="This endpoint is only available for Matcha-X accounts")

    headcount = int(row["headcount"])
    if headcount < 1:
        raise HTTPException(status_code=400, detail="Company headcount not set — please contact support")
    if headcount > 300:
        raise HTTPException(status_code=400, detail="Headcount over 300 — please contact us for pricing")

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_matcha_x_checkout(
            company_id=company_id,
            headcount=headcount,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe checkout did not return expected fields")

    logger.info("Matcha-X checkout opened: company=%s headcount=%d session=%s", company_id, headcount, stripe_session_id)
    return UpgradeCheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)




# ---------------------------------------------------------------------------
# Matcha Compliance — headcount + jurisdiction priced subscription checkout
# ---------------------------------------------------------------------------


@router.post("/checkout/compliance", response_model=UpgradeCheckoutResponse)
async def create_compliance_checkout(
    body: LiteCheckoutRequest,
    current_user: CurrentUser = Depends(require_client),
):
    """Open a Stripe subscription checkout for the standalone Matcha Compliance product.

    Pricing is admin-configurable (server/app/core/services/matcha_lite_pricing.py,
    product_code='matcha_compliance'), read from the headcount stored at
    registration time (company_handbook_profiles). Jurisdiction count is carried
    in checkout metadata but no longer affects price. Headcount outside the
    configured min/max is rejected — must contact sales. The webhook
    (metadata.type == 'matcha_compliance') flips the full `compliance` feature
    on successful payment. Only callable by matcha_compliance companies.
    """
    from app.core.services.stripe_service import StripeService, StripeServiceError
    from app.core.services.matcha_lite_pricing import get_matcha_lite_pricing, compute_matcha_lite_price_cents

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT c.signup_source,
                   COALESCE(chp.headcount, 0) AS headcount,
                   COALESCE(chp.compliance_jurisdiction_count, 0) AS jurisdiction_count
            FROM companies c
            LEFT JOIN company_handbook_profiles chp ON chp.company_id = c.id
            WHERE c.id = $1
            """,
            company_id,
        )
        if not row or row["signup_source"] != "matcha_compliance":
            raise HTTPException(status_code=403, detail="This endpoint is only available for Matcha Compliance accounts")
        pricing = await get_matcha_lite_pricing(conn, product_code="matcha_compliance")

    headcount = int(row["headcount"])
    jurisdiction_count = int(row["jurisdiction_count"])
    if headcount < 1:
        raise HTTPException(status_code=400, detail="Company headcount not set — please contact support")
    if headcount < pricing.min_headcount:
        raise HTTPException(
            status_code=400,
            detail=f"Headcount under {pricing.min_headcount} — please contact us for pricing",
        )

    amount_cents = compute_matcha_lite_price_cents(pricing, headcount)
    if amount_cents is None:
        raise HTTPException(
            status_code=400,
            detail=f"Headcount over {pricing.max_headcount} — please contact us for pricing",
        )

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_matcha_compliance_checkout(
            company_id=company_id,
            headcount=headcount,
            jurisdiction_count=jurisdiction_count,
            amount_cents=amount_cents,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe checkout did not return expected fields")

    logger.info(
        "Matcha Compliance checkout opened: company=%s headcount=%d jurisdictions=%d session=%s",
        company_id, headcount, jurisdiction_count, stripe_session_id,
    )
    return UpgradeCheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)
