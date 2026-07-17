"""Pure-logic tests for IR statute grounding (no DB, no network).

Covers the incident→category heuristic, the mapping narrowing, and the copilot
context serializer. The DB-backed `get_incident_statutes` (which calls
`compliance_service.get_location_requirements`) is exercised manually on
dev-remote — see the plan's verification section.
"""

from app.matcha.services import ir_statute_grounding as g


def _statutes():
    return [
        {"requirement_id": "1", "state": "CA", "category": "workplace_safety",
         "title": "IIPP", "description": "", "statute_citation": "8 CCR 3203", "source_url": None},
        {"requirement_id": "2", "state": "CA", "category": "workers_comp",
         "title": "Mandatory coverage", "description": "", "statute_citation": None, "source_url": None},
        {"requirement_id": "3", "state": "CA", "category": "chemical_safety",
         "title": "HazCom", "description": "", "statute_citation": "8 CCR 5194", "source_url": None},
    ]


def test_implicated_categories_from_incident_type():
    cats = g._implicated_categories({"incident_type": "injury", "description": "cut hand"})
    assert cats == frozenset({"workplace_safety", "workers_comp"})


def test_implicated_categories_keyword_in_description():
    cats = g._implicated_categories({"incident_type": "other", "description": "chemical spill in bay 3"})
    assert "chemical_safety" in cats and "process_safety" in cats


def test_implicated_categories_no_hit_defaults_to_all_safety():
    cats = g._implicated_categories({"incident_type": "misc", "description": "nothing keyworded"})
    assert cats == g.IR_SAFETY_CATEGORIES


def test_map_narrows_to_implicated():
    # injury → workplace_safety + workers_comp; chemical_safety statute dropped.
    matches = g.map_incident_to_statutes({"incident_type": "injury"}, _statutes())
    cats = {m["category"] for m in matches}
    assert cats == {"workplace_safety", "workers_comp"}
    assert all(m["relevance_reason"] for m in matches)


def test_map_empty_statutes():
    assert g.map_incident_to_statutes({"incident_type": "injury"}, []) == []


def test_serialize_empty():
    assert g.serialize_statute_context([]) == ""


def test_serialize_renders_citation_bracket():
    out = g.serialize_statute_context(_statutes())
    assert "8 CCR 3203" in out
    assert out.count("\n") == 2  # three lines
    # uncited row has no trailing bracket
    assert "Mandatory coverage" in out


def test_serialize_respects_max():
    out = g.serialize_statute_context(_statutes(), max_items=1)
    assert out.count("\n") == 0
