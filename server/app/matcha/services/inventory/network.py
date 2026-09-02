"""Cross-location inventory balancing recommendations.

The engine is deterministic and read-only. It only proposes a transfer when
both locations have usable sales history and the donor remains above its own
lead-time-plus-safety-stock target after the move.
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_CEILING
from typing import Iterable, Mapping
from uuid import UUID

from app.matcha.services.inventory import forecast_store


_CONFIDENCE_RANK = {"low": 0, "medium": 1, "high": 2}


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _group_key(line: Mapping) -> tuple[str, str]:
    return (
        str(line.get("normalized_name") or "").strip().lower(),
        str(line.get("unit") or "").strip().lower(),
    )


def _lowest_confidence(left: str, right: str) -> str:
    return min((left, right), key=lambda value: _CONFIDENCE_RANK.get(value, -1))


def _rounded_order_quantity(raw_quantity: Decimal, line: Mapping) -> Decimal:
    if raw_quantity <= 0:
        return Decimal("0")
    if line.get("shelf_life_capped"):
        return raw_quantity
    pack = max(_decimal(line.get("case_pack_quantity")), Decimal("1"))
    minimum = max(_decimal(line.get("minimum_order_quantity")), Decimal("0"))
    rounded = (raw_quantity / pack).to_integral_value(rounding=ROUND_CEILING) * pack
    if minimum > rounded:
        rounded = (minimum / pack).to_integral_value(rounding=ROUND_CEILING) * pack
    return rounded


def _priority(line: Mapping) -> tuple:
    return (
        line.get("order_by_date") is None,
        line.get("order_by_date") or date.max,
        line.get("runout_date") is None,
        line.get("runout_date") or date.max,
        str(line.get("name") or "").lower(),
        str(line.get("location_name") or "").lower(),
    )


def build_network_plan(
    lines: Iterable[Mapping],
    *,
    forecast_start: date,
    location_count: int,
) -> dict:
    """Allocate safe donor surplus to forecast shortages across locations."""
    materialized = [dict(line) for line in lines if line.get("location_id") is not None]
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    attention = []

    for line in materialized:
        if line.get("status") in {"count_required", "insufficient_history"}:
            attention.append({
                "item_id": line["item_id"],
                "item_name": line["name"],
                "location_id": line["location_id"],
                "location_name": line["location_name"],
                "status": line["status"],
            })
        key = _group_key(line)
        if key[0]:
            grouped[key].append(line)

    network_groups = [
        group for group in grouped.values()
        if len({line["location_id"] for line in group}) >= 2
    ]
    transfers: list[dict] = []
    remaining_shortages: list[dict] = []
    fully_covered = 0

    for group in grouped.values():
        receivers = []
        donors = []
        for line in group:
            if line.get("status") != "ready" or line.get("current_quantity") is None:
                continue
            current = _decimal(line["current_quantity"])
            target = _decimal(line.get("target_quantity"))
            on_order = _decimal(line.get("on_order_quantity"))
            shortage = max(target - current - on_order, Decimal("0"))
            surplus = max(current - target, Decimal("0"))
            if shortage > 0:
                receivers.append({**line, "initial_shortage": shortage, "remaining_shortage": shortage, "received": Decimal("0")})
            if surplus > 0:
                donors.append({**line, "remaining_surplus": surplus, "sent": Decimal("0")})

        receivers.sort(key=_priority)
        donors.sort(key=lambda line: (-line["remaining_surplus"], str(line.get("location_name") or "").lower()))

        for receiver in receivers:
            for donor in donors:
                if receiver["remaining_shortage"] <= 0:
                    break
                if donor["remaining_surplus"] <= 0 or donor["location_id"] == receiver["location_id"]:
                    continue
                quantity = min(receiver["remaining_shortage"], donor["remaining_surplus"])
                receiver["remaining_shortage"] -= quantity
                receiver["received"] += quantity
                donor["remaining_surplus"] -= quantity
                donor["sent"] += quantity

                unit_cost = receiver.get("unit_cost") if receiver.get("unit_cost") is not None else donor.get("unit_cost")
                inventory_value = quantity * _decimal(unit_cost) if unit_cost is not None else None
                average_demand = _decimal(receiver.get("average_daily_demand"))
                cover_days = quantity / average_demand if average_demand > 0 else None
                runout = receiver.get("runout_date")
                urgency = (
                    f" is projected to run out on {runout.isoformat()}"
                    if isinstance(runout, date)
                    else " is below its replenishment target"
                )
                rationale = (
                    f"{receiver['location_name']}{urgency}; {donor['location_name']} "
                    f"stays at or above its own target after the move."
                )
                transfers.append({
                    "item_name": receiver["name"],
                    "unit": receiver.get("unit"),
                    "quantity": quantity,
                    "from_item_id": donor["item_id"],
                    "from_location_id": donor["location_id"],
                    "from_location_name": donor["location_name"],
                    "from_current_quantity": _decimal(donor["current_quantity"]),
                    "from_target_quantity": _decimal(donor.get("target_quantity")),
                    "from_post_transfer_quantity": _decimal(donor["current_quantity"]) - donor["sent"],
                    "to_item_id": receiver["item_id"],
                    "to_location_id": receiver["location_id"],
                    "to_location_name": receiver["location_name"],
                    "to_current_quantity": _decimal(receiver["current_quantity"]),
                    "to_target_quantity": _decimal(receiver.get("target_quantity")),
                    "to_post_transfer_quantity": _decimal(receiver["current_quantity"]) + receiver["received"],
                    "receiver_remaining_shortage": receiver["remaining_shortage"],
                    "runout_date": receiver.get("runout_date"),
                    "order_by_date": receiver.get("order_by_date"),
                    "days_of_cover_added": cover_days,
                    "inventory_value": inventory_value,
                    "coverage": "full" if receiver["remaining_shortage"] <= 0 else "partial",
                    "confidence": _lowest_confidence(
                        str(donor.get("confidence") or "low"),
                        str(receiver.get("confidence") or "low"),
                    ),
                    "rationale": rationale,
                })

            if receiver["remaining_shortage"] <= 0:
                fully_covered += 1
            else:
                remaining_shortages.append({
                    "item_id": receiver["item_id"],
                    "item_name": receiver["name"],
                    "unit": receiver.get("unit"),
                    "location_id": receiver["location_id"],
                    "location_name": receiver["location_name"],
                    "shortage_quantity": receiver["remaining_shortage"],
                    "suggested_order_quantity": _rounded_order_quantity(receiver["remaining_shortage"], receiver),
                    "runout_date": receiver.get("runout_date"),
                    "order_by_date": receiver.get("order_by_date"),
                    "confidence": receiver.get("confidence") or "low",
                })

    transfers.sort(key=lambda line: (
        line["order_by_date"] is None,
        line["order_by_date"] or date.max,
        line["runout_date"] is None,
        line["runout_date"] or date.max,
        line["item_name"].lower(),
        line["from_location_name"].lower(),
    ))
    remaining_shortages.sort(key=_priority)
    attention.sort(key=lambda line: (line["status"], line["item_name"].lower(), line["location_name"].lower()))
    valued_transfers = [line["inventory_value"] for line in transfers if line["inventory_value"] is not None]

    return {
        "forecast_start": forecast_start,
        "summary": {
            "location_count": location_count,
            "matched_item_groups": len(network_groups),
            "transfer_count": len(transfers),
            "shortages_fully_covered": fully_covered,
            "remaining_reorder_count": len(remaining_shortages),
            "attention_count": len(attention),
            "inventory_value_moved": sum(valued_transfers, Decimal("0")) if valued_transfers else None,
        },
        "transfers": transfers,
        "remaining_shortages": remaining_shortages,
        "attention": attention,
    }


async def build_network_preview(conn, *, company_id: UUID, run_id: UUID) -> dict | None:
    """Rebuild each location with the saved run's date and scenario overrides."""
    run = await conn.fetchrow(
        """SELECT forecast_start, location_id
           FROM inventory_forecast_runs
           WHERE id=$1 AND company_id=$2""",
        run_id,
        company_id,
    )
    if run is None or run["location_id"] is not None:
        return None
    override_rows = await conn.fetch(
        """SELECT week_start, demand_multiplier, reason, source, confidence
           FROM inventory_forecast_overrides
           WHERE run_id=$1 AND company_id=$2
           ORDER BY week_start, id""",
        run_id,
        company_id,
    )
    overrides = [dict(row) for row in override_rows]
    locations = await conn.fetch(
        """SELECT id, COALESCE(name, city, 'Unnamed') AS name
           FROM business_locations
           WHERE company_id=$1 AND is_active IS NOT FALSE AND is_company_wide=FALSE
           ORDER BY name, id""",
        company_id,
    )
    metadata_rows = await conn.fetch(
        """SELECT i.id, i.normalized_name,
                  COALESCE(bl.name, bl.city, 'Unnamed') AS location_name
           FROM inventory_items i
           JOIN business_locations bl ON bl.id=i.location_id
           WHERE i.company_id=$1 AND i.archived_at IS NULL
             AND bl.company_id=$1 AND bl.is_active IS NOT FALSE
             AND bl.is_company_wide=FALSE""",
        company_id,
    )
    metadata = {row["id"]: dict(row) for row in metadata_rows}
    lines = []
    for location in locations:
        preview = await forecast_store.build_preview(
            conn,
            company_id=company_id,
            location_id=location["id"],
            forecast_start=run["forecast_start"],
            overrides=overrides,
        )
        for raw in preview["lines"]:
            if raw.get("location_id") != location["id"]:
                continue
            item_metadata = metadata.get(raw["item_id"])
            if item_metadata is None:
                continue
            lines.append({
                **raw,
                "normalized_name": item_metadata["normalized_name"],
                "location_name": item_metadata["location_name"],
            })
    return build_network_plan(
        lines,
        forecast_start=run["forecast_start"],
        location_count=len(locations),
    )
