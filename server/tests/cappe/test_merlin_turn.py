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

from google.genai.types import ThinkingLevel as _ThinkingLevel  # noqa: E402

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


def test_build_prompt_carries_design_principles_and_color_token_vocab():
    """2026-07-21 fix: the model must be told to prefer theme tokens over hex
    and to reach for apply_style_recipe for a 'make it look designed' ask —
    without these, op volume alone doesn't produce a theme-coherent result."""
    prompt = _build_prompt(
        message="make this look designed", history=[], blocks=_BLOCKS, theme={},
        business_name=None, business_type=None, feedback=None,
    )
    assert "PREFER tokens over hex" in prompt
    assert "apply_style_recipe" in prompt
    assert "brand-soft" in prompt  # a real token name from the shared vocab line
    assert "wireframe" in prompt   # the anti-pattern rule made it in


def test_build_prompt_includes_history_and_feedback():
    prompt = _build_prompt(
        message="now bigger",
        history=[{"role": "assistant", "content": "Done.", "ops_summary": "set hero.heading"}],
        blocks=_BLOCKS, theme={"mode": "dark"}, business_name=None, business_type=None,
        feedback="2 op(s) were invalid",
    )
    assert "set hero.heading" in prompt
    assert "FAILED VALIDATION" in prompt


def test_build_prompt_strips_noise_from_blocks_without_mutating_the_input():
    blocks = [{
        "id": "b1", "type": "hero", "heading": "Old", "subheading": "",
        "eyebrow": None, "_design": {"motion": {"effect": "fade"}, "bg": {}},
    }]
    prompt = _build_prompt(
        message="hi", history=[], blocks=blocks, theme={}, business_name=None,
        business_type=None, feedback=None,
    )
    blocks_line = next(line for line in prompt.splitlines() if line.startswith("Current blocks"))
    blocks_json = prompt.splitlines()[prompt.splitlines().index(blocks_line) + 1]
    assert '"subheading"' not in blocks_json   # empty string dropped
    assert '"eyebrow"' not in blocks_json      # null dropped
    assert '"bg"' not in blocks_json           # empty _design group dropped
    assert '"motion":{"effect":"fade"}' in blocks_json  # non-empty group kept, compact separators
    # the caller's original block dict is untouched — validate_ops still needs
    # subheading/eyebrow/bg.* at full fidelity from the same request payload.
    assert blocks[0]["subheading"] == ""
    assert blocks[0]["eyebrow"] is None
    assert blocks[0]["_design"]["bg"] == {}


# --- turn contract -----------------------------------------------------------

class _FakeResponse:
    def __init__(self, text):
        self.text = text


class _FakeModels:
    def __init__(self, behavior):
        self._behavior = behavior
        self.last_kwargs: dict = {}

    async def generate_content(self, **kwargs):
        self.last_kwargs = kwargs
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


# --- design brief (forced planning field, dropped before it reaches the client) -

@pytest.mark.asyncio
async def test_payload_with_a_plan_field_parses_and_the_plan_is_not_returned(monkeypatch):
    payload = (
        '{"plan": "Dark theme, surface is near-black — use a token-based elevate.", '
        '"message": "Styled it.", "ops": []}'
    )
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await _run(payload)
    assert result["message"] == "Styled it."
    assert "plan" not in result
    assert set(result) == {"message", "ops", "rejected", "tier"}


@pytest.mark.asyncio
async def test_payload_without_a_plan_field_still_works(monkeypatch):
    """Model omissions must not break the never-raises contract — `plan` is a
    prompt instruction, not an enforced schema field."""
    payload = '{"message": "Done.", "ops": []}'
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await _run(payload)
    assert result["message"] == "Done."
    assert result["ops"] == []


def test_system_prompt_documents_plan_before_message_and_ops():
    """Generation order in the documented shape forces the model to write the
    brief before it commits to concrete values — `plan` must lead."""
    shape_line = merlin._SYSTEM_PROMPT.split("\n\n")[1]
    assert shape_line.index('"plan"') < shape_line.index('"message"') < shape_line.index('"ops"')


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

