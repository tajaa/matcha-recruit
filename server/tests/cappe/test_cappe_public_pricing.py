"""Cappe public pricing: the anonymous lineup the gummfit.com landing page quotes.

Driven through real requests against a stubbed connection — no database.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_public_pricing.py -q
"""
import os
import uuid

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.dependencies import require_cappe_account  # noqa: E402
from app.cappe.models.cappe import CappeAccount  # noqa: E402
from app.cappe.routes import billing as billing_routes  # noqa: E402
from app.cappe.routes import cappe_router  # noqa: E402
from app.cappe.routes.public import pricing as pricing_routes  # noqa: E402


def _product(code, kind="plan", **kw):
    row = {
        "code": code,
        "kind": kind,
        "name": code.title(),
        "description": f"{code} plan",
        "status": "active",
        "sort_order": 0,
        "can_sell": True,
        "platform_fee_bps": 200,
        "allowed_fulfillment": ["physical", "service"],
        "site_limit": None,
        "mailbox_quota_included": 0,
        "features": '{"rider": true}',
        "unit_label": "unit",
        "max_quantity": 100,
    }
    row.update(kw)
    return row


def _price(code, role="standard", interval="month", cents=4900, minted=True, intro_days=None):
    return {
        "product_code": code,
        "role": role,
        "interval": interval,
        "unit_amount_cents": cents,
        "currency": "USD",
        "stripe_price_id": f"price_{code}_{role}_{interval}" if minted else None,
        "intro_days": intro_days,
    }


class _Conn:
    def __init__(self, products, prices):
        self._products, self._prices = products, prices

    async def fetch(self, sql, *_a):
        return self._products if "cappe_billing_products" in sql else self._prices

    async def fetchval(self, *_a, **_k):
        return 0


class _Ctx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *_a):
        return False


@pytest.fixture
def app():
    a = FastAPI()
    a.include_router(cappe_router, prefix="/api/cappe")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def stub(monkeypatch):
    async def _no_limit(*_a, **_k):
        return None

    monkeypatch.setattr(pricing_routes, "check_rate_limit", _no_limit)

    def _install(products, prices):
        conn = _Conn(products, prices)
        monkeypatch.setattr(pricing_routes, "get_connection", lambda: _Ctx(conn))
        monkeypatch.setattr(billing_routes, "get_connection", lambda: _Ctx(conn))
        return conn

    return _install


def test_public_pricing_needs_no_account(client, stub):
    stub([_product("free")], [])
    resp = client.get("/api/cappe/public/pricing")
    assert resp.status_code == 200
    assert [p["code"] for p in resp.json()["plans"]] == ["free"]


def test_only_purchasable_prices_and_plans_are_public(client, stub):
    stub(
        [
            _product("free"),
            _product("business"),
            _product("creator"),  # every price un-minted → not sellable → hidden
            _product("mailbox", kind="addon", unit_label="mailbox"),
        ],
        [
            _price("business", interval="month", cents=4900),
            _price("business", interval="year", cents=49000, minted=False),
            _price("creator", cents=1900, minted=False),
            _price("mailbox", cents=300),
        ],
    )
    body = client.get("/api/cappe/public/pricing").json()
    plans = {p["code"]: p for p in body["plans"]}
    assert set(plans) == {"free", "business"}
    assert plans["free"]["prices"] == []
    assert [p["interval"] for p in plans["business"]["prices"]] == ["month"]
    assert [a["code"] for a in body["addons"]] == ["mailbox"]


def test_intro_only_shown_when_its_stripe_price_exists(client, stub):
    stub(
        [_product("business"), _product("creator")],
        [
            _price("business"),
            _price("business", role="intro", interval="once", cents=100, intro_days=30),
            _price("creator", cents=1900),
            _price("creator", role="intro", interval="once", cents=100, minted=False, intro_days=30),
        ],
    )
    plans = {p["code"]: p for p in client.get("/api/cappe/public/pricing").json()["plans"]}
    assert plans["business"]["intro_price_cents"] == 100
    assert plans["business"]["intro_days"] == 30
    assert plans["creator"]["intro_price_cents"] is None


def test_public_response_is_an_allowlist(client, stub):
    stub([_product("business")], [_price("business")])
    body = client.get("/api/cappe/public/pricing").json()
    assert "intro_available" not in body
    plan = body["plans"][0]
    for internal in ("features", "can_sell", "status"):
        assert internal not in plan


def test_tenant_catalog_still_uses_the_shared_builder(app, client, stub, monkeypatch):
    """Regression for the extraction: the tenant catalog keeps un-minted
    prices (rendered disabled) and its account-specific intro flag."""
    stub([_product("business")], [_price("business", minted=False)])

    async def _eligible(*_a, **_k):
        return True

    monkeypatch.setattr(billing_routes.billing_svc, "intro_eligible", _eligible)
    app.dependency_overrides[require_cappe_account] = lambda: CappeAccount(
        id=uuid.uuid4(),
        email="owner@example.com",
        plan="free",
        status="active",
        account_type="business",
        is_platform_admin=False,
    )
    try:
        body = client.get("/api/cappe/billing/catalog").json()
    finally:
        app.dependency_overrides.clear()
    assert body["intro_available"] is True
    plan = body["plans"][0]
    assert plan["features"] == {"rider": True}
    assert plan["prices"][0]["purchasable"] is False
