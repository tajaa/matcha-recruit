"""`routes/employee_schedule/planning.py` — the REST backbone of the Schedule
Pilot workspace. Collaborators patched at the route module; the request
shaping, authorization order, status mapping and creator-only rules are real.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_planning_routes.py -q
"""

import asyncio
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.matcha.models.scheduling.employee_schedule import FillVacantPreviewRequest
from app.matcha.routes.employee_schedule import planning
from app.matcha.services.scheduling import schedule_chat

UTC = timezone.utc
LOCATION = UUID("c0ffeeee-0001-4001-8001-000000000001")
WEEK = date(2026, 8, 23)


def _run(coro):
    return asyncio.run(coro)


def _user(role="client"):
    return SimpleNamespace(id=uuid4(), role=role)


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self, *, proposal_row=None, created_shift_ids=None, updated=None):
        self.proposal_row = proposal_row
        self.created_shift_ids = created_shift_ids
        self.updated = updated
        self.queries = []

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if "FROM schedule_chat_proposals" in query and "created_shift_ids" in query:
            return {"created_shift_ids": self.created_shift_ids}
        return self.proposal_row

    async def fetchval(self, query, *args):
        self.queries.append((query, args))
        return self.updated


def _wire(monkeypatch, conn, *, company_id):
    monkeypatch.setattr(planning, "require_company_id", AsyncMock(return_value=company_id))
    monkeypatch.setattr(planning, "get_connection", lambda: _Ctx(conn))
    authz = AsyncMock()
    monkeypatch.setattr(planning, "assert_manager_location", authz)
    return authz


def _plan(assignments, unfilled=(), *, status="ready", message=None):
    return {
        "status": status, "message": message, "assignments": list(assignments), "unfilled": list(unfilled),
        "hours_by_employee": {}, "metrics": {}, "roster_size": 2, "demand_size": 2,
        "jurisdiction": {"state": "CA", "status": "curated", "message": "on file"},
    }


def _assignment(shift_id, name):
    return {"shift_id": shift_id, "role": "Shift Lead", "starts_at": "2026-08-24T06:00:00+00:00",
            "ends_at": "2026-08-24T14:00:00+00:00", "employee_id": str(uuid4()), "employee_name": name, "reason": "ok"}


# ── planning inputs ──────────────────────────────────────────────────────────

def test_planning_inputs_authorizes_the_location_then_returns_the_builder_shape(monkeypatch):
    company_id, user = uuid4(), _user()
    conn = _Conn()
    authz = _wire(monkeypatch, conn, company_id=company_id)
    builder = AsyncMock(return_value={"roster": [], "open_slots": [], "policy": {}})
    monkeypatch.setattr(planning, "build_planning_inputs", builder)

    result = _run(planning.get_planning_inputs(LOCATION, week_start=WEEK, current_user=user))

    assert result == {"roster": [], "open_slots": [], "policy": {}}
    authz.assert_awaited_once_with(conn, company_id=company_id, user_id=user.id, actor_role="client", location_id=LOCATION)
    builder.assert_awaited_once_with(conn, company_id=company_id, location_id=LOCATION, week_start=WEEK)


def test_planning_inputs_stops_at_a_refused_location(monkeypatch):
    conn = _Conn()
    authz = _wire(monkeypatch, conn, company_id=uuid4())
    authz.side_effect = HTTPException(status_code=403, detail="not your store")
    builder = AsyncMock()
    monkeypatch.setattr(planning, "build_planning_inputs", builder)
    with pytest.raises(HTTPException) as exc:
        _run(planning.get_planning_inputs(LOCATION, week_start=WEEK, current_user=_user()))
    assert exc.value.status_code == 403 and not builder.await_count


# ── preview ──────────────────────────────────────────────────────────────────

def _preview(monkeypatch, *, plan, build=None, body=None, company_id=None, user=None):
    company_id, user = company_id or uuid4(), user or _user()
    conn = _Conn()
    _wire(monkeypatch, conn, company_id=company_id)
    captured = {"plan": None, "build": None}

    async def fake_plan(conn_, **kwargs):
        captured["plan"] = kwargs
        return plan

    async def fake_build(conn_, **kwargs):
        captured["build"] = kwargs
        return build

    monkeypatch.setattr(planning, "plan_vacant_fill", fake_plan)
    monkeypatch.setattr(schedule_chat, "build_edit_proposal", fake_build)
    body = body or FillVacantPreviewRequest(week_start=WEEK)
    return _run(planning.preview_fill_vacant(LOCATION, body, current_user=user)), captured, user


