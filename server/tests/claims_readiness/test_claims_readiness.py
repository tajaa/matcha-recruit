"""Pure tests for claims-readiness packet assembly (DB paths smoke-tested vs dev)."""

from app.matcha.services import claims_readiness as cr


def test_loads_variants():
    assert cr._loads(None) is None
    assert cr._loads({"a": 1}) == {"a": 1}
    assert cr._loads([1, 2]) == [1, 2]
    assert cr._loads("[1,2]") == [1, 2]
    assert cr._loads("not json") is None


def test_fmt_dt_none():
    assert cr._fmt_dt(None) == "—"


def test_incident_html_renders_all_sections():
    data = {
        "incident": {
            "incident_number": "IR-1", "title": "Slip", "incident_type": "safety",
            "severity": "high", "status": "closed", "occurred_at": None, "location": "Dock",
            "description": "desc", "root_cause": "wet floor", "corrective_actions": "mop up",
            "osha_recordable": True, "osha_classification": "fall", "days_away_from_work": 3,
            "days_restricted_duty": 0, "return_to_work_date": None,
        },
        "witnesses": [{"name": "Jane", "statement": "saw it"}],
        "timeline": [{"action": "incident_created", "entity_type": "incident", "details": None, "created_at": None}],
        "documents": [{"filename": "p.jpg", "document_type": "photo", "mime_type": "image/jpeg", "file_size": 10, "created_at": None}],
        "policy_map": {"matches": [{"title": "Safety Policy", "description": "x", "status": "violated"}]},
        "recommendations": {"actions": ["retrain staff"]},
    }
    html = cr._incident_html(data)
    for needle in ["Claims-Readiness", "IR-1", "Jane", "Safety Policy", "wet floor", "mop up", "OSHA recordable", "retrain staff"]:
        assert needle in html, needle


def test_incident_html_handles_empty_sections():
    data = {
        "incident": {"incident_number": "IR-2", "title": "x", "incident_type": "safety",
                     "severity": "low", "status": "open", "occurred_at": None, "location": None,
                     "description": None, "root_cause": None, "corrective_actions": None,
                     "osha_recordable": False, "osha_classification": None,
                     "days_away_from_work": None, "days_restricted_duty": None, "return_to_work_date": None},
        "witnesses": [], "timeline": [], "documents": [], "policy_map": None, "recommendations": None,
    }
    html = cr._incident_html(data)
    assert "No witness statements on file." in html
    assert "No policy-violation mapping recorded." in html


def test_er_html_renders():
    data = {
        "case": {"case_number": "ER-1", "title": "Conflict", "status": "closed", "category": "harassment",
                 "outcome": "resolved", "created_at": None, "closed_at": None, "description": "d"},
        "notes": [{"note_type": "guidance", "content": "talk to HR", "created_at": None}],
        "documents": [],
        "analyses": {"determination": {"summary": "no violation found"}},
    }
    html = cr._er_html(data)
    assert "ER-1" in html
    assert "talk to HR" in html
    assert "no violation found" in html
