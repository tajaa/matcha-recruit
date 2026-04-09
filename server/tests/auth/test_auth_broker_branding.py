import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.routes import auth as auth_routes


class _FakeConn:
    def __init__(self, row=None):
        self.row = row
        self.last_key = None

    async def fetchrow(self, query, *args):
        self.last_key = args[0] if args else None
        return self.row


class _FakeConnContext:
    def __init__(self, conn: _FakeConn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


def _set_fake_connection(monkeypatch, conn: _FakeConn):
    monkeypatch.setattr(auth_routes, "get_connection", lambda: _FakeConnContext(conn))


def test_broker_branding_runtime_rejects_invalid_key(monkeypatch):
    _set_fake_connection(monkeypatch, _FakeConn())
    with pytest.raises(HTTPException, match="broker_key must be 2-120 chars"):
        asyncio.run(auth_routes.get_broker_branding_runtime("bad key"))


def test_broker_branding_runtime_not_found(monkeypatch):
    _set_fake_connection(monkeypatch, _FakeConn(row=None))
    with pytest.raises(HTTPException, match="Broker branding not found"):
        asyncio.run(auth_routes.get_broker_branding_runtime("acme-broker"))


def test_broker_branding_runtime_success(monkeypatch):
    broker_id = uuid4()
    conn = _FakeConn(
        row={
            "broker_id": broker_id,
            "broker_slug": "acme-broker",
            "broker_name": "Acme Broker",
            "branding_mode": "co_branded",
            "brand_display_name": "Acme Benefits",
            "brand_legal_name": "Acme Benefits LLC",
            "logo_url": "https://example.com/logo.png",
            "favicon_url": "https://example.com/favicon.ico",
            "primary_color": "#123456",
            "secondary_color": "#abcdef",
            "login_subdomain": "acme",
            "custom_login_url": "https://portal.example.com/login",
            "support_email": "support@example.com",
            "support_phone": "555-123-4567",
            "support_url": "https://portal.example.com/support",
            "email_from_name": "Acme Benefits",
            "email_from_address": "no-reply@example.com",
            "powered_by_badge": True,
            "hide_matcha_identity": False,
            "mobile_branding_enabled": False,
            "theme": '{"banner":"clean"}',
            "resolved_by": "subdomain",
        }
    )
    _set_fake_connection(monkeypatch, conn)

    result = asyncio.run(auth_routes.get_broker_branding_runtime("acme"))

    assert conn.last_key == "acme"
    assert str(result.broker_id) == str(broker_id)
    assert result.brand_display_name == "Acme Benefits"
    assert result.branding_mode == "co_branded"
    assert result.theme == {"banner": "clean"}
    assert result.resolved_by == "subdomain"
