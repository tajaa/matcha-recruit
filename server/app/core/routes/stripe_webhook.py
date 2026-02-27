"""Stripe webhook routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status

from ..services.stripe_service import StripeService, StripeServiceError, CREDIT_PACKS
from ...matcha.services import billing_service

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

    # ── One-time checkout completed ───────────────────────────────────────────
    if event_type == "checkout.session.completed":
        session_mode = str(event_object.get("mode") or "payment")
        stripe_session_id = str(event_object.get("id") or "")

        if session_mode == "payment":
            # One-time purchase — fulfill credits immediately
            if not stripe_session_id:
                return {"received": True}
            fulfillment = await billing_service.fulfill_checkout_session(stripe_session_id)
            if fulfillment is None:
                logger.warning("Stripe session %s not found during fulfillment", stripe_session_id)
            elif fulfillment.get("already_fulfilled"):
                logger.info("Stripe session %s already fulfilled", stripe_session_id)
            else:
                logger.info(
                    "Stripe one-time session %s fulfilled: +%s credits (company %s)",
                    stripe_session_id,
                    fulfillment.get("transaction", {}).get("credits_delta", "?"),
                    fulfillment.get("session", {}).get("company_id", "?"),
                )

        elif session_mode == "subscription":
            # Subscription created — record it; credits come via invoice.paid
            meta = event_object.get("metadata") or {}
            company_id_str = meta.get("company_id") or ""
            pack_id = meta.get("pack_id") or ""
            stripe_sub_id = str(event_object.get("subscription") or "")
            stripe_customer_id = str(event_object.get("customer") or "")

            if company_id_str and pack_id and stripe_sub_id:
                try:
                    company_id = UUID(company_id_str)
                    pack = CREDIT_PACKS.get(pack_id)
                    credits_per_cycle = int(pack["credits"]) if pack else 0
                    amount_cents = int(pack["amount_cents"]) if pack else 0

                    await billing_service.upsert_subscription(
                        company_id=company_id,
                        stripe_subscription_id=stripe_sub_id,
                        stripe_customer_id=stripe_customer_id,
                        pack_id=pack_id,
                        credits_per_cycle=credits_per_cycle,
                        amount_cents=amount_cents,
                    )
                    logger.info("Subscription %s recorded for company %s", stripe_sub_id, company_id_str)
                except Exception as exc:
                    logger.error("Failed to record subscription %s: %s", stripe_sub_id, exc)

    # ── Checkout expired ──────────────────────────────────────────────────────
    elif event_type == "checkout.session.expired":
        stripe_session_id = str(event_object.get("id") or "")
        if stripe_session_id:
            await billing_service.mark_stripe_session_expired(stripe_session_id)
            logger.info("Stripe session %s marked expired", stripe_session_id)

    # ── Monthly invoice paid → add credits ───────────────────────────────────
    elif event_type == "invoice.paid":
        stripe_sub_id = str(event_object.get("subscription") or "")
        stripe_invoice_id = str(event_object.get("id") or "")
        billing_reason = str(event_object.get("billing_reason") or "")

        # Skip initial invoice — credits are granted when subscription is recorded above
        if stripe_sub_id and stripe_invoice_id and billing_reason == "subscription_cycle":
            result = await billing_service.fulfill_subscription_invoice(
                stripe_subscription_id=stripe_sub_id,
                stripe_invoice_id=stripe_invoice_id,
            )
            if result is None:
                logger.warning("Subscription %s not found for invoice %s", stripe_sub_id, stripe_invoice_id)
            elif result.get("already_fulfilled"):
                logger.info("Invoice %s already fulfilled", stripe_invoice_id)
            else:
                logger.info(
                    "Auto-renewal fulfilled: invoice %s, subscription %s, +%s credits",
                    stripe_invoice_id,
                    stripe_sub_id,
                    result.get("transaction", {}).get("credits_delta", "?"),
                )

    # ── Subscription canceled / deleted ──────────────────────────────────────
    elif event_type == "customer.subscription.deleted":
        stripe_sub_id = str(event_object.get("id") or "")
        if stripe_sub_id:
            canceled = await billing_service.cancel_subscription_record(stripe_sub_id)
            if canceled:
                logger.info("Subscription %s marked canceled", stripe_sub_id)

    return {"received": True}
