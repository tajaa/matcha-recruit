"""Pure tests for the loss-run parser's _coerce (Gemini call is best-effort, not tested)."""

from app.matcha.services import loss_run_parser as lr


def test_coerce_clamps_and_types():
    out = lr._coerce({
        "recordable_cases": "5", "dart_cases": -2, "current_emr": 1.25,
        "avg_days_to_rtw": "30", "carrier": "Travelers", "annual_premium": None,
        "period_label": "2024 policy year",
    })
    assert out["recordable_cases"] == 5          # str → int
    assert out["dart_cases"] == 0                 # negative clamped
    assert out["current_emr"] == 1.25
    assert out["avg_days_to_rtw"] == 30.0
    assert out["carrier"] == "Travelers"
    assert out["period_label"] == "2024 policy year"


def test_coerce_rejects_out_of_range_emr():
    assert lr._coerce({"current_emr": 50})["current_emr"] is None     # > 10
    assert lr._coerce({"current_emr": "abc"})["current_emr"] is None  # non-numeric


def test_coerce_defaults_missing():
    out = lr._coerce({})
    assert out["recordable_cases"] == 0
    assert out["carrier"] is None
    assert out["current_emr"] is None
