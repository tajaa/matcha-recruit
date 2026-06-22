"""Pure tests for controls-evidence helpers (DB/render paths smoke-tested vs dev)."""

from app.matcha.services import controls_evidence as ce


def test_catalog_has_8_unique_keys():
    keys = [c["key"] for c in ce.CONTROL_CATALOG]
    assert len(keys) == 8
    assert len(set(keys)) == 8


def test_band_thresholds():
    assert ce._band(90) == "strong"
    assert ce._band(70) == "strong"
    assert ce._band(69) == "partial"
    assert ce._band(35) == "partial"
    assert ce._band(34) == "gap"
    assert ce._band(0) == "gap"


def test_epl_keys_are_catalog_subset():
    catalog_keys = {c["key"] for c in ce.CONTROL_CATALOG}
    assert ce._EPL_KEYS <= catalog_keys
    assert "anti_harassment_policy" in ce._EPL_KEYS
    # computed-here controls are NOT in the EPL-reuse set
    assert "safety_programs" not in ce._EPL_KEYS
    assert "credentialing_currency" not in ce._EPL_KEYS
    assert "safety_incident_response" not in ce._EPL_KEYS


def test_controls_html_renders_and_includes_note():
    reg = {
        "company_name": "Acme Co",
        "controls": [
            {"key": "k1", "label": "Anti-harassment", "source": "epl", "status": "strong",
             "score": 90, "metric": "92% signed", "detail": "d", "note": None, "verified": True, "verified_at": None},
            {"key": "k2", "label": "Safety programs", "source": "safety", "status": "gap",
             "score": None, "metric": "None", "detail": "d", "note": "follow up", "verified": False, "verified_at": None},
        ],
        "summary": {"total": 2, "strong": 1, "partial": 0, "gap": 1, "na": 0, "verified": 1},
    }
    html = ce._controls_html("Acme Co", reg)
    assert "Proof of Controls" in html
    assert "Anti-harassment" in html
    assert "STRONG" in html
    assert "follow up" in html  # the note row is rendered
