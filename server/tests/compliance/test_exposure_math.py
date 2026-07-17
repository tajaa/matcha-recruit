"""compute_exposure — what an open issue actually costs. Pure, no DB.

`per_violation` and `annual_cap` had been carried on every penalty block since
they were seeded and read by nothing: the old math was a flat sum, so a
per-employee fine at a 120-person plant counted once. These pin the multiplier,
the clamp, and the uninsurable subset a broker reads.
"""
from app.core.models.compliance import RiskIssue, RiskPenalty
from app.core.services.compliance_risk import (
    WAGE_LANE_OWNED_KEYS,
    compute_conditional_ceiling,
    compute_exposure,
)


def _issue(**kw):
    pen_fields = {k: kw.pop(k) for k in
                  ("civil_min", "civil_max", "per_violation", "annual_cap") if k in kw}
    base = {"id": "i1", "source": "requirement", "severity": "high", "title": "t"}
    base.update(kw)
    if pen_fields:
        base["penalty"] = RiskPenalty(**pen_fields)
    return RiskIssue(**base)


# ── the basics that must not regress ────────────────────────────────────────

def test_no_penalty_contributes_nothing():
    lo, hi, unq, unins = compute_exposure([_issue()])
    assert (lo, hi, unq, unins) == (0, 0, 0, 0)


def test_a_penalty_with_no_numbers_is_counted_as_unquantified():
    """The statute has a penalty but names no figure — that's a known unknown,
    not a zero."""
    lo, hi, unq, _ = compute_exposure([_issue(civil_min=None, civil_max=None)])
    assert (lo, hi, unq) == (0, 0, 1)


def test_a_zero_floor_is_a_real_bound_not_a_missing_value():
    """"Up to $50,000" means the floor is $0. A falsy-0 check would borrow the
    max and report a $50k minimum."""
    lo, hi, _, _ = compute_exposure([_issue(civil_min=0, civil_max=50_000)])
    assert lo == 0
    assert hi == 50_000


def test_a_lone_max_fills_the_floor_and_vice_versa():
    lo, hi, _, _ = compute_exposure([_issue(civil_min=None, civil_max=900)])
    assert (lo, hi) == (900, 900)
    lo, hi, _, _ = compute_exposure([_issue(civil_min=700, civil_max=None)])
    assert (lo, hi) == (700, 700)


def test_issues_sum():
    lo, hi, _, _ = compute_exposure([
        _issue(civil_min=100, civil_max=200),
        _issue(civil_min=50, civil_max=75),
    ])
    assert (lo, hi) == (150, 275)


# ── per_violation: the multiplier that was ignored ──────────────────────────

def test_per_violation_multiplies_by_the_violation_count():
    lo, hi, _, _ = compute_exposure([
        _issue(civil_min=1_190, civil_max=16_550, per_violation=True, violation_count=120),
    ])
    assert lo == 1_190 * 120
    assert hi == 16_550 * 120


def test_a_non_per_violation_penalty_never_multiplies():
    """A flat fine is a flat fine regardless of how many people it touched."""
    lo, hi, _, _ = compute_exposure([
        _issue(civil_min=1_000, civil_max=5_000, per_violation=False, violation_count=50),
    ])
    assert (lo, hi) == (1_000, 5_000)


def test_per_violation_with_no_count_stays_at_1x():
    """Under-counting beats inventing a multiplier we can't evidence."""
    lo, hi, _, _ = compute_exposure([
        _issue(civil_min=1_000, civil_max=5_000, per_violation=True, violation_count=None),
    ])
    assert (lo, hi) == (1_000, 5_000)


def test_a_zero_or_negative_count_cannot_erase_the_penalty():
    for n in (0, -3):
        lo, hi, _, _ = compute_exposure([
            _issue(civil_min=1_000, civil_max=5_000, per_violation=True, violation_count=n),
        ])
        assert (lo, hi) == (1_000, 5_000)


# ── annual_cap: the clamp that was ignored ──────────────────────────────────

