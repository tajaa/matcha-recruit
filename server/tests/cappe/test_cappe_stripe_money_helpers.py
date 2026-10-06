"""`CappeStripe` — the calls that move money back, or charge a saved card.

Driven against a fake `stripe` module so the exact arguments each call sends
are pinned: which ACCOUNT a refund runs on, that an off-session charge names
its payment method, that a refused card is told apart from an outage.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_stripe_money_helpers.py -q
"""
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402

from app.cappe.services import stripe_connect as sc  # noqa: E402
from app.cappe.services.stripe_connect import CappeStripeCardError, CappeStripeError  # noqa: E402


class CardError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class CodedError(Exception):
    def __init__(self, message, code):
        super().__init__(message)
        self.code = code


class Recorder:
    """A Stripe resource class stand-in: records calls, returns/raises on cue."""

    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def _do(self, name, args, kwargs):
        self.calls.append((name, args, kwargs))
        if self.exc:
            raise self.exc
        return self.result(name, args, kwargs) if callable(self.result) else self.result

    def create(self, *args, **kwargs):
        return self._do("create", args, kwargs)

    def retrieve(self, *args, **kwargs):
        return self._do("retrieve", args, kwargs)

    def list(self, *args, **kwargs):
        return self._do("list", args, kwargs)

    def modify(self, *args, **kwargs):
        return self._do("modify", args, kwargs)

    def expire(self, *args, **kwargs):
        return self._do("expire", args, kwargs)


@pytest.fixture
def stripe(monkeypatch):
    fake = SimpleNamespace(
        CardError=CardError,
        Refund=Recorder({"id": "re_1"}),
        PaymentIntent=Recorder({"id": "pi_1", "payment_method": "pm_1"}),
        PaymentMethod=Recorder({"data": [{"id": "pm_listed"}], "card": {"fingerprint": "fp_1"}}),
        Invoice=Recorder({"payment_intent": "pi_legacy"}),
        InvoicePayment=Recorder({"data": []}),
        SubscriptionItem=Recorder({"id": "si_1"}),
        checkout=SimpleNamespace(Session=Recorder({"id": "cs_1", "status": "open", "url": "u"})),
    )
    monkeypatch.setattr(sc, "stripe", fake)
    monkeypatch.setattr(sc.CappeStripe, "_ensure_key", lambda self: None)
    return fake


@pytest.fixture
def cs(stripe):
    # `__init__` only reads app settings (for the API key `_ensure_key` sets,
    # which is patched out above), so the methods are driven without it.
    return sc.CappeStripe.__new__(sc.CappeStripe)


def run(coro):
    return asyncio.run(coro)


# ── refunds ──────────────────────────────────────────────────────────────────

def test_a_connected_refund_runs_on_the_merchants_account_and_returns_our_fee(stripe, cs):
    """`refund()` runs on the platform account, where a connected account's
    PaymentIntent does not exist — this is the call that can actually refund a
    storefront order."""
    out = run(cs.refund_connected_charge(account_id="acct_1", payment_intent="pi_1", idempotency_key="k1"))
    assert out == {"id": "re_1"}
    _, _, kwargs = stripe.Refund.calls[0]
    assert kwargs == {"payment_intent": "pi_1", "refund_application_fee": True,
                      "stripe_account": "acct_1", "idempotency_key": "k1"}


def test_a_connected_refund_without_a_key_sends_none(stripe, cs):
    run(cs.refund_connected_charge(account_id="acct_1", payment_intent="pi_1"))
    assert "idempotency_key" not in stripe.Refund.calls[0][2]


@pytest.mark.parametrize("method,kwargs", [
    ("refund_connected_charge", {"account_id": "acct_1", "payment_intent": "pi_1"}),
    ("refund", {"payment_intent": "pi_1"}),
])
def test_a_charge_already_refunded_counts_as_done_not_as_a_failure(stripe, cs, method, kwargs):
    """Refunded in the dashboard, or by an earlier attempt whose reply was
    lost: the money IS back, and failing would wedge the order for ever."""
    stripe.Refund.exc = CodedError("already refunded", "charge_already_refunded")
    assert run(getattr(cs, method)(**kwargs)) == {"id": None, "already_refunded": True}


@pytest.mark.parametrize("method,kwargs", [
    ("refund_connected_charge", {"account_id": "acct_1", "payment_intent": "pi_1"}),
    ("refund", {"payment_intent": "pi_1"}),
])
def test_any_other_refund_error_is_raised(stripe, cs, method, kwargs):
    stripe.Refund.exc = CodedError("insufficient balance", "balance_insufficient")
    with pytest.raises(CappeStripeError):
        run(getattr(cs, method)(**kwargs))


