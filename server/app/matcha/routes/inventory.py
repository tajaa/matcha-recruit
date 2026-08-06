"""Inventory router — items, movement ledger, order queue. Mounted under
/inventory, gated on the `inventory` feature flag at mount time (see
routes/__init__.py). Channel intake (auto-create + movements + order
staging) happens in server/app/werk/routes/channels_ws.py; this router is
the /work Inventory page's REST surface plus manual item/order management.
"""

import csv
import io
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.services.redis_cache import check_rate_limit
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client, require_feature
from app.matcha.models.inventory import (
    AuditCommit, AuditCommitResult, InventoryItemCreate, InventoryItemOut, InventoryItemPatch,
    ItemListResponse, MovementListResponse, MovementOut, OrderAction, OrderCreate,
    OrderListResponse, OrderOut, ReceiptCommit, ReceiptCommitResult, VoiceCountDraft,
)
from app.matcha.services._shared.uploads import read_wav_or_400
from app.matcha.services.inventory import audits as audits_service
from app.matcha.services.inventory import movements as movements_service
from app.matcha.services.inventory import orders as orders_service
from app.matcha.services.inventory import receipts as receipts_service
from app.matcha.services.inventory import voice_audit
from app.matcha.services.inventory.matching import normalize_name
from app.matcha.services.inventory.reorder import suggest_order

router = APIRouter()
logger = logging.getLogger(__name__)

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
    async with get_connection() as conn:
        try:
            row = await movements_service.create_item_checked(
                conn, company_id=company_id, name=body.name, unit=body.unit,
                current_quantity=body.current_quantity, low_stock_threshold=body.low_stock_threshold,
                location_id=body.location_id, created_by=user.id,
            )
        except ValueError as exc:
            if str(exc) == "location not found":
                raise HTTPException(404, "Location not found.")
            raise HTTPException(409, "An item with this name already exists.")
    return InventoryItemOut(**row)


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
        async with conn.transaction():
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


@router.post("/audit/commit", response_model=AuditCommitResult)
async def commit_audit(body: AuditCommit, company_id: UUID = Depends(get_client_company_id),
                        user=Depends(require_admin_or_client)):
    """Bulk stock-count save from the Audit sheet — one or many item counts
    in a single request, each written as a kind='adjust' movement (see
    services/inventory/audits.py). Untouched items simply aren't in
    `lines` — the sheet only sends rows the manager actually edited."""
    if not body.lines:
        raise HTTPException(400, "No counts to save.")
    if len(body.lines) > audits_service.MAX_LINES:
        raise HTTPException(413, f"Too many lines (max {audits_service.MAX_LINES}).")
    async with get_connection() as conn:
        try:
            result = await audits_service.commit_audit_lines(
                conn, company_id=company_id, user_id=user.id,
                location_id=body.location_id, note=body.note,
                lines=[line.model_dump() for line in body.lines],
            )
        except ValueError as exc:
            if str(exc) != "location not found":
                raise
            raise HTTPException(404, "Location not found.")
    return AuditCommitResult(**result)


@router.post("/audit/voice-parse", response_model=VoiceCountDraft)
async def parse_audit_voice(
    file: UploadFile = File(...),
    location_id: Optional[UUID] = Query(None),
    current_user=Depends(require_admin_or_client),
    _gate=Depends(require_feature("inventory_voice")),
):
    """Dictate stock counts instead of typing them — one Gemini multimodal
    parse of a WAV recording into a count-per-item draft. Writes nothing;
    the Audit sheet merges the result and the manager saves via
    POST /audit/commit as normal. 2-segment path so it isn't shadowed by
    /items/{item_id}-style single-segment routes."""
    # Each parse is an expensive Gemini multimodal call — same rate-limit
    # shape as ir_voice_intake's /voice/parse (burst + hourly per-user,
    # hourly per-company), own action keys so the two features don't share
    # a budget.
    user_key = f"user:{current_user.id}"
    await check_rate_limit(user_key, "inv_voice_parse_burst", 5, 60)
    await check_rate_limit(user_key, "inv_voice_parse", 40, 3600)

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")
    await check_rate_limit(str(company_id), "inv_voice_parse_co", 120, 3600)

    audio = await read_wav_or_400(file)

    async with get_connection() as conn:
        catalog = await movements_service.list_item_names_for_audit(conn, company_id, location_id)

    # Gemini call happens with no pooled connection held — it can take up to
    # 2x VOICE_PARSE_TIMEOUT on a retry, same reasoning as ir_voice_intake's
    # voice.py.
    parsed = await voice_audit.parse_voice_counts(
        audio, (file.content_type or "audio/wav").lower(),
        item_names=[row["name"] for row in catalog],
    )
    resolved = await voice_audit.resolve_count_lines(
        None, company_id=company_id, location_id=location_id, lines=parsed["lines"],
        existing=catalog,
    )
    return VoiceCountDraft(
        available=parsed["available"], transcript=parsed["transcript"],
        model=parsed["model"], lines=resolved,
    )


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
    """Delegates to receipts_service.commit_receipt_lines — see that
    docstring for the transaction/error-shape contract."""
    if not body.lines:
        raise HTTPException(400, "No lines to commit")
    if len(body.lines) > receipts_service.MAX_LINES:
        raise HTTPException(413, f"Too many lines (max {receipts_service.MAX_LINES})")

    lines = [
        {"item_id": line.item_id, "new_item_name": line.new_item_name,
         "quantity": line.quantity, "order_id": line.order_id}
        for line in body.lines
    ]
    async with get_connection() as conn:
        try:
            result = await receipts_service.commit_receipt_lines(
                conn, company_id=company_id, user_id=user.id, location_id=body.location_id,
                vendor=body.vendor, invoice_number=body.invoice_number, force=body.force, lines=lines,
            )
        except ValueError:
            raise HTTPException(404, "Location not found.")
        except receipts_service.DuplicateInvoiceError as exc:
            raise HTTPException(409, detail={"code": "duplicate_invoice", "message": str(exc)})
    return ReceiptCommitResult(**result)
