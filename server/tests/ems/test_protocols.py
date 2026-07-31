"""Company event-protocol helpers. Pure — no DB/Gemini.

    cd server && ./venv/bin/python -m pytest tests/ems/test_protocols.py -q
"""

from app.matcha.services.ems.protocols import mentions_incident, protocol_prompt_excerpt


class TestMentionsIncident:
    def test_capital_incident(self):
        assert mentions_incident("we had an Incident today") is True

    def test_plural(self):
        assert mentions_incident("incidents happen sometimes") is True

    def test_absent(self):
        assert mentions_incident("the fridge broke again") is False

    def test_empty_and_none(self):
        assert mentions_incident("") is False
        assert mentions_incident(None) is False


class TestProtocolPromptExcerpt:
    def test_none_row_returns_none(self):
        assert protocol_prompt_excerpt(None) is None

    def test_both_blank_returns_none(self):
        row = {"incident_definition": "", "culture_notes": "", "corrective_actions": "x"}
        assert protocol_prompt_excerpt(row) is None

    def test_definition_only(self):
        row = {"incident_definition": "Any guest complaint with a refund.", "culture_notes": "", "corrective_actions": ""}
        excerpt = protocol_prompt_excerpt(row)
        assert "What counts as an incident:" in excerpt
        assert "Any guest complaint with a refund." in excerpt

    def test_includes_culture_when_present(self):
        row = {
            "incident_definition": "def", "culture_notes": "We escalate fast.",
            "corrective_actions": "",
        }
        excerpt = protocol_prompt_excerpt(row)
        assert "Culture notes:" in excerpt
        assert "We escalate fast." in excerpt

    def test_excludes_corrective_actions(self):
        row = {
            "incident_definition": "def", "culture_notes": "",
            "corrective_actions": "Always offer a refund first.",
        }
        excerpt = protocol_prompt_excerpt(row)
        assert "Always offer a refund first." not in excerpt

    def test_caps_at_4000_chars(self):
        row = {"incident_definition": "x" * 10000, "culture_notes": "", "corrective_actions": ""}
        excerpt = protocol_prompt_excerpt(row)
        assert len(excerpt) <= 4000
