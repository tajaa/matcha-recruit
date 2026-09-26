"""Personal checkout keeps Lite until a successful Pro activation."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.routes.billing import stripe_webhook as webhook
from app.core.services.stripe_service import StripeServiceError
from app.core.services.stripe_service import StripeService
from app.matcha.routes.work import billing as routes
from app.matcha.services.billing import billing_service, entitlements_service, token_budget_service


@pytest.mark.asyncio
async def test_personal_checkout_carries_upgrade_intent_in_stripe_metadata():
    created = {}

    def create_session(**kwargs):
        created.update(kwargs)
        return SimpleNamespace(id="cs_pro", url="https://checkout.stripe.com/cs_pro")

    fake_stripe = SimpleNamespace(checkout=SimpleNamespace(Session=SimpleNamespace(create=create_session)))
    with patch("app.core.services.stripe_service.get_settings", return_value=SimpleNamespace()):
        service = StripeService()
    with (
        patch.object(service, "_ensure_secret_key"),
        patch("app.core.services.stripe_service.stripe", fake_stripe),
    ):
        await service.create_personal_subscription_checkout(
            company_id=uuid4(), user_id=uuid4(), plan="pro",
            success_url="https://example.com/espresso?upgraded=1",
            cancel_url="https://example.com/espresso?canceled=1",
            upgrade_from_subscription_id="sub_lite",
        )

    assert created["metadata"]["upgrade_from_subscription_id"] == "sub_lite"
    assert created["subscription_data"]["metadata"]["upgrade_from_subscription_id"] == "sub_lite"


@pytest.mark.asyncio
async def test_period_end_reads_current_stripe_subscription_item():
    fake_stripe = SimpleNamespace(Subscription=SimpleNamespace(retrieve=lambda _id: {
        "items": {"data": [{"current_period_end": 1_800_000_000}]},
    }))
    with patch("app.core.services.stripe_service.get_settings", return_value=SimpleNamespace()):
        service = StripeService()
    with (
        patch.object(service, "_ensure_secret_key"),
        patch("app.core.services.stripe_service.stripe", fake_stripe),
    ):
        assert await service.get_subscription_period_end("sub_lite") == 1_800_000_000


@pytest.mark.asyncio
async def test_lite_upgrade_keeps_old_subscription_until_checkout_completes():
    user = SimpleNamespace(id=uuid4(), role="individual")
    company_id = uuid4()
    stripe = SimpleNamespace(
        PERSONAL_PLANS={"pro": {"pack_id": entitlements_service.PRO_PACK_ID, "amount_cents": 2000}},
        create_personal_subscription_checkout=AsyncMock(return_value=SimpleNamespace(
            id="cs_pro", url="https://checkout.stripe.com/cs_pro",
        )),
        cancel_subscription=AsyncMock(),
    )
    old = {"pack_id": entitlements_service.LITE_PACK_ID, "stripe_subscription_id": "sub_lite"}
    with (
        patch.object(routes, "get_client_company_id", AsyncMock(return_value=company_id)),
        patch.object(billing_service, "get_active_subscription", AsyncMock(return_value=old)),
        patch.object(billing_service, "create_pending_stripe_session", AsyncMock()),
        patch.object(billing_service, "cancel_subscription_record", AsyncMock()) as cancel_record,
        patch.object(routes, "StripeService", return_value=stripe),
    ):
        result = await routes.create_personal_checkout_session(
            routes.PersonalCheckoutRequest(plan="pro"), user,
        )

    assert result.stripe_session_id == "cs_pro"
    assert stripe.create_personal_subscription_checkout.await_args.kwargs["upgrade_from_subscription_id"] == "sub_lite"
    stripe.cancel_subscription.assert_not_awaited()
    cancel_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_pro_checkout_does_not_cancel_lite():
    user = SimpleNamespace(id=uuid4(), role="individual")
    stripe = SimpleNamespace(
        PERSONAL_PLANS={"pro": {"pack_id": entitlements_service.PRO_PACK_ID, "amount_cents": 2000}},
        create_personal_subscription_checkout=AsyncMock(side_effect=StripeServiceError("Stripe unavailable")),
        cancel_subscription=AsyncMock(),
    )
    old = {"pack_id": entitlements_service.LITE_PACK_ID, "stripe_subscription_id": "sub_lite"}
    with (
        patch.object(routes, "get_client_company_id", AsyncMock(return_value=uuid4())),
        patch.object(billing_service, "get_active_subscription", AsyncMock(return_value=old)),
        patch.object(billing_service, "cancel_subscription_record", AsyncMock()) as cancel_record,
        patch.object(routes, "StripeService", return_value=stripe),
    ):
        with pytest.raises(HTTPException) as exc:
            await routes.create_personal_checkout_session(routes.PersonalCheckoutRequest(plan="pro"), user)

    assert exc.value.status_code == 400
    stripe.cancel_subscription.assert_not_awaited()
    cancel_record.assert_not_awaited()


def _pro_checkout_event(company_id):
    return {
        "id": "cs_pro",
        "mode": "subscription",
        "subscription": "sub_pro",
        "customer": "cus_pro",
        "metadata": {
            "company_id": str(company_id),
            "pack_id": entitlements_service.PRO_PACK_ID,
            "amount_cents": "2000",
            "billing_type": "token_budget",
            "tokens_per_cycle": "1000000",
            "upgrade_from_subscription_id": "sub_lite",
        },
    }


@pytest.mark.asyncio
async def test_paid_pro_webhook_records_pro_before_canceling_lite():
    company_id = uuid4()
    calls = []

    async def record_pro(**kwargs):
        calls.append("record_pro")
        assert kwargs["current_period_end"] == datetime.fromtimestamp(1_800_000_000, timezone.utc)

    async def cancel_lite(_id):
        calls.append("cancel_lite")

    stripe = SimpleNamespace(
        get_subscription_period_end=AsyncMock(return_value=1_800_000_000),
        cancel_subscription=AsyncMock(side_effect=cancel_lite),
    )
    old = {
        "company_id": company_id,
        "pack_id": entitlements_service.LITE_PACK_ID,
        "status": "active",
    }
    with (
        patch.object(webhook, "StripeService", return_value=stripe),
        patch.object(billing_service, "upsert_subscription", AsyncMock(side_effect=record_pro)),
        patch.object(billing_service, "get_subscription_by_stripe_id", AsyncMock(return_value=old)),
        patch.object(billing_service, "cancel_subscription_record", AsyncMock()) as cancel_record,
        patch.object(token_budget_service, "reset_subscription_tokens", AsyncMock()),
        patch.object(entitlements_service, "invalidate_plan_cache", MagicMock()),
    ):
        await webhook._route_event("checkout.session.completed", _pro_checkout_event(company_id))

    assert calls == ["record_pro", "cancel_lite"]
    cancel_record.assert_awaited_once_with(
        "sub_lite", current_period_end=datetime.fromtimestamp(1_800_000_000, timezone.utc),
    )


@pytest.mark.asyncio
async def test_failed_lite_cancellation_retries_paid_pro_webhook():
    company_id = uuid4()
    stripe = SimpleNamespace(
        get_subscription_period_end=AsyncMock(return_value=1_800_000_000),
        cancel_subscription=AsyncMock(side_effect=StripeServiceError("Stripe unavailable")),
    )
    old = {"company_id": company_id, "pack_id": entitlements_service.LITE_PACK_ID, "status": "active"}
    with (
        patch.object(webhook, "StripeService", return_value=stripe),
        patch.object(billing_service, "upsert_subscription", AsyncMock()),
        patch.object(billing_service, "get_subscription_by_stripe_id", AsyncMock(return_value=old)),
        patch.object(billing_service, "cancel_subscription_record", AsyncMock()) as cancel_record,
        patch.object(token_budget_service, "reset_subscription_tokens", AsyncMock()) as reset_tokens,
    ):
        with pytest.raises(StripeServiceError):
            await webhook._route_event("checkout.session.completed", _pro_checkout_event(company_id))

    cancel_record.assert_not_awaited()
    reset_tokens.assert_not_awaited()


@pytest.mark.asyncio
async def test_canceled_personal_subscription_keeps_paid_through_status():
    user = SimpleNamespace(id=uuid4(), role="individual")
    company_id = uuid4()
    period_end = datetime.fromtimestamp(1_800_000_000, timezone.utc)
    canceled = {
        "status": "canceled",
        "pack_id": entitlements_service.LITE_PACK_ID,
        "amount_cents": 900,
        "current_period_end": period_end,
        "canceled_at": datetime.now(timezone.utc),
    }
    with (
        patch.object(routes, "get_client_company_id", AsyncMock(return_value=company_id)),
        patch.object(billing_service, "get_current_personal_subscription", AsyncMock(return_value=canceled)),
    ):
        result = await routes.get_subscription(user)

    assert result.active is False
    assert result.status == "canceled"
    assert result.current_period_end == period_end


@pytest.mark.asyncio
async def test_personal_cancel_preserves_budget_and_records_period_end():
    user = SimpleNamespace(id=uuid4(), role="individual")
    company_id = uuid4()
    stripe = SimpleNamespace(
        get_subscription_period_end=AsyncMock(return_value=1_800_000_000),
        cancel_subscription=AsyncMock(),
    )
    old = {"pack_id": entitlements_service.LITE_PACK_ID, "stripe_subscription_id": "sub_lite"}
    with (
        patch.object(routes, "get_client_company_id", AsyncMock(return_value=company_id)),
        patch.object(routes, "StripeService", return_value=stripe),
        patch.object(billing_service, "get_active_subscription", AsyncMock(return_value=old)),
        patch.object(billing_service, "cancel_subscription_record", AsyncMock()) as cancel_record,
        patch.object(token_budget_service, "cancel_subscription_budget", AsyncMock()) as cancel_budget,
    ):
        result = await routes.cancel_subscription(user)

    assert result["canceled"] is True
    cancel_record.assert_awaited_once_with(
        "sub_lite", current_period_end=datetime.fromtimestamp(1_800_000_000, timezone.utc),
    )
    cancel_budget.assert_not_awaited()
