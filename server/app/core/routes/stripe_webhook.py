"""Stripe webhook routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from ..services.stripe_service import StripeService, StripeServiceError
from ...matcha.services import billing_service
from ...matcha.services import token_budget_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stripe-webhooks"])


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    if not signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Stripe signature",
        )

    stripe_service = StripeService()
    try:
        event = await stripe_service.verify_webhook(payload, signature)
    except StripeServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    event_type = str(event.get("type") or "")
    event_object = event.get("data", {}).get("object", {})

    # ── Route channel-specific events via metadata ─────────────────────────
    meta = event_object.get("metadata") or {}
    is_channel_event = meta.get("type") == "channel_subscription"

    # ── One-time checkout completed ───────────────────────────────────────────
    if event_type == "checkout.session.completed":
        session_mode = str(event_object.get("mode") or "payment")
        stripe_session_id = str(event_object.get("id") or "")

        if session_mode == "payment":
            if not stripe_session_id:
                return {"received": True}
            fulfillment = await billing_service.fulfill_checkout_session(stripe_session_id)
            if fulfillment is None:
                logger.warning("Stripe session %s not found during fulfillment", stripe_session_id)
            elif fulfillment.get("already_fulfilled"):
                logger.info("Stripe session %s already fulfilled", stripe_session_id)
            else:
                logger.info(
                    "Stripe one-time session %s fulfilled (company %s)",
                    stripe_session_id,
                    fulfillment.get("session", {}).get("company_id", "?"),
                )

        elif session_mode == "subscription" and is_channel_event:
            # ── Channel subscription checkout ────────────────────────────
            channel_id_str = meta.get("channel_id") or ""
            user_id_str = meta.get("user_id") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")

            if channel_id_str and user_id_str and stripe_sub_id:
                try:
                    from ..services.channel_payment_service import handle_subscription_activated
                    import asyncio
                    import stripe as _stripe
                    _stripe.api_key = StripeService().settings.stripe_secret_key
                    sub = await asyncio.to_thread(_stripe.Subscription.retrieve, stripe_sub_id)
                    await handle_subscription_activated(
                        channel_id=UUID(channel_id_str),
                        user_id=UUID(user_id_str),
                        stripe_subscription_id=stripe_sub_id,
                        current_period_end=sub.current_period_end,
                    )
                    logger.info("Channel subscription activated: %s for user %s", stripe_sub_id, user_id_str)
                except Exception as exc:
                    logger.error("Failed to activate channel subscription: %s", exc)

        elif session_mode == "subscription":
            meta = event_object.get("metadata") or {}
            company_id_str = meta.get("company_id") or ""
            pack_id = meta.get("pack_id") or ""
            billing_type = meta.get("billing_type") or ""
            tokens_per_cycle = int(meta.get("tokens_per_cycle") or "0")
            stripe_sub_id = str(event_object.get("subscription") or "")
            stripe_customer_id = str(event_object.get("customer") or "")

            if company_id_str and pack_id and stripe_sub_id:
                try:
                    company_id = UUID(company_id_str)

                    # Record subscription in mw_subscriptions
                    await billing_service.upsert_subscription(
                        company_id=company_id,
                        stripe_subscription_id=stripe_sub_id,
                        stripe_customer_id=stripe_customer_id,
                        pack_id=pack_id,
                        credits_per_cycle=0,
                        amount_cents=token_budget_service.SUBSCRIPTION_AMOUNT_CENTS,
                    )

                    # Activate token budget
                    if billing_type == "token_budget" and tokens_per_cycle > 0:
                        await token_budget_service.reset_subscription_tokens(
                            company_id, token_limit=tokens_per_cycle,
                        )
                        logger.info(
                            "Token subscription activated for company %s: %d tokens/month",
                            company_id_str, tokens_per_cycle,
                        )
                    else:
                        logger.info("Subscription %s recorded for company %s", stripe_sub_id, company_id_str)

                except Exception as exc:
                    logger.error("Failed to record subscription %s: %s", stripe_sub_id, exc)

    # ── Checkout expired ──────────────────────────────────────────────────────
    elif event_type == "checkout.session.expired":
        stripe_session_id = str(event_object.get("id") or "")
        if stripe_session_id:
            await billing_service.mark_stripe_session_expired(stripe_session_id)
            logger.info("Stripe session %s marked expired", stripe_session_id)

    # ── Invoice payment failed ─────────────────────────────────────────────
    elif event_type == "invoice.payment_failed":
        stripe_sub_id = str(event_object.get("subscription") or "")
        if stripe_sub_id:
            # Only handle for channel subscriptions (safe no-op if not found)
            try:
                from ..services.channel_payment_service import handle_payment_failed
                await handle_payment_failed(stripe_sub_id)
            except Exception as exc:
                logger.error("Channel payment failure handler error: %s", exc)

    # ── Monthly invoice paid → reset token budget ────────────────────────────
    elif event_type == "invoice.paid":
        stripe_sub_id = str(event_object.get("subscription") or "")
        stripe_invoice_id = str(event_object.get("id") or "")
        billing_reason = str(event_object.get("billing_reason") or "")

        if stripe_sub_id and stripe_invoice_id and billing_reason == "subscription_cycle":
            # Check if this is a channel subscription renewal
            try:
                from ..services.channel_payment_service import handle_subscription_renewed
                from ...database import get_connection as _get_conn
                async with _get_conn() as _conn:
                    is_channel_sub = await _conn.fetchval(
                        "SELECT EXISTS(SELECT 1 FROM channel_members WHERE stripe_subscription_id = $1)",
                        stripe_sub_id,
                    )
                if is_channel_sub:
                    amount = int(event_object.get("amount_paid") or 0)
                    # Get period end from subscription lines
                    lines = event_object.get("lines", {}).get("data", [])
                    period_end = lines[0]["period"]["end"] if lines else None
                    if period_end and period_end > 0:
                        await handle_subscription_renewed(stripe_sub_id, period_end, amount)
                        logger.info("Channel subscription renewed: %s", stripe_sub_id)
                    else:
                        logger.warning("Channel subscription renewal %s missing period end", stripe_sub_id)
            except Exception as exc:
                logger.error("Channel subscription renewal error: %s", exc)

            # Look up the subscription to check if it's a token subscription
            sub = await billing_service.get_subscription_by_stripe_id(stripe_sub_id)
            if sub and sub["pack_id"] == token_budget_service.SUBSCRIPTION_PACK_ID:
                await token_budget_service.reset_subscription_tokens(
                    sub["company_id"],
                    token_limit=token_budget_service.SUBSCRIPTION_TOKENS,
                    stripe_invoice_id=stripe_invoice_id,
                )
                logger.info(
                    "Token subscription renewed: invoice %s, company %s",
                    stripe_invoice_id, sub["company_id"],
                )
            else:
                # Legacy dollar-credit subscription
                result = await billing_service.fulfill_subscription_invoice(
                    stripe_subscription_id=stripe_sub_id,
                    stripe_invoice_id=stripe_invoice_id,
                )
                if result and not result.get("already_fulfilled"):
                    logger.info("Legacy subscription invoice %s fulfilled", stripe_invoice_id)

    # ── Subscription canceled / deleted ──────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        stripe_sub_id = str(event_object.get("id") or "")
        if stripe_sub_id:
            # Handle channel subscription cancellation
            try:
                from ..services.channel_payment_service import handle_subscription_canceled
                await handle_subscription_canceled(stripe_sub_id)
            except Exception as exc:
                logger.error("Channel subscription cancellation error: %s", exc)

            # Fetch before canceling to get company_id and pack_id
            sub = await billing_service.get_subscription_by_stripe_id(stripe_sub_id)
            canceled = await billing_service.cancel_subscription_record(stripe_sub_id)
            if canceled:
                logger.info("Subscription %s marked canceled", stripe_sub_id)
                if sub and sub["pack_id"] == token_budget_service.SUBSCRIPTION_PACK_ID:
                    await token_budget_service.cancel_subscription_budget(sub["company_id"])
                    logger.info("Token budget zeroed for company %s", sub["company_id"])

    return {"received": True}
