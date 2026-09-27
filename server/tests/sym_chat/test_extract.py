"""Stance coercion + the flash-lite turn (services/sym_chat/extract.py).

`next_turn` runs against an httpx.MockTransport behind `_http_client`, patched
on the DEFINING module, per server/CLAUDE.md.
"""
import asyncio
import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.matcha.services.sym_chat import extract
from app.matcha.services.sym_chat.kinds import materialize_config

SCHED = materialize_config(
    "schedule",
    {"date": "2030-01-15", "window_start": "09:00", "window_end": "17:00", "duration_min": 60},
    today=date(2030, 1, 1),
)


def test_schedule_windows_are_clipped_merged_and_validated():
    stance = extract.coerce_stance("schedule", {
        "available": [
            {"start": "07:00", "end": "10:00"},   # clipped to 09:00
            {"start": "09:30", "end": "11:00"},   # overlaps → merged
            {"start": "16:00", "end": "20:00"},   # clipped to 17:00
            {"start": "3pm", "end": "4pm"},       # not HH:MM → dropped
            {"start": "18:00", "end": "19:00"},   # entirely outside → dropped
            "junk",
        ],
        "unavailable": "not a list",
        "preferred": ["10:00", "10:00", "08:00", "nope"],
        "extra_key": True,
    }, SCHED)
    assert stance == {
        "available": [{"start": "09:00", "end": "11:00"}, {"start": "16:00", "end": "17:00"}],
        "unavailable": [],
        "preferred": ["10:00"],
    }


def test_decide_names_canonicalise_and_vetoes_win():
    stance = extract.coerce_stance("decide", {
        "proposals": ["  sushi   go ", "Tacos"],
        "ok_with": ["THAI PALACE", "tacos", "x" * 200],
        "vetoes": ["Tacos"],
        "top_pick": "tacos",
    }, {}, ["Thai Palace", "Sushi Go"])
    assert stance["proposals"] == ["Sushi Go"]
    assert stance["ok_with"] == ["Thai Palace", "x" * 60]
    assert stance["vetoes"] == ["Tacos"]
    assert stance["top_pick"] is None


def test_stance_has_content():
    assert not extract.stance_has_content("schedule", None)
    assert not extract.stance_has_content("schedule", {"available": [], "unavailable": [], "preferred": ["10:00"]})
    assert extract.stance_has_content("schedule", {"available": [], "unavailable": [{"start": "09:00", "end": "17:00"}]})
    assert not extract.stance_has_content("decide", {"proposals": [], "ok_with": [], "vetoes": [], "top_pick": None})
    assert extract.stance_has_content("decide", {"top_pick": "A"})


def test_prompt_is_private_and_carries_the_window():
    prompt = extract.build_prompt(
        "schedule", "Quarterly sync", SCHED,
        [{"role": "user", "content": "I'm free after 2"}], None, [], "Dana",
    )
    assert "Only Dana sees this conversation" in prompt
    assert "between 09:00 and 17:00" in prompt
    assert "Dana: I'm free after 2" in prompt
    assert "Quarterly sync" in prompt


def _responses_payload(obj) -> dict:
    """A minimal OpenAI Responses body whose output text is `obj` (str or JSON-able)."""
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return {"id": "resp_1", "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}]}


@pytest.fixture
def luna(monkeypatch):
    """Route extract's Responses call to a handler; capture requests + usage records."""
    seen = {"requests": [], "records": []}
    state = {"handler": lambda request: httpx.Response(200, json=_responses_payload({"reply": "ok", "stance": {}}))}

    def factory(timeout):
        def handle(request):
            seen["requests"].append(json.loads(request.content))
            return state["handler"](request)
        return httpx.AsyncClient(transport=httpx.MockTransport(handle), timeout=timeout)

    async def record(**kwargs):
        seen["records"].append(kwargs)

    monkeypatch.setattr(extract, "_http_client", factory)
    monkeypatch.setattr(extract, "record_openai_response", record)
    monkeypatch.setattr(extract, "get_settings", lambda: SimpleNamespace(openai_api_key="sk-test", openai_luna_model="gpt-5.6-luna"))
    seen["set"] = lambda handler: state.__setitem__("handler", handler)
    return seen


def _turn(current=None):
    return asyncio.run(extract.next_turn(
        "schedule", "", SCHED, [{"role": "user", "content": "free 2-4"}], current, [], "Dana",
    ))


def test_next_turn_calls_luna_in_json_mode_and_replaces_the_stance(luna):
    luna["set"](lambda r: httpx.Response(200, json=_responses_payload(
        {"reply": "Got it — 2 to 4.", "stance": {"available": [{"start": "14:00", "end": "16:00"}]}})))
    out = _turn({"available": [{"start": "09:00", "end": "10:00"}], "unavailable": [], "preferred": []})
    assert out["error"] is False
    assert out["reply"] == "Got it — 2 to 4."
    # Re-derived, not merged: the old 09:00-10:00 window is gone.
    assert out["stance"]["available"] == [{"start": "14:00", "end": "16:00"}]
    body = luna["requests"][0]
    assert body["model"] == "gpt-5.6-luna"
    assert body["text"] == {"format": {"type": "json_object"}}
    assert body["reasoning"] == {"effort": extract.REASONING_EFFORT}
    assert luna["records"][0]["response"]["id"] == "resp_1"


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(401, json={"error": {"message": "bad key"}}),
    lambda r: httpx.Response(200, json=_responses_payload("not json")),
    lambda r: httpx.Response(200, json=_responses_payload("[1, 2]")),
])
def test_next_turn_never_raises_and_keeps_the_current_stance(luna, handler):
    luna["set"](handler)
    current = {"available": [{"start": "09:00", "end": "10:00"}], "unavailable": [], "preferred": []}
    out = _turn(current)
    assert out["error"] is True
    assert out["reply"] == extract.FALLBACK_REPLY
    assert out["stance"] == current
    assert luna["records"], "usage is recorded on failure too"


def test_next_turn_without_a_key_falls_back_without_calling(luna, monkeypatch):
    monkeypatch.setattr(extract, "get_settings", lambda: SimpleNamespace(openai_api_key=None, openai_luna_model="gpt-5.6-luna"))
    out = _turn()
    assert out["error"] is True and luna["requests"] == []


def test_next_turn_defaults_an_empty_reply(luna):
    luna["set"](lambda r: httpx.Response(200, json=_responses_payload({"reply": "  ", "stance": {}})))
    assert _turn()["reply"] == "Got it."
