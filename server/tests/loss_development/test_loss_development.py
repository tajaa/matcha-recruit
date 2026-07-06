"""Pure tests for the chain-ladder loss-development engine."""

from datetime import date

import pytest

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
    # synthetic fixture carries no reserve_confidence/CI fields -> defaults to "low"/None
    assert result == {"adverse_penalty": 8, "adverse_pct": 35.0, "detail": "35.0% adverse development",
                       "confidence": "low", "ci_width_pct": None}


def test_property_loss_signal_caps_at_15():
    result = ld.property_loss_signal(_tri_with_property(adverse_pct=100.0))
    assert result["adverse_penalty"] == 15


def test_property_loss_signal_carries_real_confidence_and_ci_width():
    # a summary shaped like build_triangle's real output (post Mack's-method fields)
    tri = _tri_with_property(adverse_pct=35.0)
    summary = tri["lines"][0]["summary"]
    summary.update(reserve_confidence="moderate", total_ultimate_low=90_000.0, total_ultimate_high=110_000.0)
    result = ld.property_loss_signal(tri)
    assert result["confidence"] == "moderate"
    assert result["ci_width_pct"] == 20.0  # (110k-90k)/100k*100


# --- Mack's-method reserve variance -----------------------------------------

def test_factor_stats_single_observation_has_no_variance():
    s = ld._factor_stats([1.4])
    assert s == {"mean": 1.4, "n": 1, "variance": None, "std_error": None}


def test_factor_stats_multiple_observations():
    s = ld._factor_stats([1.3, 1.5])
    assert s["mean"] == 1.4 and s["n"] == 2
    # variance is intentionally UNROUNDED here (it's the arithmetic input to
    # _mack_reserve_variance) — only the reported factors[] copy is rounded.
    assert s["variance"] == pytest.approx(((1.3 - 1.4) ** 2 + (1.5 - 1.4) ** 2) / 1)


def test_mack_reserve_variance_none_when_any_step_underdetermined():
    # 12->24 has 2 obs (estimable), 24->36 has 1 obs (not estimable) -> whole chain None
    atf = {12: 1.4, 24: 1.1}
    factor_stats = {12: ld._factor_stats([1.3, 1.5]), 24: ld._factor_stats([1.1])}
    assert ld._mack_reserve_variance(300_000, 12, atf, factor_stats) is None


def test_mack_reserve_variance_zero_when_no_remaining_factors():
    # already at the max maturity -> no projection left -> exact, variance 0
    assert ld._mack_reserve_variance(165_000, 36, {12: 1.4, 24: 1.1}, {}) == 0.0


def test_mack_reserve_variance_positive_when_estimable():
    atf = {12: 1.4}
    factor_stats = {12: ld._factor_stats([1.3, 1.5])}
    var = ld._mack_reserve_variance(200_000, 12, atf, factor_stats)
    assert var is not None and var > 0


def test_build_triangle_period_confidence_fields():
    # a bigger, well-observed triangle: 4 accident years all seen at 12->24mo,
    # 3 at 24->36mo, so the 12mo bucket has n=4 (>=4 -> "high" eligible).
    snaps = [
        _snap("2020", date(2020, 12, 31), 100_000), _snap("2020", date(2021, 12, 31), 140_000),
        _snap("2020", date(2022, 12, 31), 148_000),
        _snap("2021", date(2021, 12, 31), 110_000), _snap("2021", date(2022, 12, 31), 154_000),
        _snap("2021", date(2023, 12, 31), 162_000),
        _snap("2022", date(2022, 12, 31), 120_000), _snap("2022", date(2023, 12, 31), 168_000),
        _snap("2022", date(2024, 12, 31), 176_000),
        _snap("2023", date(2023, 12, 31), 130_000), _snap("2023", date(2024, 12, 31), 182_000),
    ]
    line = _wc(ld.build_triangle(snaps))
    fac12 = {f["from_maturity"]: f for f in line["factors"]}[12]
    assert fac12["n"] == 4 and fac12["variance"] is not None
    p2023 = _period(line, "2023")  # latest at 12mo, needs 12->24 (n=4) and 24->36 (n=3) factors
    assert p2023["reserve_confidence"] in ("high", "moderate")
    assert p2023["reserve_std_error"] is not None
    assert p2023["ultimate_low"] < p2023["ultimate"] < p2023["ultimate_high"]
    # a fully mature period (no remaining factors) is exact
    p2020 = _period(line, "2020")
    assert p2020["reserve_confidence"] == "high"
    assert p2020["ultimate_low"] == p2020["ultimate_high"] == p2020["ultimate"]


