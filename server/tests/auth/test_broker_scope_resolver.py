import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.models.auth import CurrentUser
from app.matcha import dependencies as matcha_dependencies


class _FakeConn:
    def __init__(self, *, terms_accepted: bool, link_rows: list[dict] | None = None):
        self.terms_accepted = terms_accepted
        self.link_rows = link_rows or []
        self.broker_id = uuid4()

    async def fetchrow(self, query, *args):
        if "FROM broker_members bm" in query and "JOIN brokers b" in query:
            return {
                "broker_id": self.broker_id,
                "member_role": "owner",
                "member_active": True,
                "broker_status": "active",
                "terms_required_version": "v1",
            }
        return None

    async def fetchval(self, query, *args):
        if "FROM broker_terms_acceptances" in query:
            return self.terms_accepted
        return None

    async def fetch(self, query, *args):
        if "FROM broker_company_links l" in query:
            return self.link_rows
        return []


class _FakeConnContext:
    def __init__(self, conn: _FakeConn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _set_fake_connection(monkeypatch, conn: _FakeConn):
    monkeypatch.setattr(matcha_dependencies, "get_connection", lambda: _FakeConnContext(conn))


def test_broker_scope_requires_terms_acceptance(monkeypatch):
    conn = _FakeConn(terms_accepted=False)
    _set_fake_connection(monkeypatch, conn)

    user = CurrentUser(id=uuid4(), email="broker@example.com", role="broker")

    with pytest.raises(HTTPException, match="terms must be accepted"):
        asyncio.run(matcha_dependencies.resolve_accessible_company_scope(user))


def test_broker_scope_returns_first_accessible_company(monkeypatch):
    company_id = uuid4()
    conn = _FakeConn(
        terms_accepted=True,
        link_rows=[
            {
                "company_id": company_id,
                "permissions": {"allowed_features": ["compliance", "policies"]},
                "company_status": "approved",
                "rejection_reason": None,
            }
        ],
    )
    _set_fake_connection(monkeypatch, conn)

    user = CurrentUser(id=uuid4(), email="broker@example.com", role="broker")
    scope = asyncio.run(matcha_dependencies.resolve_accessible_company_scope(user))

    assert scope["actor_role"] == "broker"
    assert scope["broker_id"] == conn.broker_id
    assert scope["company_id"] == company_id
    assert scope["company_ids"] == [company_id]
    assert scope["link_permissions"] == {"allowed_features": ["compliance", "policies"]}
