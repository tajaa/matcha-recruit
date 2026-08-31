from datetime import date
from decimal import Decimal
from uuid import UUID

from app.matcha.models.inventory import BuyingPlanOut
from app.matcha.services.inventory.buying import build_buying_plan


ITEM = UUID("10000000-0000-0000-0000-000000000001")
LOCATION = UUID("20000000-0000-0000-0000-000000000001")
SUPPLIER_A = UUID("30000000-0000-0000-0000-000000000001")
SUPPLIER_B = UUID("30000000-0000-0000-0000-000000000002")


def shortage(**overrides):
    value = {
        "item_id": ITEM, "item_name": "Oat milk", "unit": "each", "location_id": LOCATION,
        "location_name": "Downtown", "shortage_quantity": Decimal("10"),
        "suggested_order_quantity": Decimal("10"), "runout_date": date(2026, 9, 10),
        "order_by_date": date(2026, 9, 5), "confidence": "high",
    }
    value.update(overrides)
    return value


def offer(supplier_id=SUPPLIER_A, **overrides):
    value = {
        "supplier_item_id": supplier_id, "item_id": ITEM, "supplier_id": supplier_id,
        "supplier_name": "Supplier A" if supplier_id == SUPPLIER_A else "Supplier B",
        "units_per_pack": Decimal("6"), "minimum_order_quantity": Decimal("0"),
        "unit_price": Decimal("5"), "freight_flat": Decimal("4"), "lead_time_days": 3,
        "price_observed_on": date(2026, 8, 20), "preferred": False, "active": True,
    }
    value.update(overrides)
    return value


def plan(*, shortages=None, attention=None, offers=None, transfers=None):
    return build_buying_plan(
        forecast_run_id=UUID("40000000-0000-0000-0000-000000000001"),
        forecast_start=date(2026, 8, 30), today=date(2026, 9, 1),
        shortages=shortages or [], attention=attention or [], offers=offers or [], transfers=transfers or [],
    )


def test_supplier_pack_and_minimum_round_the_remaining_shortage():
    result = plan(shortages=[shortage()], offers=[offer(minimum_order_quantity=Decimal("13"))])
    line = result["lines"][0]
    assert line["purchase_quantity"] == Decimal("18")
    assert line["landed_cost"] == Decimal("94")
    assert line["action"] == "buy"


def test_cheaper_late_supplier_loses_to_on_time_supplier():
    late = offer(SUPPLIER_A, unit_price=Decimal("1"), lead_time_days=15)
    on_time = offer(SUPPLIER_B, unit_price=Decimal("6"), lead_time_days=3)
    result = plan(shortages=[shortage()], offers=[late, on_time])
    assert result["lines"][0]["supplier_id"] == SUPPLIER_B
    assert result["lines"][0]["action"] == "buy"
    assert result["lines"][0]["alternatives"][0]["reason"] == "Expected after projected runout"


def test_only_late_supplier_becomes_expedite_review():
    result = plan(shortages=[shortage()], offers=[offer(lead_time_days=15)])
    assert result["lines"][0]["action"] == "expedite"


def test_missing_terms_never_invents_supplier_price_or_arrival():
    result = plan(shortages=[shortage()], offers=[])
    line = result["lines"][0]
    assert line["action"] == "buy"
    assert line["supplier_id"] is None
    assert line["landed_cost"] is None
    assert line["expected_arrival"] is None
    assert line["price_confirmation_required"] is True


def test_stale_price_requires_confirmation():
    result = plan(shortages=[shortage()], offers=[offer(price_observed_on=date(2026, 1, 1))])
    assert result["lines"][0]["price_confirmation_required"] is True


def test_attention_item_is_count_first_and_never_has_purchase_quantity():
    result = plan(attention=[{"item_id": ITEM, "item_name": "Oat milk", "location_id": LOCATION,
                                   "location_name": "Downtown", "status": "count_required"}])
    assert result["lines"][0]["action"] == "count_first"
    assert result["lines"][0]["purchase_quantity"] is None


def test_transfer_quantity_is_explained_but_shortage_is_not_double_subtracted():
    result = plan(shortages=[shortage(shortage_quantity=Decimal("4"), suggested_order_quantity=Decimal("6"))],
                  offers=[offer()], transfers=[{"to_item_id": ITEM, "quantity": Decimal("6")}])
    assert result["lines"][0]["needed_quantity"] == Decimal("4")
    assert result["lines"][0]["transfer_quantity"] == Decimal("6")
    assert result["lines"][0]["purchase_quantity"] == Decimal("6")


def test_full_transfer_becomes_hold_instead_of_purchase():
    result = plan(transfers=[{
        "to_item_id": ITEM, "to_location_id": LOCATION, "to_location_name": "Downtown",
        "item_name": "Oat milk", "unit": "each", "quantity": Decimal("10"),
        "receiver_remaining_shortage": Decimal("0"), "confidence": "high",
        "runout_date": date(2026, 9, 10), "order_by_date": date(2026, 9, 5),
    }])
    assert result["lines"][0]["action"] == "hold"
    assert result["lines"][0]["purchase_quantity"] is None
    assert result["summary"]["hold"] == 1


def test_response_contract_serializes_decimals_as_numbers():
    result = plan(shortages=[shortage()], offers=[offer()])
    result.update({"location_id": None, "input_fingerprint": "abc"})
    payload = BuyingPlanOut.model_validate(result).model_dump(mode="json")
    assert payload["lines"][0]["purchase_quantity"] == 12.0
    assert isinstance(payload["lines"][0]["landed_cost"], float)
