"""Matcha Schedule device sessions stay separate from ordinary web sessions."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.core import dependencies
from app.core.models.auth import LoginRequest, RefreshTokenRequest
from app.core.routes.auth import login as login_routes
from app.core.services import auth, session_tokens


def _settings():
    return SimpleNamespace(
        jwt_secret_key="test-secret",
        jwt_algorithm="HS256",
        jwt_access_token_expire_minutes=15,
        jwt_refresh_token_expire_days=7,
        jwt_refresh_idle_expire_minutes=30,
        jwt_session_absolute_expire_hours=12,
    )


def _request():
    return Request({"type": "http", "method": "POST", "path": "/api/auth/login",
                    "headers": [], "client": ("127.0.0.1", 12345)})


class _Connection:
    def __init__(self, role="employee", employment_status="active"):
        self.user_id = uuid4()
        self.role = role
        self.employment_status = employment_status
        self.employee_missing = False
        self.suspended = False
        self.sid = None
        self.revoked = False
        self.device_updates = 0

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchrow(self, query, *args):
        if "FROM users" in query or "FROM users u" in query:
            return {
                "id": self.user_id, "email": "employee@example.com", "password_hash": "unused",
                "role": self.role, "is_active": True, "is_suspended": self.suspended,
                "company_deleted_at": None, "company_name": None,
                "created_at": datetime.now(timezone.utc), "last_login": None,
            }
        if "FROM employees" in query:
            if self.employee_missing:
                return None
            return {"id": uuid4(), "employment_status": self.employment_status}
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if "SELECT EXISTS" in query and "auth_device_sessions" in query:
            return args == (self.sid, self.user_id) and not self.revoked
        assert "UPDATE auth_device_sessions" in query
        self.device_updates += 1
        return self.sid if args[0] == self.sid and not self.revoked \
            and self.employment_status not in ("terminated", "offboarded") else None

    async def execute(self, query, *args):
        if "INSERT INTO auth_device_sessions" in query:
            self.sid = args[0]
        elif "UPDATE auth_device_sessions SET revoked_at" in query:
            assert args == (self.sid, self.user_id)
            self.revoked = True
        else:
            raise AssertionError(query)


@pytest.fixture
def route_env(monkeypatch):
    conn = _Connection()

    @asynccontextmanager
    async def get_connection():
        yield conn

    async def verify_password(_password, _hash):
        return True

    async def touch(_user_id):
        return None

    async def not_revoked(*_args):
        return False

    monkeypatch.setattr(login_routes, "get_connection", get_connection)
    monkeypatch.setattr(dependencies, "get_connection", get_connection)
    monkeypatch.setattr(login_routes, "verify_password_async", verify_password)
    monkeypatch.setattr(login_routes, "_touch_user_last_login", touch)
    monkeypatch.setattr(login_routes, "session_revoked", not_revoked)
    monkeypatch.setattr(login_routes, "_check_login_rate_limit", lambda _ip: None)
    for module in (login_routes, auth, session_tokens):
        monkeypatch.setattr(module, "get_settings", _settings)
    return conn


@pytest.mark.asyncio
async def test_mobile_login_refresh_and_device_only_logout(route_env):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password",
                     client="ios_schedule", device_name="iPhone"), _request(),
    )
    payload = auth.decode_token(result.refresh_token, expected_type="refresh")
    assert payload.sid == str(conn.sid)
    assert payload.cl == "ios_schedule"
    assert payload.exp - payload.session_started_at <= 12 * 3600
    assert conn.device_updates == 0
    access = HTTPAuthorizationCredentials(scheme="Bearer", credentials=result.access_token)
    assert auth.decode_token(result.access_token, expected_type="access") is None
    assert (await dependencies.get_token_payload(access)).sid == str(conn.sid)

    rotated = await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    rotated_payload = auth.decode_token(rotated.refresh_token, expected_type="refresh")
    assert rotated_payload.sid == payload.sid
    assert rotated_payload.session_started_at == payload.session_started_at
    assert rotated_payload.exp - payload.session_started_at <= 12 * 3600
    assert conn.device_updates == 1
    rotated_access = HTTPAuthorizationCredentials(scheme="Bearer", credentials=rotated.access_token)
    assert (await dependencies.get_token_payload(rotated_access)).sid == str(conn.sid)

    await login_routes.mobile_logout(RefreshTokenRequest(refresh_token=rotated.refresh_token))
    with pytest.raises(HTTPException) as access_error:
        await dependencies.get_token_payload(access)
    assert access_error.value.status_code == 401
    with pytest.raises(HTTPException) as access_error:
        await dependencies.get_token_payload(rotated_access)
    assert access_error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=rotated.refresh_token))
    assert error.value.status_code == 401

    web = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password"), _request(),
    )
    assert (await login_routes.refresh_token(
        RefreshTokenRequest(refresh_token=web.refresh_token)
    )).refresh_token


@pytest.mark.asyncio
async def test_refresh_locks_user_row_before_revocation_check(route_env):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    original_fetchrow = conn.fetchrow

    async def fetchrow(query, *args):
        if "FROM users WHERE id = $1" in query:
            assert "FOR UPDATE OF users" in query
        return await original_fetchrow(query, *args)

    conn.fetchrow = fetchrow
    assert (await login_routes.refresh_token(
        RefreshTokenRequest(refresh_token=result.refresh_token)
    )).refresh_token


@pytest.mark.asyncio
async def test_mobile_login_rejects_business_user_and_inactive_employee(route_env):
    conn = route_env
    request = LoginRequest(email="employee@example.com", password="password", client="ios_schedule")
    conn.role = "client"
    with pytest.raises(HTTPException) as error:
        await login_routes.login(request, _request())
    assert error.value.status_code == 403
    assert conn.sid is None

    conn.role = "employee"
    conn.employment_status = "active"
    conn.employee_missing = True
    with pytest.raises(HTTPException) as error:
        await login_routes.login(request, _request())
    assert error.value.status_code == 403
    assert conn.sid is None

    conn.employee_missing = False
    conn.employment_status = "terminated"
    with pytest.raises(HTTPException) as error:
        await login_routes.login(request, _request())
    assert error.value.status_code == 403
    assert conn.sid is None


@pytest.mark.asyncio
async def test_terminated_employee_cannot_refresh_mobile_session(route_env):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    conn.employment_status = "terminated"
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_suspended_employee_cannot_refresh_mobile_session(route_env):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    conn.suspended = True
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_web_refresh_has_no_device_session_dependency(route_env):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password"), _request(),
    )
    assert conn.sid is None
    assert auth.decode_token(result.refresh_token, expected_type="refresh").sid is None
    rotated = await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert rotated.refresh_token
    assert conn.device_updates == 0
    with pytest.raises(HTTPException) as error:
        await login_routes.mobile_logout(RefreshTokenRequest(refresh_token=rotated.refresh_token))
    assert error.value.status_code == 401
