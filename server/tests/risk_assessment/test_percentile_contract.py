"""Monte Carlo's low/high are PERCENTILES, not statutory bounds. No DB.

The sharp edge of unifying the exposure engines. Two things both called
"low/high" mean different quantities:

  * `risk_assessment` line_items — the 10th and 90th PERCENTILES of a loss
    distribution. `monte_carlo_service._lognormal_params` fits mu/sigma from them
    via Z_90 and draws from it.
  * `compliance_risk` penalties — statutory BOUNDS. $16,550 is a ceiling a
    regulator MAY impose under 29 CFR 1903.15(d)(3); it is not "90% of outcomes
    fall below this".

Feeding bounds into that fit produces a confident, wrong distribution on a page
that renders exceedance curves and percentiles — the kind of error that looks
like rigour. These pin the boundary so a future "let's just reuse the penalty
numbers here" cannot land quietly.
"""
import math

from app.matcha.services.monte_carlo_service import Z_90, _lognormal_params


def test_low_high_are_treated_as_the_10th_and_90th_percentiles():
    """Not min/max. The fit places them at ±Z_90 sigma around mu, so ~10% of
    draws fall BELOW low and ~10% ABOVE high — a statutory maximum interpreted
    this way would be exceeded by 10% of simulated outcomes, which for a
    regulator's ceiling is nonsense."""
    low, high = 1_000.0, 100_000.0
    mu, sigma = _lognormal_params(low, high)
    assert mu == (math.log(low) + math.log(high)) / 2
    assert sigma == (math.log(high) - math.log(low)) / (2 * Z_90)
    # The distribution genuinely extends beyond both ends.
    assert math.exp(mu + 3 * sigma) > high
    assert math.exp(mu - 3 * sigma) < low


def test_a_statutory_ceiling_pair_degenerates_rather_than_modelling():
    """compliance_risk reports a single-figure penalty as min==max (most statutes
    say only "shall not exceed $X"). Handing that to the fit yields a spike, not
    a loss model — evidence the shapes are not interchangeable."""
    mu, sigma = _lognormal_params(16_550.0, 16_550.0)
    assert sigma == 0.1  # the degenerate branch
    assert math.isclose(math.exp(mu), 16_550.0, rel_tol=1e-9)


def test_zero_and_negative_bounds_are_refused():
    """A $0 statutory floor ("up to $X") is a real bound in compliance_risk and
    meaningless as a 10th percentile — log(0) is undefined. The guard is what
    stops a bound leaking in and raising."""
    assert _lognormal_params(0.0, 50_000.0) == (0.0, 0.0)
    assert _lognormal_params(-1.0, 50_000.0) == (0.0, 0.0)


def test_the_exposure_engines_do_not_share_a_field_name_by_accident():
    """compliance_risk's RiskPenalty says civil_min/civil_max; risk_assessment's
    line_items say low/high. Different names for different quantities is the only
    thing stopping a well-meaning merge, so assert the shapes stayed apart."""
    from app.core.models.compliance import RiskPenalty

    penalty_fields = set(RiskPenalty.model_fields)
    assert "civil_min" in penalty_fields and "civil_max" in penalty_fields
    # If these ever appear on RiskPenalty, someone is about to pipe statutory
    # bounds into the percentile fit.
    assert "low" not in penalty_fields
    assert "high" not in penalty_fields


def test_penalty_facts_exposes_bounds_under_an_unmistakable_name():
    """penalty_facts is the shared source. Its tier figures are min_usd/max_usd —
    never low/high — so a caller cannot pass them to _lognormal_params by
    autocomplete."""
    from app.core.services.penalty_facts import PenaltyTierFact

    fields = PenaltyTierFact.__dataclass_fields__
    assert "min_usd" in fields and "max_usd" in fields
    assert "low" not in fields and "high" not in fields
