"""Cappe Stripe Connect — business onboarding + storefront payment webhook.

Two authed endpoints let a business connect/refresh its Stripe account, plus one
public webhook the Connect endpoint posts to. Storefront Checkout Sessions
themselves are created in `public.py` (the checkout flow); this router owns
onboarding + the paid-order webhook.
"""

from __future__ import annotations

import json
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
from ..services.common import url_within_origins
from ..services.email import (
    dashboard_url,
    send_cappe_collab_completed_email,
    send_cappe_collab_paid_email,
)
from ..services.inventory import restock_order
from ..services.receipt import issue_receipt_for_paid_order
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger("cappe.payments")

router = APIRouter()


def extract_shipping_details(obj: dict) -> Optional[dict]:
    """Newer Stripe API versions nest the buyer's address under
    collected_information.shipping_details; older ones put it at top level.
    Read both; None when absent either way. Works on raw event payloads and
    retrieved StripeObject sessions alike (both are dict-like)."""
    collected = obj.get("collected_information") or {}
    return collected.get("shipping_details") or obj.get("shipping_details") or None


def _own_dashboard_url(url: Optional[str]) -> Optional[str]:
    """Return `url` only if it points at our own creator dashboard.

    Stripe renders `return_url` / `refresh_url` as links on its hosted, Stripe-
    branded onboarding page. Forwarding a client-supplied URL there turns
    Stripe into a phishing springboard for any address the caller chooses, so
    anything outside the dashboard origin is dropped for the safe default.
    """
    return url_within_origins(url, [dashboard_url("")])


def session_is_paid(obj: dict) -> bool:
    """Has this Checkout Session actually been paid?

    Delayed-notification payment methods (ACH debit, SEPA, Klarna — any of
    which a Connect merchant can enable on their own account) fire
    `checkout.session.completed` immediately with `payment_status: "unpaid"`,
    then settle hours later with `async_payment_succeeded` or fail with
    `async_payment_failed`. Treating `completed` as money in the bank released
    digital downloads and receipts against a payment that had not cleared.

    A session that carries no `payment_status` at all is only honoured when it
    isn't a one-time payment session; `mode="payment"` always carries one.
    """
    ps = obj.get("payment_status")
    if ps is None:
        return obj.get("mode") != "payment"
    return ps == "paid"


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
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
            )
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE cappe_accounts SET stripe_account_id = $1, updated_at = NOW() WHERE id = $2",
                acct_id,
                account.id,
            )

    return_url = _own_dashboard_url(body.return_url) or dashboard_url("/sites")
    refresh_url = _own_dashboard_url(body.refresh_url) or return_url
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
        return {
            "connected": False,
            "charges_enabled": False,
            "details_submitted": False,
        }
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
            charges,
            details,
            account.id,
        )
    return {"connected": True, "charges_enabled": charges, "details_submitted": details}


@router.post("/payments/webhook")
async def payments_webhook(request: Request, background: BackgroundTasks):
    """Stripe Connect webhook. Verifies the signature, then:
      - checkout.session.completed / .async_payment_succeeded → mark the order
        paid (+ payment intent, fee) — but only once `payment_status` says the
        money cleared (see `session_is_paid`).
      - checkout.session.async_payment_failed / .expired → cancel the still-
        pending order and put its stock back.
      - account.updated → refresh the business's capability flags.
    Always returns 200 on handled events so Stripe stops retrying.

    The three delayed-payment event types must be enabled on the Connect
    webhook endpoint in the Stripe dashboard; until they are, the abandoned-
    order reaper (workers/tasks/cappe_order_reaper.py) is the only thing that
    frees stock held by an unpaid session."""
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
    if etype in ("checkout.session.completed", "checkout.session.async_payment_succeeded"):
        if not session_is_paid(obj):
            # Not a failure: the async methods settle later on their own event.
            # Returning 200 stops Stripe retrying a decision that is correct.
            logger.info(
                "cappe webhook: session %s %s but payment_status=%s — waiting for settlement",
                obj.get("id"), etype, obj.get("payment_status"),
            )
            return {"received": True, "status": "unpaid"}
        return await _mark_order_paid(obj, event, background)

    if etype in ("checkout.session.async_payment_failed", "checkout.session.expired"):
        return await _cancel_unpaid_session(etype, obj, event)

    if etype == "account.updated":
        acct_id = obj.get("id") or event.get("account")
        if acct_id:
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE cappe_accounts SET stripe_charges_enabled = $1, "
                    "stripe_details_submitted = $2, updated_at = NOW() WHERE stripe_account_id = $3",
                    bool(obj.get("charges_enabled")),
                    bool(obj.get("details_submitted")),
                    acct_id,
                )

    return {"received": True}


