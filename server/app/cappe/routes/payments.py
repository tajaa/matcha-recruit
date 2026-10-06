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
from ..services.entitlements import resolve_entitlements
from ..services.email import (
    app_origin,
    dashboard_url,
    send_cappe_collab_completed_email,
    send_cappe_collab_paid_email,
    send_cappe_order_alert_email,
)
from ..services.inventory import release_order_bookings, restock_order, retake_order_stock
from ..services.order_lifecycle import mark_order_refunded
from ..services.receipt import issue_receipt_for_paid_order
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger("cappe.payments")

router = APIRouter()

# Statuses an order reaches by being released (stock + slots handed back)
# without any money having moved. A paid event for one of these means the buyer
# was charged for an order we had thrown away.
_RELEASED_STATUSES = ("cancelled", "declined")


def extract_shipping_details(obj: dict) -> Optional[dict]:
    """Newer Stripe API versions nest the buyer's address under
    collected_information.shipping_details; older ones put it at top level.
    Read both; None when absent either way. Works on raw event payloads and
    retrieved StripeObject sessions alike (both are dict-like)."""
    collected = obj.get("collected_information") or {}
    return collected.get("shipping_details") or obj.get("shipping_details") or None


def _own_dashboard_url(url: Optional[str]) -> Optional[str]:
    """Return `url` only if it points at our own app origin.

    Stripe renders `return_url` / `refresh_url` as links on its hosted, Stripe-
    branded onboarding page. Forwarding a client-supplied URL there turns
    Stripe into a phishing springboard for any address the caller chooses, so
    anything off our origin is dropped for the safe default.

    The ORIGIN is the boundary, not the `/cappe` path: the same SPA serves the
    creator marketplace under `/gummfit/creators/...` and the whole tree at the
    apex on the Cappe host, and pinning `/cappe` bounced every creator coming
    back from Stripe onboarding onto the business dashboard.
    """
    return url_within_origins(url, [app_origin()])


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
    # `no_payment_required` is a settled session too: a 100%-discount order has
    # nothing to collect, and treating it as unpaid strands it pending until the
    # reaper cancels an order the buyer legitimately completed.
    return ps in ("paid", "no_payment_required")


class ConnectLinkRequest(BaseModel):
    return_url: Optional[str] = None
    refresh_url: Optional[str] = None


class ConnectLinkResponse(BaseModel):
    url: str


class ConnectStatusResponse(BaseModel):
    connected: bool
    charges_enabled: bool
    details_submitted: bool
    # The caller's plan take rate, so the dashboard states the real fee instead
    # of a hard-coded one. None when the billing catalog can't be read.
    platform_fee_bps: Optional[int] = None


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
        try:
            fee_bps = (await resolve_entitlements(account.plan, conn=conn)).platform_fee_bps
        except Exception:  # noqa: BLE001 — the fee line is informational
            fee_bps = None
    if not acct_id:
        return {
            "connected": False,
            "charges_enabled": False,
            "details_submitted": False,
            "platform_fee_bps": fee_bps,
        }
    # Connection released before the Stripe round-trip — see connect_account.
    try:
        acct = await cs.retrieve_account(acct_id)
    except CappeStripeError:
        return {"connected": True, "charges_enabled": False, "details_submitted": False,
                "platform_fee_bps": fee_bps}
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
    return {"connected": True, "charges_enabled": charges, "details_submitted": details,
            "platform_fee_bps": fee_bps}


