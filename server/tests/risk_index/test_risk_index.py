"""Pure-logic tests for the composite risk index. compute_risk_index itself is
DB-coupled (exercised by a dev integration smoke); these cover the pure pieces."""

from app.matcha.services import risk_index, epl_readiness


def test_band_reexports_epl_thresholds():
    assert risk_index.band(85) == "strong"
    assert risk_index.band(65) == "adequate"
    assert risk_index.band(40) == "developing"
    assert risk_index.band(10) == "exposed"


def test_weights_cover_components():
    assert set(risk_index._WEIGHTS) == {"wc", "epl", "compliance", "property"}
    # The casualty triple still sums to 100 → a casualty-only client's renormalized
    # index is unchanged by adding the (optional, presence-gated) property component.
    assert risk_index._WEIGHTS["wc"] + risk_index._WEIGHTS["epl"] + risk_index._WEIGHTS["compliance"] == 100


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


def test_top_fixes_ranks_by_weight_times_shortfall_not_raw_score():
    comps = [
        {"key": "wc", "label": "Workers' Comp", "weight": 40, "score": 65, "detail": ""},
        {"key": "compliance", "label": "Compliance coverage", "weight": 10, "score": 10, "detail": ""},
    ]
    # raw score order would rank compliance (10) before wc (65); weight×shortfall
    # (wc: 40*35=1400 vs compliance: 10*90=900) ranks wc first instead.
    epl = epl_readiness.assess_from_statuses({f["key"]: "in_place" for f in epl_readiness.FACTORS})
    fixes = risk_index._top_fixes(comps, epl)
    assert fixes[0].lower().startswith("raise workers' comp")
    assert fixes[1].lower().startswith("raise compliance coverage")


# --- _assemble coverage / components_missing -------------------------------

def test_assemble_reports_coverage_and_missing_components():
    comps = [
        {"key": "wc", "label": "Workers' Comp", "weight": risk_index._WEIGHTS["wc"], "score": 80, "detail": ""},
        {"key": "epl", "label": "EPL readiness", "weight": risk_index._WEIGHTS["epl"], "score": 80, "detail": ""},
    ]
    epl = epl_readiness.assess_from_statuses({})
    result = risk_index._assemble(comps, epl, universe=("wc", "epl", "compliance", "property"))
    assert result["coverage"] == round((risk_index._WEIGHTS["wc"] + risk_index._WEIGHTS["epl"]) / 130, 2)
    assert {m["key"] for m in result["components_missing"]} == {"compliance", "property"}
    missing_compliance = next(m for m in result["components_missing"] if m["key"] == "compliance")
    assert missing_compliance == {"key": "compliance", "label": "Compliance coverage", "weight": risk_index._WEIGHTS["compliance"]}


def test_assemble_full_coverage_when_all_components_present():
    comps = [
        {"key": k, "label": label, "weight": weight, "score": 80, "detail": ""}
        for k, (label, weight) in risk_index._COMPONENT_META.items()
    ]
    epl = epl_readiness.assess_from_statuses({})
    result = risk_index._assemble(comps, epl)
    assert result["coverage"] == 1.0
    assert result["components_missing"] == []


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
