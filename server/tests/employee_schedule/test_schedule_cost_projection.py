"""Recipient security and frozen automatic-plan pricing (no real DB)."""

import json
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.matcha.services.scheduling import labor_cost_service as costs
from app.matcha.services.scheduling import schedule_cost_projection as projection
from app.matcha.services.scheduling import schedule_assistant_session as sessions


@pytest.mark.parametrize("role,flag,visible", [
    ("employee", True, False), ("individual", True, False), (None, True, False),
    ("client", False, False), ("admin", False, False),
    ("client", True, True), ("admin", True, True),
])
@pytest.mark.asyncio
async def test_live_flag_and_recipient_role_are_both_required(monkeypatch, role, flag, visible):
    features = AsyncMock(return_value={"labor_cost": flag})
    monkeypatch.setattr(costs, "get_company_features", features)
    assert await projection.schedule_cost_visible(_conn(), company_id=uuid4(), actor_role=role) is visible


@pytest.mark.asyncio
async def test_feature_read_failure_hides_cached_wages(monkeypatch):
    monkeypatch.setattr(projection, "is_labor_cost_visible", AsyncMock(side_effect=RuntimeError("unavailable")))
    assert not await projection.schedule_cost_visible(_conn(), company_id=uuid4(), actor_role="admin")


def test_projection_covers_nested_reviews_choices_and_load_without_mutating_source():
    payload = {
        "huume_action": {"confirm_id": "same", "review": {"cost": {"by_employee": {"person": 40}}},
                         "demand_model": {"labor": {"labor_pct": 20}, "forecast_sales_week": 200}},
        "choices": [{"review": {"cost": {"after": 40}}}],
        "roster_load": [{"minutes": 120, "week_cost": 40, "pay_rate": 20}],
    }
    result = projection.project_schedule_payload(payload, include_cost=False)
    assert result["huume_action"]["review"] == {}
    assert result["huume_action"]["demand_model"] == {"forecast_sales_week": 200}
    assert result["roster_load"] == [{"minutes": 120}]
    assert result["choices"] == [{"review": {}}]
    assert payload["huume_action"]["review"]["cost"]
    assert projection.project_schedule_payload(payload, include_cost=True) == payload


def test_history_withholds_wage_bearing_and_unlabelled_prose_after_revocation():
    messages = [
        {"role": "user", "content": "Review this", "metadata": None},
        {"role": "assistant", "content": "Pay is $20", "metadata": '{"schedule_cost_visible":true}'},
        {"role": "assistant", "content": "Legacy pay is $25", "metadata": "broken"},
        {"role": "system", "content": "Legacy summary", "metadata": {}},
        {"role": "assistant", "content": "Two seats remain", "metadata": {"schedule_cost_visible": False,
            "huume_steps": [{"result": {"cost": {"after": 40}}}]}},
    ]
    result = projection.project_schedule_messages(messages, include_cost=False)
    assert [message["content"] for message in result] == ["Review this", "Two seats remain"]
    assert result[-1]["metadata"]["huume_steps"] == [{"result": {}}]
    assert len(projection.project_schedule_messages(messages, include_cost=True)) == 5


def _action():
    return {
        "generation_run_id": str(uuid4()), "confirm_id": "keep-consent", "status": "proposed",
        "metrics": {"open_positions": 0}, "review": {"kind": "week_draft", "cost": {"after": 999}},
        "demand_model": {"forecast_sales_week": 400, "labor": {"labor_pct": 99}},
    }


def _proposal():
    return {"shifts": [{"starts_at": "2026-10-04T08:00:00+00:00", "worked_minutes": 240,
                        "proposed_assignments": [{"employee_id": str(uuid4())}]}]}


@pytest.fixture
def pricing(monkeypatch):
    visible = AsyncMock(return_value=True)
    before = [{"employee_id": str(uuid4()), "starts_at": "2026-10-04T06:00:00+00:00", "worked_minutes": 60}]
    load = AsyncMock(return_value=(before, False))
    delta = AsyncMock(return_value={"before": 20, "after": 100, "delta": 80, "by_employee": {}})
    monkeypatch.setattr(projection, "schedule_cost_visible", visible)
    monkeypatch.setattr(projection, "load_week_assignment_rows", load)
    monkeypatch.setattr(projection, "cost_delta_for_rows", delta)
    return visible, load, delta, before


def _conn():
    conn = AsyncMock()
    conn.transaction = MagicMock(side_effect=lambda: AsyncMock())
    return conn


async def _price(action, proposal=None, conn=None):
    return await projection.price_automatic_action(
        conn or _conn(), company_id=uuid4(), location_id=uuid4(), week_start=date(2026, 10, 4),
        actor_role="client", action=action, proposal=proposal,
    )


