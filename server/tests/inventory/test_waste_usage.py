from decimal import Decimal

from app.matcha.services.inventory.waste.usage import usage_variance


def test_usage_variance_over_use():
    result = usage_variance(Decimal("100"), Decimal("130"), Decimal("2"))
    assert result == {
        "variance_units": Decimal("30"), "variance_value": Decimal("60"),
        "variance_pct": Decimal("0.3"), "direction": "over_use",
    }


def test_usage_variance_even():
    result = usage_variance(Decimal("100"), Decimal("100"), Decimal("2"))
    assert result["variance_units"] == 0
    assert result["direction"] == "even"


def test_usage_variance_no_cost():
    result = usage_variance(Decimal("100"), Decimal("130"), None)
    assert result["variance_units"] == Decimal("30")
    assert result["variance_value"] is None


def test_usage_variance_unknown():
    assert usage_variance(None, Decimal("5"), Decimal("2")) == {
        "variance_units": None, "variance_value": None,
        "variance_pct": None, "direction": "unknown",
    }


def test_usage_variance_zero_theoretical():
    result = usage_variance(Decimal("0"), Decimal("5"), Decimal("2"))
    assert result["variance_units"] == Decimal("5")
    assert result["variance_pct"] is None
