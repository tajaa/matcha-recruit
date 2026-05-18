"""IR Copilot smoke tests — pure-function helpers + Pydantic shape.

Avoids importing app.matcha.routes.ir_incidents (which transitively pulls
twilio_webhook → audioop on Python 3.13/3.14). Tests the orchestrator
helpers + Pydantic models without DB or Gemini calls.
"""

import json

import pytest

from typing import get_args

from app.matcha.models.ir_incident import (
    IRCopilotAcceptRequest,
    IRCopilotActionType,
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
    expected = {
        "run_analysis", "set_field", "request_info", "escalate", "close_incident",
        # OSHA recordable chain + root-cause interview: backend-emitted card
        # types accepted by the dispatch handler and surfaced through the
        # transcript filter.
        "quick_reply", "numeric_input", "text_input", "osha_emergency_alert",
    }
    assert IR_ACTION_TYPES == expected


def test_pydantic_action_type_matches_orchestrator():
    """Pydantic Literal must mirror IR_ACTION_TYPES — open_tab in particular
    must be absent so stale persisted cards die at model_validate."""
    assert set(get_args(IRCopilotActionType)) == IR_ACTION_TYPES
    assert "open_tab" not in get_args(IRCopilotActionType)


def test_generate_guidance_drops_invalid_cards(monkeypatch):
    """AI may emit cards with action types IR doesn't support (open_tab via the
    shared ER normalizer fallback) or run_analysis with an unrecognized
    analysis_type. Both must be filtered before reaching the user."""
    import asyncio
    from types import SimpleNamespace

    from app.matcha.services import ir_ai_orchestrator

    payload_json = json.dumps({
        "summary": "Mixed bag.",
        "open_questions": [],
        "cards": [
            {
                "id": "good_set_field",
                "title": "Set severity to high",
                "recommendation": "Severity should be high.",
                "rationale": "Multiple injuries reported.",
                "priority": "high",
                "action": {
                    "type": "set_field",
                    "label": "Set severity",
                    "field_name": "severity",
                    "field_value": "high",
                },
            },
            {
                "id": "bad_open_tab",
                "title": "Look at timeline",
                "recommendation": "Open the timeline tab.",
                "rationale": "Context.",
                "priority": "low",
                "action": {"type": "open_tab", "label": "Open timeline", "tab": "timeline"},
            },
            {
                "id": "bad_run_analysis",
                "title": "Run mystery analysis",
                "recommendation": "Run an unknown analysis.",
                "rationale": "Reason.",
                "priority": "medium",
                "action": {
                    "type": "run_analysis",
                    "label": "Run",
                    "analysis_type": "nonsense",
                },
            },
            {
                "id": "bad_set_field",
                "title": "Categorize as Tardiness",
                "recommendation": "Set incident_type to Tardiness.",
                "rationale": "Reported user bug — AI invents enum values.",
                "priority": "high",
                "action": {
                    "type": "set_field",
                    "label": "Set Type to Tardiness",
                    "field_name": "incident_type",
                    "field_value": "Tardiness",
                },
            },
        ],
    })

    async def fake_generate_content(*args, **kwargs):
        return SimpleNamespace(text=payload_json)

    fake_analyzer = SimpleNamespace(
        client=SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=fake_generate_content),
            ),
        ),
        model="fake-model",
        _parse_json_response=lambda raw: json.loads(raw),
    )

    monkeypatch.setattr(ir_ai_orchestrator, "get_ir_analyzer", lambda: fake_analyzer)

    class FakeRateLimiter:
        async def check_limit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(ir_ai_orchestrator, "get_rate_limiter", lambda: FakeRateLimiter())

    incident = {"id": "00000000-0000-0000-0000-000000000000", "title": "Test"}
    result = asyncio.run(
        ir_ai_orchestrator.generate_guidance(
            incident=incident, analyses=[], messages=[],
        )
    )

    card_ids = {c["id"] for c in result["cards"]}
    assert "good-set-field" in card_ids or "good_set_field" in card_ids
    assert "bad-open-tab" not in card_ids and "bad_open_tab" not in card_ids
    assert "bad-run-analysis" not in card_ids and "bad_run_analysis" not in card_ids
    assert "bad-set-field" not in card_ids and "bad_set_field" not in card_ids
    for card in result["cards"]:
        assert card["action"]["type"] in IR_ACTION_TYPES
        if card["action"]["type"] == "set_field":
            from app.matcha.services.ir_ai_orchestrator import _is_valid_set_field
            assert _is_valid_set_field(card["action"]["field_name"], card["action"]["field_value"])


