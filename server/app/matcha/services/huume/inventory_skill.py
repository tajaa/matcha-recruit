"""Huume's inventory-ops executors — stock movements, order decisions, item
create/archive, receipt-attachment commits.

Every function here assumes `actions.evaluate_huume_action` already returned
`kind == "proceed"`: the role/flag/two-turn envelope and all field validation
happened there, purely. This module only does the DB work, wrapping the SAME
shared writers `routes/inventory.py` uses (`services/inventory/movements.py`,
`orders.py`, `receipts.py`) — a chat-originated write and a page-originated
write land in the identical ledger row shape. Return shape mirrors
`hr_ops_skill.py`: `{status, message, record_id?, record_label?, bg_tasks?}`.

`stage_inventory_order` (a plain WRITE tool, not staged — see agent.py) does
NOT go through this module's `execute()` dispatch; it's handled directly in
the loop, mirroring `services/ems/channel_agent.py`'s tool of the same name.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_LOOKUP_HINT = "look it up again with lookup_context(topic='inventory')."

_ROW_HEADER_RE = re.compile(r"^Row \d+:$")


def _parse_row_block_lines(text: str) -> list[dict]:
    """Attachment text reaching Huume was already run through
    `ERDocumentParser.extract_text_from_bytes` (`_build_thread_file_attachment_
    meta` in turn_pipeline.py) for EVERY file type, including CSV —
    `ERDocumentParser.parse_csv` reformats it into human-readable "Row N:" /
    "  key: value" blocks rather than passing the original CSV through, so
    `receipts.parse_csv_bytes`'s `csv.DictReader` can't read it directly.
    This reconstructs row dicts from that reformatted shape (keys are the
    original CSV header names, lowercased by this parser to match
    `receipts._CSV_FIELDS`) rather than threading a raw-bytes path through
    the whole messaging pipeline just for this one tool."""
    rows: list[dict] = []
    current: dict = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _ROW_HEADER_RE.match(stripped):
            if current:
                rows.append(current)
            current = {}
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            current[key.strip().lower()] = value.strip()
    if current:
        rows.append(current)
    return rows


async def execute(*, company_id: UUID, actor_user_id: Optional[UUID], action: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a validated staged inventory action to its executor."""
    atype = action.get("type")
    if atype == "inventory_movement":
        return await _execute_movement(company_id, actor_user_id, action)
    if atype == "inventory_order_decision":
        return await _execute_order_decision(company_id, actor_user_id, action)
    if atype == "inventory_item_create":
        return await _execute_item_create(company_id, actor_user_id, action)
    if atype == "inventory_item_archive":
        return await _execute_item_archive(company_id, actor_user_id, action)
    if atype == "inventory_receipt":
        return await _execute_receipt(company_id, actor_user_id, action)
    return {"status": "error", "message": "Unsupported action."}


async def _resolve_location(conn, company_id: UUID, location_id_str: Optional[str]) -> Optional[UUID]:
    """None passes through as company-wide. A bad/foreign id refuses rather
    than silently falling back to company-wide — the admin named a specific
    store and got it wrong, that's worth surfacing."""
    if not location_id_str:
        return None
    location_id = UUID(location_id_str)
    ok = await conn.fetchval(
        "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2 "
        "AND is_active IS NOT FALSE AND is_company_wide = FALSE",
        location_id, company_id,
    )
    if not ok:
        raise ValueError("location not found")
    return location_id


