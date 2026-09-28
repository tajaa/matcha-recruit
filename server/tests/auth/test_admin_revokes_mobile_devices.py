"""Suspending a user or deactivating a company ends their Matcha Schedule
devices: the push send checks the device session, not the user row."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.routes.admin import companies as company_routes
from app.core.routes.admin import users as user_routes


class _Conn:
    def __init__(self, update_result="UPDATE 1", employee_user_ids=()):
        self.update_result = update_result
        self.employee_user_ids = list(employee_user_ids)
        self.executed = []

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if query.startswith("UPDATE users SET is_suspended") or query.startswith("UPDATE companies"):
            return self.update_result
        return "UPDATE 1"

    async def fetchrow(self, query, *args):
        self.executed.append((query, args))
        return {"id": args[0]} if self.update_result != "UPDATE 0" else None

    async def fetch(self, query, *args):
        assert "FROM employees WHERE org_id = $1" in query
        return [{"user_id": u} for u in self.employee_user_ids]


def _patch(monkeypatch, module, conn):
    @asynccontextmanager
    async def connection():
        yield conn
    monkeypatch.setattr(module, "get_connection", connection)


def _device_statements(conn):
    return [(q, a) for q, a in conn.executed
            if "auth_device_sessions" in q or "device_tokens" in q]


@pytest.mark.asyncio
async def test_suspend_ends_the_users_mobile_devices(monkeypatch):
    conn, user_id = _Conn(), uuid4()
    _patch(monkeypatch, user_routes, conn)
    assert await user_routes.admin_suspend_user(user_id, user_routes.SuspendBody()) == {"ok": True}
    statements = _device_statements(conn)
    assert len(statements) == 2
    assert all(args == ([user_id],) for _q, args in statements)


@pytest.mark.asyncio
async def test_suspending_an_unknown_user_touches_nothing(monkeypatch):
    conn = _Conn(update_result="UPDATE 0")
    _patch(monkeypatch, user_routes, conn)
    with pytest.raises(HTTPException) as exc:
        await user_routes.admin_suspend_user(uuid4(), user_routes.SuspendBody())
    assert exc.value.status_code == 404
    assert _device_statements(conn) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["delete_company_admin", "admin_soft_delete_company"])
async def test_company_delete_ends_its_employees_mobile_devices(monkeypatch, route):
    employees = [uuid4(), uuid4()]
    conn = _Conn(employee_user_ids=employees)
    _patch(monkeypatch, company_routes, conn)
    monkeypatch.setattr(
        "app.matcha.services.matcha_work.matcha_work_document.invalidate_company_profile_cache",
        lambda _company_id: None,
    )
    assert await getattr(company_routes, route)(uuid4()) == {"ok": True}
    statements = _device_statements(conn)
    assert len(statements) == 2
    assert all(args == (employees,) for _q, args in statements)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["delete_company_admin", "admin_soft_delete_company"])
async def test_deleting_a_missing_company_touches_no_devices(monkeypatch, route):
    conn = _Conn(update_result="UPDATE 0")
    _patch(monkeypatch, company_routes, conn)
    with pytest.raises(HTTPException) as exc:
        await getattr(company_routes, route)(uuid4())
    assert exc.value.status_code == 404
    assert _device_statements(conn) == []
