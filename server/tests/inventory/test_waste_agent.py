import asyncio
from types import SimpleNamespace

from app.matcha.services.inventory.waste import agent


def test_response_text_reads_responses_message_content():
    assert agent._response_text({"output": [{"type": "message", "content": [
        {"type": "output_text", "text": "Waste is concentrated in a single area."},
    ]}]}) == "Waste is concentrated in a single area."


def test_luna_narration_uses_configured_responses_model(monkeypatch):
    payload = {}
    recorded = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "resp_waste_123",
                "model": "gpt-5.6-luna-2026-08-01",
                "status": "completed",
                "service_tier": "default",
                "output_text": "Waste appears concentrated in a recurring operating pattern.",
                "usage": {
                    "input_tokens": 120,
                    "input_tokens_details": {"cached_tokens": 20},
                    "output_tokens": 35,
                    "output_tokens_details": {"reasoning_tokens": 10},
                },
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, _url, *, headers, json):
            payload.update(headers=headers, json=json)
            return Response()

    monkeypatch.setattr(agent, "get_settings", lambda: SimpleNamespace(
        openai_api_key="test-key", openai_luna_model="gpt-5.6-luna",
    ))
    monkeypatch.setattr(agent.httpx, "AsyncClient", lambda **_kwargs: Client())

    async def record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(agent, "record_openai_response", record)

    result = asyncio.run(agent._narrate_with_luna(question="What is driving waste?", sources={"waste:reason": {}}))

    assert result == "Waste appears concentrated in a recurring operating pattern."
    assert payload["json"]["model"] == "gpt-5.6-luna"
    assert payload["json"]["reasoning"] == {"effort": "high"}
    assert payload["headers"]["Authorization"] == "Bearer test-key"
    assert recorded[0]["model"] == "gpt-5.6-luna"
    assert recorded[0]["response"]["id"] == "resp_waste_123"


def test_luna_narration_rejects_numeric_model_output(monkeypatch):
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"output_text": "Waste rose by 10%."}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(agent, "get_settings", lambda: SimpleNamespace(
        openai_api_key="test-key", openai_luna_model="gpt-5.6-luna",
    ))
    monkeypatch.setattr(agent.httpx, "AsyncClient", lambda **_kwargs: Client())

    async def record(**_kwargs):
        return None

    monkeypatch.setattr(agent, "record_openai_response", record)

    assert asyncio.run(agent._narrate_with_luna(question="Why?", sources={})) is None


def test_numeric_guard_rejects_plain_digits_without_currency_or_percent():
    assert agent._NUMERIC_NARRATION.search("Waste includes 172 discarded units.")
