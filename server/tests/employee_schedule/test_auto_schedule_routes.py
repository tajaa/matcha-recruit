"""`routes/employee_schedule/auto_schedules.py` — the Autopilot rule mode.

Collaborators are patched at the route module; the mode validation, the
premium-flag gate and the run-now pass-through are real.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_auto_schedule_routes.py -q
"""

import asyncio
from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.scheduling.employee_schedule import ScheduleAutomationRuleUpsert
from app.matcha.routes.employee_schedule import auto_schedules

LOCATION = UUID("c0ffeeee-0001-4001-8001-000000000001")
COMPANY = uuid4()


def _run(coro):
    return asyncio.run(coro)


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self):
        self.inserts = []

    async def fetchrow(self, query, *args):
        if "FROM business_locations" in query:
            return {"id": LOCATION, "timezone": "America/Los_Angeles"}
        if "INSERT INTO schedule_automation_rules" in query:
            self.inserts.append(args)
            return {"id": uuid4(), "schedule_version": 1}
        raise AssertionError(f"unexpected fetchrow: {query}")

    async def fetchval(self, query, *_args):
        raise AssertionError(f"autopilot mode must not look up a template: {query}")

    def transaction(self):
        return _Ctx(self)


def _rule_row(**changes):
    row = {
        "id": uuid4(), "location_id": LOCATION, "location_name": "Downtown",
        "timezone": "America/Los_Angeles", "enabled": False, "mode": "autopilot",
        "cadence": "weekly", "week_template_id": None, "week_template_name": None,
        "run_weekday": 4, "run_date": None, "run_time": time(9), "target_weeks_ahead": 1,
        "target_week_start": None, "next_run_at": None, "last_attempt_at": None,
        "last_completed_at": None, "last_status": None, "last_message": None,
        "last_generation_run_id": None,
    }
    row.update(changes)
    return row


def _wire(monkeypatch, conn, *, features):
    monkeypatch.setattr(auto_schedules, "require_company_id", AsyncMock(return_value=COMPANY))
    monkeypatch.setattr(auto_schedules, "_require_schedule_huume", AsyncMock())
    monkeypatch.setattr(auto_schedules, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(auto_schedules, "get_company_features", AsyncMock(return_value=features))
    monkeypatch.setattr(auto_schedules, "log_audit", AsyncMock())
    monkeypatch.setattr(auto_schedules, "_fetch_rule", AsyncMock(return_value=_rule_row()))


def _body():
    return ScheduleAutomationRuleUpsert(
        mode="autopilot", enabled=False, cadence="weekly", run_weekday=4,
        run_time=time(9), target_weeks_ahead=1,
    )


def test_autopilot_rule_needs_the_premium_flag(monkeypatch):
    conn = _Conn()
    _wire(monkeypatch, conn, features={"huume": True, "matcha_work": True})
    with pytest.raises(HTTPException) as exc:
        _run(auto_schedules.save_auto_schedule(LOCATION, _body(), current_user=SimpleNamespace(id=uuid4())))
    assert exc.value.status_code == 403
    assert conn.inserts == []


def test_autopilot_rule_saves_without_a_template(monkeypatch):
    conn = _Conn()
    _wire(monkeypatch, conn, features={"schedule_autopilot": True})
    saved = _run(auto_schedules.save_auto_schedule(LOCATION, _body(), current_user=SimpleNamespace(id=uuid4())))
    # company_id, location_id, mode, week_template_id, ...
    assert conn.inserts[0][2:4] == ("autopilot", None)
    assert saved["mode"] == "autopilot" and saved["week_template_id"] is None


def test_run_now_passes_the_rule_mode(monkeypatch):
    class RunConn:
        def __init__(self):
            self.updates = []

        async def execute(self, query, *args):
            self.updates.append(args)
            return "UPDATE 1"

    conn = RunConn()
    _wire(monkeypatch, conn, features={})
    monkeypatch.setattr(auto_schedules, "resolve_week_start_weekday", AsyncMock(return_value=0))
    generate = AsyncMock(return_value={"status": "not_ready", "message": "Add a timezone."})
    monkeypatch.setattr(auto_schedules, "generate_review_suggestion", generate)

    result = _run(auto_schedules.run_auto_schedule_now(LOCATION, current_user=SimpleNamespace(id=uuid4())))

    assert result["status"] == "not_ready"
    assert generate.await_args.kwargs["mode"] == "autopilot"
    assert generate.await_args.kwargs["week_template_id"] is None
    assert conn.updates[0][0] == "not_ready"