def test_a_platform_refund_is_keyed_when_asked(stripe, cs):
    run(cs.refund("pi_1", idempotency_key="cappe-domain-refund-d1"))
    assert stripe.Refund.calls[0][2] == {"payment_intent": "pi_1", "idempotency_key": "cappe-domain-refund-d1"}
    run(cs.refund("pi_2"))
    assert stripe.Refund.calls[1][2] == {"payment_intent": "pi_2"}


# ── the off-session charge ───────────────────────────────────────────────────

def _charge(cs, **over):
    kwargs = dict(customer_id="cus_1", payment_method_id="pm_1", amount_cents=1600, currency="usd",
                  metadata={"type": "cappe_domain_renewal"}, idempotency_key="k")
    kwargs.update(over)
    return run(cs.charge_off_session(**kwargs))


def test_the_off_session_charge_names_its_payment_method(stripe, cs):
    """A PaymentIntent does not fall back to "the customer's card"."""
    _charge(cs)
    kwargs = stripe.PaymentIntent.calls[0][2]
    assert kwargs["customer"] == "cus_1" and kwargs["payment_method"] == "pm_1"
    assert kwargs["off_session"] is True and kwargs["confirm"] is True
    assert kwargs["idempotency_key"] == "k" and kwargs["amount"] == 1600


def test_a_refused_card_is_a_card_error(stripe, cs):
    stripe.PaymentIntent.exc = CardError("Your card was declined.", code="card_declined")
    with pytest.raises(CappeStripeCardError) as exc:
        _charge(cs)
    assert exc.value.code == "card_declined"
    assert isinstance(exc.value, CappeStripeError)      # existing handlers still catch it


def test_an_outage_is_not_a_card_error(stripe, cs):
    stripe.PaymentIntent.exc = RuntimeError("connection reset")
    with pytest.raises(CappeStripeError) as exc:
        _charge(cs, idempotency_key=None)
    assert not isinstance(exc.value, CappeStripeCardError)


def test_card_error_detection_survives_a_missing_sdk(monkeypatch):
    monkeypatch.setattr(sc, "stripe", None)
    assert sc._is_card_error(RuntimeError("x")) is False


# ── saved cards ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pm,expected", [
    ("pm_1", "pm_1"), ({"id": "pm_obj"}, "pm_obj"), (None, None), ("", None),
])
def test_payment_method_for_intent(stripe, cs, pm, expected):
    stripe.PaymentIntent.result = {"id": "pi_1", "payment_method": pm}
    assert run(cs.payment_method_for_intent("pi_1")) == expected


def test_saved_card_for_customer_takes_the_most_recent_card(stripe, cs):
    assert run(cs.saved_card_for_customer("cus_1")) == "pm_listed"
    assert stripe.PaymentMethod.calls[0][2] == {"customer": "cus_1", "type": "card", "limit": 1}
    stripe.PaymentMethod.result = {"data": []}
    assert run(cs.saved_card_for_customer("cus_1")) is None


def test_card_fingerprint(stripe, cs):
    assert run(cs.card_fingerprint("pm_1")) == "fp_1"
    stripe.PaymentMethod.result = {"card": None}
    assert run(cs.card_fingerprint("pm_1")) is None


@pytest.mark.parametrize("call", [
    lambda cs: cs.payment_method_for_intent("pi_1"),
    lambda cs: cs.saved_card_for_customer("cus_1"),
    lambda cs: cs.card_fingerprint("pm_1"),
])
def test_lookup_failures_are_stripe_errors(stripe, cs, call):
    stripe.PaymentIntent.exc = stripe.PaymentMethod.exc = RuntimeError("down")
    with pytest.raises(CappeStripeError):
        run(call(cs))


# ── platform checkout sessions ───────────────────────────────────────────────

def test_an_open_platform_session_is_expired(stripe, cs):
    stripe.checkout.Session.result = lambda name, a, k: {"status": "open" if name == "retrieve" else "expired"}
    assert run(cs.expire_platform_checkout_session("cs_1")) == "expired"
    assert [c[0] for c in stripe.checkout.Session.calls] == ["retrieve", "expire"]
    # No stripe_account: this is OUR account, not a connected one.
    assert all("stripe_account" not in c[2] for c in stripe.checkout.Session.calls)


def test_a_completed_platform_session_is_reported_not_expired(stripe, cs):
    stripe.checkout.Session.result = {"status": "complete"}
    assert run(cs.expire_platform_checkout_session("cs_1")) == "complete"
    assert [c[0] for c in stripe.checkout.Session.calls] == ["retrieve"]


