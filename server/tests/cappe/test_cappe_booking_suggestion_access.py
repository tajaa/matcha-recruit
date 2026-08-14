"""Unit coverage for Cappe booking suggestion capabilities."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services import booking_suggestion_access as access  # noqa: E402


SITE_ID = uuid4()
NOW = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)


class _Conn:
    def __init__(self, client=None, link=None):
        self.client = client
        self.link = link
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def fetchrow(self, query, *args):
        if "FROM cappe_clients" in query:
            return self.client
        if "FROM cappe_booking_suggestion_links" in query:
            return self.link
        raise AssertionError(query)

    async def fetchval(self, *_args):
        return None

    async def execute(self, *args):
        self.executed.append(args)


@pytest.mark.asyncio
async def test_unknown_email_does_not_issue_link(monkeypatch):
    conn = _Conn()
    token = await access.issue_suggestion_link(
        conn, site_id=SITE_ID, email="unknown@example.com", now=NOW
    )
    assert token is None
    assert conn.executed == []


@pytest.mark.asyncio
async def test_existing_client_link_stores_hash_only(monkeypatch):
    conn = _Conn(client={"name": "Maria"})
    monkeypatch.setattr(access, "make_access_token", lambda: "raw-secret-token")
    token, name = await access.issue_suggestion_link(
        conn, site_id=SITE_ID, email="Maria@Example.com", now=NOW
    )
    assert token == "raw-secret-token"
    assert name == "Maria"
    assert "raw-secret-token" not in repr(conn.executed)
    assert access.hash_access_token(token) in repr(conn.executed)


@pytest.mark.asyncio
async def test_redeem_consumes_link_and_creates_hashed_session(monkeypatch):
    conn = _Conn(link={"id": uuid4(), "site_id": SITE_ID, "client_email": "maria@example.com"})
    monkeypatch.setattr(access, "make_access_token", lambda: "session-secret-token")
    result = await access.redeem_suggestion_link(
        conn, token="link-secret", site_id=SITE_ID, now=NOW
    )
    assert result == (SITE_ID, "maria@example.com", "session-secret-token")
    assert "link-secret" not in repr(conn.executed)
    assert access.hash_access_token("session-secret-token") in repr(conn.executed)


def test_canonical_origin_uses_only_validated_subdomain(monkeypatch):
    monkeypatch.setenv("CAPPE_BASE_DOMAIN", "gummfit.com")
    assert access.canonical_suggestion_origin({"subdomain": "lumiere-spa"}) == (
        "https://lumiere-spa.gummfit.com"
    )
    assert access.canonical_suggestion_origin({"subdomain": "tenant.attacker"}) is None
