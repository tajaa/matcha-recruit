"""Cappe shop — products CRUD + order management (owner side).

Public checkout lives in public.py. Payment capture is stubbed: orders are
created 'pending' and the owner advances status manually here.
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeOrder,
    CappeOrderStatusUpdate,
    CappeProduct,
    CappeProductCreate,
    CappeProductUpdate,
)
from ._shared import get_owned_site, loads

router = APIRouter()

_PRODUCT_COLS = (
    "id, site_id, name, description, price_cents, currency, image_url, sku, "
    "inventory, status, sort_order, created_at, updated_at"
)
_ORDER_COLS = (
    "id, site_id, customer_email, customer_name, status, subtotal_cents, "
    "currency, payment_ref, note, metadata, created_at, updated_at"
)


def _order_row(row, items=None) -> dict:
    d = dict(row)
    d["metadata"] = loads(row["metadata"])
    d["items"] = items or []
    return d


# --- Products ---------------------------------------------------------------

@router.get("/sites/{site_id}/products", response_model=list[CappeProduct])
async def list_products(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE site_id = $1 ORDER BY sort_order, created_at",
            site_id,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/products", response_model=CappeProduct, status_code=status.HTTP_201_CREATED)
async def create_product(
    site_id: UUID, body: CappeProductCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_products
                    (site_id, name, description, price_cents, currency, image_url, sku, inventory, status, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING {_PRODUCT_COLS}""",
            site_id, body.name, body.description, body.price_cents, body.currency,
            body.image_url, body.sku, body.inventory, body.status, body.sort_order,
        )
    return dict(row)


@router.get("/sites/{site_id}/products/{product_id}", response_model=CappeProduct)
async def get_product(
    site_id: UUID, product_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE id = $1 AND site_id = $2",
            product_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return dict(row)


@router.put("/sites/{site_id}/products/{product_id}", response_model=CappeProduct)
async def update_product(
    site_id: UUID, product_id: UUID, body: CappeProductUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        sets, args = [], []
        for col in ("name", "description", "price_cents", "currency", "image_url",
                    "sku", "inventory", "status", "sort_order"):
            val = getattr(body, col)
            if val is not None:
                args.append(val)
                sets.append(f"{col} = ${len(args)}")
        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE id = $1 AND site_id = $2",
                product_id, site_id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
            return dict(row)
        sets.append("updated_at = NOW()")
        args.extend([product_id, site_id])
        row = await conn.fetchrow(
            f"UPDATE cappe_products SET {', '.join(sets)} "
            f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_PRODUCT_COLS}",
            *args,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return dict(row)


@router.delete("/sites/{site_id}/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    site_id: UUID, product_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_products WHERE id = $1 AND site_id = $2", product_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


# --- Orders -----------------------------------------------------------------

@router.get("/sites/{site_id}/orders", response_model=list[CappeOrder])
async def list_orders(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_ORDER_COLS} FROM cappe_orders WHERE site_id = $1 ORDER BY created_at DESC",
            site_id,
        )
    return [_order_row(r) for r in rows]


@router.get("/sites/{site_id}/orders/{order_id}", response_model=CappeOrder)
async def get_order(
    site_id: UUID, order_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        order = await conn.fetchrow(
            f"SELECT {_ORDER_COLS} FROM cappe_orders WHERE id = $1 AND site_id = $2",
            order_id, site_id,
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        items = await conn.fetch(
            "SELECT id, product_id, title, unit_price_cents, quantity "
            "FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
            order_id,
        )
    return _order_row(order, [dict(i) for i in items])


@router.patch("/sites/{site_id}/orders/{order_id}", response_model=CappeOrder)
async def update_order_status(
    site_id: UUID, order_id: UUID, body: CappeOrderStatusUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        order = await conn.fetchrow(
            f"""UPDATE cappe_orders SET status = $1, updated_at = NOW()
                WHERE id = $2 AND site_id = $3 RETURNING {_ORDER_COLS}""",
            body.status, order_id, site_id,
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        items = await conn.fetch(
            "SELECT id, product_id, title, unit_price_cents, quantity "
            "FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
            order_id,
        )
    return _order_row(order, [dict(i) for i in items])
