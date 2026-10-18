"""Checkout delegates payment-method selection to the Stripe Dashboard."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from app.core.services import stripe_service
from app.werk.services import channel_job_posting_service, channel_links, channel_payment_service


COMPANY_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")
SUCCESS_URL = "https://example.com/success"
CANCEL_URL = "https://example.com/cancel"


@pytest.fixture
def checkout(monkeypatch):
    session = SimpleNamespace(id="cs_test", url="https://checkout.example.com/session")
    create = Mock(return_value=session)
    fake_stripe = SimpleNamespace(
        checkout=SimpleNamespace(Session=SimpleNamespace(create=create))
    )
    settings = SimpleNamespace(
        stripe_secret_key="sk_test_placeholder",
        stripe_success_url=SUCCESS_URL,
        stripe_cancel_url=CANCEL_URL,
        app_base_url="https://example.com",
    )
    for module in (stripe_service, channel_payment_service, channel_job_posting_service):
        monkeypatch.setattr(module, "stripe", fake_stripe)
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(
        channel_links, "resolve_channel_app_path", AsyncMock(return_value="/work/channels/test")
    )
    return create, session


@pytest.mark.parametrize(
    "method, kwargs, mode",
    [
        ("create_checkout_session", {"company_id": COMPANY_ID, "pack_id": "twenty"}, "payment"),
        (
            "create_subscription_checkout_session",
            {"company_id": COMPANY_ID, "pack_id": "twenty"},
            "subscription",
        ),
        (
            "create_personal_subscription_checkout",
            {"company_id": COMPANY_ID, "user_id": USER_ID, "amount_cents": 2000},
            "subscription",
        ),
        ("create_ir_upgrade_checkout", {"company_id": COMPANY_ID}, "subscription"),
        (
            "create_matcha_lite_checkout",
            {"company_id": COMPANY_ID, "headcount": 40, "amount_cents": 7500},
            "subscription",
        ),
        (
            "create_tellus_brand_checkout",
            {"brand_id": COMPANY_ID, "location_count": 3, "amount_cents": 7500},
            "subscription",
        ),
        (
            "create_lite_addon_checkout",
            {
                "company_id": COMPANY_ID,
                "addon_key": "handbook_watch",
                "addon_name": "Handbook Watch",
                "addon_description": "Handbook freshness checks",
                "headcount": 40,
                "amount_cents": 7500,
            },
            "subscription",
        ),
        (
            "create_custom_product_checkout",
            {
                "company_id": COMPANY_ID,
                "product_slug": "matcha-sc",
                "product_name": "Matcha S&C",
                "product_description": "",
                "headcount": 40,
                "location_count": 3,
                "amount_cents": 7500,
            },
            "subscription",
        ),
        (
            "create_lite_essentials_upgrade_checkout",
            {
                "company_id": COMPANY_ID,
                "headcount": 40,
                "amount_cents": 7500,
                "old_subscription_id": "sub_essentials",
            },
            "subscription",
        ),
        (
            "create_matcha_x_checkout",
            {"company_id": COMPANY_ID, "headcount": 40},
            "subscription",
        ),
        (
            "create_matcha_compliance_checkout",
            {
                "company_id": COMPANY_ID,
                "headcount": 40,
                "jurisdiction_count": 3,
                "amount_cents": 7500,
            },
            "subscription",
        ),
        ("create_recruiter_tier_checkout", {"user_id": USER_ID}, "subscription"),
        ("create_token_subscription_checkout", {"company_id": COMPANY_ID}, "subscription"),
    ],
    ids=lambda value: value if isinstance(value, str) and value.startswith("create_") else None,
)
def test_core_checkout_uses_dashboard_payment_methods(checkout, method, kwargs, mode):
    create, session = checkout
    service = stripe_service.StripeService()

    result = asyncio.run(
        getattr(service, method)(**kwargs, success_url=SUCCESS_URL, cancel_url=CANCEL_URL)
    )

    assert result is session
    create.assert_called_once()
    payload = create.call_args.kwargs
    assert "payment_method_types" not in payload
    assert payload["mode"] == mode
    assert payload["success_url"] == SUCCESS_URL
    assert payload["cancel_url"] == CANCEL_URL
    assert payload["line_items"]
    assert payload["metadata"]
    if mode == "subscription":
        assert payload["subscription_data"]["metadata"] == payload["metadata"]


@pytest.mark.parametrize(
    "module, method, kwargs, mode, metadata_type",
    [
        (
            channel_payment_service,
            "create_checkout_session",
            {
                "channel_id": COMPANY_ID,
                "channel_name": "Test channel",
                "stripe_price_id": "price_test",
                "user_id": USER_ID,
            },
            "subscription",
            "channel_subscription",
        ),
        (
            channel_payment_service,
            "create_tip_checkout",
            {
                "channel_id": COMPANY_ID,
                "channel_name": "Test channel",
                "sender_id": USER_ID,
                "creator_id": COMPANY_ID,
                "amount_cents": 500,
            },
            "payment",
            "channel_tip",
        ),
        (
            channel_job_posting_service,
            "create_job_posting_checkout",
            {
                "posting_id": COMPANY_ID,
                "channel_id": COMPANY_ID,
                "user_id": USER_ID,
                "stripe_price_id": "price_test",
            },
            "subscription",
            "job_posting_subscription",
        ),
    ],
    ids=["channel_subscription", "channel_tip", "job_posting_subscription"],
)
def test_channel_checkout_uses_dashboard_payment_methods(
    checkout, module, method, kwargs, mode, metadata_type
):
    create, session = checkout

    result = asyncio.run(getattr(module, method)(**kwargs))

    assert result == session.url
    create.assert_called_once()
    payload = create.call_args.kwargs
    assert "payment_method_types" not in payload
    assert payload["mode"] == mode
    assert payload["metadata"]["type"] == metadata_type
    assert payload["line_items"]
    if mode == "subscription":
        assert payload["subscription_data"]["metadata"] == payload["metadata"]
