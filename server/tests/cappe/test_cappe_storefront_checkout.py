from types import SimpleNamespace
from uuid import uuid4

import pytest
from starlette.requests import Request

from app.cappe.models.shop import CappeCartItem, CappeCheckoutRequest, CappeProduct
from app.cappe.routes.public import shop as routes
from app.cappe.services import shopper_customers, stripe_connect


class _Ctx:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_args):
        return False


class _Conn:
    def __init__(self, product=None):
        self.product = product
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if "tax_rate_bps" in query:
            return {"tax_rate_bps": 1000, "shipping_flat_cents": 500,
                    "shipping_free_threshold_cents": 3000}
        if "FROM cappe_shoppers" in query:
            return {"id": args[0], "site_id": args[1], "email": "buyer@example.com",
                    "name": "Buyer", "stripe_customer_id": None}
        if "FROM cappe_shopper_addresses" in query:
            return {"name": "Buyer", "phone": None, "line1": "1 Main", "line2": None,
                    "city": "Oakland", "region": "CA", "postal_code": "94601", "country": "US"}
        return None

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        return [self.product] if self.product else []

    async def fetchval(self, query, *args):
        self.calls.append((query, args))
        if "NOW()" in query:
            from datetime import datetime, timezone
            return datetime.now(timezone.utc)
        if "UPDATE cappe_shoppers" in query:
            return "cus_buyer"
        return None


def _request():
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": ("127.0.0.1", 1)})


@pytest.mark.asyncio
async def test_public_quote_and_signed_order_use_authoritative_shopper(monkeypatch):
    site_id, product_id = uuid4(), uuid4()
    site = {"id": site_id, "timezone": "UTC"}
    product = {
        "id": product_id, "site_id": site_id, "name": "Soap", "price_cents": 1000,
        "currency": "USD", "inventory": 10, "status": "active", "fulfillment": "physical",
    }
    conn = _Conn(product)
    monkeypatch.setattr(routes, "get_connection", lambda: _Ctx(conn))
    monkeypatch.setattr(routes, "_read_rate_limit", lambda *_args: _async(None))
    monkeypatch.setattr(routes, "_published_site", lambda *_args: _async(site))
    monkeypatch.setattr(routes, "fetch_option_groups", lambda *_args: _async({product_id: []}))
    monkeypatch.setattr(routes, "fetch_active_discounts", lambda *_args: _async([]))
    quote = await routes.quote(
        "ahnimal", routes.CartQuoteRequest(items=[CappeCartItem(product_id=product_id, quantity=2)]), _request(),
    )
    assert quote["subtotal_cents"] == 2000
    assert quote["tax_cents"] == 200 and quote["shipping_cents"] == 500

    product.update(subscription_intervals=["month"], subscription_discount_bps=1000,
                   requires_approval=False)
    recurring_quote = await routes.quote(
        "ahnimal", routes.CartQuoteRequest(
            items=[CappeCartItem(product_id=product_id, quantity=2)], interval="month",
        ), _request(),
    )
    assert recurring_quote["subtotal_cents"] == 1800

    rates = []
    captured = []
    monkeypatch.setattr(routes, "check_rate_limit", lambda *args: _record(rates, args))

    async def create(site_arg, body_arg, background, *, shopper=None):
        captured.append((site_arg, body_arg, shopper))
        return {"order_id": "order"}

    monkeypatch.setattr(routes, "create_public_order", create)
    shopper = {"id": uuid4(), "email": "signed@gmail.com"}
    body = CappeCheckoutRequest(
        customer_email="other@example.net", items=[CappeCartItem(product_id=product_id, quantity=1)],
    )
    assert await routes.public_create_order("ahnimal", body, _request(), SimpleNamespace(), shopper) == {"order_id": "order"}
    assert captured[0][2] == shopper
    assert rates[0][0] == f"shopper:{shopper['id']}"


def test_public_product_response_keeps_active_discount_fields():
    product = CappeProduct(
        id=uuid4(), site_id=uuid4(), name="Sale soap", price_cents=1000,
        currency="USD", status="active", sort_order=0,
        discount_percent=20, discounted_price_cents=800,
    )
    payload = product.model_dump()
    assert payload["discount_percent"] == 20
    assert payload["discounted_price_cents"] == 800