@router.post("/payments/webhook")
async def payments_webhook(request: Request, background: BackgroundTasks):
    """Stripe Connect webhook. Verifies the signature, then:
      - checkout.session.completed / .async_payment_succeeded → mark the order
        paid (+ payment intent, fee) — but only once `payment_status` says the
        money cleared (see `session_is_paid`).
      - checkout.session.async_payment_failed / .expired → cancel the still-
        pending order and put its stock back.
      - charge.refunded → a refund made in the Stripe dashboard (or by our own
        refund route) lands on the order / collab installment.
      - charge.dispute.created / .updated / .closed → the chargeback is
        recorded on the order; a lost one closes it out.
      - account.updated → refresh the business's capability flags.
    Always returns 200 on handled events so Stripe stops retrying.

    The delayed-payment, refund and dispute event types must be enabled on the
    Connect webhook endpoint in the Stripe dashboard (list in
    `docs/ops/CAPPE_PAYMENTS.md`). Until the delayed-payment ones are, the
    abandoned-order reaper is the only thing that frees stock held by an unpaid
    session; until the refund ones are, a dashboard refund leaves the order
    `paid` here."""
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
    if (etype in ("invoice.paid", "invoice.payment_failed", "customer.subscription.updated", "customer.subscription.deleted")
        or (etype in ("checkout.session.completed", "checkout.session.expired", "checkout.session.async_payment_succeeded", "checkout.session.async_payment_failed")
            and obj.get("mode") == "subscription")):
        from ..services.recurring import handle_event
        return await handle_event(etype, obj, event, background)
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

    if etype == "charge.refunded":
        return await _sync_charge_refunded(obj, event)

    if etype in ("charge.dispute.created", "charge.dispute.updated", "charge.dispute.closed"):
        return await _sync_dispute(obj, event)

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
        if meta.get("collab_payment_id") and event_account_id:
            await _reopen_collab_installment(meta["collab_payment_id"], obj, event_account_id, etype)
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
                      -- Only the order's CURRENT page ending releases it: a
                      -- page "Pay now" replaced expires later and must not
                      -- cancel an order whose newer page is still open.
                      AND (o.stripe_session_id IS NULL OR o.stripe_session_id = $3)
                      -- An approved order stays open until its pay-by date;
                      -- the buyer can open a new page from the order page.
                      AND (o.pay_by IS NULL OR o.pay_by < NOW())
                RETURNING o.id, o.site_id""",
                oid,
                event_account_id,
                obj.get("id"),
            )
            if row is not None:
                await restock_order(
                    conn, site_id=row["site_id"], order_id=row["id"], reason="restock"
                )
                # Booking lines hold their appointment slot from order creation;
                # stock alone coming back leaves the calendar blocked for nobody.
                await release_order_bookings(conn, order_id=row["id"])
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
                      -- Paid on the order's current page. A page "Pay now"
                      -- replaced is expired first, so this only refuses a
                      -- race; that payment is refunded below.
                      AND (o.stripe_session_id IS NULL OR o.stripe_session_id = $6)
                    RETURNING o.id, o.site_id, o.customer_email, o.customer_name, o.shopper_id,
                              o.total_cents, o.subtotal_cents, o.currency,
                              s.name AS site_name, a.email AS owner_email, a.name AS owner_name""",
                oid,
                payment_intent,
                fee,
                event_account_id,
                json.dumps(dict(ship)) if ship else None,
                obj.get("id"),
            )
        if row is not None:
            from ..services.push import notify_order_event
            if row.get("shopper_id"):
                background.add_task(notify_order_event, row["id"], "paid")
            # Issue the receipt (assign number → render PDF → email) after
            # the 200 so Stripe isn't kept waiting on render/SMTP.
            background.add_task(
                issue_receipt_for_paid_order, row["id"], row["site_id"]
            )
            # Tell the owner. The alert used to go out only for orders that took
            # NO card — so a store with Stripe connected, the normal case, heard
            # nothing about a sale until someone opened the dashboard.
            if row.get("owner_email"):
                background.add_task(
                    send_cappe_order_alert_email, row["owner_email"], row.get("owner_name"),
                    row.get("site_name") or "", row.get("customer_name"),
                    row.get("total_cents") or row.get("subtotal_cents") or 0,
                    row.get("currency") or "USD",
                    dashboard_url(f"/sites/{row['site_id']}/orders"),
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
                paid_on = None
                if already in ("pending", "paid", "fulfilled") and payment_intent:
                    paid_on = await conn.fetchrow(
                        "SELECT stripe_session_id, stripe_payment_intent FROM cappe_orders WHERE id = $1",
                        oid,
                    )
            stray_payment = bool(paid_on) and (
                # Paid on a page that is no longer the order's current one.
                (already == "pending" and paid_on["stripe_session_id"] not in (None, obj.get("id")))
                # A second payment for an order that is already paid.
                or (already in ("paid", "fulfilled") and paid_on["stripe_payment_intent"]
                    and paid_on["stripe_payment_intent"] != payment_intent)
            )
            if stray_payment:
                await _refund_stray_order_payment(oid, obj.get("id"), payment_intent, event_account_id, already)
                return {"received": True, "status": "refunded_stray_payment"}
            if already is None:
                logger.error(
                    "cappe webhook: order %s not matched; releasing claim for retry",
                    order_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Order not matched; releasing event for retry",
                )
            if already in _RELEASED_STATUSES:
                # Money arrived for an order we had already released (owner
                # cancelled or declined it while the payment page was still
                # open, or a release raced a late settlement). The buyer HAS
                # been charged, so the released status is now false: put the
                # order back to paid and make the mismatch loud.
                #
                # `paid` is a decremented state (a later refund restocks it), so
                # the stock handed back at release time is taken out again in
                # the same transaction — otherwise a refund credits the shelf
                # twice. Booking slots are NOT re-taken: the slot may already
                # belong to someone else, which a human has to sort out.
                async with get_connection() as conn:
                    async with conn.transaction():
                        revived = await conn.fetchrow(
                            """UPDATE cappe_orders o
                                  SET status = 'paid', paid_at = NOW(),
                                      stripe_payment_intent = $2, payment_ref = $2,
                                      platform_fee_cents = COALESCE($3, platform_fee_cents),
                                      shipping_address = COALESCE($5::jsonb, o.shipping_address),
                                      decline_reason = NULL,
                                      updated_at = NOW()
                                 FROM cappe_sites s, cappe_accounts a
                                WHERE o.id = $1 AND o.status IN ('cancelled', 'declined')
                                  AND s.id = o.site_id AND a.id = s.account_id
                                  AND a.stripe_account_id = $4
                            RETURNING o.id, o.site_id""",
                            oid, payment_intent, fee, event_account_id,
                            json.dumps(dict(ship)) if ship else None,
                        )
                        if revived is not None:
                            await retake_order_stock(
                                conn, site_id=revived["site_id"], order_id=revived["id"]
                            )
                logger.error(
                    "cappe webhook: PAID event for %s order %s (intent %s) — order restored to "
                    "paid and its stock re-taken; booking slots were released and are NOT "
                    "re-held, verify fulfilment or refund",
                    str(already).upper(), order_id, payment_intent,
                )
                if revived is not None:
                    background.add_task(
                        issue_receipt_for_paid_order, revived["id"], revived["site_id"]
                    )
            elif already == "refunded":
                # Refunded orders stay refunded, but a fresh charge against one
                # is money nobody is tracking.
                logger.error(
                    "cappe webhook: PAID event for REFUNDED order %s (intent %s) — not restored; "
                    "reconcile the charge in Stripe",
                    order_id, payment_intent,
                )
            else:
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
            await _settle_collab_installment(cpid, obj, event_account_id, background)

    return {"received": True}


# ── collab installments ─────────────────────────────────────────────────────

def _collab_reject_reason(row, session_id, amount_total, currency) -> Optional[str]:
    """Why a settled Checkout Session must NOT be applied to this installment,
    or None when it is exactly the payment we asked for.

    Everything in the session's metadata is attacker-controllable by the
    connected account it was created on — and that account is the CREATOR's.
    Matching on the payment id alone meant a creator could mint their own
    50-cent session carrying the installment id, pay it, and have the
    installment marked paid and the offer activated with the platform fee
    never collected. So a session only settles an installment when it is the
    one our server created for it, for the stored amount, in the stored
    currency.
    """
    if row["status"] not in ("due", "processing"):
        return f"installment is already {row['status']}"
    if not row["stripe_checkout_session_id"] or session_id != row["stripe_checkout_session_id"]:
        return "paid through a checkout session that is not this installment's current one"
    try:
        if amount_total is None or int(amount_total) != int(row["amount_cents"]):
            return f"Stripe total {amount_total} does not match the installment's {row['amount_cents']}"
    except (TypeError, ValueError):
        return f"unreadable Stripe total {amount_total!r}"
    if currency and str(currency).lower() != str(row["currency"] or "").lower():
        return f"currency {currency} does not match the installment's {row['currency']}"
    return None


async def _settle_collab_installment(cpid: UUID, obj, event_account_id: str, background) -> None:
    """Apply a settled Checkout Session to its collab installment — or, when it
    cannot be applied, give the money back.

    "Cannot be applied" covers the two double-charge windows (a stale tab
    paying a session the brand had re-opened past; a session paid after the
    offer was cancelled) and a forged or mismatched session. In every one of
    them a card has been charged for nothing, and the old code could only log
    it for a human. The charge is refunded on the creator's connected account,
    platform fee included.
    """
    session_id = obj.get("id")
    intent = obj.get("payment_intent")
    reject: Optional[str] = None
    paid = None
    completed = False
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """SELECT cp.id, cp.offer_id, cp.status, cp.trigger, cp.label,
                          cp.amount_cents, cp.currency,
                          cp.stripe_checkout_session_id, cp.stripe_payment_intent
                     FROM cappe_collab_payments cp
                     JOIN cappe_collab_offers o ON o.id = cp.offer_id
                     JOIN cappe_creator_profiles p ON p.id = o.creator_profile_id
                     JOIN cappe_accounts ca ON ca.id = p.account_id
                    WHERE cp.id = $1 AND ca.stripe_account_id = $2
                      FOR UPDATE OF cp""",
                cpid, event_account_id,
            )
            if row is None:
                # No such installment on THIS connected account. Not provably
                # ours, so it is not ours to refund either.
                logger.error(
                    "cappe collab webhook: session %s on account %s names installment %s, which "
                    "does not exist for that account — ignored; reconcile in Stripe if real",
                    session_id, event_account_id, cpid,
                )
                return
            if row["status"] == "paid" and intent and row["stripe_payment_intent"] == intent:
                return  # this very payment, delivered again
            reject = _collab_reject_reason(row, session_id, obj.get("amount_total"), obj.get("currency"))
            if reject is None:
                paid = await conn.fetchrow(
                    """UPDATE cappe_collab_payments
                          SET status = 'paid', paid_at = NOW(),
                              stripe_payment_intent = $2, updated_at = NOW()
                        WHERE id = $1 AND status IN ('due', 'processing')
                    RETURNING offer_id, trigger, label, amount_cents""",
                    cpid, intent,
                )
                if paid is not None:
                    if paid["trigger"] == "on_accept":
                        await conn.execute(
                            "UPDATE cappe_collab_offers SET status = 'active', "
                            "last_action_at = NOW(), updated_at = NOW() "
                            "WHERE id = $1 AND status = 'accepted'",
                            paid["offer_id"],
                        )
                    from ..services.collab import check_completion

                    completed = await check_completion(conn, paid["offer_id"])

    if reject is not None:
        await _refund_unapplied_collab_charge(cpid, session_id, intent, event_account_id, reject)
        return
    if paid is not None:
        background.add_task(_notify_collab_paid, paid["offer_id"], paid["label"], paid["amount_cents"])
        if completed:
            background.add_task(_notify_collab_completed, paid["offer_id"])


