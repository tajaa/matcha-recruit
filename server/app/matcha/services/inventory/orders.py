"""DB service for the inventory order queue."""

import json
from datetime import date
from typing import Optional
from uuid import UUID

from app.matcha.services.inventory import movements as movements_service
from app.matcha.services.inventory._codec import decode_jsonb
from app.matcha.services.inventory.waste import lots as lots_service


def decode_suggestion(value):
    return decode_jsonb(value, None)


async def stage_order(
    conn, *, company_id: UUID, item_id: UUID, channel_id: Optional[UUID],
    source_message_id: Optional[UUID], created_by: Optional[UUID], suggestion: Optional[dict],
) -> dict:
    """A repeat stockout re-points the confirm pill at the SAME queued
    order (partial unique index uniq_inventory_orders_open enforces one
    queued order per item) rather than erroring or duplicating."""
    suggested_quantity = suggestion.get("suggested_quantity") if suggestion else None
    row = await conn.fetchrow(
        """
        INSERT INTO inventory_orders (
            company_id, item_id, channel_id, source_message_id, created_by,
            suggested_quantity, quantity, suggestion
        ) VALUES ($1, $2, $3, $4, $5, $6, $6, $7)
        ON CONFLICT (item_id) WHERE status = 'queued'
        DO UPDATE SET suggestion = EXCLUDED.suggestion,
                      suggested_quantity = EXCLUDED.suggested_quantity,
                      quantity = EXCLUDED.quantity,
                      updated_at = NOW()
        RETURNING *
        """,
        company_id, item_id, channel_id, source_message_id, created_by,
        suggested_quantity, json.dumps(suggestion) if suggestion is not None else None,
    )
    result = dict(row)
    result["suggestion"] = decode_suggestion(result.get("suggestion"))
    return result


async def approve_order(conn, *, order_id: UUID, company_id: UUID, user_id: UUID, quantity=None) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        UPDATE inventory_orders
        SET status = 'ordered', quantity = COALESCE($3, quantity),
            approved_by = $2, approved_at = NOW(), ordered_at = NOW(),
            confirm_message_id = NULL, updated_at = NOW()
        WHERE id = $1 AND company_id = $4 AND status = 'queued'
        RETURNING *
        """,
        order_id, user_id, quantity, company_id,
    )
    if row is None:
        return None
    result = dict(row)
    result["suggestion"] = decode_suggestion(result.get("suggestion"))
    return result


async def cancel_order(conn, *, order_id: UUID, company_id: UUID, user_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        UPDATE inventory_orders
        SET status = 'cancelled', confirm_message_id = NULL, updated_at = NOW()
        WHERE id = $1 AND company_id = $2 AND status IN ('queued', 'ordered')
        RETURNING *
        """,
        order_id, company_id,
    )
    if row is None:
        return None
    result = dict(row)
    result["suggestion"] = decode_suggestion(result.get("suggestion"))
    return result


async def mark_received(
    conn, *, order_id: UUID, company_id: UUID, user_id: UUID, quantity=None, note: Optional[str] = None,
    source_message_id: Optional[UUID] = None,
) -> Optional[dict]:
    order = await conn.fetchrow(
        "SELECT * FROM inventory_orders WHERE id = $1 AND company_id = $2 AND status IN ('queued', 'ordered')",
        order_id, company_id,
    )
    if order is None:
        return None
    received_qty = float(quantity) if quantity is not None else float(order["quantity"] or 0)

    inserted = await movements_service.record_movements(
        conn, company_id=company_id, channel_id=order["channel_id"], source_message_id=source_message_id,
        recorded_by=user_id, kind="in", narrative="Order received", note=note,
        lines=[{"item_id": order["item_id"], "quantity": received_qty, "estimated": False}],
    )
    if not inserted:
        # ON CONFLICT (source_message_id, item_id) DO NOTHING hit — a retry of
        # the same WS message for the same item. The order is still queued/
        # ordered (the SELECT above already excludes a previously-received
        # one), so surface this the same as "not open" rather than crashing
        # on movement["id"] below.
        return None
    movement = inserted[0]
    await lots_service.record_lot(
        conn, company_id=company_id, item_id=order["item_id"], location_id=None,
        received_movement_id=movement["id"], quantity=received_qty, received_on=date.today(),
        expires_on=None, lot_code=None, unit_cost=None, created_by=user_id,
    )
    row = await conn.fetchrow(
        """
        UPDATE inventory_orders
        SET status = 'received', received_by = $2, received_at = NOW(),
            received_quantity = $3, receipt_movement_id = $4, updated_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        order_id, user_id, received_qty, movement["id"],
    )
    result = dict(row)
    result["suggestion"] = decode_suggestion(result.get("suggestion"))
    return result
