"""Pure aggregation for the gap-surface engine bridge. No DB."""
from app.core.services.scope_registry.gap_surfaces import (
    aggregate_company_coordinates,
    cell_coverage,
)


def _item(key, citation="29 CFR 1910.1"):
    return {"regulation_key": key, "citation": citation}


def _coord(state="CA", city=None, *, resolved=True, definitive=True, partial=False,
           codified=(), uncodified=(), provisional=0, unmodeled=()):
    return {
        "state": state, "city": city, "resolved": resolved,
        "engine_definitive": definitive,
        "engine_partial": partial,
        "codified": list(codified),
        "uncodified": list(uncodified),
        "counts": {"provisional": provisional},
        "unmodeled": list(unmodeled),
    }


# ── aggregate_company_coordinates ──────────────────────────────────────────


def test_empty_is_bank_full_coverage():
    agg = aggregate_company_coordinates([])
    assert agg["coverage_source"] == "bank"
    assert agg["counts"]["locations"] == 0
    assert agg["coverage_pct"] == 100  # zero-denominator convention


def test_all_definitive_no_degrade_is_engine():
    agg = aggregate_company_coordinates([
        _coord("CA", codified=[_item("minimum_wage"), _item("overtime", "b")]),
        _coord("CA", city="Los Angeles", codified=[_item("overtime", "b")]),
    ])
    assert agg["coverage_source"] == "engine"
    # key union dedupes; item counts sum per coordinate (per-chain facts)
    assert agg["codified_keys"] == ["minimum_wage", "overtime"]
    assert agg["counts"]["codified"] == 3
    assert agg["gate"] == {"total": 2, "engine": 2, "partial": 0, "fallback": 0}


def test_one_non_definitive_falls_back_to_bank():
    agg = aggregate_company_coordinates([
        _coord("CA", definitive=True, codified=[_item("minimum_wage")]),
        _coord("TX", definitive=False),
    ])
    assert agg["coverage_source"] == "bank"
    assert agg["gate"] == {"total": 2, "engine": 1, "partial": 0, "fallback": 1}


def test_partial_coordinate_renders_engine_partial_not_bank():
    """A confirmed-but-incompletely-classified chain yields a FLOOR, not nothing:
    the keys it reports really are in scope, unclassified items may add more.
    Falling all the way back to the bank here is what made the overlay dead
    weight while the federal index sat far from fully classified."""
    agg = aggregate_company_coordinates([
        _coord("CA", definitive=False, partial=True, codified=[_item("minimum_wage")]),
    ])
    assert agg["coverage_source"] == "engine_partial"
    assert agg["gate"] == {"total": 1, "engine": 0, "partial": 1, "fallback": 0}
    assert agg["coordinates"][0]["coverage_source"] == "engine_partial"


def test_partial_plus_definitive_is_partial_overall():
    agg = aggregate_company_coordinates([
        _coord("CA", definitive=True, codified=[_item("minimum_wage")]),
        _coord("NY", definitive=False, partial=True, codified=[_item("overtime", "b")]),
    ])
    assert agg["coverage_source"] == "engine_partial"


def test_partial_plus_unknown_still_falls_back_to_bank():
    """A coordinate with NO engine verdict at all is unknown footprint — a
    partial verdict elsewhere can't speak for it."""
    agg = aggregate_company_coordinates([
        _coord("CA", definitive=False, partial=True, codified=[_item("minimum_wage")]),
        _coord("TX", definitive=False, partial=False),
    ])
    assert agg["coverage_source"] == "bank"


def test_partial_with_degraded_coordinate_falls_back_to_bank():
    agg = aggregate_company_coordinates([
        _coord("CA", definitive=False, partial=True, codified=[_item("minimum_wage")],
               unmodeled=[{"kind": "city", "value": "Nowhere"}]),
    ])
    assert agg["coverage_source"] == "bank"


def test_degraded_coordinate_forces_bank():
    # A resolved coordinate with an unmodeled (unknown city) entry is uncertain.
    agg = aggregate_company_coordinates([
        _coord("CA", codified=[_item("minimum_wage")],
               unmodeled=[{"kind": "city", "value": "Nowhere"}]),
    ])
    assert agg["coverage_source"] == "bank"
    assert agg["degraded"] is True
    assert len(agg["unmodeled_coordinates"]) == 1


def test_failed_resolve_forces_bank_and_is_counted():
    # A location whose resolve raised must degrade the verdict — a "grounded"
    # verdict may never silently omit part of the company's footprint.
    agg = aggregate_company_coordinates([
        _coord("CA", codified=[_item("minimum_wage")]),
        _coord("TX", resolved=False, definitive=False),
    ])
    assert agg["coverage_source"] == "bank"
    assert agg["degraded"] is True
    assert agg["counts"]["locations"] == 1
    assert agg["counts"]["locations_failed"] == 1
    assert agg["gate"] == {"total": 2, "engine": 1, "partial": 0, "fallback": 1}


def test_cross_chain_gap_is_retained():
    # 'overtime' codified in CA's chain but uncodified in TX's chain: the TX
    # catalog row is genuinely missing, so the gap must NOT be dropped just
    # because another jurisdiction covers the same key.
    agg = aggregate_company_coordinates([
        _coord("CA", codified=[_item("overtime")]),
        _coord("TX", uncodified=[_item("overtime"), _item("meal_break", "c2")]),
    ])
    keys = {u["regulation_key"] for u in agg["uncodified"]}
    assert keys == {"overtime", "meal_break"}
    assert agg["counts"]["uncodified"] == 2
    # each gap is annotated with the chain it belongs to
    assert all(u["state"] == "TX" for u in agg["uncodified"])


def test_coverage_pct_is_item_unit_consistent():
    # 2 codified items vs 2 uncodified items → 50%, same units both sides
    # (never a key-union numerator against a per-citation denominator).
    agg = aggregate_company_coordinates([
        _coord("CA",
               codified=[_item("a", "c1"), _item("a", "c2")],
               uncodified=[_item("b", "c3"), _item(None, "c4")]),
    ])
    assert agg["counts"]["codified"] == 2
    assert agg["counts"]["uncodified"] == 2
    assert agg["coverage_pct"] == 50


def test_provisional_summed_per_coordinate():
    # provisional is chain-wide per coordinate; the caller feeds one entry per
    # UNIQUE coordinate, so identical locations don't multiply-count it.
    agg = aggregate_company_coordinates([
        _coord("CA", provisional=4),
        _coord("TX", provisional=1),
    ])
    assert agg["counts"]["provisional"] == 5


def test_only_failed_coordinates_is_bank():
    agg = aggregate_company_coordinates([_coord("CA", resolved=False, definitive=False)])
    assert agg["coverage_source"] == "bank"
    assert agg["counts"]["locations"] == 0
    assert agg["counts"]["locations_failed"] == 1


# ── cell_coverage ──────────────────────────────────────────────────────────


def test_cell_coverage_intersection_and_gap():
    cov = cell_coverage({"a", "b", "c"}, {"b", "c", "z"})
    assert cov["expected"] == 3
    assert cov["codified"] == 2          # b, c
    assert cov["to_codify"] == 1         # a
    assert cov["to_codify_keys"] == ["a"]


def test_cell_coverage_empty_present_all_to_codify():
    cov = cell_coverage({"a", "b"}, set())
    assert cov["codified"] == 0
    assert cov["to_codify"] == 2


def test_cell_coverage_handles_none():
    cov = cell_coverage(None, None)
    assert cov == {"expected": 0, "codified": 0, "to_codify": 0, "to_codify_keys": []}