async def _refund_stray_order_payment(order_id, session_id, intent, account_id, order_status) -> None:
    """Refund a storefront payment the order cannot take: made on a page that
    was replaced, or a second payment for an order already paid. These used to
    be logged as an "idempotent skip" while the money stayed taken. ERROR
    either way — a human should know an automatic refund happened."""
    try:
        await get_cappe_stripe().refund_connected_charge(
            account_id=account_id, payment_intent=intent,
            idempotency_key=f"cappe-order-stray-{intent}",
        )
    except CappeStripeError as exc:
        logger.error(
            "cappe webhook: order %s (%s) received a payment it cannot take (session %s, intent %s, "
            "account %s) and the automatic refund FAILED: %s — MANUAL REFUND REQUIRED",
            order_id, order_status, session_id, intent, account_id, exc,
        )
        return
    logger.error(
        "cappe webhook: order %s (%s) received a payment it cannot take (session %s, intent %s, "
        "account %s) — refunded automatically",
        order_id, order_status, session_id, intent, account_id,
    )


async def _refund_unapplied_collab_charge(cpid, session_id, intent, account_id, reason) -> None:
    """Refund a collab charge that settled but cannot be applied. No DB
    connection is held across the Stripe call. ERROR either way: an automatic
    refund is still something a human should know happened, and a failed one
    is money owed."""
    if not intent:
        logger.error(
            "cappe collab webhook: installment %s session %s on %s settled but cannot be applied "
            "(%s) and carries no payment intent — MANUAL REFUND REQUIRED",
            cpid, session_id, account_id, reason,
        )
        return
    try:
        await get_cappe_stripe().refund_connected_charge(
            account_id=account_id, payment_intent=intent,
            idempotency_key=f"cappe-collab-unapplied-{intent}",
        )
    except CappeStripeError as exc:
        logger.error(
            "cappe collab webhook: installment %s session %s (intent %s, account %s) settled but "
            "cannot be applied (%s), and the automatic refund FAILED: %s — MANUAL REFUND REQUIRED",
            cpid, session_id, intent, account_id, reason, exc,
        )
        return
    logger.error(
        "cappe collab webhook: installment %s session %s (intent %s, account %s) settled but could "
        "not be applied (%s) — the charge was refunded automatically",
        cpid, session_id, intent, account_id, reason,
    )


