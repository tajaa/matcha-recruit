"""`routes/employee_schedule/labor_cost.py` — the gate order on the one
endpoint that returns wage data directly.

Collaborators are patched at the route module; what is real is the order the
checks run in and what a refused caller gets back. The endpoint deliberately
403s rather than returning zeros: on every other surface an absent `cost` key
means "not priced", and a caller must never read silence here as "free".

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_labor_cost_route.py -q
"""

import asyncio
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.matcha.routes.employee_schedule import labor_cost as route
from app.matcha.services.scheduling.labor_cost import WeekCost

LOCATION = UUID("c0ffeeee-0001-4001-8001-000000000001")
WEEK = date(2026, 9, 13)


def _run(coro):
    return asyncio.run(coro)


class _Ctx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_exc):
        return False


@pytest.fixture
def wired(monkeypatch):
    """Every collaborator stubbed permissive; each test tightens one."""
    monkeypatch.setattr(route, "get_connection", lambda: _Ctx())
    monkeypatch.setattr(route, "require_company_id", AsyncMock(return_value=uuid4()))
    monkeypatch.setattr(route, "is_labor_cost_visible", AsyncMock(return_value=True))
    monkeypatch.setattr(route, "assert_manager_location", AsyncMock(return_value=None))
    monkeypatch.setattr(route, "load_week_cost", AsyncMock(return_value=WeekCost(week_start=WEEK)))
    monkeypatch.setattr(
        route, "jurisdiction_rule_status", AsyncMock(return_value={"state": "CA", "status": "curated"}),
    )
    return route


def _call(role="client"):
    return _run(route.get_labor_cost(
        LOCATION, week_start=WEEK, current_user=SimpleNamespace(id=uuid4(), role=role),
    ))


def test_a_business_admin_gets_the_week_and_its_jurisdiction_line(wired):
    payload = _call()
    assert payload["week_start"] == WEEK.isoformat()
    assert payload["total"] == 0.0
    assert payload["jurisdiction"]["state"] == "CA"


def test_no_access_is_a_403_not_a_zeroed_payload(wired, monkeypatch):
    monkeypatch.setattr(route, "is_labor_cost_visible", AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as excinfo:
        _call()
    assert excinfo.value.status_code == 403


def test_visibility_is_checked_before_the_location_scope_is_even_resolved(wired, monkeypatch):
    """A caller with no cost access must not be able to probe which locations
    exist by reading apart a 403 from a 404."""
    monkeypatch.setattr(route, "is_labor_cost_visible", AsyncMock(return_value=False))
    scope = AsyncMock(side_effect=AssertionError("scope resolved before the cost gate"))
    monkeypatch.setattr(route, "assert_manager_location", scope)
    with pytest.raises(HTTPException):
        _call()
    scope.assert_not_awaited()


def test_a_location_outside_the_manager_s_scope_still_refuses(wired, monkeypatch):
    monkeypatch.setattr(route, "assert_manager_location", AsyncMock(
        side_effect=HTTPException(status_code=403, detail="not yours"),
    ))
    with pytest.raises(HTTPException) as excinfo:
        _call()
    assert excinfo.value.status_code == 403


def test_the_caller_s_role_is_what_the_gate_is_asked_about(wired, monkeypatch):
    seen = {}

    async def record(company_id, actor_role, conn=None):
        seen["role"] = actor_role
        return True

    monkeypatch.setattr(route, "is_labor_cost_visible", record)
    _call(role="individual")
    assert seen["role"] == "individual"


def test_a_pricing_failure_here_raises_rather_than_reporting_a_free_week(wired, monkeypatch):
    """The /week board swallows so the schedule survives; this endpoint must
    not, because its whole payload is the money."""
    monkeypatch.setattr(route, "load_week_cost", AsyncMock(side_effect=RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        _call()
