"""Stripe webhook routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, status

from ..services.stripe_service import StripeService, StripeServiceError
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
    stripe_session_id = str(event_object.get("id") or "")

    if not stripe_session_id:
        logger.info("Stripe webhook received without session id for event type %s", event_type)
        return {"received": True}

    if event_type == "checkout.session.completed":
        fulfillment = await billing_service.fulfill_checkout_session(stripe_session_id)
        if fulfillment is None:
            logger.warning("Stripe session %s not found during fulfillment", stripe_session_id)
        elif fulfillment.get("already_fulfilled"):
            logger.info("Stripe session %s was already fulfilled (duplicate webhook)", stripe_session_id)
        else:
            credits_added = fulfillment.get("transaction", {}).get("credits_delta", "?")
            new_balance = fulfillment.get("balance", {}).get("credits_remaining", "?")
            logger.info(
                "Stripe session %s fulfilled: +%s credits, new balance %s (company %s)",
                stripe_session_id,
                credits_added,
                new_balance,
                fulfillment.get("session", {}).get("company_id", "?"),
            )
    elif event_type == "checkout.session.expired":
        await billing_service.mark_stripe_session_expired(stripe_session_id)
        logger.info("Stripe session %s marked expired", stripe_session_id)

    return {"received": True}
