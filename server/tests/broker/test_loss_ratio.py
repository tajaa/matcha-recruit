"""Unit tests for loss-ratio merge math (pure, no DB).

Loss ratio = projected ultimate ÷ paid premium, per (line, policy year), with a
per-year account rollup. Threshold: < 60% favorable, >= 60% adverse, no premium = na.
"""
from app.matcha.services import loss_development as ld


def _dev():
    return {
        "lines": [
            {"line": "wc", "label": "Workers' Comp", "periods": [
                {"period_label": "PY2023", "period_start": "2023-01-01", "ultimate": 84000.0},
                {"period_label": "PY2024", "period_start": "2024-01-01", "ultimate": 96000.0},
            ]},
            {"line": "gl", "label": "General Liability", "periods": [
                {"period_label": "PY2024", "period_start": "2024-01-01", "ultimate": 30000.0},
            ]},
        ],
    }


def test_per_line_ratios_and_statuses():
    prem = {("wc", "PY2023"): 150000.0, ("wc", "PY2024"): 140000.0, ("gl", "PY2024"): 80000.0}
    m = ld._merge_loss_ratio(_dev(), prem)
    rows = {(r["line"], r["period_label"]): r for r in m["rows"]}
    assert rows[("wc", "PY2023")]["loss_ratio"] == 56.0 and rows[("wc", "PY2023")]["status"] == "favorable"
    assert rows[("wc", "PY2024")]["loss_ratio"] == 68.6 and rows[("wc", "PY2024")]["status"] == "adverse"
    assert rows[("gl", "PY2024")]["loss_ratio"] == 37.5 and rows[("gl", "PY2024")]["status"] == "favorable"


def test_year_rollup_sums_across_lines():
    prem = {("wc", "PY2024"): 140000.0, ("gl", "PY2024"): 80000.0}
    m = ld._merge_loss_ratio(_dev(), prem)
    years = {y["period_label"]: y for y in m["years"]}
    # PY2024: (96000 + 30000) / (140000 + 80000) = 57.3%
    assert years["PY2024"]["total_ultimate"] == 126000.0
    assert years["PY2024"]["total_premium"] == 220000.0
    assert years["PY2024"]["loss_ratio"] == 57.3 and years["PY2024"]["status"] == "favorable"
    # PY2023 has no premium entered → na rollup
    assert years["PY2023"]["total_premium"] is None
    assert years["PY2023"]["loss_ratio"] is None and years["PY2023"]["status"] == "na"


def test_missing_premium_is_na_not_zero():
    m = ld._merge_loss_ratio(_dev(), {})  # no premiums at all
    assert all(r["loss_ratio"] is None and r["status"] == "na" for r in m["rows"])
    assert all(r["paid_premium"] is None for r in m["rows"])


def test_threshold_boundary_and_zero_premium():
    assert ld._ratio_status(59.9) == "favorable"
    assert ld._ratio_status(60.0) == "adverse"   # 60% is the target ceiling → not favorable
    assert ld._ratio_status(None) == "na"
    assert ld._ratio(50000.0, 0) is None         # zero premium never divides
    assert ld._ratio(50000.0, None) is None
    assert ld._ratio(60000.0, 100000.0) == 60.0
    assert ld.LOSS_RATIO_TARGET == 60