# NOTE: plan names and tier names overlap but are different things — plan "pro"
# is a paid Cappe plan; there is deliberately no "pro" model TIER (retired: the
# heavy model has no cost guard until the token wallet exists).
@pytest.mark.parametrize("plan,requested,expected", [
    # Lite is open to every plan — the upgrade funnel.
    ("free", "lite", "lite"),
    ("hosting", "lite", "lite"),
    # Paid tiers clamp DOWN on a non-premium plan rather than 403ing.
    ("free", "regular", "lite"),
    ("hosting", "regular", "lite"),
    # Premium plans get what they asked for.
    ("pro", "regular", "regular"),
    ("business", "regular", "regular"),
    # A retired tier is junk now — must not resolve to a real model.
    ("business", "pro", "lite"),
    ("pro", "pro", "lite"),
    # Junk / missing degrades to the default.
    ("business", "bogus", "lite"),
    ("business", None, "lite"),
    ("business", {"a": 1}, "lite"),
    (None, "regular", "lite"),
    # max is premium like regular — clamps down the same way.
    ("free", "max", "lite"),
    ("hosting", "max", "lite"),
    ("pro", "max", "max"),
    ("business", "max", "max"),
])
def test_resolve_model_tier_clamps_to_plan(plan, requested, expected):
    from app.cappe.services.merlin import resolve_model_tier
    assert resolve_model_tier(requested, plan) == expected


@pytest.mark.asyncio
async def test_turn_reports_the_tier_it_used(monkeypatch):
    payload = '{"message": "Done.", "ops": []}'
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: _FakeClient(payload))
    result = await run_merlin_turn(
        message="hi", history=[], blocks=_BLOCKS, theme={}, model_tier="regular",
    )
    assert result["tier"] == "regular"


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,expect_level", [
    ("lite", _ThinkingLevel.MINIMAL),   # "thinking off" for the 3.x generation
    ("regular", _ThinkingLevel.LOW),
    ("max", _ThinkingLevel.HIGH),
])
async def test_turn_configures_thinking_per_tier(monkeypatch, tier, expect_level):
    payload = '{"message": "Done.", "ops": []}'
    fake = _FakeClient(payload)
    monkeypatch.setattr(merlin, "get_genai_client", lambda **kw: fake)
    result = await run_merlin_turn(
        message="hi", history=[], blocks=_BLOCKS, theme={}, model_tier=tier, plan="business",
    )
    assert result["tier"] == tier
    thinking = fake.aio.models.last_kwargs["config"].thinking_config
    assert thinking.thinking_level == expect_level
    # NEVER a budget. `thinking_budget` is a 2.5-era param; 3.5-flash-lite
    # 400s on it (including budget=0), which silently killed the default tier
    # for every user — the never-raises contract turned it into a friendly
    # "couldn't process that" instead of an alarm. Regression guard.
    assert thinking.thinking_budget is None


def test_no_tier_uses_a_thinking_budget():
    """The 3.x models take thinking_level only. A tier configured with a
    budget is a 400 on every single turn it serves."""
    from app.cappe.services.merlin_catalog import MODEL_TIERS
    valid = {"minimal", "low", "medium", "high"}
    for name, cfg in MODEL_TIERS.items():
        assert cfg.thinking_level in valid, f"{name}: {cfg.thinking_level!r} is not a ThinkingLevel"


def test_max_tier_gets_a_longer_timeout_than_lite():
    from app.cappe.services.merlin_catalog import MODEL_TIERS
    assert MODEL_TIERS["max"].timeout > MODEL_TIERS["lite"].timeout


def test_no_heavy_pro_tier_is_offered():
    """Guard against re-adding an unmetered expensive model by accident. `max`
    doesn't violate this — it's the SAME model as `regular` (3.6-flash)
    reconfigured with more thinking, not a distinct heavier model."""
    from app.cappe.services.merlin_catalog import MODEL_TIERS
    assert set(MODEL_TIERS) == {"lite", "regular", "max"}
    assert not any("pro-" in t.model for t in MODEL_TIERS.values())


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
    assert all(t.model.startswith("gemini-") for t in MODEL_TIERS.values())
    # No two tiers are configured identically (max/regular share a MODEL but
    # differ in thinking_level, so the ModelTier objects themselves are
    # distinct — this would only fail if a tier were a byte-for-byte dupe).
    assert len(set(MODEL_TIERS.values())) == len(MODEL_TIERS)


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
