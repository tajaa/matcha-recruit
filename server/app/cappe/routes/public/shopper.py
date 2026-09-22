"""Shopper authentication and private account data on a published store."""
from datetime import datetime
from uuid import UUID

from fastapi import BackgroundTasks, Depends, HTTPException, Query, Request, Response

from app.core.services.email._shared import _is_reserved_test_domain
from app.core.services.redis_cache import check_rate_limit, client_ip
from app.database import get_connection
from app.cappe.dependencies import require_shopper
from app.cappe.models.shopper import (
    Shopper, ShopperAddress, ShopperDevice, ShopperProfile, ShopperRefresh, ShopperStart, ShopperVerify,
)
from app.cappe.services import shopper_auth as auth
from app.cappe.services.commerce import check_recipient_send_ok
from app.cappe.services.common import loads_list
from app.cappe.services.email import send_cappe_shopper_code_email
from ._body_limit import limited_public_router

router = limited_public_router(16384)
PREFIX = "/public/sites/{slug}/shopper"


@router.post(PREFIX + "/auth/start", status_code=204)
async def start(slug: str, body: ShopperStart, request: Request, background: BackgroundTasks):
    await check_rate_limit(client_ip(request), "cappe_shopper_code", 5, 900)
    email = str(body.email).strip().lower()
    if _is_reserved_test_domain(email):
        raise HTTPException(422, "Reserved/test email domains are not accepted")
    async with get_connection() as conn:
        site = await auth.published_shopper_site(conn, slug)
    if await check_recipient_send_ok(email):
        async with get_connection() as conn:
            code = await auth.issue_login_code(conn, site=site, email=email)
        background.add_task(send_cappe_shopper_code_email, email, site["name"], code)
    return Response(status_code=204)


@router.post(PREFIX + "/auth/verify")
async def verify(slug: str, body: ShopperVerify, request: Request):
    await check_rate_limit(client_ip(request), "cappe_shopper_verify", 30, 900)
    async with get_connection() as conn:
        site = await auth.published_shopper_site(conn, slug)
        result = await auth.verify_login_code(conn, site=site, email=str(body.email), code=body.code)
    if result is None:
        raise HTTPException(401, "Invalid or expired code")
    return result


@router.post(PREFIX + "/auth/refresh")
async def refresh(slug: str, body: ShopperRefresh, request: Request):
    await check_rate_limit(client_ip(request), "cappe_shopper_refresh", 120, 3600)
    async with get_connection() as conn:
        site = await auth.published_shopper_site(conn, slug)
        async with conn.transaction():
            shopper, payload = await auth.resolve_shopper(conn, site, body.refresh_token, "refresh", lock=True)
            return await auth.issue_session(conn, shopper, sid=UUID(payload["sid"]), started=payload["session_started_at"])


@router.post(PREFIX + "/auth/logout", status_code=204)
async def logout(context=Depends(require_shopper)):
    site, shopper = context
    async with get_connection() as conn, conn.transaction():
        await conn.execute("UPDATE cappe_shoppers SET tokens_valid_after=NOW() WHERE id=$1 AND site_id=$2",
                           shopper["id"], site["id"])
        await conn.execute("DELETE FROM cappe_shopper_sessions WHERE shopper_id=$1", shopper["id"])
        await conn.execute("DELETE FROM cappe_shopper_devices WHERE shopper_id=$1 AND site_id=$2", shopper["id"], site["id"])
    return Response(status_code=204)


@router.get(PREFIX + "/me", response_model=Shopper)
async def me(context=Depends(require_shopper)):
    return context[1]


@router.patch(PREFIX + "/me", response_model=Shopper)
async def update_me(body: ShopperProfile, context=Depends(require_shopper)):
    site, shopper = context
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return shopper
    columns = list(changes)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "UPDATE cappe_shoppers SET " + ",".join(f"{key}=${i+3}" for i, key in enumerate(columns))
            + ",updated_at=NOW() WHERE id=$1 AND site_id=$2 RETURNING *",
            shopper["id"], site["id"], *[changes[key] for key in columns],
        )
    if not row:
        raise HTTPException(401, "Shopper no longer exists")
    return dict(row)


