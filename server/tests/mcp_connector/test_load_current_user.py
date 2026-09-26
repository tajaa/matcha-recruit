"""`load_current_user` — the gate shared by app JWTs and connector tokens."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

import app.core.dependencies as deps
from tests._helpers.routes import QueryConn

USER_ID = uuid.UUID("dddddddd-4444-4444-8444-444444444444")


def _row(**over):
    row = {
        "id": USER_ID, "email": "u@example.com", "role": "client", "is_active": True,
        "is_suspended": False, "beta_features": {}, "interview_prep_tokens": 0,
        "allowed_interview_roles": [], "company_deleted_at": None,
    }
    row.update(over)
    return row


@pytest.fixture
def conn(monkeypatch):
    c = QueryConn(
        fetchrow={"FROM users u": _row()},
        fetchval={
            "information_schema.columns": True,
            "SELECT tokens_valid_after": datetime.now(timezone.utc),
        },
    )
    monkeypatch.setattr(deps, "get_connection", lambda *a, **k: c)
    monkeypatch.setattr(deps, "_users_has_valid_after", None)
    return c


@pytest.mark.asyncio
async def test_connector_tokens_skip_the_browser_session_watermark(conn):
    old_iat = int((datetime.now(timezone.utc) - timedelta(days=1)).timestamp())
    with pytest.raises(HTTPException) as err:
        await deps.load_current_user(USER_ID, token_iat=old_iat)
    assert err.value.status_code == 401  # an app JWT from before the logout is dead

    user = await deps.load_current_user(USER_ID, check_session_revocation=False)
    assert user.id == USER_ID and user.role == "client"


@pytest.mark.asyncio
@pytest.mark.parametrize("over, status", [
    ({"is_active": False}, 401),
    ({"is_suspended": True}, 403),
    ({"company_deleted_at": datetime.now(timezone.utc)}, 403),
])
async def test_account_state_still_gates_connector_callers(conn, over, status):
    conn.set("fetchrow", "FROM users u", _row(**over))
    with pytest.raises(HTTPException) as err:
        await deps.load_current_user(USER_ID, check_session_revocation=False)
    assert err.value.status_code == status


@pytest.mark.asyncio
async def test_get_current_user_still_applies_the_jwt_watermark(conn, monkeypatch):
    from types import SimpleNamespace

    stamp = int(datetime.now(timezone.utc).timestamp())
    payload = SimpleNamespace(sub=str(USER_ID), iat=stamp - 86400, iat_ms=None)

    async def token_payload(credentials):
        return payload

    monkeypatch.setattr(deps, "get_token_payload", token_payload)
    with pytest.raises(HTTPException) as err:
        await deps.get_current_user(credentials=None)
    assert err.value.status_code == 401

    payload.iat = stamp + 60  # minted after the watermark
    conn.set("fetchval", "SELECT tokens_valid_after", datetime.now(timezone.utc) - timedelta(minutes=5))
    user = await deps.get_current_user(credentials=None)
    assert user.id == USER_ID
