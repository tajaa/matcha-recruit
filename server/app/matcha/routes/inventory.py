"""Inventory router — items, movement ledger, order queue. Mounted under
/inventory, gated on the `inventory` feature flag at mount time (see
routes/__init__.py). Channel intake (auto-create + movements + order
staging) happens in server/app/werk/routes/channels_ws.py; this router is
the /work Inventory page's REST surface plus manual item/order management.
"""

import csv
import io
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.matcha.models.inventory import (
    InventoryItemCreate, InventoryItemOut, InventoryItemPatch, ItemListResponse,
    MovementListResponse, MovementOut, OrderAction, OrderCreate, OrderListResponse, OrderOut,
    ReceiptCommit, ReceiptCommitResult,
)
from app.matcha.services.inventory import movements as movements_service
from app.matcha.services.inventory import orders as orders_service
from app.matcha.services.inventory import receipts as receipts_service
from app.matcha.services.inventory.matching import normalize_name
from app.matcha.services.inventory.reorder import suggest_order

router = APIRouter()

_RECEIPT_MAX_BYTES = 15 * 1024 * 1024
_RECEIPT_EXT_OK = (".csv", ".pdf", ".png", ".jpg", ".jpeg", ".webp")


@router.get("/items", response_model=ItemListResponse)
async def list_items(include_archived: bool = False, company_id: UUID = Depends(get_client_company_id),
                      _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        clause = "" if include_archived else "AND archived_at IS NULL"
        rows = await conn.fetch(
            f"""
            SELECT it.*, bl.name AS location_name,
                   o.id AS order_id, o.status AS order_status,
                   o.suggested_quantity AS order_suggested_quantity, o.quantity AS order_quantity,
                   o.suggestion AS order_suggestion, o.created_at AS order_created_at,
                   o.updated_at AS order_updated_at
            FROM inventory_items it
            LEFT JOIN business_locations bl ON bl.id = it.location_id
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
        if body.location_id is not None:
            ok = await conn.fetchval(
                "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2 "
                "AND is_active IS NOT FALSE AND is_company_wide = FALSE",
                body.location_id, company_id,
            )
            if not ok:
                raise HTTPException(404, "Location not found.")
        existing = await conn.fetchval(
            "SELECT id FROM inventory_items WHERE company_id = $1 AND normalized_name = $2 "
            "AND location_id IS NOT DISTINCT FROM $3 AND archived_at IS NULL",
            company_id, normalized, body.location_id,
        )
        if existing:
            raise HTTPException(409, "An item with this name already exists.")
        row = await conn.fetchrow(
            """
            INSERT INTO inventory_items (company_id, name, normalized_name, unit, current_quantity,
                                         low_stock_threshold, created_by, location_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *
            """,
            company_id, body.name, normalized, body.unit, body.current_quantity,
            body.low_stock_threshold, user.id, body.location_id,
        )
    return InventoryItemOut(**dict(row))


@router.get("/items/{item_id}", response_model=dict)
async def get_item(item_id: UUID, company_id: UUID = Depends(get_client_company_id),
                    _=Depends(require_admin_or_client)):
    async with get_connection() as conn:
        item = await conn.fetchrow(
            "SELECT it.*, bl.name AS location_name FROM inventory_items it "
            "LEFT JOIN business_locations bl ON bl.id = it.location_id "
            "WHERE it.id = $1 AND it.company_id = $2",
            item_id, company_id,
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
            normalized = normalize_name(body.name)
            dup = await conn.fetchval(
                "SELECT id FROM inventory_items WHERE company_id = $1 AND normalized_name = $2 "
                "AND location_id IS NOT DISTINCT FROM $3 AND archived_at IS NULL AND id != $4",
                company_id, normalized, item["location_id"], item_id,
            )
            if dup:
                raise HTTPException(409, "An item with this name already exists.")
            values.append(body.name)
            fields.append(f"name = ${len(values) + 1}")
            values.append(normalized)
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


@router.get("/receipts/template")
async def receipt_template(_=Depends(require_admin_or_client)):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=list(receipts_service._CSV_FIELDS))
    w.writeheader()
    w.writerow({"item_name": "Nitrile Gloves (M)", "quantity": "10", "unit": "BX",
                "pack_size": "100/BX", "vendor_sku": "NG-100-M", "unit_price": "8.99"})
    out.seek(0)
    return StreamingResponse(
        io.BytesIO(out.getvalue().encode()), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=inventory_receipt_template.csv"},
    )


@router.post("/receipts/parse")
async def parse_receipt_route(
    file: UploadFile = File(...),
    location_id: Optional[UUID] = Query(None),
    company_id: UUID = Depends(get_client_company_id),
    _=Depends(require_admin_or_client),
):
    """Parse an invoice/packing slip into a reviewable draft. Writes NOTHING."""
    name = (file.filename or "").lower()
    if not name.endswith(_RECEIPT_EXT_OK):
        if name.endswith((".xlsx", ".xls")):
            raise HTTPException(400, "Export the spreadsheet as CSV first — .xlsx isn't supported.")
        raise HTTPException(400, "Upload a CSV, PDF, or photo of the invoice.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Empty file")
    if len(data) > _RECEIPT_MAX_BYTES:
        raise HTTPException(413, "File too large (max 15MB)")
    receipt = await receipts_service.parse_receipt(data, file.content_type or "", file.filename or "")
    async with get_connection() as conn:
        receipt["lines"] = await receipts_service.resolve_lines(
            conn, company_id=company_id, location_id=location_id, lines=receipt["lines"],
        )
    return receipt


@router.post("/receipts/commit", response_model=ReceiptCommitResult)
async def commit_receipt_route(
    body: ReceiptCommit,
    company_id: UUID = Depends(get_client_company_id),
    user=Depends(require_admin_or_client),
):
    """Write the user-reviewed lines: matched-order lines via mark_received
    (movement + order flip atomic together), the rest as bare `in`
    movements. PER-LINE transactions — one wrapping transaction can't
    survive a failed row in Postgres (first error aborts it), and the
    BulkUploadResult contract is that bad rows fail alone."""
    if not body.lines:
        raise HTTPException(400, "No lines to commit")
    if len(body.lines) > receipts_service.MAX_LINES:
        raise HTTPException(413, f"Too many lines (max {receipts_service.MAX_LINES})")
    note = None
    if body.vendor or body.invoice_number:
        note = " ".join(filter(None, [body.vendor, f"invoice {body.invoice_number}" if body.invoice_number else None]))

    errors: list[dict] = []
    movement_ids: list[str] = []
    created = 0
    async with get_connection() as conn:
        # Forceable duplicate guard (schedule-conflict 409 idiom): the note
        # stamped on every committed movement is what we match on.
        if body.invoice_number and not body.force:
            dup = await conn.fetchval(
                "SELECT 1 FROM inventory_movements WHERE company_id = $1 AND kind = 'in' "
                "AND note LIKE '%' || $2 || '%' LIMIT 1",
                company_id, f"invoice {body.invoice_number}",
            )
            if dup:
                raise HTTPException(409, detail={
                    "code": "duplicate_invoice",
                    "message": f"Invoice {body.invoice_number} looks already received — commit anyway?",
                })
        for n, line in enumerate(body.lines, start=1):
            try:
                async with conn.transaction():
                    if line.order_id is not None:
                        row = await orders_service.mark_received(
                            conn, order_id=line.order_id, company_id=company_id,
                            user_id=user.id, quantity=line.quantity,
                        )
                        if row is None:
                            raise ValueError("order not open")
                        movement_ids.append(str(row["receipt_movement_id"]))
                    else:
                        if line.item_id is not None:
                            item_id = line.item_id
                        elif line.new_item_name:
                            item = await movements_service.find_or_create_item(
                                conn, company_id, line.new_item_name,
                                created_by=user.id, location_id=body.location_id,
                            )
                            item_id = item["id"]
                        else:
                            raise ValueError("line needs item_id or new_item_name")
                        inserted = await movements_service.record_movements(
                            conn, company_id=company_id, channel_id=None,
                            source_message_id=None, recorded_by=user.id,
                            kind="in", narrative="Receipt ingest", note=note,
                            lines=[{"item_id": item_id, "quantity": line.quantity, "estimated": False}],
                        )
                        movement_ids.append(str(inserted[0]["id"]))
                    created += 1
            except Exception as exc:
                errors.append({"row": n, "item": line.new_item_name or str(line.item_id or ""), "error": str(exc)})
    return ReceiptCommitResult(total_rows=len(body.lines), created=created,
                               failed=len(errors), errors=errors, ids=movement_ids)
