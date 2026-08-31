"""Deterministic Level-1 inventory buying guidance.

This module never places an order and never invents commercial terms. It ranks
reviewed/configured supplier evidence only after network transfers have reduced
the forecast shortage.
"""

from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING


PRICE_STALE_DAYS = 90


def _d(value) -> Decimal:
    return Decimal(str(value or 0))


def _round_quantity(needed: Decimal, pack: Decimal, minimum: Decimal) -> Decimal:
    base = max(needed, minimum)
    if pack <= 0:
        pack = Decimal("1")
    return (base / pack).to_integral_value(rounding=ROUND_CEILING) * pack


def _priority(line: dict):
    rank = {"expedite": 0, "buy": 1, "count_first": 2, "hold": 3}
    return (rank[line["action"]], line.get("order_by_date") or date.max, line["item_name"].lower())


def build_buying_plan(*, forecast_run_id, forecast_start: date, shortages: list[dict],
                      attention: list[dict], offers: list[dict], transfers: list[dict],
                      today: date) -> dict:
    """Create advisory actions from trusted forecast/network inputs."""
    transfer_by_item: dict[object, Decimal] = {}
    for transfer in transfers:
        key = transfer["to_item_id"]
        transfer_by_item[key] = transfer_by_item.get(key, Decimal("0")) + _d(transfer["quantity"])

    offers_by_item: dict[object, list[dict]] = {}
    for offer in offers:
        offers_by_item.setdefault(offer["item_id"], []).append(offer)

    lines: list[dict] = []
    decision_item_ids = {item["item_id"] for item in attention} | {item["item_id"] for item in shortages}
    for item in attention:
        lines.append({
            "item_id": item["item_id"], "item_name": item["item_name"],
            "unit": item.get("unit"), "location_id": item.get("location_id"),
            "location_name": item.get("location_name"), "action": "count_first",
            "needed_quantity": None, "transfer_quantity": transfer_by_item.get(item["item_id"], Decimal("0")),
            "purchase_quantity": None, "supplier_id": None, "supplier_item_id": None,
            "supplier_name": None, "order_by_date": None, "expected_arrival": None,
            "projected_runout": None, "landed_cost": None, "confidence": "low",
            "price_confirmation_required": False, "alternatives": [],
            "rationale": "Verify the physical count before making a purchasing decision. The forecast does not have a trusted quantity or enough sales history.",
            "calculation": {"status": item["status"]},
        })

    for shortage in shortages:
        needed = _d(shortage["shortage_quantity"])
        item_offers = offers_by_item.get(shortage["item_id"], [])
        evaluated = []
        for offer in item_offers:
            pack = _d(offer.get("units_per_pack") or 1)
            quantity = _round_quantity(needed, pack, _d(offer.get("minimum_order_quantity")))
            unit_price = offer.get("unit_price")
            freight = _d(offer.get("freight_flat"))
            landed = quantity * _d(unit_price) + freight if unit_price is not None else None
            lead = offer.get("lead_time_days")
            arrival = today + timedelta(days=int(lead)) if lead is not None else None
            runout = shortage.get("runout_date")
            on_time = arrival is not None and (runout is None or arrival <= runout)
            observed = offer.get("price_observed_on")
            stale = observed is None or (today - observed).days > PRICE_STALE_DAYS
            eligible = bool(offer.get("active", True)) and lead is not None
            reason = "Eligible"
            if not eligible:
                reason = "Lead time or active supplier terms are missing"
            elif not on_time:
                reason = "Expected after projected runout"
            elif unit_price is None:
                reason = "Price confirmation required"
            elif stale:
                reason = "Price is older than 90 days; confirm before ordering"
            evaluated.append({**offer, "purchase_quantity": quantity, "expected_arrival": arrival,
                              "landed_cost": landed, "on_time": on_time, "eligible": eligible,
                              "price_stale": stale, "reason": reason})

        feasible = [option for option in evaluated if option["eligible"]]
        feasible.sort(key=lambda option: (
            not option["on_time"], option["landed_cost"] is None,
            option["landed_cost"] if option["landed_cost"] is not None else Decimal("Infinity"),
            not option.get("preferred", False), option["supplier_name"].lower(),
        ))
        selected = feasible[0] if feasible else None
        transfer_quantity = transfer_by_item.get(shortage["item_id"], Decimal("0"))
        if selected is None:
            action = "buy"
            rationale = "Purchase the remaining forecast shortage after transfers, but confirm a supplier, price, and lead time before ordering."
            confidence = "low"
        else:
            action = "buy" if selected["on_time"] else "expedite"
            timing = "arrives before the projected runout" if selected["on_time"] else "is expected after the projected runout"
            rationale = (
                f"After available transfers, buy {selected['purchase_quantity']} from {selected['supplier_name']}. "
                f"Configured lead time {timing}; quantity respects the supplier pack and minimum."
            )
            confidence = shortage.get("confidence") or "low"
        alternatives = [{
            "supplier_id": option["supplier_id"], "supplier_name": option["supplier_name"],
            "purchase_quantity": option["purchase_quantity"], "expected_arrival": option["expected_arrival"],
            "landed_cost": option["landed_cost"], "eligible": option["eligible"], "reason": option["reason"],
        } for option in evaluated if selected is None or option["supplier_item_id"] != selected["supplier_item_id"]]
        lines.append({
            "item_id": shortage["item_id"], "item_name": shortage["item_name"], "unit": shortage.get("unit"),
            "location_id": shortage.get("location_id"), "location_name": shortage.get("location_name"),
            "action": action, "needed_quantity": needed, "transfer_quantity": transfer_quantity,
            "purchase_quantity": selected["purchase_quantity"] if selected else shortage["suggested_order_quantity"],
            "supplier_id": selected["supplier_id"] if selected else None,
            "supplier_item_id": selected["supplier_item_id"] if selected else None,
            "supplier_name": selected["supplier_name"] if selected else None,
            "order_by_date": shortage.get("order_by_date"),
            "expected_arrival": selected["expected_arrival"] if selected else None,
            "projected_runout": shortage.get("runout_date"),
            "landed_cost": selected["landed_cost"] if selected else None,
            "confidence": confidence,
            "price_confirmation_required": selected is None or selected["unit_price"] is None or selected["price_stale"],
            "rationale": rationale, "alternatives": alternatives,
            "calculation": {"forecast_start": forecast_start.isoformat(), "remaining_need": str(needed),
                            "transfer_quantity": str(transfer_quantity)},
        })

    for transfer in transfers:
        item_id = transfer["to_item_id"]
        if item_id in decision_item_ids or _d(transfer.get("receiver_remaining_shortage")) > 0:
            continue
        decision_item_ids.add(item_id)
        quantity = transfer_by_item.get(item_id, Decimal("0"))
        lines.append({
            "item_id": item_id, "item_name": transfer["item_name"], "unit": transfer.get("unit"),
            "location_id": transfer.get("to_location_id"), "location_name": transfer.get("to_location_name"),
            "action": "hold", "needed_quantity": Decimal("0"), "transfer_quantity": quantity,
            "purchase_quantity": None, "supplier_id": None, "supplier_item_id": None, "supplier_name": None,
            "order_by_date": transfer.get("order_by_date"), "expected_arrival": None,
            "projected_runout": transfer.get("runout_date"), "landed_cost": None,
            "confidence": transfer.get("confidence") or "low", "price_confirmation_required": False,
            "rationale": f"Do not purchase now. Move {quantity} from another store; the safe transfer fully covers the forecast shortage.",
            "alternatives": [], "calculation": {"covered_by_transfer": str(quantity)},
        })

    lines.sort(key=_priority)
    costs = [line["landed_cost"] for line in lines if line["landed_cost"] is not None]
    summary = {
        "count_first": sum(line["action"] == "count_first" for line in lines),
        "hold": sum(line["action"] == "hold" for line in lines),
        "buy": sum(line["action"] == "buy" for line in lines),
        "expedite": sum(line["action"] == "expedite" for line in lines),
        "total_landed_cost": sum(costs, Decimal("0")) if costs else None,
        "unpriced_count": sum(line["action"] in ("buy", "expedite") and line["landed_cost"] is None for line in lines),
    }
    return {"forecast_run_id": forecast_run_id, "summary": summary, "lines": lines}
