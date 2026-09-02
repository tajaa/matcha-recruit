import asyncio
import json
from types import SimpleNamespace

from app.matcha.services.inventory import insight


def test_interpret_records_exact_openai_response(monkeypatch):
    sent = {}
    recorded = []
    provider_payload = {
        "id": "resp_insight_123",
        "model": "gpt-5.6-luna-2026-08-01",
        "status": "completed",
        "service_tier": "default",
        "output_text": json.dumps({
            "headline": "Loss points to over-ordering.",
            "diagnosis": "over_ordering",
            "action": "right_size_par",
            "confidence": "high",
            "detail": "Review {amount} before the next purchase.",
        }),
        "usage": {
            "input_tokens": 90,
            "input_tokens_details": {"cached_tokens": 15},
            "output_tokens": 45,
            "output_tokens_details": {"reasoning_tokens": 20},
            "total_tokens": 135,
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

    monkeypatch.setattr(insight, "get_redis_cache", lambda: None)
    monkeypatch.setattr(insight, "get_settings", lambda: SimpleNamespace(
        openai_api_key="test-key",
        openai_luna_model="gpt-5.6-luna",
    ))
    monkeypatch.setattr(insight.httpx, "AsyncClient", lambda **_kwargs: Client())

    async def record(**kwargs):
        recorded.append(kwargs)

    monkeypatch.setattr(insight, "record_openai_response", record)

    result = asyncio.run(insight.interpret(
        surface="forecast",
        diagnosis="over_ordering",
        tokens={"amount": "12 units"},
    ))

    assert result["detail"] == "Review 12 units before the next purchase."
    assert sent["json"]["reasoning"] == {"effort": "high"}
    assert recorded[0]["response"] == provider_payload