async def _cancel_unpaid_session(etype, obj, event) -> dict:
    """A payment that failed or a session that expired releases the order.

    Stock is decremented when the anonymous order is created, so an order that
    is never paid holds a tenant's inventory hostage. Both the status flip and
    the restock are status-guarded (`status = 'pending'`) and joined to the
    event's own connected account, so this is idempotent and can't be aimed at
    another business's order — the same shape as the mark-paid UPDATE.

    `restock_order`'s `reason` is constrained by a DB CHECK to the seven
    existing audit reasons, so the specific cause is logged rather than stored.
    """
    meta = obj.get("metadata") or {}
    order_id = meta.get("order_id")
    event_account_id = event.get("account")
    try:
        oid = UUID(str(order_id)) if order_id else None
    except (ValueError, TypeError):
        oid = None
    if oid is None or not event_account_id:
        if meta.get("collab_payment_id"):
            # Collab installments are not auto-reversed here: the brand can
            # re-open checkout, and the row is left for the existing due/
            # processing flow rather than silently rewritten by a webhook.
            logger.warning(
                "cappe webhook: collab payment %s %s — left for manual retry",
                meta.get("collab_payment_id"), etype,
            )
        return {"received": True}

    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE cappe_orders o
                      SET status = 'cancelled', updated_at = NOW()
                     FROM cappe_sites s, cappe_accounts a
                    WHERE o.id = $1 AND o.status = 'pending'
                      AND s.id = o.site_id AND a.id = s.account_id
                      AND a.stripe_account_id = $2
                RETURNING o.id, o.site_id""",
                oid,
                event_account_id,
            )
            if row is not None:
                await restock_order(
                    conn, site_id=row["site_id"], order_id=row["id"], reason="restock"
                )
    if row is None:
        logger.info("cappe webhook: order %s not pending on %s; nothing to release", order_id, etype)
    else:
        logger.info("cappe order %s cancelled + restocked after %s", order_id, etype)
    return {"received": True}


async def _mark_order_paid(obj, event, background) -> dict:
    """Mark the order (and/or collab installment) behind a settled Checkout
    Session paid. Shared by `completed` and `async_payment_succeeded`, which
    carry the same object and must do exactly the same thing."""
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
        ship = extract_shipping_details(obj)
        if ship is None and obj.get("shipping_cost") and obj.get("id"):
            try:
                sess = await get_cappe_stripe().retrieve_checkout_session(
                    event_account_id, obj["id"]
                )
                ship = extract_shipping_details(sess)
            except CappeStripeError:
                ship = None  # best-effort; never block marking the order paid
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """UPDATE cappe_orders o
                      SET status = 'paid', paid_at = NOW(),
                          stripe_payment_intent = $2, payment_ref = $2,
                          platform_fee_cents = COALESCE($3, platform_fee_cents),
                          shipping_address = COALESCE($5::jsonb, o.shipping_address),
                          updated_at = NOW()
                    FROM cappe_sites s, cappe_accounts a
                    WHERE o.id = $1 AND o.status = 'pending'
                      AND s.id = o.site_id AND a.id = s.account_id
                      AND a.stripe_account_id = $4
                    RETURNING o.id, o.site_id, o.customer_email, o.customer_name""",
                oid,
                payment_intent,
                fee,
                event_account_id,
                json.dumps(dict(ship)) if ship else None,
            )
        if row is not None:
            # Issue the receipt (assign number → render PDF → email) after
            # the 200 so Stripe isn't kept waiting on render/SMTP.
            background.add_task(
                issue_receipt_for_paid_order, row["id"], row["site_id"]
            )
            logger.info("cappe order %s marked paid via Stripe", order_id)
        else:
            async with get_connection() as conn:
                already = await conn.fetchval(
                    """SELECT o.status FROM cappe_orders o
                         JOIN cappe_sites s ON s.id = o.site_id
                         JOIN cappe_accounts a ON a.id = s.account_id
                        WHERE o.id = $1 AND a.stripe_account_id = $2""",
                    oid,
                    event_account_id,
                )
            if already is None:
                logger.error(
                    "cappe webhook: order %s not matched; releasing claim for retry",
                    order_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Order not matched; releasing event for retry",
                )
            logger.info(
                "cappe webhook: order %s already %s; idempotent skip",
                order_id,
                already,
            )
    elif oid is not None:
        logger.warning("cappe webhook: order %s has no event account", order_id)

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
                # metadata) plus connected-account ownership is sufficient;
                # session id is stored for audit only.
                crow = await conn.fetchrow(
                    """UPDATE cappe_collab_payments cp
                          SET status = 'paid', paid_at = NOW(),
                              stripe_payment_intent = $2, stripe_checkout_session_id = $4,
                              updated_at = NOW()
                         FROM cappe_collab_offers o, cappe_creator_profiles p, cappe_accounts ca
                        WHERE cp.id = $1 AND cp.status IN ('due', 'processing')
                          AND o.id = cp.offer_id AND p.id = o.creator_profile_id
                          AND ca.id = p.account_id AND ca.stripe_account_id = $3
                    RETURNING cp.offer_id, cp.trigger, cp.label, cp.amount_cents""",
                    cpid,
                    obj.get("payment_intent"),
                    event_account_id,
                    session_id,
                )
                if (
                    crow is not None
                    and amount_total is not None
                    and int(amount_total) != int(crow["amount_cents"])
                ):
                    logger.warning(
                        "cappe collab webhook: payment %s matched with Stripe total %s != stored %s",
                        collab_payment_id,
                        amount_total,
                        crow["amount_cents"],
                    )
                completed = False
                if crow is not None:
                    if crow["trigger"] == "on_accept":
                        await conn.execute(
                            "UPDATE cappe_collab_offers SET status = 'active', "
                            "last_action_at = NOW(), updated_at = NOW() "
                            "WHERE id = $1 AND status = 'accepted'",
                            crow["offer_id"],
                        )
                    from ..services.collab import check_completion

                    completed = await check_completion(conn, crow["offer_id"])
            if crow is not None:
                background.add_task(
                    _notify_collab_paid,
                    crow["offer_id"],
                    crow["label"],
                    crow["amount_cents"],
                )
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
                    collab_payment_id,
                    session_id,
                    event_account_id,
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
        row["email"],
        row["name"],
        row["offer_title"],
        label,
        amount_cents,
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
        row["brand_email"],
        row["brand_name"],
        row["offer_title"],
        dashboard_url(f"/collabs/{offer_id}"),
    )
    await send_cappe_collab_completed_email(
        row["creator_email"],
        row["creator_name"],
        row["offer_title"],
        dashboard_url(f"/creator/deals/{offer_id}"),
    )
