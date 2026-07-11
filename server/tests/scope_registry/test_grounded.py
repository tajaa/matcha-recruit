"""Grounded extraction pure core — corpus builder + citation gate. No DB, no AI."""
from app.core.services.scope_registry.grounded import (
    build_grounded_corpus,
    validate_penalty_citations,
    validate_requirement_citations,
)


def _item(item_id, citation, body, heading="h"):
    return {"item_id": item_id, "citation": citation, "heading": heading, "body_text": body}


def test_corpus_empty_input():
    corpus, index = build_grounded_corpus([])
    assert corpus == "" and index == {}


def test_corpus_stable_ids_and_index():
    items = [_item("i1", "29 CFR 541.600", "Salary is $844/week."),
             _item("i2", "29 USC 213", "Exemptions authorized.")]
    corpus, index = build_grounded_corpus(items)
    assert "[S1] 29 CFR 541.600 — h" in corpus
    assert "$844/week" in corpus
    assert index["S1"] == {"item_id": "i1", "citation": "29 CFR 541.600"}
    assert index["S2"]["citation"] == "29 USC 213"


def test_corpus_excludes_bodyless_items():
    items = [_item("i1", "A", ""), _item("i2", "B", "  "), _item("i3", "C", "real text")]
    corpus, index = build_grounded_corpus(items)
    assert list(index) == ["S1"]                 # only the one with body
    assert index["S1"]["citation"] == "C"


def test_corpus_per_item_truncation():
    items = [_item("i1", "A", "x" * 100)]
    corpus, index = build_grounded_corpus(items, per_item_cap=10)
    assert "x" * 10 in corpus and "x" * 11 not in corpus


def test_corpus_total_cap_stops_adding():
    items = [_item(f"i{n}", f"C{n}", "y" * 50) for n in range(10)]
    corpus, index = build_grounded_corpus(items, per_item_cap=50, total_cap=120)
    # first couple fit, then it stops — far fewer than 10 full blocks
    assert len(index) < 10
    assert "omitted" in corpus


def test_validate_drops_unknown_ids():
    index = {"S1": {"item_id": "i1", "citation": "29 CFR 541.600"}}
    reqs = [{"title": "salary", "cited_sources": ["S1", "S9"]}]
    out, dropped = validate_requirement_citations(reqs, index)
    assert dropped == ["S9"]
    assert out[0]["grounded"] is True
    assert out[0]["grounded_citations"] == ["29 CFR 541.600"]


def test_validate_no_valid_ids_is_ungrounded():
    index = {"S1": {"item_id": "i1", "citation": "X"}}
    reqs = [{"title": "t", "cited_sources": ["S7"]}]
    out, dropped = validate_requirement_citations(reqs, index)
    assert out[0]["grounded"] is False
    assert out[0]["grounded_citations"] == []
    assert dropped == ["S7"]


def test_validate_tolerates_bracketed_string_and_junk():
    index = {"S1": {"item_id": "i1", "citation": "X"}, "S2": {"item_id": "i2", "citation": "Y"}}
    reqs = [
        {"cited_sources": "[S1], [S2]"},   # string form
        {"cited_sources": None},           # missing
        {"cited_sources": 42},             # junk type
    ]
    out, _ = validate_requirement_citations(reqs, index)
    assert out[0]["grounded"] is True and set(out[0]["grounded_citations"]) == {"X", "Y"}
    assert out[1]["grounded"] is False
    assert out[2]["grounded"] is False


def test_validate_empty_index():
    reqs = [{"cited_sources": ["S1"]}]
    out, dropped = validate_requirement_citations(reqs, None)
    assert out[0]["grounded"] is False and dropped == ["S1"]


# ── validate_penalty_citations (WS2) ─────────────────────────────────────────

_IDX = {"S1": {"item_id": "i1", "citation": "29 CFR 541.600"},
        "S2": {"item_id": "i2", "citation": "29 CFR 1903.15"}}


def test_penalty_grounded_on_valid_id():
    reqs = [{"penalties": {"summary": "up to $16,131", "civil_penalty_max": 16131,
                           "cited_sources": ["S2"]}}]
    out, dropped = validate_penalty_citations(reqs, _IDX, verified_date="2026-07-11")
    p = out[0]["penalties"]
    assert p["grounding"] == "grounded"
    assert p["grounded_citations"] == ["29 CFR 1903.15"]
    assert p["verified_date"] == "2026-07-11"
    assert "cited_sources" not in p          # corpus-run-local, popped
    assert dropped == []


def test_penalty_ungrounded_when_ids_absent():
    reqs = [{"penalties": {"summary": "fines", "civil_penalty_max": 500,
                           "cited_sources": ["S9"]}}]
    out, dropped = validate_penalty_citations(reqs, _IDX)
    assert out[0]["penalties"]["grounding"] == "ungrounded"
    assert "grounded_citations" not in out[0]["penalties"]
    assert dropped == ["S9"]


def test_penalty_no_cited_sources_is_ungrounded():
    reqs = [{"penalties": {"summary": "fines", "enforcing_agency": "OSHA"}}]
    out, _ = validate_penalty_citations(reqs, _IDX)
    assert out[0]["penalties"]["grounding"] == "ungrounded"


def test_missing_penalties_untouched():
    reqs = [{"regulation_key": "x"}]
    out, dropped = validate_penalty_citations(reqs, _IDX)
    assert "penalties" not in out[0] and dropped == []


def test_non_dict_penalties_untouched():
    reqs = [{"penalties": "n/a"}, {"penalties": None}]
    out, _ = validate_penalty_citations(reqs, _IDX)
    assert out[0]["penalties"] == "n/a"
    assert out[1]["penalties"] is None


def test_insubstantive_penalties_stripped_to_none():
    # a grounding-only shell (or all-null) must not persist — guards the upsert's
    # any(penalties.values()) check.
    reqs = [{"penalties": {"grounding": "x", "grounded_citations": []}},
            {"penalties": {"civil_penalty_max": None, "summary": None}}]
    out, _ = validate_penalty_citations(reqs, _IDX)
    assert out[0]["penalties"] is None
    assert out[1]["penalties"] is None


def test_penalty_independent_of_req_grounded_flag():
    # a value-grounded req can carry ungrounded penalties (different section).
    reqs = [{"grounded": True, "cited_sources": ["S1"],
             "penalties": {"summary": "recalled fine", "cited_sources": ["S9"]}}]
    out, _ = validate_penalty_citations(reqs, _IDX)
    assert out[0]["penalties"]["grounding"] == "ungrounded"
