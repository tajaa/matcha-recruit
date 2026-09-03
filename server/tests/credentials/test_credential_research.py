"""Credential research reconciliation for tenant-owned credential types."""

import json
from unittest import mock
from uuid import uuid4

import pytest

from app.core.services import credential_template_service as service


class _ResearchConnection:
    def __init__(self, credential_types, response):
        self.credential_types = credential_types
        self.response = response
        self.executed = []
        self.inserted_global = []
        self.prompt = ""
        self.research_log_args = None

    async def fetchrow(self, query, *args):
        if "FROM role_categories" in query:
            return {"key": "nurse", "label": "Registered Nurse", "is_clinical": True}
        raise AssertionError(f"unexpected fetchrow: {query}")

    async def fetch(self, query, *args):
        assert "FROM scoped_credential_types" in query
        return self.credential_types

    async def fetchval(self, query, *args):
        if "INSERT INTO credential_research_logs" in query:
            self.research_log_args = args
            return uuid4()
        if "SELECT id FROM scoped_credential_types" in query:
            key = args[0]
            for row in self.credential_types:
                if row["key"] == key and (row["company_id"] is None or row["company_id"] == args[1]):
                    return row["id"]
            return None
        if "INSERT INTO credential_types" in query:
            self.inserted_global.append(args)
            return uuid4()
        raise AssertionError(f"unexpected fetchval: {query}")

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if "INSERT INTO credential_requirement_templates" in query:
            self.prompt = args


class _LunaCall:
    def __init__(self, response):
        self.response = response
        self.prompt = ""
        self.kwargs = {}

    async def __call__(self, prompt, **kwargs):
        self.prompt = prompt
        self.kwargs = kwargs
        return json.dumps(self.response)


def _custom_type(company_id, *, key="custom_abc123", label="Forklift Certification", category="clearance"):
    return {
        "id": uuid4(),
        "key": key,
        "label": label,
        "category": category,
        "company_id": company_id,
    }


async def _run_research(monkeypatch, conn, company_id):
    luna_call = _LunaCall(conn.response)
    monkeypatch.setattr(
        service,
        "_luna_credentials",
        lambda: ("test-key", "gpt-5.6-luna"),
    )
    monkeypatch.setattr(service, "_generate_luna_text", luna_call)
    result = await service.research_credential_requirements(
        conn,
        state="CA",
        city=None,
        role_category_id=uuid4(),
        company_id=company_id,
    )
    return result, luna_call


@pytest.mark.asyncio
async def test_research_prompt_includes_custom_context_and_reuses_by_normalized_label(monkeypatch):
    company_id = uuid4()
    custom = _custom_type(company_id)
    conn = _ResearchConnection(
        [custom],
        {
            "requirements": [{
                "credential_type_key": "forklift_certification",
                "label": "  forklift   CERTIFICATION ",
                "category": " CLEARANCE ",
                "confidence": 0.95,
            }],
        },
    )

    result, luna_call = await _run_research(monkeypatch, conn, company_id)

    assert result[0]["credential_type_key"] == custom["key"]
    assert not conn.inserted_global
    template_insert = next(
        args for query, args in conn.executed
        if "INSERT INTO credential_requirement_templates" in query
    )
    assert template_insert[4] == custom["id"]
    assert '"key": "custom_abc123"' in luna_call.prompt
    assert '"label": "Forklift Certification"' in luna_call.prompt
    assert '"category": "clearance"' in luna_call.prompt
    assert luna_call.kwargs == {
        "api_key": "test-key",
        "model": "gpt-5.6-luna",
        "max_output_tokens": 8192,
        "json_output": True,
    }
    assert conn.research_log_args[4] == "gpt-5.6-luna"


@pytest.mark.asyncio
async def test_research_rejects_custom_key_with_mismatched_metadata_without_global_duplicate(monkeypatch):
    company_id = uuid4()
    custom = _custom_type(company_id)
    conn = _ResearchConnection(
        [custom],
        {
            "requirements": [{
                "credential_type_key": custom["key"],
                "label": "A different credential",
                "category": custom["category"],
                "confidence": 0.95,
            }],
        },
    )

    result, _client = await _run_research(monkeypatch, conn, company_id)

    assert result == []
    assert not conn.inserted_global
    assert not [
        query for query, _args in conn.executed
        if "INSERT INTO credential_requirement_templates" in query
    ]


@pytest.mark.asyncio
async def test_luna_request_uses_responses_high_reasoning_and_records_usage(monkeypatch):
    sent = {}
    provider_payload = {
        "id": "resp_credentials_123",
        "model": "gpt-5.6-luna-2026-08-01",
        "status": "completed",
        "output_text": '{"requirements": []}',
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return provider_payload

    class _HttpClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, *, headers, json):
            sent.update(url=url, headers=headers, json=json)
            return _Response()

    monkeypatch.setattr(service.httpx, "AsyncClient", lambda **_kwargs: _HttpClient())
    record = mock.AsyncMock()
    monkeypatch.setattr(service, "record_openai_response", record)

    result = await service._generate_luna_text(
        "Research credentials",
        api_key="test-key",
        model="gpt-5.6-luna",
        max_output_tokens=8192,
        json_output=True,
    )

    assert result == '{"requirements": []}'
    assert sent["url"] == "https://api.openai.com/v1/responses"
    assert sent["headers"] == {"Authorization": "Bearer test-key"}
    assert sent["json"] == {
        "model": "gpt-5.6-luna",
        "input": "Research credentials",
        "reasoning": {"effort": "high"},
        "service_tier": "default",
        "max_output_tokens": 8192,
        "text": {"format": {"type": "json_object"}},
    }
    record.assert_awaited_once_with(
        model="gpt-5.6-luna",
        latency_ms=mock.ANY,
        response=provider_payload,
    )
