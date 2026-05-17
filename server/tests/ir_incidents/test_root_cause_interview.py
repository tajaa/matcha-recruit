"""Tests for the IR Copilot root-cause interview chain.

Replaces the prior AI-driven `run_analysis root_cause` recommendation with
a structured 3-question user interview (Hazard / Why / Prevention). These
are pure helpers — no app boot, no DB.
"""

import sys
from types import ModuleType

# Stub google.genai before any app imports (matches test_ir_incidents.py).
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

from uuid import uuid4

import pytest

from app.matcha.models.ir_incident import IRCopilotAcceptRequest
from app.matcha.routes.ir_incidents._shared import (
    ROOT_CAUSE_INTERVIEW_STEPS,
    ROOT_CAUSE_PLAINTEXT_LABELS,
    ROOT_CAUSE_PROMPTS,
    build_log_root_cause_query_card,
    build_root_cause_logged_ack_card,
    build_root_cause_text_card,
    compose_root_cause_text,
)
from app.matcha.services.ir_ai_orchestrator import IR_ACTION_TYPES


# ============================================================
# Constants
# ============================================================

class TestConstants:
    def test_steps_order_is_hazard_why_prevention(self):
        assert ROOT_CAUSE_INTERVIEW_STEPS == ("hazard", "why", "prevention")

    def test_every_step_has_a_prompt_and_label(self):
        for step in ROOT_CAUSE_INTERVIEW_STEPS:
            assert step in ROOT_CAUSE_PROMPTS
            assert ROOT_CAUSE_PROMPTS[step].endswith("?")
            assert step in ROOT_CAUSE_PLAINTEXT_LABELS

    def test_text_input_in_action_types(self):
        assert "text_input" in IR_ACTION_TYPES


# ============================================================
# Card builders
# ============================================================

class TestLogRootCauseQueryCard:
    def test_yes_no_choices(self):
        card = build_log_root_cause_query_card()
        action = card["action"]
        assert action["type"] == "quick_reply"
        assert action["quick_reply_kind"] == "log_root_cause_query"
        values = {c["value"] for c in action["choices"]}
        assert values == {"yes", "no"}

    def test_user_facing_prompt(self):
        card = build_log_root_cause_query_card()
        assert "root cause" in card["recommendation"].lower()


class TestRootCauseTextCard:
    @pytest.mark.parametrize("step", list(ROOT_CAUSE_INTERVIEW_STEPS))
    def test_each_step_builds(self, step):
        card = build_root_cause_text_card(step=step)
        action = card["action"]
        assert action["type"] == "text_input"
        assert action["target_field"] == step
        assert action["prompt_text"] == ROOT_CAUSE_PROMPTS[step]
        assert action["input_rows"] == 3

    def test_unknown_step_raises(self):
        with pytest.raises(ValueError):
            build_root_cause_text_card(step="hallucinated_step")


class TestRootCauseLoggedAckCard:
    def test_ack_card_shape(self):
        card = build_root_cause_logged_ack_card()
        assert card["id"] == "root_cause_logged"
        assert card["action"]["type"] == "request_info"


# ============================================================
# compose_root_cause_text
# ============================================================

class TestComposeRootCauseText:
    def test_all_three_answers(self):
        interview = {
            "hazard": "Forklift speed > 5mph in pedestrian zone",
            "why": "Operator skipped pre-shift inspection; horn disabled",
            "prevention": "Reinstate horn check; install speed governor",
        }
        text = compose_root_cause_text(interview)
        assert "Hazard: Forklift speed > 5mph in pedestrian zone" in text
        assert "Why it happened: Operator skipped pre-shift inspection; horn disabled" in text
        assert "Prevention: Reinstate horn check; install speed governor" in text
        # Step order preserved with blank lines between blocks.
        idx_hazard = text.index("Hazard:")
        idx_why = text.index("Why it happened:")
        idx_prev = text.index("Prevention:")
        assert idx_hazard < idx_why < idx_prev

    def test_missing_step_renders_empty_block(self):
        text = compose_root_cause_text({"hazard": "X", "why": "Y"})
        # prevention missing — block still emitted, no error.
        assert "Prevention:" in text

    def test_none_and_empty(self):
        # Should not crash, just emit empty labels.
        assert "Hazard:" in compose_root_cause_text({})
        assert "Hazard:" in compose_root_cause_text(None)  # type: ignore[arg-type]

    def test_whitespace_trimmed(self):
        interview = {"hazard": "  trailing   ", "why": "  ", "prevention": "leading  "}
        text = compose_root_cause_text(interview)
        # Trailing/leading whitespace stripped on each answer.
        assert "Hazard: trailing" in text
        assert "Prevention: leading" in text


# ============================================================
# Accept request shape
# ============================================================

class TestAcceptRequest:
    def test_text_value_roundtrips(self):
        req = IRCopilotAcceptRequest(
            message_id=uuid4(),
            card_id="root_cause_interview__hazard",
            text_value="Forklift speed > 5mph in pedestrian zone",
        )
        assert req.text_value.startswith("Forklift")
        assert req.selected_value is None
        assert req.numeric_value is None

    def test_text_value_max_length_enforced(self):
        # max_length=4000 on the model. Pydantic raises on overlong.
        with pytest.raises(Exception):
            IRCopilotAcceptRequest(
                message_id=uuid4(),
                card_id="x",
                text_value="x" * 4001,
            )
