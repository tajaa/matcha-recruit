"""The schedule assistant's model picker: Luna by default, Claude Haiku 5.5 or
Sonnet 5.5 on request.

    cd server && ./venv/bin/python -m pytest tests/huume/test_schedule_model_picker.py -q

No network and no database: the Anthropic client is a fake that returns real
SDK `BetaMessage` objects, and the ledger writer is captured in memory.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import get_args
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import anthropic
import httpx2
import pytest
from anthropic.types.beta import BetaMessage

from app.core.services import ai_usage, rate_limiter
from app.matcha.models.matcha_work.matcha_work import SendMessageRequest
from app.matcha.services.billing.model_pricing import calculate_call_cost
from app.matcha.services.huume import agent, claude_client, routing, schedule_profile_skill
from app.matcha.services.huume.luna_client import LunaResponse, image_item, text_item, tool_output_item
from app.matcha.services.huume.scope import HuumeSurfaceContext, SCHEDULE_LOOKUP_TOPICS, SCHEDULE_TOOLS


# --- Registry ---------------------------------------------------------------

def test_request_literal_matches_the_picker_registry():
    field = SendMessageRequest.model_fields["huume_model"]
    literal = next(arg for arg in get_args(field.annotation) if get_args(arg))
    assert set(get_args(literal)) == {choice.id for choice in routing.SCHEDULE_MODEL_CHOICES}


def test_unknown_or_missing_model_resolves_to_luna():
    assert routing.resolve_model_choice(None).id == routing.LUNA
    assert routing.resolve_model_choice("gpt-4o").id == routing.LUNA
    assert routing.resolve_model_choice(routing.CLAUDE_HAIKU).provider == "anthropic"


def test_claude_is_only_offered_with_a_key():
    without = routing.schedule_model_options(anthropic_configured=False)
    assert [m["id"] for m in without] == [routing.LUNA]
    with_key = routing.schedule_model_options(anthropic_configured=True)
    assert [m["id"] for m in with_key] == [routing.LUNA, routing.CLAUDE_HAIKU, routing.CLAUDE_SONNET]
    assert with_key[1]["label"] == "Claude Haiku 5.5"


def test_rate_limiter_has_an_anthropic_bucket(monkeypatch):
    monkeypatch.setattr("app.config.get_settings", lambda: SimpleNamespace(
        anthropic_hourly_limit=7, anthropic_daily_limit=70,
        openai_hourly_limit=1, openai_daily_limit=1, gemini_hourly_limit=1, gemini_daily_limit=1,
    ))
    limiter = rate_limiter.ApiRateLimiter(provider="anthropic")
    assert (limiter.provider, limiter.hourly_limit, limiter.daily_limit) == ("anthropic", 7, 70)


# --- Pricing ----------------------------------------------------------------

def test_anthropic_cost_counts_cache_and_not_thinking_twice():
    cost = ai_usage.compute_cost(
        "anthropic", "claude-sonnet-5-5", 10_000, 1_000, 999, cached_tokens=4_000, cache_write_tokens=1_000,
    )
    expected = (5_000 * 2.00 + 4_000 * 0.20 + 1_000 * 2.00 * 1.25 + 1_000 * 10.00) / 1_000_000
    assert cost == pytest.approx(expected)


def test_haiku_long_prompt_reprices_the_whole_request():
    short = ai_usage.compute_cost("anthropic", "claude-haiku-5-5", 100_000, 1_000, None)
    long = ai_usage.compute_cost("anthropic", "claude-haiku-5-5", 100_001, 1_000, None)
    assert short == pytest.approx((100_000 * 0.10 + 1_000 * 0.50) / 1_000_000)
    assert long == pytest.approx((100_001 * 0.50 + 1_000 * 2.50) / 1_000_000)


def test_usage_event_cost_for_claude_does_not_add_thinking():
    with_thinking = calculate_call_cost("claude-sonnet-5-5", 1_000_000, 100_000, thinking_tokens=50_000)
    assert with_thinking == Decimal("3.000000")
    assert calculate_call_cost("claude-haiku-5-5", 1_000_000, 0, cached_tokens=1_000_000) == Decimal("0.010000")


@pytest.mark.asyncio
async def test_record_anthropic_response_builds_a_whole_prompt_row(monkeypatch):
    rows = []
    monkeypatch.setattr(ai_usage, "LOGGING_ENABLED", True)
    monkeypatch.setattr(ai_usage, "_record_async", AsyncMock(side_effect=rows.append))
    await ai_usage.record_anthropic_response(model="claude-haiku-5-5", latency_ms=12, message={
        "id": "msg_1", "model": "claude-haiku-5-5", "stop_reason": "tool_use",
        "usage": {"input_tokens": 100, "cache_read_input_tokens": 50,
                  "cache_creation_input_tokens": 10, "output_tokens": 20},
    })
    await ai_usage.record_anthropic_response(model="claude-haiku-5-5", latency_ms=5, error="boom")
    ok, failed = rows
    assert (ok["provider"], ok["input_tokens"], ok["cached_tokens"], ok["cache_write_tokens"]) == (
        "anthropic", 160, 50, 10,
    )
    assert ok["provider_status"] == "tool_use" and ok["status"] == "ok" and ok["cost_usd"] > 0
    assert failed["status"] == "error" and failed["input_tokens"] is None and failed["cost_usd"] is None


@pytest.mark.asyncio
async def test_record_anthropic_response_respects_the_kill_switch(monkeypatch):
    writer = AsyncMock()
    monkeypatch.setattr(ai_usage, "LOGGING_ENABLED", False)
    monkeypatch.setattr(ai_usage, "_record_async", writer)
    await ai_usage.record_anthropic_response(model="claude-haiku-5-5", latency_ms=1)
    writer.assert_not_awaited()


# --- Item conversion --------------------------------------------------------

def test_to_messages_maps_text_images_and_batches_tool_results():
    png = image_item(b"\x89PNG", "image/png")
    pdf = image_item(b"%PDF", "application/pdf")
    items = [
        text_item("assistant", "Earlier reply"),
        {"role": "user", "content": [png, pdf, {"type": "input_text", "text": "  "}]},
        text_item("user", "Assign Elena"),
        tool_output_item("toolu_1", {"ok": True}),
        tool_output_item("toolu_2", None),
    ]
    messages = claude_client.to_messages(items)
    assert [m["role"] for m in messages] == ["assistant", "user"]
    user = messages[1]["content"]
    assert user[0]["type"] == "image" and user[0]["source"]["media_type"] == "image/png"
    # The PDF and the blank text are dropped; same-role turns merged; both
    # tool results land in one user message.
    assert user[1] == {"type": "text", "text": "Assign Elena"}
    assert [b["tool_use_id"] for b in user[2:]] == ["toolu_1", "toolu_2"]
    assert user[3]["content"] == "{}"


def test_image_block_rejects_non_data_urls():
    assert claude_client._image_block("https://example.com/a.png") is None
    assert claude_client._image_block("data:image/png,raw") is None


# --- Session ----------------------------------------------------------------

def _message(*, content, stop_reason="end_turn", model="claude-haiku-5-5", usage=None):
    return BetaMessage.model_validate({
        "id": f"msg_{uuid4().hex[:8]}", "type": "message", "role": "assistant", "model": model,
        "content": content, "stop_reason": stop_reason, "stop_sequence": None,
        "usage": usage or {"input_tokens": 10, "output_tokens": 5,
                           "cache_read_input_tokens": 3, "cache_creation_input_tokens": 2},
    })


class _FakeAnthropic:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def with_options(self, **kwargs):
        self.options = kwargs
        return self

    async def _create(self, **params):
        # Snapshot: the session reuses its history list across calls.
        self.calls.append({**params, "messages": [dict(m) for m in params["messages"]]})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture
def ledger(monkeypatch):
    rows = []

    async def record(**kwargs):
        rows.append(kwargs)

    monkeypatch.setattr(claude_client, "record_anthropic_response", record)
    return rows


@pytest.mark.asyncio
async def test_session_chains_the_turn_and_parses_tool_calls(ledger):
    fake = _FakeAnthropic([
        _message(content=[
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "Checking."},
            {"type": "tool_use", "id": "toolu_1", "name": "get_schedule_overview", "input": {"x": 1}},
        ], stop_reason="tool_use"),
        _message(content=[{"type": "text", "text": "Done."}]),
    ])
    hooks = []
    session = claude_client.ClaudeSession(client=fake)

    async def before():
        hooks.append("before")

    async def after():
        hooks.append("after")

    first = await session.create_response(
        model=routing.CLAUDE_HAIKU, input=[text_item("user", "Fill Monday")], instructions="SYSTEM",
        tools=[{"type": "function", "name": "get_schedule_overview", "description": "d",
                "parameters": {"type": "object", "properties": {}}}],
        timeout_seconds=30, before_request=before, after_request=after,
    )
    assert first.function_calls == [{"call_id": "toolu_1", "name": "get_schedule_overview", "arguments": {"x": 1}}]
    assert first.text == "Checking." and not first.truncated
    assert first.usage == {"input_tokens": 15, "output_tokens": 5, "total_tokens": 20,
                           "input_tokens_details": {"cached_tokens": 3}, "output_tokens_details": {}}
    assert session.previous_response_id == first.response_id

    second = await session.create_response(
        model=routing.CLAUDE_HAIKU, input=[tool_output_item("toolu_1", {"ok": True})], instructions="SYSTEM",
    )
    assert second.text == "Done."

    call1, call2 = fake.calls
    assert call1["system"] == "SYSTEM" and call1["tools"][0]["input_schema"] == {"type": "object", "properties": {}}
    assert call1["thinking"] == {"type": "adaptive"} and call1["output_config"] == {"effort": "medium"}
    assert "fallbacks" not in call1  # Haiku has no server-side fallback
    assert 0 < fake.options["timeout"] <= 60.0
    # The follow-up resends the turn with the reply appended unchanged —
    # thinking block and signature included — then the tool result.
    assert [m["role"] for m in call2["messages"]] == ["user", "assistant", "user"]
    assert call2["messages"][1]["content"][0].signature == "sig"
    assert call2["messages"][2]["content"][0]["tool_use_id"] == "toolu_1"
    assert hooks == ["before", "after"]
    assert len(ledger) == 2 and ledger[0]["message"]["usage"]["input_tokens"] == 10


@pytest.mark.asyncio
async def test_sonnet_opts_into_server_side_fallback(ledger):
    fake = _FakeAnthropic([_message(content=[{"type": "text", "text": "Hi"}], model="claude-sonnet-5-5")])
    session = claude_client.ClaudeSession(client=fake)
    await session.create_response(model=routing.CLAUDE_SONNET, input=[text_item("assistant", "Earlier")],
                                  instructions="")
    params = fake.calls[0]
    assert params["fallbacks"] == "default" and params["betas"] == ["server-side-fallback-2026-07-01"]
    # A conversation must open and close on the user.
    assert params["messages"][0]["role"] == "user" and params["messages"][-1]["role"] == "user"


@pytest.mark.asyncio
async def test_refusal_and_max_tokens_read_as_truncated(ledger):
    fake = _FakeAnthropic([
        _message(content=[], stop_reason="refusal"),
        _message(content=[{"type": "text", "text": "partial"}], stop_reason="max_tokens"),
    ])
    session = claude_client.ClaudeSession(client=fake)
    refused = await session.create_response(model=routing.CLAUDE_HAIKU, input=[text_item("user", "x")], instructions="")
    assert refused.truncated and refused.text == "I can't help with that request."
    capped = await session.create_response(model=routing.CLAUDE_HAIKU, input=[text_item("user", "y")], instructions="")
    assert capped.truncated and capped.incomplete_details == {"reason": "max_tokens"}


def _request():
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.asyncio
@pytest.mark.parametrize("error, status", [
    (anthropic.APITimeoutError(request=_request()), "timeout"),
    (anthropic.APIConnectionError(request=_request()), "error"),
    (anthropic.BadRequestError("bad", response=httpx2.Response(400, request=_request()), body=None), "error"),
])
async def test_api_errors_are_recorded_then_raised(ledger, error, status):
    after = AsyncMock()
    session = claude_client.ClaudeSession(client=_FakeAnthropic([error]))
    with pytest.raises(RuntimeError):
        await session.create_response(model=routing.CLAUDE_HAIKU, input=[text_item("user", "x")],
                                      instructions="", after_request=after)
    assert ledger[0]["status"] == status
    after.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancellation_is_recorded(ledger):
    import asyncio
    session = claude_client.ClaudeSession(client=_FakeAnthropic([asyncio.CancelledError()]))
    with pytest.raises(asyncio.CancelledError):
        await session.create_response(model=routing.CLAUDE_HAIKU, input=[text_item("user", "x")], instructions="")
    assert ledger[0]["status"] == "timeout"


@pytest.mark.asyncio
async def test_session_requires_a_key_and_a_positive_deadline(monkeypatch):
    from app.core.services import anthropic_messages

    monkeypatch.setattr(anthropic_messages, "_client", None)
    monkeypatch.setattr(anthropic_messages, "get_settings", lambda: SimpleNamespace(anthropic_api_key=None))
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await claude_client.ClaudeSession().create_response(model=routing.CLAUDE_HAIKU, input=[], instructions="")
    with pytest.raises(ValueError):
        await claude_client.ClaudeSession(client=_FakeAnthropic([])).create_response(
            model=routing.CLAUDE_HAIKU, input=[], instructions="", timeout_seconds=0,
        )
    monkeypatch.setattr(anthropic_messages, "get_settings", lambda: SimpleNamespace(anthropic_api_key="sk-test"))
    assert isinstance(claude_client.ClaudeSession()._get_client(), anthropic.AsyncAnthropic)
    assert isinstance(claude_client.get_claude_client(), claude_client.ClaudeSession)


# --- The loop picks the provider -------------------------------------------

class _RecordingLimiter:
    providers: list[str] = []

    def __init__(self, provider="gemini"):
        _RecordingLimiter.providers.append(provider)

    async def check_limit(self, *args, **kwargs):
        return None

    async def record_call(self, *args, **kwargs):
        return None


def _schedule_context(model):
    return HuumeSurfaceContext(
        surface="schedule_assistant", location_id=uuid4(),
        week_start=date(2026, 8, 23), week_end=date(2026, 8, 30),
        allowed_tools=SCHEDULE_TOOLS, allowed_lookup_topics=SCHEDULE_LOOKUP_TOPICS, model=model,
    )


async def _run(monkeypatch, surface_context):
    _RecordingLimiter.providers = []
    luna, claude = MagicMock(), MagicMock()
    reply = LunaResponse(response_id="r", text="All set.",
                         usage={"input_tokens": 10, "output_tokens": 2, "total_tokens": 12})
    luna.create_response = AsyncMock(return_value=reply)
    claude.create_response = AsyncMock(return_value=reply)
    monkeypatch.setattr(agent, "get_luna_client", lambda: luna)
    monkeypatch.setattr(agent, "get_claude_client", lambda: claude)
    monkeypatch.setattr(agent, "ApiRateLimiter", _RecordingLimiter)
    monkeypatch.setattr(schedule_profile_skill, "context_block", AsyncMock(return_value=""))
    frames = [frame async for frame in agent.run_huume_turn(
        thread_id=uuid4(), company_id=uuid4(), user_id=uuid4(), user_role="client",
        history=[{"role": "user", "content": "what's open this week"}], current_state={},
        company_name="Acme", features={"huume": True, "matcha_work": True, "employee_schedule": True},
        integrations={}, surface_context=surface_context,
    )]
    result = next(f["data"] for f in frames if f["type"] == "huume_result")
    return result, luna, claude


@pytest.mark.asyncio
async def test_schedule_turn_runs_on_the_picked_claude_model(monkeypatch):
    result, luna, claude = await _run(monkeypatch, _schedule_context(routing.CLAUDE_SONNET))
    luna.create_response.assert_not_awaited()
    assert claude.create_response.await_args.kwargs["model"] == routing.CLAUDE_SONNET
    assert _RecordingLimiter.providers == ["anthropic"]
    assert result["token_usage"]["model"] == routing.CLAUDE_SONNET
    assert result["message"] == "All set."


@pytest.mark.asyncio
async def test_default_schedule_turn_stays_on_luna(monkeypatch):
    result, luna, claude = await _run(monkeypatch, _schedule_context(None))
    claude.create_response.assert_not_awaited()
    assert luna.create_response.await_args.kwargs["model"] == routing.LUNA
    assert _RecordingLimiter.providers == ["openai"]
    assert result["token_usage"]["model"] == routing.LUNA


@pytest.mark.asyncio
async def test_picker_is_ignored_off_the_schedule_surface(monkeypatch):
    _result, luna, claude = await _run(monkeypatch, HuumeSurfaceContext(model=routing.CLAUDE_HAIKU))
    claude.create_response.assert_not_awaited()
    luna.create_response.assert_awaited()


# --- Session endpoint -------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("key, ids", [
    (None, [routing.LUNA]),
    ("sk-test", [routing.LUNA, routing.CLAUDE_HAIKU, routing.CLAUDE_SONNET]),
])
async def test_session_endpoint_lists_available_models(monkeypatch, key, ids):
    from app.matcha.routes.employee_schedule import assistant as route

    monkeypatch.setattr(route, "require_company_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(route, "_require_schedule_huume", AsyncMock())
    monkeypatch.setattr(route, "get_or_create_schedule_assistant_session", AsyncMock(return_value={"session_id": "s"}))
    monkeypatch.setattr(route, "anthropic_configured", lambda: bool(key))
    body = route.ScheduleAssistantSessionRequest(location_id=uuid4(), week_start=date(2026, 8, 23))
    result = await route.create_schedule_assistant_session(body, current_user=SimpleNamespace(id=uuid4(), role="client"))
    assert [m["id"] for m in result["available_models"]] == ids


# --- The platform "Agent model" setting --------------------------------------

@pytest.mark.asyncio
async def test_platform_setting_routes_every_surface_to_claude(monkeypatch):
    monkeypatch.setattr(agent, "claude_override", AsyncMock(return_value=routing.CLAUDE_HAIKU))
    result, luna, claude = await _run(monkeypatch, HuumeSurfaceContext())
    luna.create_response.assert_not_awaited()
    assert claude.create_response.await_args.kwargs["model"] == routing.CLAUDE_HAIKU
    assert _RecordingLimiter.providers == ["anthropic"]
    assert result["token_usage"]["model"] == routing.CLAUDE_HAIKU


@pytest.mark.asyncio
async def test_a_schedule_pick_beats_the_platform_setting(monkeypatch):
    override = AsyncMock(return_value=routing.CLAUDE_SONNET)
    monkeypatch.setattr(agent, "claude_override", override)
    _result, luna, claude = await _run(monkeypatch, _schedule_context(routing.LUNA))
    claude.create_response.assert_not_awaited()
    luna.create_response.assert_awaited()
    override.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_endpoint_defaults_to_the_platform_setting(monkeypatch):
    from app.matcha.routes.employee_schedule import assistant as route

    monkeypatch.setattr(route, "require_company_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(route, "_require_schedule_huume", AsyncMock())
    monkeypatch.setattr(route, "get_or_create_schedule_assistant_session", AsyncMock(return_value={"session_id": "s"}))
    monkeypatch.setattr(route, "anthropic_configured", lambda: True)
    monkeypatch.setattr(route, "claude_override", AsyncMock(return_value=routing.CLAUDE_HAIKU))
    body = route.ScheduleAssistantSessionRequest(location_id=uuid4(), week_start=date(2026, 8, 23))
    result = await route.create_schedule_assistant_session(body, current_user=SimpleNamespace(id=uuid4(), role="client"))
    assert result["default_model"] == routing.CLAUDE_HAIKU
