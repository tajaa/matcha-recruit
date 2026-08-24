"""Read-only, FEFO-aware expiry risk ranking for advisory inventory lots."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.matcha.services.inventory import movements, reorder
from app.matcha.services.inventory.waste import lots


async def at_risk_stock(conn, *, company_id: UUID, location_id: Optional[UUID], within_days: int = 365) -> dict:
    open_lots = await lots.expiring_lots(conn, company_id=company_id, location_id=location_id, within_days=within_days)
    by_item: dict[UUID, list[dict]] = {}
    for lot in open_lots:
        by_item.setdefault(lot["item_id"], []).append(lot)
    history = await movements.recent_movements_for_items(conn, company_id=company_id, item_ids=list(by_item))
    lines: list[dict] = []
    for item_id, item_lots in by_item.items():
        suggestion = reorder.suggest_order(history.get(item_id, []), datetime.now(timezone.utc))
        demand = Decimal(str(suggestion["daily_rate"])) if suggestion and suggestion["daily_rate"] is not None else Decimal("0")
        scored = lots.spoilage_risk_for_item_lots(lots=item_lots, average_daily_demand=demand)
        at_risk_quantity = sum((row["at_risk_quantity"] for row in scored), Decimal("0"))
        costed = [row for row in scored if row["unit_cost"] is not None]
        value_at_risk = sum((row["at_risk_quantity"] * Decimal(str(row["unit_cost"])) for row in costed), Decimal("0")) if costed else None
        first = scored[0]
        lines.append({
            "item_id": item_id, "name": first["name"], "unit": first["unit"],
            "item_current_quantity": first["item_current_quantity"],
            "open_lot_quantity": sum((Decimal(str(row["quantity_remaining"])) for row in item_lots), Decimal("0")),
            "soonest_days_to_expiry": min(row["days_to_expiry"] for row in item_lots if row["days_to_expiry"] is not None),
            "average_daily_demand": demand, "demand_basis": "ledger" if suggestion and suggestion["daily_rate"] is not None else "insufficient_history",
            "confidence": suggestion["confidence"] if suggestion else "none", "n_samples": suggestion["n_samples"] if suggestion else 0,
            "quantity_at_risk": at_risk_quantity, "value_at_risk": value_at_risk,
            "uncosted_count": sum(1 for row in scored if row["unit_cost"] is None and row["at_risk_quantity"] > 0),
            "lot_drift": (first["item_current_quantity"] - sum((Decimal(str(row["quantity_remaining"])) for row in item_lots), Decimal("0"))) if first["item_current_quantity"] is not None else None,
            "lots": scored,
        })
    lines.sort(key=lambda line: (line["value_at_risk"] is None, -(line["value_at_risk"] or Decimal("0")), -line["quantity_at_risk"], line["soonest_days_to_expiry"], line["name"].lower()))
    return {"lines": lines}
