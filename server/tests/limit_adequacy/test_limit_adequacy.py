"""Pure tests for the limit-adequacy engine + contract-requirement coercion.
DB build_review is smoke-tested against dev separately."""

from app.matcha.services import limit_adequacy as la
from app.matcha.services import contract_parser as cp

M = 1_000_000


def _line(review, key):
    return {l["key"]: l for l in review["lines"]}[key]


def _contract(name, reqs, **extra):
    return {"name": name, "counterparty": extra.get("counterparty"), "status": "manual",
            "id": extra.get("id", "c1"), "ai_available": False, "requirements": reqs}


# --- normalize_line ---------------------------------------------------------

def test_normalize_line_aliases():
    assert la.normalize_line("CGL") == "gl"
    assert la.normalize_line("Commercial General Liability") == "gl"
    assert la.normalize_line("E&O") == "professional"
    assert la.normalize_line("Umbrella/Excess") == "umbrella"
    assert la.normalize_line("workers' compensation") == "wc"
    assert la.normalize_line("gl") == "gl"
    assert la.normalize_line("nonsense line") is None
    assert la.normalize_line(None) is None


# --- baseline ---------------------------------------------------------------

def test_baseline_scales_with_size_and_venue():
    assert la.recommend_baseline("umbrella", 10, None)["per_occurrence"] == 1 * M
    assert la.recommend_baseline("umbrella", 100, None)["per_occurrence"] == 5 * M
    assert la.recommend_baseline("umbrella", 500, None)["per_occurrence"] == 10 * M
    # severe venue bumps +$5M
    assert la.recommend_baseline("umbrella", 500, "severe")["per_occurrence"] == 15 * M
    # epl scales with headcount
    assert la.recommend_baseline("epl", 10, None)["per_occurrence"] == 1 * M
    assert la.recommend_baseline("epl", 500, None)["per_occurrence"] == 3 * M
    # professional intentionally not floored
    assert la.recommend_baseline("professional", 100, None) is None


# --- analyze: contract shortfall (the headline deliverable) -----------------

def test_contract_shortfall_is_hard_gap():
    carried = [{"line": "gl", "per_occurrence": 1 * M, "aggregate": 2 * M}]
    contracts = [_contract("Acme MSA", [{"line": "General Liability", "per_occurrence": 2 * M}],
                           counterparty="Acme")]
    r = la.analyze(carried, contracts, headcount=100, venue_tier=None)
    gl = _line(r, "gl")
    assert gl["status"] == "shortfall"
    assert "$1M" in gl["gap"] and "$2M" in gl["gap"]
    assert r["summary"]["contract_shortfalls"] == 1


def test_contract_required_but_nothing_carried_is_no_coverage():
    contracts = [_contract("Lease", [{"line": "gl", "per_occurrence": 2 * M}])]
    r = la.analyze([], contracts, headcount=20, venue_tier=None)
    gl = _line(r, "gl")
    assert gl["status"] == "no_coverage"
    assert r["summary"]["contract_shortfalls"] == 1


def test_meets_contract_is_ok():
    carried = [{"line": "gl", "per_occurrence": 5 * M, "aggregate": 10 * M}]
    contracts = [_contract("MSA", [{"line": "gl", "per_occurrence": 2 * M, "aggregate": 4 * M}])]
    r = la.analyze(carried, contracts, headcount=100, venue_tier=None)
    assert _line(r, "gl")["status"] == "ok"
    assert r["summary"]["contract_shortfalls"] == 0


def test_missing_carried_aggregate_is_not_a_shortfall():
    # per-occ meets the contract; the aggregate simply isn't recorded → a data nudge,
    # NOT a hard gap (recording only per-occ must not false-flag every agg-naming line).
    carried = [{"line": "gl", "per_occurrence": 5 * M}]  # no aggregate keyed
    contracts = [_contract("MSA", [{"line": "gl", "per_occurrence": 1 * M, "aggregate": 2 * M}])]
    r = la.analyze(carried, contracts, headcount=100, venue_tier=None)
    gl = _line(r, "gl")
    assert gl["status"] == "ok"
    assert r["summary"]["contract_shortfalls"] == 0
    assert "Aggregate not on file" in (gl["gap"] or "")


