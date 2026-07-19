"""Merlin's prompt build + chat-turn contract, with a fake Gemini client.

These are the tests whose absence let two 500-on-every-request bugs ship: the
prompt was built with `str.format()` over a template full of literal JSON
braces, and a non-dict payload hit `.get`. Both crashed before any assertion
in the validation suite could notice.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_turn.py -q
"""
import json
import os

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()  # run_merlin_turn reads settings.analysis_model

from app.cappe.services import merlin  # noqa: E402
from app.cappe.services.merlin import _build_prompt, run_merlin_turn  # noqa: E402

_BLOCKS = [{"id": "b1", "type": "hero", "heading": "Old"}]


# --- prompt ------------------------------------------------------------------

def test_build_prompt_does_not_raise_and_carries_the_catalog():
    """`_SYSTEM_PROMPT` is full of literal `{...}` JSON. Any f-string or
    .format() over it raises KeyError — and it is built outside the try, so it
    500s every single request."""
    prompt = _build_prompt(
        message="make the hero darker", history=[], blocks=_BLOCKS, theme={},
        business_name="Demo", business_type=None, feedback=None,
    )
    assert "hero (Hero)" in prompt          # catalog was appended
    assert "heading:text" in prompt          # …with field kinds
    assert '{"op":"set_field"' in prompt     # op shapes survived verbatim
    assert "make the hero darker" in prompt


def test_build_prompt_includes_history_and_feedback():
    prompt = _build_prompt(
        message="now bigger",
        history=[{"role": "assistant", "content": "Done.", "ops_summary": "set hero.heading"}],
        blocks=_BLOCKS, theme={"mode": "dark"}, business_name=None, business_type=None,
        feedback="2 op(s) were invalid",
    )
    assert "set hero.heading" in prompt
    assert "FAILED VALIDATION" in prompt


# --- turn contract -----------------------------------------------------------

class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, behavior):
        self._behavior = behavior

    async def generate_content(self, **_kwargs):
        if isinstance(self._behavior, Exception):
            raise self._behavior
        return _FakeResponse(self._behavior)


class _FakeClient:
    def __init__(self, behavior):
        self.aio = type("aio", (), {"models": _FakeModels(behavior)})()


class _NoopLimiter:
    async def check_limit(self, *a, **kw):
        return None

    async def record_call(self, *a, **kw):
        return None


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    monkeypatch.setattr(merlin, "_get_rate_limiter", lambda: _NoopLimiter())


async def _run(behavior):
    return await run_merlin_turn(message="hi", history=[], blocks=_BLOCKS, theme={})


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    "[]",                        # valid JSON, wrong shape — used to AttributeError
    '"just a string"',           # ditto
    "{bad json",                 # unparsable
    "",                          # empty response
    '{"message": "ok"}',         # no ops key
])
async def test_never_raises_on_bad_payloads(monkeypatch, payload):
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await _run(payload)
    assert isinstance(result["message"], str)
    assert result["ops"] == []


@pytest.mark.asyncio
async def test_never_raises_when_the_api_call_explodes(monkeypatch):
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(RuntimeError("upstream on fire")))
    result = await _run(None)
    assert result["ops"] == []
    assert isinstance(result["message"], str)


@pytest.mark.asyncio
async def test_valid_ops_pass_through(monkeypatch):
    payload = '{"message": "Updated the hero.", "ops": [{"op":"set_field","block":"b1","path":"heading","value":"New"}]}'
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await _run(payload)
    assert result["message"] == "Updated the hero."
    assert len(result["ops"]) == 1
    assert result["ops"][0]["value"] == "New"
    assert result["rejected"] == []


@pytest.mark.asyncio
async def test_markdown_fenced_json_is_parsed(monkeypatch):
    payload = '```json\n{"message": "Done.", "ops": []}\n```'
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await _run(payload)
    assert result["message"] == "Done."


