"""Expected-on-hand breakdown and audit variance calculations."""

from decimal import Decimal
from typing import Optional
from uuid import UUID


async def expected_breakdown(conn, company_id: UUID, item_ids: list[UUID], location_id: Optional[UUID]) -> list[dict]:
    if not item_ids:
        return []
    rows = await conn.fetch(
        """
        WITH baselines AS (
            SELECT DISTINCT ON (item_id) item_id, created_at AS baseline_at,
                   quantity AS baseline
            FROM inventory_movements
            WHERE company_id=$1 AND item_id=ANY($2::uuid[]) AND kind='adjust'
            ORDER BY item_id, created_at DESC, id DESC
        ), buckets AS (
            SELECT m.item_id,
                   SUM(CASE WHEN m.kind='in' THEN ABS(COALESCE(m.quantity_delta,0)) ELSE 0 END) AS received,
                   SUM(CASE WHEN m.kind='sale' THEN -COALESCE(m.quantity_delta,0) ELSE 0 END) AS sold,
                   SUM(CASE WHEN m.kind='out' THEN ABS(COALESCE(m.quantity_delta,0)) ELSE 0 END) AS manual_out,
                   SUM(CASE WHEN m.kind='stockout' THEN 1 ELSE 0 END) AS stockouts
            FROM inventory_movements m
            LEFT JOIN baselines b ON b.item_id=m.item_id
            WHERE m.company_id=$1 AND m.item_id=ANY($2::uuid[])
              AND (b.baseline_at IS NULL OR m.created_at > b.baseline_at)
            GROUP BY m.item_id
        )
        SELECT i.id AS item_id, i.current_quantity AS expected, i.unit_cost,
               b.baseline, b.baseline_at,
               COALESCE(k.received,0) AS received, COALESCE(k.sold,0) AS sold,
               COALESCE(k.manual_out,0) AS manual_out, COALESCE(k.stockouts,0) AS stockouts
        FROM inventory_items i
        LEFT JOIN baselines b ON b.item_id=i.id
        LEFT JOIN buckets k ON k.item_id=i.id
        WHERE i.company_id=$1 AND i.id=ANY($2::uuid[])
          AND ($3::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$3)
        """,
        company_id, item_ids, location_id,
    )
    return [dict(row) for row in rows]


def variance_rollup(lines: list[dict], items: dict | list[dict]) -> dict:
    by_id = items if isinstance(items, dict) else {str(item["id"]): item for item in items}
    total_units = Decimal("0")
    total_value = Decimal("0")
    over = []
    short = []
    for line in lines:
        expected = line.get("expected")
        counted = line.get("counted_quantity", line.get("counted"))
        if expected is None or counted is None:
            continue
        variance = Decimal(str(counted)) - Decimal(str(expected))
        item = by_id.get(str(line.get("item_id")), line)
        cost = item.get("unit_cost")
        value = variance * Decimal(str(cost)) if cost is not None else None
        total_units += variance
        if value is not None:
            total_value += value
        entry = {"item_id": str(line.get("item_id")), "name": item.get("name"),
                 "units": variance, "value": value}
        (over if variance > 0 else short if variance < 0 else []).append(entry)
    over.sort(key=lambda row: row["units"], reverse=True)
    short.sort(key=lambda row: row["units"])
    return {
        "total_units": total_units,
        "total_value": total_value if any(row.get("value") is not None for row in over + short) else None,
        "biggest_over": over[:5],
        "biggest_short": short[:5],
    }