def test_preview_plans_then_stages_one_editor_proposal_for_the_caller(monkeypatch):
    job_id, wanted, excluded, only = uuid4(), uuid4(), uuid4(), uuid4()
    plan = _plan(
        [_assignment("s1", "Dana Reyes"), _assignment("s2", "Ben Ortiz")],
        [{"shift_id": "s3", "role": "Shift Lead", "starts_at": datetime(2026, 8, 25, 6, tzinfo=UTC),
          "ends_at": datetime(2026, 8, 25, 14, tzinfo=UTC), "reason": "policy: second shift that day", "exclusions": {}}],
    )
    build = schedule_chat.ProposalBuild(
        kind="proposal", proposal_id=UUID("44444444-4444-4444-4444-444444444444"), pill_text="pill",
        review={"proposal_id": "44444444-4444-4444-4444-444444444444", "kind": "edit", "compliance_status": "verified",
                "assignments": [], "rejected": [], "unfilled": [], "employees": [], "advisories": [], "findings": [],
                "jurisdiction": {"state": "CA", "status": "curated", "message": "on file"}},
    )
    body = FillVacantPreviewRequest(
        week_start=WEEK, job_id=job_id, role_hint="lead", shift_ids=[wanted], employee_id=only,
        exclude_employee_ids=[excluded], allow_split_shift=True, label="Spread the leads",
    )
    result, captured, user = _preview(monkeypatch, plan=plan, build=build, body=body)

    assert captured["plan"] == {
        "company_id": captured["plan"]["company_id"], "location_id": LOCATION,
        "week_start": WEEK, "week_end": date(2026, 8, 29),
        "job_ids": [job_id], "role_hint": "lead", "shift_ids": [wanted],
        "only_employee_ids": [only], "exclude_employee_ids": [excluded], "allow_split_shift": True,
    }
    built = captured["build"]
    assert built["created_by"] == user.id and built["channel_id"] is None
    assert built["surface"] == "editor" and built["shift_statuses"] == ("draft", "published")
    assert built["editor_location_id"] == LOCATION
    assert built["editor_week_start"] == WEEK and built["editor_week_end"] == date(2026, 8, 29)
    assert built["parsed"]["edit_requests"] == [
        {"kind": "assign", "target_shift_id": "s1", "to_employee_name": "Dana Reyes",
         "to_employee_id": plan["assignments"][0]["employee_id"]},
        {"kind": "assign", "target_shift_id": "s2", "to_employee_name": "Ben Ortiz",
         "to_employee_id": plan["assignments"][1]["employee_id"]},
    ]
    # Apply reads these back — the proposal doc itself carries no location or week.
    assert built["parsed"]["editor_location_id"] == str(LOCATION)
    assert built["parsed"]["editor_week_start"] == "2026-08-23"
    assert built["parsed"]["label"] == "Spread the leads"
    assert built["original_content"] == "[editor] fill vacant shifts — Spread the leads"

    assert result["status"] == "ready"
    assert result["proposal_id"] == "44444444-4444-4444-4444-444444444444"
    assert result["pill_text"] == "pill" and result["label"] == "Spread the leads"
    assert result["review"]["compliance_status"] == "verified"
    assert result["review"]["unfilled"] == [{
        "shift_id": "s3", "role": "Shift Lead", "starts_at": "2026-08-25T06:00:00+00:00",
        "ends_at": "2026-08-25T14:00:00+00:00", "reason": "policy: second shift that day", "exclusions": {},
    }]


def test_preview_relays_a_planner_clarify_or_refusal_without_staging(monkeypatch):
    plan = _plan([], status="clarify", message="There are no open shifts in this week to fill.")
    result, captured, _ = _preview(monkeypatch, plan=plan)
    assert result == {"status": "clarify", "message": "There are no open shifts in this week to fill.",
                      "unfilled": [], "jurisdiction": {"state": "CA", "status": "curated", "message": "on file"}}
    assert captured["build"] is None


def test_preview_with_nothing_fillable_is_empty_not_a_proposal(monkeypatch):
    plan = _plan([], [{"shift_id": "s1", "role": "Shift Lead", "starts_at": datetime(2026, 8, 24, 6, tzinfo=UTC),
                       "ends_at": datetime(2026, 8, 24, 14, tzinfo=UTC), "reason": "not qualified for the shift job", "exclusions": {}}])
    result, captured, _ = _preview(monkeypatch, plan=plan)
    assert result["status"] == "empty"
    assert result["unfilled"][0]["starts_at"] == "2026-08-24T06:00:00+00:00"
    assert captured["build"] is None


