"""Claude picks in Espresso's model picker: the skill engine's structured-JSON
call on Anthropic, model selection + gating, and the picker flag.

    cd server && ./venv/bin/python -m pytest tests/matcha_work/test_skill_engine_claude.py -q

No network and no database: the Anthropic client is a fake returning real SDK
`BetaMessage` objects, the ledger writer is captured, and entitlement lookups
are stubbed.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage
from google.genai import types

from app.config import load_settings
from app.core.services import anthropic_messages
from app.core.services.anthropic_messages import CLAUDE_HAIKU, CLAUDE_SONNET
from app.matcha.services.billing import entitlements_service
from app.matcha.services.matcha_work.matcha_work_ai import (
    FLASH, FLASH_LITE, GeminiProvider, _claude, _models, provider as provider_module,
)


@pytest.fixture(scope="module", autouse=True)
def _settings():
    load_settings()


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setattr(_models, "get_matcha_work_model_mode", AsyncMock(return_value="normal"))


@pytest.fixture
def claude_on(monkeypatch):
    monkeypatch.setattr(_models, "anthropic_configured", lambda: True)


def _plan(monkeypatch, plan):
    monkeypatch.setattr(entitlements_service, "resolve_plan_for_user", AsyncMock(return_value=plan))


SETTINGS = SimpleNamespace()


# --- Model selection ---------------------------------------------------------

@pytest.mark.asyncio
async def test_haiku_is_open_to_every_plan(monkeypatch, claude_on):
    _plan(monkeypatch, "free")
    assert await _models._get_model(SETTINGS, CLAUDE_HAIKU, user_id=str(uuid4())) == CLAUDE_HAIKU


@pytest.mark.asyncio
async def test_sonnet_needs_the_pro_entitlement(monkeypatch, claude_on):
    _plan(monkeypatch, "lite")
    assert await _models._get_model(SETTINGS, CLAUDE_SONNET, user_id=str(uuid4())) == FLASH
    _plan(monkeypatch, "business")
    assert await _models._get_model(SETTINGS, CLAUDE_SONNET, user_id=str(uuid4())) == CLAUDE_SONNET


@pytest.mark.asyncio
async def test_claude_pick_without_a_key_runs_gemini():
    # tests/conftest.py blanks ANTHROPIC_API_KEY.
    assert await _models._get_model(SETTINGS, CLAUDE_HAIKU) == FLASH


@pytest.mark.asyncio
async def test_stored_flash_lite_37_pick_finally_runs_flash_lite():
    # Both pickers shipped this id; it was never supported, so it ran Flash.
    assert await _models._get_model(SETTINGS, "gemini-3.7-flash-lite") == FLASH_LITE


@pytest.mark.asyncio
async def test_admin_agent_model_replaces_gemini_picks_and_the_plan_default(monkeypatch):
    monkeypatch.setattr(_models, "claude_override", AsyncMock(return_value=CLAUDE_SONNET))
    _plan(monkeypatch, "free")  # the admin's pick is not plan-gated
    uid = str(uuid4())
    assert await _models._get_model(SETTINGS, FLASH, user_id=uid) == CLAUDE_SONNET
    assert await _models._get_model(SETTINGS, "gemini-3.7-flash-lite", user_id=uid) == CLAUDE_SONNET
    assert await _models._get_model(SETTINGS, None, user_id=uid) == CLAUDE_SONNET


@pytest.mark.asyncio
async def test_explicit_claude_pick_still_wins_over_the_admin_model(monkeypatch, claude_on):
    monkeypatch.setattr(_models, "claude_override", AsyncMock(return_value=CLAUDE_SONNET))
    _plan(monkeypatch, "free")
    assert await _models._get_model(SETTINGS, CLAUDE_HAIKU, user_id=str(uuid4())) == CLAUDE_HAIKU


@pytest.mark.asyncio
async def test_a_locked_claude_pick_runs_the_admin_model_not_gemini(monkeypatch, claude_on):
    monkeypatch.setattr(_models, "claude_override", AsyncMock(return_value=CLAUDE_HAIKU))
    _plan(monkeypatch, "lite")
    assert await _models._get_model(SETTINGS, CLAUDE_SONNET, user_id=str(uuid4())) == CLAUDE_HAIKU
    monkeypatch.setattr(_models, "claude_override", AsyncMock(return_value=CLAUDE_SONNET))
    assert await _models._get_model(SETTINGS, CLAUDE_SONNET, user_id=str(uuid4())) == CLAUDE_SONNET


@pytest.mark.asyncio
async def test_gemini_only_ignores_the_admin_model_and_claude_picks(monkeypatch, claude_on):
    override = AsyncMock(return_value=CLAUDE_SONNET)
    monkeypatch.setattr(_models, "claude_override", override)
    _plan(monkeypatch, "free")
    uid = str(uuid4())
    assert await _models._get_model(SETTINGS, CLAUDE_HAIKU, user_id=uid, gemini_only=True) == FLASH
    assert await _models._get_model(SETTINGS, FLASH_LITE, user_id=uid, gemini_only=True) == FLASH_LITE
    override.assert_not_awaited()


def test_trivial_turn_downgrade_stays_on_the_picked_provider():
    assert _models.resolve_turn_model("none", "chat", CLAUDE_SONNET) == CLAUDE_HAIKU
    assert _models.resolve_turn_model("none", "chat", CLAUDE_HAIKU) == CLAUDE_HAIKU
    assert _models.resolve_turn_model("none", "chat", FLASH) == FLASH_LITE
    assert _models.resolve_turn_model("low", "chat", CLAUDE_SONNET) == CLAUDE_SONNET
    assert _models.resolve_turn_model("none", "offer_letter", CLAUDE_SONNET) == CLAUDE_SONNET


# --- Gemini contents → Messages ----------------------------------------------

def test_contents_translate_to_messages():
    contents = [
        types.Content(role="model", parts=[types.Part(text="Earlier reply")]),
        types.Content(role="user", parts=[
            types.Part.from_bytes(data=b"\x89PNG", mime_type="image/png"),
            types.Part.from_bytes(data=b"%PDF", mime_type="application/pdf"),
            types.Part(text="   "),
        ]),
        types.Content(role="user", parts=[types.Part(text="Draft the offer")]),
        types.Content(role="model", parts=[types.Part(text="Draft ready")]),
    ]
    messages = _claude.to_messages(contents)
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant", "user"]
    user = messages[2]["content"]
    assert user[0]["type"] == "image" and user[0]["source"]["media_type"] == "image/png"
    assert user[1] == {"type": "text", "text": "Draft the offer"}  # PDF + blank text dropped
    assert messages[-1]["content"][0]["text"] == "Continue."


# --- The Claude call -----------------------------------------------------------

def _message(text, *, model=CLAUDE_HAIKU, usage=None):
    return BetaMessage.model_validate({
        "id": "msg_1", "type": "message", "role": "assistant", "model": model,
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": usage or {"input_tokens": 100, "output_tokens": 40,
                           "cache_read_input_tokens": 900, "cache_creation_input_tokens": 0},
    })


class _FakeClient:
    def __init__(self, outcome):
        self.outcome = outcome
        self.params = None
        self.options = None
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def with_options(self, **kwargs):
        self.options = kwargs
        return self

    async def _create(self, **params):
        self.params = params
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.fixture
def ledger(monkeypatch):
    rows = []

    async def record(**kwargs):
        rows.append(kwargs)

    monkeypatch.setattr(_claude, "record_anthropic_response", record)
    return rows


@pytest.mark.asyncio
async def test_call_claude_caches_the_static_prompt_and_reports_usage(monkeypatch, ledger):
    fake = _FakeClient(_message('{"reply": "Hi"}', model=CLAUDE_SONNET))
    monkeypatch.setattr(_claude, "get_async_client", lambda: fake)
    text, usage = await _claude.call_claude(
        static_prompt="STATIC", dynamic_prompt="DYNAMIC",
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
        model=CLAUDE_SONNET, thinking_level="high", timeout_seconds=30,
    )
    assert text == '{"reply": "Hi"}'
    static, dynamic = fake.params["system"]
    assert static == {"type": "text", "text": "STATIC", "cache_control": {"type": "ephemeral"}}
    assert dynamic["text"].startswith("DYNAMIC") and "exactly one JSON object" in dynamic["text"]
    assert fake.params["output_config"] == {"effort": "high"}
    assert fake.params["fallbacks"] == "default"  # Sonnet's server-side refusal fallback
    assert fake.options == {"timeout": 30}
    # prompt_tokens is the whole prompt, cache reads included — the split
    # calculate_call_cost prices.
    assert usage == {"prompt_tokens": 1000, "completion_tokens": 40, "total_tokens": 1040,
                     "cached_tokens": 900, "estimated": False, "model": CLAUDE_SONNET}
    assert ledger[0]["message"]["id"] == "msg_1"


@pytest.mark.asyncio
async def test_call_claude_effort_follows_the_thinking_level(monkeypatch, ledger):
    for level, effort in (("none", "low"), ("low", "medium"), ("high", "high")):
        fake = _FakeClient(_message("{}"))
        monkeypatch.setattr(_claude, "get_async_client", lambda fake=fake: fake)
        await _claude.call_claude(static_prompt="S", dynamic_prompt="D", contents=[], model=CLAUDE_HAIKU,
                                  thinking_level=level, timeout_seconds=5)
        assert fake.params["output_config"] == {"effort": effort}
        assert "fallbacks" not in fake.params


@pytest.mark.asyncio
async def test_call_claude_records_and_raises_on_api_errors(monkeypatch, ledger):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    monkeypatch.setattr(_claude, "get_async_client", lambda: _FakeClient(anthropic.APITimeoutError(request=request)))
    with pytest.raises(RuntimeError):
        await _claude.call_claude(static_prompt="S", dynamic_prompt="D", contents=[], model=CLAUDE_HAIKU,
                                  thinking_level="low", timeout_seconds=5)
    assert ledger[0]["status"] == "timeout"


def test_usage_absent_is_none():
    assert _claude._usage(SimpleNamespace(), CLAUDE_HAIKU) is None


# --- The provider routes a Claude pick --------------------------------------

@pytest.mark.asyncio
async def test_generate_runs_a_claude_pick_through_the_shared_parser(monkeypatch):
    reply = json.dumps({
        "mode": "skill", "skill": "offer_letter", "operation": "update", "confidence": 0.9,
        "reply": "Drafted.", "updates": {"candidate_name": "Ana", "not_a_field": "x"},
    })
    fake_call = AsyncMock(return_value=(reply, {"prompt_tokens": 1, "model": CLAUDE_HAIKU}))
    monkeypatch.setattr(provider_module, "_get_model", AsyncMock(return_value=CLAUDE_HAIKU))
    monkeypatch.setattr(provider_module, "call_claude", fake_call)
    provider = GeminiProvider()
    with patch.object(provider, "_call_gemini") as gemini:
        out = await provider.generate(
            messages=[{"role": "user", "content": "Draft an offer letter for Ana as a senior engineer"}],
            current_state={"skill": "offer_letter"},
        )
    gemini.assert_not_called()
    assert out.assistant_reply == "Drafted."
    assert out.structured_update == {"candidate_name": "Ana"}  # off-skill field filtered
    assert out.token_usage == {"prompt_tokens": 1, "model": CLAUDE_HAIKU}
    kwargs = fake_call.await_args.kwargs
    assert kwargs["model"] == CLAUDE_HAIKU and kwargs["contents"]


@pytest.mark.asyncio
async def test_generate_claude_failure_is_the_usual_retry_reply(monkeypatch):
    monkeypatch.setattr(provider_module, "_get_model", AsyncMock(return_value=CLAUDE_SONNET))
    monkeypatch.setattr(provider_module, "call_claude", AsyncMock(side_effect=RuntimeError("boom")))
    out = await GeminiProvider().generate(messages=[{"role": "user", "content": "Summarize this"}],
                                          current_state={})
    assert out.assistant_reply.startswith("I encountered an error")


@pytest.mark.asyncio
async def test_generate_claude_timeout_is_the_usual_slow_reply(monkeypatch):
    import asyncio

    monkeypatch.setattr(provider_module, "_get_model", AsyncMock(return_value=CLAUDE_HAIKU))
    monkeypatch.setattr(provider_module, "call_claude", AsyncMock(side_effect=asyncio.TimeoutError()))
    out = await GeminiProvider().generate(messages=[{"role": "user", "content": "Summarize this"}],
                                          current_state={})
    assert out.assistant_reply.startswith("I'm taking too long")


@pytest.mark.asyncio
async def test_payer_mode_keeps_gemini_search_on_a_claude_pick(monkeypatch):
    get_model = AsyncMock(return_value=FLASH)
    monkeypatch.setattr(provider_module, "_get_model", get_model)
    seen = {}

    class _Models:
        def generate_content(self, model, contents, config):
            seen["model"] = model
            return SimpleNamespace(text="Covered under LCD L1234.", usage_metadata=None)

    provider = GeminiProvider()
    provider._client = SimpleNamespace(models=_Models())
    out = await provider.generate(messages=[{"role": "user", "content": "Is CPT 99213 covered?"}],
                                  current_state={}, payer_mode_prompt="PAYER", model_override=CLAUDE_HAIKU)
    assert seen["model"] == FLASH
    assert out.assistant_reply == "Covered under LCD L1234."
    assert get_model.await_args.kwargs["gemini_only"] is True


# --- The picker flag ------------------------------------------------------------

@pytest.mark.asyncio
async def test_entitlements_say_whether_claude_is_available(monkeypatch):
    _plan(monkeypatch, "pro")
    out = await entitlements_service.resolve_entitlements(uuid4(), None)
    assert out["workspace"]["claude_models"] is False
    assert out["workspace"]["agent_model"] is None
    monkeypatch.setattr(anthropic_messages, "anthropic_configured", lambda: True)
    monkeypatch.setattr(anthropic_messages, "claude_override", AsyncMock(return_value=CLAUDE_HAIKU))
    out = await entitlements_service.resolve_entitlements(uuid4(), None)
    assert out["workspace"]["claude_models"] is True
    assert out["workspace"]["agent_model"] == CLAUDE_HAIKU
    assert out["features"]["ai_model_pro"] is True