def test_generate_guidance_preserves_quick_reply_choices(monkeypatch):
    """Regression: the AI emits a quick_reply log_root_cause_query card with
    choices + quick_reply_kind. The orchestrator's filter loop used to strip
    those extensions because _normalize_guidance_cards only knew the base
    action schema, leaving the persisted card with action.type='quick_reply'
    but no choices array — frontend then fell through to the default
    Accept/Skip branch, sent an empty selected_value, and the backend
    dispatcher returned "Pick an option to continue." Now the loop
    explicitly re-attaches IR-only extension fields for quick_reply,
    numeric_input, text_input, and osha_emergency_alert.
    """
    import asyncio
    from types import SimpleNamespace

    from app.matcha.services import ir_ai_orchestrator

    payload_json = json.dumps({
        "summary": "Capture the root cause if you like.",
        "open_questions": [],
        "cards": [
            {
                "id": "log_root_cause_query",
                "title": "Log Root Cause",
                "recommendation": "Would you like to log the root cause?",
                "rationale": "Capture hazard / why / prevention in your own words.",
                "priority": "medium",
                "action": {
                    "type": "quick_reply",
                    "label": "Choose one",
                    "quick_reply_kind": "log_root_cause_query",
                    "choices": [
                        {"label": "Yes", "value": "yes"},
                        {"label": "No", "value": "no"},
                    ],
                },
            },
        ],
    })

    async def fake_generate_content(*args, **kwargs):
        return SimpleNamespace(text=payload_json)

    fake_analyzer = SimpleNamespace(
        client=SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=fake_generate_content),
            ),
        ),
        model="fake-model",
        _parse_json_response=lambda raw: json.loads(raw),
    )
    monkeypatch.setattr(ir_ai_orchestrator, "get_ir_analyzer", lambda: fake_analyzer)

    class FakeRateLimiter:
        async def check_limit(self, *args, **kwargs):
            return None
    monkeypatch.setattr(ir_ai_orchestrator, "get_rate_limiter", lambda: FakeRateLimiter())

    incident = {"id": "00000000-0000-0000-0000-000000000000", "title": "Test"}
    result = asyncio.run(
        ir_ai_orchestrator.generate_guidance(
            incident=incident, analyses=[], messages=[],
        )
    )

    assert len(result["cards"]) == 1
    action = result["cards"][0]["action"]
    assert action["type"] == "quick_reply"
    assert action.get("quick_reply_kind") == "log_root_cause_query"
    choices = action.get("choices")
    assert isinstance(choices, list) and len(choices) == 2
    assert {c["value"] for c in choices} == {"yes", "no"}


def test_canonical_analysis_type_aliases():
    """AI commonly emits abbreviated names. Aliases must resolve to canonical."""
    from app.matcha.services.ir_ai_orchestrator import _canonical_analysis_type

    assert _canonical_analysis_type("policy") == "policy_mapping"
    assert _canonical_analysis_type("Policy") == "policy_mapping"
    assert _canonical_analysis_type("policy-mapping") == "policy_mapping"
    assert _canonical_analysis_type("rca") == "root_cause"
    assert _canonical_analysis_type("categorize") == "categorization"
    assert _canonical_analysis_type("similar_incidents") == "similar"
    assert _canonical_analysis_type("severity") == "severity"  # already canonical
    assert _canonical_analysis_type(None) is None
    assert _canonical_analysis_type("nonsense") is None


def test_is_valid_set_field_rejects_hallucinated_enums():
    """User-reported bug: AI proposed `set_field incident_type='Tardiness'`
    which the backend rejects. Orchestrator should drop the card upstream."""
    from app.matcha.services.ir_ai_orchestrator import _is_valid_set_field

    # Valid enum values
    assert _is_valid_set_field("incident_type", "behavioral") is True
    assert _is_valid_set_field("severity", "high") is True
    assert _is_valid_set_field("status", "investigating") is True
    # Case-insensitive enum match (orchestrator lowercases before route check)
    assert _is_valid_set_field("incident_type", "Behavioral") is True
    # Free-text fields accept any non-empty string
    assert _is_valid_set_field("root_cause", "Employee was late.") is True
    assert _is_valid_set_field("corrective_actions", "Coach the employee.") is True
    # Hallucinated enum — must reject
    assert _is_valid_set_field("incident_type", "Tardiness") is False
    assert _is_valid_set_field("severity", "very high") is False
    assert _is_valid_set_field("status", "new") is False
    # Unknown field name
    assert _is_valid_set_field("priority", "high") is False
    assert _is_valid_set_field(None, "behavioral") is False
    # Empty / non-string values
    assert _is_valid_set_field("root_cause", "") is False
    assert _is_valid_set_field("root_cause", None) is False


def test_summaries_too_similar_catches_paraphrase():
    """Repetitive copilot summaries (same facts, different wording) should
    register as similar so persist_assistant_round can skip the duplicate."""
    from app.matcha.services.ir_ai_orchestrator import _summaries_too_similar

    a = "The incident concerns Gina's 10-minute tardiness without prior notification, violating the attendance policy. It is currently categorized as behavioral and low severity."
    b = "The incident regarding Gina's 10-minute tardiness without prior notification is categorized as behavioral and low severity, with a clear violation of the attendance policy."
    assert _summaries_too_similar(a, b) is True

    # Distinct summaries describing different state
    c = "Awaiting your reply on whether the tardiness was documented."
    d = "Policy mapping complete. Two attendance policy violations identified."
    assert _summaries_too_similar(c, d) is False

    # Identical strings
    assert _summaries_too_similar(a, a) is True
    # Empty inputs short-circuit to False (no signal)
    assert _summaries_too_similar("", a) is False
    assert _summaries_too_similar(a, "") is False