def test_an_empty_preview_says_why_the_same_way_the_thread_does(monkeypatch):
    """A scenario chip that only says "nothing could be filled" disagrees
    with the Huume answer beside it and tells the manager nothing to fix."""
    sentence = "Food Handler Card expired 2026-08-01 and blocks new scheduling"
    plan = _plan([], [{"shift_id": "s1", "role": "Shift Lead",
                       "starts_at": datetime(2026, 8, 24, 6, tzinfo=UTC),
                       "ends_at": datetime(2026, 8, 24, 14, tzinfo=UTC),
                       "reason": sentence, "reason_code": "credential_expired",
                       "exclusions": {sentence: 2},
                       "exclusion_codes": {"credential_expired": 2}}])
    result, _captured, _ = _preview(monkeypatch, plan=plan)
    assert result["status"] == "empty"
    assert sentence in result["message"]
    assert "Update that employee's credential record" in result["message"]


def test_an_empty_preview_with_no_open_seats_keeps_the_plain_sentence(monkeypatch):
    result, _captured, _ = _preview(monkeypatch, plan=_plan([], []))
    assert result["status"] == "empty"
    assert result["message"] == "No open position could be filled under the staffing rules."


def test_preview_maps_a_guard_refusal_to_refused_and_strips_the_channel_tail(monkeypatch):
    build = schedule_chat.ProposalBuild(
        kind="clarify", proposal_id=None, clarify_kind="refused",
        pill_text="\U0001F4C5 I couldn't stage any of those — Dana Reyes on the Shift Lead Mon Aug 24: already on the Opener. "
                  "Just reply to this message.",
    )
    result, _, _ = _preview(monkeypatch, plan=_plan([_assignment("s1", "Dana Reyes")]), build=build)
    assert result["status"] == "refused"
    assert result["message"].startswith("I couldn't stage any of those")
    assert "Just reply" not in result["message"] and "\U0001F4C5" not in result["message"]
    ambiguous = schedule_chat.ProposalBuild(kind="clarify", proposal_id=None, pill_text="Which Dana? 1. Dana Reyes 2. Dana Kim")
    result, _, _ = _preview(monkeypatch, plan=_plan([_assignment("s1", "Dana")]), build=ambiguous)
    assert result["status"] == "clarify" and result["message"] == "Which Dana? 1. Dana Reyes 2. Dana Kim"


# ── apply / discard ──────────────────────────────────────────────────────────

def _row(*, created_by, status="proposed", surface="editor", kind="edit", parse=None):
    return {
        "id": uuid4(), "company_id": uuid4(), "channel_id": None, "created_by": created_by,
        "proposal": {"kind": kind, "surface": surface, "ops": []},
        "parse": parse if parse is not None else {"editor_location_id": str(LOCATION), "editor_week_start": "2026-08-23"},
        "status": status,
    }


def _apply(monkeypatch, *, row, user=None, execute=None, created_shift_ids=None):
    user = user or _user()
    conn = _Conn(proposal_row=row, created_shift_ids=created_shift_ids)
    authz = _wire(monkeypatch, conn, company_id=uuid4())
    monkeypatch.setattr(planning, "get_company_features", AsyncMock(return_value={"employee_schedule": True}))
    executor = execute or AsyncMock(return_value="2 changes are live.")
    monkeypatch.setattr(schedule_chat, "execute_edit_proposal", executor)
    proposal_id = row["id"] if row else uuid4()
    return _run(planning.apply_fill_vacant(proposal_id, current_user=user)), executor, authz, conn


def test_apply_reruns_the_confirm_time_checks_with_the_week_bound_from_the_parse(monkeypatch):
    user = _user()
    row = _row(created_by=user.id)
    s1, s2 = uuid4(), uuid4()
    result, executor, authz, conn = _apply(monkeypatch, row=row, user=user, created_shift_ids=[s1, s2])

    assert result == {"status": "applied", "message": "2 changes are live.", "touched_shift_ids": [str(s1), str(s2)]}
    authz.assert_awaited_once()
    assert authz.await_args.kwargs["location_id"] == LOCATION
    kwargs = executor.await_args.kwargs
    assert kwargs["proposal_row"]["proposal"] == row["proposal"]
    assert kwargs["confirmed_by"] == user.id
    assert kwargs["week_start"] == WEEK and kwargs["week_end"] == date(2026, 8, 29)
    assert kwargs["features"] == {"employee_schedule": True}
    assert "force" not in kwargs


