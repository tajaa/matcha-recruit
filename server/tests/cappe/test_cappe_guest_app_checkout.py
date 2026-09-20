"""Exercise order creation through the actual hosted-checkout return contract."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from app.cappe.models.shop import CappeCartItem, CappeCheckoutRequest
from app.cappe.routes import render
from app.cappe.services import commerce, shopper_customers
from fastapi import BackgroundTasks
from starlette.requests import Request


class CheckoutConnection:
    def __init__(self, site, product):
        self.site, self.product = site, product
        self.order = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def transaction(self):
        return self

    async def fetchrow(self, query, *args):
        if "FROM cappe_products" in query:
            assert args == (self.product["id"], self.site["id"])
            return self.product
        if "FROM cappe_sites" in query:
            return {"tax_rate_bps": 0, "tax_label": None, "shipping_flat_cents": 0,
                    "shipping_free_threshold_cents": None, "shipping_label": None}
        if "INSERT INTO cappe_orders" in query:
            self.order = {
                "id": uuid4(), "status": "pending", "access_token": uuid4().hex,
                "subtotal_cents": args[3], "tax_cents": args[4],
                "shipping_cents": args[5], "total_cents": args[6],
                "currency": args[7], "requires_approval": args[9],
            }
            return self.order
        raise AssertionError(query)

    async def fetchval(self, query, *args):
        if query == "SELECT NOW()":
            return datetime.now(timezone.utc)
        if "app_url_scheme" in query:
            assert args == (self.site["id"],)
            return "ahnimal"
        if "FROM cappe_orders" in query:
            assert args == (self.order["access_token"], self.site["id"])
            return self.order["id"]
        raise AssertionError(query)

    async def execute(self, query, *_args):
        assert "cappe_order_items" in query or "UPDATE cappe_orders" in query


@pytest.mark.asyncio
@pytest.mark.parametrize("signed_in", [False, True])
@pytest.mark.parametrize("return_kind", ["app", "external", "web"])
async def test_checkout_returns_bind_guest_and_signed_orders_without_leaking_tokens(
    monkeypatch, signed_in, return_kind,
):
    origin = "https://store.example.com"
    site = {"id": uuid4(), "name": "Store", "timezone": "UTC", "custom_domain": "store.example.com"}
    product = {"id": uuid4(), "name": "Guide", "price_cents": 1000, "currency": "USD",
               "status": "active", "fulfillment": "digital", "requires_approval": False}
    conn = CheckoutConnection(site, product)
    owner = {"plan": "business", "stripe_account_id": "acct_store", "stripe_charges_enabled": True}
    stripe = SimpleNamespace(create_checkout_session=AsyncMock(return_value={
        "id": "cs_test", "url": "https://checkout.example.com/session",
    }))
    monkeypatch.setattr(commerce, "get_connection", lambda: conn)
    monkeypatch.setattr(commerce, "fetch_active_discounts", AsyncMock(return_value=[]))
    monkeypatch.setattr(commerce, "fetch_option_groups", AsyncMock(return_value={}))
    monkeypatch.setattr(commerce, "fetch_site_owner", AsyncMock(return_value=owner))
    monkeypatch.setattr(commerce, "resolve_entitlements", AsyncMock(return_value=SimpleNamespace(platform_fee_bps=200)))
    monkeypatch.setattr(commerce, "require_can_sell", lambda _: None)
    monkeypatch.setattr(commerce, "get_cappe_stripe", lambda: stripe)
    monkeypatch.setattr(shopper_customers, "connected_customer", AsyncMock(return_value="cus_buyer"))
    shopper = {"id": uuid4(), "email": "buyer@example.com"} if signed_in else None
    requested_return = {
        "app": origin + "/__cappe/app-return?o=untrusted&r=cancel",
        "external": "https://external.example.com/__cappe/app-return",
        "web": origin + "/thanks?from=checkout",
    }[return_kind]
    result = await commerce.create_public_order(
        site, CappeCheckoutRequest(
            customer_email="buyer@example.com", items=[CappeCartItem(product_id=product["id"], quantity=1)],
            success_url=requested_return, cancel_url=requested_return,
        ), BackgroundTasks(), shopper=shopper,
    )
    assert result["checkout_url"] == "https://checkout.example.com/session"
    checkout_args = stripe.create_checkout_session.call_args.kwargs
    assert ("customer_id" in checkout_args) is signed_in
    monkeypatch.setattr(render, "get_connection", lambda: conn)
    monkeypatch.setattr(render, "_resolve_published_site", AsyncMock(return_value=site))
    for outcome in ("success", "cancel"):
        target = checkout_args[f"{outcome}_url"]
        if return_kind != "app":
            assert target == (origin + "/" if return_kind == "external" else requested_return)
            assert result["order_token"] not in target
            continue
        parsed = urlsplit(target)
        assert f"{parsed.scheme}://{parsed.netloc}" == origin
        query = parse_qs(parsed.query)
        assert query == {"o": [result["order_token"]], "r": [outcome]}
        request = Request({"type": "http", "method": "GET", "path": parsed.path,
                           "headers": [(b"host", parsed.netloc.encode())]})
        response = await render.app_return(request, o=query["o"][0], r=query["r"][0])
        assert response.status_code == 302
        assert response.headers["location"] == f"ahnimal://order/{result['order_token']}?r={outcome}"