def test_missing_carried_per_occurrence_is_a_shortfall():
    # the carried line records only an aggregate; contract requires a per-occ limit →
    # real gap, phrased as "none recorded" rather than implying $0 carried.
    carried = [{"line": "gl", "aggregate": 4 * M}]  # no per_occurrence keyed
    contracts = [_contract("MSA", [{"line": "gl", "per_occurrence": 2 * M}])]
    r = la.analyze(carried, contracts, headcount=100, venue_tier=None)
    gl = _line(r, "gl")
    assert gl["status"] == "shortfall"
    assert "none recorded" in (gl["gap"] or "")
    assert r["summary"]["contract_shortfalls"] == 1


def test_max_required_across_contracts():
    contracts = [
        _contract("A", [{"line": "gl", "per_occurrence": 1 * M}]),
        _contract("B", [{"line": "gl", "per_occurrence": 5 * M}]),
    ]
    r = la.analyze([{"line": "gl", "per_occurrence": 2 * M}], contracts, headcount=50, venue_tier=None)
    gl = _line(r, "gl")
    assert gl["contract_required"]["per_occurrence"] == 5 * M  # highest wins
    assert gl["status"] == "shortfall"
    assert len(gl["contract_sources"]) == 2


# --- analyze: baseline (no contract) ---------------------------------------

def test_baseline_low_when_no_contract():
    # umbrella carried 1M, large employer baseline 10M → directional_low
    carried = [{"line": "umbrella", "per_occurrence": 1 * M}]
    r = la.analyze(carried, [], headcount=500, venue_tier=None)
    u = _line(r, "umbrella")
    assert u["status"] == "directional_low"
    assert r["summary"]["baseline_lows"] == 1


def test_not_carried_when_no_contract_and_nothing_on_file():
    r = la.analyze([], [], headcount=20, venue_tier=None)
    assert _line(r, "cyber")["status"] == "not_carried"
    assert r["summary"]["contract_shortfalls"] == 0


# --- endorsement gaps -------------------------------------------------------

def test_endorsement_gaps_flag_missing_required():
    carried = [{"line": "gl", "per_occurrence": 5 * M, "additional_insured": True}]
    contracts = [_contract("MSA", [{"line": "gl", "per_occurrence": 1 * M,
                                     "additional_insured": True, "waiver_of_subrogation": True}])]
    r = la.analyze(carried, contracts, headcount=100, venue_tier=None)
    gaps = {e["key"] for e in _line(r, "gl")["endorsement_gaps"]}
    assert gaps == {"waiver_of_subrogation"}  # AI satisfied, WOS missing


def test_no_endorsement_gaps_when_all_present():
    carried = [{"line": "gl", "per_occurrence": 5 * M, "additional_insured": True,
                "waiver_of_subrogation": True, "primary_noncontributory": True}]
    contracts = [_contract("MSA", [{"line": "gl", "per_occurrence": 1 * M,
                                     "additional_insured": True, "waiver_of_subrogation": True}])]
    r = la.analyze(carried, contracts, headcount=100, venue_tier=None)
    assert _line(r, "gl")["endorsement_gaps"] == []


# --- contract_parser coercion ----------------------------------------------

def test_coerce_requirements_normalizes_and_drops_unknown():
    payload = {"requirements": [
        {"line": "Commercial General Liability", "per_occurrence": "2000000", "additional_insured": 1},
        {"line": "Pizza Insurance", "per_occurrence": 1000000},  # unknown → dropped
        {"line": "E&O", "aggregate": 3000000},
    ]}
    out = cp._coerce_requirements(payload)
    lines = [r["line"] for r in out]
    assert lines == ["gl", "professional"]
    assert out[0]["per_occurrence"] == 2_000_000.0
    assert out[0]["additional_insured"] is True
    assert out[0]["waiver_of_subrogation"] is False


def test_coerce_handles_garbage():
    assert cp._coerce_requirements({}) == []
    assert cp._coerce_requirements({"requirements": ["nope", 5, None]}) == []


# --- money formatting -------------------------------------------------------

def test_money_format():
    assert la._money(2_000_000) == "$2M"
    assert la._money(1_500_000) == "$1.5M"
    assert la._money(500_000) == "$500K"
    assert la._money(None) == "—"
