"""Pure-logic tests for the exposure-weighted book risk roll-up.

No DB — only the pure function app.matcha.services.risk_index.weighted_book_risk.
This is the canonical source of truth the client-side TS port (utils/bookRisk.ts)
mirrors; the same fixtures are ported to client/src/utils/bookRisk.test.ts.
"""

import pytest

from app.matcha.services.risk_index import weighted_book_risk


def _c(index, band, headcount=None, premium=None):
    return {"index": index, "band": band, "headcount": headcount, "annual_premium": premium}


# --- empty / degenerate -----------------------------------------------------

def test_empty_book():
    a = weighted_book_risk([], "headcount")
    assert a["weighted_mean"] is None
    assert a["equal_weight_mean"] is None
    assert a["weighted_band"] is None
    assert a["total_weight"] == 0
    assert a["scored_count"] == 0
    assert a["band_mix"] == {"strong": 0.0, "adequate": 0.0, "developing": 0.0, "exposed": 0.0}


def test_all_basis_missing_keeps_equal_mean_only():
    # Two scored clients, neither has headcount → no weighted mean, but equal mean holds.
    clients = [_c(40, "developing"), _c(80, "strong")]
    a = weighted_book_risk(clients, "headcount")
    assert a["weighted_mean"] is None
    assert a["weighted_band"] is None
    assert a["equal_weight_mean"] == 60.0
    assert a["total_weight"] == 0
    assert a["scored_count"] == 2
    assert a["weighted_count"] == 0
    assert a["missing_basis_count"] == 2
    assert all(v == 0.0 for v in a["band_mix"].values())


# --- weighting --------------------------------------------------------------

def test_single_client():
    a = weighted_book_risk([_c(72, "adequate", headcount=50)], "headcount")
    assert a["weighted_mean"] == 72.0
    assert a["equal_weight_mean"] == 72.0
    assert a["weighted_band"] == "adequate"
    assert a["total_weight"] == 50
    assert a["band_mix"]["adequate"] == 1.0


def test_big_account_dominates_weighted_mean():
    # 90-index tiny shop (10) vs 30-index big shop (90). Equal mean = 60; weighted
    # toward the big low-scoring account.
    clients = [_c(90, "strong", headcount=10), _c(30, "exposed", headcount=90)]
    a = weighted_book_risk(clients, "headcount")
    assert a["equal_weight_mean"] == 60.0
    # (90*10 + 30*90) / 100 = 36.0
    assert a["weighted_mean"] == 36.0
    assert a["weighted_band"] == "developing"
    assert a["total_weight"] == 100


def test_premium_basis_uses_annual_premium():
    clients = [_c(80, "strong", headcount=5, premium=100_000),
               _c(40, "developing", headcount=5, premium=300_000)]
    a = weighted_book_risk(clients, "premium")
    assert a["basis"] == "premium"
    # (80*100k + 40*300k) / 400k = 50.0
    assert a["weighted_mean"] == 50.0
    assert a["total_weight"] == 400_000


def test_mixed_missing_excluded_from_weight_but_in_equal_mean():
    clients = [_c(90, "strong", headcount=100), _c(30, "exposed")]  # 2nd has no headcount
    a = weighted_book_risk(clients, "headcount")
    assert a["weighted_mean"] == 90.0          # only the weighted client counts
    assert a["equal_weight_mean"] == 60.0      # both count equally here
    assert a["weighted_count"] == 1
    assert a["missing_basis_count"] == 1
    assert a["band_mix"]["strong"] == 1.0      # mix is over weighted clients only


# --- band mix ---------------------------------------------------------------

def test_band_mix_sums_to_one():
    clients = [
        _c(90, "strong", headcount=20),
        _c(70, "adequate", headcount=30),
        _c(50, "developing", headcount=10),
        _c(20, "exposed", headcount=40),
    ]
    a = weighted_book_risk(clients, "headcount")
    assert a["band_mix"]["strong"] == pytest.approx(0.2)
    assert a["band_mix"]["exposed"] == pytest.approx(0.4)
    assert sum(a["band_mix"].values()) == pytest.approx(1.0)
