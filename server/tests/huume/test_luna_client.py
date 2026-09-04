"""OpenAI Responses adapter regressions for Huume."""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

from app.matcha.services.huume import luna_client
from app.matcha.services.huume.luna_client import (
    _LunaModels,
    _http_error_detail,
    _messages,
    _rate_limit_delay,
)


def test_messages_use_responses_content_types_for_each_role():
    result = _messages([
        types.Content(role="user", parts=[types.Part(text="first prompt")]),
        types.Content(role="model", parts=[types.Part(text="first reply")]),
        types.Content(role="user", parts=[types.Part(text="second prompt")]),
    ])

    assert result == [
        {"role": "user", "content": [{"type": "input_text", "text": "first prompt"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "first reply"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "second prompt"}]},
    ]


def test_http_error_detail_preserves_provider_message_without_headers():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        400,
        request=request,
        json={"error": {"type": "invalid_request_error", "message": "Bad content type"}},
    )
    error = httpx.HTTPStatusError("400", request=request, response=response)

    assert _http_error_detail(error) == "invalid_request_error: Bad content type"


def test_messages_keep_empty_fallback_user_shaped():
    assert _messages([SimpleNamespace(role="model", parts=[])]) == [
        {"role": "user", "content": [{"type": "input_text", "text": "Hello."}]},
    ]


def test_messages_do_not_replay_assistant_images_as_user_input():
    result = _messages([
        types.Content(
            role="model",
            parts=[
                types.Part(text="Here is the image."),
                types.Part.from_bytes(data=b"not-a-real-image", mime_type="image/png"),
            ],
        ),
    ])

    assert result == [{
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Here is the image."}],
    }]


def test_rate_limit_delay_never_caps_retry_after(monkeypatch):
    monkeypatch.setattr(luna_client.random, "uniform", lambda *_args: 0.0)
    response = httpx.Response(
        429,
        headers={"retry-after": "56"},
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )

    assert _rate_limit_delay(response, 0) == 56.0


def test_rate_limit_delay_parses_composite_reset_duration(monkeypatch):
    monkeypatch.setattr(luna_client.random, "uniform", lambda *_args: 0.0)
    response = httpx.Response(
        429,
        headers={"x-ratelimit-reset-tokens": "6m0s"},
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )

    assert _rate_limit_delay(response, 0) == 360.0


def test_rate_limit_delay_prefers_request_specific_message_to_full_reset(monkeypatch):
    monkeypatch.setattr(luna_client.random, "uniform", lambda *_args: 0.0)
    response = httpx.Response(
        429,
        headers={"x-ratelimit-reset-tokens": "6m0s"},
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        json={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Rate limit reached. Please try again in 9.675s.",
            },
        },
    )

    assert _rate_limit_delay(response, 0) == 9.675


def test_rate_limit_delay_uses_longest_advertised_dimension(monkeypatch):
    monkeypatch.setattr(luna_client.random, "uniform", lambda *_args: 0.0)
    response = httpx.Response(
        429,
        headers={
            "x-ratelimit-reset-requests": "12s",
            "x-ratelimit-reset-tokens": "100ms",
            "x-ratelimit-reset-project-tokens": "3s",
        },
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        json={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Rate limit reached. Please try again in 12s.",
            },
        },
    )

    assert _rate_limit_delay(response, 0) == 12.0


@pytest.mark.asyncio
async def test_generate_content_records_exact_response_and_requests_high_reasoning(monkeypatch):
    sent = {}
    recorded = []
    provider_payload = {
        "id": "resp_huume_123",
        "model": "gpt-5.6-luna-2026-08-01",
        "status": "completed",
        "service_tier": "default",
        "output_text": "Done.",
        "usage": {
            "input_tokens": 80,
            "input_tokens_details": {
                "cached_tokens": 30,
                "cache_write_tokens": 10,
            },
            "output_tokens": 40,
            "output_tokens_details": {"reasoning_tokens": 25},
            "total_tokens": 120,
        },
    }

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return provider_payload

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, *, headers, json):
            sent.update(url=url, headers=headers, json=json)
            return Response()

    monkeypatch.setattr(luna_client, "get_settings", lambda: SimpleNamespace(openai_api_key="test-key"))
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())

    async def record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(luna_client, "record_openai_response", record)

    result = await _LunaModels().generate_content(
        model="gpt-5.6-luna",
        contents=[types.Content(role="user", parts=[types.Part(text="Help")])],
        config=SimpleNamespace(system_instruction="Be useful", tools=[]),
    )

    assert sent["json"]["reasoning"] == {"effort": "high"}
    assert sent["json"]["service_tier"] == "default"
    assert len(recorded) == 1
    assert recorded[0]["model"] == "gpt-5.6-luna"
    assert isinstance(recorded[0]["latency_ms"], int)
    assert recorded[0]["response"] == provider_payload
    assert result.usage_metadata.prompt_token_count == 80
    assert result.usage_metadata.candidates_token_count == 40
    assert result.usage_metadata.thoughts_token_count == 25
    assert result.usage_metadata.cached_content_token_count == 30
    assert result.usage_metadata.cache_write_token_count == 10