@router.delete(PREFIX + "/me", status_code=204)
async def delete_me(context=Depends(require_shopper)):
    site, shopper = context
    from app.cappe.services.recurring import delete_shopper_subscriptions
    await delete_shopper_subscriptions(site, shopper)
    async with get_connection() as conn, conn.transaction():
        await conn.execute("DELETE FROM cappe_shopper_login_codes WHERE site_id=$1 AND email=$2", site["id"], shopper["email"])
        await conn.execute("DELETE FROM cappe_shoppers WHERE id=$1 AND site_id=$2", shopper["id"], site["id"])
    return Response(status_code=204)


@router.get(PREFIX + "/me/addresses")
async def addresses(context=Depends(require_shopper)):
    site, shopper = context
    async with get_connection() as conn:
        return [dict(r) for r in await conn.fetch(
            "SELECT * FROM cappe_shopper_addresses WHERE shopper_id=$1 AND site_id=$2 ORDER BY is_default DESC,created_at,id",
            shopper["id"], site["id"],
        )]


async def save_address(body, context, address_id=None):
    site, shopper = context
    values = body.model_dump()
    async with get_connection() as conn, conn.transaction():
        # Serializes default changes even when the shopper has no addresses yet.
        exists = await conn.fetchval("SELECT id FROM cappe_shoppers WHERE id=$1 AND site_id=$2 FOR UPDATE", shopper["id"], site["id"])
        if not exists:
            raise HTTPException(401, "Shopper no longer exists")
        if address_id and not await conn.fetchval(
            "SELECT id FROM cappe_shopper_addresses WHERE id=$1 AND shopper_id=$2 AND site_id=$3",
            address_id, shopper["id"], site["id"],
        ):
            raise HTTPException(404, "Address not found")
        if not address_id and await conn.fetchval("SELECT count(*) FROM cappe_shopper_addresses WHERE shopper_id=$1", shopper["id"]) >= 20:
            raise HTTPException(409, "Address limit reached")
        if body.is_default:
            await conn.execute("UPDATE cappe_shopper_addresses SET is_default=false WHERE shopper_id=$1 AND site_id=$2",
                               shopper["id"], site["id"])
        columns = list(values)
        if address_id:
            row = await conn.fetchrow(
                "UPDATE cappe_shopper_addresses SET " + ",".join(f"{key}=${i+4}" for i, key in enumerate(columns))
                + ",updated_at=NOW() WHERE id=$1 AND shopper_id=$2 AND site_id=$3 RETURNING *",
                address_id, shopper["id"], site["id"], *values.values(),
            )
        else:
            row = await conn.fetchrow(
                "INSERT INTO cappe_shopper_addresses(shopper_id,site_id," + ",".join(columns) + ") VALUES($1,$2,"
                + ",".join(f"${i+3}" for i in range(len(columns))) + ") RETURNING *",
                shopper["id"], site["id"], *values.values(),
            )
    return dict(row)


@router.post(PREFIX + "/me/addresses", status_code=201)
async def add_address(body: ShopperAddress, context=Depends(require_shopper)):
    return await save_address(body, context)


@router.patch(PREFIX + "/me/addresses/{address_id}")
async def edit_address(address_id: UUID, body: ShopperAddress, context=Depends(require_shopper)):
    return await save_address(body, context, address_id)


@router.delete(PREFIX + "/me/addresses/{address_id}", status_code=204)
async def delete_address(address_id: UUID, context=Depends(require_shopper)):
    site, shopper = context
    async with get_connection() as conn:
        result = await conn.execute("DELETE FROM cappe_shopper_addresses WHERE id=$1 AND shopper_id=$2 AND site_id=$3",
                                    address_id, shopper["id"], site["id"])
    if result == "DELETE 0":
        raise HTTPException(404, "Address not found")
    return Response(status_code=204)


@router.get(PREFIX + "/me/favorites")
async def favorites(context=Depends(require_shopper)):
    site, shopper = context
    async with get_connection() as conn:
        return [str(r["product_id"]) for r in await conn.fetch(
            "SELECT f.product_id FROM cappe_shopper_favorites f JOIN cappe_products p ON p.id=f.product_id "
            "WHERE f.shopper_id=$1 AND p.site_id=$2 AND p.status='active' ORDER BY f.created_at,f.product_id",
            shopper["id"], site["id"],
        )]


