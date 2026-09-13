import asyncio
from types import SimpleNamespace
from uuid import uuid4

from app.core.services import stripe_service as stripe_module


def test_custom_product_checkout_carries_location_billing_quantity(monkeypatch):
    captured = {}

    def create_session(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(id="cs_test", url="https://checkout.example.com")

    fake_stripe = SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(create=create_session))
    )
    monkeypatch.setattr(stripe_module, "stripe", fake_stripe)

    service = stripe_module.StripeService.__new__(stripe_module.StripeService)
    service.settings = SimpleNamespace(
        stripe_success_url="https://example.com/success",
        stripe_cancel_url="https://example.com/cancel",
    )
    monkeypatch.setattr(service, "_ensure_secret_key", lambda: None)

    asyncio.run(
        service.create_custom_product_checkout(
            company_id=uuid4(),
            product_slug="safety-pro",
            product_name="Safety Pro",
            product_description="",
            headcount=40,
            location_count=3,
            amount_cents=7500,
        )
    )

    assert captured["metadata"]["location_count"] == "3"
    assert captured["metadata"]["headcount"] == "40"
    assert captured["line_items"][0]["price_data"]["unit_amount"] == 7500
