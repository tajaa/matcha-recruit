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


def test_compliance_label_no_longer_claims_to_measure_coverage():
    """The score reports posture now; "Compliance coverage" would be the lie."""
    assert risk_index._COMPONENT_META["compliance"][0] == "Compliance"


# ── compliance posture: the score a broker reads ────────────────────────────
#
# This replaced a score that measured whether WE had researched the company's
# law and reported it as whether the company OBEYED it — at 25% of the
# composite, and it could never fall. Sunset Smile Dental read 100/100 while
# provably violating an OSHA standard we can cite.

def _posture(**kw):
    base = dict(covered=1, locs=1, known=0, surface=10, non_compliant=0)
    base.update(kw)
    return risk_index.compliance_posture_score(**base)


def test_a_confirmed_violation_makes_a_perfect_score_unreachable():
    """The load-bearing one. Proof of a breach must not be outweighable by good
    coverage elsewhere."""
    score, detail, _ = _posture(known=10, surface=10, non_compliant=1)
    assert score <= 70
    assert "1 confirmed violation" in detail


def test_a_fully_assessed_clean_company_can_still_reach_100():
    """The score must remain winnable, or it stops being a signal."""
    score, _, conf = _posture(known=10, surface=10, non_compliant=0)
    assert score == 100
    assert conf == "high"


def test_an_unassessed_company_lands_at_half_not_at_a_pass():
    """Unmeasured is not clean (the evals' rule, with an underwriter attached) —
    but it is not guilt either."""
    score, _, conf = _posture(known=0, surface=10)
    assert score == 50
    assert conf == "low"


def test_more_violations_score_worse():
    scores = [_posture(known=10, surface=10, non_compliant=n)[0] for n in (0, 1, 2, 5)]
    assert scores == sorted(scores, reverse=True)
    assert len(set(scores)) == 4  # each violation actually moves the number


def test_the_score_never_bottoms_out_to_zero():
    """0 would read as "assessed and catastrophic"; the floor keeps a heavily-
    cited company distinguishable from one with no locations at all."""
    score, _, _ = _posture(known=10, surface=10, non_compliant=99)
    assert score == 5


def test_no_locations_is_not_scored():
    score, detail, conf = _posture(covered=0, locs=0)
    assert (score, conf) == (0, "low")
    assert "no active locations" in detail


def test_untracked_locations_drag_the_score():
    tracked, _, _ = _posture(covered=2, locs=2, known=0, surface=10)
    half, _, _ = _posture(covered=1, locs=2, known=0, surface=10)
    assert half < tracked


def test_confidence_tracks_how_much_we_actually_assessed():
    assert _posture(known=0, surface=10)[2] == "low"
    assert _posture(known=3, surface=10)[2] == "low"      # < 1/3
    assert _posture(known=4, surface=10)[2] == "medium"   # >= 1/3
    assert _posture(known=7, surface=10)[2] == "high"     # >= 2/3


def test_confidence_feeds_the_bands_variance_not_just_a_label():
    """_assemble propagates confidence into the composite's ±. Compliance was
    the only component that never set one and silently rode "high"."""
    low = risk_index._component_sigma({"confidence": "low"})
    high = risk_index._component_sigma({"confidence": "high"})
    assert low > high


def test_an_empty_surface_does_not_divide_by_zero():
    score, detail, conf = _posture(known=0, surface=0)
    assert score == 50
    assert conf == "low"
    assert "requirements assessed" not in detail  # nothing to report on


def test_detail_names_what_it_measured():
    _, detail, _ = _posture(covered=1, locs=2, known=3, surface=10, non_compliant=2)
    assert "1/2 locations tracked" in detail
    assert "3/10 requirements assessed" in detail
    assert "2 confirmed violations" in detail


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
    # Read the label from the meta rather than restating it: the string moved
    # once already ("Compliance coverage" → "Compliance", when the score stopped
    # measuring coverage), and a literal here only re-pins the old name.
    assert missing_compliance == {
        "key": "compliance",
        "label": risk_index._COMPONENT_META["compliance"][0],
        "weight": risk_index._WEIGHTS["compliance"],
    }


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


