"""`routes/employee_schedule/auto_schedules.py` — the Autopilot rule mode.

Collaborators are patched at the route module; the mode validation, the
premium-flag gate and the run-now pass-through are real.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_auto_schedule_routes.py -q
"""

import asyncio
from datetime import date, time
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


def _manager():
    return SimpleNamespace(id=uuid4(), role="client")


def _body():
    return ScheduleAutomationRuleUpsert(
        mode="autopilot", enabled=False, cadence="weekly", run_weekday=4,
        run_time=time(9), target_weeks_ahead=1,
    )


def test_autopilot_rule_needs_the_premium_flag(monkeypatch):
    conn = _Conn()
    _wire(monkeypatch, conn, features={"huume": True, "matcha_work": True})
    with pytest.raises(HTTPException) as exc:
        _run(auto_schedules.save_auto_schedule(LOCATION, _body().model_copy(update={"enabled": True}), current_user=SimpleNamespace(id=uuid4())))
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

    result = _run(auto_schedules.run_auto_schedule_now(LOCATION, current_user=_manager()))

    assert result["status"] == "not_ready"
    assert generate.await_args.kwargs["mode"] == "autopilot"
    assert generate.await_args.kwargs["week_template_id"] is None
    assert conn.updates[0][0] == "not_ready"


def test_run_now_is_a_manager_rebuild_not_a_refusal(monkeypatch):
    """A manager clicking Run now after tuning the template gets the rebuild
    `generate_review_suggestion` promises manager clicks — the week's
    unapproved suggestion is replaced, not quoted back as 'already waiting'."""
    conn = _RunConn()
    _wire(monkeypatch, conn, features={})
    monkeypatch.setattr(auto_schedules, "resolve_week_start_weekday", AsyncMock(return_value=0))
    generate = AsyncMock(return_value={"status": "generated", "message": "ok"})
    monkeypatch.setattr(auto_schedules, "generate_review_suggestion", generate)
    manager = _manager()

    _run(auto_schedules.run_auto_schedule_now(LOCATION, current_user=manager))

    kwargs = generate.await_args.kwargs
    assert kwargs["supersede_proposed"] is True
    assert kwargs["actor_user_id"] == manager.id
    assert kwargs["actor_role"] == "client"


class _RunConn:
    def __init__(self):
        self.updates = []

    async def execute(self, query, *args):
        self.updates.append(args)
        return "UPDATE 1"


def _wire_run(monkeypatch, row):
    conn = _RunConn()
    _wire(monkeypatch, conn, features={})
    monkeypatch.setattr(auto_schedules, "_fetch_rule", AsyncMock(return_value=row))
    monkeypatch.setattr(auto_schedules, "resolve_week_start_weekday", AsyncMock(return_value=0))
    generate = AsyncMock(return_value={
        "status": "generated", "message": "ok", "generation_run_id": str(uuid4()),
    })
    monkeypatch.setattr(auto_schedules, "generate_review_suggestion", generate)
    return conn, generate


def test_run_now_refuses_a_one_time_rule_whose_week_has_passed(monkeypatch):
    """The reported Po Coffee sequence: a one-time rule saved for 2026-09-06
    was run on 2026-09-27 while the manager looked at the week of 2026-10-04.
    It rebuilt September 6 and was refused by that week's old approved run under
    a message that named no week. Now it never reaches the generator, and the
    refusal names the week it targeted."""
    conn, generate = _wire_run(monkeypatch, _rule_row(
        cadence="once", run_weekday=None, target_weeks_ahead=None,
        run_date=date(2026, 9, 5), target_week_start=date(2026, 9, 6),
    ))

    result = _run(auto_schedules.run_auto_schedule_now(LOCATION, current_user=_manager()))

    generate.assert_not_awaited()
    assert result["status"] == "not_ready"
    assert result["week_start"] == "2026-09-06"
    assert "2026-09-06" in result["message"] and "already passed" in result["message"]
    # The rule's status line carries the same explanation.
    assert conn.updates[0][:2] == ("not_ready", result["message"])


