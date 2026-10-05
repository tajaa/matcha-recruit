"""Cappe password reset: request a link, then set a new password with it.

No database: the routes run against a fake connection.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_password_reset.py -q
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from fastapi import BackgroundTasks, HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.models.auth import CappeForgotPasswordRequest, CappeResetPasswordRequest  # noqa: E402
from app.cappe.routes import auth  # noqa: E402
from app.cappe.services import email as email_mod  # noqa: E402
from app.cappe.services.auth import hash_reset_token, make_reset_token  # noqa: E402


class _Conn:
    def __init__(self, *, row=None, updated=True):
        self.row = row
        self.updated = updated
        self.selects = []
        self.executed = []
        self.updates = []

    async def fetchrow(self, sql, *args):
        self.selects.append((sql, args))
        return self.row

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchval(self, sql, *args):
        self.updates.append((sql, args))
        return self.row["id"] if self.updated else None


class _ConnCtx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


@pytest.fixture
def wired(monkeypatch):
    state = {"send_ok": True, "reserved": False}

    async def _no_limit(*_args, **_kwargs):
        return None

    async def _send_ok(_email):
        return state["send_ok"]

    monkeypatch.setattr(auth, "check_rate_limit", _no_limit)
    monkeypatch.setattr(auth, "client_ip", lambda _request: "203.0.113.7")
    monkeypatch.setattr(auth, "hash_password", lambda pw: f"hashed:{pw}")
    monkeypatch.setattr(auth, "check_recipient_send_ok", _send_ok)
    # Test addresses are reserved domains on disk; the route must see a real one.
    monkeypatch.setattr(auth, "_is_reserved_test_domain", lambda _email: state["reserved"])

    def use(conn):
        monkeypatch.setattr(auth, "get_connection", lambda: _ConnCtx(conn))
        return conn

    state["use"] = use
    return state


async def _forgot(email="Owner@Example.com"):
    background = BackgroundTasks()
    res = await auth.forgot_password(
        CappeForgotPasswordRequest(email=email), request=None, background=background
    )
    return res, [(t.func.__name__, t.args) for t in background.tasks]


def _active(**over):
    row = {"id": uuid.uuid4(), "email": "owner@example.com", "name": "Pat", "status": "active"}
    row.update(over)
    return row


# ── requesting a link ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_forgot_password_stores_a_hash_and_emails_the_token(wired):
    conn = wired["use"](_Conn(row=_active()))
    res, sent = await _forgot()

    assert res == {"status": "ok"}
    assert "lower(email)" in conn.selects[0][0] and conn.selects[0][1] == ("owner@example.com",)
    [(sql, args)] = conn.executed
    [(name, (to, to_name, token))] = sent
    assert name == "send_cappe_password_reset_email" and (to, to_name) == ("owner@example.com", "Pat")
    # Only the hash is stored; the emailed token is what hashes to it.
    assert "password_reset_token_hash = $1" in sql
    assert args[0] == hash_reset_token(token) and args[0] != token


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [None, _active(status="suspended")])
async def test_forgot_password_answers_the_same_for_an_unknown_or_inactive_account(wired, row):
    conn = wired["use"](_Conn(row=row))
    res, sent = await _forgot()
    assert res == {"status": "ok"}
    assert conn.executed == [] and sent == []


@pytest.mark.asyncio
async def test_a_throttled_recipient_keeps_the_link_already_sent(wired):
    conn = wired["use"](_Conn(row=_active()))
    wired["send_ok"] = False
    res, sent = await _forgot()
    assert res == {"status": "ok"}
    assert conn.selects == [] and conn.executed == [] and sent == []


@pytest.mark.asyncio
async def test_forgot_password_skips_undeliverable_test_domains(wired):
    conn = wired["use"](_Conn(row=_active()))
    wired["reserved"] = True
    _res, sent = await _forgot()
    assert conn.executed == [] and sent == []


# ── using a link ─────────────────────────────────────────────────────────────

async def _reset(token="tok", password="new password"):
    return await auth.reset_password(
        CappeResetPasswordRequest(token=token, password=password), request=None
    )


def _pending(minutes_ago=5):
    return {
        "id": uuid.uuid4(),
        "password_reset_sent_at": datetime.now(timezone.utc) - timedelta(minutes=minutes_ago),
    }


@pytest.mark.asyncio
async def test_reset_sets_the_password_revokes_sessions_and_confirms_the_email(wired):
    row = _pending()
    conn = wired["use"](_Conn(row=row))
    assert await _reset(token="tok") is None

    assert conn.selects[0][1] == (hash_reset_token("tok"),)
    assert "status = 'active'" in conn.selects[0][0]
    [(sql, args)] = conn.updates
    assert args == ("hashed:new password", row["id"], hash_reset_token("tok"))
    for clause in (
        "password_reset_token_hash = NULL",          # single use
        "tokens_valid_after = NOW()",                # every existing session dies
        "email_verified_at = COALESCE(email_verified_at, NOW())",
        "verification_token = NULL",
        "AND password_reset_token_hash = $3",        # two racing requests can't both win
    ):
        assert clause in sql


@pytest.mark.asyncio
async def test_reset_rejects_an_unknown_or_used_token(wired):
    conn = wired["use"](_Conn(row=None))
    with pytest.raises(HTTPException) as exc:
        await _reset()
    assert exc.value.status_code == 400 and exc.value.detail["code"] == "reset_invalid"
    assert conn.updates == []


@pytest.mark.asyncio
async def test_reset_rejects_an_expired_token_without_touching_the_password(wired):
    conn = wired["use"](_Conn(row=_pending(minutes_ago=61)))
    with pytest.raises(HTTPException) as exc:
        await _reset()
    assert exc.value.status_code == 410 and exc.value.detail["code"] == "reset_expired"
    assert conn.updates == []


@pytest.mark.asyncio
async def test_reset_reports_invalid_when_another_request_used_the_link_first(wired):
    wired["use"](_Conn(row=_pending(), updated=False))
    with pytest.raises(HTTPException) as exc:
        await _reset()
    assert exc.value.status_code == 400 and exc.value.detail["code"] == "reset_invalid"


def test_reset_enforces_the_signup_password_rule():
    with pytest.raises(ValidationError):
        CappeResetPasswordRequest(token="tok", password="short")


def test_reset_tokens_are_unguessable_and_hashed_deterministically():
    a, b = make_reset_token(), make_reset_token()
    assert a != b and len(a) >= 40
    assert hash_reset_token(a) == hash_reset_token(a) and len(hash_reset_token(a)) == 64


# ── the emails ───────────────────────────────────────────────────────────────

class _Svc:
    def __init__(self):
        self.calls = []

    async def send_email_with_fallback(self, **kw):
        self.calls.append(kw)
        return True


def test_reset_email_keeps_the_token_in_the_url_fragment(monkeypatch):
    svc = _Svc()
    monkeypatch.setattr(email_mod, "get_email_service", lambda: svc)
    monkeypatch.setenv("CAPPE_BASE_DOMAIN", "gummfit.com")
    asyncio.run(email_mod.send_cappe_password_reset_email("owner@example.com", "Pat <b>", "tok-1"))

    [call] = svc.calls
    link = "https://gummfit.com/cappe/reset-password#token=tok-1"
    assert link in call["html_content"] and link in call["text_content"]
    assert "?token=" not in call["html_content"]
    assert call["from_name"] == "Gummfit"
    assert "Pat &lt;b&gt;" in call["html_content"]  # the stored name is escaped


def test_account_exists_email_points_at_password_reset(monkeypatch):
    svc = _Svc()
    monkeypatch.setattr(email_mod, "get_email_service", lambda: svc)
    monkeypatch.setenv("CAPPE_BASE_DOMAIN", "gummfit.com")
    asyncio.run(email_mod.send_cappe_account_exists_email("owner@example.com", None))

    [call] = svc.calls
    assert "https://gummfit.com/cappe/forgot-password" in call["html_content"]
    assert "https://gummfit.com/cappe/forgot-password" in call["text_content"]
