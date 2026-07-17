"""Pure-logic tests for IR statute grounding (no DB, no network).

Covers the incident→category heuristic (keyword hits over free text +
category_data; incident_type gates the no-keyword fallback), the mapping
narrowing, and the copilot context serializer. The DB-backed
`get_incident_statutes` is exercised manually on dev-remote — see the plan.
"""

from app.matcha.services import ir_statute_grounding as g


def _statutes():
    return [
        {"requirement_id": "1", "state": "California", "category": "workplace_safety",
         "title": "IIPP", "description": "", "statute_citation": "8 CCR 3203", "source_url": None},
        {"requirement_id": "2", "state": "California", "category": "workers_comp",
         "title": "Mandatory coverage", "description": "", "statute_citation": None, "source_url": None},
        {"requirement_id": "3", "state": "California", "category": "chemical_safety",
         "title": "HazCom", "description": "", "statute_citation": "8 CCR 5194", "source_url": None},
    ]


def test_keyword_hit_from_description():
    cats = g._implicated_categories({"incident_type": "safety", "description": "employee injury on the line"})
    assert cats == frozenset({"workplace_safety", "workers_comp"})


def test_keyword_hit_from_category_data():
    cats = g._implicated_categories({"incident_type": "safety", "category_data": {"detail": "forklift machine guard removed"}})
    assert "machine_safety" in cats


def test_keyword_hit_independent_of_type():
    # A keyword wins even on a non-safety type (the text is the signal).
    cats = g._implicated_categories({"incident_type": "other", "description": "chemical spill in bay 3"})
    assert "chemical_safety" in cats and "process_safety" in cats


def test_no_keyword_safety_type_defaults_to_all():
    cats = g._implicated_categories({"incident_type": "safety", "description": "slip in bay 3"})
    assert cats == g.IR_SAFETY_CATEGORIES


def test_no_keyword_nonsafety_type_grounds_nothing():
    # A behavioral/harassment incident with no safety keyword implicates no OSHA law.
    assert g._implicated_categories({"incident_type": "behavioral", "description": "verbal dispute"}) == frozenset()


def test_map_narrows_to_implicated():
    matches = g.map_incident_to_statutes({"incident_type": "safety", "description": "injury"}, _statutes())
    cats = {m["category"] for m in matches}
    assert cats == {"workplace_safety", "workers_comp"}  # chemical_safety dropped
    assert all(m["relevance_reason"] for m in matches)


def test_map_nonsafety_no_keyword_returns_empty():
    assert g.map_incident_to_statutes({"incident_type": "behavioral"}, _statutes()) == []


def test_map_empty_statutes():
    assert g.map_incident_to_statutes({"incident_type": "safety", "description": "injury"}, []) == []


def test_serialize_empty():
    assert g.serialize_statute_context([]) == ""


def test_serialize_renders_citation_bracket():
    out = g.serialize_statute_context(_statutes())
    assert "8 CCR 3203" in out
    assert out.count("\n") == 2  # three lines
    assert "Mandatory coverage" in out  # uncited row still listed


def test_serialize_respects_max():
    assert g.serialize_statute_context(_statutes(), max_items=1).count("\n") == 0
