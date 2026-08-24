"""Dollarized waste rollups — grouped by reason, category, or item. All
money math happens here in SQL/Decimal; callers (routes, the waste
analyst agent) never compute a total themselves — the deterministic-math
invariant this whole feature is built on."""

from datetime import date
from decimal import Decimal
from typing import Literal, Optional
from uuid import UUID

from app.matcha.services.inventory.waste.reasons import UNEXPLAINED_REASONS, label

GroupBy = Literal["reason", "category", "item"]

_GROUP_COLUMNS: dict[str, str] = {
    "reason": "COALESCE(m.waste_reason, 'unknown')",
    "category": "COALESCE(i.category, 'uncategorized')",
    "item": "i.id::text",
}


async def waste_rollup(
    conn, *, company_id: UUID, location_id: Optional[UUID],
    start: date, end: date, group_by: GroupBy = "reason",
) -> dict:
    """Totals + breakdown of kind='waste' movements in [start, end]
    (inclusive on both ends, by created_at date), dollarized via
    inventory_items.unit_cost where it's set. An item with no unit_cost
    contributes its units to the total but not to total_value — the
    caller is told how many such rows exist via `uncosted_count` rather
    than the dollar figure silently under-reporting."""
    if group_by not in _GROUP_COLUMNS:
        raise ValueError(f"unknown group_by: {group_by!r}")
    group_col = _GROUP_COLUMNS[group_by]
    rows = await conn.fetch(
        f"""
        SELECT {group_col} AS key,
               MAX(i.name) AS item_name,
               SUM(ABS(COALESCE(m.quantity_delta, 0))) AS units,
               SUM(ABS(COALESCE(m.quantity_delta, 0)) * i.unit_cost)
                 FILTER (WHERE i.unit_cost IS NOT NULL) AS value,
               COUNT(*) FILTER (WHERE i.unit_cost IS NULL) AS uncosted_count
        FROM inventory_movements m
        JOIN inventory_items i ON i.id = m.item_id
        WHERE m.company_id = $1 AND m.kind = 'waste'
          AND m.created_at::date BETWEEN $2 AND $3
          AND ($4::uuid IS NULL OR i.location_id IS NULL OR i.location_id = $4)
        GROUP BY {group_col}
        ORDER BY value DESC NULLS LAST, units DESC
        """,
        company_id, start, end, location_id,
    )

    total_units = sum((row["units"] or Decimal("0")) for row in rows)
    any_costed = any(row["value"] is not None for row in rows)
    total_value = sum((row["value"] or Decimal("0")) for row in rows) if any_costed else None
    uncosted_count = sum(row["uncosted_count"] or 0 for row in rows)

    unexplained_value = None
    if group_by == "reason" and any_costed:
        unexplained_value = sum(
            (row["value"] or Decimal("0")) for row in rows if row["key"] in UNEXPLAINED_REASONS
        )

    groups = []
    for row in rows:
        value = row["value"]
        groups.append({
            "key": row["key"],
            "label": label(row["key"]) if group_by == "reason" else (
                row["item_name"] if group_by == "item" else row["key"]
            ),
            "units": row["units"] or Decimal("0"),
            "value": value,
            "pct": (value / total_value) if (value is not None and total_value) else None,
            "uncosted_count": row["uncosted_count"] or 0,
        })

    revenue = await waste_revenue(conn, company_id=company_id, location_id=location_id, start=start, end=end)
    waste_pct_of_revenue = (total_value / revenue) if (total_value is not None and revenue) else None

    return {
        "start": start, "end": end, "group_by": group_by,
        "total_units": total_units, "total_value": total_value,
        "unexplained_value": unexplained_value, "uncosted_count": uncosted_count,
        "revenue": revenue, "waste_pct_of_revenue": waste_pct_of_revenue,
        "groups": groups,
    }


async def waste_revenue(
    conn, *, company_id: UUID, location_id: Optional[UUID], start: date, end: date,
) -> Optional[Decimal]:
    """SUM(gross_sales) over committed sales imports in the window — the
    revenue denominator for waste_pct_of_revenue. None when sales_intake
    has no committed imports in range (the caller then reports the
    absolute waste dollar figure and omits the percentage, rather than
    inventing one against zero revenue)."""
    value = await conn.fetchval(
        """
        SELECT SUM(sl.gross_sales)
        FROM inventory_sales_lines sl
        JOIN inventory_sales_imports si ON si.id = sl.import_id
        WHERE si.company_id = $1 AND si.status = 'committed'
          AND si.business_date BETWEEN $2 AND $3
          AND ($4::uuid IS NULL OR si.location_id IS NULL OR si.location_id = $4)
        """,
        company_id, start, end, location_id,
    )
    return Decimal(str(value)) if value is not None else None
