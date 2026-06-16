"""Cappe Stripe Connect — business onboarding + storefront payment webhook.

Two authed endpoints let a business connect/refresh its Stripe account, plus one
public webhook the Connect endpoint posts to. Storefront Checkout Sessions
themselves are created in `public.py` (the checkout flow); this router owns
onboarding + the paid-order webhook.
"""

from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount
from ..services.email import dashboard_url
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger("cappe.payments")

router = APIRouter()


class ConnectLinkRequest(BaseModel):
    return_url: Optional[str] = None
    refresh_url: Optional[str] = None


class ConnectLinkResponse(BaseModel):
    url: str


class ConnectStatusResponse(BaseModel):
    connected: bool
    charges_enabled: bool
    details_submitted: bool


@router.post("/payments/connect", response_model=ConnectLinkResponse)
async def connect_account(
    body: ConnectLinkRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Create (or reuse) the caller's connected Stripe account and return a
    hosted onboarding link. The business finishes setup on Stripe, then returns."""
    cs = get_cappe_stripe()
    async with get_connection() as conn:
        acct_id = await conn.fetchval(
            "SELECT stripe_account_id FROM cappe_accounts WHERE id = $1", account.id
        )
        if not acct_id:
            try:
                acct_id = await cs.create_connected_account(account.email)
            except CappeStripeError as exc:
                raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
            await conn.execute(
                "UPDATE cappe_accounts SET stripe_account_id = $1, updated_at = NOW() WHERE id = $2",
                acct_id, account.id,
            )

    return_url = body.return_url or dashboard_url("/sites")
    refresh_url = body.refresh_url or return_url
    try:
        link = await cs.create_account_link(acct_id, refresh_url, return_url)
    except CappeStripeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return {"url": link["url"]}


@router.get("/payments/status", response_model=ConnectStatusResponse)
async def connect_status(account: CappeAccount = Depends(require_cappe_account)):
    """Report whether the caller can accept card payments. Refreshes the cached
    capability flags from Stripe so the UI reflects completed onboarding."""
    cs = get_cappe_stripe()
    async with get_connection() as conn:
        acct_id = await conn.fetchval(
            "SELECT stripe_account_id FROM cappe_accounts WHERE id = $1", account.id
        )
        if not acct_id:
            return {"connected": False, "charges_enabled": False, "details_submitted": False}
        try:
            acct = await cs.retrieve_account(acct_id)
        except CappeStripeError:
            return {"connected": True, "charges_enabled": False, "details_submitted": False}
        charges = bool(acct.get("charges_enabled"))
        details = bool(acct.get("details_submitted"))
        await conn.execute(
            "UPDATE cappe_accounts SET stripe_charges_enabled = $1, stripe_details_submitted = $2, "
            "updated_at = NOW() WHERE id = $3",
            charges, details, account.id,
        )
    return {"connected": True, "charges_enabled": charges, "details_submitted": details}


@router.post("/payments/webhook")
async def payments_webhook(request: Request):
    """Stripe Connect webhook. Verifies the signature, then:
      - checkout.session.completed → mark the order paid (+ payment intent, fee).
      - account.updated            → refresh the business's capability flags.
    Always returns 200 on handled events so Stripe stops retrying."""
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    cs = get_cappe_stripe()
    try:
        event = await cs.verify_webhook(payload, signature)
    except CappeStripeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    etype = event.get("type")
    obj = event.get("data", {}).get("object", {}) or {}

    if etype == "checkout.session.completed":
        meta = obj.get("metadata") or {}
        order_id = meta.get("order_id")
        # Connect events all land on this one endpoint; require the event's
        # connected account to own the order before mutating it — otherwise a
        # malicious connected business could send a (validly-signed) event on
        # their own account carrying another business's order_id.
        event_account_id = event.get("account")
        try:
            oid = UUID(str(order_id)) if order_id else None
        except (ValueError, TypeError):
            oid = None
        if oid is not None and event_account_id:
            payment_intent = obj.get("payment_intent")
            fee = None
            try:
                fee = meta.get("platform_fee_cents")
                fee = int(fee) if fee is not None else None
            except (TypeError, ValueError):
                fee = None
            async with get_connection() as conn:
                row = await conn.fetchrow(
                    """UPDATE cappe_orders o
                          SET status = 'paid', paid_at = NOW(),
                              stripe_payment_intent = $2, payment_ref = $2,
                              platform_fee_cents = COALESCE($3, platform_fee_cents),
                              updated_at = NOW()
                        FROM cappe_sites s, cappe_accounts a
                        WHERE o.id = $1 AND o.status = 'pending'
                          AND s.id = o.site_id AND a.id = s.account_id
                          AND a.stripe_account_id = $4
                        RETURNING o.id, o.site_id, o.customer_email, o.customer_name""",
                    oid, payment_intent, fee, event_account_id,
                )
            if row is not None:
                # Phase 2 (receipts) hooks here: generate + email the PDF receipt.
                logger.info("cappe order %s marked paid via Stripe", order_id)
            else:
                logger.warning(
                    "cappe webhook: order %s not matched to event account %s (ignored)",
                    order_id, event_account_id,
                )

    elif etype == "account.updated":
        acct_id = obj.get("id") or event.get("account")
        if acct_id:
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE cappe_accounts SET stripe_charges_enabled = $1, "
                    "stripe_details_submitted = $2, updated_at = NOW() WHERE stripe_account_id = $3",
                    bool(obj.get("charges_enabled")), bool(obj.get("details_submitted")), acct_id,
                )

    return {"received": True}