# --- index_confidence --------------------------------------------------------

def test_assemble_index_confidence_high_when_all_components_high():
    comps = [
        {"key": "wc", "label": "Workers' Comp", "weight": 40, "score": 80, "detail": "", "confidence": "high"},
        {"key": "epl", "label": "EPL readiness", "weight": 35, "score": 80, "detail": "", "confidence": "high"},
    ]
    epl = epl_readiness.assess_from_statuses({})
    result = risk_index._assemble(comps, epl, universe=("wc", "epl", "compliance", "property"))
    assert result["index_confidence"] == "high"


def test_assemble_index_confidence_worst_across_components():
    comps = [
        {"key": "wc", "label": "Workers' Comp", "weight": 40, "score": 80, "detail": "", "confidence": "high"},
        {"key": "property", "label": "Commercial Property", "weight": 30, "score": 70, "detail": "", "confidence": "moderate"},
    ]
    epl = epl_readiness.assess_from_statuses({})
    result = risk_index._assemble(comps, epl, universe=("wc", "epl", "compliance", "property"))
    assert result["index_confidence"] == "moderate"


def test_assemble_index_confidence_defaults_high_when_component_omits_it():
    # a component dict without a "confidence" key (backward-compat) defaults high
    comps = [{"key": "wc", "label": "Workers' Comp", "weight": 40, "score": 80, "detail": ""}]
    epl = epl_readiness.assess_from_statuses({})
    result = risk_index._assemble(comps, epl, universe=("wc", "epl", "compliance", "property"))
    assert result["index_confidence"] == "high"


# --- weighted_book_risk confidence_mix ---------------------------------------

def test_weighted_book_risk_confidence_mix_sums_to_one():
    clients = [
        {"index": 80, "band": "strong", "headcount": 10, "confidence": "high"},
        {"index": 60, "band": "adequate", "headcount": 10, "confidence": "moderate"},
        {"index": 40, "band": "developing", "headcount": 20, "confidence": "low"},
    ]
    r = risk_index.weighted_book_risk(clients, "headcount")
    assert abs(sum(r["confidence_mix"].values()) - 1.0) < 1e-6
    assert r["confidence_mix"]["low"] == 0.5  # 20/40 weight


def test_weighted_book_risk_confidence_mix_ignores_missing_confidence():
    clients = [
        {"index": 80, "band": "strong", "headcount": 10, "confidence": "high"},
        {"index": 60, "band": "adequate", "headcount": 10},  # e.g. an off-platform book entry
    ]
    r = risk_index.weighted_book_risk(clients, "headcount")
    assert r["confidence_mix"]["high"] == 0.5  # only the 10/20 with a confidence signal counts
    assert sum(r["confidence_mix"].values()) == 0.5


# --- precomputed-input injection ---------------------------------------------

def test_wc_component_uses_injected_metrics_without_querying():
    """The broker submission context already has WC metrics and the experience
    mod; handing them over must skip both queries, not just be accepted."""
    import asyncio

    class _Conn:
        async def fetch(self, sql, *args):
            raise AssertionError("no query expected when both inputs are injected")

        async def fetchrow(self, sql, *args):
            raise AssertionError("no query expected when both inputs are injected")

    scored = asyncio.run(risk_index._wc_component(
        _Conn(), "cid",
        wc={"severity_band": "at_risk", "ever_recordable": True, "trir": 4.2},
        emr=1.18,
    ))
    assert scored is not None and isinstance(scored[0], int)


def test_property_component_uses_an_injected_cat_rollup():
    import asyncio

    seen: list[str] = []

    class _Conn:
        async def fetch(self, sql, *args):
            seen.append(sql)
            return []

        async def fetchrow(self, sql, *args):
            seen.append(sql)
            return None

    # no buildings → None, but the point is that company_cat_exposure is never
    # reached when the caller passes its own rollup
    asyncio.run(risk_index._property_component(_Conn(), "cid", cat={"worst_tier": "high"}))
    assert not any("property_building_perils" in s for s in seen)
