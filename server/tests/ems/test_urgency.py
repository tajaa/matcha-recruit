"""Urgency overlay + fallback classification. Pure — no DB/Gemini.

    cd server && ./venv/bin/python -m pytest tests/ems/test_urgency.py -q
"""

import pytest

from app.matcha.services.ems import event_intake
from app.matcha.services.ems.event_intake import apply_urgency_overlay, fallback_classification


def _base(**overrides):
    base = {
        "title": None, "category": "uncategorized", "severity_hint": None,
        "doc": {}, "ack": None, "incident_recommendation": False,
        "incident_reasoning": None, "suggested_incident_type": None,
        "suggested_severity": None, "needs_clarification": False,
        "clarify_question": None, "model_ok": False, "not_an_event": False,
        "severe": False, "urgency": None, "protocol_qualifies": None,
        "protocol_reasoning": None,
    }
    base.update(overrides)
    return base


class TestApplyUrgencyOverlay:
    def test_osha_keyword_flags_and_forces_recommendation(self):
        out = apply_urgency_overlay(_base(), "she was hospitalized overnight")
        assert out["urgency"] == "osha"
        assert out["incident_recommendation"] is True
        assert out["incident_reasoning"] == event_intake.OSHA_INCIDENT_REASONING

    def test_osha_keeps_model_provided_reasoning(self):
        out = apply_urgency_overlay(
            _base(incident_reasoning="Model's own reasoning."),
            "a fatality occurred on site",
        )
        assert out["urgency"] == "osha"
        assert out["incident_reasoning"] == "Model's own reasoning."

    def test_severe_true_without_osha_words(self):
        out = apply_urgency_overlay(_base(severe=True), "someone yelled at a coworker")
        assert out["urgency"] == "severe"

    def test_osha_wins_over_severe(self):
        out = apply_urgency_overlay(_base(severe=True), "a worker was hospitalized")
        assert out["urgency"] == "osha"

    def test_plain_text_no_severe_stays_unflagged(self):
        out = apply_urgency_overlay(_base(), "the printer is out of paper")
        assert out["urgency"] is None
        assert out["incident_recommendation"] is False

    def test_protocol_qualifies_true_forces_recommendation_without_urgency(self):
        out = apply_urgency_overlay(_base(protocol_qualifies=True), "a guest complained about the wait")
        assert out["urgency"] is None
        assert out["incident_recommendation"] is True

    def test_protocol_qualifies_false_does_not_force_recommendation(self):
        out = apply_urgency_overlay(_base(protocol_qualifies=False), "routine restock")
        assert out["incident_recommendation"] is False


class TestFallbackClassification:
    def test_osha_text_flags_even_with_zero_gemini_calls(self):
        out = fallback_classification("the truck driver passed away at the scene")
        assert out["urgency"] == "osha"
        assert out["incident_recommendation"] is True
        assert out["category"] == "uncategorized"
        assert out["model_ok"] is False

    def test_plain_text_stays_unflagged(self):
        out = fallback_classification("the ice machine is broken again")
        assert out["urgency"] is None
        assert out["incident_recommendation"] is False


class TestNegationPostureIsPreserved:
    """apply_urgency_overlay rides _detect_osha_reportable_keywords, whose
    deliberate false-positive posture (no negation handling) is pinned by
    tests/ir_incidents/test_osha_emergency_keywords.py. This test only
    confirms the overlay doesn't add its own negation logic on top."""

    @pytest.mark.parametrize("text", [
        "no one was hospitalized, just a scare",
        "thankfully nobody was killed",
    ])
    def test_negated_osha_language_still_flags(self, text):
        out = apply_urgency_overlay(_base(), text)
        assert out["urgency"] == "osha"
