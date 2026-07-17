"""Pure-logic tests for the Workforce Compliance bundle + EPL scoring math.

No DB / app boot — mirrors the IR pure-helper test model (fast, CI-safe). The
DB-backed derive helpers (derive_pay_transparency / _ai_audit / _biometric) and
the routes are exercised by a manual integration smoke against dev, not here.
"""

from datetime import date, timedelta

import pytest

from app.matcha.services import workforce_compliance as wf
from app.matcha.services import epl_readiness as epl
from app.matcha.services import pay_equity_analysis as pe


# --- audit_dates (AI-audit cadence / overdue math) -------------------------

def test_audit_dates_never_audited_is_overdue():
    nxt, overdue = wf.audit_dates(None, 365)
    assert nxt is None
    assert overdue is True


def test_audit_dates_recent_not_overdue():
    last = date.today() - timedelta(days=10)
    nxt, overdue = wf.audit_dates(last, 365)
    assert overdue is False
    assert nxt == last + timedelta(days=365)


def test_audit_dates_past_due_is_overdue():
    last = date.today() - timedelta(days=400)
    _, overdue = wf.audit_dates(last, 365)
    assert overdue is True


def test_audit_dates_cadence_zero_defaults_to_365():
    nxt, _ = wf.audit_dates(date(2026, 1, 1), 0)
    assert nxt == date(2026, 1, 1) + timedelta(days=365)


# --- PAY_TRANSPARENCY_STATES -----------------------------------------------

def test_pay_transparency_states_are_valid_codes():
    assert wf.PAY_TRANSPARENCY_STATES
    assert all(len(s) == 2 and s.isupper() and s.isalpha() for s in wf.PAY_TRANSPARENCY_STATES)
    assert "CA" in wf.PAY_TRANSPARENCY_STATES


# --- EPL factor catalog invariants -----------------------------------------

def test_factor_weights_sum_to_100():
    assert sum(f["weight"] for f in epl.FACTORS) == 100


def test_exactly_ten_factors():
    assert len(epl.FACTORS) == 10


def test_business_derivable_are_attested_factor_keys():
    """The 3 flip-able factors must be attested in the catalog (so off-platform
    stays attested; only the tenant path with the feature on flips them)."""
    attested = {f["key"] for f in epl.FACTORS if f["kind"] == "attested"}
    assert epl.BUSINESS_DERIVABLE <= attested
    assert epl.BUSINESS_DERIVABLE == {"pay_transparency", "ai_hiring_audit", "biometrics_bipa", "pay_equity"}


# --- band thresholds -------------------------------------------------------

@pytest.mark.parametrize("score,band", [
    (100, "strong"), (80, "strong"), (79, "adequate"), (60, "adequate"),
    (59, "developing"), (35, "developing"), (34, "exposed"), (0, "exposed"),
])
def test_readiness_band_boundaries(score, band):
    assert epl.readiness_band(score) == band


@pytest.mark.parametrize("score,band", [
    (100, "strong"), (70, "strong"), (69, "partial"), (35, "partial"), (34, "gap"), (0, "gap"),
])
def test_factor_band_boundaries(score, band):
    assert epl._factor_band(score) == band


# --- assess_from_statuses (off-platform pure scorer) -----------------------

def test_assess_all_unknown_is_zero_and_exposed():
    a = epl.assess_from_statuses({})
    assert a["score"] == 0
    assert a["band"] == "exposed"
    assert a["derived_max"] == 0
    assert a["attested_max"] == 100
    assert len(a["factors"]) == 10
    assert all(f["kind"] == "attested" for f in a["factors"])


def test_assess_all_in_place_is_100_strong():
    statuses = {f["key"]: "in_place" for f in epl.FACTORS}
    a = epl.assess_from_statuses(statuses)
    assert a["score"] == 100
    assert a["band"] == "strong"


def test_assess_all_partial_is_half():
    statuses = {f["key"]: "partial" for f in epl.FACTORS}
    assert epl.assess_from_statuses(statuses)["score"] == 50


def test_assess_single_factor_weighted_correctly():
    # only the 15-weight anti-harassment policy in place → composite 15.
    a = epl.assess_from_statuses({"anti_harassment_policy": "in_place"})
    assert a["score"] == 15


