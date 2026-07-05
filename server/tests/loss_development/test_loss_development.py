"""Pure tests for the chain-ladder loss-development engine."""

from datetime import date

from app.matcha.services import loss_development as ld


def _snap(label, val, incurred, line="wc", start=None):
    return {"line": line, "policy_period_label": label, "policy_period_start": start,
            "valuation_date": val, "paid": incurred, "reserved": 0,
            "claim_count": 0, "open_count": 0}


# A clean triangle: 2021 seen at 12/24/36mo, 2022 at 12/24, 2023 at 12.
TRIANGLE = [
    _snap("2021", date(2021, 12, 31), 100_000),
    _snap("2021", date(2022, 12, 31), 150_000),
    _snap("2021", date(2023, 12, 31), 165_000),
    _snap("2022", date(2022, 12, 31), 200_000),
    _snap("2022", date(2023, 12, 31), 260_000),
    _snap("2023", date(2023, 12, 31), 300_000),
]


def _wc(tri):
    return {l["line"]: l for l in tri["lines"]}["wc"]


def _period(line, label):
    return {p["period_label"]: p for p in line["periods"]}[label]


# --- helpers ---------------------------------------------------------------

def test_period_start_derivation():
    assert ld._period_start("2021", None) == date(2021, 1, 1)
    assert ld._period_start("2021-2022", None) == date(2021, 1, 1)
    assert ld._period_start("PY2020", None) == date(2020, 1, 1)
    assert ld._period_start("no year", None) is None
    assert ld._period_start("2021", date(2021, 7, 1)) == date(2021, 7, 1)  # explicit wins
    # a stray year in a claim number must not beat the explicit policy-year token
    assert ld._period_start("Claim 2019-00042 PY2021", None) == date(2021, 1, 1)


def test_maturity_bucketing():
    assert ld._maturity(11) == 12
    assert ld._maturity(13) == 12
    assert ld._maturity(23) == 24
    assert ld._maturity(35) == 36
    assert ld._maturity(0) == 12
    assert ld._maturity(None) is None


# --- chain ladder ----------------------------------------------------------

def test_link_ratios_simple_average():
    line = _wc(ld.build_triangle(TRIANGLE))
    fac = {f["from_maturity"]: f for f in line["factors"]}
    # 12→24: avg(150/100, 260/200) = avg(1.5, 1.3) = 1.4 over 2 obs
    assert fac[12]["factor"] == 1.4 and fac[12]["n"] == 2
    # 24→36: only 2021 (165/150 = 1.1) over 1 obs
    assert fac[24]["factor"] == 1.1 and fac[24]["n"] == 1


def test_ultimate_projection_and_adverse_development():
    line = _wc(ld.build_triangle(TRIANGLE))
    # 2021 is fully mature (36mo, max) → cdf 1.0, no adverse
    p21 = _period(line, "2021")
    assert p21["ultimate"] == 165_000.0 and p21["adverse_development"] == 0.0
    # 2022 latest 24mo 260k × cdf(24)=1.1 → 286k
    p22 = _period(line, "2022")
    assert p22["ultimate"] == 286_000.0 and p22["adverse_development"] == 26_000.0
    # 2023 latest 12mo 300k × cdf(12)=1.4×1.1=1.54 → 462k
    p23 = _period(line, "2023")
    assert p23["cdf"] == 1.54 and p23["ultimate"] == 462_000.0
    assert p23["adverse_development"] == 162_000.0


def test_summary_totals():
    s = _wc(ld.build_triangle(TRIANGLE))["summary"]
    assert s["total_latest_incurred"] == 725_000.0
    assert s["total_ultimate"] == 913_000.0
    assert s["total_adverse_development"] == 188_000.0
    assert s["adverse_pct"] == 25.9
    assert s["periods"] == 3 and s["max_maturity"] == 36


def test_incurred_is_paid_plus_reserved():
    snaps = [{"line": "wc", "policy_period_label": "2022", "policy_period_start": None,
              "valuation_date": date(2022, 12, 31), "paid": 80_000, "reserved": 20_000,
              "claim_count": 5, "open_count": 2}]
    p = _period(_wc(ld.build_triangle(snaps)), "2022")
    assert p["points"][0]["incurred"] == 100_000.0


# --- degenerate cases ------------------------------------------------------

