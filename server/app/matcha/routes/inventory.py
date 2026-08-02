"""Inventory router — items, movement ledger, order queue. Mounted under
/inventory, gated on the `inventory` feature flag at mount time (see
routes/__init__.py). Channel intake (auto-create + movements + order
staging) happens in server/app/werk/routes/channels_ws.py; this router is
the /work Inventory page's REST surface plus manual item/order management.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.inventory import (
    InventoryItemCreate, InventoryItemOut, InventoryItemPatch, ItemListResponse,
    MovementListResponse, MovementOut, OrderAction, OrderCreate, OrderListResponse, OrderOut,
)
from app.matcha.services.inventory import movements as movements_service
from app.matcha.services.inventory import orders as orders_service
from app.matcha.services.inventory.matching import normalize_name
from app.matcha.services.inventory.reorder import suggest_order

router = APIRouter()


@router.get("/items", response_model=ItemListResponse)
async def list_items(include_archived: bool = False, company_id: UUID = Depends(get_client_company_id),
                      _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        clause = "" if include_archived else "AND archived_at IS NULL"
        rows = await conn.fetch(
            f"""
            SELECT it.*, o.id AS order_id, o.status AS order_status,
                   o.suggested_quantity AS order_suggested_quantity, o.quantity AS order_quantity,
                   o.suggestion AS order_suggestion, o.created_at AS order_created_at,
                   o.updated_at AS order_updated_at
            FROM inventory_items it
            LEFT JOIN inventory_orders o ON o.item_id = it.id AND o.status = 'queued'
            WHERE it.company_id = $1 {clause}
            ORDER BY it.name
            """,
            company_id,
        )
    items = []
    for r in rows:
        open_order = None
        if r["order_id"] is not None:
            open_order = OrderOut(
                id=r["order_id"], item_id=r["id"], status=r["order_status"],
                suggested_quantity=r["order_suggested_quantity"], quantity=r["order_quantity"],
                suggestion=orders_service.decode_suggestion(r["order_suggestion"]),
                created_at=r["order_created_at"], updated_at=r["order_updated_at"],
            )
        base = {k: v for k, v in dict(r).items() if not k.startswith("order_")}
        items.append(InventoryItemOut(**{**base, "open_order": open_order}))
    return ItemListResponse(items=items)


@router.post("/items", response_model=InventoryItemOut, status_code=201)
async def create_item(body: InventoryItemCreate, company_id: UUID = Depends(get_client_company_id),
                       user=Depends(require_admin_or_client)):
    normalized = normalize_name(body.name)
    async with get_connection() as conn:
        existing = await conn.fetchval(
            "SELECT id FROM inventory_items WHERE company_id = $1 AND normalized_name = $2 AND archived_at IS NULL",
            company_id, normalized,
        )
        if existing:
            raise HTTPException(409, "An item with this name already exists.")
        row = await conn.fetchrow(
            """
            INSERT INTO inventory_items (company_id, name, normalized_name, unit, current_quantity,
                                         low_stock_threshold, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING *
            """,
            company_id, body.name, normalized, body.unit, body.current_quantity,
            body.low_stock_threshold, user.id,
        )
    return InventoryItemOut(**dict(row))


@router.get("/items/{item_id}", response_model=dict)
async def get_item(item_id: UUID, company_id: UUID = Depends(get_client_company_id),
                    _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        item = await conn.fetchrow(
            "SELECT * FROM inventory_items WHERE id = $1 AND company_id = $2", item_id, company_id,
        )
        if item is None:
            raise HTTPException(404, "Item not found.")
        movement_rows = await conn.fetch(
            "SELECT * FROM inventory_movements WHERE item_id = $1 ORDER BY created_at DESC LIMIT 50",
            item_id,
        )
    return {
        "item": InventoryItemOut(**dict(item)),
        "movements": [MovementOut(**dict(m)) for m in movement_rows],
    }


@router.patch("/items/{item_id}", response_model=InventoryItemOut)
async def patch_item(item_id: UUID, body: InventoryItemPatch,
                      company_id: UUID = Depends(get_client_company_id),
                      user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        item = await conn.fetchrow(
            "SELECT * FROM inventory_items WHERE id = $1 AND company_id = $2", item_id, company_id,
        )
        if item is None:
            raise HTTPException(404, "Item not found.")

        if body.set_quantity is not None:
            await movements_service.adjust_item_count(
                conn, item_id=item_id, company_id=company_id, quantity=body.set_quantity, user_id=user.id,
            )

        fields, values = [], []
        if body.name is not None:
            values.append(body.name)
            fields.append(f"name = ${len(values) + 1}")
            values.append(normalize_name(body.name))
            fields.append(f"normalized_name = ${len(values) + 1}")
        if body.unit is not None:
            values.append(body.unit)
            fields.append(f"unit = ${len(values) + 1}")
        if body.low_stock_threshold is not None:
            values.append(body.low_stock_threshold)
            fields.append(f"low_stock_threshold = ${len(values) + 1}")
        if body.archived is not None:
            fields.append("archived_at = %s" % ("NOW()" if body.archived else "NULL"))

        if fields:
            await conn.execute(
                f"UPDATE inventory_items SET {', '.join(fields)}, updated_at = NOW() WHERE id = $1",
                item_id, *values,
            )
        row = await conn.fetchrow("SELECT * FROM inventory_items WHERE id = $1", item_id)
    return InventoryItemOut(**dict(row))


@router.get("/movements", response_model=MovementListResponse)
async def list_movements(item_id: Optional[UUID] = None, limit: int = Query(50, le=200), offset: int = 0,
                          company_id: UUID = Depends(get_client_company_id),
                          _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        if item_id:
            rows = await conn.fetch(
                "SELECT * FROM inventory_movements WHERE company_id = $1 AND item_id = $2 "
                "ORDER BY created_at DESC LIMIT $3 OFFSET $4",
                company_id, item_id, limit, offset,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM inventory_movements WHERE company_id = $1 "
                "ORDER BY created_at DESC LIMIT $2 OFFSET $3",
                company_id, limit, offset,
            )
    return MovementListResponse(movements=[MovementOut(**dict(r)) for r in rows])


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(status: Optional[str] = None, company_id: UUID = Depends(get_client_company_id),
                       _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT * FROM inventory_orders WHERE company_id = $1 AND status = $2 ORDER BY created_at DESC",
                company_id, status,
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM inventory_orders WHERE company_id = $1 ORDER BY created_at DESC", company_id,
            )
    return OrderListResponse(orders=[
        OrderOut(**{**dict(r), "suggestion": orders_service.decode_suggestion(r["suggestion"])}) for r in rows
    ])


@router.post("/orders", response_model=OrderOut, status_code=201)
async def create_order(body: OrderCreate, company_id: UUID = Depends(get_client_company_id),
                        user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        row = await orders_service.stage_order(
            conn, company_id=company_id, item_id=body.item_id, channel_id=None, source_message_id=None,
            created_by=user.id,
            suggestion={"suggested_quantity": float(body.quantity)} if body.quantity is not None else None,
        )
    return OrderOut(**row)


@router.post("/orders/{order_id}/approve", response_model=OrderOut)
async def approve_order_route(order_id: UUID, body: OrderAction,
                               company_id: UUID = Depends(get_client_company_id),
                               user=Depends(require_admin_or_client)):
    if user.role not in ("client", "admin"):
        raise HTTPException(403, "Only a manager can approve an order.")
    async with get_connection() as conn:
        row = await orders_service.approve_order(
            conn, order_id=order_id, company_id=company_id, user_id=user.id, quantity=body.quantity,
        )
    if row is None:
        raise HTTPException(404, "No queued order found.")
    return OrderOut(**row)


@router.post("/orders/{order_id}/receive", response_model=OrderOut)
async def receive_order_route(order_id: UUID, body: OrderAction,
                               company_id: UUID = Depends(get_client_company_id),
                               user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        row = await orders_service.mark_received(
            conn, order_id=order_id, company_id=company_id, user_id=user.id, quantity=body.quantity,
        )
    if row is None:
        raise HTTPException(404, "No open order found.")
    return OrderOut(**row)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
async def cancel_order_route(order_id: UUID, company_id: UUID = Depends(get_client_company_id),
                              user=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        row = await orders_service.cancel_order(conn, order_id=order_id, company_id=company_id, user_id=user.id)
    if row is None:
        raise HTTPException(404, "No cancellable order found.")
    return OrderOut(**row)


@router.get("/suggestions", response_model=dict)
async def list_suggestions(company_id: UUID = Depends(get_client_company_id),
                            _=Depends(require_admin_or_client)):
    from datetime import datetime, timezone

    async with get_connection() as conn:
        items = await conn.fetch(
            "SELECT id, name FROM inventory_items WHERE company_id = $1 AND archived_at IS NULL", company_id,
        )
        out = {}
        for item in items:
            movement_rows = await conn.fetch(
                "SELECT kind, quantity, quantity_delta, created_at FROM inventory_movements "
                "WHERE item_id = $1 AND created_at > NOW() - INTERVAL '90 days' ORDER BY created_at ASC",
                item["id"],
            )
            suggestion = suggest_order([dict(m) for m in movement_rows], datetime.now(timezone.utc))
            if suggestion:
                out[str(item["id"])] = {"name": item["name"], **suggestion}
    return out