async def _reopen_collab_installment(collab_payment_id, obj, event_account_id: str, etype) -> None:
    """A collab checkout expired or its delayed payment failed: put the
    installment back to `due` so the brand sees "Pay" again.

    Only when the dead session is the installment's CURRENT one — an older
    session expiring must not reopen an installment whose newer checkout is
    still in flight. Nothing is charged on this path, so there is nothing to
    refund.
    """
    try:
        cpid = UUID(str(collab_payment_id))
    except (ValueError, TypeError):
        return
    async with get_connection() as conn:
        reopened = await conn.fetchval(
            """UPDATE cappe_collab_payments cp
                  SET status = 'due', updated_at = NOW()
                 FROM cappe_collab_offers o, cappe_creator_profiles p, cappe_accounts ca
                WHERE cp.id = $1 AND cp.status = 'processing'
                  AND cp.stripe_checkout_session_id = $2
                  AND o.id = cp.offer_id AND p.id = o.creator_profile_id
                  AND ca.id = p.account_id AND ca.stripe_account_id = $3
            RETURNING cp.id""",
            cpid, obj.get("id"), event_account_id,
        )
    if reopened is not None:
        logger.info("cappe collab installment %s back to due after %s", cpid, etype)


# ── refunds + disputes made in Stripe ───────────────────────────────────────

