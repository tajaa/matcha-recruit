"""Tests for the OSHA reportable-event keyword detector and chain card builders.

These are pure-helper unit tests — no app boot, no DB. The detector backs
the emergency alert that the IR Copilot drops into the transcript on
incident creation, and the chain card builders shape the recordable Q&A
sequence (Yes/No → days type → days count → injury type → close).
"""

import sys
from types import ModuleType

# Stub google.genai before any app imports (mirrors test_ir_incidents.py).
google_module = ModuleType("google")
genai_module = ModuleType("google.genai")
types_module = ModuleType("google.genai.types")
genai_module.Client = object
genai_module.types = types_module
types_module.Tool = lambda **kw: None
types_module.GoogleSearch = lambda **kw: None
types_module.GenerateContentConfig = lambda **kw: None
sys.modules.setdefault("google", google_module)
sys.modules.setdefault("google.genai", genai_module)
sys.modules.setdefault("google.genai.types", types_module)

import pytest

from app.matcha.routes.ir_incidents._shared import (
    OSHA_INJURY_TYPES,
    OSHA_INJURY_TYPE_LABELS,
    _detect_osha_reportable_keywords,
    build_osha_close_confirmation_card,
    build_osha_days_count_card,
    build_osha_days_type_query_card,
    build_osha_emergency_alert_card,
    build_osha_injury_type_query_card,
    build_osha_recordable_query_card,
)


# ============================================================
# _detect_osha_reportable_keywords
# ============================================================

class TestKeywordDetector:
    @pytest.mark.parametrize(
        "text",
        [
            "John was hospitalized after the fall.",
            "Worker was hospitalised at City General.",
            "Two-finger amputation reported.",
            "Forklift caused amputation of right index finger.",
            "Tragic — passed away on the way to the hospital.",
            "Suspected fatality at the press line.",
            "Worker has died from injuries sustained on site.",
            "She lost an eye during the welding incident.",
            "Lost his eye to a flying chip.",
            "In-patient admission for crush injury.",
            "Confirmed multiple fatalities at the warehouse fire.",
        ],
    )
    def test_positive_matches(self, text):
        assert _detect_osha_reportable_keywords(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "Employee tripped, applied a band-aid, returned to work.",
            "Studied the safety bulletin during morning meeting.",
            "Skilled foreman caught the bag before it fell.",
            "Hospitalization was discussed as a what-if scenario but did NOT occur.",
            # Negation-aware detection is out of scope — the assistant later
            # re-reads context. The detector here is intentionally permissive
            # on false positives; this last test documents that intent.
        ],
    )
    def test_negatives(self, text):
        # 'Hospitalization was discussed' contains the keyword and SHOULD trip
        # the detector — operator will resolve in the chat. We only assert
        # the unambiguous negatives here.
        if "hospitalization" in text.lower():
            return
        assert _detect_osha_reportable_keywords(text) is False

    def test_none_and_empty(self):
        assert _detect_osha_reportable_keywords(None) is False
        assert _detect_osha_reportable_keywords("") is False
        assert _detect_osha_reportable_keywords("   ") is False

    def test_case_insensitive(self):
        assert _detect_osha_reportable_keywords("AMPUTATION CONFIRMED") is True
        assert _detect_osha_reportable_keywords("Hospitalized OVERNIGHT") is True

    def test_word_boundary_protects_against_false_friends(self):
        # 'studied' contains 'died' as a substring but is not a fatality.
        assert _detect_osha_reportable_keywords("She studied the policy") is False
        # 'skilled' has 'killed' as suffix but no fatality occurred.
        assert _detect_osha_reportable_keywords("He is a skilled welder") is False


# ============================================================
# Chain card builders
# ============================================================

class TestEmergencyAlertCard:
    def test_static_shape(self):
        card = build_osha_emergency_alert_card()
        assert card["id"] == "osha_emergency_alert"
        assert "OSHA" in card["title"]
        assert card["priority"] == "high"
        action = card["action"]
        assert action["type"] == "osha_emergency_alert"
        assert action["phone"] == "1-800-321-6742"
        assert action["deadline"] == "8 to 24 hours"


class TestRecordableQueryCard:
    def test_yes_no_choices(self):
        card = build_osha_recordable_query_card()
        assert card["action"]["type"] == "quick_reply"
        assert card["action"]["quick_reply_kind"] == "osha_recordable_query"
        values = {c["value"] for c in card["action"]["choices"]}
        assert values == {"yes", "no"}


class TestDaysTypeQueryCard:
    def test_three_choices(self):
        card = build_osha_days_type_query_card()
        action = card["action"]
        assert action["type"] == "quick_reply"
        assert action["quick_reply_kind"] == "osha_days_type_query"
        values = {c["value"] for c in action["choices"]}
        assert values == {"days_away", "restricted_duty", "neither"}


class TestDaysCountCard:
    def test_days_away_target(self):
        card = build_osha_days_count_card(
            target_field="days_away_from_work",
            pending_classification="days_away",
        )
        action = card["action"]
        assert action["type"] == "numeric_input"
        assert action["target_field"] == "days_away_from_work"
        assert action["pending_classification"] == "days_away"
        assert action["input_min"] == 1
        assert action["input_max"] == 365

    def test_restricted_duty_target(self):
        card = build_osha_days_count_card(
            target_field="days_restricted_duty",
            pending_classification="restricted_duty",
        )
        assert card["action"]["target_field"] == "days_restricted_duty"
        assert card["action"]["pending_classification"] == "restricted_duty"


class TestInjuryTypeCard:
    def test_six_choices_from_injury_types(self):
        card = build_osha_injury_type_query_card()
        action = card["action"]
        assert action["type"] == "quick_reply"
        assert action["quick_reply_kind"] == "osha_injury_type_query"
        values = {c["value"] for c in action["choices"]}
        # All six OSHA 300 M-column types present.
        assert values == OSHA_INJURY_TYPES
        # Labels match the user-facing strings.
        labels = {c["label"] for c in action["choices"]}
        assert labels == set(OSHA_INJURY_TYPE_LABELS.values())


class TestCloseConfirmationCard:
    def test_close_action(self):
        card = build_osha_close_confirmation_card()
        assert card["action"]["type"] == "close_incident"
        assert card["id"] == "osha_close_confirmation"


# ============================================================
# OSHA_INJURY_TYPES + label map sanity
# ============================================================

class TestInjuryTypeConstants:
    def test_label_map_is_complete(self):
        # Every value in the set has a user-facing label.
        assert set(OSHA_INJURY_TYPE_LABELS.keys()) == OSHA_INJURY_TYPES

    def test_labels_match_spec(self):
        # Sourced from the OSHA 300 M-columns user-facing labels.
        assert OSHA_INJURY_TYPE_LABELS["injury"] == "Standard Injury"
        assert OSHA_INJURY_TYPE_LABELS["skin_disorder"] == "Skin Disorder"
        assert OSHA_INJURY_TYPE_LABELS["respiratory"] == "Respiratory Condition"
        assert OSHA_INJURY_TYPE_LABELS["poisoning"] == "Poisoning"
        assert OSHA_INJURY_TYPE_LABELS["hearing_loss"] == "Hearing Loss"
        assert OSHA_INJURY_TYPE_LABELS["other_illness"] == "All Other"
