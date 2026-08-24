from decimal import Decimal

from app.matcha.services.inventory.waste.lots import spoilage_risk_score


def test_spoilage_risk_is_deterministic_and_bounded():
    result = spoilage_risk_score(
        quantity_remaining=Decimal("10"), days_to_expiry=3, average_daily_demand=Decimal("2"),
    )
    assert result == {
        "score": Decimal("0.4"), "days_of_cover": Decimal("5"),
        "at_risk_quantity": Decimal("4"), "basis": "expiry_vs_demand",
    }


def test_spoilage_risk_without_expiry_is_not_a_spoilage_claim():
    result = spoilage_risk_score(
        quantity_remaining=Decimal("10"), days_to_expiry=None, average_daily_demand=Decimal("2"),
    )
    assert result["score"] == 0
    assert result["basis"] == "no_expiry"