def test_annual_cap_clamps_the_multiplied_figure():
    """HIPAA's per-violation tier runs to $2.07M and its annual cap is $2.07M;
    without the clamp 120 violations produce a number no regulator could impose."""
    lo, hi, _, _ = compute_exposure([
        _issue(civil_min=137, civil_max=2_067_813, per_violation=True,
               violation_count=120, annual_cap=2_067_813),
    ])
    assert hi == 2_067_813
    assert lo == 137 * 120  # the floor is nowhere near the cap


def test_annual_cap_clamps_the_floor_too_when_it_bites():
    lo, hi, _, _ = compute_exposure([
        _issue(civil_min=1_000, civil_max=9_000, per_violation=True,
               violation_count=100, annual_cap=5_000),
    ])
    assert (lo, hi) == (5_000, 5_000)


def test_no_cap_means_no_clamp():
    lo, hi, _, _ = compute_exposure([
        _issue(civil_min=100, civil_max=1_000, per_violation=True,
               violation_count=10, annual_cap=None),
    ])
    assert (lo, hi) == (1_000, 10_000)


# ── the uninsurable subset (what a broker actually reads) ───────────────────

def test_a_sourced_uninsurable_key_lands_in_the_uninsurable_bucket():
    _, hi, _, unins = compute_exposure([
        _issue(civil_min=100, civil_max=5_000, regulation_key="state_minimum_wage"),
    ])
    assert unins == hi == 5_000


def test_an_unsourced_key_never_inflates_the_uninsurable_number():
    """`review` is not `uninsurable`. Quietly counting unsourced keys would
    overstate the untransferred exposure on a broker's submission."""
    _, hi, _, unins = compute_exposure([
        _issue(civil_min=100, civil_max=5_000, regulation_key="key_we_never_sourced"),
    ])
    assert hi == 5_000
    assert unins == 0


def test_an_issue_with_no_regulation_key_is_not_uninsurable():
    _, _, _, unins = compute_exposure([_issue(civil_min=100, civil_max=5_000)])
    assert unins == 0


def test_a_partial_key_is_excluded_from_the_uninsurable_bucket():
    """harassment training drags an INSURED loss (the EPLI claim) behind it —
    it is not untransferred exposure."""
    _, _, _, unins = compute_exposure([
        _issue(civil_min=100, civil_max=5_000,
               regulation_key="harassment_prevention_training"),
    ])
    assert unins == 0


def test_uninsurable_is_a_subset_of_total_not_an_addition():
    issues = [
        _issue(id="a", civil_min=100, civil_max=1_000, regulation_key="state_minimum_wage"),
        _issue(id="b", civil_min=200, civil_max=2_000, regulation_key="key_we_never_sourced"),
    ]
    _, hi, _, unins = compute_exposure(issues)
    assert hi == 3_000
    assert unins == 1_000
    assert unins <= hi


# ── lane ownership: the wage keys must not be counted twice ─────────────────

def test_the_wage_lane_owns_every_key_the_wage_derivations_produce():
    """The requirement lane derives status for these (coverage needs it) but must
    not emit issues for them — the wage lane already emits one PER EMPLOYEE. Both
    lanes carry the same penalty block, so a key in both double-counts exposure.

    Read from compliance_status so adding a wage derivation without claiming it
    here fails loudly instead of silently doubling a customer's exposure."""
    from app.core.services.compliance_status import DERIVATIONS, _derive_exempt_salary, _derive_minimum_wage

    wage_derived = {
        k for k, d in DERIVATIONS.items()
        if d.fn in (_derive_minimum_wage, _derive_exempt_salary)
    }
    assert wage_derived == set(WAGE_LANE_OWNED_KEYS), (
        "a wage-family derivation is not claimed by WAGE_LANE_OWNED_KEYS — it "
        "would be emitted by both lanes and counted twice"
    )


def test_non_wage_derivations_are_not_claimed_by_the_wage_lane():
    """The requirement lane must still own everything the wage lane can't see."""
    assert "harassment_prevention_training" not in WAGE_LANE_OWNED_KEYS
    assert "injury_illness_recordkeeping" not in WAGE_LANE_OWNED_KEYS


# ── conditional ceiling: the price of what we have NOT established ──────────

