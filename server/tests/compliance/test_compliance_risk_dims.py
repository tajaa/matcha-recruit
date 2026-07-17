"""compliance_risk_dims — the curated table's contract. Pure, no DB.

The table is deliberately partial, so the tests that matter are about what
happens at its edges: an unmapped key must degrade to `review`, and `review`
must never be mistaken for "no exposure" — especially in the uninsurable bucket,
which is the number a broker takes to an underwriter.
"""
import pytest

from app.core.services.compliance_risk_dims import (
    _DIMS,
    dims_payload,
    is_uninsurable,
    risk_dims_for,
    sourced_keys,
)


# ── the review default ──────────────────────────────────────────────────────

def test_an_unmapped_key_degrades_to_review():
    d = risk_dims_for("some_key_we_never_sourced")
    assert d.insurability == "review"
    assert d.detection_mode == "review"
    assert d.sourced is False


def test_no_key_at_all_degrades_to_review():
    for empty in (None, ""):
        assert risk_dims_for(empty).insurability == "review"
        assert risk_dims_for(empty).sourced is False


def test_review_is_never_counted_as_uninsurable():
    """The load-bearing one. Counting unsourced keys as uninsurable would
    inflate the exposure figure a broker hands an underwriter."""
    assert is_uninsurable("some_key_we_never_sourced") is False
    assert is_uninsurable(None) is False


def test_a_sourced_uninsurable_key_counts():
    assert is_uninsurable("state_minimum_wage") is True


def test_a_sourced_partial_key_is_not_uninsurable():
    """harassment training drags an INSURED loss (the EPLI claim) — it must not
    land in the uninsurable bucket."""
    assert risk_dims_for("harassment_prevention_training").insurability == "partial"
    assert is_uninsurable("harassment_prevention_training") is False


# ── table integrity ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", sorted(_DIMS))
def test_every_row_carries_a_citation(key):
    """The rule the table exists under: rows are added only with a real
    citation, never by inference. An uncited row is indistinguishable from a
    guess."""
    d = _DIMS[key]
    assert d.citations, f"{key} has no citation"
    assert all(c.strip() for c in d.citations)
    assert d.sourced is True


@pytest.mark.parametrize("key", sorted(_DIMS))
def test_no_sourced_row_leaves_a_verdict_at_review(key):
    """If we bothered to source it, it must say something."""
    d = _DIMS[key]
    assert d.insurability != "review", f"{key} is sourced but insurability is review"
    assert d.detection_mode != "review", f"{key} is sourced but detection is review"


@pytest.mark.parametrize("key", sorted(_DIMS))
def test_vocabularies_are_respected(key):
    d = _DIMS[key]
    assert d.insurability in ("uninsurable_fine", "insurable", "partial", "review")
    assert d.detection_mode in ("automatic", "complaint", "audit", "litigation", "review")
    assert d.private_right_of_action in (True, False, None)
    assert d.cure_period in (True, False, None)


@pytest.mark.parametrize("key", sorted(_DIMS))
def test_an_uninsurable_verdict_explains_itself(key):
    """A bare 'uninsurable' on a broker deliverable invites the question 'says
    who?'. The note is the answer."""
    d = _DIMS[key]
    if d.insurability in ("uninsurable_fine", "partial"):
        assert d.insurability_note, f"{key} gives an insurability verdict with no rationale"


def test_the_table_covers_the_keys_the_status_layer_can_actually_derive():
    """A derivable key with no dims produces a confirmed violation we can price
    in dollars but can't say anything else about — the exact gap this module
    exists to close."""
    from app.core.services.compliance_status import derivable_keys
    missing = [k for k in derivable_keys() if k not in _DIMS]
    assert not missing, f"derivable but no risk dims: {missing}"


# ── wire shape ──────────────────────────────────────────────────────────────

def test_payload_carries_sourced_so_the_ui_can_say_needs_review():
    unsourced = dims_payload("nope_not_here")
    assert unsourced["sourced"] is False
    assert unsourced["insurability"] == "review"
    assert unsourced["citations"] == []

    sourced = dims_payload("state_minimum_wage")
    assert sourced["sourced"] is True
    assert sourced["insurability"] == "uninsurable_fine"
    assert "29 U.S.C. 216" in sourced["citations"]


def test_payload_citations_are_copied_not_aliased():
    """A caller mutating the payload must not corrupt the module-level table."""
    p = dims_payload("state_minimum_wage")
    p["citations"].append("bogus")
    assert "bogus" not in risk_dims_for("state_minimum_wage").citations


def test_sourced_keys_lists_the_table():
    keys = sourced_keys()
    assert "state_minimum_wage" in keys
    assert keys == sorted(set(keys))
