"""Every `CappeStripe` call hands back plain data on stripe-python 16.

The SDK's objects aren't dicts there (`.get` raises), and Cappe reads every
response with `.get`, so each wrapper goes through `_call`. These drive the
wrappers the money paths don't already cover, with the SDK faked, and check
both the plain result and what each asks Stripe for.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_stripe_wrappers.py -q
"""
import asyncio
import json
import time
from types import SimpleNamespace

import pytest
import stripe

from app.cappe.services import stripe_connect
from app.cappe.services.stripe_connect import CappeStripe, CappeStripeError, StripeData


def _obj(data: dict):
    return stripe.StripeObject.construct_from(data, "sk_test_x")


@pytest.fixture
def cs(monkeypatch):
    monkeypatch.setattr(stripe_connect, "get_settings", lambda: SimpleNamespace(
        stripe_secret_key="sk_test_x", cappe_platform_webhook_secret="whsec_platform",
        cappe_stripe_webhook_secret="whsec_connect"))
    return CappeStripe()


@pytest.fixture
def sdk(monkeypatch):
    """`sdk(owner, "create", {...})` fakes one SDK call; `sdk.calls` records them."""
    calls: list[tuple[str, tuple, dict]] = []

    def fake(owner, name, answer):
        def call(*args, **kwargs):
            calls.append((f"{owner.__name__}.{name}", args, kwargs))
            if isinstance(answer, Exception):
                raise answer
            return _obj(answer)
        monkeypatch.setattr(owner, name, call)

    fake.calls = calls
    return fake


def run(coro):
    return asyncio.run(coro)


def _plain(out) -> bool:
    return isinstance(out, StripeData) and all(isinstance(v, dict) == isinstance(v, StripeData) for v in out.values())


def test_connect_onboarding(cs, sdk):
    sdk(stripe.Account, "create", {"id": "acct_1"})
    sdk(stripe.AccountLink, "create", {"url": "https://connect.stripe.test/a", "expires_at": 1})
    sdk(stripe.Account, "retrieve", {"id": "acct_1", "charges_enabled": True, "settings": {"x": 1}})
    assert run(cs.create_connected_account("owner@example.com")) == "acct_1"
    link = run(cs.create_account_link("acct_1", "https://r.test", "https://u.test"))
    assert _plain(link) and link.get("url") == "https://connect.stripe.test/a"
    acct = run(cs.retrieve_account("acct_1"))
    assert _plain(acct) and acct.get("settings").get("x") == 1
    assert sdk.calls[0][2]["type"] == "standard" and sdk.calls[1][2]["type"] == "account_onboarding"


def test_checkout_sessions_are_read_and_closed_before_an_order_is_released(cs, sdk):
    sdk(stripe.checkout.Session, "retrieve", {"id": "cs_1", "status": "open", "shipping_details": {"name": "A"}})
    sdk(stripe.checkout.Session, "expire", {"id": "cs_1", "status": "expired"})
    sess = run(cs.retrieve_checkout_session("acct_1", "cs_1"))
    assert _plain(sess) and sess.get("shipping_details").get("name") == "A"
    assert run(cs.expire_checkout_session("acct_1", "cs_1")) == "expired"
    assert [c[0] for c in sdk.calls] == ["Session.retrieve", "Session.retrieve", "Session.expire"]
    assert all(c[2]["stripe_account"] == "acct_1" for c in sdk.calls)
    sdk.calls.clear()
    sdk(stripe.checkout.Session, "retrieve", {"id": "cs_1", "status": "complete"})
    assert run(cs.expire_checkout_session("acct_1", "cs_1")) == "complete"  # paid: never expired
    assert [c[0] for c in sdk.calls] == ["Session.retrieve"]


def _signed(payload: bytes, secret: str) -> str:
    ts = int(time.time())
    return f"t={ts},v1={stripe.WebhookSignature._compute_signature(f'{ts}.{payload.decode()}', secret)}"


@pytest.mark.parametrize("verify, secret", [("verify_platform_webhook", "whsec_platform"),
                                            ("verify_webhook", "whsec_connect")])
def test_each_webhook_checks_its_own_secret_and_returns_the_event(cs, verify, secret):
    payload = json.dumps({"id": "evt_1", "type": "invoice.paid", "data": {"object": {"id": "in_1"}}}).encode()
    event = run(getattr(cs, verify)(payload, _signed(payload, secret)))
    assert _plain(event) and event.get("data").get("object").get("id") == "in_1"
    other = "whsec_connect" if secret == "whsec_platform" else "whsec_platform"
    with pytest.raises(CappeStripeError, match="Invalid Stripe webhook"):
        run(getattr(cs, verify)(payload, _signed(payload, other)))


