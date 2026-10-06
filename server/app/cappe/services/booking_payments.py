"""Deposits and paid bookings.

A service can take a deposit or its full price when it's booked
(`cappe_booking_types.payment_mode`). Such a booking is made as an ORDER with
one booking line, so it reuses everything orders have: the Stripe payment page
and its expiry, the abandoned-order sweep, pay-after-approval, refunds.

The booking is HELD — `pending`, its slot kept — until the payment lands:

  * paid (webhook, or the owner marking the order paid) → confirmed;
  * the page abandoned or expired → the order is released, and with it the
    booking (`inventory.release_order_bookings`);
  * a payment that lands after the hold was released is refunded: the slot
    may already be someone else's.

The owner can't confirm a hold that hasn't been paid. Whatever the deposit
leaves is collected at the appointment (`balance_due_cents`), outside Stripe.
"""
from __future__ import annotations

import json
from typing import Any, Optional

PAYMENT_MODES = ("none", "deposit", "full")


def amount_due_now(btype: Any, quote_cents: int) -> tuple[int, int]:
    """(charged when booking, left for the appointment). A deposit larger
    than the price is the price."""
    mode = (btype.get("payment_mode") if hasattr(btype, "get") else None) or "none"
    quote = max(0, int(quote_cents or 0))
    if mode == "full":
        return quote, 0
    if mode == "deposit":
        deposit = min(quote, int(btype.get("deposit_cents") or 0))
        return deposit, quote - deposit
    return 0, quote


def line_title(btype: Any, balance_cents: int, when_label: str = "") -> str:
    """What the receipt and the payment page call it: the service and when."""
    name = (btype.get("name") if hasattr(btype, "get") else None) or "Booking"
    title = f"Deposit — {name}" if balance_cents > 0 else name
    return f"{title}, {when_label}" if when_label else title


async def takes_payment_for(conn, site_id, btype, *, owner=None, ent=None) -> bool:
    """Whether a booking of this service is paid when it's made: the service
    asks for it, and the store can take cards and is allowed to sell. A store
    that can't is booked as before (pay at the appointment) rather than not
    at all."""
    mode = (btype.get("payment_mode") if hasattr(btype, "get") else None) or "none"
    if mode not in ("deposit", "full"):
        return False
    if owner is None:
        owner = await conn.fetchrow(
            "SELECT a.plan, a.status, a.stripe_account_id, a.stripe_charges_enabled "
            "FROM cappe_accounts a JOIN cappe_sites s ON s.account_id = a.id WHERE s.id = $1",
            site_id,
        )
    if not owner or (owner["status"] or "active") != "active":
        return False
    if not (owner["stripe_account_id"] and owner["stripe_charges_enabled"]):
        return False
    if ent is None:
        from .entitlements import resolve_entitlements
        ent = await resolve_entitlements(owner["plan"], conn=conn)
    return bool(ent.can_sell)


async def create_booking_order(
    conn, *, site, btype, booking, email: str, name: Optional[str], note: Optional[str],
    currency: str, pay_now: int, balance: int, title: str,
):
    """The order a paid booking is made as: one booking line for what's due
    now. Caller holds the transaction the booking was made in."""
    order = await conn.fetchrow(
        """INSERT INTO cappe_orders
               (site_id, customer_email, customer_name, status, subtotal_cents, tax_cents,
                shipping_cents, total_cents, currency, note, requires_approval)
           VALUES ($1, $2, $3, 'pending', $4, 0, 0, $4, $5, $6, $7)
           RETURNING id, status, subtotal_cents, tax_cents, shipping_cents, total_cents,
                     currency, access_token, requires_approval""",
        site["id"], email, name, pay_now, currency, note, bool(booking["requires_approval"]),
    )
    await conn.execute(
        """INSERT INTO cappe_order_items
               (order_id, site_id, product_id, title, unit_price_cents, quantity, fulfillment,
                intake_answers, selected_options, booking_id, balance_due_cents)
           VALUES ($1, $2, NULL, $3, $4, 1, 'booking', $5, $6, $7, $8)""",
        order["id"], site["id"], title, pay_now, json.dumps({}), json.dumps([]),
        booking["id"], balance,
    )
    return order


async def confirm_paid_bookings(conn, order_id) -> int:
    """Confirm the bookings an order was holding, now that it's paid.
    Idempotent: only held (`pending`) bookings move."""
    rows = await conn.fetch(
        """UPDATE cappe_bookings
              SET status = 'confirmed', approved_at = COALESCE(approved_at, NOW()), updated_at = NOW()
            WHERE status = 'pending'
              AND id IN (SELECT booking_id FROM cappe_order_items
                          WHERE order_id = $1 AND booking_id IS NOT NULL)
        RETURNING id""",
        order_id,
    )
    return len(rows)


async def unpaid_hold(conn, booking_id):
    """The order a booking is held for, when it is still waiting to be paid."""
    return await conn.fetchrow(
        """SELECT o.id, o.status, o.requires_approval, o.subtotal_cents
             FROM cappe_order_items oi JOIN cappe_orders o ON o.id = oi.order_id
            WHERE oi.booking_id = $1 AND o.status = 'pending' AND o.subtotal_cents > 0
            ORDER BY o.created_at DESC LIMIT 1""",
        booking_id,
    )


async def order_has_bookings(conn, order_id) -> bool:
    return bool(await conn.fetchval(
        "SELECT 1 FROM cappe_order_items WHERE order_id = $1 AND booking_id IS NOT NULL LIMIT 1", order_id,
    ))
