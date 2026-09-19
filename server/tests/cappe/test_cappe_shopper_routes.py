import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe import dependencies  # noqa: E402
from app.cappe.routes.public import shopper as routes  # noqa: E402
from app.cappe.services import recurring  # noqa: E402


class _Tx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, *, row=None, rows=None, values=None, execute_result="UPDATE 1"):
        self.row = row
        self.rows = list(rows or [])
        self.values = values if callable(values) else list(values or [])
        self.execute_result = execute_result
        self.calls = []

    def transaction(self):
        return _Tx()

    async def execute(self, query, *args):
        self.calls.append((query, args))
        return self.execute_result

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if callable(self.row):
            return self.row(query, args)
        return self.row

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return self.rows

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        if callable(self.values):
            return self.values(query, args)
        return self.values.pop(0) if self.values else None


class _Background:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *args):
        self.tasks.append((fn, args))


def _request():
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1)})


def _context():
    site = {"id": uuid4(), "name": "Ahnimal"}
    shopper = {
        "id": uuid4(), "site_id": site["id"], "email": "buyer@somewhere.com",
        "name": None, "phone": None, "push_order_updates": True,
    }
    return site, shopper


@pytest.mark.asyncio
async def test_shopper_dependencies_bind_bearer_to_path_site(monkeypatch):
    site, shopper = _context()
    conn = _Conn()
    seen = []

    async def published(_conn, slug):
        seen.append(slug)
        return site

    async def resolve(_conn, resolved_site, token):
        assert resolved_site == site and token == "shopper-token"
        return shopper, {"scope": "cappe_shopper"}

    monkeypatch.setattr(dependencies, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr("app.cappe.services.shopper_auth.published_shopper_site", published)
    monkeypatch.setattr("app.cappe.services.shopper_auth.resolve_shopper", resolve)
    credential = HTTPAuthorizationCredentials(scheme="Bearer", credentials="shopper-token")

    assert await dependencies.optional_shopper("ahnimal", credential) == shopper
    assert await dependencies.require_shopper("ahnimal", credential) == (site, shopper)
    assert seen == ["ahnimal", "ahnimal"]
    assert await dependencies.optional_shopper("ahnimal", None) is None
    with pytest.raises(HTTPException) as caught:
        await dependencies.require_shopper("ahnimal", None)
    assert caught.value.status_code == 401


@pytest.mark.asyncio
async def test_shopper_auth_routes_start_verify_refresh_and_logout(monkeypatch):
    site, shopper = _context()
    conn = _Conn()
    background = _Background()
    rate_calls = []

    async def rate(*args):
        rate_calls.append(args)

    async def published(_conn, slug):
        assert slug == "ahnimal"
        return site

    async def issue(_conn, **kwargs):
        assert kwargs["email"] == shopper["email"]
        return "123456"

    async def verify(_conn, **kwargs):
        return {"access_token": "access"} if kwargs["code"] == "123456" else None

    async def resolve(_conn, _site, token, kind, lock):
        assert (token, kind, lock) == ("refresh", "refresh", True)
        return shopper, {"sid": str(uuid4()), "session_started_at": 10}

    async def session(_conn, resolved, **kwargs):
        assert resolved == shopper and kwargs["started"] == 10
        return {"access_token": "rotated"}

    monkeypatch.setattr(routes, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(routes, "check_rate_limit", rate)
    monkeypatch.setattr(routes, "check_recipient_send_ok", lambda _email: _async(True))
    monkeypatch.setattr(routes.auth, "published_shopper_site", published)
    monkeypatch.setattr(routes.auth, "issue_login_code", issue)
    monkeypatch.setattr(routes.auth, "verify_login_code", verify)
    monkeypatch.setattr(routes.auth, "resolve_shopper", resolve)
    monkeypatch.setattr(routes.auth, "issue_session", session)

    response = await routes.start("ahnimal", routes.ShopperStart(email=shopper["email"]), _request(), background)
    assert response.status_code == 204 and background.tasks[0][1][-1] == "123456"
    assert (await routes.verify("ahnimal", routes.ShopperVerify(email=shopper["email"], code="123456"), _request()))["access_token"] == "access"
    with pytest.raises(HTTPException) as caught:
        await routes.verify("ahnimal", routes.ShopperVerify(email=shopper["email"], code="654321"), _request())
    assert caught.value.status_code == 401
    refreshed = await routes.refresh("ahnimal", routes.ShopperRefresh(refresh_token="refresh"), _request())
    assert refreshed == {"access_token": "rotated"}
    assert (await routes.logout((site, shopper))).status_code == 204
    assert any("DELETE FROM cappe_shopper_devices" in sql for sql, _ in conn.calls)
    assert len(rate_calls) == 4


async def _async(value):
    return value


@pytest.mark.asyncio
async def test_profile_addresses_and_account_delete_are_site_scoped(monkeypatch):
    site, shopper = _context()
    address_id = uuid4()

    def row(query, args):
        if "UPDATE cappe_shoppers SET name" in query:
            return {**shopper, "name": args[2]}
        if "cappe_shopper_addresses SET" in query or "INSERT INTO cappe_shopper_addresses" in query:
            return {"id": address_id, "shopper_id": shopper["id"], "site_id": site["id"], **address.model_dump()}
        return None

    def value(query, _args):
        if "SELECT id FROM cappe_shoppers" in query:
            return shopper["id"]
        if "SELECT count(*)" in query:
            return 0
        if "SELECT id FROM cappe_shopper_addresses" in query:
            return address_id
        return None

    conn = _Conn(row=row, values=value)
    monkeypatch.setattr(routes, "get_connection", lambda: _Ctx(conn))
    deleted = []

    async def delete_subs(*args):
        deleted.append(args)

    monkeypatch.setattr(recurring, "delete_shopper_subscriptions", delete_subs)

    assert await routes.me((site, shopper)) == shopper
    assert await routes.update_me(routes.ShopperProfile(), (site, shopper)) == shopper
    updated = await routes.update_me(routes.ShopperProfile(name="Buyer"), (site, shopper))
    assert updated["name"] == "Buyer"

    address = routes.ShopperAddress(
        label="Home", name="Buyer", line1="1 Main", city="Oakland", postal_code="94601", is_default=True,
    )
    created = await routes.add_address(address, (site, shopper))
    edited = await routes.edit_address(address_id, address, (site, shopper))
    assert created["id"] == edited["id"] == address_id
    assert any("SET is_default=false" in sql for sql, _ in conn.calls)
    assert (await routes.delete_address(address_id, (site, shopper))).status_code == 204
    assert (await routes.delete_me((site, shopper))).status_code == 204
    assert deleted == [(site, shopper)]

    missing = _Conn(values=lambda query, _args: shopper["id"] if "cappe_shoppers" in query else None)
    monkeypatch.setattr(routes, "get_connection", lambda: _Ctx(missing))
    with pytest.raises(HTTPException) as caught:
        await routes.edit_address(address_id, address, (site, shopper))
    assert caught.value.status_code == 404

    zero = _Conn(execute_result="DELETE 0")
    monkeypatch.setattr(routes, "get_connection", lambda: _Ctx(zero))
    with pytest.raises(HTTPException) as caught:
        await routes.delete_address(address_id, (site, shopper))
    assert caught.value.status_code == 404


@pytest.mark.asyncio
async def test_favorites_orders_and_devices_enforce_shopper_ownership(monkeypatch):
    site, shopper = _context()
    product_id, order_id = uuid4(), uuid4()
    created = datetime.now(timezone.utc)
    order_row = {
        "id": order_id, "order_token": "a" * 32, "status": "paid", "subtotal_cents": 100,
        "tax_cents": 0, "shipping_cents": 0, "total_cents": 100, "currency": "USD",
        "created_at": created, "carrier": None, "tracking_number": None,
    }
    favorite_rows = [{"product_id": product_id}]
    item_rows = [{"order_id": order_id, "title": "Soap", "quantity": 1, "unit_price_cents": 100,
                  "fulfillment": "physical", "selected_options": "[]"}]

    async def fetch(query, *_args):
        if "cappe_shopper_favorites" in query:
            return favorite_rows
        if "cappe_order_items" in query:
            return item_rows
        if "FROM cappe_orders" in query:
            return [order_row]
        return []

    def value(query, _args):
        if "SELECT id FROM cappe_shoppers" in query or "SELECT id FROM cappe_products" in query:
            return product_id
        if "count(*)" in query:
            return 0
        return None

    conn = _Conn(row=order_row, values=value)
    conn.fetch = fetch
    monkeypatch.setattr(routes, "get_connection", lambda: _Ctx(conn))

    assert await routes.favorites((site, shopper)) == [str(product_id)]
    assert (await routes.add_favorite(product_id, (site, shopper))).status_code == 204
    assert (await routes.delete_favorite(product_id, (site, shopper))).status_code == 204
    page = await routes.orders(cursor=None, limit=20, context=(site, shopper))
    assert page["orders"][0]["items"][0]["title"] == "Soap"
    detail = await routes.order(order_id, (site, shopper))
    assert detail["id"] == order_id

    registered = []

    async def register(*args):
        registered.append(args)

    monkeypatch.setattr("app.cappe.services.push.register_token", register)
    device = routes.ShopperDevice(token="a" * 64, bundle_id="com.ahnimal.app", environment="sandbox")
    assert (await routes.register_device(device, (site, shopper))).status_code == 204
    assert registered[0][0:2] == (site, shopper)
    assert (await routes.unregister_device("a" * 64, (site, shopper))).status_code == 204

    conn.row = None
    with pytest.raises(HTTPException) as caught:
        await routes.order(uuid4(), (site, shopper))
    assert caught.value.status_code == 404
