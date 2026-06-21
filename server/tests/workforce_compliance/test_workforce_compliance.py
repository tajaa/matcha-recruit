"""Pure-logic tests for the Workforce Compliance bundle + EPL scoring math.

No DB / app boot — mirrors the IR pure-helper test model (fast, CI-safe). The
DB-backed derive helpers (derive_pay_transparency / _ai_audit / _biometric) and
the routes are exercised by a manual integration smoke against dev, not here.
"""

from datetime import date, timedelta

import pytest

from app.matcha.services import workforce_compliance as wf
from app.matcha.services import epl_readiness as epl


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
