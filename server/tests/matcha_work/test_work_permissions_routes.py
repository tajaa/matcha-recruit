"""Route shaping tests for the effective Work permission roster."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from app.core.models.auth import CurrentUser
from app.matcha.routes.matcha_work import permissions


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, query, *args):
        assert "FROM mw_work_permissions" in query
        return self.rows


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
