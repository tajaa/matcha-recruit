"""Pure-logic tests for EPL-readiness scoring (``_assemble_epl``). No DB — the
DB-gathering half of ``compute_epl_readiness`` is exercised by manual
integration on dev (per repo convention)."""

from app.matcha.services import epl_readiness as epl


def _full_inputs(overrides: dict | None = None) -> dict:
    """One factor_inputs entry per FACTORS key, all present + assessed, with
    distinct scores so ranking/renormalization bugs aren't masked by ties. Tests
    override individual factors to exercise the assessed/excluded paths."""
    base = {
        "anti_harassment_policy": {"score": 80, "detail": "d", "kind": "derived", "attestation": None, "assessed": True},
        "harassment_training": {"score": 70, "detail": "d", "kind": "derived", "attestation": None, "assessed": True},
        "documented_discipline": {"score": 60, "detail": "d", "kind": "derived", "attestation": None, "assessed": True},
        "er_case_management": {"score": 50, "detail": "d", "kind": "derived", "attestation": None, "assessed": True},
        "wage_hour_compliance": {"score": 90, "detail": "d", "kind": "derived", "attestation": None, "assessed": True},
        "pay_transparency": {"score": 100, "detail": "d", "kind": "attested", "attestation": {"status": "in_place"}, "assessed": True},
        "biometrics_bipa": {"score": 100, "detail": "d", "kind": "attested", "attestation": {"status": "in_place"}, "assessed": True},
        "pay_equity": {"score": 100, "detail": "d", "kind": "attested", "attestation": {"status": "in_place"}, "assessed": True},
        "ai_hiring_audit": {"score": 100, "detail": "d", "kind": "attested", "attestation": {"status": "in_place"}, "assessed": True},
        "dei_posture": {"score": 100, "detail": "d", "kind": "attested", "attestation": {"status": "in_place"}, "assessed": True},
    }
    for key, patch in (overrides or {}).items():
        base[key] = {**base[key], **patch}
    return base


def _factor(result: dict, key: str) -> dict:
    return {f["key"]: f for f in result["factors"]}[key]


def test_fully_assessed_matches_pre_change_formula():
    """Regression invariant: when every factor is assessed, the new renormalized
    formula must reduce to the old round(composite) — assessed_weight is 100."""
    result = epl._assemble_epl(_full_inputs())
    # scores 80,70,60,50,90 (weights 15,12,10,8,10) + 100x5 (weights 9x5)
    expected = round(
        15 * 0.80 + 12 * 0.70 + 10 * 0.60 + 8 * 0.50 + 10 * 0.90 + 9 * 1.00 * 5
    )
    assert result["score"] == expected == 84
    assert result["assessed_weight"] == 100
    assert result["coverage"] == 1.0


def test_feature_off_zero_records_excluded_and_renormalized():
    """A gated derived factor with zero records and its module off is excluded —
    not scored as a confirmed 0 — and the rest renormalize over the shrunk
    denominator."""
    on = epl._assemble_epl(_full_inputs())
    off = epl._assemble_epl(_full_inputs({
        "harassment_training": {"score": 0, "assessed": False},
    }))
    assert _factor(off, "harassment_training")["assessed"] is False
    assert off["derived_max"] == on["derived_max"] - 12
    assert off["assessed_weight"] == on["assessed_weight"] - 12
    # excluding a zero-scoring factor can only raise (or hold) the composite score
    assert off["score"] >= on["score"]


def test_feature_on_zero_records_counted_as_confirmed_gap():
    """Same zero records, but the module IS on — this is a real gap, not missing
    data, so it's assessed and drags the score down (vs. the excluded/off case)."""
    fully_assessed = epl._assemble_epl(_full_inputs())
    result = epl._assemble_epl(_full_inputs({
        "harassment_training": {"score": 0, "assessed": True},
    }))
    factor = _factor(result, "harassment_training")
    assert factor["assessed"] is True
    assert factor["score"] == 0
    assert result["assessed_weight"] == 100
    assert result["score"] < fully_assessed["score"]


def test_wage_hour_zero_locations_excluded_vs_zero_covered_counted():
    no_locations = epl._assemble_epl(_full_inputs({
        "wage_hour_compliance": {"score": 0, "assessed": False},
    }))
    zero_covered = epl._assemble_epl(_full_inputs({
        "wage_hour_compliance": {"score": 0, "assessed": True},
    }))
    assert _factor(no_locations, "wage_hour_compliance")["assessed"] is False
    assert no_locations["assessed_weight"] == 90  # 100 - wage_hour's weight (10)
    assert _factor(zero_covered, "wage_hour_compliance")["assessed"] is True
    assert zero_covered["assessed_weight"] == 100
    assert zero_covered["score"] < no_locations["score"]


def test_unknown_attested_excluded_others_counted():
    unknown = epl._assemble_epl(_full_inputs({
        "dei_posture": {"score": 0, "assessed": False, "attestation": {"status": "unknown"}},
    }))
    for status, score in (("in_place", 100), ("partial", 50), ("gap", 0)):
        result = epl._assemble_epl(_full_inputs({
            "dei_posture": {"score": score, "assessed": True, "attestation": {"status": status}},
        }))
        factor = _factor(result, "dei_posture")
        assert factor["assessed"] is True
        assert factor["score"] == score
        assert result["assessed_weight"] == 100

    assert _factor(unknown, "dei_posture")["assessed"] is False
    assert unknown["assessed_weight"] == 91  # 100 - dei_posture's weight (9)
    assert unknown["attested_max"] == 36  # 45 - 9


def test_assessed_weight_zero_scores_zero_without_exception():
    all_unassessed = {
        key: {**inp, "assessed": False, "score": 0}
        for key, inp in _full_inputs().items()
    }
    result = epl._assemble_epl(all_unassessed)
    assert result["score"] == 0
    assert result["assessed_weight"] == 0
    assert result["coverage"] == 0.0


def test_excluded_factor_keeps_zero_score_for_controls_evidence_contract():
    """controls_evidence.py downgrades a feature-disabled factor to 'na' by
    checking f.get('score') == 0 — an excluded factor's score must stay 0, not
    disappear or change shape, or that downstream check breaks."""
    result = epl._assemble_epl(_full_inputs({
        "documented_discipline": {"score": 0, "assessed": False},
    }))
    factor = _factor(result, "documented_discipline")
    assert factor["score"] == 0
    assert "assessed" in factor
    # untouched fields stay exactly as before
    assert set(factor.keys()) >= {"key", "label", "kind", "weight", "score", "status", "contribution", "detail", "attestation"}