async def stage_order(
    *, company_id: UUID, actor_user_id: Optional[UUID], role: Optional[str],
    features: Optional[dict[str, Any]], item_id: Optional[str], new_item_name: Optional[str],
    quantity: Any, location_id_str: Optional[str],
) -> dict[str, Any]:
    """Backs the thread-mode `stage_inventory_order` WRITE tool (no confirm
    needed — queuing IS the staging step; decide_inventory_order approves/
    receives/cancels it). Copies `services/ems/channel_agent.py:
    _stage_inventory_order`'s writer sequence exactly (find_or_create_item ->
    suggest_order -> orders.stage_order) so a chat-staged order and a
    channel-staged order are indistinguishable rows — minus the pill text,
    which is a channel-only concept."""
    from datetime import datetime, timezone

    from app.database import get_connection
    from app.matcha.services.inventory import movements as movements_service
    from app.matcha.services.inventory import orders as orders_service
    from app.matcha.services.inventory.reorder import suggest_order
    from app.matcha.services.inventory.rules import APPROVE_ROLES, evaluate_inventory_action

    verdict = evaluate_inventory_action(role=role, features=features, stage="movement")
    if not verdict.ok:
        return {"status": "error", "message": verdict.reason}
    # A thread's collaborators are a broader/less-trusted population than a
    # channel's members — unlike the channel-side twin this mirrors, staging
    # a real order here needs the same admin-only gate every other Huume
    # write in this thread already carries.
    if (role or "").strip().lower() not in APPROVE_ROLES:
        return {"status": "error", "message": "Only a business admin can do this."}

    async with get_connection() as conn:
        try:
            location_id = await _resolve_location(conn, company_id, location_id_str)
        except ValueError:
            return {"status": "error", "message": "I couldn't find that location — check lookup_context(topic='locations')."}

        if item_id is not None:
            try:
                item_uuid = UUID(item_id)
            except ValueError:
                return {"status": "error", "message": f"I couldn't find that item — {_LOOKUP_HINT}"}
            item = await conn.fetchrow(
                "SELECT id, name FROM inventory_items WHERE id = $1 AND company_id = $2 AND archived_at IS NULL",
                item_uuid, company_id,
            )
            if item is None:
                return {"status": "error", "message": f"I couldn't find that item — {_LOOKUP_HINT}"}
        elif new_item_name:
            async with conn.transaction():
                item = await movements_service.find_or_create_item(
                    conn, company_id, new_item_name, created_by=actor_user_id, location_id=location_id,
                )
        else:
            return {"status": "error", "message": "I need either an item_id or a new_item_name."}

        history_rows = await conn.fetch(
            "SELECT kind, quantity, quantity_delta, created_at FROM inventory_movements "
            "WHERE item_id = $1 ORDER BY created_at ASC",
            item["id"],
        )
        suggestion = suggest_order([dict(r) for r in history_rows], datetime.now(timezone.utc))
        explicit_qty = isinstance(quantity, (int, float)) and not isinstance(quantity, bool) and quantity > 0
        order_qty = (
            float(quantity) if explicit_qty
            else (suggestion.get("suggested_quantity") if suggestion else None)
        )
        async with conn.transaction():
            order = await orders_service.stage_order(
                conn, company_id=company_id, item_id=item["id"], channel_id=None,
                source_message_id=None, created_by=actor_user_id, suggestion=suggestion,
            )
            if order_qty is not None and order_qty != order.get("quantity"):
                await conn.execute("UPDATE inventory_orders SET quantity = $1 WHERE id = $2", order_qty, order["id"])

    if order_qty is None:
        qty_note = " (no suggested quantity yet)"
    elif explicit_qty:
        qty_note = f" ({order_qty:g})"
    else:
        qty_note = f" (suggested {order_qty:g})"
    return {
        "status": "created",
        "message": f"Queued an order for {item['name']}{qty_note}. Approve with decide_inventory_order or on the Inventory page.",
        "order_id": str(order["id"]), "record_label": item["name"],
    }


async def _execute_movement(company_id, actor_user_id, action) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.services.huume.actions import _INVENTORY_RECEIVED_STEER_MESSAGE
    from app.matcha.services.inventory import movements as movements_service

    kind = action["kind"]
    quantity = action.get("quantity")

    # Defense in depth — _validate_inventory_movement already refuses kind='in'
    # on the confirm turn and the tool's schema enum excludes it as the
    # primary gate, but this executor is reachable from anywhere a caller
    # assembles an `action` dict directly, so the invariant is walled here too.
    if kind == "in":
        return {"status": "error", "message": _INVENTORY_RECEIVED_STEER_MESSAGE}

    async with get_connection() as conn:
        try:
            location_id = await _resolve_location(conn, company_id, action.get("location_id"))
        except ValueError:
            return {"status": "error", "message": "I couldn't find that location — check lookup_context(topic='locations')."}

        item_id = action.get("item_id")
        if item_id is not None:
            item = await conn.fetchrow(
                "SELECT id, name FROM inventory_items WHERE id = $1 AND company_id = $2 AND archived_at IS NULL",
                UUID(item_id), company_id,
            )
            if item is None:
                return {"status": "error", "message": f"I couldn't find that item — {_LOOKUP_HINT}"}
            item_id, item_name = item["id"], item["name"]
        elif action.get("new_item_name"):
            async with conn.transaction():
                item = await movements_service.find_or_create_item(
                    conn, company_id, action["new_item_name"],
                    created_by=actor_user_id, location_id=location_id,
                )
            item_id, item_name = item["id"], item["name"]
        else:
            return {"status": "error", "message": "I need either an item_id or a new_item_name."}

        if kind == "adjust":
            async with conn.transaction():
                row = await movements_service.adjust_item_count(
                    conn, item_id=item_id, company_id=company_id, quantity=quantity, user_id=actor_user_id,
                    note=action.get("note"),
                )
            message = f"Set {item_name} to {quantity}."
        else:
            async with conn.transaction():
                inserted = await movements_service.record_movements(
                    conn, company_id=company_id, channel_id=None, source_message_id=None,
                    recorded_by=actor_user_id, kind=kind, narrative="Recorded via Huume chat",
                    note=action.get("note"),
                    lines=[{"item_id": item_id, "quantity": quantity, "estimated": False}],
                )
            row = inserted[0] if inserted else None
            if kind == "stockout":
                message = f"Marked {item_name} as out of stock."
            else:
                message = f"Recorded {quantity} {item_name} used."

    return {
        "status": "created", "message": message,
        "record_id": str(row["id"]) if row else str(item_id),
        "record_label": item_name, "bg_tasks": [],
    }


