"""Tell-Us brand billing — per-store-location Stripe subscription.

Pricing lives in the shared `matcha_lite_pricing` table under
product_code='tellus_brand' (server/app/core/services/matcha_lite_pricing.py) —
reused rather than a new table so the existing admin editor
(Admin > Matcha Lite Pricing > "Tell-Us (per store)") and its audit history
come for free. block_size is pinned to 1 there, so the step-function math
degenerates to a flat per-store rate.

/billing/pricing is unauthenticated — the signup form needs a live total
before an account exists. Everything else requires require_brand (not the
paid dep — a pending brand must be able to see its own status and pay).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core.services.matcha_lite_pricing import compute_matcha_lite_price_cents, get_matcha_lite_pricing
from ...database import get_connection
from ..dependencies import require_brand
from ..models.tellus import TellusAccount

router = APIRouter()

_PRODUCT_CODE = "tellus_brand"


class TellusBrandPricing(BaseModel):
    price_per_location_cents: int
    min_locations: int
    max_locations: int


class TellusBillingStatus(BaseModel):
    plan_status: str
    location_count: int
    store_count: int
    price_per_location_cents: int
    monthly_total_cents: int
    price_available: bool


class TellusCheckoutRequest(BaseModel):
    success_url: str = Field(min_length=1)
    cancel_url: str = Field(min_length=1)


class TellusCheckoutResponse(BaseModel):
    checkout_url: str
    stripe_session_id: str


class TellusLocationUpdateRequest(BaseModel):
    location_count: int = Field(ge=1, le=500)


@router.get("/billing/pricing", response_model=TellusBrandPricing)
async def get_brand_pricing():
    async with get_connection() as conn:
        pricing = await get_matcha_lite_pricing(conn, product_code=_PRODUCT_CODE)
    return TellusBrandPricing(
        price_per_location_cents=pricing.effective_price_per_block_cents,
        min_locations=pricing.min_headcount,
        max_locations=pricing.max_headcount,
    )


@router.get("/billing/status", response_model=TellusBillingStatus)
async def get_billing_status(account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT plan_status, location_count FROM tellus_brands WHERE id = $1", account.brand_id
        )
        store_count = await conn.fetchval(
            "SELECT count(*) FROM tellus_stores WHERE brand_id = $1", account.brand_id
        )
        pricing = await get_matcha_lite_pricing(conn, product_code=_PRODUCT_CODE)

    amount_cents = compute_matcha_lite_price_cents(pricing, row["location_count"])
    return TellusBillingStatus(
        plan_status=row["plan_status"],
        location_count=row["location_count"],
        store_count=store_count,
        price_per_location_cents=pricing.effective_price_per_block_cents,
        monthly_total_cents=amount_cents or 0,
        price_available=amount_cents is not None,
    )


@router.patch("/billing/locations", response_model=TellusBillingStatus)
async def update_locations(
    body: TellusLocationUpdateRequest, account: TellusAccount = Depends(require_brand)
):
    """Set the target store count. For a pending/past_due/canceled brand this is the
    pre-checkout count. For an active brand, raising it here only updates the target —
    it doesn't change what Stripe bills until the brand goes through /billing/checkout
    again, which replaces the existing subscription at the new count."""
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE tellus_brands SET location_count = $2, updated_at = NOW() WHERE id = $1",
            account.brand_id, body.location_count,
        )
    return await get_billing_status(account)


@router.post("/billing/checkout", response_model=TellusCheckoutResponse)
async def create_checkout(body: TellusCheckoutRequest, account: TellusAccount = Depends(require_brand)):
    from ...core.services.stripe_service import StripeService, StripeServiceError

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT plan_status, location_count, stripe_subscription_id FROM tellus_brands WHERE id = $1",
            account.brand_id,
        )
        pricing = await get_matcha_lite_pricing(conn, product_code=_PRODUCT_CODE)

    location_count = row["location_count"]
    amount_cents = compute_matcha_lite_price_cents(pricing, location_count)
    if amount_cents is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Store count outside {pricing.min_headcount}-{pricing.max_headcount} — please contact us for pricing",
        )

    # An active/past_due brand hitting checkout again is raising its store count —
    # the new session replaces the existing subscription rather than stacking a
    # second one (mirrors the Essentials→Lite upgrade cancel-then-activate pattern).
    old_subscription_id = (
        row["stripe_subscription_id"] if row["plan_status"] in ("active", "past_due") else None
    )

    stripe_service = StripeService()
    try:
        session = await stripe_service.create_tellus_brand_checkout(
            brand_id=UUID(str(account.brand_id)),
            location_count=location_count,
            amount_cents=amount_cents,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            old_subscription_id=old_subscription_id,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stripe_session_id = str(getattr(session, "id", "") or "")
    checkout_url = str(getattr(session, "url", "") or "")
    if not stripe_session_id or not checkout_url:
        raise HTTPException(status_code=502, detail="Stripe checkout did not return expected fields")

    return TellusCheckoutResponse(checkout_url=checkout_url, stripe_session_id=stripe_session_id)
