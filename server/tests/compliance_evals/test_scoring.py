"""Subscore math + the onboarding-readiness gate."""
import pytest

from app.core.services.compliance_evals.scoring import (
    DEGRADED,
    NOT_READY,
    READY,
    Subscores,
    accuracy_score,
    authority_score,
    completeness_score,
    composite_score,
    evaluate_readiness,
    freshness_score,
    missing_keys,
    tagging_score,
)


# ── completeness ──────────────────────────────────────────────────────────────

def test_completeness_all_present():
    expected = {"minimum_wage": {"a", "b"}, "overtime": {"c"}}
    present = {"minimum_wage": {"a", "b"}, "overtime": {"c"}}
    assert completeness_score(present, expected, {}) == 100.0


def test_completeness_half_present():
    expected = {"minimum_wage": {"a", "b"}}
    present = {"minimum_wage": {"a"}}
    assert completeness_score(present, expected, {}) == 50.0


def test_completeness_weights_shift_the_score():
    """A miss in a high-confidence category costs more than one in a low."""
    expected = {"hot": {"a"}, "cold": {"b"}}
    weights = {"hot": 1.0, "cold": 0.2}

    missing_hot = completeness_score({"cold": {"b"}}, expected, weights)
    missing_cold = completeness_score({"hot": {"a"}}, expected, weights)
    assert missing_cold > missing_hot


def test_completeness_unprofiled_category_weighs_full():
    expected = {"unprofiled": {"a", "b"}}
    assert completeness_score({"unprofiled": {"a"}}, expected, {"other": 0.1}) == 50.0


def test_completeness_extra_present_keys_do_not_inflate():
    expected = {"minimum_wage": {"a"}}
    present = {"minimum_wage": {"a", "z", "y"}}
    assert completeness_score(present, expected, {}) == 100.0


def test_completeness_empty_expected():
    assert completeness_score({}, {}, {}) == 0.0


def test_missing_keys_omits_covered_categories():
    expected = {"a": {"x", "y"}, "b": {"z"}}
    present = {"a": {"x"}, "b": {"z"}}
    assert missing_keys(present, expected) == {"a": ["y"]}


# ── authority ─────────────────────────────────────────────────────────────────

def test_authority_all_primary():
    assert authority_score({"primary": 10}) == 100.0


def test_authority_missing_citations_score_zero():
    assert authority_score({"missing": 5}) == 0.0


def test_authority_mixed():
    # 1 primary (1.0) + 1 aggregator (0.3) over 2 rows → 65
    assert authority_score({"primary": 1, "aggregator": 1}) == 65.0


def test_authority_no_rows_is_none_not_zero():
    assert authority_score({}) is None


# ── accuracy ──────────────────────────────────────────────────────────────────

def test_accuracy_pass_rate():
    assert accuracy_score(9, 1) == 90.0


def test_accuracy_unmeasured_is_none():
    assert accuracy_score(0, 0) is None


def test_one_critical_failure_zeroes_accuracy():
    """40 passing facts cannot launder a wrong state minimum wage."""
    assert accuracy_score(40, 1, critical_failures=1) == 0.0


# ── tagging ───────────────────────────────────────────────────────────────────

def test_tagging_clean():
    assert tagging_score(100, 0, 0) == 100.0


def test_structural_violation_caps_the_score():
    """One untagged industry row leaks to every tenant; the cap says so."""
    assert tagging_score(1000, 1, 0) == 50.0


def test_integrity_violations_scale_linearly_without_cap():
    assert tagging_score(100, 0, 10) == 90.0


def test_tagging_no_rows_is_none():
    assert tagging_score(0, 0, 0) is None


def test_tagging_blends_label_f1():
    score = tagging_score(100, 0, 0, label_precision=0.5, label_recall=0.5)
    assert score == pytest.approx(0.6 * 100 + 0.4 * 50)


# ── freshness / composite ─────────────────────────────────────────────────────

def test_freshness():
    assert freshness_score(8, 10) == 80.0
    assert freshness_score(0, 0) is None


def test_composite_ignores_unmeasured():
    s = Subscores(completeness=100.0, accuracy=None, authority=50.0)
    assert composite_score(s) == 75.0


def test_composite_all_none():
    assert composite_score(Subscores()) is None


# ── readiness gate ────────────────────────────────────────────────────────────

def _good() -> Subscores:
    return Subscores(
        completeness=95.0, accuracy=100.0, authority=90.0, freshness=95.0, tagging=100.0
    )


def test_ready_when_everything_clears():
    r = evaluate_readiness(
        _good(), focused_keys_complete=True, open_critical_findings=0, golden_fact_count=12
    )
    assert r.status == READY
    assert r.ready
    assert r.blocking == []


def test_unmeasured_accuracy_can_never_be_ready():
    """The whole point: silence is not a pass."""
    s = _good()
    s.accuracy = None
    r = evaluate_readiness(
        s, focused_keys_complete=True, open_critical_findings=0, golden_fact_count=0
    )
    assert r.status == DEGRADED
    assert any("unverified" in b for b in r.blocking)


def test_too_few_golden_facts_blocks_ready():
    r = evaluate_readiness(
        _good(), focused_keys_complete=True, open_critical_findings=0, golden_fact_count=3
    )
    assert r.status != READY


def test_missing_focused_keys_blocks_ready():
    r = evaluate_readiness(
        _good(), focused_keys_complete=False, open_critical_findings=0, golden_fact_count=12
    )
    assert r.status != READY
    assert any("industry-critical" in b for b in r.blocking)


def test_open_critical_finding_blocks_ready():
    r = evaluate_readiness(
        _good(), focused_keys_complete=True, open_critical_findings=2, golden_fact_count=12
    )
    assert r.status != READY
    assert any("critical" in b for b in r.blocking)


def test_zero_accuracy_forces_not_ready_even_with_high_completeness():
    """A critical golden failure zeroed accuracy; completeness must not rescue it."""
    s = _good()
    s.accuracy = 0.0
    r = evaluate_readiness(
        s, focused_keys_complete=True, open_critical_findings=0, golden_fact_count=12
    )
    assert r.status == NOT_READY


def test_low_completeness_is_not_ready_not_degraded():
    s = _good()
    s.completeness = 40.0
    r = evaluate_readiness(
        s, focused_keys_complete=True, open_critical_findings=0, golden_fact_count=12
    )
    assert r.status == NOT_READY


def test_degraded_band():
    s = _good()
    s.completeness = 80.0
    r = evaluate_readiness(
        s, focused_keys_complete=True, open_critical_findings=0, golden_fact_count=12
    )
    assert r.status == DEGRADED
