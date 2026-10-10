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
from app.core.models.auth import LoginRequest, MobileLogoutRequest, RefreshTokenRequest
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
        self.generation = 0
        self.company_deleted_at = None
        # A business admin's company is non-personal and approved.
        self.client_company_ok = True
        # Whether the previous generation is still inside the lost-response
        # grace window (_MOBILE_REFRESH_GRACE_SECONDS after the last rotation).
        self.grace_open = True
        self.executed: list[tuple[str, tuple]] = []

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchrow(self, query, *args):
        if "refresh_generation = $4 + 1" in query:
            sid, user_id, _inactive, presented, grace = args
            assert grace == login_routes._MOBILE_REFRESH_GRACE_SECONDS
            assert login_routes._MOBILE_ELIGIBLE_SQL in query
            if sid != self.sid or user_id != self.user_id or self.revoked \
                    or not self._eligible() \
                    or presented != self.generation - 1 or not self.grace_open:
                return None
            return {"id": self.sid, "refresh_generation": self.generation}
        if "UPDATE auth_device_sessions" in query:
            # Compare-and-swap rotation: the presented generation must match.
            assert "refresh_generation = $4" in query
            assert login_routes._MOBILE_ELIGIBLE_SQL in query
            sid, user_id, _inactive, presented = args
            self.device_updates += 1
            if sid != self.sid or user_id != self.user_id or self.revoked \
                    or not self._eligible() \
                    or presented != self.generation:
                return None
            self.generation += 1
            return {"id": self.sid, "refresh_generation": self.generation}
        if "FROM users" in query or "FROM users u" in query:
            return {
                "id": self.user_id, "email": "employee@example.com", "password_hash": "unused",
                "role": self.role, "is_active": True, "is_suspended": self.suspended,
                "company_deleted_at": self.company_deleted_at, "company_name": None,
                "created_at": datetime.now(timezone.utc), "last_login": None,
            }
        if "FROM employees" in query:
            if self.employee_missing:
                return None
            return {"id": uuid4(), "employment_status": self.employment_status}
        raise AssertionError(query)

    def _eligible(self):
        """What `_MOBILE_ELIGIBLE_SQL` decides, for the role the fake holds."""
        if self.role == "employee":
            return self.employment_status not in ("terminated", "offboarded")
        return self.role == "client" and self.client_company_ok

    async def fetchval(self, query, *args):
        if "SELECT EXISTS" in query and "auth_device_sessions" in query:
            return args == (self.sid, self.user_id) and not self.revoked
        if "FROM clients cl JOIN companies c" in query:
            assert args == (self.user_id,)
            assert "NOT COALESCE(c.is_personal, false)" in query
            return self.client_company_ok
        raise AssertionError(query)

    async def execute(self, query, *args):
        self.executed.append((query, args))
        if "INSERT INTO auth_device_sessions" in query:
            self.sid = args[0]
        elif "UPDATE auth_device_sessions SET revoked_at" in query:
            if "user_id = ANY($1::uuid[])" in query:
                # revoke_mobile_devices: every device of these users.
                if self.user_id in args[0]:
                    self.revoked = True
            elif "refresh_generation <> $3" in query:
                # Replay revoke: only fires when the generation really moved on.
                assert args[:2] == (self.sid, self.user_id)
                if args[2] != self.generation:
                    self.revoked = True
            else:
                assert args == (self.sid, self.user_id)
                self.revoked = True
        elif "UPDATE users SET tokens_valid_after" in query:
            return None
        elif "DELETE FROM device_tokens" in query:
            return None
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

    await login_routes.mobile_logout(
        MobileLogoutRequest(refresh_token=rotated.refresh_token, push_token="d" * 64)
    )
    token_deletes = [(q, a) for q, a in conn.executed if "DELETE FROM device_tokens" in q]
    assert len(token_deletes) == 1
    assert "device_session_id = $2" in token_deletes[0][0]
    assert token_deletes[0][1] == (conn.user_id, conn.sid, "d" * 64)
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
        await login_routes.mobile_logout(MobileLogoutRequest(refresh_token=rotated.refresh_token))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_replayed_mobile_refresh_token_revokes_the_device(route_env):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    first = auth.decode_token(result.refresh_token, expected_type="refresh")
    assert first.gen == 0
    rotated = await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert auth.decode_token(rotated.refresh_token, expected_type="refresh").gen == 1
    assert not conn.revoked

    # Past the lost-response grace window, presenting the superseded token
    # again is a replay: reject it AND revoke
    # the session so the holder of the rotated token is cut off too.
    conn.grace_open = False
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert error.value.status_code == 401
    assert conn.revoked
    assert any("refresh_generation <> $3" in q for q, _ in conn.executed)
    assert any("DELETE FROM device_tokens WHERE device_session_id = $1" in q
               for q, _ in conn.executed)
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=rotated.refresh_token))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_mobile_refresh_token_without_generation_is_rejected(route_env):
    conn = route_env
    await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    legacy = auth.create_refresh_token(
        conn.user_id, "employee@example.com", "employee",
        extra_claims={"sid": str(conn.sid), "cl": "ios_schedule"},
    )
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=legacy))
    assert error.value.status_code == 401
    assert conn.device_updates == 0


