"""Route-boundary tests for Cappe booking suggestion access."""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.responses import Response

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.models.bookings import (  # noqa: E402
    CappeBookingSuggestionAccessRedeem,
    CappeBookingSuggestionAccessRequest,
)
from app.cappe.routes.public import booking_suggestion_access as route  # noqa: E402
from app.cappe.routes.public import bookings as bookings_route  # noqa: E402


SITE_ID = uuid4()
REQUEST = SimpleNamespace(
    headers={"host": "lumiere-spa.cappe.localhost:8001"},
    url=SimpleNamespace(scheme="http"),
    client=SimpleNamespace(host="127.0.0.1"),
    cookies={},
)


class _Transaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, *, client=None, redeemed=None, session_email=None):
        self.client = client
        self.redeemed = redeemed
        self.session_email = session_email
        self.executed = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def transaction(self):
        return _Transaction()

    async def fetchrow(self, query, *_args):
        if "cappe_booking_suggestion_links" in query:
            return self.redeemed
        return None

    async def fetchval(self, *_args):
        return self.session_email

    async def execute(self, *args):
        self.executed.append(args)


async def _noop(*_args, **_kwargs):
    return None


async def _site(*_args, **_kwargs):
    return {
        "id": SITE_ID,
        "name": "Lumiere",
        "slug": "lumiere-spa",
        "subdomain": "lumiere-spa",
        "custom_domain": None,
    }


@pytest.mark.asyncio
async def test_access_request_is_generic_for_unknown_email(monkeypatch):
    conn = _Conn()
    monkeypatch.setattr(route, "check_rate_limit", _noop)
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    monkeypatch.setattr(route, "_published_site", _site)
    monkeypatch.setattr(route, "issue_suggestion_link", _no_link)
    monkeypatch.setattr(route, "_recipient_send_ok", _unexpected_send_check)

    result = await route.request_booking_suggestion_access(
        "lumiere-spa",
        CappeBookingSuggestionAccessRequest(email="unknown@example.com"),
        REQUEST,
        BackgroundTasks(),
    )

    assert result.body == b'{"status":"sent"}'


@pytest.mark.asyncio
async def test_missing_session_rejects_before_suggestion_work(monkeypatch):
    conn = _Conn(session_email=None)
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    monkeypatch.setattr(route, "_published_site", _site)

    with pytest.raises(HTTPException) as exc:
        await route.require_booking_suggestion_session("lumiere-spa", REQUEST)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_canonical_session_is_resolved_for_suggestion_dependency(monkeypatch):
    conn = _Conn(session_email="ai-client@lumiere.test")
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    monkeypatch.setattr(route, "_published_site", _site)

    request = SimpleNamespace(
        headers={"host": "lumiere-spa.hey-matcha.com"},
        url=SimpleNamespace(scheme="https"),
        client=SimpleNamespace(host="127.0.0.1"),
        cookies={"cappe_booking_suggestion": "session-secret"},
    )
    assert await route.require_booking_suggestion_session("lumiere-spa", request) == (
        "ai-client@lumiere.test"
    )


@pytest.mark.asyncio
async def test_redeem_sets_site_session_cookie(monkeypatch):
    conn = _Conn(
        redeemed={
            "id": uuid4(),
            "site_id": SITE_ID,
            "client_email": "ai-client@lumiere.test",
        }
    )
    monkeypatch.setattr(route, "check_rate_limit", _noop)
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    monkeypatch.setattr(route, "_published_site", _site)
    monkeypatch.setattr(
        route,
        "redeem_suggestion_link",
        lambda *_args, **_kwargs: _redeemed_session(),
    )
    response = Response()

    result = await route.redeem_site_booking_suggestion_access(
        "lumiere-spa",
        CappeBookingSuggestionAccessRedeem(token="link-secret-012345678901234567890123"),
        REQUEST,
        response,
    )

    assert result == {"status": "ok"}
    cookie = response.headers["set-cookie"]
    assert "cappe_booking_suggestion=session-secret" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=1800" in cookie
    assert "Domain=" not in cookie


