"""Claim validation, qualification filtering and manager review without a database."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.matcha.models.scheduling.employee_schedule import RequestReview, ScheduleRequestCreate
from app.matcha.routes.employee_portal import schedule as portal
from app.matcha.routes.employee_schedule import requests as manager


NOW = datetime.now(timezone.utc)


def test_claim_requires_only_a_shift():
    with pytest.raises(ValidationError, match="shift_id is required"):
        ScheduleRequestCreate(request_type="claim")
    with pytest.raises(ValidationError, match="only accept a shift_id"):
        ScheduleRequestCreate(request_type="claim", shift_id=uuid4(), target_employee_id=uuid4())


@pytest.mark.asyncio
async def test_open_seats_filter_unqualified_and_strip_assignment_details(monkeypatch):
    company_id, employee_id, allowed_id, blocked_id = (uuid4() for _ in range(4))
    job_id = uuid4()
    candidates = [
        {"id": allowed_id, "job_id": job_id, "starts_at": NOW + timedelta(days=1), "has_conflict": True},
        {"id": blocked_id, "job_id": job_id, "starts_at": NOW + timedelta(days=2), "has_conflict": False},
    ]
    received_ids = []

    class Conn:
        async def fetch(self, query, *args):
            assert "NOT EXISTS" in query and "request_type = 'claim'" in query
            assert args[:2] == (company_id, employee_id)
            return candidates

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def qualified(_conn, *, as_of, **_kwargs):
        return {employee_id} if as_of == candidates[0]["starts_at"].date() else set()

    async def shifts(_conn, _company, _start, _end, **kwargs):
        received_ids.extend(kwargs["shift_ids"])
        return [{"id": str(allowed_id), "assignments": [
            {"employee_id": str(uuid4()), "name": "Coworker", "job_title": "Barista",
             "status": "assigned", "manager_note": "private"},
        ]}]

    monkeypatch.setattr(portal, "get_connection", connection)
    monkeypatch.setattr(
        "app.matcha.services.scheduling.schedule_profiles.fetch_effective_job_employee_ids", qualified,
    )
    monkeypatch.setattr("app.matcha.routes.employee_schedule._shared.fetch_shifts", shifts)

    result = await portal.list_my_open_seats(
        start=NOW, end=NOW + timedelta(days=7), employee={"id": employee_id, "org_id": company_id},
    )
    assert received_ids == [allowed_id]
    assert result["shifts"][0]["has_conflict"] is True
    assert "manager_note" not in result["shifts"][0]["assignments"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state,expected",
    [("unpublished", 404), ("past", 409), ("full", 409), ("mine", 409),
     ("unqualified", 409), ("duplicate", 409)],
)
async def test_claim_create_validation(monkeypatch, state, expected):
    company_id, employee_id, shift_id = (uuid4() for _ in range(3))

    class Conn:
        def transaction(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def fetchrow(self, query, *_args):
            if "FOR UPDATE" in query:
                return {"status": "draft" if state == "unpublished" else "published",
                        "starts_at": NOW - timedelta(hours=1) if state == "past" else NOW + timedelta(days=1),
                        "required_staff": 1, "job_id": None}
            raise AssertionError(query)

        async def fetchval(self, query, *_args):
            if "NOW()" in query:
                return NOW
            if "count(*)" in query:
                return 1 if state == "full" else 0
            if "schedule_shift_assignments" in query:
                return 1 if state == "mine" else None
            if "schedule_requests" in query:
                return 1 if state == "duplicate" else None
            raise AssertionError(query)

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def qualified(_conn, **_kwargs):
        return set() if state == "unqualified" else {employee_id}

    monkeypatch.setattr(portal, "get_connection", connection)
    monkeypatch.setattr(
        "app.matcha.services.scheduling.schedule_profiles.fetch_effective_job_employee_ids", qualified,
    )
    with pytest.raises(HTTPException) as exc:
        await portal.create_my_schedule_request(
            ScheduleRequestCreate(request_type="claim", shift_id=shift_id),
            {"id": employee_id, "org_id": company_id},
        )
    assert exc.value.status_code == expected


@pytest.mark.asyncio
async def test_claim_create_starts_awaiting_manager_and_dispatches_after_commit(monkeypatch):
    company_id, employee_id, shift_id, request_id = (uuid4() for _ in range(4))
    events = []

    class Conn:
        def transaction(self):
            return self

        async def __aenter__(self):
            events.append("begin")
            return self

        async def __aexit__(self, *_args):
            events.append("commit")
            return False

        async def fetchrow(self, query, *_args):
            if "FOR UPDATE" in query:
                return {"status": "published", "starts_at": NOW + timedelta(days=1),
                        "required_staff": 2, "job_id": None}
            return {"id": request_id, "status": "awaiting_manager"}

        async def fetchval(self, query, *args):
            if "NOW()" in query:
                return NOW
            if "count(*)" in query:
                return 1
            if "INSERT INTO schedule_requests" in query:
                assert args[2] == "claim"
                events.append("insert")
                return request_id
            return None

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def qualified(_conn, **_kwargs):
        return {employee_id}

    async def audit(*_args, **_kwargs):
        events.append("audit")

    def dispatch(_request_id):
        events.append("dispatch")

    monkeypatch.setattr(portal, "get_connection", connection)
    monkeypatch.setattr(portal, "_dispatch_manager_ready", dispatch)
    monkeypatch.setattr(portal, "serialize_request", lambda row: row, raising=False)
    monkeypatch.setattr("app.matcha.routes.employee_schedule._shared.serialize_request", lambda row: row)
    monkeypatch.setattr("app.matcha.routes.employee_schedule._shared.log_audit", audit)
    monkeypatch.setattr(
        "app.matcha.services.scheduling.schedule_profiles.fetch_effective_job_employee_ids", qualified,
    )

    result = await portal.create_my_schedule_request(
        ScheduleRequestCreate(request_type="claim", shift_id=shift_id),
        {"id": employee_id, "org_id": company_id},
    )
    assert result["status"] == "awaiting_manager"
    assert events == ["begin", "insert", "audit", "commit", "dispatch"]


@pytest.mark.asyncio
@pytest.mark.parametrize("force,expected_status", [(False, 409), (True, 200)])
async def test_manager_claim_full_shift_requires_force(monkeypatch, force, expected_status):
    company_id, employee_id, shift_id, request_id = (uuid4() for _ in range(4))
    applied = []
    future = NOW + timedelta(days=1)

    class Conn:
        def transaction(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def fetchrow(self, query, *_args):
            if "FROM schedule_requests" in query:
                return {"id": request_id, "request_type": "claim", "shift_id": shift_id,
                        "employee_id": employee_id, "target_employee_id": None,
                        "counter_shift_id": None, "counterparty_confirmed_at": None,
                        "status": "awaiting_manager", "availability_effective_on": None}
            return {"status": "approved"}

        async def fetchval(self, query, *_args):
            if "NOW()" in query:
                return NOW
            if "schedule_shift_assignments" in query:
                return None
            if "starts_at" in query:
                return future
            raise AssertionError(query)

        async def execute(self, *_args):
            return "UPDATE 1"

    @asynccontextmanager
    async def connection():
        yield Conn()

    async def locked(_conn, _company, *_ids):
        return {str(shift_id): {"id": shift_id, "status": "published", "starts_at": future,
                               "required_staff": 1, "assigned_count": 1}}

    async def noop(*_args, **_kwargs):
        return None

    async def check(*_args, **_kwargs):
        return [], None

    async def apply(*_args, **_kwargs):
        applied.append(employee_id)

    monkeypatch.setattr(manager, "get_connection", connection)
    monkeypatch.setattr(manager, "require_company_id", lambda _user: _company(company_id))
    monkeypatch.setattr(manager, "fetch_locked_shift_pair", locked)
    monkeypatch.setattr(manager, "lock_scheduling_employees", noop)
    monkeypatch.setattr(manager, "_check_recipient", check)
    monkeypatch.setattr(manager, "apply_assignment_core", apply)
    monkeypatch.setattr(manager, "mark_manager_ready_notifications_resolved", noop)
    monkeypatch.setattr(manager, "log_audit", noop)
    monkeypatch.setattr(manager, "reconcile_warning_events", noop)
    monkeypatch.setattr(manager, "stage_request_event", noop)
    monkeypatch.setattr(manager, "dispatch_events", lambda: None)
    monkeypatch.setattr(manager, "serialize_request", lambda row: row)

    if expected_status == 409:
        with pytest.raises(HTTPException) as exc:
            await manager.review_request(request_id, RequestReview(decision="approved", force=force), SimpleNamespace(id=uuid4()))
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "shift_full"
        assert applied == []
    else:
        await manager.review_request(request_id, RequestReview(decision="approved", force=force), SimpleNamespace(id=uuid4()))
        assert applied == [employee_id]


async def _company(company_id):
    return company_id
