"""Pure-logic tests for directional property exposure ($ AAL / PML / coinsurance).

No DB — only the pure helpers in app.matcha.services.property_exposure.
"""

from app.matcha.services import property_exposure as ex


def _b(bid="b1", tiv=10_000_000, insured=None, replacement=None, perils=None):
    return {
        "id": bid, "tiv": tiv, "insured_value": insured, "replacement_cost": replacement,
        "perils": perils or [],
    }


# --- coinsurance shortfall -------------------------------------------------

def test_coinsurance_shortfall_under_insured():
    # 60% ITV on $9M replacement → required 0.9*9M=8.1M, carried 5.4M → 2.7M short.
    assert ex.coinsurance_shortfall(5_400_000, 9_000_000) == 2_700_000


def test_coinsurance_shortfall_compliant_is_zero():
    assert ex.coinsurance_shortfall(9_000_000, 9_000_000) == 0.0


def test_coinsurance_shortfall_no_replacement_is_zero():
    assert ex.coinsurance_shortfall(5_000_000, None) == 0.0
    assert ex.coinsurance_shortfall(5_000_000, 0) == 0.0


# --- peril pml / aal -------------------------------------------------------

def test_peril_pml_scales_with_tier():
    severe = ex.peril_pml(10_000_000, "wind", "severe")
    high = ex.peril_pml(10_000_000, "wind", "high")
    assert severe > high > 0


def test_peril_pml_none_tier_is_zero():
    assert ex.peril_pml(10_000_000, "wind", None) == 0.0
    assert ex.peril_aal(10_000_000, "wind", None) == 0.0


def test_aal_is_smaller_than_pml():
    # AAL ≈ PML × annual probability, so always well below the single-event PML.
    assert ex.peril_aal(10_000_000, "flood", "severe") < ex.peril_pml(10_000_000, "flood", "severe")


# --- building / portfolio rollup -------------------------------------------

def test_building_exposure_worst_pml_is_single_peril_max():
    b = _b(tiv=10_000_000, perils=[
        {"peril": "flood", "tier": "severe"}, {"peril": "wind", "tier": "moderate"}])
    out = ex.building_exposure(b)
    # worst_pml is the single worst peril event, not the sum.
    assert out["worst_pml"] == max(v["pml"] for v in out["by_peril"].values())
    assert out["aal"] == sum(v["aal"] for v in out["by_peril"].values())


def test_portfolio_pml_accumulates_by_peril_across_buildings():
    # Two buildings both severe-wind → portfolio wind PML is their SUM (one storm hits both).
    b1 = _b(bid="a", tiv=10_000_000, perils=[{"peril": "wind", "tier": "severe"}])
    b2 = _b(bid="b", tiv=10_000_000, perils=[{"peril": "wind", "tier": "severe"}])
    out = ex.portfolio_exposure([b1, b2])
    single = ex.peril_pml(10_000_000, "wind", "severe")
    assert out["worst_pml_peril"] == "wind"
    assert out["worst_pml"] == round(single * 2)
    assert out["basis"] == "directional estimate"


def test_portfolio_empty_is_zeroed():
    out = ex.portfolio_exposure([])
    assert out["total_aal"] == 0 and out["worst_pml"] == 0 and out["coinsurance_shortfall"] == 0
    assert out["worst_pml_peril"] is None


# --- deeper capture (propd01): deductibles + per-building coinsurance ------

def test_pml_is_net_of_percentage_deductible():
    b = _b(tiv=10_000_000, perils=[{"peril": "quake", "tier": "severe"}])
    b["quake_deductible_pct"] = 10            # 10% of TIV = $1M retained
    out = ex.building_exposure(b)
    gross = ex.peril_pml(10_000_000, "quake", "severe")
    assert out["by_peril"]["quake"]["pml"] == round(gross - 1_000_000)


def test_named_storm_deductible_applies_to_wind():
    b = _b(tiv=10_000_000, perils=[{"peril": "wind", "tier": "severe"}])
    b["named_storm_deductible_pct"] = 5
    out = ex.building_exposure(b)
    gross = ex.peril_pml(10_000_000, "wind", "severe")
    assert out["by_peril"]["wind"]["pml"] == round(gross - 500_000)


def test_coinsurance_uses_building_pct():
    # 80% clause + insured to 80% of replacement → compliant, no shortfall.
    b = _b(tiv=5_000_000, insured=4_000_000, replacement=5_000_000)
    b["coinsurance_pct"] = 80
    assert ex.building_exposure(b)["coinsurance_shortfall"] == 0.0