def test_catalog_products_prices_and_customers(cs, sdk):
    sdk(stripe.Product, "create", {"id": "prod_1"})
    sdk(stripe.Price, "create", {"id": "price_1"})
    sdk(stripe.Price, "modify", {"id": "price_0", "active": False})
    sdk(stripe.Customer, "create", {"id": "cus_1"})
    assert run(cs.ensure_product(code="writer", name="Writer")) == "prod_1"
    assert run(cs.ensure_price(product_id="prod_1", unit_amount_cents=900, currency="USD", interval="month",
                               lookup_key="writer_month")) == "price_1"
    assert run(cs.ensure_price(product_id="prod_1", unit_amount_cents=500, currency="usd", interval="once")) == "price_1"
    assert run(cs.archive_price("price_0")) is None
    assert run(cs.ensure_customer(email="owner@example.com", account_id="a1")) == "cus_1"
    monthly, once = sdk.calls[1][2], sdk.calls[2][2]
    assert monthly == {"product": "prod_1", "unit_amount": 900, "currency": "usd", "metadata": {"product": "cappe"},
                       "recurring": {"interval": "month"}, "lookup_key": "writer_month"}
    assert "recurring" not in once and "lookup_key" not in once
    assert sdk.calls[3][1:] == (("price_0",), {"active": False})


def test_subscriptions_are_read_changed_trimmed_and_cancelled(cs, sdk):
    sub = {"id": "sub_1", "items": {"data": [{"id": "si_1", "price": {"id": "price_1"}}]}}
    sdk(stripe.Subscription, "retrieve", sub)
    sdk(stripe.Subscription, "modify", {**sub, "cancel_at_period_end": True})
    sdk(stripe.Subscription, "delete", {"id": "sub_1", "status": "canceled"})
    sdk(stripe.SubscriptionItem, "delete", {"id": "si_2", "deleted": True})
    got = run(cs.retrieve_subscription("sub_1"))
    assert _plain(got) and got.get("items").get("data")[0].get("price").get("id") == "price_1"
    changed = run(cs.change_subscription_price(subscription_id="sub_1", item_id="si_1", new_price_id="price_2",
                                               anchor_now=True, end_trial=True))
    assert _plain(changed)
    assert run(cs.remove_subscription_item("si_2")).get("deleted") is True
    assert run(cs.cancel_subscription("sub_1")).get("cancel_at_period_end") is True
    assert run(cs.cancel_subscription("sub_1", at_period_end=False)).get("status") == "canceled"
    modify = sdk.calls[1][2]
    assert modify["items"] == [{"id": "si_1", "price": "price_2"}] and modify["billing_cycle_anchor"] == "now"
    assert modify["trial_end"] == "now" and modify["payment_behavior"] == "pending_if_incomplete"
    assert [c[0] for c in sdk.calls[2:]] == ["SubscriptionItem.delete", "Subscription.modify", "Subscription.delete"]


def test_billing_portals_on_the_platform_and_on_a_store(cs, sdk):
    sdk(stripe.billing_portal.Session, "create", {"url": "https://billing.stripe.test/s"})
    sdk(stripe.billing_portal.Configuration, "create", {"id": "bpc_1"})
    assert run(cs.create_billing_portal_session(customer_id="cus_1", return_url="https://r.test")).get("url")
    assert run(cs.create_portal_configuration("acct_1")) == "bpc_1"
    shop = run(cs.create_connected_portal_session(account_id="acct_1", customer_id="cus_2",
                                                  return_url="https://r.test", configuration_id="bpc_1"))
    assert _plain(shop)
    assert sdk.calls[1][2]["stripe_account"] == "acct_1"
    assert sdk.calls[2][2] == {"customer": "cus_2", "return_url": "https://r.test", "stripe_account": "acct_1",
                               "configuration": "bpc_1"}
    run(cs.create_connected_portal_session(account_id="acct_1", customer_id="cus_2", return_url="https://r.test",
                                           configuration_id=None))
    assert "configuration" not in sdk.calls[3][2]


@pytest.mark.parametrize("call, owner, name", [
    (lambda cs: cs.create_connected_account("a@example.com"), stripe.Account, "create"),
    (lambda cs: cs.retrieve_account("acct_1"), stripe.Account, "retrieve"),
    (lambda cs: cs.expire_checkout_session("acct_1", "cs_1"), stripe.checkout.Session, "retrieve"),
    (lambda cs: cs.ensure_customer(email="a@example.com", account_id="a1"), stripe.Customer, "create"),
    (lambda cs: cs.remove_subscription_item("si_1"), stripe.SubscriptionItem, "delete"),
    (lambda cs: cs.create_portal_configuration("acct_1"), stripe.billing_portal.Configuration, "create"),
])
def test_a_stripe_failure_is_a_cappe_stripe_error(cs, sdk, call, owner, name):
    sdk(owner, name, stripe.APIConnectionError("down"))
    with pytest.raises(CappeStripeError):
        run(call(cs))
