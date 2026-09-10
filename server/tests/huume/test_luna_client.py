"""OpenAI Responses client regressions for the Luna tool loops.

Retry, back-off and deadline policy is this layer's real job and its
assertions are unchanged by the move off the Gemini-shaped adapter — only the
way a request is constructed changed.
"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from app.core.services.openai_responses import http_error_detail as _http_error_detail
from app.matcha.services.huume import luna_client
from app.matcha.services.huume.luna_client import (
    LunaSession,
    _rate_limit_delay,
    image_item,
    text_item,
    tool_output_item,
)


def test_text_items_use_the_right_content_type_per_role():
    # Not a style choice: assistant history sent as `input_text` is a hard 400.
    assert text_item("user", "first prompt") == {
        "role": "user", "content": [{"type": "input_text", "text": "first prompt"}],
    }
    assert text_item("assistant", "first reply") == {
        "role": "assistant", "content": [{"type": "output_text", "text": "first reply"}],
    }


def test_image_items_carry_a_data_url_and_default_their_mime():
    assert image_item(b"not-a-real-image", "image/png") == {
        "type": "input_image",
        "image_url": "data:image/png;base64,bm90LWEtcmVhbC1pbWFnZQ==",
    }
    assert image_item(b"x", None)["image_url"].startswith("data:application/octet-stream;base64,")


def test_tool_output_is_keyed_by_call_id_not_by_tool_name():
    # Two concurrent calls to the same tool are only distinguishable by id.
    first = tool_output_item("call_a", {"status": "ok", "n": 1})
    second = tool_output_item("call_b", {"status": "ok", "n": 2})
    assert first["call_id"] == "call_a" and second["call_id"] == "call_b"
    assert first["type"] == "function_call_output"
    assert first["output"] == '{"status":"ok","n":1}'
    assert tool_output_item("call_c", None)["output"] == "{}"


def test_http_error_detail_preserves_provider_message_without_headers():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(
        429, request=request,
        json={"error": {"code": "rate_limit_exceeded", "message": "slow down"}},
    )
    detail = _http_error_detail(httpx.HTTPStatusError("boom", request=request, response=response))
    assert detail == "rate_limit_exceeded: slow down"
    assert "Authorization" not in detail


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
async def test_create_response_records_exact_response_and_requests_high_reasoning(monkeypatch):
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

    result = await LunaSession().create_response(
        model="gpt-5.6-luna",
        input=[text_item("user", "Help")],
        instructions="Be useful",
        tools=[],
    )

    assert sent["json"]["reasoning"] == {"effort": "high"}
    assert sent["json"]["service_tier"] == "default"
    # store is stated, not inherited: the follow-up path reads server-side
    # state through previous_response_id and used to rely on the API default.
    assert sent["json"]["store"] is True
    assert len(recorded) == 1
    assert recorded[0]["model"] == "gpt-5.6-luna"
    assert isinstance(recorded[0]["latency_ms"], int)
    assert recorded[0]["response"] == provider_payload
    assert result.usage["input_tokens"] == 80
    assert result.usage["output_tokens"] == 40
    assert result.usage["output_tokens_details"]["reasoning_tokens"] == 25
    assert result.usage["input_tokens_details"]["cached_tokens"] == 30
    assert result.text == "Done."
    assert result.response_id == "resp_huume_123"


def _tool(name: str) -> dict:
    return {
        "type": "function", "name": name, "description": f"{name} tool",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
    }


async def _capture_payload(monkeypatch, **kwargs) -> dict:
    """Run one create_response against a stub transport and return the body."""
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
        luna_client, "get_settings",
        lambda: SimpleNamespace(openai_api_key="test-key"),
    )
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    await LunaSession().create_response(
        model="gpt-5.6-luna",
        input=[text_item("user", "Help")],
        instructions="Be useful",
        **kwargs,
    )
    return sent["json"]


@pytest.mark.asyncio
async def test_tool_choice_is_passed_through_as_given(monkeypatch):
    payload = await _capture_payload(
        monkeypatch, tools=[_tool("read_file")], tool_choice="required",
    )
    assert payload["tool_choice"] == "required"

    payload = await _capture_payload(
        monkeypatch, tools=[_tool("read_file")], tool_choice="none",
    )
    assert payload["tool_choice"] == "none"


@pytest.mark.asyncio
async def test_tool_choice_is_absent_unless_asked_for(monkeypatch):
    payload = await _capture_payload(monkeypatch, tools=[_tool("read_file")])
    assert "tool_choice" not in payload


@pytest.mark.asyncio
async def test_required_tool_choice_is_dropped_when_there_are_no_tools(monkeypatch):
    # OpenAI rejects tool_choice="required" with an empty tools array (HTTP 400).
    payload = await _capture_payload(monkeypatch, tools=[], tool_choice="required")
    assert payload["tools"] == []
    assert "tool_choice" not in payload


@pytest.mark.asyncio
async def test_json_response_format_is_opt_in(monkeypatch):
    payload = await _capture_payload(monkeypatch, tools=[])
    assert "text" not in payload
    payload = await _capture_payload(monkeypatch, tools=[], response_format_json=True)
    assert payload["text"] == {"format": {"type": "json_object"}}


@pytest.mark.asyncio
async def test_a_function_call_without_a_call_id_is_refused_not_deferred(monkeypatch):
    """The adapter used to let this through and fail one round later, on a
    different turn's watch, because it re-paired results by tool name."""
    sent = {}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, _url, *, headers, json):
            sent.update(json=json)
            return httpx.Response(
                200, request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"id": "resp_1", "usage": {}, "output": [
                    {"type": "function_call", "name": "read_file", "arguments": "{}"},
                ]},
            )

    async def record(**_kwargs):
        return None

    monkeypatch.setattr(luna_client, "get_settings", lambda: SimpleNamespace(openai_api_key="k"))
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    with pytest.raises(RuntimeError, match="without a name and call_id"):
        await LunaSession().create_response(
            model="gpt-5.6-luna", input=[text_item("user", "hi")], instructions="",
        )


