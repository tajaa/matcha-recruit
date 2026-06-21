"""Pure-logic tests for the composite risk index. compute_risk_index itself is
DB-coupled (exercised by a dev integration smoke); these cover the pure pieces."""

from app.matcha.services import risk_index, epl_readiness


def test_band_reexports_epl_thresholds():
    assert risk_index.band(85) == "strong"
    assert risk_index.band(65) == "adequate"
    assert risk_index.band(40) == "developing"
    assert risk_index.band(10) == "exposed"


def test_weights_cover_three_components():
    assert set(risk_index._WEIGHTS) == {"wc", "epl", "compliance"}
    assert sum(risk_index._WEIGHTS.values()) == 100


def test_top_fixes_orders_weak_components_and_appends_epl_gap():
    comps = [
        {"key": "wc", "label": "Workers' Comp", "weight": 40, "score": 20, "detail": ""},
        {"key": "epl", "label": "EPL readiness", "weight": 35, "score": 80, "detail": ""},
        {"key": "compliance", "label": "Compliance coverage", "weight": 25, "score": 50, "detail": ""},
    ]
    epl = epl_readiness.assess_from_statuses({})  # all-gap → top_gap returns the heaviest factor
    fixes = risk_index._top_fixes(comps, epl)
    assert fixes[0].startswith("raise workers' comp") or fixes[0].startswith("Raise workers' comp")
    assert any("compliance coverage" in f for f in fixes)
    assert not any("epl readiness" in f.lower() for f in fixes)  # 80 is not < 70
    assert any(f.startswith("EPL: address") for f in fixes)


def test_top_fixes_empty_when_all_strong():
    comps = [{"key": "wc", "label": "Workers' Comp", "weight": 40, "score": 90, "detail": ""}]
    epl = epl_readiness.assess_from_statuses({f["key"]: "in_place" for f in epl_readiness.FACTORS})
    assert risk_index._top_fixes(comps, epl) == []


# --- external_risk_index (off-platform) ------------------------------------

def test_external_risk_index_has_no_compliance_component():
    wc = {"has_data": True, "severity_band": "good", "current_emr": 0.9, "recordable_cases": 1, "trir": 1.0}
    epl = epl_readiness.assess_from_statuses({f["key"]: "in_place" for f in epl_readiness.FACTORS})
    r = risk_index.external_risk_index(wc, epl)
    assert {c["key"] for c in r["components"]} == {"wc", "epl"}  # off-platform = no locations
    assert r["index"] is not None and r["band"]


def test_external_risk_index_drops_wc_without_data():
    epl = epl_readiness.assess_from_statuses({})
    r = risk_index.external_risk_index({"has_data": False, "recordable_cases": 0}, epl)
    assert [c["key"] for c in r["components"]] == ["epl"]
    assert r["index"] == epl["score"]  # single component → index equals it
