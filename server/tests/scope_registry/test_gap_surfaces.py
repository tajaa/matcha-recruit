"""Pure aggregation for the gap-surface engine bridge. No DB."""
from app.core.services.scope_registry.gap_surfaces import (
    aggregate_company_coordinates,
    cell_coverage,
)


def _coord(state="CA", city=None, *, resolved=True, definitive=True,
           codified=(), uncodified=(), provisional=0, unmodeled=()):
    return {
        "state": state, "city": city, "resolved": resolved,
        "engine_definitive": definitive,
        "codified_keys": list(codified),
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
        _coord("CA", codified=["minimum_wage", "overtime"]),
        _coord("CA", city="Los Angeles", codified=["overtime"]),
    ])
    assert agg["coverage_source"] == "engine"
    # union dedupes the shared key
    assert agg["codified_keys"] == ["minimum_wage", "overtime"]
    assert agg["counts"]["codified"] == 2
    assert agg["gate"] == {"total": 2, "engine": 2, "fallback": 0}


def test_one_non_definitive_falls_back_to_bank():
    agg = aggregate_company_coordinates([
        _coord("CA", definitive=True, codified=["minimum_wage"]),
        _coord("TX", definitive=False, codified=[]),
    ])
    assert agg["coverage_source"] == "bank"
    assert agg["gate"] == {"total": 2, "engine": 1, "fallback": 1}


def test_degraded_coordinate_forces_bank():
    # A resolved coordinate with an unmodeled (unknown city) entry is uncertain.
    agg = aggregate_company_coordinates([
        _coord("CA", codified=["minimum_wage"],
               unmodeled=[{"kind": "city", "value": "Nowhere"}]),
    ])
    assert agg["coverage_source"] == "bank"
    assert agg["degraded"] is True
    assert len(agg["unmodeled_coordinates"]) == 1


def test_uncodified_dropped_when_codified_elsewhere():
    # 'overtime' is uncodified in TX but codified in CA → not a company gap.
    agg = aggregate_company_coordinates([
        _coord("CA", codified=["overtime"]),
        _coord("TX", uncodified=[{"regulation_key": "overtime", "citation": "x"},
                                 {"regulation_key": "meal_break", "citation": "y"}]),
    ])
    keys = {u["regulation_key"] for u in agg["uncodified"]}
    assert keys == {"meal_break"}
    assert agg["counts"]["uncodified"] == 1


def test_uncodified_deduped_on_key_and_citation():
    agg = aggregate_company_coordinates([
        _coord("CA", uncodified=[{"regulation_key": "k", "citation": "c"}]),
        _coord("NV", uncodified=[{"regulation_key": "k", "citation": "c"}]),
    ])
    assert len(agg["uncodified"]) == 1


def test_coverage_pct_and_provisional():
    agg = aggregate_company_coordinates([
        _coord("CA", codified=["a", "b", "c"], provisional=2,
               uncodified=[{"regulation_key": "d", "citation": "c"}]),
    ])
    # 3 codified / (3 + 1) = 75%
    assert agg["coverage_pct"] == 75
    assert agg["counts"]["provisional"] == 2


def test_unresolved_coordinate_excluded_from_engine_decision():
    # A location whose resolve failed is not counted as engine-definitive nor
    # blocks the engine verdict on its own, but with zero resolved → bank.
    agg = aggregate_company_coordinates([_coord("CA", resolved=False, definitive=False)])
    assert agg["coverage_source"] == "bank"
    assert agg["counts"]["locations"] == 0


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