@pytest.mark.asyncio
async def test_unparsable_tool_arguments_are_refused_not_silently_emptied(monkeypatch):
    """`{}` reads to the loop as a deliberate no-argument call."""
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, _url, *, headers, json):
            return httpx.Response(
                200, request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"id": "resp_1", "usage": {}, "output": [
                    {"type": "function_call", "call_id": "c1", "name": "read_file",
                     "arguments": "{not json"},
                ]},
            )

    async def record(**_kwargs):
        return None

    monkeypatch.setattr(luna_client, "get_settings", lambda: SimpleNamespace(openai_api_key="k"))
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    with pytest.raises(RuntimeError, match="unparsable arguments for read_file"):
        await LunaSession().create_response(
            model="gpt-5.6-luna", input=[text_item("user", "hi")], instructions="",
        )


@pytest.mark.asyncio
async def test_a_truncated_reply_is_distinguishable_from_an_empty_one(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, _url, *, headers, json):
            return httpx.Response(
                200, request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"id": "r", "usage": {}, "output": [], "status": "incomplete",
                      "incomplete_details": {"reason": "max_output_tokens"}},
            )

    async def record(**_kwargs):
        return None

    monkeypatch.setattr(luna_client, "get_settings", lambda: SimpleNamespace(openai_api_key="k"))
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    result = await LunaSession().create_response(
        model="gpt-5.6-luna", input=[text_item("user", "hi")], instructions="",
    )
    assert result.truncated is True
    assert result.text == "" and result.function_calls == []


@pytest.mark.asyncio
async def test_create_response_retries_transient_token_rate_limit(monkeypatch):
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

    result = await LunaSession().create_response(
        model="gpt-5.6-luna",
        input=[text_item("user", "Help")],
        instructions="Be useful",
        tools=[],
        before_request=before_request,
        after_request=after_request,
    )

    assert sleeps == [pytest.approx(9.925)]
    assert not responses
    assert result.text == "Done."
    assert hooks == ["before", "after", "before", "after"]
    assert [entry.get("status", "ok") for entry in recorded] == ["error", "ok"]


