"""Route shaping tests for the effective Work permission roster."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.core.models.auth import CurrentUser
from app.matcha.routes.matcha_work import permissions
from app.matcha.routes.matcha_work.permissions import WorkPermissionUpdate


class FakeConn:
    def __init__(self, rows=None, *, company_name="Example Company", owner_id=None):
        self.rows = rows
        self.company_name = company_name
        self.owner_id = owner_id
        self.roster_query = None

    async def fetch(self, query, *args):
        assert "FROM mw_work_permissions" in query
        self.roster_query = query
        return self.rows

    async def fetchval(self, query, *args):
        if "SELECT name FROM companies" in query:
            return self.company_name
        if "SELECT owner_id FROM companies" in query:
            return self.owner_id
        raise AssertionError(f"Unexpected query: {query}")


def _connection_context(conn):
    @asynccontextmanager
    async def context():
        yield conn
    return context


def _row(*, role="employee", source=("company_employee",), explicit=None, owner=False):
    return {
        "user_id": uuid4(),
        "email": "person@example.com",
        "name": "Person Example",
        "role": role,
        "avatar_url": None,
        "eligible_via": list(source),
        "explicit_level": explicit,
        "granted_by": None,
        "created_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 8, 12, tzinfo=timezone.utc),
        "is_company_owner": owner,
    }


def _user(role="admin"):
    return CurrentUser(id=uuid4(), email="admin@example.com", role=role)


@pytest.mark.asyncio
async def test_roster_returns_effective_employee_default(monkeypatch):
    company_id = uuid4()
    conn = FakeConn([_row()])
    monkeypatch.setattr(permissions, "get_connection", _connection_context(conn))
    monkeypatch.setattr(permissions, "_target_company", AsyncMock(return_value=company_id))
    monkeypatch.setattr(permissions, "_assert_manager", AsyncMock())

    result = await permissions.list_work_permissions(current_user=_user())

    entry = result["permissions"][0]
    assert result["company_id"] == company_id
    assert result["company_name"] == "Example Company"
    assert "e.termination_date IS NULL" in conn.roster_query
    assert entry["effective_level"] == "member"
    assert entry["effective_source"] == "employee_default"
    assert entry["explicit_level"] is None
    assert "actions.propose" in entry["capabilities"]
    assert "actions.execute" not in entry["capabilities"]


@pytest.mark.asyncio
async def test_roster_explicit_grant_overrides_default(monkeypatch):
    company_id = uuid4()
    conn = FakeConn([_row(explicit="reviewer")])
    monkeypatch.setattr(permissions, "get_connection", _connection_context(conn))
    monkeypatch.setattr(permissions, "_target_company", AsyncMock(return_value=company_id))
    monkeypatch.setattr(permissions, "_assert_manager", AsyncMock())

    result = await permissions.list_work_permissions(current_user=_user())
    entry = result["permissions"][0]

    assert entry["effective_level"] == "reviewer"
    assert entry["effective_source"] == "explicit"
    assert entry["explicit_level"] == "reviewer"
    assert entry["immutable"] is False


@pytest.mark.asyncio
async def test_roster_keeps_stale_explicit_grant_reversible(monkeypatch):
    company_id = uuid4()
    conn = FakeConn([_row(source=("explicit_grant",), explicit="operator")])
    monkeypatch.setattr(permissions, "get_connection", _connection_context(conn))
    monkeypatch.setattr(permissions, "_target_company", AsyncMock(return_value=company_id))
    monkeypatch.setattr(permissions, "_assert_manager", AsyncMock())

    result = await permissions.list_work_permissions(current_user=_user())
    entry = result["permissions"][0]

    assert entry["effective_level"] == "operator"
    assert entry["effective_source"] == "explicit"
    assert entry["eligible_via"] == ["explicit_grant"]


@pytest.mark.asyncio
async def test_roster_marks_company_owner_immutable(monkeypatch):
    company_id = uuid4()
    conn = FakeConn([_row(role="employee", source=("company_owner",), owner=True)])
    monkeypatch.setattr(permissions, "get_connection", _connection_context(conn))
    monkeypatch.setattr(permissions, "_target_company", AsyncMock(return_value=company_id))
    monkeypatch.setattr(permissions, "_assert_manager", AsyncMock())

    result = await permissions.list_work_permissions(current_user=_user())
    entry = result["permissions"][0]

    assert entry["effective_level"] == "admin"
    assert entry["effective_source"] == "company_owner"
    assert entry["immutable"] is True


@pytest.mark.asyncio
async def test_roster_marks_platform_admin_admin(monkeypatch):
    company_id = uuid4()
    conn = FakeConn([_row(role="admin", source=("channel_member",))])
    monkeypatch.setattr(permissions, "get_connection", _connection_context(conn))
    monkeypatch.setattr(permissions, "_target_company", AsyncMock(return_value=company_id))
    monkeypatch.setattr(permissions, "_assert_manager", AsyncMock())

    result = await permissions.list_work_permissions(current_user=_user())

    entry = result["permissions"][0]
    assert entry["effective_level"] == "admin"
    assert entry["effective_source"] == "platform_admin"
    assert entry["immutable"] is True


@pytest.mark.asyncio
async def test_set_owner_rejected(monkeypatch):
    company_id = uuid4()
    owner_id = uuid4()
    conn = FakeConn(owner_id=owner_id)
    monkeypatch.setattr(permissions, "get_connection", _connection_context(conn))
    monkeypatch.setattr(permissions, "_target_company", AsyncMock(return_value=company_id))
    monkeypatch.setattr(permissions, "_assert_manager", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await permissions.set_work_permission(
            user_id=owner_id,
            body=WorkPermissionUpdate(level="member"),
            current_user=_user(),
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_owner_rejected(monkeypatch):
    company_id = uuid4()
    owner_id = uuid4()
    conn = FakeConn(owner_id=owner_id)
    monkeypatch.setattr(permissions, "get_connection", _connection_context(conn))
    monkeypatch.setattr(permissions, "_target_company", AsyncMock(return_value=company_id))
    monkeypatch.setattr(permissions, "_assert_manager", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await permissions.delete_work_permission(
            user_id=owner_id,
            current_user=_user(),
        )

    assert exc.value.status_code == 400
