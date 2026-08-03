"""DB service for inventory items + the append-only movement ledger."""

from typing import Optional
from uuid import UUID

from app.matcha.services.inventory.matching import best_match, normalize_name


async def list_item_names(conn, company_id: UUID, location_id: Optional[UUID] = None) -> list[dict]:
    """Items visible in a store scope. A store-scoped channel sees its own
    items plus legacy company-wide (location_id IS NULL) rows; an unscoped
    channel (location_id=None) sees ONLY company-wide rows — two stores'
    same-named items would otherwise be indistinguishable to best_match.
    The /inventory page keeps listing everything (its own query)."""
    rows = await conn.fetch(
        "SELECT id, name, normalized_name, location_id FROM inventory_items "
        "WHERE company_id = $1 AND archived_at IS NULL "
        "AND (location_id IS NULL OR location_id = $2)",
        company_id, location_id,
    )
    return [dict(r) for r in rows]


async def find_or_create_item(
    conn, company_id: UUID, raw_name: str, *,
    created_by: Optional[UUID], location_id: Optional[UUID] = None,
) -> dict:
    existing = await list_item_names(conn, company_id, location_id)
    match = best_match(raw_name, existing)
    if match is not None:
        # May resolve to a shared NULL-location legacy item — intended.
        row = await conn.fetchrow("SELECT * FROM inventory_items WHERE id = $1", match["id"])
        return dict(row)

    normalized = normalize_name(raw_name)
    await conn.execute(
        """
        INSERT INTO inventory_items (company_id, location_id, name, normalized_name, auto_created, created_by)
        VALUES ($1, $2, $3, $4, TRUE, $5)
        ON CONFLICT (company_id, location_id, normalized_name) WHERE archived_at IS NULL DO NOTHING
        """,
        company_id, location_id, raw_name.strip(), normalized, created_by,
    )
    row = await conn.fetchrow(
        "SELECT * FROM inventory_items WHERE company_id = $1 AND normalized_name = $2 "
        "AND location_id IS NOT DISTINCT FROM $3 AND archived_at IS NULL",
        company_id, normalized, location_id,
    )
    return dict(row)


async def record_movements(
    conn, *, company_id: UUID, channel_id: Optional[UUID], source_message_id: Optional[UUID],
    recorded_by: Optional[UUID], kind: str, lines: list[dict], narrative: str, note: Optional[str],
) -> list[dict]:
    """lines: [{item_id, quantity (Decimal|None), estimated (bool)}]. kind
    applies to every line in this call (movement handler calls this once
    per kind: 'out'/'in'; stockout handler calls it separately with
    kind='stockout'). Returns inserted rows only — a WS replay that hits
    the ON CONFLICT DO NOTHING contributes nothing to the return list."""
    inserted = []
    for line in lines:
        quantity = line.get("quantity")
        estimated = bool(line.get("estimated", False))
        delta = None
        if kind == "out" and quantity is not None:
            delta = -abs(float(quantity))
        elif kind == "in" and quantity is not None:
            delta = abs(float(quantity))

        row = await conn.fetchrow(
            """
            INSERT INTO inventory_movements (
                company_id, item_id, channel_id, source_message_id, recorded_by,
                kind, quantity, quantity_delta, quantity_estimated, note, narrative
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (source_message_id, item_id) WHERE source_message_id IS NOT NULL DO NOTHING
            RETURNING *
            """,
            company_id, line["item_id"], channel_id, source_message_id, recorded_by,
            kind, quantity, delta, estimated, note, narrative,
        )
        if row is None:
            continue
        inserted.append(dict(row))

        if kind == "stockout":
            await conn.execute(
                "UPDATE inventory_items SET current_quantity = 0, updated_at = NOW() WHERE id = $1",
                line["item_id"],
            )
        elif delta is not None:
            await conn.execute(
                """
                UPDATE inventory_items SET current_quantity = CASE
                    WHEN current_quantity IS NULL THEN NULL
                    ELSE GREATEST(current_quantity + $2, 0)
                END, updated_at = NOW() WHERE id = $1
                """,
                line["item_id"], delta,
            )
    return inserted


async def amend_movement_quantity(conn, *, movement_id: UUID, quantity, user_id: UUID) -> Optional[dict]:
    """Only amends WHILE quantity_estimated=TRUE — the one sanctioned edit
    on an otherwise append-only ledger. Recomputes delta vs the old value
    and applies the diff to the item's running count."""
    old = await conn.fetchrow(
        "SELECT * FROM inventory_movements WHERE id = $1 AND quantity_estimated = TRUE", movement_id,
    )
    if old is None:
        return None
    old_qty = float(old["quantity"] or 0)
    new_qty = float(quantity)
    sign = -1 if old["kind"] == "out" else 1
    diff = sign * (new_qty - old_qty)

    row = await conn.fetchrow(
        """
        UPDATE inventory_movements
        SET quantity = $2, quantity_delta = $3, quantity_estimated = FALSE,
            amended_by = $4, amended_at = NOW()
        WHERE id = $1
        RETURNING *
        """,
        movement_id, new_qty, sign * new_qty, user_id,
    )
    await conn.execute(
        """
        UPDATE inventory_items SET current_quantity = CASE
            WHEN current_quantity IS NULL THEN NULL
            ELSE GREATEST(current_quantity + $2, 0)
        END, updated_at = NOW() WHERE id = $1
        """,
        old["item_id"], diff,
    )
    return dict(row)


async def adjust_item_count(conn, *, item_id: UUID, company_id: UUID, quantity, user_id: UUID) -> dict:
    """The ONLY set-count path — never write inventory_items.current_quantity
    directly from a route handler."""
    old = await conn.fetchrow(
        "SELECT current_quantity FROM inventory_items WHERE id = $1 AND company_id = $2",
        item_id, company_id,
    )
    if old is None:
        raise ValueError("item not found")
    old_qty = old["current_quantity"]
    new_qty = float(quantity)
    delta = None if old_qty is None else new_qty - float(old_qty)

    await conn.execute(
        "UPDATE inventory_items SET current_quantity = $2, updated_at = NOW() WHERE id = $1",
        item_id, new_qty,
    )
    row = await conn.fetchrow(
        """
        INSERT INTO inventory_movements (
            company_id, item_id, recorded_by, kind, quantity, quantity_delta, narrative
        ) VALUES ($1, $2, $3, 'adjust', $4, $5, 'Manual count adjustment')
        RETURNING *
        """,
        company_id, item_id, user_id, new_qty, delta,
    )
    return dict(row)