@pytest.mark.asyncio
async def test_deactivated_company_blocks_employee_login_and_refresh(route_env):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    conn.company_deleted_at = datetime.now(timezone.utc)
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert error.value.status_code == 401
    assert conn.device_updates == 0
    with pytest.raises(HTTPException) as error:
        await login_routes.login(
            LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
            _request(),
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_global_revocation_watermark_is_stamped_at_write_time(route_env):
    """NOW() is frozen at transaction start — before this UPDATE waits on the
    row lock a concurrent refresh holds — so a refresh committing during the
    wait would outlive the logout. The watermark must use clock_timestamp()."""
    conn = route_env
    await dependencies.revoke_user_sessions(conn, conn.user_id)
    query, args = next((q, a) for q, a in conn.executed if "tokens_valid_after" in q)
    assert "tokens_valid_after = clock_timestamp()" in query
    assert "NOW()" not in query
    assert args == (conn.user_id,)


@pytest.mark.asyncio
async def test_lost_refresh_response_is_retried_inside_the_grace_window(route_env):
    """The server commits a rotation before the phone stores it. Re-presenting
    the previous generation moments later returns the CURRENT generation
    without bumping it — a lost response must not sign the employee out."""
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    retried = await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert auth.decode_token(retried.refresh_token, expected_type="refresh").gen == 1
    assert conn.generation == 1 and not conn.revoked
    assert not any("DELETE FROM device_tokens" in q for q, _ in conn.executed)


@pytest.mark.asyncio
async def test_expired_mobile_session_revokes_the_device_on_refresh(route_env, monkeypatch):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    monkeypatch.setattr(login_routes, "refresh_session_expired", lambda *_a: True)
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert error.value.status_code == 401
    assert error.value.detail == "Session expired. Please log in again."
    assert conn.revoked
    deletes = [a for q, a in conn.executed if "DELETE FROM device_tokens WHERE device_session_id" in q]
    assert deletes == [(conn.sid, conn.user_id)]


@pytest.mark.asyncio
async def test_suspended_employee_refresh_ends_the_device(route_env):
    conn = route_env
    result = await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    conn.suspended = True
    with pytest.raises(HTTPException):
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert conn.revoked


@pytest.mark.asyncio
async def test_mobile_logout_still_revokes_after_the_session_expired(route_env):
    """Past the 12-hour absolute limit the refresh token is expired. Sign-out
    must still end the device, or the phone keeps the previous user's pushes."""
    conn = route_env
    await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    from jose import jwt as jose_jwt

    expired = jose_jwt.encode(
        {"sub": str(conn.user_id), "email": "employee@example.com", "role": "employee",
         "type": "refresh", "exp": 1, "iat": 0, "sid": str(conn.sid), "cl": "ios_schedule",
         "gen": 0},
        "test-secret", algorithm="HS256",
    )
    assert auth.decode_token(expired, expected_type="refresh") is None
    await login_routes.mobile_logout(MobileLogoutRequest(refresh_token=expired, push_token="e" * 64))
    assert conn.revoked
    forged = jose_jwt.encode({"sub": str(conn.user_id), "type": "refresh", "exp": 1},
                             "wrong-secret", algorithm="HS256")
    with pytest.raises(HTTPException) as error:
        await login_routes.mobile_logout(MobileLogoutRequest(refresh_token=forged))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_revoking_user_sessions_ends_every_mobile_device(route_env):
    """Password change/reset and web logout-all go through revoke_user_sessions;
    the push send only checks the device session, so it must be revoked too."""
    conn = route_env
    await login_routes.login(
        LoginRequest(email="employee@example.com", password="password", client="ios_schedule"),
        _request(),
    )
    await dependencies.revoke_user_sessions(conn, conn.user_id)
    assert conn.revoked
    deletes = [(q, a) for q, a in conn.executed if "DELETE FROM device_tokens" in q]
    assert "device_session_id IS NOT NULL" in deletes[-1][0]
    assert deletes[-1][1] == ([conn.user_id],)


@pytest.mark.asyncio
async def test_revoke_mobile_devices_with_no_users_is_a_no_op(route_env):
    await dependencies.revoke_mobile_devices(route_env, [])
    assert route_env.executed == []


# ── business admins on Matcha Schedule ───────────────────────────────────────


def _manager_login(**kwargs):
    return LoginRequest(email="owner@example.com", password="password", client="ios_schedule",
                        device_name="iPhone", **kwargs)


@pytest.mark.asyncio
async def test_business_admin_signs_in_from_a_build_that_can_manage(route_env):
    conn = route_env
    conn.role = "client"
    result = await login_routes.login(_manager_login(capabilities=["manage"]), _request())
    payload = auth.decode_token(result.refresh_token, expected_type="refresh")
    assert payload.sid == str(conn.sid) and payload.cl == "ios_schedule" and payload.role == "client"
    access = HTTPAuthorizationCredentials(scheme="Bearer", credentials=result.access_token)
    assert (await dependencies.get_token_payload(access)).role == "client"
    # Never through a plain decode: WebSockets and telemetry can't check revocation.
    assert auth.decode_token(result.access_token, expected_type="access") is None

    rotated = await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert auth.decode_token(rotated.refresh_token, expected_type="refresh").sid == payload.sid
    assert conn.device_updates == 1

    await login_routes.mobile_logout(MobileLogoutRequest(refresh_token=rotated.refresh_token))
    assert conn.revoked


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "capabilities", "company_ok", "detail"), [
    ("client", [], True, "Update Matcha Schedule"),
    ("client", ["manage"], False, "approved business account"),
    ("admin", ["manage"], True, "employees and business admins"),
    ("individual", ["manage"], True, "employees and business admins"),
    ("candidate", ["manage"], True, "employees and business admins"),
])
async def test_other_accounts_cannot_start_a_phone_session(route_env, role, capabilities, company_ok, detail):
    conn = route_env
    conn.role = role
    conn.client_company_ok = company_ok
    with pytest.raises(HTTPException) as error:
        await login_routes.login(_manager_login(capabilities=capabilities), _request())
    assert error.value.status_code == 403
    assert detail in error.value.detail
    assert conn.sid is None