@pytest.mark.asyncio
async def test_access_request_uses_canonical_origin_not_forwarded_host(monkeypatch):
    conn = _Conn()
    captured = {}

    async def issued(*_args, **_kwargs):
        return "link-secret-012345678901234567890123456789", "Maria"

    async def fake_send(*args, **kwargs):
        captured.update({"args": args, "kwargs": kwargs})

    malicious_request = SimpleNamespace(
        headers={
            "host": "lumiere-spa.cappe.localhost:8001",
            "x-forwarded-host": "lumiere-spa.cappe.localhost:8001@attacker.example",
        },
        url=SimpleNamespace(scheme="http"),
        client=SimpleNamespace(host="127.0.0.1"),
        cookies={},
    )
    monkeypatch.setattr(route, "check_rate_limit", _noop)
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    monkeypatch.setattr(route, "_published_site", _site)
    monkeypatch.setattr(route, "issue_suggestion_link", issued)
    monkeypatch.setattr(route, "_recipient_send_ok", _yes)
    monkeypatch.setattr(route, "send_cappe_booking_suggestion_access_email", fake_send)

    background = BackgroundTasks()
    result = await route.request_booking_suggestion_access(
        "lumiere-spa",
        CappeBookingSuggestionAccessRequest(email="maria@example.com"),
        malicious_request,
        background,
    )

    assert result.body == b'{"status":"sent"}'
    await background()
    assert "attacker.example" not in captured["args"][3]
    assert "lumiere-spa.hey-matcha.com" in captured["args"][3]


@pytest.mark.asyncio
async def test_custom_domain_access_still_emails_canonical_host(monkeypatch):
    conn = _Conn()
    captured = {}

    async def issued(*_args, **_kwargs):
        return "link-secret-012345678901234567890123456789", "Maria"

    async def fake_send(*args, **kwargs):
        captured.update({"args": args, "kwargs": kwargs})

    site = {**(await _site()), "custom_domain": "lumiere.example.com"}
    custom_request = SimpleNamespace(
        headers={"host": "www.lumiere.example.com"},
        url=SimpleNamespace(scheme="https"),
        client=SimpleNamespace(host="127.0.0.1"),
        cookies={},
    )
    monkeypatch.setattr(route, "check_rate_limit", _noop)
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    async def custom_site(*_args, **_kwargs):
        return site

    monkeypatch.setattr(route, "_published_site", custom_site)
    monkeypatch.setattr(route, "issue_suggestion_link", issued)
    monkeypatch.setattr(route, "_recipient_send_ok", _yes)
    monkeypatch.setattr(route, "send_cappe_booking_suggestion_access_email", fake_send)

    background = BackgroundTasks()
    await route.request_booking_suggestion_access(
        "lumiere-spa",
        CappeBookingSuggestionAccessRequest(email="maria@example.com"),
        custom_request,
        background,
    )
    await background()
    assert "lumiere.example.com" not in captured["args"][3]
    assert "lumiere-spa.hey-matcha.com" in captured["args"][3]


def test_suggestion_route_dependency_rejects_missing_session(monkeypatch):
    app = FastAPI()
    app.include_router(bookings_route.suggestions_router)

    conn = _Conn(session_email=None)
    monkeypatch.setattr(route, "get_connection", lambda: conn)
    monkeypatch.setattr(route, "_published_site", _site)
    monkeypatch.setattr(bookings_route, "_published_site", _site)
    client = TestClient(app, base_url="http://lumiere-spa.cappe.localhost:8001")

    response = client.post(
        "/public/sites/lumiere-spa/booking-suggestions",
        json={"booking_type_id": str(uuid4()), "request": "Tuesday morning"},
    )

    assert response.status_code == 403


def test_manual_booking_route_has_no_suggestion_session_dependency():
    manual_route = next(
        item for item in bookings_route.router.routes
        if getattr(item, "path", "").endswith("/bookings")
    )
    suggestion_route = next(
        item for item in bookings_route.suggestions_router.routes
        if getattr(item, "path", "").endswith("/booking-suggestions")
    )
    assert not manual_route.dependant.dependencies
    assert any(
        dependency.call is route.require_booking_suggestion_session
        for dependency in suggestion_route.dependant.dependencies
    )


async def _yes(*_args, **_kwargs):
    return True


async def _no_link(*_args, **_kwargs):
    return None


async def _redeemed_session():
    return SITE_ID, "ai-client@lumiere.test", "session-secret"


async def _unexpected_send_check(*_args, **_kwargs):
    raise AssertionError("unknown email must not send")