@router.put(PREFIX + "/me/favorites/{product_id}", status_code=204)
async def add_favorite(product_id: UUID, context=Depends(require_shopper)):
    site, shopper = context
    async with get_connection() as conn, conn.transaction():
        await conn.fetchval("SELECT id FROM cappe_shoppers WHERE id=$1 FOR UPDATE", shopper["id"])
        if not await conn.fetchval("SELECT id FROM cappe_products WHERE id=$1 AND site_id=$2 AND status='active'", product_id, site["id"]):
            raise HTTPException(404, "Product not found")
        if await conn.fetchval("SELECT count(*) FROM cappe_shopper_favorites WHERE shopper_id=$1", shopper["id"]) >= 500:
            raise HTTPException(409, "Favorite limit reached")
        await conn.execute("INSERT INTO cappe_shopper_favorites(shopper_id,product_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
                           shopper["id"], product_id)
    return Response(status_code=204)


@router.delete(PREFIX + "/me/favorites/{product_id}", status_code=204)
async def delete_favorite(product_id: UUID, context=Depends(require_shopper)):
    async with get_connection() as conn:
        await conn.execute("DELETE FROM cappe_shopper_favorites WHERE shopper_id=$1 AND product_id=$2", context[1]["id"], product_id)
    return Response(status_code=204)


ORDER_COLS = "id,access_token AS order_token,status,subtotal_cents,tax_cents,shipping_cents,total_cents,currency,created_at,carrier,tracking_number"


async def order_items(conn, orders):
    rows = await conn.fetch(
        "SELECT order_id,title,quantity,unit_price_cents,fulfillment,selected_options "
        "FROM cappe_order_items WHERE order_id=ANY($1::uuid[]) ORDER BY created_at,id", [r["id"] for r in orders],
    )
    for order in orders:
        order["items"] = [{**dict(r), "selected_options": loads_list(r["selected_options"])} for r in rows if r["order_id"] == order["id"]]
    return orders


@router.get(PREFIX + "/me/orders")
async def orders(cursor: str | None = Query(default=None, max_length=100), limit: int = Query(default=20, ge=1, le=100), context=Depends(require_shopper)):
    site, shopper = context
    timestamp, order_id = None, None
    if cursor:
        try:
            stamp, identity = cursor.split("|")
            timestamp, order_id = datetime.fromisoformat(stamp), UUID(identity)
            if timestamp.tzinfo is None:
                raise ValueError()
        except ValueError:
            raise HTTPException(422, "Invalid cursor") from None
    async with get_connection() as conn:
        rows = [dict(r) for r in await conn.fetch(
            f"SELECT {ORDER_COLS} FROM cappe_orders WHERE shopper_id=$1 AND site_id=$2 "
            "AND ($3::timestamptz IS NULL OR (created_at,id)<($3,$4::uuid)) ORDER BY created_at DESC,id DESC LIMIT $5",
            shopper["id"], site["id"], timestamp, order_id, limit + 1,
        )]
        page = await order_items(conn, rows[:limit])
    next_cursor = f"{page[-1]['created_at'].isoformat()}|{page[-1]['id']}" if len(rows) > limit else None
    return {"orders": page, "next_cursor": next_cursor}


@router.get(PREFIX + "/me/orders/{order_id}")
async def order(order_id: UUID, context=Depends(require_shopper)):
    site, shopper = context
    async with get_connection() as conn:
        row = await conn.fetchrow(f"SELECT {ORDER_COLS} FROM cappe_orders WHERE id=$1 AND shopper_id=$2 AND site_id=$3",
                                  order_id, shopper["id"], site["id"])
        if not row:
            raise HTTPException(404, "Order not found")
        return (await order_items(conn, [dict(row)]))[0]


@router.post(PREFIX + "/me/devices", status_code=204)
async def register_device(body: ShopperDevice, context=Depends(require_shopper)):
    from app.cappe.services.push import register_token
    await register_token(*context, body)
    return Response(status_code=204)


@router.delete(PREFIX + "/me/devices/{token}", status_code=204)
async def unregister_device(token: str, context=Depends(require_shopper)):
    async with get_connection() as conn:
        await conn.execute("DELETE FROM cappe_shopper_devices WHERE token=$1 AND shopper_id=$2 AND site_id=$3",
                           token.lower(), context[1]["id"], context[0]["id"])
    return Response(status_code=204)