def test_run_now_builds_the_one_time_rules_own_future_week(monkeypatch):
    target = date(2099, 1, 4)  # a Sunday, well in the future
    _conn, generate = _wire_run(monkeypatch, _rule_row(
        cadence="once", run_weekday=None, target_weeks_ahead=None,
        run_date=date(2099, 1, 1), target_week_start=target,
    ))

    result = _run(auto_schedules.run_auto_schedule_now(LOCATION, current_user=_manager()))

    assert result["status"] == "generated"
    assert result["week_start"] == target.isoformat()
    assert generate.await_args.kwargs["week_start"] == target


def _once_body(*, target, run_date, enabled=True):
    return ScheduleAutomationRuleUpsert(
        mode="autopilot", enabled=enabled, cadence="once", run_date=run_date,
        run_time=time(9), target_week_start=target,
    )


def _wire_save_once(monkeypatch):
    conn = _Conn()
    _wire(monkeypatch, conn, features={"schedule_autopilot": True})
    monkeypatch.setattr(auto_schedules, "resolve_week_start_weekday", AsyncMock(return_value=0))
    monkeypatch.setattr(
        "app.workers.tasks.schedule_auto_generation.enqueue_schedule_automation",
        lambda *_args: None,
    )
    return conn


def test_saving_an_enabled_rule_for_a_past_week_is_refused(monkeypatch):
    """Caught where it is written, not two weeks later when the worker lands
    on a finished week and quietly disables the rule."""
    conn = _wire_save_once(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        _run(auto_schedules.save_auto_schedule(
            LOCATION, _once_body(target=date(2020, 1, 5), run_date=date(2099, 1, 1)),
            current_user=_manager(),
        ))

    assert exc.value.status_code == 422
    assert "2020-01-05 has already passed" in exc.value.detail
    assert conn.inserts == []


def test_a_run_date_after_the_target_week_is_refused(monkeypatch):
    conn = _wire_save_once(monkeypatch)

    with pytest.raises(HTTPException) as exc:
        _run(auto_schedules.save_auto_schedule(
            LOCATION, _once_body(target=date(2099, 1, 4), run_date=date(2099, 1, 11)),
            current_user=_manager(),
        ))

    assert exc.value.status_code == 422
    assert "last day of the week of 2099-01-04" in exc.value.detail
    assert conn.inserts == []


def test_a_run_date_inside_the_target_week_saves(monkeypatch):
    conn = _wire_save_once(monkeypatch)

    _run(auto_schedules.save_auto_schedule(
        LOCATION, _once_body(target=date(2099, 1, 4), run_date=date(2099, 1, 10)),
        current_user=_manager(),
    ))

    assert len(conn.inserts) == 1


def test_an_old_rule_can_still_be_paused(monkeypatch):
    """The form resends the rule's frozen week; refusing it would leave a
    manager unable to switch an old rule off."""
    conn = _wire_save_once(monkeypatch)

    _run(auto_schedules.save_auto_schedule(
        LOCATION, _once_body(target=date(2020, 1, 5), run_date=date(2020, 1, 4), enabled=False),
        current_user=_manager(),
    ))

    assert len(conn.inserts) == 1


def test_autopilot_rule_can_be_paused_after_premium_grant_is_removed(monkeypatch):
    conn = _Conn()
    _wire(monkeypatch, conn, features={"huume": True, "matcha_work": True})
    saved = _run(auto_schedules.save_auto_schedule(LOCATION, _body(), current_user=_manager()))
    assert saved["enabled"] is False
    assert conn.inserts[0][4] is False
    auto_schedules.get_company_features.assert_not_awaited()


def test_pausing_still_requires_huume_access(monkeypatch):
    conn = _Conn()
    _wire(monkeypatch, conn, features={})
    monkeypatch.setattr(auto_schedules, "_require_schedule_huume", AsyncMock(
        side_effect=HTTPException(status_code=403, detail="Huume scheduling is not enabled"),
    ))
    with pytest.raises(HTTPException) as exc:
        _run(auto_schedules.save_auto_schedule(LOCATION, _body(), current_user=_manager()))
    assert exc.value.status_code == 403 and conn.inserts == []


def test_pausing_still_requires_a_location_owned_by_the_tenant(monkeypatch):
    class ForeignLocationConn(_Conn):
        async def fetchrow(self, query, *args):
            assert "FROM business_locations" in query and "company_id=$2" in query
            assert args == (LOCATION, COMPANY)
            return None

    conn = ForeignLocationConn()
    _wire(monkeypatch, conn, features={})
    with pytest.raises(HTTPException) as exc:
        _run(auto_schedules.save_auto_schedule(LOCATION, _body(), current_user=_manager()))
    assert exc.value.status_code == 404 and conn.inserts == []


def test_committed_auto_schedule_save_succeeds_when_publication_fails(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.workers.tasks import schedule_auto_generation as worker

    conn = _Conn()
    _wire(monkeypatch, conn, features={"schedule_autopilot": True})
    scheduled = datetime.now(timezone.utc) + timedelta(seconds=30)
    monkeypatch.setattr(auto_schedules, "next_run_at", lambda **_kwargs: scheduled)
    monkeypatch.setattr(worker, "enqueue_schedule_automation", lambda *_args: (_ for _ in ()).throw(ConnectionError("Redis down")))
    body = _body().model_copy(update={"enabled": True})
    result = _run(auto_schedules.save_auto_schedule(LOCATION, body, current_user=_manager()))
    assert result["mode"] == "autopilot"
    assert len(conn.inserts) == 1 and conn.inserts[0][11] == scheduled
    auto_schedules.log_audit.assert_awaited_once()


@pytest.mark.parametrize("old_status", ["queued", "running", "retrying"])
def test_new_rule_version_has_no_lease_when_initial_publication_fails(monkeypatch, old_status):
    from datetime import datetime, timedelta, timezone
    from app.workers.tasks import schedule_auto_generation as worker

    old_generation = uuid4()
    old_completion = datetime(2026, 1, 1, tzinfo=timezone.utc)
    state = _rule_row(enabled=True, last_status=old_status, last_message="Old attempt",
                      last_generation_run_id=old_generation, last_completed_at=old_completion,
                      schedule_version=1)

    class SaveConn(_Conn):
        async def fetchrow(self, query, *args):
            if "INSERT INTO schedule_automation_rules" in query:
                assert "last_status=NULL" in query and "last_message=NULL" in query
                self.inserts.append(args)
                state.update(schedule_version=state["schedule_version"] + 1,
                             next_run_at=args[11], last_status=None, last_message=None)
                return {"id": state["id"], "schedule_version": state["schedule_version"]}
            return await super().fetchrow(query, *args)

    conn = SaveConn()
    _wire(monkeypatch, conn, features={"schedule_autopilot": True})
    monkeypatch.setattr(auto_schedules, "_fetch_rule", AsyncMock(side_effect=lambda *_args: state.copy()))
    scheduled = datetime.now(timezone.utc) + timedelta(seconds=30)
    monkeypatch.setattr(auto_schedules, "next_run_at", lambda **_kwargs: scheduled)
    monkeypatch.setattr(worker, "enqueue_schedule_automation", lambda *_args: (_ for _ in ()).throw(ConnectionError("Redis down")))
    result = _run(auto_schedules.save_auto_schedule(LOCATION, _body().model_copy(update={"enabled": True}), current_user=_manager()))
    assert state["schedule_version"] == 2 and state["next_run_at"] == scheduled
    assert result["last_status"] is None and result["last_message"] is None
    # Prior completed work remains available as history, but cannot lease the
    # new version out of the dispatcher's recovery scan.
    assert result["last_completed_at"] == old_completion.isoformat()
    assert result["last_generation_run_id"] == str(old_generation)
