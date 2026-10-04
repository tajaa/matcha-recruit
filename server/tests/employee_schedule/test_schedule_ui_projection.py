"""The board receives frozen review rows while thread/model state stays compact."""

import json
from copy import deepcopy
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import schedule_cost_projection as projection
from app.matcha.services.scheduling.schedule_review import compact_review
from tests.employee_schedule.projection_fixtures import (
    compact_week_state, connection, full_week_review, patch_preview_connection,
)


async def project(state, **kwargs):
    return await projection.project_schedule_ui_state(
        state, company_id=uuid4(), thread_id=uuid4(), location_id=uuid4(),
        week_start=date(2026, 10, 11), **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("include_cost", [True, False])
@pytest.mark.parametrize("encoded", [True, False])
async def test_full_frozen_week_is_returned_without_changing_compact_state_or_consent(
    monkeypatch, include_cost, encoded,
):
    review = full_week_review()
    frozen = deepcopy(review)
    conn = patch_preview_connection(monkeypatch, connection(json.dumps(review) if encoded else review))
    state = compact_week_state(review)
    original = deepcopy(state)
    result = await project(state, include_cost=include_cost)
    action = result["huume_action"]
    assert len(action["review"]["assignments"]) == 28
    assert action["review"]["assignments"] == review["assignments"]
    assert action["review"]["demand_model"]["forecast_sales_week"] == 14000
    assert ("cost" in action["review"]) is include_cost
    assert ("labor" in action["review"]["demand_model"]) is include_cost
    assert action["confirm_id"] == original["huume_action"]["confirm_id"]
    assert action["status"] == "proposed"
    assert state == original and "assignments" not in state["huume_action"]["review"]
    assert review == frozen
    conn.execute.assert_not_awaited()
    query, run_id, company_id, location_id, week_start, thread_id = conn.fetchval.call_args.args
    assert str(run_id) == action["generation_run_id"]
    assert len({company_id, location_id, thread_id}) == 3 and week_start == date(2026, 10, 11)
    # Only the review is read, never the frozen plan beside it.
    assert "SELECT proposal->'schedule_review' FROM schedule_generation_runs" in query
    for predicate in ("id=$1", "company_id=$2", "location_id=$3", "week_start=$4",
                      "status='proposed'", "thread_id=$5 OR origin='automatic'"):
        assert predicate in query


@pytest.mark.asyncio
async def test_manual_week_keeps_the_per_person_cost_the_review_pane_reads(monkeypatch):
    """The compact cost has no `by_employee`; it must not replace the frozen one."""
    review = full_week_review()
    patch_preview_connection(monkeypatch, connection(review))
    state = compact_week_state(review)
    assert "by_employee" not in state["huume_action"]["review"]["cost"]
    expanded = (await project(state, include_cost=True))["huume_action"]["review"]
    assert expanded["employees"] == review["employees"]
    assert expanded["cost"] == review["cost"]
    for key in ("by_employee", "ot_premium_before", "unpriced_employee_ids"):
        assert key in expanded["cost"]


@pytest.mark.asyncio
async def test_staged_schedule_change_is_expanded_from_its_own_proposal_row(monkeypatch):
    proposal_id = uuid4()
    review = {**full_week_review(), "kind": "edit", "proposal_id": None}
    conn = patch_preview_connection(monkeypatch, connection(review))
    state = {"huume_action": {
        "type": "schedule_change", "status": "proposed", "confirm_id": "same-confirmation",
        "proposal_id": str(proposal_id), "review": compact_review(review),
    }}
    company_id = uuid4()
    result = await projection.project_schedule_ui_state(
        state, company_id=company_id, thread_id=uuid4(), location_id=uuid4(),
        week_start=date(2026, 10, 11), include_cost=False,
    )
    action = result["huume_action"]
    assert len(action["review"]["assignments"]) == 28
    assert action["review"]["proposal_id"] == str(proposal_id)
    assert "cost" not in action["review"] and "demand_model" not in action["review"]
    assert action["confirm_id"] == "same-confirmation"
    assert "assignments" not in state["huume_action"]["review"]
    query, *params = conn.fetchval.call_args.args
    assert params == [proposal_id, company_id]
    assert "SELECT proposal->'review' FROM schedule_chat_proposals" in query
    for predicate in ("id=$1", "company_id=$2", "status='proposed'"):
        assert predicate in query
    conn.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_automatic_preview_preserves_recipient_price_instead_of_saved_price(monkeypatch):
    review = full_week_review()
    patch_preview_connection(monkeypatch, connection(review))
    state = compact_week_state(review)
    state["huume_action"]["origin"] = "automatic"
    state["huume_action"]["review"]["cost"] = {"after": 80}
    result = await project(state, include_cost=True)
    assert result["huume_action"]["review"]["cost"] == {"after": 80}
    # Without a recipient price and without a role to price for: unpriced,
    # never the price cached on the run.
    del state["huume_action"]["review"]["cost"]
    result = await project(state, include_cost=True)
    assert "cost" not in result["huume_action"]["review"]
    assert len(result["huume_action"]["review"]["assignments"]) == 28


@pytest.mark.asyncio
async def test_automatic_preview_without_a_price_is_priced_for_the_reader(monkeypatch):
    review = full_week_review()
    conn = patch_preview_connection(monkeypatch, connection(review))
    state = compact_week_state(review)
    state["huume_action"]["origin"] = "automatic"
    del state["huume_action"]["review"]["cost"]

    async def price(conn_, *, action, actor_role, **scope):
        assert conn_ is conn and actor_role == "client"
        assert "cost" not in action["review"] and len(action["review"]["assignments"]) == 28
        return {**action, "review": {**action["review"], "cost": {"after": 70, "by_employee": {}}}}

    monkeypatch.setattr(projection, "price_automatic_action", price)
    result = await project(state, include_cost=True, actor_role="client")
    assert result["huume_action"]["review"]["cost"] == {"after": 70, "by_employee": {}}
    assert result["huume_action"]["confirm_id"] == "same-confirmation"
    # A reader without wage access is never priced.
    monkeypatch.setattr(projection, "price_automatic_action", AsyncMock(side_effect=AssertionError))
    result = await project(state, include_cost=False, actor_role="employee")
    assert "cost" not in result["huume_action"]["review"]


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [None, {}, {"huume_action": []},
    {"huume_action": {"type": "schedule_change", "status": "proposed"}},
    {"huume_action": {"type": "schedule_change", "status": "applied", "proposal_id": str(uuid4())}},
    {"huume_action": {"type": "inventory_order", "status": "proposed"}},
    {"huume_action": {"type": "schedule_week_draft", "status": "applied"}},
    {"huume_action": {"type": "schedule_week_draft", "status": "proposed", "generation_run_id": "invalid"}},
    {"huume_action": {"type": "schedule_week_draft", "status": "proposed", "review": {"assignments": []}}},
])
async def test_unrelated_settled_invalid_and_complete_states_need_no_database_read(monkeypatch, state):
    def get_connection():
        raise AssertionError("no connection is needed")

    monkeypatch.setattr(projection, "get_connection", get_connection)
    assert await project(state, include_cost=False) == state


