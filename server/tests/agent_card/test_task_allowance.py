"""One monthly allowance for cards, job searches and (soon) Espresso tasks."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.matcha_work.agent_tasks import allowance
from tests.agent_runtime.helpers import FakeConn, connection


def test_plans_and_weights():
    assert allowance.limit_for_plan("pro") == 60 and allowance.limit_for_plan("business") == 150
    assert allowance.limit_for_plan("lite") == 0 and allowance.limit_for_plan(None) == 0
    # Today's totals still fit: 40 card runs + 4 job searches on Pro.
    assert 40 * allowance.WEIGHTS["agent_card"] + 4 * allowance.WEIGHTS["job_search"] == 60


def test_card_rounds():
    assert [allowance.card_round_cost(n) for n in range(1, 8)] == [1, 0, 0, 0, 0, 1, 1]


def test_over():
    assert not allowance.over(None, 10_000, 5)  # an admin
    assert not allowance.over(60, 60, 0)  # free work
    assert not allowance.over(60, 55, 5) and allowance.over(60, 56, 5)


def test_as_count():
    usage = allowance.usage_payload(60, 23)
    assert allowance.as_count(usage, 5) == {**usage, "limit": 12, "used": 5, "remaining": 7}
    assert allowance.as_count(allowance.usage_payload(60, 70), 5)["remaining"] == 0
    assert allowance.as_count(usage, 1)["remaining"] == 37


@pytest.mark.asyncio
async def test_used_units_sums_both_sources_in_one_query():
    user = uuid4()
    conn = FakeConn().on("FROM mw_project_agent_runs r, month", 17)
    assert await allowance.used_units(conn, user) == 17
    [(_method, query, args)] = conn.calls
    assert "r.kind = 'card_agent'" in query and "s.status <> 'failed'" in query
    assert args == (user, allowance.FREE_CARD_SENDBACKS, 1, 5)
    assert await allowance.used_units(FakeConn(), user) == 0


@pytest.mark.asyncio
async def test_task_usage_and_lock(monkeypatch):
    conn = FakeConn().on("FROM mw_project_agent_runs r, month", 12)
    monkeypatch.setattr(allowance, "connection_or_direct", connection(conn))
    monkeypatch.setattr(allowance, "resolve_plan_for_user", AsyncMock(return_value="business"))
    usage = await allowance.task_usage(uuid4())
    assert (usage["limit"], usage["used"], usage["remaining"]) == (150, 12, 138)
    user = uuid4()
    await allowance.lock(conn, user)
    assert conn.ran("pg_advisory_xact_lock")[0][2] == (f"{user}:task_allowance",)
