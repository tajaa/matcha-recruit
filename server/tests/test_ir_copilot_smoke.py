"""IR Copilot smoke tests — pure-function helpers + Pydantic shape.

Avoids importing app.matcha.routes.ir_incidents (which transitively pulls
twilio_webhook → audioop on Python 3.13/3.14). Tests the orchestrator
helpers + Pydantic models without DB or Gemini calls.
"""

import json

import pytest

from app.matcha.models.ir_incident import (
    IRCopilotAcceptRequest,
    IRCopilotCard,
    IRCopilotCardAction,
)
from app.matcha.services.ir_ai_orchestrator import (
    IR_VALID_ANALYSIS_TYPES,
    IR_VALID_TABS,
    IR_ACTION_TYPES,
    _serialize_analyses,
    _serialize_conversation,
    _serialize_incident_core,
)
from app.matcha.services.er_guidance import (
    DEFAULT_VALID_TABS,
    DEFAULT_VALID_ANALYSIS_TYPES,
    _normalize_guidance_action,
)


def test_ir_constants_disjoint_from_er_defaults():
    """IR's tab keys must not be ER's — confirms parameterization is needed."""
    assert IR_VALID_TABS != DEFAULT_VALID_TABS
    assert IR_VALID_ANALYSIS_TYPES != DEFAULT_VALID_ANALYSIS_TYPES
    assert "copilot" in IR_VALID_TABS
    assert "categorization" in IR_VALID_ANALYSIS_TYPES


def test_normalize_action_with_ir_valid_tabs():
    raw = {
        "type": "open_tab",
        "label": "Open analysis",
        "tab": "analysis",
    }
    result = _normalize_guidance_action(
        raw,
        can_run_discrepancies=False,
        valid_tabs=IR_VALID_TABS,
        valid_analysis_types=IR_VALID_ANALYSIS_TYPES,
    )
    assert result["tab"] == "analysis"


def test_normalize_action_default_tabs_unchanged():
    """ER's default behavior unchanged when no kwargs passed (regression check)."""
    raw = {"type": "open_tab", "label": "Open timeline", "tab": "timeline"}
    result = _normalize_guidance_action(raw, can_run_discrepancies=True)
    assert result["tab"] == "timeline"


def test_serialize_incident_core_handles_none():
    serialized = _serialize_incident_core({})
    assert "title" in serialized
    parsed = json.loads(serialized)
    assert parsed["title"] is None


def test_serialize_analyses_empty():
    assert _serialize_analyses([]) == "(none)"


def test_serialize_conversation_cold_start():
    text, latest = _serialize_conversation([])
    assert "no prior" in text
    assert "cold start" in latest


def test_serialize_conversation_extracts_latest_user_message():
    msgs = [
        {"role": "user", "message_type": "text", "content": "first user msg"},
        {"role": "assistant", "message_type": "text", "content": "ai reply"},
        {"role": "user", "message_type": "text", "content": "second user msg"},
    ]
    text, latest = _serialize_conversation(msgs)
    assert "first user msg" in text
    assert "ai reply" in text
    assert latest == "second user msg"


def test_copilot_card_pydantic_validates():
    card = IRCopilotCard(
        id="card_1",
        title="Run severity analysis",
        recommendation="The incident type is 'safety' — run severity to flag escalation.",
        rationale="Safety incidents with critical/high severity should be escalated.",
        priority="high",
        blockers=[],
        action=IRCopilotCardAction(type="run_analysis", label="Run", analysis_type="severity"),
    )
    assert card.action.type == "run_analysis"
    assert card.action.analysis_type == "severity"


def test_copilot_card_rejects_unknown_action_type():
    with pytest.raises(Exception):
        IRCopilotCardAction(type="hack_database", label="Pwn")  # type: ignore[arg-type]


def test_accept_request_validates_uuid():
    from uuid import uuid4
    req = IRCopilotAcceptRequest(message_id=uuid4(), card_id="card_1")
    assert req.card_id == "card_1"


def test_action_type_set_complete():
    """All emitted action types match the dispatch whitelist in the route."""
    expected = {"run_analysis", "set_field", "request_info", "escalate", "close_incident"}
    assert expected.issubset(IR_ACTION_TYPES)
