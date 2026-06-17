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
    CappeApprovalDecline,
    CappeDeliverableUpdate,
    CappeOrder,
    CappeOrderItem,
    CappeOrderStatusUpdate,
    CappeProduct,
    CappeProductCreate,
    CappeProductUpdate,
)
from ._shared import fetch_option_groups, get_owned_site, loads, loads_list

router = APIRouter()

_PRODUCT_COLS = (
    "id, site_id, name, description, price_cents, currency, image_url, sku, "
    "inventory, status, sort_order, fulfillment, digital_file_url, booking_type_id, "
    "requires_approval, intake_fields, category, created_at, updated_at"
)
_ORDER_COLS = (
    "id, site_id, customer_email, customer_name, status, subtotal_cents, "
    "tax_cents, total_cents, receipt_number, "
    "currency, payment_ref, note, requires_approval, approved_at, decline_reason, "
    "metadata, created_at, updated_at"
)
_ITEM_COLS = (
    "id, product_id, title, unit_price_cents, quantity, fulfillment, "
    "intake_answers, selected_options, deliverable_url, booking_id"
)


def _product_row(row, groups=None) -> dict:
    d = dict(row)
    d["intake_fields"] = loads_list(row["intake_fields"])
    d["option_groups"] = groups or []
    return d


def _item_row(row) -> dict:
    d = dict(row)
    d["intake_answers"] = loads(row["intake_answers"])
    d["selected_options"] = loads_list(row["selected_options"])
    return d


async def _replace_option_groups(conn, site_id, product_id, groups) -> None:
    """Replace a product's option groups+options in one shot (None = leave as-is,
    [] = clear). Mirrors the availability/rate-rule replace pattern."""
    if groups is None:
        return
    await conn.execute(
        "DELETE FROM cappe_product_option_groups WHERE product_id = $1 AND site_id = $2",
        product_id, site_id,
    )
    for gi, g in enumerate(groups):
        gid = await conn.fetchval(
            """INSERT INTO cappe_product_option_groups
                   (site_id, product_id, name, select_type, required, sort_order)
               VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
            site_id, product_id, g.name, g.select_type, g.required, g.sort_order or gi,
        )
        for oi, o in enumerate(g.options or []):
            await conn.execute(
                """INSERT INTO cappe_product_options
                       (site_id, group_id, name, price_delta_cents, sort_order)
                   VALUES ($1, $2, $3, $4, $5)""",
                site_id, gid, o.name, o.price_delta_cents, o.sort_order or oi,
            )


def _order_row(row, items=None) -> dict:
    d = dict(row)
    d["metadata"] = loads(row["metadata"])
    d["items"] = items or []
    return d


async def _validate_booking_type(conn, site_id, booking_type_id) -> None:
    """Ensure a referenced booking type belongs to this site (or 400)."""
    if booking_type_id is None:
        return
    ok = await conn.fetchval(
        "SELECT 1 FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
        booking_type_id, site_id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown booking type")


# --- Products ---------------------------------------------------------------

@router.get("/sites/{site_id}/products", response_model=list[CappeProduct])
async def list_products(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE site_id = $1 ORDER BY sort_order, created_at",
            site_id,
        )
        groups = await fetch_option_groups(conn, [r["id"] for r in rows])
    return [_product_row(r, groups.get(r["id"])) for r in rows]


@router.post("/sites/{site_id}/products", response_model=CappeProduct, status_code=status.HTTP_201_CREATED)
async def create_product(
    site_id: UUID, body: CappeProductCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _validate_booking_type(conn, site_id, body.booking_type_id)
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_products
                        (site_id, name, description, price_cents, currency, image_url, sku, inventory,
                         status, sort_order, fulfillment, digital_file_url, booking_type_id,
                         requires_approval, intake_fields, category)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    RETURNING {_PRODUCT_COLS}""",
                site_id, body.name, body.description, body.price_cents, body.currency,
                body.image_url, body.sku, body.inventory, body.status, body.sort_order,
                body.fulfillment, body.digital_file_url, body.booking_type_id,
                body.requires_approval, json.dumps(body.intake_fields), body.category,
            )
            await _replace_option_groups(conn, site_id, row["id"], body.option_groups)
        groups = await fetch_option_groups(conn, [row["id"]])
    return _product_row(row, groups.get(row["id"]))


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
        groups = await fetch_option_groups(conn, [product_id])
    return _product_row(row, groups.get(product_id))


