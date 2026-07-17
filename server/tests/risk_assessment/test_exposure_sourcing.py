"""Where /app/risk-assessment's dollar figures come from, and admitting it. No DB.

This page prices non-compliance in dollars and has since long before the penalty
work. Its wage model is the BETTER instrument for wage keys — it computes back
pay (shortfall x 2080 x lookback x liquidated damages), not a statutory ceiling.
What it never did was say where its numbers came from, which is how
"The 2024 DOL salary threshold is $43,888" sat two years stale in a string a
customer was asked to act on, while our own catalog said $70,304 for California.
"""
import pytest

from app.matcha.services.risk_assessment_service import (
    _UNSOURCED_REASONS,
    _exempt_threshold_sentence,
    _stamp_sourcing,
)


def _v(state="CA", threshold=70_304.0, **kw):
    base = {"location_state": state, "threshold": threshold,
            "pay_classification": "exempt", "pay_rate": 50_000.0}
    base.update(kw)
    return base


# ── the threshold sentence: name what we actually compared against ──────────

def test_the_sentence_names_the_detected_threshold_not_a_literal():
    """The regression. $43,888 was hardcoded; the row we measured against says
    $70,304. State the latter."""
    s = _exempt_threshold_sentence([_v()])
    assert "$70,304" in s
    assert "43,888" not in s


def test_multiple_states_are_each_named():
    s = _exempt_threshold_sentence([_v("CA", 70_304.0), _v("NY", 62_400.0)])
    assert "CA: $70,304" in s
    assert "NY: $62,400" in s
    assert s.index("CA") < s.index("NY")  # sorted → stable copy across runs


def test_the_highest_threshold_per_state_wins():
    """A city overlay can raise the bar; describe the one they had to clear."""
    s = _exempt_threshold_sentence([_v("CA", 70_304.0), _v("CA", 66_560.0)])
    assert "$70,304" in s
    assert "66,560" not in s


def test_no_threshold_says_nothing_specific_rather_than_guessing():
    s = _exempt_threshold_sentence([_v(threshold=None)])
    assert "$" not in s
    assert "threshold" in s.lower()


def test_an_unnamed_state_does_not_render_an_empty_label():
    s = _exempt_threshold_sentence([_v(state="", threshold=58_656.0)])
    assert "applicable jurisdiction: $58,656" in s
    assert ": $58,656" in s and "  " not in s


def test_empty_violations_do_not_explode():
    assert isinstance(_exempt_threshold_sentence([]), str)


# ── sourcing labels ────────────────────────────────────────────────────────

def test_every_line_item_gets_labelled():
    items = _stamp_sourcing([{"key": "hourly_wage_shortfall"}, {"key": "hipaa_breach_exposure"}])
    assert all("sourced" in i for i in items)


def test_nothing_on_this_page_claims_to_be_statute_sourced_yet():
    """The honest state, and the point of the label. The compliance cockpit can
    cite 29 CFR 1903.15(d)(3) for its $16,550; every figure here is a constant
    someone typed. When that stops being true this test should fail and be
    updated — deliberately."""
    items = _stamp_sourcing([{"key": k} for k in _UNSOURCED_REASONS])
    assert not any(i["sourced"] for i in items)
    assert all(i["unsourced_reason"] for i in items)


def test_an_unknown_key_defaults_to_unsourced():
    """A new line item must not ship silently looking authoritative — guilty
    until it can show its authority."""
    item = _stamp_sourcing([{"key": "some_new_exposure_we_add_later"}])[0]
    assert item["sourced"] is False
    assert "hand-entered" in item["unsourced_reason"]


def test_a_line_item_with_no_key_at_all_is_still_labelled():
    item = _stamp_sourcing([{}])[0]
    assert item["sourced"] is False
    assert item["unsourced_reason"]


def test_stamping_never_overwrites_a_line_that_declares_itself_sourced():
    """When HIPAA's 45 CFR 102.3 parser lands, that line sets sourced=True and
    the stamp must leave it and its citation alone."""
    item = _stamp_sourcing([
        {"key": "hipaa_breach_exposure", "sourced": True, "citation": "45 CFR 102.3"},
    ])[0]
    assert item["sourced"] is True
    assert "unsourced_reason" not in item
    assert item["citation"] == "45 CFR 102.3"


def test_stamping_is_idempotent():
    once = _stamp_sourcing([{"key": "open_cases"}])
    twice = _stamp_sourcing(once)
    assert twice[0]["unsourced_reason"] == once[0]["unsourced_reason"]


@pytest.mark.parametrize("key", sorted(_UNSOURCED_REASONS))
def test_each_reason_explains_rather_than_hedges(key):
    reason = _UNSOURCED_REASONS[key]
    assert len(reason) > 30, f"{key}'s reason says nothing useful"
    assert reason.rstrip().endswith("."), key


def test_the_reason_map_covers_every_key_monte_carlo_knows():
    """monte_carlo keys off line_item['key']; a key it models but we never label
    is a line that renders unexplained."""
    from app.matcha.services.monte_carlo_service import STOCHASTIC_LAMBDA_OVERRIDES
    for key in STOCHASTIC_LAMBDA_OVERRIDES:
        assert key in _UNSOURCED_REASONS, f"{key} is modelled but unlabelled"