@pytest.mark.asyncio
async def test_a_business_admin_whose_company_is_no_longer_accessible_cannot_refresh(route_env):
    conn = route_env
    conn.role = "client"
    result = await login_routes.login(_manager_login(capabilities=["manage"]), _request())
    conn.client_company_ok = False
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_a_phone_session_whose_user_became_an_admin_is_ended(route_env):
    conn = route_env
    conn.role = "client"
    result = await login_routes.login(_manager_login(capabilities=["manage"]), _request())
    conn.role = "admin"
    with pytest.raises(HTTPException) as error:
        await login_routes.refresh_token(RefreshTokenRequest(refresh_token=result.refresh_token))
    assert error.value.status_code == 401
    assert conn.revoked


def test_eligibility_sql_covers_both_roles():
    sql = login_routes._MOBILE_ELIGIBLE_SQL
    assert "u.role = 'employee'" in sql and "employment_status" in sql and "$3::text[]" in sql
    assert "u.role = 'client'" in sql and "NOT IN ('pending', 'rejected')" in sql
    assert "is_personal" in sql


@pytest.mark.parametrize(("role", "ok"), [("employee", True), ("client", True), ("admin", False), ("individual", False)])
def test_mobile_session_roles(role, ok, monkeypatch):
    for module in (auth, session_tokens):
        monkeypatch.setattr(module, "get_settings", _settings)
    sid = uuid4()
    token = auth.create_access_token(uuid4(), "x@example.com", role,
                                     extra_claims={"sid": str(sid), "cl": "ios_schedule"})
    decoded = auth.decode_token(token, expected_type="access", allow_mobile_access=True)
    assert (decoded is not None) is ok
    refresh = auth.create_refresh_token(uuid4(), "x@example.com", role,
                                        extra_claims={"sid": str(sid), "cl": "ios_schedule", "gen": 0})
    payload = auth.decode_token(refresh, expected_type="refresh")
    if ok:
        assert login_routes._mobile_session_id(payload) == sid
    else:
        with pytest.raises(HTTPException):
            login_routes._mobile_session_id(payload)
