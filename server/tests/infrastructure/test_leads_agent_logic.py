"""LeadsAgentService._save_lead_from_search — dedupe + insert behaviour.

Previously this file mocked `_save_lead_from_search` itself and then asserted
on the mock's return value, so it passed without exercising any product code
(and, being an unmarked `async def`, pytest could not run it at all). It now
drives the real method against a fake connection.
"""
import os
from unittest.mock import AsyncMock, patch

import pytest

# Mock config — the service reads these at construction.
os.environ.setdefault("SEARCH_API_KEY", "mock_key")
os.environ.setdefault("JINA_API_KEY", "mock_key")
os.environ.setdefault("HUNTER_API_KEY", "mock_key")

from app.config import load_settings
from app.core.models.leads_agent import GeminiAnalysis, SearchResultItem
from app.core.services import leads_agent as leads_agent_module
from app.core.services.leads_agent import LeadsAgentService


class _FakeConn:
    def __init__(self, existing_row=None):
        self.existing_row = existing_row
        self.execute_calls = []

    async def fetchrow(self, query, *args):
        if "FROM executive_leads" in query:
            return self.existing_row
        return None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "INSERT 1"


class _FakeConnContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _item():
    return SearchResultItem(
        job_id="test_job_1",
        title="CTO",
        company_name="Acme Corp",
        location="San Francisco",
        description="Looking for a CTO...",
    )


def _analysis():
    return GeminiAnalysis(
        relevance_score=8,
        is_qualified=True,
        reasoning="Good match",
        extracted_seniority="c_suite",
        extracted_domain="acme.test",
        extracted_salary_min=200000,
    )


@pytest.fixture(scope="module", autouse=True)
def _settings():
    load_settings()


@pytest.mark.asyncio
async def test_save_lead_inserts_new_lead():
    service = LeadsAgentService()
    conn = _FakeConn(existing_row=None)

    with patch.object(leads_agent_module, "get_connection", lambda: _FakeConnContext(conn)):
        created, deduped = await service._save_lead_from_search(_item(), _analysis())

    assert created is True
    assert deduped is False
    assert len(conn.execute_calls) == 1
    query, args = conn.execute_calls[0]
    assert "INSERT INTO executive_leads" in query
    assert "Acme Corp" in args
    assert "CTO" in args


@pytest.mark.asyncio
async def test_save_lead_deduplicates_existing_lead():
    service = LeadsAgentService()
    conn = _FakeConn(existing_row={"id": "existing-lead-id"})

    with patch.object(leads_agent_module, "get_connection", lambda: _FakeConnContext(conn)):
        created, deduped = await service._save_lead_from_search(_item(), _analysis())

    assert created is False
    assert deduped is True
    # A duplicate must not write a second row.
    assert conn.execute_calls == []
