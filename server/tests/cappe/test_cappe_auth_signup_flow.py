"""Behaviour of Cappe signup / verify / login around email confirmation.

No database: the routes are called directly against a fake connection, with
the rate limiter, bcrypt and the email senders stubbed.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_auth_signup_flow.py -q
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import asyncpg  # noqa: E402
import pytest  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.models.auth import CappeLogin, CappeSignup, CappeVerifyRequest  # noqa: E402
from app.cappe.routes import auth  # noqa: E402


class _Conn:
    """Answers the three statements signup issues, and records writes."""

    def __init__(self, *, existing=None, duplicate=False):
        self.existing = existing
        self.duplicate = duplicate
        self.inserted = None
        self.executed = []
        self.selects = []

    async def fetchrow(self, sql, *args):
        if "INSERT INTO cappe_accounts" in sql:
            if self.duplicate:
                raise asyncpg.UniqueViolationError("duplicate")
            self.inserted = args
            return {
                "id": uuid.uuid4(), "email": args[0], "name": args[2],
                "plan": "free", "status": "active", "account_type": args[3],
            }
        self.selects.append((sql, args))
        return self.existing

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


class _ConnCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Settings:
    """The real settings with `is_production` overridden."""

    def __init__(self, real, is_production):
        self._real = real
        self.is_production = is_production

    def __getattr__(self, name):
        return getattr(self._real, name)


@pytest.fixture
def wired(monkeypatch):
    """Stub everything signup reaches outside the fake connection."""
    state = {"send_ok": True}

    async def _no_limit(*_args, **_kwargs):
        return None

    async def _send_ok(_email):
        return state["send_ok"]

    monkeypatch.setattr(auth, "check_rate_limit", _no_limit)
    monkeypatch.setattr(auth, "client_ip", lambda _request: "203.0.113.7")
    monkeypatch.setattr(auth, "hash_password", lambda _pw: "hashed")
    monkeypatch.setattr(auth, "check_recipient_send_ok", _send_ok)

    def use(conn, *, is_production=False):
        real = auth.get_settings()
        monkeypatch.setattr(auth, "get_connection", lambda: _ConnCtx(conn))
        monkeypatch.setattr(auth, "get_settings", lambda: _Settings(real, is_production))

    state["use"] = use
    return state


def _body(email):
    return CappeSignup.model_construct(
        email=email, password="correct horse", name="Typed Name", account_type="business"
    )


def _sent(background):
    return [(t.func.__name__, t.args) for t in background.tasks]


async def _signup(email):
    background = BackgroundTasks()
    res = await auth.signup(_body(email), request=None, background=background)
    return res, background


@pytest.fixture
def deliverable(monkeypatch):
    """Treat the test address as deliverable (it is a reserved domain on disk,
    per the repo's test-data rule, but the routes must see a real one)."""
    monkeypatch.setattr(auth, "_is_reserved_test_domain", lambda _email: False)


@pytest.mark.asyncio
async def test_fresh_signup_sends_a_confirmation_link_and_no_tokens(wired, deliverable):
    conn = _Conn()
    wired["use"](conn)
    res, background = await _signup("owner@example.com")

    assert res.verification_required is True and res.access_token is None
    [(name, args)] = _sent(background)
    assert name == "send_cappe_verification_email"
    assert args[0] == "owner@example.com" and args[2] == str(conn.inserted[5])


@pytest.mark.asyncio
async def test_duplicate_of_a_confirmed_account_writes_nothing(wired, deliverable):
    existing = {
        "id": uuid.uuid4(), "email": "owner@example.com", "name": "On File",
        "email_verified_at": datetime.now(timezone.utc),
    }
    conn = _Conn(existing=existing, duplicate=True)
    wired["use"](conn)
    res, background = await _signup("Owner@Example.com")

    assert res.model_dump() == {
        "verification_required": True, "email": "owner@example.com",
        "access_token": None, "refresh_token": None, "expires_in": None, "account": None,
    }
    assert conn.executed == []
    # Greeted with the name on file, never the one typed into the form.
    assert _sent(background) == [("send_cappe_account_exists_email", ("owner@example.com", "On File"))]
    assert "lower(email)" in conn.selects[0][0]


@pytest.mark.asyncio
async def test_duplicate_of_an_unconfirmed_account_gets_a_fresh_link(wired, deliverable):
    account_id = uuid.uuid4()
    existing = {"id": account_id, "email": "owner@example.com", "name": "On File", "email_verified_at": None}
    conn = _Conn(existing=existing, duplicate=True)
    wired["use"](conn)
    res, background = await _signup("owner@example.com")

    # Same answer as every other signup: no oracle.
    assert res.verification_required is True and res.access_token is None
    [(sql, args)] = conn.executed
    assert "verification_token = $1" in sql and args[1] == account_id
    # The password on file is not replaced by an unproven caller.
    assert "password_hash" not in sql
    [(name, sent_args)] = _sent(background)
    assert name == "send_cappe_verification_email"
    assert sent_args == ("owner@example.com", "On File", str(args[0]))


@pytest.mark.asyncio
async def test_a_throttled_duplicate_neither_writes_nor_sends(wired, deliverable):
    existing = {"id": uuid.uuid4(), "email": "owner@example.com", "name": None, "email_verified_at": None}
    conn = _Conn(existing=existing, duplicate=True)
    wired["use"](conn)
    wired["send_ok"] = False
    res, background = await _signup("owner@example.com")

    assert res.verification_required is True
    assert conn.executed == [] and conn.selects == [] and _sent(background) == []


@pytest.mark.asyncio
async def test_reserved_domain_auto_verifies_outside_production(wired):
    conn = _Conn()
    wired["use"](conn, is_production=False)
    res, background = await _signup("seed@example.com")

    assert res.verification_required is False and res.access_token
    assert conn.inserted[4] is True and conn.inserted[5] is None
    assert _sent(background) == []


@pytest.mark.asyncio
async def test_reserved_domain_is_not_auto_verified_in_production(wired):
    conn = _Conn()
    wired["use"](conn, is_production=True)
    res, _background = await _signup("seed@example.com")

    assert res.verification_required is True and res.access_token is None
    assert conn.inserted[4] is False and conn.inserted[5] is not None


# ── verify + login error codes ───────────────────────────────────────────────

class _VerifyConn(_Conn):
    def __init__(self, row):
        super().__init__()
        self.row = row

    async def fetchrow(self, sql, *args):
        return self.row


def _account_row(**over):
    row = {
        "id": uuid.uuid4(), "email": "owner@example.com", "name": None, "plan": "free",
        "status": "active", "account_type": "business",
        "verification_sent_at": datetime.now(timezone.utc),
    }
    row.update(over)
    return row


async def _verify(token):
    return await auth.verify_email(CappeVerifyRequest(token=token), request=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("token,row", [("not-a-uuid", None), (str(uuid.uuid4()), None)])
async def test_verify_rejects_a_bad_or_used_link_with_a_code(wired, token, row):
    wired["use"](_VerifyConn(row))
    with pytest.raises(HTTPException) as exc:
        await _verify(token)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "verification_invalid"


@pytest.mark.asyncio
async def test_verify_reports_an_expired_link_as_410_with_a_code(wired):
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    wired["use"](_VerifyConn(_account_row(verification_sent_at=old)))
    with pytest.raises(HTTPException) as exc:
        await _verify(str(uuid.uuid4()))
    assert exc.value.status_code == 410
    assert exc.value.detail["code"] == "verification_expired"


@pytest.mark.asyncio
async def test_verify_signs_the_account_in_and_clears_the_token(wired):
    conn = _VerifyConn(_account_row())
    wired["use"](conn)
    res = await _verify(str(uuid.uuid4()))
    assert res.access_token and res.account.email == "owner@example.com"
    assert "verification_token = NULL" in conn.executed[0][0]


@pytest.mark.asyncio
async def test_login_of_an_unconfirmed_account_carries_a_stable_code(wired, monkeypatch):
    async def _password_ok(_pw, _hash):
        return True

    monkeypatch.setattr(auth, "verify_password_async", _password_ok)
    wired["use"](_VerifyConn(_account_row(password_hash="hashed", email_verified_at=None)))
    with pytest.raises(HTTPException) as exc:
        await auth.login(CappeLogin(email="owner@example.com", password="correct horse"), request=None)
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "email_unverified"
    # The iOS client still matches on this phrase.
    assert "confirm your email" in exc.value.detail["message"]