@pytest.mark.asyncio
async def test_invalid_ops_are_reported_not_raised(monkeypatch):
    payload = '{"message": "ok", "ops": [{"op":"set_field","block":{"x":1},"path":"heading","value":"a"}]}'
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await _run(payload)
    assert result["ops"] == []
    assert len(result["rejected"]) == 1


# --- model tier clamp ---------------------------------------------------------

@pytest.mark.parametrize("plan,requested,expected", [
    # Lite is open to every plan — the upgrade funnel.
    ("free", "lite", "lite"),
    ("hosting", "lite", "lite"),
    # Paid tiers clamp DOWN on a non-premium plan rather than 403ing.
    ("free", "regular", "lite"),
    ("free", "pro", "lite"),
    ("hosting", "pro", "lite"),
    # Premium plans get what they asked for.
    ("pro", "regular", "regular"),
    ("pro", "pro", "pro"),
    ("business", "pro", "pro"),
    # Junk / missing degrades to the default.
    ("business", "bogus", "lite"),
    ("business", None, "lite"),
    ("business", {"a": 1}, "lite"),
    (None, "pro", "lite"),
])
def test_resolve_model_tier_clamps_to_plan(plan, requested, expected):
    from app.cappe.services.merlin import resolve_model_tier
    assert resolve_model_tier(requested, plan) == expected


@pytest.mark.asyncio
async def test_turn_reports_the_tier_it_used(monkeypatch):
    payload = '{"message": "Done.", "ops": []}'
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await run_merlin_turn(
        message="hi", history=[], blocks=_BLOCKS, theme={}, model_tier="pro",
    )
    assert result["tier"] == "pro"


@pytest.mark.asyncio
async def test_turn_falls_back_to_lite_on_an_unknown_tier(monkeypatch):
    payload = '{"message": "Done.", "ops": []}'
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await run_merlin_turn(
        message="hi", history=[], blocks=_BLOCKS, theme={}, model_tier="nonsense",
    )
    assert result["tier"] == "lite"


def test_every_tier_maps_to_a_real_model():
    from app.cappe.services.merlin_catalog import DEFAULT_MODEL_TIER, MODEL_TIERS
    assert DEFAULT_MODEL_TIER in MODEL_TIERS
    assert all(m.startswith("gemini-") for m in MODEL_TIERS.values())
    assert len(set(MODEL_TIERS.values())) == len(MODEL_TIERS)  # no tier aliasing another


# --- theme-intent detection ---------------------------------------------------

@pytest.mark.parametrize("message,expected", [
    # The reported failure: no theme mention at all -> preset swap must not fire.
    ("make this section animate the main text somehow", False),
    ("make the heading bigger", False),
    ("add an FAQ after the features", False),
    # Genuine theme requests.
    ("switch to the midnight theme", True),
    ("change my color scheme", True),
    ("use a different preset", True),
    ("can you restyle the site", True),
    ("update the palette please", True),
])
def test_theme_intent_detection(message, expected):
    from app.cappe.services.merlin import _THEME_INTENT_RE
    assert bool(_THEME_INTENT_RE.search(message)) is expected


@pytest.mark.asyncio
async def test_animation_request_cannot_swap_the_theme(monkeypatch):
    """End-to-end guard for the exact reported failure: the model answers an
    animation request with a theme swap + an unrelated copy edit. The theme op
    must be rejected; only the design op survives."""
    payload = json.dumps({
        "message": "I've enabled the hero shimmer effect.",
        "ops": [
            {"op": "set_theme", "key": "preset", "value": "studio"},
            {"op": "set_design", "block": "b1", "group": "motion", "key": "heading", "value": "shimmer"},
        ],
    })
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await run_merlin_turn(
        message="make this section animate the main text somehow",
        history=[], blocks=_BLOCKS, theme={}, plan="pro",
    )
    ops = result["ops"]
    assert len(ops) == 1 and ops[0]["op"] == "set_design"
    assert any("unless you ask" in r["reason"] for r in result["rejected"])