async def _order_for_charge(conn, intent, invoice_id, account_id):
    """The order a connected-account charge belongs to, locked. Card orders are
    keyed by payment intent; subscription orders by invoice. The join to the
    event's own connected account is what stops one business's signed event
    from reaching another's order."""
    for column, value in (("stripe_payment_intent", intent), ("stripe_invoice_id", invoice_id)):
        if not isinstance(value, str) or not value:
            continue
        row = await conn.fetchrow(
            f"""SELECT o.id, o.site_id, o.status
                  FROM cappe_orders o
                  JOIN cappe_sites s ON s.id = o.site_id
                  JOIN cappe_accounts a ON a.id = s.account_id
                 WHERE o.{column} = $1 AND a.stripe_account_id = $2
                 ORDER BY o.created_at DESC
                 LIMIT 1
                   FOR UPDATE OF o""",
            value, account_id,
        )
        if row is not None:
            return row
    return None


async def _sync_charge_refunded(obj, event) -> dict:
    """`charge.refunded` on a connected account.

    Before this, a refund issued from the Stripe dashboard changed nothing
    here: the order stayed `paid`, its digital download stayed live, and its
    stock was never returned. A FULL refund now does what the refund route
    does; a PARTIAL one records its amount and leaves the order paid (the
    customer still has the goods). Idempotent — `mark_order_refunded` only
    moves a paid/fulfilled order, so our own refund route's echo of this event
    is a no-op.
    """
    account_id = event.get("account")
    if not account_id:
        return {"received": True}
    intent = obj.get("payment_intent")
    amount = int(obj.get("amount") or 0)
    refunded = int(obj.get("amount_refunded") or 0)
    full = bool(obj.get("refunded")) or (amount > 0 and refunded >= amount)
    refunds = ((obj.get("refunds") or {}).get("data") or []) if isinstance(obj.get("refunds"), dict) else []
    refund_id = refunds[0].get("id") if refunds else None

    async with get_connection() as conn:
        async with conn.transaction():
            order = await _order_for_charge(conn, intent, obj.get("invoice"), account_id)
            if order is not None:
                if full:
                    moved = await mark_order_refunded(
                        conn, order_id=order["id"], site_id=order["site_id"],
                        refunded_cents=refunded or None, stripe_refund_id=refund_id,
                        # Same default as the refund route: goods that already
                        # shipped are not assumed to be back on the shelf.
                        restock=order["status"] != "fulfilled",
                    )
                    if moved is not None:
                        logger.info("cappe order %s refunded in Stripe; synced", order["id"])
                    return {"received": True, "status": "refunded"}
                await conn.execute(
                    "UPDATE cappe_orders SET refunded_cents = $2, "
                    "stripe_refund_id = COALESCE($3, stripe_refund_id), updated_at = NOW() "
                    "WHERE id = $1",
                    order["id"], refunded, refund_id,
                )
                logger.info(
                    "cappe order %s partially refunded in Stripe (%s of %s)", order["id"], refunded, amount
                )
                return {"received": True, "status": "partially_refunded"}

            if isinstance(intent, str) and intent and full:
                collab = await conn.fetchrow(
                    """UPDATE cappe_collab_payments cp
                          SET status = 'refunded', refunded_at = NOW(),
                              stripe_refund_id = COALESCE($3, cp.stripe_refund_id),
                              updated_at = NOW()
                         FROM cappe_collab_offers o, cappe_creator_profiles p, cappe_accounts ca
                        WHERE cp.stripe_payment_intent = $1 AND cp.status = 'paid'
                          AND o.id = cp.offer_id AND p.id = o.creator_profile_id
                          AND ca.id = p.account_id AND ca.stripe_account_id = $2
                    RETURNING cp.id, cp.offer_id""",
                    intent, account_id, refund_id,
                )
                if collab is not None:
                    # The offer's own state (active / completed) is NOT rewound:
                    # whether a refunded milestone un-completes a collab is a
                    # judgement, not arithmetic.
                    logger.error(
                        "cappe collab installment %s (offer %s) was refunded in Stripe — marked "
                        "refunded; review the offer's status",
                        collab["id"], collab["offer_id"],
                    )
                    return {"received": True, "status": "collab_refunded"}
    return {"received": True}


