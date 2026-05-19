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


# ---------------------------------------------------------------------------
# Fallback-cards block (AI returned empty payload → orchestrator inserts two
# hard-coded cards: review_basics + fallback_close). Block runs AFTER the
# per-card filter loop so it bypasses the close_incident rewrite branch.
# Bug confirmed via transcript of incident 0d4fc4d6 on 2026-05-19.
# ---------------------------------------------------------------------------


def test_fallback_close_swapped_for_rcq_on_safety(monkeypatch):
    """AI returns empty + safety/high incident → fallback inserts
    review_basics + log_root_cause_query (NOT fallback_close)."""
    _wire(monkeypatch, {})  # empty payload — triggers fallback
    incident = {
        "id": "00000000-0000-0000-0000-00000000000a",
        "title": "Forklift incident",
        "incident_type": "safety",
        "severity": "high",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    ids = [c["id"] for c in result["cards"]]
    types = [c["action"]["type"] for c in result["cards"]]
    kinds = [c["action"].get("quick_reply_kind") for c in result["cards"]]
    assert "review_basics" in ids, ids
    assert "fallback_close" not in ids, ids
    assert "close_incident" not in types, types
    assert "log_root_cause_query" in kinds, kinds


def test_fallback_close_kept_on_behavioral_low(monkeypatch):
    """AI returns empty + behavioral/low incident → fallback_close kept
    (gate doesn't trip for non-safety / non-high-severity)."""
    _wire(monkeypatch, {})
    incident = {
        "id": "00000000-0000-0000-0000-00000000000b",
        "title": "Tardiness",
        "incident_type": "behavioral",
        "severity": "low",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    ids = [c["id"] for c in result["cards"]]
    types = [c["action"]["type"] for c in result["cards"]]
    assert "review_basics" in ids
    assert "fallback_close" in ids, ids
    assert "close_incident" in types, types


def test_fallback_close_kept_when_root_cause_logged(monkeypatch):
    """AI returns empty + safety/high + root_cause already set →
    suppress_root_cause_card flips on, gate skips, fallback_close kept."""
    _wire(monkeypatch, {})
    incident = {
        "id": "00000000-0000-0000-0000-00000000000c",
        "title": "Slip",
        "incident_type": "safety",
        "severity": "high",
        "root_cause": "Wet floor — coffee spill, no sign placed.",
        "category_data": {},
    }
    result = _run(incident)
    ids = [c["id"] for c in result["cards"]]
    types = [c["action"]["type"] for c in result["cards"]]
    assert "fallback_close" in ids, ids
    assert "close_incident" in types, types


# ---------------------------------------------------------------------------
# quick_reply hallucination scrubbing. Gemini sometimes emits a quick_reply
# card with Yes/No choices but no quick_reply_kind (or an invented kind that
# the dispatcher at copilot.py:_handle_quick_reply doesn't route). User-
# facing symptom: red "Unknown quick_reply kind:" banner on accept. Bug
# confirmed via transcript of incident fd496e59 on 2026-05-19 21:06.
# ---------------------------------------------------------------------------


def _quick_reply_card(*, card_id, title, quick_reply_kind=None, recommendation="Pick one."):
    action = {
        "type": "quick_reply",
        "label": "Choose",
        "choices": [
            {"label": "Yes", "value": "yes"},
            {"label": "No", "value": "no"},
        ],
    }
    if quick_reply_kind is not None:
        action["quick_reply_kind"] = quick_reply_kind
    return {
        "id": card_id,
        "title": title,
        "recommendation": recommendation,
        "rationale": "AI-emitted quick_reply.",
        "priority": "high",
        "action": action,
    }


def test_quick_reply_missing_kind_root_cause_intent_rewritten(monkeypatch):
    """quick_reply with title='Start Root Cause...' but no kind →
    rewrite to canonical log_root_cause_query card."""
    _wire(monkeypatch, {
        "summary": "Begin root cause analysis.",
        "open_questions": [],
        "cards": [
            _quick_reply_card(
                card_id="start-root-cause-analysis",
                title="Start Root Cause Analysis Interview",
                recommendation="Initiate the structured interview.",
            ),
        ],
    })
    incident = {
        "id": "00000000-0000-0000-0000-00000000000d",
        "title": "Slip",
        "incident_type": "safety",
        "severity": "high",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    kinds = [c["action"].get("quick_reply_kind") for c in result["cards"]]
    assert "log_root_cause_query" in kinds, kinds
    # All quick_reply cards must have a recognized kind.
    for c in result["cards"]:
        if c["action"]["type"] == "quick_reply":
            assert c["action"].get("quick_reply_kind") in {
                "osha_recordable_query", "osha_days_type_query",
                "osha_injury_type_query", "log_root_cause_query",
            }, c["action"]


def test_quick_reply_missing_kind_no_intent_dropped(monkeypatch):
    """quick_reply with no kind AND no root-cause keyword → drop."""
    _wire(monkeypatch, {
        "summary": "Pick a flavor.",
        "open_questions": [],
        "cards": [
            _quick_reply_card(
                card_id="flavor-pick",
                title="Pick a flavor",
                recommendation="Vanilla or chocolate?",
            ),
        ],
    })
    incident = {
        "id": "00000000-0000-0000-0000-00000000000e",
        "title": "Slip",
        "incident_type": "safety",
        "severity": "high",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    types = [c["action"]["type"] for c in result["cards"]]
    # The broken quick_reply got dropped. Other safety-net cards may have
    # been inserted by close-rewrite or fallback, but no quick_reply with
    # the bad kind should remain.
    assert "flavor-pick" not in [c["id"] for c in result["cards"]]
    for c in result["cards"]:
        if c["action"]["type"] == "quick_reply":
            assert c["action"].get("quick_reply_kind") in {
                "osha_recordable_query", "osha_days_type_query",
                "osha_injury_type_query", "log_root_cause_query",
            }


def test_quick_reply_unknown_kind_root_cause_keyword_rewritten(monkeypatch):
    """quick_reply with invented kind but 'root cause' in title → rewrite."""
    _wire(monkeypatch, {
        "summary": "Root cause time.",
        "open_questions": [],
        "cards": [
            _quick_reply_card(
                card_id="rc-prompt",
                title="Root Cause Prompt",
                quick_reply_kind="custom_rc_thing",
            ),
        ],
    })
    incident = {
        "id": "00000000-0000-0000-0000-00000000000f",
        "title": "Slip",
        "incident_type": "safety",
        "severity": "high",
        "root_cause": None,
        "category_data": {},
    }
    result = _run(incident)
    kinds = [c["action"].get("quick_reply_kind") for c in result["cards"]]
    assert "log_root_cause_query" in kinds, kinds


def test_quick_reply_valid_kind_passes_through(monkeypatch):
    """quick_reply with a recognized kind passes through unchanged."""
    _wire(monkeypatch, {
        "summary": "OSHA classification needed.",
        "open_questions": [],
        "cards": [
            _quick_reply_card(
                card_id="osha-q",
                title="OSHA Recordable Event",
                quick_reply_kind="osha_recordable_query",
            ),
        ],
    })
    incident = {
        "id": "00000000-0000-0000-0000-000000000010",
        "title": "Slip",
        "incident_type": "safety",
        "severity": "high",
        "root_cause": "Already logged.",  # suppress rewrite branches
        "category_data": {},
    }
    result = _run(incident)
    qr_cards = [c for c in result["cards"] if c["action"]["type"] == "quick_reply"]
    assert any(
        c["action"].get("quick_reply_kind") == "osha_recordable_query"
        for c in qr_cards
    ), [c["action"] for c in qr_cards]