def test_apply_refuses_a_missing_row_someone_elses_row_and_a_spent_row(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _apply(monkeypatch, row=None)
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        _apply(monkeypatch, row=_row(created_by=uuid4()))
    assert exc.value.status_code == 403 and "Only the person who previewed" in exc.value.detail

    user = _user()
    with pytest.raises(HTTPException) as exc:
        _apply(monkeypatch, row=_row(created_by=user.id, status="confirmed"), user=user)
    assert exc.value.status_code == 409


def test_apply_only_accepts_editor_edit_proposals(monkeypatch):
    user = _user()
    for row in (_row(created_by=user.id, surface="channel"), _row(created_by=user.id, kind="batch")):
        with pytest.raises(HTTPException) as exc:
            _apply(monkeypatch, row=row, user=user)
        assert exc.value.status_code == 400


def test_apply_maps_executor_errors_to_409_and_422(monkeypatch):
    user = _user()
    claim = AsyncMock(side_effect=schedule_chat.ProposalExecutionClaimError("already being applied"))
    with pytest.raises(HTTPException) as exc:
        _apply(monkeypatch, row=_row(created_by=user.id), user=user, execute=claim)
    assert exc.value.status_code == 409 and "already being applied" in exc.value.detail

    scope = AsyncMock(side_effect=schedule_chat.ProposalScopeError("outside the selected schedule week"))
    with pytest.raises(HTTPException) as exc:
        _apply(monkeypatch, row=_row(created_by=user.id), user=user, execute=scope)
    assert exc.value.status_code == 422


def test_apply_reads_a_json_string_proposal_and_parse(monkeypatch):
    import json
    user = _user()
    row = _row(created_by=user.id)
    row["proposal"] = json.dumps(row["proposal"])
    row["parse"] = json.dumps(row["parse"])
    result, executor, _, _ = _apply(monkeypatch, row=row, user=user)
    assert result["status"] == "applied"
    assert executor.await_args.kwargs["week_start"] == WEEK


def test_discard_cancels_only_the_callers_proposed_row(monkeypatch):
    user = _user()
    row = _row(created_by=user.id)
    conn = _Conn(proposal_row=row, updated=row["id"])
    _wire(monkeypatch, conn, company_id=uuid4())
    assert _run(planning.discard_fill_vacant(row["id"], current_user=user)) is None
    query, args = conn.queries[-1]
    assert "SET status = 'cancelled'" in query and "status = 'proposed'" in query
    assert args[2] == user.id

    spent = _Conn(proposal_row=row, updated=None)
    _wire(monkeypatch, spent, company_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        _run(planning.discard_fill_vacant(row["id"], current_user=user))
    assert exc.value.status_code == 409

    other = _Conn(proposal_row=_row(created_by=uuid4()))
    _wire(monkeypatch, other, company_id=uuid4())
    with pytest.raises(HTTPException) as exc:
        _run(planning.discard_fill_vacant(row["id"], current_user=user))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("parse", [
    {}, {"editor_location_id": str(LOCATION)}, {"editor_week_start": "2026-08-23"},
    {"editor_location_id": "bad", "editor_week_start": "2026-08-23"},
    {"editor_location_id": str(LOCATION), "editor_week_start": "bad"},
    {"editor_location_id": str(LOCATION), "editor_week_start": "9999-12-31"},
])
def test_apply_requires_valid_persisted_scope_before_execution(monkeypatch, parse):
    user = _user("employee")
    executor = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        _apply(monkeypatch, row=_row(created_by=user.id, parse=parse), user=user, execute=executor)
    assert exc.value.status_code == 400
    executor.assert_not_awaited()


def test_apply_rechecks_revoked_location_permission(monkeypatch):
    user = _user("employee")
    row = _row(created_by=user.id)
    authz = _wire(monkeypatch, _Conn(proposal_row=row), company_id=row["company_id"])
    authz.side_effect = HTTPException(status_code=403, detail="not your store")
    executor = AsyncMock()
    monkeypatch.setattr(schedule_chat, "execute_edit_proposal", executor)
    with pytest.raises(HTTPException) as exc:
        _run(planning.apply_fill_vacant(row["id"], current_user=user))
    assert exc.value.status_code == 403
    executor.assert_not_awaited()


def test_apply_body_cannot_override_saved_scope_or_force(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    user = _user()
    row = _row(created_by=user.id)
    authz = _wire(monkeypatch, _Conn(proposal_row=row), company_id=row["company_id"])
    monkeypatch.setattr(planning, "get_company_features", AsyncMock(return_value={"employee_schedule": True}))
    executor = AsyncMock(return_value="applied")
    monkeypatch.setattr(schedule_chat, "execute_edit_proposal", executor)
    app = FastAPI()
    app.include_router(planning.router)
    app.dependency_overrides[planning.require_company_member] = lambda: user
    with TestClient(app) as client:
        response = client.post(f"/fill-vacant/{row['id']}/apply?force=true", json={
            "force": True, "editor_location_id": str(uuid4()), "editor_week_start": "2026-01-01",
        })
    assert response.status_code == 200
    assert authz.await_args.kwargs["location_id"] == LOCATION
    assert executor.await_args.kwargs["week_start"] == WEEK
    assert "force" not in executor.await_args.kwargs


def test_preview_refuses_over_cap_before_resolving_or_persisting(monkeypatch):
    result, captured, _ = _preview(monkeypatch, plan=_plan([
        _assignment(str(uuid4()), "Alex Lee") for _ in range(41)
    ]))
    assert result["status"] == "refused" and "41 schedule operations" in result["message"]
    assert captured["build"] is None


@pytest.mark.parametrize("available", [True, False])
def test_selected_employee_identity_reaches_real_resolution_and_saved_proposal(monkeypatch, available):
    import json

    company_id, user, employee_id, other_id, shift_id = uuid4(), _user(), uuid4(), uuid4(), uuid4()
    # Two equal names; only the selected UUID is valid for this assignment.
    people = {eid: {"id": eid, "first_name": "Alex", "last_name": "Lee"} for eid in (employee_id, other_id)}

    class IdentityConn:
        saved = None

        async def fetchrow(self, query, *args):
            if "FROM employees" in query:
                assert "id=$1 AND org_id=$2" in query and "work_location_id=$3" in query
                assert "NOT IN ('terminated', 'offboarded')" in query
                assert args == (employee_id, company_id, LOCATION)
                return people[employee_id] if available else None
            assert "INSERT INTO schedule_chat_proposals" in query
            self.saved = {"status": args[4], "proposal": json.loads(args[5]), "parse": json.loads(args[6])}
            return {"id": uuid4()}

    conn = IdentityConn()
    _wire(monkeypatch, conn, company_id=company_id)
    assignment = {**_assignment(shift_id, "Alex Lee"), "employee_id": str(employee_id)}
    monkeypatch.setattr(planning, "plan_vacant_fill", AsyncMock(return_value=_plan([assignment])))
    name_matcher = AsyncMock(side_effect=AssertionError("Planner IDs must not be matched by name"))
    monkeypatch.setattr(schedule_chat, "_match_single_employee", name_matcher)
    monkeypatch.setattr(schedule_chat, "_resolve_shift_ref", AsyncMock(return_value={"shift": {
        "id": shift_id, "role": "Lead", "location_id": LOCATION, "job_id": None,
        "starts_at": datetime(2026, 8, 24, 6, tzinfo=UTC), "ends_at": datetime(2026, 8, 24, 14, tzinfo=UTC),
        "break_minutes": 0, "kind": "work", "training_requirement_id": None, "published_at": None,
    }}))
    monkeypatch.setattr(schedule_chat, "check_shift_compliance", AsyncMock(return_value=[]))
    guard = AsyncMock()
    monkeypatch.setattr(schedule_chat, "_review_assign_ops", guard)
    monkeypatch.setattr(schedule_chat, "_ops_jurisdiction", AsyncMock(return_value={"state": "CA", "status": "curated"}))
    result = _run(planning.preview_fill_vacant(
        LOCATION, FillVacantPreviewRequest(week_start=WEEK, employee_id=employee_id), current_user=user,
    ))
    name_matcher.assert_not_awaited()
    if available:
        assert result["status"] == "ready"
        assert guard.await_args.args[2][0]["to_employee_id"] == str(employee_id)
        assert conn.saved["proposal"]["ops"][0]["to_employee_id"] == str(employee_id)
        assert conn.saved["parse"]["editor_location_id"] == str(LOCATION)
        assert conn.saved["parse"]["editor_week_start"] == WEEK.isoformat()
    else:
        assert result["status"] == "clarify" and "no longer active" in result["message"]
        guard.assert_not_awaited()
        assert conn.saved["status"] == "clarifying"
