import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services import shopper_auth  # noqa: E402
from app.cappe.services.auth import create_cappe_access_token, decode_cappe_token  # noqa: E402


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _CodeConn:
    def __init__(self, code_row):
        self.code_row = code_row
        self.executed = []
        self.fetches = []

    def transaction(self):
        return _Transaction()

    async def execute(self, query, *args):
        self.executed.append((query, args))

    async def fetchrow(self, query, *args):
        self.fetches.append((query, args))
        if "FROM cappe_shopper_login_codes" in query:
            return self.code_row
        if "INSERT INTO cappe_shoppers" in query:
            return {
                "id": uuid4(), "site_id": args[0], "email": args[1], "name": None,
                "phone": None, "push_order_updates": True,
            }
        raise AssertionError(query)


def _row(site_id, email, code, *, attempts=0, valid=True, consumed_at=None):
    return {
        "id": uuid4(),
        "code_hash": shopper_auth.code_hash(site_id, email, code),
        "attempts": attempts,
        "valid": valid,
        "consumed_at": consumed_at,
    }


@pytest.mark.asyncio
async def test_login_code_claims_only_same_site_and_normalized_email(monkeypatch):
    site_id, email, code = uuid4(), "buyer@example.com", "123456"
    conn = _CodeConn(_row(site_id, email, code))

    async def fake_session(_conn, shopper, **_kwargs):
        return {"shopper_id": str(shopper["id"])}

    monkeypatch.setattr(shopper_auth, "issue_session", fake_session)
    result = await shopper_auth.verify_login_code(
        conn, site={"id": site_id}, email=" Buyer@Example.com ", code=code
    )
    assert result["shopper_id"]
    claim = next(entry for entry in conn.executed if "UPDATE cappe_orders SET shopper_id" in entry[0])
    assert claim[1][1:] == (site_id, email)


@pytest.mark.asyncio
@pytest.mark.parametrize("attempts,valid,consumed", [(5, True, None), (0, False, None), (0, True, datetime.now(timezone.utc))])
async def test_locked_expired_or_consumed_code_cannot_be_reused(attempts, valid, consumed):
    site_id, email, code = uuid4(), "buyer@example.com", "123456"
    conn = _CodeConn(_row(site_id, email, code, attempts=attempts, valid=valid, consumed_at=consumed))
    assert await shopper_auth.verify_login_code(conn, site={"id": site_id}, email=email, code=code) is None
    assert not any("INSERT INTO cappe_shoppers" in query for query, _args in conn.fetches)


@pytest.mark.asyncio
async def test_wrong_code_increments_attempt_inside_successful_transaction():
    site_id, email = uuid4(), "buyer@example.com"
    conn = _CodeConn(_row(site_id, email, "123456"))
    assert await shopper_auth.verify_login_code(conn, site={"id": site_id}, email=email, code="654321") is None
    assert any("attempts=attempts+1" in query for query, _args in conn.executed)


def test_owner_and_shopper_token_scopes_are_mutually_rejected():
    shopper_id, site_id = uuid4(), uuid4()
    helpers = shopper_auth.token_helpers()
    shopper_token = helpers.create_access_token(
        shopper_id,
        "buyer@example.com",
        extra_claims={"site_id": str(site_id), "sid": str(uuid4()), "nonce": "n"},
    )
    owner_token = create_cappe_access_token(uuid4(), "owner@example.com")
    assert decode_cappe_token(shopper_token, "access") is None
    assert helpers.decode_token(owner_token, "access") is None
    assert helpers.decode_token(shopper_token, "access")["site_id"] == str(site_id)


@pytest.mark.asyncio
async def test_issue_code_invalidates_old_code_and_stores_only_hash(monkeypatch):
    site_id, email = uuid4(), "buyer@example.com"
    conn = _CodeConn(None)
    monkeypatch.setattr(shopper_auth.secrets, "randbelow", lambda _limit: 42)
    code = await shopper_auth.issue_login_code(conn, site={"id": site_id}, email=f" {email.upper()} ")
    assert code == "000042"
    assert any("consumed_at=NOW()" in query for query, _ in conn.executed)
    inserted = next(args for query, args in conn.executed if "INSERT INTO cappe_shopper_login_codes" in query)
    assert inserted[1] == email
    assert inserted[2] == shopper_auth.code_hash(site_id, email, code)
    assert code not in inserted


class _SessionConn:
    def __init__(self, shopper, refresh_hash=None):
        self.shopper = shopper
        self.refresh_hash = refresh_hash
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((query, args))

    async def fetchrow(self, query, *args):
        if "FROM cappe_shoppers" in query:
            return self.shopper
        if "FROM cappe_shopper_sessions" in query:
            return {"refresh_hash": self.refresh_hash}
        raise AssertionError(query)


@pytest.mark.asyncio
async def test_session_issue_and_rotating_refresh_resolution():
    shopper = {
        "id": uuid4(), "site_id": uuid4(), "email": "buyer@example.com",
        "name": None, "phone": None, "push_order_updates": True, "tokens_valid_after": None,
    }
    conn = _SessionConn(shopper)
    pair = await shopper_auth.issue_session(conn, shopper)
    assert pair["shopper"]["site_id"] == str(shopper["site_id"])
    insert = next(args for query, args in conn.executed if "cappe_shopper_sessions" in query)
    conn.refresh_hash = insert[2]
    site = {"id": shopper["site_id"]}
    resolved, payload = await shopper_auth.resolve_shopper(
        conn, site, pair["refresh_token"], "refresh", lock=True,
    )
    assert resolved == shopper
    assert payload["site_id"] == str(site["id"])

    with pytest.raises(HTTPException) as caught:
        await shopper_auth.resolve_shopper(conn, {"id": uuid4()}, pair["access_token"])
    assert caught.value.status_code == 401