async def _sync_dispute(obj, event) -> dict:
    """`charge.dispute.*` on a connected account: record the chargeback on the
    order so the owner sees it beside the order rather than only in Stripe.

    A LOST dispute means the money is gone for good, so the order is closed
    out as refunded — without a restock, because unlike a refund nothing came
    back to the shelf.
    """
    account_id = event.get("account")
    intent = obj.get("payment_intent")
    if not account_id or not isinstance(intent, str) or not intent:
        return {"received": True}
    dispute_status = str(obj.get("status") or "open")[:40]
    async with get_connection() as conn:
        async with conn.transaction():
            order = await _order_for_charge(conn, intent, None, account_id)
            if order is None:
                return {"received": True}
            await conn.execute(
                "UPDATE cappe_orders SET dispute_status = $2, "
                "disputed_at = COALESCE(disputed_at, NOW()), updated_at = NOW() WHERE id = $1",
                order["id"], dispute_status,
            )
            if dispute_status == "lost":
                await mark_order_refunded(
                    conn, order_id=order["id"], site_id=order["site_id"],
                    refunded_cents=int(obj.get("amount") or 0) or None,
                    stripe_refund_id=None, restock=False,
                )
    logger.error(
        "cappe order %s: Stripe dispute %s is %s (reason: %s)",
        order["id"], obj.get("id"), dispute_status, obj.get("reason"),
    )
    return {"received": True, "status": "dispute_recorded"}


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
