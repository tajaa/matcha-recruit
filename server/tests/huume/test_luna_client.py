"""OpenAI Responses adapter regressions for Huume."""

from types import SimpleNamespace

import httpx
import pytest
from google.genai import types

from app.matcha.services.huume import luna_client
from app.matcha.services.huume.luna_client import _LunaModels, _http_error_detail, _messages


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
