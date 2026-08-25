"""Deterministic theoretical-versus-actual inventory usage."""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID


async def theoretical_usage(
    conn, *, company_id: UUID, location_id: Optional[UUID], item_ids: list[UUID],
    start: date, end: date,
) -> dict[UUID, Decimal]:
    """POS recipe usage, adjusted for an item's usable yield when configured."""
    if not item_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT component.item_id,
               SUM(sl.quantity * component.quantity_per_sale
                   / COALESCE(i.yield_pct, 1)) AS quantity
        FROM inventory_sales_lines sl
        JOIN inventory_sales_imports si ON si.id=sl.import_id
        JOIN LATERAL (
            SELECT slc.item_id, slc.quantity_per_sale, NULL::uuid AS mapping_location_id
            FROM inventory_sales_line_components slc
            WHERE slc.sales_line_id=sl.id
            UNION ALL
            SELECT ml.item_id, ml.quantity_per_sale, sm.location_id AS mapping_location_id
            FROM inventory_sales_mappings sm
            JOIN inventory_sales_mapping_lines ml ON ml.mapping_id=sm.id
            WHERE sm.id=sl.mapping_id AND sm.company_id=si.company_id
              AND NOT EXISTS (
                  SELECT 1 FROM inventory_sales_line_components slc
                  WHERE slc.sales_line_id=sl.id
              )
        ) component ON TRUE
        JOIN inventory_items i ON i.id=component.item_id
        WHERE si.company_id=$1 AND sl.status='mapped' AND si.status='committed'
          AND component.item_id=ANY($2::uuid[])
          AND si.business_date >= $4 AND si.business_date <= $5
          AND ($3::uuid IS NULL OR si.location_id IS NULL OR si.location_id=$3)
          AND ($3::uuid IS NULL OR component.mapping_location_id IS NULL OR component.mapping_location_id=$3)
          AND ($3::uuid IS NULL OR i.location_id IS NULL OR i.location_id=$3)
        GROUP BY component.item_id
        """,
        company_id, item_ids, location_id, start, end,
    )
    return {row["item_id"]: Decimal(str(row["quantity"] or 0)) for row in rows}


async def actual_usage(
    conn, *, company_id: UUID, item_ids: list[UUID], start: date, end: date,
) -> dict[UUID, Decimal]:
    """Ledger depletion. Waste is actual use, but never demand."""
    if not item_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT item_id, SUM(ABS(COALESCE(quantity_delta, 0))) AS quantity
        FROM inventory_movements
        WHERE company_id=$1 AND item_id=ANY($2::uuid[])
          AND kind IN ('sale', 'out', 'waste')
          AND created_at >= $3::date AND created_at < ($4::date + INTERVAL '1 day')
        GROUP BY item_id
        """,
        company_id, item_ids, start, end,
    )
    return {row["item_id"]: Decimal(str(row["quantity"] or 0)) for row in rows}


def usage_variance(
    theoretical: Optional[Decimal], actual: Optional[Decimal], unit_cost: Optional[Decimal],
) -> dict:
    """Return positive units for over-use, negative for under-use."""
    if theoretical is None or actual is None:
        return {"variance_units": None, "variance_value": None,
                "variance_pct": None, "direction": "unknown"}
    variance = Decimal(str(actual)) - Decimal(str(theoretical))
    cost = Decimal(str(unit_cost)) if unit_cost is not None else None
    return {
        "variance_units": variance,
        "variance_value": variance * cost if cost is not None else None,
        "variance_pct": variance / Decimal(str(theoretical)) if theoretical else None,
        "direction": "over_use" if variance > 0 else "under_use" if variance < 0 else "even",
    }