async def _async(value):
    return value


async def _record(values, value):
    values.append(value)


@pytest.mark.asyncio
async def test_connected_customer_prefills_default_shipping_and_claims_id(monkeypatch):
    shopper = {"id": uuid4(), "site_id": uuid4()}
    conn = _Conn()
    monkeypatch.setattr(shopper_customers, "get_connection", lambda: _Ctx(conn))
    calls = []

    class _Stripe:
        async def ensure_connected_customer(self, **kwargs):
            calls.append(kwargs)
            return "cus_buyer"

    monkeypatch.setattr(shopper_customers, "get_cappe_stripe", lambda: _Stripe())
    assert await shopper_customers.connected_customer(shopper, "acct_owner") == "cus_buyer"
    assert calls[0]["shipping"]["address"]["postal_code"] == "94601"
    assert calls[0]["idempotency_key"].startswith("shopper:")


@pytest.mark.asyncio
async def test_stripe_connected_customer_subscription_and_customer_checkout(monkeypatch):
    calls = []

    class _Customer:
        @staticmethod
        def create(**kwargs):
            calls.append(("customer.create", kwargs))
            return {"id": "cus_new"}

        @staticmethod
        def modify(customer_id, **kwargs):
            calls.append(("customer.modify", customer_id, kwargs))
            return {"id": customer_id}

    class _Session:
        @staticmethod
        def create(**kwargs):
            calls.append(("session.create", kwargs))
            return {"id": "cs_1", "url": "https://checkout.test"}

    class _Subscription:
        @staticmethod
        def retrieve(subscription_id, **kwargs):
            calls.append(("subscription.retrieve", subscription_id, kwargs))
            return {"id": subscription_id}

        @staticmethod
        def modify(subscription_id, **kwargs):
            calls.append(("subscription.modify", subscription_id, kwargs))
            return {"id": subscription_id, "cancel_at_period_end": kwargs["cancel_at_period_end"]}

        @staticmethod
        def delete(subscription_id, **kwargs):
            calls.append(("subscription.delete", subscription_id, kwargs))
            return {"id": subscription_id, "status": "canceled"}

    fake_stripe = SimpleNamespace(
        api_key=None, Customer=_Customer, Subscription=_Subscription,
        checkout=SimpleNamespace(Session=_Session),
    )
    monkeypatch.setattr(stripe_connect, "stripe", fake_stripe)
    monkeypatch.setattr(stripe_connect, "get_settings", lambda: SimpleNamespace(stripe_secret_key="sk_test"))
    service = stripe_connect.CappeStripe()
    service.settings = SimpleNamespace(stripe_secret_key="sk_test")

    shipping = {"name": "Buyer", "address": {"country": "US"}}
    assert await service.ensure_connected_customer(
        account_id="acct_owner", email="buyer@example.com", shipping=shipping,
        idempotency_key="shopper:1",
    ) == "cus_new"
    assert await service.ensure_connected_customer(
        account_id="acct_owner", email="buyer@example.com", customer_id="cus_new",
    ) == "cus_new"
    await service.create_checkout_session(
        account_id="acct_owner", currency="USD", line_items=[], application_fee_cents=20,
        success_url="https://store.test/s", cancel_url="https://store.test/c", metadata={},
        customer_id="cus_new", collect_shipping_address=True,
    )
    await service.create_subscription_checkout(
        account_id="acct_owner", customer_id="cus_new", line_items=[], application_fee_percent=2.0,
        success_url="https://store.test/s", cancel_url="https://store.test/c", metadata={},
        collect_shipping=True, idempotency_key="sub:1",
    )
    assert await service.retrieve_connected_subscription("acct_owner", "sub_1") == {"id": "sub_1"}
    assert (await service.modify_connected_subscription(
        account_id="acct_owner", subscription_id="sub_1", cancel_at_period_end=True,
    ))["cancel_at_period_end"] is True
    assert (await service.cancel_connected_subscription("acct_owner", "sub_1"))["status"] == "canceled"
    customer_checkout = [entry[1] for entry in calls if entry[0] == "session.create"][0]
    assert customer_checkout["customer"] == "cus_new"
    assert customer_checkout["customer_update"] == {"shipping": "auto"}