def test_a_confirmed_violation_is_not_in_the_ceiling():
    """It's priced as CONFIRMED exposure; counting it twice would inflate both."""
    ceiling, count = compute_conditional_ceiling([
        {"status": "non_compliant", "civil_penalty_max": 5_000},
    ])
    assert (ceiling, count) == (0, 0)


def test_a_proven_compliant_requirement_has_no_ceiling():
    ceiling, count = compute_conditional_ceiling([
        {"status": "compliant", "civil_penalty_max": 9_000},
    ])
    assert (ceiling, count) == (0, 0)


def test_unknown_and_never_evaluated_both_count():
    """A row with no status row at all (None) is exactly as unproven as one
    explicitly marked unknown."""
    ceiling, count = compute_conditional_ceiling([
        {"status": None, "civil_penalty_max": 1_000},
        {"status": "unknown", "civil_penalty_max": 2_000},
    ])
    assert (ceiling, count) == (3_000, 2)


def test_in_progress_still_counts_as_unproven():
    ceiling, count = compute_conditional_ceiling([
        {"status": "in_progress", "civil_penalty_max": 4_000},
    ])
    assert (ceiling, count) == (4_000, 1)


def test_an_unpriced_unknown_is_counted_but_adds_no_dollars():
    """The count is the honest part: we know we haven't checked, and we can't
    say what it would cost."""
    ceiling, count = compute_conditional_ceiling([
        {"status": "unknown", "civil_penalty_max": None},
    ])
    assert (ceiling, count) == (0, 1)


def test_the_ceiling_never_multiplies_by_headcount():
    """per_violation needs a violation count and we have not established a
    violation at all — a multiplier here invents a scary number from nothing.
    The signature takes no count, which is the enforcement."""
    ceiling, _ = compute_conditional_ceiling([
        {"status": "unknown", "civil_penalty_max": 1_190},
    ])
    assert ceiling == 1_190


def test_nothing_unproven_is_a_zero_ceiling():
    assert compute_conditional_ceiling([]) == (0, 0)


# ── provenance: a figure must be able to answer "says who?" ─────────────────

def test_a_grounded_block_carries_its_citation_and_link():
    """The UI shows the citation only when `grounded`. If the builder drops these
    the figure silently becomes an unsourced assertion again — which is the whole
    condition this work exists to end."""
    from app.core.services.compliance_risk import _risk_penalty

    p = _risk_penalty({
        "civil_penalty_max": 16_550.0,
        "per_violation": True,
        "enforcing_agency": "OSHA",
        "citation": "29 CFR 1903.15(d)",
        "source_url": "https://www.ecfr.gov/current/title-29/section-1903.15",
        "effective_date": "2025-01-15",
        "grounding": "grounded",
    })
    assert p.grounded is True
    assert p.citation == "29 CFR 1903.15(d)"
    assert p.source_url.startswith("https://www.ecfr.gov/current/")
    assert p.effective_date == "2025-01-15"
    assert p.civil_max == 16_550.0


def test_a_model_recalled_block_is_not_dressed_as_grounded():
    """1,023 rows look exactly like this — figures with no source. They must
    report grounded=False so the UI shows no citation rather than implying one."""
    from app.core.services.compliance_risk import _risk_penalty

    p = _risk_penalty({
        "civil_penalty_max": 16_131.0,
        "enforcing_agency": "OSHA",
        "summary": "OSHA penalties apply.",
    })
    assert p.grounded is False
    assert p.citation is None
    assert p.source_url is None


def test_the_source_url_is_never_the_xml_api_endpoint():
    """A person following the citation needs the eCFR page. body_source_url is
    the versioner API we fetch XML from — a snapshot-dated machine endpoint that
    renders as a wall of markup."""
    from app.core.services.compliance_risk import _risk_penalty

    p = _risk_penalty({
        "civil_penalty_max": 16_550.0,
        "citation": "29 CFR 1903.15(d)",
        "source_url": "https://www.ecfr.gov/current/title-29/section-1903.15",
        "grounding": "grounded",
    })
    assert "api/versioner" not in (p.source_url or "")
    assert ".xml" not in (p.source_url or "")


def test_no_penalty_block_yields_no_penalty():
    from app.core.services.compliance_risk import _risk_penalty
    assert _risk_penalty(None) is None
    assert _risk_penalty({}) is None