@pytest.mark.asyncio
async def test_already_projected_state_is_not_copied_again(monkeypatch):
    monkeypatch.setattr(projection, "project_schedule_payload", AsyncMock(side_effect=AssertionError))
    state = {"huume_action": {"type": "schedule_week_draft", "status": "applied"}}
    assert await project(state, include_cost=False, already_projected=True) is state


@pytest.mark.asyncio
@pytest.mark.parametrize("frozen", ["bad-json", [], {}, None, {"assignments": None}])
async def test_malformed_old_proposal_keeps_confirmation_and_redacts_cost(monkeypatch, frozen):
    patch_preview_connection(monkeypatch, connection(frozen))
    state = compact_week_state(full_week_review())
    result = await project(state, include_cost=False)
    assert result == projection.project_schedule_payload(state, include_cost=False)


@pytest.mark.asyncio
async def test_missing_or_failed_read_can_be_retried_without_spending_confirmation(monkeypatch):
    state = compact_week_state(full_week_review())
    conn = patch_preview_connection(monkeypatch, connection(None))
    compact = projection.project_schedule_payload(state, include_cost=False)
    assert await project(state, include_cost=False) == compact
    conn.fetchval.side_effect = RuntimeError("unavailable")
    assert await project(state, include_cost=False) == compact
    conn.fetchval.side_effect = None
    conn.fetchval.return_value = full_week_review()
    assert len((await project(state, include_cost=False))["huume_action"]["review"]["assignments"]) == 28