def test_assess_invalid_status_treated_as_unknown():
    assert epl.assess_from_statuses({"pay_equity": "bogus"})["score"] == 0


# --- top_gap ---------------------------------------------------------------

def test_top_gap_picks_highest_weighted_shortfall():
    a = epl.assess_from_statuses({})  # everything 0
    gap = epl.top_gap(a)
    assert gap is not None
    # anti_harassment_policy carries the largest weight (15)
    assert gap["key"] == "anti_harassment_policy"


def test_top_gap_none_when_all_strong():
    statuses = {f["key"]: "in_place" for f in epl.FACTORS}
    a = epl.assess_from_statuses(statuses)
    assert epl.top_gap(a) is None


# --- pay-equity role_stats (within-role dispersion math) -------------------

def test_pay_equity_role_stats_clean_role():
    s = pe.role_stats("Analyst", [100_000, 100_000])
    assert s["spread_pct"] == 0.0 and s["severity"] == "ok"
    assert s["below_band_n"] == 0 and s["remediation_cost"] == 0


def test_pay_equity_role_stats_flagged_with_remediation():
    s = pe.role_stats("Engineer", [50_000, 100_000, 150_000])
    assert s["median"] == 100_000
    assert s["spread_pct"] == 100.0          # (150k-50k)/100k
    assert s["severity"] == "flag"           # ≥30% spread
    assert s["range_ratio"] == 3.0
    # one person below 80% of the 100k median (80k floor); lift cost = 30k
    assert s["below_band_n"] == 1 and s["remediation_cost"] == 30_000


def test_pay_equity_role_stats_watch_tier():
    s = pe.role_stats("Manager", [100_000, 120_000])
    assert 15.0 <= s["spread_pct"] < 30.0 and s["severity"] == "watch"
    assert s["below_band_n"] == 0            # 100k is above the 0.8*110k band floor


# --- pay-equity posture_band (overall headline) ----------------------------

def test_posture_band_insufficient_when_no_roles():
    assert pe.posture_band([], 0)["band"] == "insufficient"


def test_posture_band_equitable_when_all_ok():
    roles = [{"severity": "ok"}, {"severity": "ok"}]
    assert pe.posture_band(roles, 0)["band"] == "equitable"


def test_posture_band_watch_on_dispersion_but_nobody_below():
    roles = [{"severity": "ok"}, {"severity": "watch"}, {"severity": "ok"}, {"severity": "ok"}]
    assert pe.posture_band(roles, 0)["band"] == "watch"


def test_posture_band_action_when_anyone_below_band():
    roles = [{"severity": "ok"}, {"severity": "ok"}]
    assert pe.posture_band(roles, 1)["band"] == "action"


def test_posture_band_action_when_quarter_of_roles_flagged():
    roles = [{"severity": "flag"}, {"severity": "ok"}, {"severity": "ok"}, {"severity": "ok"}]
    # 1/4 = 0.25 → action even with nobody below band
    assert pe.posture_band(roles, 0)["band"] == "action"


# --- pay-equity priority_actions (ranked fixes) ----------------------------

def _role(title, *, below=0, cost=0, spread=0.0, severity="ok", n=2):
    return {"title": title, "below_band_n": below, "remediation_cost": cost,
            "spread_pct": spread, "severity": severity, "n": n}


def test_priority_actions_empty_when_clean():
    roles = [_role("A"), _role("B", spread=10.0, severity="watch")]
    assert pe.priority_actions(roles) == []


def test_priority_actions_below_band_outranks_high_spread():
    roles = [
        _role("HighSpread", spread=80.0, severity="flag"),               # flagged, nobody below
        _role("BelowBand", below=2, cost=20_000, spread=40.0, severity="flag"),
    ]
    out = pe.priority_actions(roles)
    assert [p["title"] for p in out] == ["BelowBand", "HighSpread"]
    assert "Lift 2 employees" in out[0]["action"] and "$20,000" in out[0]["action"]
    assert "Review 80.0% spread" in out[1]["action"]