def test_chain_hole_between_flanking_buckets_forces_low_confidence():
    # A1/A2 observed 12mo->24mo (books a ratio keyed at maturity 12, n=2).
    # B1/B2 observed 36mo->48mo (books a ratio keyed at maturity 36, n=2).
    # No period is EVER observed across the 24->36 transition, so atf = {12, 36}
    # with a hole at 24 — cdf_from silently treats that missing step as 1.0.
    # The confidence ladder must catch this even though each flanking bucket
    # individually has n=2 (which would otherwise read as "moderate").
    snaps = [
        _snap("A1", date(2019, 1, 1), 100_000, start=date(2018, 1, 1)),
        _snap("A1", date(2020, 1, 1), 140_000, start=date(2018, 1, 1)),
        _snap("A2", date(2019, 1, 1), 100_000, start=date(2018, 1, 1)),
        _snap("A2", date(2020, 1, 1), 140_000, start=date(2018, 1, 1)),
        _snap("B1", date(2023, 1, 1), 100_000, start=date(2020, 1, 1)),
        _snap("B1", date(2024, 1, 1), 140_000, start=date(2020, 1, 1)),
        _snap("B2", date(2023, 1, 1), 100_000, start=date(2020, 1, 1)),
        _snap("B2", date(2024, 1, 1), 140_000, start=date(2020, 1, 1)),
        _snap("SUBJ", date(2025, 1, 1), 300_000, start=date(2024, 1, 1)),
    ]
    line = _wc(ld.build_triangle(snaps))
    fac = {f["from_maturity"]: f for f in line["factors"]}
    assert set(fac) == {12, 36}  # confirms the hole at 24 exists in this fixture
    subj = _period(line, "SUBJ")
    assert subj["maturity_gap"] is False  # single point — no gap in ITS OWN valuations
    assert subj["reserve_confidence"] == "low"
    assert subj["reserve_std_error"] is None
    assert subj["ultimate_low"] is None and subj["ultimate_high"] is None


def test_greenfield_line_no_development_factors_is_low_confidence():
    # A single loss run (one valuation per policy year, no development pairs) has
    # NO age-to-age factors at all — cdf_from returns 1.0 by default, so the
    # projected ultimate is just the latest reported. That's the LEAST certain
    # read (most likely to develop), and must NOT report as high confidence.
    snaps = [
        _snap("2023", date(2023, 12, 31), 350_000),
        _snap("2024", date(2024, 12, 31), 430_000),
    ]
    line = _wc(ld.build_triangle(snaps))
    assert line["factors"] == []  # confirms zero development signal
    for label in ("2023", "2024"):
        p = _period(line, label)
        assert p["cdf"] == 1.0
        assert p["ultimate"] == p["latest_incurred"]  # undeveloped — latest = ultimate
        assert p["reserve_confidence"] == "low"
        assert p["ultimate_low"] is None and p["ultimate_high"] is None
    assert line["summary"]["reserve_confidence"] == "low"
    assert line["summary"]["total_ultimate_low"] is None


def test_genuine_runoff_period_at_max_maturity_stays_high():
    # Distinct from greenfield: the line HAS a triangle, and the oldest period
    # sits beyond its last measured development step — cdf=1.0 is evidence-based
    # (fully run off), so it legitimately reports high with an exact point.
    line = _wc(ld.build_triangle(TRIANGLE))
    p21 = _period(line, "2021")  # fully mature at 36mo (the max), no remaining factors
    assert p21["latest_maturity"] == 36 and p21["cdf"] == 1.0
    assert p21["reserve_confidence"] == "high"
    assert p21["ultimate_low"] == p21["ultimate_high"] == p21["ultimate"]


def test_empty_points_period_drags_summary_confidence_to_low():
    # a period label with no parseable year and no explicit start -> every
    # valuation fails to bucket into a maturity -> zero points. It must still
    # count toward the summary's worst-of, matching what its own row shows.
    snaps = list(TRIANGLE) + [_snap("Current Term", date(2024, 1, 1), 50_000)]
    line = _wc(ld.build_triangle(snaps))
    unparsed = _period(line, "Current Term")
    assert unparsed["points"] == []
    assert unparsed["reserve_confidence"] == "low"
    assert line["summary"]["reserve_confidence"] == "low"


def test_build_triangle_single_valuation_is_low_confidence():
    # every maturity bucket has n=1 -> no variance is estimable anywhere
    line = _wc(ld.build_triangle(TRIANGLE))
    p23 = _period(line, "2023")  # latest at 12mo; chain needs 12->24 (n=2, ok) and 24->36 (n=1, not ok)
    assert p23["reserve_confidence"] == "low"
    assert p23["reserve_std_error"] is None
    assert p23["ultimate_low"] is None and p23["ultimate_high"] is None
    assert line["summary"]["reserve_confidence"] == "low"
    assert line["summary"]["total_reserve_std_error"] is None
