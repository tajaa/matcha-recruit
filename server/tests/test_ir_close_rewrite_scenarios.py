"""Regression tests for the close_incident → log_root_cause_query rewrite.

Mirrors the patterns in test_ir_copilot_smoke.py: monkey-patches the IR
analyzer to return a known payload, runs generate_guidance, asserts on the
filtered cards.

The bug: AI emits a close_incident card for a safety / near-miss / high /
critical incident before any root-cause prompt. User report on 2026-05-19:
"completed a safety incident report and it is prompting me to close it
without ever prompting for root cause." Backend safety net at
copilot.py:497 catches the close click; this filter catches the card
suggestion BEFORE the user can click it.
"""

import asyncio
import json
from types import SimpleNamespace

from app.matcha.services import ir_ai_orchestrator


def _build_fake_analyzer(payload: dict):
    payload_json = json.dumps(payload)

    async def fake_generate_content(*args, **kwargs):
        return SimpleNamespace(text=payload_json)

    return SimpleNamespace(
        client=SimpleNamespace(
            aio=SimpleNamespace(
                models=SimpleNamespace(generate_content=fake_generate_content),
            ),
        ),
        model="fake-model",
        _parse_json_response=lambda raw: json.loads(raw),
    )


class _FakeRateLimiter:
    async def check_limit(self, *args, **kwargs):
        return None


def _wire(monkeypatch, payload):
    monkeypatch.setattr(
        ir_ai_orchestrator, "get_ir_analyzer",
        lambda: _build_fake_analyzer(payload),
    )
    monkeypatch.setattr(
        ir_ai_orchestrator, "get_rate_limiter", lambda: _FakeRateLimiter(),
    )


def _close_card():
    return {
        "id": "close_now",
        "title": "Close this incident",
        "recommendation": "All steps complete — close it out.",
        "rationale": "Action plan in place.",
        "priority": "medium",
        "action": {
            "type": "close_incident",
            "label": "Close incident",
        },
    }


def _log_rcq_card():
    return {
        "id": "log_root_cause_query",
        "title": "Log Root Cause",
        "recommendation": "Would you like to log the root cause?",
        "rationale": "Capture in your own words.",
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
    }


def _run(incident):
    return asyncio.run(
        ir_ai_orchestrator.generate_guidance(
            incident=incident, analyses=[], messages=[],
        )
    )


def test_safety_no_root_cause_rewrites_close_to_root_cause_query(monkeypatch):
    """Safety incident, no root_cause, AI proposes close → must rewrite."""
    _wire(monkeypatch, {
        "summary": "Ready to close — accept the recommendation below.",
        "open_questions": [],
        "cards": [_close_card()],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000001",
        "title": "Slip in hallway",
        "incident_type": "safety",
        "severity": "medium",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    types = [c["action"]["type"] for c in result["cards"]]
    kinds = [c["action"].get("quick_reply_kind") for c in result["cards"]]
    assert "close_incident" not in types, f"close_incident leaked: {types}"
    assert "log_root_cause_query" in kinds, f"no rcq card: {kinds}"
    assert result["summary"].startswith("Before closing"), result["summary"]


def test_high_severity_behavioral_rewrites_close(monkeypatch):
    """High-severity behavioral incident → severity gate trips rewrite."""
    _wire(monkeypatch, {
        "summary": "Close it out.",
        "open_questions": [],
        "cards": [_close_card()],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000002",
        "title": "Harassment claim",
        "incident_type": "behavioral",
        "severity": "high",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    kinds = [c["action"].get("quick_reply_kind") for c in result["cards"]]
    assert "log_root_cause_query" in kinds
    types = [c["action"]["type"] for c in result["cards"]]
    assert "close_incident" not in types


def test_low_severity_behavioral_keeps_close(monkeypatch):
    """Behavioral + low severity → no gate, close card passes through."""
    _wire(monkeypatch, {
        "summary": "Close it out.",
        "open_questions": [],
        "cards": [_close_card()],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000003",
        "title": "Dress code violation",
        "incident_type": "behavioral",
        "severity": "low",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    types = [c["action"]["type"] for c in result["cards"]]
    assert "close_incident" in types, f"close_incident should remain: {types}"
    # Summary unmodified
    assert not result["summary"].startswith("Before closing")


def test_safety_with_root_cause_logged_keeps_close(monkeypatch):
    """Safety + root_cause already non-empty → suppress flag on, close OK."""
    _wire(monkeypatch, {
        "summary": "Close it out.",
        "open_questions": [],
        "cards": [_close_card()],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000004",
        "title": "Slip in hallway",
        "incident_type": "safety",
        "severity": "medium",
        "root_cause": "Wet floor — spilled coffee not signed off.",
        "category_data": {},
    }
    result = _run(incident)
    types = [c["action"]["type"] for c in result["cards"]]
    assert "close_incident" in types, types


def test_safety_root_cause_declined_keeps_close(monkeypatch):
    """User said No to root cause → suppress flag on, close OK."""
    _wire(monkeypatch, {
        "summary": "Close it out.",
        "open_questions": [],
        "cards": [_close_card()],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000005",
        "title": "Slip in hallway",
        "incident_type": "safety",
        "severity": "medium",
        "root_cause": None,
        "category_data": {"root_cause_declined": True},
    }
    result = _run(incident)
    types = [c["action"]["type"] for c in result["cards"]]
    assert "close_incident" in types, types


def test_safety_close_plus_rcq_dedupes_to_single_rcq(monkeypatch):
    """AI emits BOTH close_incident AND quick_reply log_root_cause_query →
    dedup so only one log_root_cause_query card surfaces."""
    _wire(monkeypatch, {
        "summary": "Capture root cause then close.",
        "open_questions": [],
        "cards": [_close_card(), _log_rcq_card()],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000006",
        "title": "Slip",
        "incident_type": "safety",
        "severity": "medium",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    kinds = [c["action"].get("quick_reply_kind") for c in result["cards"]]
    log_count = sum(1 for k in kinds if k == "log_root_cause_query")
    assert log_count == 1, f"expected 1 rcq card, got {log_count}: kinds={kinds}"
    types = [c["action"]["type"] for c in result["cards"]]
    assert "close_incident" not in types


def test_near_miss_rewrites_close(monkeypatch):
    """near_miss + low severity → incident_type gate trips."""
    _wire(monkeypatch, {
        "summary": "Close it.",
        "open_questions": [],
        "cards": [_close_card()],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000007",
        "title": "Nearly slipped",
        "incident_type": "near_miss",
        "severity": "low",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    kinds = [c["action"].get("quick_reply_kind") for c in result["cards"]]
    assert "log_root_cause_query" in kinds
    types = [c["action"]["type"] for c in result["cards"]]
    assert "close_incident" not in types


def test_critical_severity_rewrites_close(monkeypatch):
    """severity=critical regardless of type → rewrite."""
    _wire(monkeypatch, {
        "summary": "Close it.",
        "open_questions": [],
        "cards": [_close_card()],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000008",
        "title": "Theft",
        "incident_type": "property",
        "severity": "critical",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    kinds = [c["action"].get("quick_reply_kind") for c in result["cards"]]
    assert "log_root_cause_query" in kinds
