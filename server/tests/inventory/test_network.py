from datetime import date
from decimal import Decimal
from uuid import UUID

from app.matcha.services.inventory.network import build_network_plan


_DOWNTOWN = UUID("00000000-0000-0000-0000-000000000001")
_UPTOWN = UUID("00000000-0000-0000-0000-000000000002")
_WESTSIDE = UUID("00000000-0000-0000-0000-000000000003")


def _line(
    *,
    item_id: str,
    location_id: UUID,
    location_name: str,
    current: str,
    target: str,
    unit: str | None = "case",
    status: str = "ready",
    on_order: str = "0",
    case_pack: str = "1",
    minimum_order: str = "0",
    runout: date | None = date(2026, 9, 2),
) -> dict:
    return {
        "item_id": UUID(item_id),
        "name": "Ceremonial Matcha",
        "normalized_name": "ceremonial matcha",
        "unit": unit,
        "location_id": location_id,
        "location_name": location_name,
        "current_quantity": Decimal(current),
        "target_quantity": Decimal(target),
        "on_order_quantity": Decimal(on_order),
        "average_daily_demand": Decimal("2"),
        "case_pack_quantity": Decimal(case_pack),
        "minimum_order_quantity": Decimal(minimum_order),
        "shelf_life_capped": False,
        "unit_cost": Decimal("4"),
        "status": status,
        "confidence": "high",
        "runout_date": runout,
        "order_by_date": date(2026, 8, 29) if runout else None,
    }


def test_network_plan_fully_covers_shortage_without_dipping_below_donor_target():
    plan = build_network_plan([
        _line(item_id="10000000-0000-0000-0000-000000000001", location_id=_DOWNTOWN, location_name="Downtown", current="2", target="10"),
        _line(item_id="10000000-0000-0000-0000-000000000002", location_id=_UPTOWN, location_name="Uptown", current="25", target="8"),
    ], forecast_start=date(2026, 8, 27), location_count=2)

    assert len(plan["transfers"]) == 1
    transfer = plan["transfers"][0]
    assert transfer["quantity"] == Decimal("8")
    assert transfer["from_post_transfer_quantity"] == Decimal("17")
    assert transfer["coverage"] == "full"
    assert plan["remaining_shortages"] == []
    assert plan["summary"]["shortages_fully_covered"] == 1
    assert plan["summary"]["inventory_value_moved"] == Decimal("32")


def test_network_plan_leaves_pack_rounded_reorder_after_partial_transfer():
    plan = build_network_plan([
        _line(item_id="20000000-0000-0000-0000-000000000001", location_id=_DOWNTOWN, location_name="Downtown", current="2", target="10", case_pack="6"),
        _line(item_id="20000000-0000-0000-0000-000000000002", location_id=_UPTOWN, location_name="Uptown", current="10", target="8"),
    ], forecast_start=date(2026, 8, 27), location_count=2)

    assert plan["transfers"][0]["quantity"] == Decimal("2")
    assert plan["transfers"][0]["coverage"] == "partial"
    assert plan["remaining_shortages"][0]["shortage_quantity"] == Decimal("6")
    assert plan["remaining_shortages"][0]["suggested_order_quantity"] == Decimal("6")


def test_network_plan_respects_incoming_orders_and_unit_boundaries():
    plan = build_network_plan([
        _line(item_id="30000000-0000-0000-0000-000000000001", location_id=_DOWNTOWN, location_name="Downtown", current="2", target="10", on_order="8"),
        _line(item_id="30000000-0000-0000-0000-000000000002", location_id=_UPTOWN, location_name="Uptown", current="25", target="8"),
        _line(item_id="30000000-0000-0000-0000-000000000003", location_id=_WESTSIDE, location_name="Westside", current="0", target="6", unit="bag"),
    ], forecast_start=date(2026, 8, 27), location_count=3)

    assert plan["transfers"] == []
    assert len(plan["remaining_shortages"]) == 1
    assert plan["remaining_shortages"][0]["location_name"] == "Westside"


def test_network_plan_surfaces_untrusted_counts_instead_of_using_them_as_supply():
    sparse = _line(
        item_id="40000000-0000-0000-0000-000000000001",
        location_id=_UPTOWN,
        location_name="Uptown",
        current="40",
        target="0",
        status="insufficient_history",
        runout=None,
    )
    receiver = _line(
        item_id="40000000-0000-0000-0000-000000000002",
        location_id=_DOWNTOWN,
        location_name="Downtown",
        current="2",
        target="10",
    )
    plan = build_network_plan([sparse, receiver], forecast_start=date(2026, 8, 27), location_count=2)

    assert plan["transfers"] == []
    assert plan["remaining_shortages"][0]["shortage_quantity"] == Decimal("8")
    assert plan["attention"] == [{
        "item_id": sparse["item_id"],
        "item_name": "Ceremonial Matcha",
        "location_id": _UPTOWN,
        "location_name": "Uptown",
        "status": "insufficient_history",
    }]
