"""An admin's top-up to one person's monthly allowance of background work."""
import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.routes.admin import users as user_routes
from app.matcha.services.matcha_work.agent_tasks import allowance
from tests.agent_runtime.helpers import FakeConn, connection


def test_clean_bonus():
    assert allowance.clean_bonus("40") == 40 and allowance.clean_bonus(40) == 40
    assert allowance.clean_bonus(None) == 0 and allowance.clean_bonus("lots") == 0
    assert allowance.clean_bonus(True) == 0 and allowance.clean_bonus(-5) == 0
    assert allowance.clean_bonus(allowance.MAX_BONUS_UNITS + 1) == allowance.MAX_BONUS_UNITS


@pytest.mark.asyncio
async def test_bonus_is_read_from_the_users_beta_flags(monkeypatch):
    user = uuid4()
    conn = FakeConn().on("beta_features ->>", "25")
    monkeypatch.setattr(allowance, "connection_or_direct", connection(conn))
    assert await allowance.bonus_units(user) == 25
    [(_method, query, args)] = conn.calls
    assert "FROM users WHERE id = $1" in query and args == (user, allowance.BONUS_KEY)
    # No row, or no key stored: no bonus.
    monkeypatch.setattr(allowance, "connection_or_direct", connection(FakeConn()))
    assert await allowance.bonus_units(user) == 0


@pytest.mark.asyncio
async def test_limit_adds_the_bonus_only_to_a_plan_with_an_allowance(monkeypatch):
    user = uuid4()
    monkeypatch.setattr(allowance, "bonus_units", AsyncMock(return_value=30))
    assert await allowance.limit_for_user(user, "pro") == 90
    assert await allowance.limit_for_user(user, "business") == 180
    assert await allowance.limit_for_user(user, "lite") == 0
    assert await allowance.limit_for_user(user, None) == 0


@pytest.mark.asyncio
async def test_usage_reports_the_topped_up_limit(monkeypatch):
    conn = FakeConn().on("FROM mw_project_agent_runs r, month", 20)
    monkeypatch.setattr(allowance, "connection_or_direct", connection(conn))
    monkeypatch.setattr(allowance, "bonus_units", AsyncMock(return_value=40))
    usage = await allowance.task_usage(uuid4(), plan="pro")
    assert (usage["limit"], usage["used"], usage["remaining"]) == (100, 20, 80)
    # A job search is five units: 100 units is 20 searches, 4 spent.
    counted = allowance.as_count(usage, allowance.WEIGHTS["job_search"])
    assert (counted["limit"], counted["used"], counted["remaining"]) == (20, 4, 16)


def _admin_conn(monkeypatch, row):
    conn = FakeConn().on("UPDATE users", row)
    monkeypatch.setattr(user_routes, "get_connection", connection(conn))
    return conn


@pytest.mark.asyncio
async def test_admin_sets_the_bonus(monkeypatch):
    user = uuid4()
    conn = _admin_conn(monkeypatch, {"beta_features": {allowance.BONUS_KEY: 40}})
    out = await user_routes.patch_user_beta_flags(user, {allowance.BONUS_KEY: 40}, current_user=None)
    assert out == {"beta_features": {allowance.BONUS_KEY: 40}}
    [(_method, query, args)] = conn.calls
    assert "|| $1::jsonb" in query
    assert json.loads(args[0]) == {allowance.BONUS_KEY: 40} and args[1] == user


@pytest.mark.asyncio
async def test_admin_sets_the_bonus_beside_a_comp_flag(monkeypatch):
    conn = _admin_conn(monkeypatch, {"beta_features": {}})
    await user_routes.patch_user_beta_flags(
        uuid4(), {"matcha_work_beta_full": True, allowance.BONUS_KEY: 0, "ignored": 1}, current_user=None,
    )
    assert json.loads(conn.calls[0][2][0]) == {"matcha_work_beta_full": True, allowance.BONUS_KEY: 0}


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [-1, allowance.MAX_BONUS_UNITS + 1, True, "40", 2.5, None])
async def test_admin_refuses_a_bad_bonus(monkeypatch, bad):
    conn = _admin_conn(monkeypatch, {"beta_features": {}})
    with pytest.raises(HTTPException) as err:
        await user_routes.patch_user_beta_flags(uuid4(), {allowance.BONUS_KEY: bad}, current_user=None)
    assert err.value.status_code == 400 and not conn.calls


@pytest.mark.asyncio
async def test_admin_bonus_for_a_missing_user_is_a_404(monkeypatch):
    _admin_conn(monkeypatch, None)
    with pytest.raises(HTTPException) as err:
        await user_routes.patch_user_beta_flags(uuid4(), {allowance.BONUS_KEY: 10}, current_user=None)
    assert err.value.status_code == 404