@pytest.mark.asyncio
async def test_create_response_skips_retry_that_exceeds_total_budget(monkeypatch):
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
        await LunaSession().create_response(
            model="gpt-5.6-luna",
            input=[text_item("user", "Help")],
            instructions="Be useful",
            tools=[],
            timeout_seconds=55.0,
        )

    assert calls == ["post"]
    assert len(recorded) == 1
    assert recorded[0]["status"] == "error"


@pytest.mark.asyncio
async def test_create_response_enforces_total_request_deadline(monkeypatch):
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
        await LunaSession().create_response(
            model="gpt-5.6-luna",
            input=[text_item("user", "Help")],
            instructions="Be useful",
            tools=[],
            timeout_seconds=0.01,
            after_request=after_request,
        )

    assert hooks == ["after"]
    assert len(recorded) == 1
    assert recorded[0]["status"] == "timeout"


@pytest.mark.asyncio
async def test_the_batch_cap_reaches_the_model_as_a_real_constraint(monkeypatch):
    """`minItems`/`maxItems` were declared on the tool and thrown away in
    translation, so the model was told the 40-cap in prose only. Root CLAUDE.md
    says the number lives in three places "so they cannot drift"; this is the
    one that had gone quiet."""
    from app.matcha.services.huume.tools import TOOLS_BY_NAME
    from app.matcha.services.scheduling.schedule_batch import MAX_BATCH_OPERATIONS

    changes = TOOLS_BY_NAME["propose_schedule_change"].parameters["properties"]["changes"]
    assert changes["minItems"] == 1
    assert changes["maxItems"] == MAX_BATCH_OPERATIONS

    payload = await _capture_payload(
        monkeypatch,
        tools=[{
            "type": "function", "name": "propose_schedule_change",
            "description": "d",
            "parameters": TOOLS_BY_NAME["propose_schedule_change"].parameters,
        }],
    )
    sent = payload["tools"][0]["parameters"]["properties"]["changes"]
    assert sent["minItems"] == 1 and sent["maxItems"] == MAX_BATCH_OPERATIONS


@pytest.mark.asyncio
async def test_two_calls_to_the_same_tool_keep_distinct_call_ids(monkeypatch):
    """The retired adapter re-paired results to calls by tool NAME, popping the
    first match — so two concurrent calls to one tool could take each other's
    result with nothing to warn on."""
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, _url, *, headers, json):
            return httpx.Response(
                200, request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                json={"id": "r", "usage": {}, "output": [
                    {"type": "function_call", "call_id": "c1", "name": "show_record",
                     "arguments": '{"record_id": "a"}'},
                    {"type": "function_call", "call_id": "c2", "name": "show_record",
                     "arguments": '{"record_id": "b"}'},
                ]},
            )

    async def record(**_kwargs):
        return None

    monkeypatch.setattr(luna_client, "get_settings", lambda: SimpleNamespace(openai_api_key="k"))
    monkeypatch.setattr(luna_client.httpx, "AsyncClient", lambda **_kwargs: Client())
    monkeypatch.setattr(luna_client, "record_openai_response", record)

    result = await LunaSession().create_response(
        model="gpt-5.6-luna", input=[text_item("user", "show me both")], instructions="",
    )
    assert [c["call_id"] for c in result.function_calls] == ["c1", "c2"]
    assert [c["arguments"]["record_id"] for c in result.function_calls] == ["a", "b"]

    outputs = [tool_output_item(c["call_id"], {"id": c["arguments"]["record_id"]})
               for c in result.function_calls]
    assert [o["call_id"] for o in outputs] == ["c1", "c2"]
    assert outputs[0]["output"] == '{"id":"a"}' and outputs[1]["output"] == '{"id":"b"}'