@router.put("/sites/{site_id}/products/{product_id}", response_model=CappeProduct)
async def update_product(
    site_id: UUID, product_id: UUID, body: CappeProductUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _validate_booking_type(conn, site_id, body.booking_type_id)
        async with conn.transaction():
            sets, args = [], []
            for col in ("name", "description", "price_cents", "currency", "image_url",
                        "sku", "inventory", "status", "sort_order", "fulfillment",
                        "digital_file_url", "booking_type_id", "requires_approval", "category"):
                val = getattr(body, col)
                if val is not None:
                    args.append(val)
                    sets.append(f"{col} = ${len(args)}")
            if body.intake_fields is not None:  # JSONB column needs explicit serialization
                args.append(json.dumps(body.intake_fields))
                sets.append(f"intake_fields = ${len(args)}")
            if sets:
                sets.append("updated_at = NOW()")
                args.extend([product_id, site_id])
                row = await conn.fetchrow(
                    f"UPDATE cappe_products SET {', '.join(sets)} "
                    f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_PRODUCT_COLS}",
                    *args,
                )
            else:
                row = await conn.fetchrow(
                    f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE id = $1 AND site_id = $2",
                    product_id, site_id,
                )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
            await _replace_option_groups(conn, site_id, product_id, body.option_groups)
        groups = await fetch_option_groups(conn, [product_id])
    return _product_row(row, groups.get(product_id))


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
            f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
            order_id,
        )
    return _order_row(order, [_item_row(i) for i in items])


@router.get("/sites/{site_id}/orders/{order_id}/receipt.pdf")
async def owner_order_receipt_pdf(
    site_id: UUID, order_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """Owner-facing printable/exportable PDF receipt for one of their orders."""
    from fastapi import Response
    from ..services.receipt import render_order_receipt_pdf

    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        owns = await conn.fetchval(
            "SELECT 1 FROM cappe_orders WHERE id = $1 AND site_id = $2", order_id, site_id
        )
        if not owns:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        rendered = await render_order_receipt_pdf(conn, order_id)
    if rendered is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    _order, pdf = rendered
    fname = (_order.get("receipt_number") or "receipt") + ".pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


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
            f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
            order_id,
        )
    return _order_row(order, [_item_row(i) for i in items])


@router.post("/sites/{site_id}/orders/{order_id}/accept", response_model=CappeOrder)
async def accept_order(
    site_id: UUID, order_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """Approve an order that was held for review. Stays 'pending' (payment is
    stubbed) but is stamped approved and leaves the requests queue."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        order = await conn.fetchrow(
            f"""UPDATE cappe_orders
                SET requires_approval = false, approved_at = NOW(), updated_at = NOW()
                WHERE id = $1 AND site_id = $2 AND status = 'pending' AND requires_approval = true
                RETURNING {_ORDER_COLS}""",
            order_id, site_id,
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending order to accept")
        items = await conn.fetch(
            f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
            order_id,
        )
    return _order_row(order, [_item_row(i) for i in items])


@router.post("/sites/{site_id}/orders/{order_id}/decline", response_model=CappeOrder)
async def decline_order(
    site_id: UUID, order_id: UUID, body: CappeApprovalDecline,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Decline an order held for review → 'declined' with an optional reason.
    Restocks any physical inventory the pending order had decremented."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            order = await conn.fetchrow(
                f"""UPDATE cappe_orders
                    SET status = 'declined', decline_reason = $3, updated_at = NOW()
                    WHERE id = $1 AND site_id = $2 AND status = 'pending'
                    RETURNING {_ORDER_COLS}""",
                order_id, site_id, body.reason,
            )
            if order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending order to decline")
            # Restock physical lines + free any held booking slots.
            await conn.execute(
                """UPDATE cappe_products p
                   SET inventory = p.inventory + oi.quantity, updated_at = NOW()
                   FROM cappe_order_items oi
                   WHERE oi.order_id = $1 AND oi.product_id = p.id
                     AND oi.fulfillment = 'physical' AND p.inventory IS NOT NULL""",
                order_id,
            )
            await conn.execute(
                """UPDATE cappe_bookings SET status = 'declined', updated_at = NOW()
                   WHERE id IN (SELECT booking_id FROM cappe_order_items
                                WHERE order_id = $1 AND booking_id IS NOT NULL)
                     AND status = 'pending'""",
                order_id,
            )
            items = await conn.fetch(
                f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
                order_id,
            )
    return _order_row(order, [_item_row(i) for i in items])


@router.patch("/sites/{site_id}/orders/{order_id}/items/{item_id}", response_model=CappeOrderItem)
async def attach_deliverable(
    site_id: UUID, order_id: UUID, item_id: UUID, body: CappeDeliverableUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Attach a delivered result (uploaded file URL) to a service/digital line."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""UPDATE cappe_order_items SET deliverable_url = $1
                WHERE id = $2 AND order_id = $3 AND site_id = $4
                RETURNING {_ITEM_COLS}""",
            body.deliverable_url, item_id, order_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order item not found")
    return _item_row(row)