@pytest.mark.asyncio
async def test_generate_content_maps_any_function_mode_to_required_tool_choice(monkeypatch):
    sent = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, _url, *, headers, json):
            sent.update(headers=headers, json=json)
            return httpx.Response(
                200,
                request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"id": "resp_required", "output": [], "usage": {}},
            )

    async def record(**_kwargs):
        return None

    monkeypatch.setattr(
        luna_client,
        "get_settings",
        lambda: SimpleNamespace(openai_api_key="test-key"),
    )
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    await _LunaModels().generate_content(
        model="gpt-5.6-luna",
        contents=[types.Content(role="user", parts=[types.Part(text="Help")])],
        config=types.GenerateContentConfig(
            tools=[types.Tool(function_declarations=[])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode=types.FunctionCallingConfigMode.ANY,
                ),
            ),
        ),
    )

    assert sent["json"]["tool_choice"] == "required"


@pytest.mark.asyncio
async def test_generate_content_retries_transient_token_rate_limit(monkeypatch):
    responses = [
        httpx.Response(
            429,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={
                "error": {
                    "code": "rate_limit_exceeded",
                    "message": "Rate limit reached. Please try again in 9.675s.",
                },
            },
        ),
        httpx.Response(
            200,
            request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
            json={"id": "resp_retry", "output_text": "Done.", "output": [], "usage": {}},
        ),
    ]
    sleeps = []
    recorded = []
    hooks = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return responses.pop(0)

    async def sleep(delay):
        sleeps.append(delay)

    async def record(**kwargs):
        recorded.append(kwargs)

    async def before_request():
        hooks.append("before")

    async def after_request():
        hooks.append("after")

    monkeypatch.setattr(luna_client, "get_settings", lambda: SimpleNamespace(openai_api_key="test-key"))
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client.asyncio, "sleep", sleep)
    monkeypatch.setattr(luna_client.random, "uniform", lambda *_args: 0.25)
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    result = await _LunaModels().generate_content(
        model="gpt-5.6-luna",
        contents=[types.Content(role="user", parts=[types.Part(text="Help")])],
        config=SimpleNamespace(system_instruction="Be useful", tools=[]),
        before_request=before_request,
        after_request=after_request,
    )

    assert sleeps == [pytest.approx(9.925)]
    assert not responses
    assert result.text == "Done."
    assert hooks == ["before", "after", "before", "after"]
    assert [entry.get("status", "ok") for entry in recorded] == ["error", "ok"]


@pytest.mark.asyncio
async def test_generate_content_skips_retry_that_exceeds_total_budget(monkeypatch):
    response = httpx.Response(
        429,
        headers={"retry-after": "56"},
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
        json={
            "error": {
                "code": "rate_limit_exceeded",
                "message": "Please try again later.",
            },
        },
    )
    calls = []
    recorded = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            calls.append("post")
            return response

    async def fail_sleep(_delay):
        pytest.fail("the adapter must not retry before Retry-After")

    async def record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(luna_client, "get_settings", lambda: SimpleNamespace(openai_api_key="test-key"))
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client.asyncio, "sleep", fail_sleep)
    monkeypatch.setattr(luna_client.random, "uniform", lambda *_args: 0.0)
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    with pytest.raises(RuntimeError, match="retry delay 56.000s exceeds"):
        await _LunaModels().generate_content(
            model="gpt-5.6-luna",
            contents=[types.Content(role="user", parts=[types.Part(text="Help")])],
            config=SimpleNamespace(system_instruction="Be useful", tools=[]),
            timeout_seconds=55.0,
        )

    assert calls == ["post"]
    assert len(recorded) == 1
    assert recorded[0]["status"] == "error"


@pytest.mark.asyncio
async def test_generate_content_enforces_total_request_deadline(monkeypatch):
    recorded = []
    hooks = []

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            await asyncio.Event().wait()

    async def after_request():
        hooks.append("after")

    async def record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(luna_client, "get_settings", lambda: SimpleNamespace(openai_api_key="test-key"))
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    with pytest.raises(RuntimeError, match="request exceeded 0.01s total deadline"):
        await _LunaModels().generate_content(
            model="gpt-5.6-luna",
            contents=[types.Content(role="user", parts=[types.Part(text="Help")])],
            config=SimpleNamespace(system_instruction="Be useful", tools=[]),
            timeout_seconds=0.01,
            after_request=after_request,
        )

    assert hooks == ["after"]
    assert len(recorded) == 1
    assert recorded[0]["status"] == "timeout"
