from decimal import Decimal

from app.matcha.services.inventory.waste.par import (
    par_drift_pct, recommend_par, should_auto_apply,
)


def test_par_equals_lead_plus_safety_without_shelf_life():
    result = recommend_par(lead_demand=Decimal("20"), safety_demand=Decimal("10"), daily_demand=[], lead_time_days=2)
    assert result["recommended_par"] == Decimal("30")
    assert result["par_basis"] == "demand" and result["shelf_cap"] is None


def test_shelf_life_caps_par_and_can_signal_structural_deficit():
    result = recommend_par(lead_demand=Decimal("20"), safety_demand=Decimal("10"), daily_demand=[Decimal("2")] * 8, lead_time_days=2, shelf_life_days=4)
    assert result["recommended_par"] == Decimal("8")
    assert result["par_basis"] == "structural_deficit"
    assert result["structural_deficit"] is True


def test_shelf_window_past_horizon_falls_back():
    result = recommend_par(lead_demand=Decimal("20"), safety_demand=Decimal("10"), daily_demand=[Decimal("2")] * 3, lead_time_days=10, shelf_life_days=2)
    assert result["shelf_cap"] == Decimal("4")


def test_unready_status_yields_no_par():
    assert recommend_par(lead_demand=Decimal("2"), safety_demand=Decimal("1"), daily_demand=[], lead_time_days=1, status="no_demand")["recommended_par"] is None


def test_drift_pct_and_auto_apply_guards():
    assert par_drift_pct(Decimal("10"), Decimal("13")) == Decimal("0.3")
    assert par_drift_pct(Decimal("0"), Decimal("13")) is None
    assert should_auto_apply(current_par=Decimal("10"), recommended_par=Decimal("13"), par_source="manual", status="ready", confidence="medium", max_drift_pct=Decimal("0.5")) == (False, "manual_par_pinned")
    assert should_auto_apply(current_par=Decimal("10"), recommended_par=Decimal("40"), par_source="auto", status="ready", confidence="medium", max_drift_pct=Decimal("0.5")) == (False, "drift_exceeds_bound")
    assert should_auto_apply(current_par=None, recommended_par=Decimal("13"), par_source="auto", status="ready", confidence="medium", max_drift_pct=Decimal("0.5")) == (True, "first_par")
    assert should_auto_apply(current_par=Decimal("10"), recommended_par=Decimal("13"), par_source="auto", status="ready", confidence="medium", max_drift_pct=Decimal("0.5")) == (True, "within_bound")
