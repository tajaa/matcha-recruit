"""The board receives frozen week rows while thread/model state stays compact."""

import json
from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import schedule_cost_projection as projection
from app.matcha.services.scheduling.schedule_review import compact_review


def full_week_review():
    return {
        "proposal_id": str(uuid4()), "kind": "week_draft", "compliance_status": "verified",
        "assignments": [
            {"shift_id": f"autopilot:{i}", "employee_id": str(uuid4()),
             "employee_name": f"Crew {i}", "role": "Barista", "verdict": "ok",
             "starts_at": "2026-10-11T07:00:00Z", "ends_at": "2026-10-11T13:30:00Z"}
            for i in range(28)
        ],
        "unfilled": [], "rejected": [], "advisories": [], "findings": [],
        "employees": [], "jurisdiction": {}, "cost": {"after": 900, "by_employee": {"crew": 900}},
    }


def compact_week_state(review):
    return {"huume_action": {
        "type": "schedule_week_draft", "status": "proposed", "origin": "manual",
        "confirm_id": "same-confirmation", "generation_run_id": str(uuid4()),
        "review": compact_review(review),
        "demand_model": {"forecast_sales_week": 14000, "days": [], "labor": {"labor_pct": 20}},
    }}


def connection(proposal):
    conn = AsyncMock()
    conn.transaction = MagicMock(side_effect=lambda: AsyncMock())
    conn.fetchrow.return_value = {"proposal": proposal}
    return conn


async def project(state, conn, **kwargs):
    return await projection.project_schedule_ui_state(
        state, company_id=uuid4(), thread_id=uuid4(), location_id=uuid4(),
        week_start=date(2026, 10, 11), conn=conn, **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("include_cost", [True, False])
@pytest.mark.parametrize("encoded", [True, False])
async def test_full_frozen_week_is_returned_without_changing_compact_state_or_consent(include_cost, encoded):
    review = full_week_review()
    proposal = {"schedule_review": review}
    conn = connection(json.dumps(proposal) if encoded else proposal)
    state = compact_week_state(review)
    original = deepcopy(state)
    result = await project(state, conn, include_cost=include_cost)
    action = result["huume_action"]
    assert len(action["review"]["assignments"]) == 28
    assert action["review"]["assignments"] == review["assignments"]
    assert action["review"]["demand_model"]["forecast_sales_week"] == 14000
    assert ("cost" in action["review"]) is include_cost
    assert ("labor" in action["review"]["demand_model"]) is include_cost
    assert action["confirm_id"] == original["huume_action"]["confirm_id"]
    assert action["status"] == "proposed"
    assert state == original and "assignments" not in state["huume_action"]["review"]
    assert proposal["schedule_review"]["cost"]["after"] == 900
    conn.execute.assert_not_awaited()
    query, run_id, company_id, location_id, week_start, thread_id = conn.fetchrow.call_args.args
    assert str(run_id) == action["generation_run_id"]
    assert len({company_id, location_id, thread_id}) == 3 and week_start == date(2026, 10, 11)
    for predicate in ("id=$1", "company_id=$2", "location_id=$3", "week_start=$4",
                      "status='proposed'", "thread_id=$5 OR origin='automatic'"):
        assert predicate in query


@pytest.mark.asyncio
async def test_automatic_preview_preserves_recipient_price_instead_of_saved_price():
    review = full_week_review()
    state = compact_week_state(review)
    state["huume_action"]["origin"] = "automatic"
    state["huume_action"]["review"]["cost"] = {"after": 80}
    result = await project(state, connection({"schedule_review": review}), include_cost=True)
    assert result["huume_action"]["review"]["cost"] == {"after": 80}
    del state["huume_action"]["review"]["cost"]
    result = await project(state, connection({"schedule_review": review}), include_cost=True)
    assert "cost" not in result["huume_action"]["review"]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [None, {}, {"huume_action": []},
    {"huume_action": {"type": "schedule_change", "status": "proposed"}},
    {"huume_action": {"type": "schedule_week_draft", "status": "applied"}},
    {"huume_action": {"type": "schedule_week_draft", "status": "proposed", "generation_run_id": "invalid"}},
    {"huume_action": {"type": "schedule_week_draft", "status": "proposed", "review": {"assignments": []}}},
])
async def test_unrelated_settled_invalid_and_complete_states_need_no_database_read(state):
    conn = connection(None)
    assert await project(state, conn, include_cost=False) == state
    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("proposal", ["bad-json", [], {}, {"schedule_review": []},
                                     {"schedule_review": {"assignments": None}}])
async def test_malformed_old_proposal_keeps_confirmation_and_redacts_cost(proposal):
    state = compact_week_state(full_week_review())
    result = await project(state, connection(proposal), include_cost=False)
    assert result == projection.project_schedule_payload(state, include_cost=False)


@pytest.mark.asyncio
async def test_missing_or_failed_read_can_be_retried_without_spending_confirmation():
    state = compact_week_state(full_week_review())
    conn = connection(None)
    conn.fetchrow.return_value = None
    assert await project(state, conn, include_cost=False) == projection.project_schedule_payload(state, include_cost=False)
    conn.fetchrow.side_effect = RuntimeError("unavailable")
    assert await project(state, conn, include_cost=False) == projection.project_schedule_payload(state, include_cost=False)
    conn.fetchrow.side_effect = None
    conn.fetchrow.return_value = {"proposal": {"schedule_review": full_week_review()}}
    assert len((await project(state, conn, include_cost=False))["huume_action"]["review"]["assignments"]) == 28


@pytest.mark.asyncio
async def test_turn_response_uses_its_own_connection_when_not_inside_session(monkeypatch):
    from contextlib import asynccontextmanager

    state = compact_week_state(full_week_review())
    conn = connection({"schedule_review": full_week_review()})

    @asynccontextmanager
    async def get_connection():
        yield conn

    monkeypatch.setattr(projection, "get_connection", get_connection)
    result = await project(state, None, include_cost=False)
    assert len(result["huume_action"]["review"]["assignments"]) == 28


@pytest.mark.asyncio
async def test_failed_preview_read_rolls_back_savepoint_before_session_can_save():
    class Savepoint:
        def __init__(self, conn):
            self.conn = conn

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            if exc_type is not None:
                self.conn.aborted = False

    class Connection:
        aborted = False

        def transaction(self):
            return Savepoint(self)

        async def fetchrow(self, *args):
            self.aborted = True
            raise RuntimeError("query failed")

        async def execute(self, *args):
            assert not self.aborted, "optional preview read poisoned the session transaction"

    conn = Connection()
    state = compact_week_state(full_week_review())
    result = await project(state, conn, include_cost=False)
    assert result["huume_action"]["confirm_id"] == "same-confirmation"
    await conn.execute("UPDATE mw_threads")
