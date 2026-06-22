"""Pure tests for the experience-mod proxy + worksheet-parse coercion.

No DB / app boot — the trajectory assembly + routes are smoke-tested against dev.
"""

from app.matcha.services import wc_depth
from app.matcha.services import wc_mod_parser as mp


# --- proxy_mod (directional actual ÷ expected) -----------------------------

def test_proxy_mod_basic():
    assert wc_depth.proxy_mod(120_000, 100_000) == 1.2   # adverse
    assert wc_depth.proxy_mod(50_000, 100_000) == 0.5    # favorable
    assert wc_depth.proxy_mod(100_000, 100_000) == 1.0   # on plan


def test_proxy_mod_no_expected_base_is_none():
    assert wc_depth.proxy_mod(50_000, 0) is None
    assert wc_depth.proxy_mod(50_000, None) is None      # type: ignore[arg-type]
    assert wc_depth.proxy_mod(0, -10) is None


# --- worksheet parse coercion (clamps model output to the mod schema) ------

def test_mod_worksheet_coerce_valid():
    out = mp._coerce({"experience_mod": 1.05, "rating_effective_date": "2026-01-01",
                      "carrier": "Acme Mutual", "state": "ca",
                      "expected_losses": 250000, "actual_losses": 300000})
    assert out["experience_mod"] == 1.05
    assert out["policy_period_start"] == "2026-01-01"   # falls back to rating date
    assert out["state"] == "CA"                          # upper-cased
    assert out["carrier"] == "Acme Mutual"


def test_mod_worksheet_coerce_rejects_out_of_range_mod():
    assert mp._coerce({"experience_mod": 0})["experience_mod"] is None      # must be > 0
    assert mp._coerce({"experience_mod": 12})["experience_mod"] is None     # must be <= 10
    assert mp._coerce({"experience_mod": "n/a"})["experience_mod"] is None  # non-numeric


def test_mod_worksheet_coerce_garbage_safe():
    out = mp._coerce({})
    assert out["experience_mod"] is None and out["state"] is None
    # negative loss figures are dropped, not kept
    assert mp._coerce({"expected_losses": -5})["expected_losses"] is None
    assert mp._coerce({"state": "xyz"})["state"] is None  # not a 2-letter code