async def _execute_order_decision(company_id, actor_user_id, action) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.services.inventory import orders as orders_service

    order_id = UUID(action["order_id"])
    decision = action["decision"]
    quantity = action.get("quantity")

    async with get_connection() as conn:
        async with conn.transaction():
            if decision == "approve":
                row = await orders_service.approve_order(
                    conn, order_id=order_id, company_id=company_id, user_id=actor_user_id, quantity=quantity,
                )
                verb = "Approved"
            elif decision == "receive":
                row = await orders_service.mark_received(
                    conn, order_id=order_id, company_id=company_id, user_id=actor_user_id,
                    quantity=quantity, note="Received via Huume chat",
                )
                verb = "Received"
            else:
                row = await orders_service.cancel_order(
                    conn, order_id=order_id, company_id=company_id, user_id=actor_user_id,
                )
                verb = "Cancelled"

    if row is None:
        return {"status": "error",
                "message": "That order isn't open anymore — it may already be received or cancelled."}
    item_name = await _item_name_for(company_id, row["item_id"])
    return {
        "status": "created", "message": f"{verb} the order for {item_name}.",
        "record_id": str(order_id), "record_label": item_name, "bg_tasks": [],
    }


async def _item_name_for(company_id: UUID, item_id: UUID) -> str:
    from app.database import get_connection

    async with get_connection() as conn:
        name = await conn.fetchval(
            "SELECT name FROM inventory_items WHERE id = $1 AND company_id = $2", item_id, company_id,
        )
    return name or "the item"


async def _execute_item_create(company_id, actor_user_id, action) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.services.inventory import movements as movements_service

    async with get_connection() as conn:
        try:
            location_id = await _resolve_location(conn, company_id, action.get("location_id"))
        except ValueError:
            return {"status": "error", "message": "I couldn't find that location — check lookup_context(topic='locations')."}
        try:
            async with conn.transaction():
                row = await movements_service.create_item_checked(
                    conn, company_id=company_id, name=action["name"], unit=action.get("unit"),
                    current_quantity=action.get("initial_quantity"),
                    low_stock_threshold=action.get("low_stock_threshold"),
                    location_id=location_id, created_by=actor_user_id,
                )
        except ValueError as exc:
            if str(exc) == "duplicate item":
                return {"status": "error", "message": f"An item named '{action['name']}' already exists there."}
            return {"status": "error", "message": "I couldn't find that location — check lookup_context(topic='locations')."}

    return {
        "status": "created", "message": f"Added {row['name']} to inventory.",
        "record_id": str(row["id"]), "record_label": row["name"], "bg_tasks": [],
    }


async def _execute_item_archive(company_id, actor_user_id, action) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.services.inventory import movements as movements_service

    item_id = UUID(action["item_id"])
    async with get_connection() as conn:
        async with conn.transaction():
            row = await movements_service.archive_item(conn, company_id=company_id, item_id=item_id)

    if row is None:
        return {"status": "error", "message": "That item wasn't found or is already archived."}
    return {
        "status": "created", "message": f"Archived {row['name']}.",
        "record_id": str(item_id), "record_label": row["name"], "bg_tasks": [],
    }


def _to_commit_lines(resolved_lines: list[dict]) -> list[dict]:
    """Translate `receipts.resolve_lines`' output (item_name/item_id/
    matched_name/exact/open_order_id) into the shape `commit_receipt_lines`
    reads (item_id/new_item_name/order_id/quantity). The REST path does this
    same translation client-side (`ReceiveDeliveryModal.tsx`) after a human
    reviews/edits each line; the chat path has no review step, so a matched
    item commits against its match and its open order verbatim, and an
    unmatched line commits as a new item."""
    out = []
    for line in resolved_lines:
        item_id = line.get("item_id")
        out.append({
            "item_id": item_id,
            "new_item_name": None if item_id else line.get("item_name"),
            "order_id": line.get("open_order_id") if item_id else None,
            "quantity": line.get("quantity"),
        })
    return out