def test_single_valuation_no_projection():
    snaps = [_snap("2023", date(2023, 12, 31), 300_000)]
    line = _wc(ld.build_triangle(snaps))
    assert line["factors"] == []
    p = _period(line, "2023")
    assert p["ultimate"] == 300_000.0 and p["adverse_development"] == 0.0
    assert line["summary"]["valuations"] == 1


def test_maturity_gap_excluded_from_link_ratios():
    # 2021 valued at 12mo and 36mo but NOT 24mo (a skipped valuation); 2022 at 12/24mo.
    snaps = [
        _snap("2021", date(2021, 12, 31), 100_000),
        _snap("2021", date(2023, 12, 31), 160_000),  # 36mo — its 24mo valuation missing
        _snap("2022", date(2022, 12, 31), 200_000),
        _snap("2022", date(2023, 12, 31), 240_000),  # 24mo
    ]
    line = _wc(ld.build_triangle(snaps))
    fac = {f["from_maturity"]: f for f in line["factors"]}
    # the 12→36 span from 2021 must NOT pollute the 12→24 bucket — only 2022's
    # consecutive 12→24 (240/200=1.2) counts (pre-fix this averaged in 1.6 → 1.4).
    assert fac[12]["factor"] == 1.2 and fac[12]["n"] == 1
    # the gap is surfaced, not silent
    assert _period(line, "2021")["maturity_gap"] is True
    assert line["summary"]["has_maturity_gap"] is True
    assert _period(line, "2022")["maturity_gap"] is False


def test_empty():
    tri = ld.build_triangle([])
    assert tri["has_data"] is False and tri["lines"] == []


def test_multi_line_grouping():
    snaps = TRIANGLE + [_snap("2022", date(2022, 12, 31), 50_000, line="gl"),
                        _snap("2022", date(2023, 12, 31), 90_000, line="gl")]
    tri = ld.build_triangle(snaps)
    lines = {l["line"] for l in tri["lines"]}
    assert lines == {"wc", "gl"}
    gl = {l["line"]: l for l in tri["lines"]}["gl"]
    assert gl["label"] == "General Liability"
    # gl 2022: 12mo 50k → 24mo 90k = atf 1.8
    assert {f["from_maturity"]: f["factor"] for f in gl["factors"]}[12] == 1.8


# --- property_loss_signal ---------------------------------------------------
#
# Synthetic tri dicts (matching build_triangle's shape) rather than routing
# through build_triangle itself — property_loss_signal only reads
# lines[].summary/periods, so this pins the adverse_pct → penalty ramp exactly
# without fighting chain-ladder mechanics to hit precise percentages.

def _tri_with_property(adverse_pct=None, total_latest_incurred=100_000.0, periods=None, line="property"):
    return {
        "has_data": True,
        "lines": [{
            "line": line, "label": "Commercial Property",
            "periods": periods if periods is not None else [{"period_label": "2022"}],
            "factors": [],
            "summary": {
                "total_latest_incurred": total_latest_incurred,
                "adverse_pct": adverse_pct,
            },
        }],
    }


def test_property_loss_signal_no_property_line():
    tri = ld.build_triangle([_snap("2022", date(2022, 12, 31), 100_000, line="wc")])
    assert ld.property_loss_signal(tri) is None


def test_property_loss_signal_no_periods():
    tri = _tri_with_property(adverse_pct=40.0, periods=[])
    assert ld.property_loss_signal(tri) is None


def test_property_loss_signal_zero_latest_incurred():
    tri = _tri_with_property(adverse_pct=40.0, total_latest_incurred=0)
    assert ld.property_loss_signal(tri) is None


def test_property_loss_signal_at_or_below_threshold_returns_none():
    assert ld.property_loss_signal(_tri_with_property(adverse_pct=10.0)) is None
    assert ld.property_loss_signal(_tri_with_property(adverse_pct=5.0)) is None


def test_property_loss_signal_mid_ramp():
    result = ld.property_loss_signal(_tri_with_property(adverse_pct=35.0))
    # (35-10)/50*15 = 7.5 -> round-half-to-even -> 8
    assert result == {"adverse_penalty": 8, "adverse_pct": 35.0, "detail": "35.0% adverse development"}


def test_property_loss_signal_caps_at_15():
    result = ld.property_loss_signal(_tri_with_property(adverse_pct=100.0))
    assert result["adverse_penalty"] == 15
