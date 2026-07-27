from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks

from app.core.models.auth import CurrentUser
from app.matcha.models.er.case import ERCaseCreate, ERCaseUpdate
from app.matcha.routes.er_copilot import _shared as er_copilot_shared
from app.matcha.routes.er_copilot import crud as er_copilot_routes


class _ConnContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _CreateCaseConn:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, *args):
        if "INSERT INTO er_cases" in query:
            return self.row
        raise AssertionError(f"Unexpected fetchrow query: {query}")


class _UpdateCaseConn:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, query, *args):
        if "UPDATE er_cases" in query:
            return self.row
        raise AssertionError(f"Unexpected fetchrow query: {query}")

    async def fetchval(self, query, *args):
        if "SELECT COUNT(*) FROM er_case_documents" in query:
            return 0
        raise AssertionError(f"Unexpected fetchval query: {query}")


def _request():
    return SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))


def _user() -> CurrentUser:
    return CurrentUser(id=uuid4(), email="client@example.com", role="client")


@pytest.mark.asyncio
async def test_create_case_queues_risk_refresh(monkeypatch: pytest.MonkeyPatch):
    company_id = uuid4()
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "case_number": "ER-2026-03-ABCD",
        "title": "Policy issue",
        "description": "Details",
        "intake_context": None,
        "status": "open",
        "company_id": company_id,
        "created_by": uuid4(),
        "assigned_to": None,
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "category": None,
        "outcome": None,
        "involved_employees": [],
    }

    monkeypatch.setattr(er_copilot_routes, "get_connection", lambda: _ConnContext(_CreateCaseConn(row)))
    async def _fake_company_id(current_user):
        return company_id

    monkeypatch.setattr(er_copilot_routes, "get_client_company_id", _fake_company_id)

    async def _noop_log_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(er_copilot_routes, "log_audit", _noop_log_audit)
    # create_case delegates to create_case_core (services/er/er_case_create.py),
    # which reaches log_audit via its own lazy import of _shared — patching
    # crud.py's copy of the name doesn't affect that lookup.
    monkeypatch.setattr(er_copilot_shared, "log_audit", _noop_log_audit)

    background_tasks = BackgroundTasks()
    response = await er_copilot_routes.create_case(
        ERCaseCreate(title="Policy issue", description="Details"),
        _request(),
        background_tasks,
        _user(),
    )

    assert response.company_id == company_id
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].args == (company_id,)


@pytest.mark.asyncio
async def test_update_case_queues_risk_refresh_for_non_closed_status_change(monkeypatch: pytest.MonkeyPatch):
    company_id = uuid4()
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "case_number": "ER-2026-03-ABCD",
        "title": "Policy issue",
        "description": "Details",
        "intake_context": None,
        "status": "in_review",
        "company_id": company_id,
        "created_by": uuid4(),
        "assigned_to": None,
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "category": None,
        "outcome": None,
        "involved_employees": [],
    }

    monkeypatch.setattr(er_copilot_routes, "get_connection", lambda: _ConnContext(_UpdateCaseConn(row)))
    async def _fake_company_id(current_user):
        return company_id

    monkeypatch.setattr(er_copilot_routes, "get_client_company_id", _fake_company_id)

    async def _noop_verify_case_company(*args, **kwargs):
        return None

    async def _noop_log_audit(*args, **kwargs):
        return None

    monkeypatch.setattr(er_copilot_routes, "_verify_case_company", _noop_verify_case_company)
    monkeypatch.setattr(er_copilot_routes, "log_audit", _noop_log_audit)

    background_tasks = BackgroundTasks()
    response = await er_copilot_routes.update_case(
        row["id"],
        ERCaseUpdate(status="in_review"),
        _request(),
        background_tasks,
        _user(),
    )

    assert response.status == "in_review"
    assert len(background_tasks.tasks) == 1
    assert background_tasks.tasks[0].args == (company_id,)
