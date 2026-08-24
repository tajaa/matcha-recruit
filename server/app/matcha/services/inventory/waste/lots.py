"""Advisory FEFO lots — never a second inventory quantity ledger."""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

logger = logging.getLogger(__name__)


async def record_lot(
    conn, *, company_id: UUID, item_id: UUID, location_id: Optional[UUID],
    received_movement_id: Optional[UUID], quantity, received_on: date,
    expires_on: Optional[date], lot_code: Optional[str], unit_cost,
    created_by: Optional[UUID],
) -> Optional[dict]:
    """Best-effort receipt annotation; failures never invalidate its movement."""
    try:
        # This is a savepoint when the receipt already owns a transaction.
        # Without it a lot-table failure would poison the receipt transaction.
        async with conn.transaction():
            item = await conn.fetchrow(
                "SELECT shelf_life_days, location_id FROM inventory_items WHERE id=$1 AND company_id=$2",
                item_id, company_id,
            )
            if item is None:
                return None
            if expires_on is None and item["shelf_life_days"]:
                expires_on = received_on + timedelta(days=int(item["shelf_life_days"]))
            row = await conn.fetchrow(
                """
                INSERT INTO inventory_lots
                    (company_id, item_id, location_id, received_movement_id, lot_code,
                     received_on, expires_on, quantity_received, quantity_remaining, unit_cost, created_by)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$8,$9,$10)
                ON CONFLICT (received_movement_id, item_id) WHERE received_movement_id IS NOT NULL
                DO NOTHING
                RETURNING *
                """,
                company_id, item_id, location_id or item["location_id"], received_movement_id,
                lot_code, received_on, expires_on, Decimal(str(quantity)), unit_cost, created_by,
            )
            return dict(row) if row is not None else None
    except Exception:
        logger.warning("inventory lot write failed", exc_info=True)
        return None


async def consume_fefo(conn, *, company_id: UUID, item_id: UUID, quantity) -> list[dict]:
    """Spend lot labels earliest-expiring first; never update item quantity."""
    remaining = Decimal(str(quantity))
    consumed: list[dict] = []
    if remaining <= 0:
        return consumed
    rows = await conn.fetch(
        """
        SELECT * FROM inventory_lots
        WHERE company_id=$1 AND item_id=$2 AND status='open' AND quantity_remaining > 0
        ORDER BY expires_on NULLS LAST, received_on, created_at FOR UPDATE
        """, company_id, item_id,
    )
    for row in rows:
        if remaining <= 0:
            break
        used = min(remaining, Decimal(str(row["quantity_remaining"])))
        after = Decimal(str(row["quantity_remaining"])) - used
        updated = await conn.fetchrow(
            """
            UPDATE inventory_lots
            SET quantity_remaining=$2, status=CASE WHEN $2=0 THEN 'depleted' ELSE 'open' END,
                updated_at=NOW()
            WHERE id=$1 RETURNING *
            """, row["id"], after,
        )
        consumed.append({"lot": dict(updated), "quantity": used})
        remaining -= used
    return consumed


async def expiring_lots(conn, *, company_id: UUID, location_id: Optional[UUID], within_days: int) -> list[dict]:
    return [dict(row) for row in await conn.fetch(
        """
        SELECT l.*, i.name, i.unit, (l.expires_on-CURRENT_DATE) AS days_to_expiry
        FROM inventory_lots l JOIN inventory_items i ON i.id=l.item_id
        WHERE l.company_id=$1 AND l.status='open' AND l.expires_on IS NOT NULL
          AND l.expires_on <= CURRENT_DATE + $3::int
          AND ($2::uuid IS NULL OR l.location_id IS NULL OR l.location_id=$2)
        ORDER BY l.expires_on, i.name
        """, company_id, location_id, max(0, within_days),
    )]


def spoilage_risk_score(*, quantity_remaining: Decimal, days_to_expiry: Optional[int], average_daily_demand: Decimal) -> dict:
    quantity = Decimal(str(quantity_remaining))
    demand = Decimal(str(average_daily_demand))
    if days_to_expiry is None:
        return {"score": Decimal("0"), "days_of_cover": quantity / demand if demand > 0 else None,
                "at_risk_quantity": Decimal("0"), "basis": "no_expiry"}
    days = max(0, int(days_to_expiry))
    cover = quantity / demand if demand > 0 else None
    at_risk = max(quantity - demand * Decimal(days), Decimal("0"))
    score = Decimal("1") if demand <= 0 and quantity > 0 else min(Decimal("1"), at_risk / quantity) if quantity > 0 else Decimal("0")
    return {"score": score, "days_of_cover": cover, "at_risk_quantity": at_risk,
            "basis": "expiry_vs_demand"}