@pytest.mark.asyncio
async def test_authorized_recurring_plan_prices_frozen_assignments_and_whole_week(pricing):
    _, _, delta, before = pricing
    proposal, action = _proposal(), _action()
    result = await _price(action, proposal)
    assert result["review"]["cost"]["after"] == 100
    assert result["demand_model"]["labor"]["labor_pct"] == 25
    assert result["review"]["demand_model"] == result["demand_model"]
    assert result["confirm_id"] == action["confirm_id"]
    week, old, new = delta.call_args.kwargs["weeks"][0]
    assert week == date(2026, 10, 4)
    assert old == before and new[:1] == before
    assert new[1]["employee_id"] == proposal["shifts"][0]["proposed_assignments"][0]["employee_id"]
    assert new[1]["worked_minutes"] == 240
    assert action["review"]["cost"]["after"] == 999


@pytest.mark.parametrize("forecast,open_positions,percentage", [(0, 0, None), (400, 1, None), (None, 0, None)])
@pytest.mark.asyncio
async def test_labor_percentage_needs_sales_and_a_filled_plan(pricing, forecast, open_positions, percentage):
    action = _action()
    action["demand_model"]["forecast_sales_week"] = forecast
    action["metrics"]["open_positions"] = open_positions
    result = await _price(action, _proposal())
    labor = result["demand_model"].get("labor")
    assert (labor or {}).get("labor_pct") == percentage
    if open_positions:
        assert "still open" in labor["note"]


@pytest.mark.asyncio
async def test_employee_reader_never_loads_pricing_inputs(pricing):
    visible, load, delta, _ = pricing
    visible.return_value = False
    result = await _price(_action(), _proposal())
    assert "cost" not in result["review"] and "labor" not in result["demand_model"]
    load.assert_not_awaited()
    delta.assert_not_awaited()


@pytest.mark.parametrize("failure", ["truncated", "load", "cost", "unpriced", "bad-json", "missing-run"])
@pytest.mark.asyncio
async def test_pricing_failure_never_falls_back_to_saved_wages(pricing, failure):
    _, load, delta, _ = pricing
    conn, proposal = _conn(), _proposal()
    if failure == "truncated":
        load.return_value = ([], True)
    elif failure == "load":
        load.side_effect = RuntimeError("offline")
    elif failure == "cost":
        delta.side_effect = RuntimeError("offline")
    elif failure == "unpriced":
        delta.return_value = None
    elif failure == "bad-json":
        proposal = None
        conn.fetchrow.return_value = {"proposal": "bad-json"}
    else:
        proposal = None
        conn.fetchrow.return_value = None
    result = await _price(_action(), proposal, conn)
    assert "cost" not in result["review"]
    assert "labor" not in result["demand_model"]


@pytest.mark.asyncio
async def test_resumed_automatic_action_reads_company_location_week_and_keeps_consent(pricing):
    conn = _conn()
    conn.fetchrow.return_value = {"proposal": json.dumps(_proposal())}
    action = _action()
    result = await _price(action, conn=conn)
    query, run_id, company_id, location_id, week_start = conn.fetchrow.call_args.args
    assert "company_id=$2" in query and "location_id=$3" in query and "week_start=$4" in query
    assert "status='proposed'" in query and "origin='automatic'" in query
    assert str(run_id) == action["generation_run_id"] and company_id != location_id
    assert week_start == date(2026, 10, 4)
    assert result["confirm_id"] == action["confirm_id"]


def test_automatic_adoption_defaults_to_no_saved_wages():
    action = sessions._automatic_action({
        "id": uuid4(), "location_id": uuid4(), "week_start": date(2026, 10, 4),
        "source_mode": "autopilot", "week_template_id": None,
        "metrics": {}, "proposal": {"schedule_review": {"cost": {"after": 999}},
                                     "demand_model": {"labor": {"labor_pct": 99}}},
    })
    assert "cost" not in (action["review"] or {}) and "labor" not in action["demand_model"]


@pytest.mark.parametrize("boundary", ["feature-read", "pricing"])
@pytest.mark.asyncio
async def test_optional_price_read_rolls_back_before_session_write(monkeypatch, boundary):
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

        async def execute(self, query):
            if self.aborted:
                raise RuntimeError("transaction remains aborted")

    conn = Connection()

    async def fail_visibility(*args, **kwargs):
        conn.aborted = True
        raise RuntimeError("feature query failed")

    async def failed_optional_cost(*args, **kwargs):
        # cost_delta_for_rows catches query errors and returns None.
        conn.aborted = True
        return None

    if boundary == "feature-read":
        monkeypatch.setattr(projection, "is_labor_cost_visible", fail_visibility)
    else:
        monkeypatch.setattr(projection, "schedule_cost_visible", AsyncMock(return_value=True))
        monkeypatch.setattr(projection, "load_week_assignment_rows", AsyncMock(return_value=([], False)))
        monkeypatch.setattr(projection, "cost_delta_for_rows", failed_optional_cost)
    result = await _price(_action(), _proposal(), conn)
    assert "cost" not in result["review"]
    await conn.execute("UPDATE mw_threads")
    assert not conn.aborted