async def parse_attachment_for_staging(
    attachment_texts: Optional[list[str]], company_id: UUID, location_id_str: Optional[str],
) -> dict[str, Any]:
    """Pure-ish staging helper called by agent.py on the STAGE turn for
    stage_receipt_from_attachment, BEFORE the action is written to
    current_state — resolves the attachment into lines the confirm turn can
    commit verbatim. Never lets the model see or retype line items itself.
    Returns either {"lines","vendor","invoice_number","note"} to merge into
    the staged dict, or {"error": <message>} to refuse staging outright."""
    from app.database import get_connection
    from app.matcha.services.inventory import receipts as receipts_service

    # Most recent attachment first — a thread can accumulate several invoice
    # attachments over its history, and "receive this" should stage whatever
    # was just attached, not the oldest one that happens to parse.
    for text in reversed(attachment_texts or []):
        # Try raw CSV first (a future extraction change could pass it
        # through verbatim), then the reformatted "Row N:" shape the current
        # pipeline actually produces (see _parse_row_block_lines).
        parsed_csv = None
        lines = []
        try:
            parsed_csv = receipts_service.parse_csv_bytes(text.encode("utf-8"))
            lines = parsed_csv["lines"]
        except Exception:
            parsed_csv = None
        if not lines:
            lines = [
                line for raw in _parse_row_block_lines(text)
                if (line := receipts_service.coerce_receipt_line(raw)) is not None
            ]
        receipt = {
            "vendor": parsed_csv.get("vendor") if parsed_csv else None,
            "invoice_number": parsed_csv.get("invoice_number") if parsed_csv else None,
            "lines": lines,
        }
        if not receipt["lines"]:
            continue

        async with get_connection() as conn:
            try:
                location_id = await _resolve_location(conn, company_id, location_id_str)
            except ValueError:
                return {"error": "I couldn't find that location — check lookup_context(topic='locations')."}
            resolved = await receipts_service.resolve_lines(
                conn, company_id=company_id, location_id=location_id, lines=receipt["lines"],
            )
            dup_warning = None
            if receipt.get("invoice_number"):
                dup = await conn.fetchval(
                    "SELECT 1 FROM inventory_movements WHERE company_id = $1 AND kind = 'in' "
                    "AND note LIKE '%' || replace(replace($2, '%', '\\%'), '_', '\\_') || '%' ESCAPE '\\' LIMIT 1",
                    company_id, f"invoice {receipt['invoice_number']}",
                )
                if dup:
                    dup_warning = f"Invoice {receipt['invoice_number']} looks already received."

        return {
            "lines": _to_commit_lines(resolved[: receipts_service.MAX_LINES]),
            "vendor": receipt.get("vendor"),
            "invoice_number": receipt.get("invoice_number"),
            "dup_warning": dup_warning,
        }

    return {"error": "I didn't find a CSV attachment I could read line items from. "
                      "Export PDF/photo invoices as CSV first, or use Receive Delivery on the Inventory page."}


async def _execute_receipt(company_id, actor_user_id, action) -> dict[str, Any]:
    from app.database import get_connection
    from app.matcha.services.inventory import receipts as receipts_service

    lines = action.get("lines") or []
    if not lines:
        return {"status": "error", "message": "There were no lines staged to commit — attach the invoice again."}

    location_id = UUID(action["location_id"]) if action.get("location_id") else None
    async with get_connection() as conn:
        try:
            # force=True: the admin already confirmed this exact staged
            # receipt — including any dup_warning shown at stage time — so
            # the confirm turn itself is the "commit anyway" authorization.
            # No separate override round-trip (see stage_receipt_from_attachment's
            # tool description).
            result = await receipts_service.commit_receipt_lines(
                conn, company_id=company_id, user_id=actor_user_id, location_id=location_id,
                vendor=action.get("vendor"), invoice_number=action.get("invoice_number"),
                force=True, lines=lines,
            )
        except ValueError:
            return {"status": "error", "message": "I couldn't find that location — check lookup_context(topic='locations')."}

    message = f"Recorded {result['created']} of {result['total_rows']} line(s)."
    if result["failed"]:
        first_err = result["errors"][0]["error"] if result["errors"] else "unknown error"
        message += f" {result['failed']} failed ({first_err})."
    return {
        "status": "created" if result["created"] > 0 else "error", "message": message,
        "record_id": ",".join(result["ids"]) or None, "record_label": "receipt", "bg_tasks": [],
    }
