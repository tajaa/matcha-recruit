"""Fake-conn tests for the self-serve brand claim endpoint
(server/app/tellus/routes/community.py:claim_brand). No DB, no HTTP — same
_FakeConn/monkeypatch pattern as test_places_google.py's ensure_community_link
tests.

claim_brand files a PENDING row in tellus_brand_claims and does NOT touch
owner_account_id/account_type — that only happens on admin approval
(routes/admin/claims.py:approve_claim), covered separately. These tests pin
the pending-only behavior.
"""
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.tellus.models.tellus import TellusAccount
from app.tellus.routes import community as community_module


class _NullTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeConn:
    def __init__(self, *, brand_owner_account_id=None, brand_missing=False, caller_already_owns=False):
        self.calls: list[tuple] = []
        self._brand_id = uuid4()
        self._claim_id = uuid4()
        self._brand_owner_account_id = brand_owner_account_id
        self._brand_missing = brand_missing
        self._caller_already_owns = caller_already_owns

    def transaction(self):
        return _NullTxn()

    async def fetchrow(self, query, *args):
        self.calls.append(("fetchrow", query, args))
        if "SELECT id, owner_account_id FROM tellus_brands WHERE slug" in query:
            if self._brand_missing:
                return None
            return {"id": self._brand_id, "owner_account_id": self._brand_owner_account_id}
        raise AssertionError(f"unexpected fetchrow: {query}")

    async def fetchval(self, query, *args):
        self.calls.append(("fetchval", query, args))
        if "SELECT 1 FROM tellus_brands WHERE owner_account_id" in query:
            return 1 if self._caller_already_owns else None
        if "INSERT INTO tellus_brand_claims" in query:
            return self._claim_id
        raise AssertionError(f"unexpected fetchval: {query}")

    async def execute(self, query, *args):
        self.calls.append(("execute", query, args))
        return "UPDATE 1"

    def _calls_matching(self, needle: str):
        return [c for c in self.calls if needle in c[1]]


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc_info):
        return False


class _FakeRequest:
    headers: dict = {}
    client = None


def _account(**overrides):
    base = dict(id=uuid4(), email="owner@example.com", account_type="consumer")
    base.update(overrides)
    return TellusAccount(**base)


async def _noop_rate_limit(*args, **kwargs):
    return None


@pytest.fixture(autouse=True)
def _patch_rate_limit(monkeypatch):
    monkeypatch.setattr(community_module, "check_rate_limit", _noop_rate_limit)


class TestClaimBrand:
    @pytest.mark.asyncio
    async def test_consumer_claims_unclaimed_brand(self, monkeypatch):
        conn = _FakeConn(brand_owner_account_id=None)
        monkeypatch.setattr(community_module, "get_connection", lambda: _FakeConnCtx(conn))
        account = _account(account_type="consumer")

        result = await community_module.claim_brand("acme", _FakeRequest(), account)

        assert result.claim_id == conn._claim_id
        assert result.status == "pending"
        assert result.slug == "acme"
        insert_calls = conn._calls_matching("INSERT INTO tellus_brand_claims")
        assert len(insert_calls) == 1
        assert insert_calls[0][2] == (conn._brand_id, account.id, "unknown")
        # Ownership/account_type never flip here — only on admin approval.
        assert conn._calls_matching("UPDATE tellus_accounts SET account_type = 'brand'") == []
        assert conn._calls_matching("UPDATE tellus_brands SET owner_account_id") == []

    @pytest.mark.asyncio
    async def test_already_claimed_brand_is_409(self, monkeypatch):
        conn = _FakeConn(brand_owner_account_id=uuid4())
        monkeypatch.setattr(community_module, "get_connection", lambda: _FakeConnCtx(conn))
        account = _account()

        with pytest.raises(HTTPException) as exc:
            await community_module.claim_brand("acme", _FakeRequest(), account)
        assert exc.value.status_code == 409
        assert "already been claimed" in exc.value.detail

    @pytest.mark.asyncio
    async def test_caller_already_owns_a_brand_is_409(self, monkeypatch):
        conn = _FakeConn(brand_owner_account_id=None, caller_already_owns=True)
        monkeypatch.setattr(community_module, "get_connection", lambda: _FakeConnCtx(conn))
        account = _account(account_type="brand")

        with pytest.raises(HTTPException) as exc:
            await community_module.claim_brand("acme", _FakeRequest(), account)
        assert exc.value.status_code == 409
        assert "one brand per account" in exc.value.detail
        # Never reaches the mutation calls once the ownership check fails.
        assert conn._calls_matching("UPDATE tellus_brands SET owner_account_id") == []
