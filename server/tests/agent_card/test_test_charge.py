from types import SimpleNamespace
from uuid import uuid4

import pytest
import stripe

from app.matcha.services.matcha_work.agent_card import test_charge


@pytest.mark.parametrize("mode, key, expected", [
    (None, "sk_test_abc", "sk_test_abc"),           # default mode is stripe_test
    ("stripe_test", "rk_test_abc", "rk_test_abc"),
    ("handoff", "sk_test_abc", None),
    (None, "sk_live_abc", None),                    # never a live key
    (None, "rk_live_abc", None),
    (None, "", None),
])
def test_only_test_keys_ever_charge(monkeypatch, mode, key, expected):
    monkeypatch.delenv(test_charge.KEY_ENV, raising=False)
    if mode is None:
        monkeypatch.delenv(test_charge.MODE_ENV, raising=False)
    else:
        monkeypatch.setenv(test_charge.MODE_ENV, mode)
    monkeypatch.setenv("STRIPE_SECRET_KEY", key)
    assert test_charge.test_key() == expected


def test_dedicated_key_wins_over_the_app_key(monkeypatch):
    monkeypatch.delenv(test_charge.MODE_ENV, raising=False)
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_abc")
    monkeypatch.setenv(test_charge.KEY_ENV, "sk_test_dedicated")
    assert test_charge.test_key() == "sk_test_dedicated"


@pytest.mark.parametrize("amount, currency, expected", [
    (4.49, "usd", 449), (4.495, "USD", 450), (10, "eur", 1000), (1200, "jpy", 1200), ("9.5", "gbp", 950),
])
def test_minor_units(amount, currency, expected):
    assert test_charge.minor_units(amount, currency) == expected


@pytest.mark.asyncio
async def test_charge_uses_the_brands_test_method_and_the_purchase_as_idempotency_key(monkeypatch):
    seen = {}

    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(id="pi_test_1", status="succeeded")

    monkeypatch.setattr(stripe.PaymentIntent, "create", create)
    purchase = uuid4()
    out = await test_charge.charge(
        "sk_test_x", purchase_id=purchase, amount=4.49, currency="USD", brand="amex",
        description="Agent card test purchase: Balm", metadata={"purchase_id": purchase},
    )
    assert out == {"status": "test_charged", "payment_intent_id": "pi_test_1", "error": None}
    assert seen["api_key"] == "sk_test_x" and seen["idempotency_key"] == f"agent-purchase-{purchase}"
    assert seen["amount"] == 449 and seen["currency"] == "usd" and seen["payment_method"] == "pm_card_amex"
    assert seen["confirm"] is True and seen["metadata"] == {"purchase_id": str(purchase)}
    assert "4242" not in repr(seen)  # no card number is ever sent


@pytest.mark.asyncio
async def test_charge_reports_a_non_succeeded_intent_and_a_stripe_error(monkeypatch):
    monkeypatch.setattr(stripe.PaymentIntent, "create", lambda **k: SimpleNamespace(id="pi_2", status="requires_action"))
    out = await test_charge.charge("sk_test_x", purchase_id=uuid4(), amount=1, currency="usd", brand=None,
                                   description="d", metadata={})
    assert out["status"] == "test_failed" and out["payment_intent_id"] == "pi_2"

    def boom(**k):
        raise stripe.CardError("declined", param=None, code="card_declined")

    monkeypatch.setattr(stripe.PaymentIntent, "create", boom)
    out = await test_charge.charge("sk_test_x", purchase_id=uuid4(), amount=1, currency="usd", brand="visa",
                                   description="d", metadata={})
    assert out["status"] == "test_failed" and out["payment_intent_id"] is None and out["error"]
