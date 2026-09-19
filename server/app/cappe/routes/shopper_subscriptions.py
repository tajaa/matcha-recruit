"""Recurring checkout and management for shoppers and store owners."""
from uuid import UUID

from fastapi import Depends, HTTPException, Query, Request

from app.core.services.redis_cache import check_rate_limit
from app.database import get_connection
from app.cappe.dependencies import require_cappe_account, require_shopper
from app.cappe.models.cappe import CappeAccount
from app.cappe.models.shopper import SubscriptionCheckout
from app.cappe.services import recurring
from app.cappe.services.common import loads_list
from ._shared import get_owned_site
from .public._body_limit import limited_public_router

router = limited_public_router(65536)
PREFIX = "/public/sites/{slug}/shopper/me/subscriptions"
COLS = "id,site_id,shopper_id,status,interval,items,subtotal_cents,tax_cents,shipping_cents,total_cents,currency,current_period_end,cancel_at_period_end,created_at"


@router.post(PREFIX + "/checkout", status_code=201)
async def checkout(body: SubscriptionCheckout, request: Request, context=Depends(require_shopper)):
    site, shopper = context
    await check_rate_limit(str(shopper["id"]), "cappe_subscription_checkout", 10, 3600)
    return await recurring.checkout(site, shopper, body)


@router.get(PREFIX)
async def list_mine(limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0, le=10000), context=Depends(require_shopper)):
    async with get_connection() as conn:
        rows = await conn.fetch(f"SELECT {COLS} FROM cappe_shopper_subscriptions WHERE shopper_id=$1 AND site_id=$2 ORDER BY created_at DESC,id DESC LIMIT $3 OFFSET $4",
                                context[1]["id"], context[0]["id"], limit, offset)
    return [{**dict(r), "items": loads_list(r["items"])} for r in rows]


async def mine(subscription_id, context, cancel):
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM cappe_shopper_subscriptions WHERE id=$1 AND shopper_id=$2 AND site_id=$3",
                                  subscription_id, context[1]["id"], context[0]["id"])
    if not row:
        raise HTTPException(404, "Subscription not found")
    return await recurring.change_subscription(row, cancel)


@router.post(PREFIX + "/{subscription_id}/cancel")
async def cancel_mine(subscription_id: UUID, context=Depends(require_shopper)):
    return await mine(subscription_id, context, True)


@router.post(PREFIX + "/{subscription_id}/resume")
async def resume_mine(subscription_id: UUID, context=Depends(require_shopper)):
    return await mine(subscription_id, context, False)


@router.get("/sites/{site_id}/subscriptions")
async def list_owned(site_id: UUID, limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0, le=10000), account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(f"SELECT {COLS} FROM cappe_shopper_subscriptions WHERE site_id=$1 ORDER BY created_at DESC,id DESC LIMIT $2 OFFSET $3", site_id, limit, offset)
    return [{**dict(r), "items": loads_list(r["items"])} for r in rows]


@router.post("/sites/{site_id}/subscriptions/{subscription_id}/cancel")
async def cancel_owned(site_id: UUID, subscription_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow("SELECT * FROM cappe_shopper_subscriptions WHERE id=$1 AND site_id=$2", subscription_id, site_id)
    if not row:
        raise HTTPException(404, "Subscription not found")
    return await recurring.change_subscription(row, True)
