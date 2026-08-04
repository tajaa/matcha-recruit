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

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.core.services.stripe_events import (
    CONSUMER_CAPPE_CONNECT,
    claim_stripe_event,
    release_stripe_event,
)

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount
from ..services.email import dashboard_url, send_cappe_collab_completed_email, send_cappe_collab_paid_email
from ..services.receipt import issue_receipt_for_paid_order
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
        # Connection released before the Stripe round-trip — see the module-wide
        # rule in sites.py:501-513 / locations.py:38-45: an external HTTP call
        # must never pin a pooled connection (pool is shared with matcha + tellus).
        try:
            acct_id = await cs.create_connected_account(account.email)
        except CappeStripeError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        async with get_connection() as conn:
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
    # Connection released before the Stripe round-trip — see connect_account.
    try:
        acct = await cs.retrieve_account(acct_id)
    except CappeStripeError:
        return {"connected": True, "charges_enabled": False, "details_submitted": False}
    charges = bool(acct.get("charges_enabled"))
    details = bool(acct.get("details_submitted"))
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE cappe_accounts SET stripe_charges_enabled = $1, stripe_details_submitted = $2, "
            "updated_at = NOW() WHERE id = $3",
            charges, details, account.id,
        )
    return {"connected": True, "charges_enabled": charges, "details_submitted": details}


@router.post("/payments/webhook")
async def payments_webhook(request: Request, background: BackgroundTasks):
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
    event_id = event.get("id") or ""

    # Explicit event dedupe, under this endpoint's own consumer key. The order
    # UPDATE below is already guarded by `AND status = 'pending'`, but that only
    # protects the order row — `issue_receipt_for_paid_order` re-runs on a retry
    # and re-emails the customer. That it mostly doesn't today is accidental,
    # not designed.
    if event_id and not await claim_stripe_event(
        event_id, etype or "", consumer=CONSUMER_CAPPE_CONNECT
    ):
        return {"received": True, "status": "duplicate"}

    try:
        return await _handle_connect_event(etype, obj, event, background)
    except Exception:
        # Release the claim so Stripe's retry can re-process. Without this, a
        # transient failure between the claim and the order UPDATE (a pool
        # timeout, a DB blip) is permanent: the retry sees the claim, returns
        # "duplicate", and the order stays `pending` forever with no receipt —
        # while the customer has already been charged.
        await release_stripe_event(event_id, consumer=CONSUMER_CAPPE_CONNECT)
        raise


async def _handle_connect_event(etype, obj, event, background) -> dict:
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
                # Issue the receipt (assign number → render PDF → email) after
                # the 200 so Stripe isn't kept waiting on render/SMTP.
                background.add_task(issue_receipt_for_paid_order, row["id"], row["site_id"])
                logger.info("cappe order %s marked paid via Stripe", order_id)
            else:
                logger.warning(
                    "cappe webhook: order %s not matched to event account %s (ignored)",
                    order_id, event_account_id,
                )

        collab_payment_id = meta.get("collab_payment_id")
        if collab_payment_id and event_account_id:
            try:
                cpid = UUID(str(collab_payment_id))
            except (ValueError, TypeError):
                cpid = None
            if cpid is not None:
                session_id = obj.get("id")
                amount_total = obj.get("amount_total")
                async with get_connection() as conn:
                    # Match on payment id + amount + connected account, NOT the
                    # session id — checkout_payment lets the brand re-open
                    # checkout on a still-processing payment, which overwrites
                    # stripe_checkout_session_id with the new session. If the
                    # brand instead completes an earlier, now-orphaned session
                    # in a stale tab, matching on session id would find zero
                    # rows and the real charge would never get recorded. The
                    # payment id (trusted: comes from this event's own
                    # metadata) plus amount + connected-account ownership is
                    # sufficient — session id is stored for audit only.
                    crow = await conn.fetchrow(
                        """UPDATE cappe_collab_payments cp
                              SET status = 'paid', paid_at = NOW(),
                                  stripe_payment_intent = $2, stripe_checkout_session_id = $4,
                                  updated_at = NOW()
                             FROM cappe_collab_offers o, cappe_creator_profiles p, cappe_accounts ca
                            WHERE cp.id = $1 AND cp.status IN ('due', 'processing')
                              AND cp.amount_cents = $5
                              AND o.id = cp.offer_id AND p.id = o.creator_profile_id
                              AND ca.id = p.account_id AND ca.stripe_account_id = $3
                        RETURNING cp.offer_id, cp.trigger, cp.label, cp.amount_cents""",
                        cpid, obj.get("payment_intent"), event_account_id, session_id, amount_total,
                    )
                    completed = False
                    if crow is not None:
                        if crow["trigger"] == "on_accept":
                            await conn.execute(
                                "UPDATE cappe_collab_offers SET status = 'active', "
                                "last_action_at = NOW(), updated_at = NOW() "
                                "WHERE id = $1 AND status = 'accepted'", crow["offer_id"])
                        from ..services.collab import check_completion
                        completed = await check_completion(conn, crow["offer_id"])
                if crow is not None:
                    background.add_task(_notify_collab_paid, crow["offer_id"], crow["label"], crow["amount_cents"])
                    if completed:
                        background.add_task(_notify_collab_completed, crow["offer_id"])
                else:
                    # Real money moved (Stripe already charged the brand and
                    # credited the creator's connected account) but no row
                    # matched — most likely the payment was cancelled (e.g.
                    # the offer was cancelled while this checkout was still
                    # in flight, see cancel_offer's docstring). There's no
                    # automated refund path; this needs a human to reconcile
                    # in Stripe, so it goes to ERROR (persisted to
                    # server_error_reports) rather than WARNING.
                    logger.error(
                        "cappe collab webhook: payment %s (session %s, account %s) charged but not "
                        "matched to a due/processing row — needs manual reconciliation in Stripe",
                        collab_payment_id, session_id, event_account_id,
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


async def _notify_collab_paid(offer_id: UUID, label: str, amount_cents: int) -> None:
    """Creator-side 'you got paid' notice after a collab installment clears."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT o.title AS offer_title, ca.email, ca.name
                 FROM cappe_collab_offers o
                 JOIN cappe_creator_profiles p ON p.id = o.creator_profile_id
                 JOIN cappe_accounts ca ON ca.id = p.account_id
                WHERE o.id = $1""",
            offer_id,
        )
    if row is None:
        return
    await send_cappe_collab_paid_email(
        row["email"], row["name"], row["offer_title"], label, amount_cents,
        dashboard_url(f"/creator/deals/{offer_id}"),
    )


async def _notify_collab_completed(offer_id: UUID) -> None:
    """Both sides get told when the final installment clearing completes the
    collab — mirrors the identical notice the approve-deliverable route sends
    when completion happens there instead of via webhook."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT o.title AS offer_title,
                      ba.email AS brand_email, ba.name AS brand_name,
                      ca.email AS creator_email, ca.name AS creator_name
                 FROM cappe_collab_offers o
                 JOIN cappe_accounts ba ON ba.id = o.brand_account_id
                 JOIN cappe_creator_profiles p ON p.id = o.creator_profile_id
                 JOIN cappe_accounts ca ON ca.id = p.account_id
                WHERE o.id = $1""",
            offer_id,
        )
    if row is None:
        return
    await send_cappe_collab_completed_email(
        row["brand_email"], row["brand_name"], row["offer_title"], dashboard_url(f"/collabs/{offer_id}"),
    )
    await send_cappe_collab_completed_email(
        row["creator_email"], row["creator_name"], row["offer_title"], dashboard_url(f"/creator/deals/{offer_id}"),
    )