def test_platform_session_errors_are_stripe_errors(stripe, cs):
    stripe.checkout.Session.exc = RuntimeError("down")
    with pytest.raises(CappeStripeError):
        run(cs.expire_platform_checkout_session("cs_1"))
    with pytest.raises(CappeStripeError):
        run(cs.retrieve_platform_checkout_session("cs_1"))


def test_retrieve_platform_checkout_session(stripe, cs):
    assert run(cs.retrieve_platform_checkout_session("cs_1"))["id"] == "cs_1"


def test_a_short_lived_platform_session_sets_expires_at(stripe, cs, monkeypatch):
    monkeypatch.setattr(sc.time, "time", lambda: 1_000_000)
    run(cs.create_platform_checkout_session(
        currency="usd", line_items=[], success_url="s", cancel_url="c", metadata={},
        save_card=True, expires_in_seconds=3600,
    ))
    kwargs = stripe.checkout.Session.calls[0][2]
    assert kwargs["expires_at"] == 1_003_600
    assert kwargs["payment_intent_data"]["setup_future_usage"] == "off_session"


def test_stripes_thirty_minute_floor_is_respected(stripe, cs, monkeypatch):
    monkeypatch.setattr(sc.time, "time", lambda: 1_000_000)
    run(cs.create_platform_checkout_session(
        currency="usd", line_items=[], success_url="s", cancel_url="c", metadata={},
        expires_in_seconds=60,
    ))
    assert stripe.checkout.Session.calls[0][2]["expires_at"] == 1_001_800


def test_the_default_platform_session_keeps_stripes_lifetime(stripe, cs):
    run(cs.create_platform_checkout_session(
        currency="usd", line_items=[], success_url="s", cancel_url="c", metadata={},
    ))
    assert "expires_at" not in stripe.checkout.Session.calls[0][2]


# ── refunding an invoice (the duplicate-subscription case) ───────────────────

def test_refund_invoice_refunds_each_paid_payment(stripe, cs):
    stripe.InvoicePayment.result = {"data": [
        {"status": "paid", "payment": {"payment_intent": "pi_a"}},
        {"status": "open", "payment": {"payment_intent": "pi_unpaid"}},
        {"status": "paid", "payment": {}},
    ]}
    assert run(cs.refund_invoice("in_1")) == ["re_1"]
    assert stripe.Refund.calls[0][2] == {"payment_intent": "pi_a",
                                         "idempotency_key": "cappe-invoice-refund-pi_a"}
    assert stripe.Invoice.calls == []                    # no need for the legacy field


def test_refund_invoice_falls_back_to_the_legacy_field(stripe, cs):
    assert run(cs.refund_invoice("in_1")) == ["re_1"]
    assert stripe.Refund.calls[0][2]["payment_intent"] == "pi_legacy"


def test_refund_invoice_works_on_an_sdk_without_invoice_payments(stripe, cs):
    del stripe.InvoicePayment
    assert run(cs.refund_invoice("in_1")) == ["re_1"]


def test_an_invoice_with_nothing_paid_refunds_nothing(stripe, cs):
    stripe.Invoice.result = {"payment_intent": None}
    assert run(cs.refund_invoice("in_1")) == []
    assert stripe.Refund.calls == []


def test_refund_invoice_errors_are_stripe_errors(stripe, cs):
    stripe.Refund.exc = RuntimeError("down")
    with pytest.raises(CappeStripeError):
        run(cs.refund_invoice("in_1"))


# ── add-ons are only real once paid ──────────────────────────────────────────

def test_adding_an_add_on_waits_for_its_invoice(stripe, cs):
    run(cs.add_subscription_item(subscription_id="sub_1", price_id="price_1", quantity=2))
    kwargs = stripe.SubscriptionItem.calls[0][2]
    assert kwargs["proration_behavior"] == "always_invoice"
    assert kwargs["payment_behavior"] == "pending_if_incomplete"


def test_increasing_an_add_on_waits_for_its_invoice_and_a_decrease_does_not(stripe, cs):
    run(cs.set_item_quantity(item_id="si_1", quantity=3, invoice_now=True))
    assert stripe.SubscriptionItem.calls[0][2]["payment_behavior"] == "pending_if_incomplete"
    run(cs.set_item_quantity(item_id="si_1", quantity=1, invoice_now=False))
    decrease = stripe.SubscriptionItem.calls[1][2]
    assert decrease["proration_behavior"] == "create_prorations" and "payment_behavior" not in decrease