def test_priority_actions_ranks_below_band_by_cost_desc():
    roles = [
        _role("Cheap", below=1, cost=5_000, spread=35.0, severity="flag"),
        _role("Pricey", below=3, cost=50_000, spread=35.0, severity="flag"),
    ]
    out = pe.priority_actions(roles)
    assert [p["title"] for p in out] == ["Pricey", "Cheap"]


def test_priority_actions_caps_at_limit():
    roles = [_role(f"R{i}", below=1, cost=1000 * (i + 1), severity="flag") for i in range(8)]
    assert len(pe.priority_actions(roles)) == 5


# ── protected-class gap (HRIS demographics) ───────────────────────────────────

def _cell(n: int, pay: float) -> list[float]:
    return [pay] * n


def test_class_gap_measures_between_group_medians():
    """The thing role_stats deliberately is not: a difference attributable to class."""
    g = pe.class_gap_stats("Engineer", {
        "male": _cell(6, 100_000),
        "female": _cell(5, 90_000),
    })
    assert g["gap_pct"] == 10.0          # (100k-90k)/100k
    assert g["reference"] == "male"      # highest-paid class
    assert g["lowest"] == "female"
    assert g["n"] == 11


def test_class_gap_suppresses_small_cells():
    """A class with n<5 in a role is one or two people: its 'median' is an individual's
    salary, so the gap would be that person — invented statistics plus re-identification."""
    g = pe.class_gap_stats("Engineer", {
        "male": _cell(6, 100_000),
        "female": _cell(2, 40_000),      # suppressed — would otherwise show a 60% gap
    })
    assert g is None                     # only one class survives → nothing to compare
    g2 = pe.class_gap_stats("Analyst", {
        "male": _cell(5, 100_000),
        "female": _cell(5, 95_000),
        "other": _cell(1, 20_000),       # suppressed, but counted
    })
    assert g2["gap_pct"] == 5.0
    assert g2["suppressed_n"] == 1
    assert [c["class"] for c in g2["classes"]] == ["male", "female"]


def test_class_gap_needs_two_comparable_classes():
    """One group is not a comparison. Returning 0.0 would read as 'no gap found' when
    the truth is 'not measurable'."""
    assert pe.class_gap_stats("Solo", {"male": _cell(9, 100_000)}) is None
    assert pe.class_gap_stats("Empty", {}) is None


def test_class_gap_parity_is_zero_not_none():
    """Measured-and-equal must be distinguishable from not-measured."""
    g = pe.class_gap_stats("Support", {"male": _cell(5, 80_000), "female": _cell(5, 80_000)})
    assert g is not None and g["gap_pct"] == 0.0


def test_review_row_without_demographics_leaves_gap_pct_null():
    """The live defect: the dispersion share was written into gap_pct, which
    derive_pay_equity reports to brokers as '{x}% gap'."""
    a = {
        "flagged_roles": 2, "analyzed_roles": 5, "employee_count": 20,
        "headline_gap_pct": 40, "worst": None, "remediation_estimate": 0,
        "employees_below_band": 0, "class_gap_pct": None, "class_gaps": [],
        "demographics_coverage_pct": 0.0,
    }
    r = pe.review_row(a)
    assert r["gap_pct"] is None           # we did not measure a gap → claim nothing
    assert r["dispersion_pct"] == 40      # the screen result, under its own name
    assert "screen only" in r["methodology"]


def test_review_row_with_demographics_reports_the_measured_gap():
    a = {
        "flagged_roles": 1, "analyzed_roles": 4, "employee_count": 30,
        "headline_gap_pct": 25, "worst": None, "remediation_estimate": 0,
        "employees_below_band": 0, "class_gap_pct": 8.4,
        "class_gaps": [{"title": "Engineer", "gap_pct": 12.0, "reference": "male", "n": 12}],
        "demographics_coverage_pct": 87.0,
    }
    r = pe.review_row(a)
    assert r["gap_pct"] == 8.4
    assert r["dispersion_pct"] == 25
    assert "HRIS demographics" in r["methodology"]
    assert "87.0% coverage" in r["methodology"]
    assert "8.4% gender pay gap" in r["note"]
