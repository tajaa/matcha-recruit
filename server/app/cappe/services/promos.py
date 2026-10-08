"""Promo codes: what a code takes off a bag, and keeping count of its uses.

A code applies to the lines that have NO automatic discount (promotions don't
stack, the same rule automatic discounts already follow), before tax and
shipping. Its discount is split over those lines in proportion to their
totals, to the cent (largest remainder), so:

  * every line knows its own share (`promo_discount_cents`) — the Stripe page
    shows each discounted line as its discounted total, never a negative
    "discount" line Stripe would refuse, and a refund sees exact amounts;
  * tax is charged on what the buyer actually pays for the goods;
  * "free shipping over $50" compares the discounted goods.

Uses are counted under a row lock on the code at order time; an order that
is released (cancelled, declined, unpaid past its page, refunded in full)
gives its use back — see `inventory.release_order_bookings`.

Subscriptions don't take codes this round: a code's discount would be fixed
into the recurring price for ever.

`evaluate` and `allocate` are pure; the rest takes the caller's connection.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional, Sequence

from fastapi import HTTPException

from .email import fmt_money

CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,39}$")

PROMO_COLS = (
    "id, code, kind, percent_off, amount_off_cents, min_subtotal_cents, starts_on, ends_on, "
    "max_redemptions, once_per_customer, active, redemption_count, created_at"
)


def normalize_code(raw: Optional[str]) -> Optional[str]:
    """Codes are case-blind: "summer10" is "SUMMER10"."""
    code = (raw or "").strip().upper()
    return code or None


def evaluate(promo: Optional[dict], *, eligible_cents: int, on_date: date, currency: str = "USD") -> tuple[int, Optional[str]]:
    """(discount in cents, why it can't be used). A usable code returns a
    positive discount and no reason; anything else returns 0 and the reason
    the buyer is shown."""
    if promo is None or not promo.get("active"):
        return 0, "That code isn't valid."
    if promo.get("starts_on") and on_date < promo["starts_on"]:
        return 0, "That code isn't active yet."
    if promo.get("ends_on") and on_date > promo["ends_on"]:
        return 0, "That code has expired."
    cap = promo.get("max_redemptions")
    if cap is not None and int(promo.get("redemption_count") or 0) >= int(cap):
        return 0, "That code has been used up."
    if eligible_cents <= 0:
        return 0, "That code doesn't apply to anything in your bag (items already on sale are left out)."
    minimum = promo.get("min_subtotal_cents")
    if minimum and eligible_cents < int(minimum):
        return 0, f"Spend {fmt_money(int(minimum), currency)} or more to use that code."
    if promo.get("kind") == "percent":
        pct = max(0, min(int(promo.get("percent_off") or 0), 90))
        discount = (eligible_cents * pct + 50) // 100
    else:
        discount = int(promo.get("amount_off_cents") or 0)
    return min(discount, eligible_cents), None


def allocate(discount_cents: int, line_totals: Sequence[int], eligible: Sequence[bool]) -> list[int]:
    """Split a discount over the eligible lines in proportion to their totals,
    to the cent: floor shares, then the leftover cents to the lines with the
    largest remainders (earliest line first on a tie). Never more than a
    line's own total; the shares always add up to the discount."""
    base = sum(t for t, ok in zip(line_totals, eligible) if ok and t > 0)
    shares = [0] * len(line_totals)
    if discount_cents <= 0 or base <= 0:
        return shares
    discount_cents = min(discount_cents, base)
    remainders = []
    for i, (total, ok) in enumerate(zip(line_totals, eligible)):
        if not ok or total <= 0:
            continue
        exact = discount_cents * total
        shares[i] = exact // base
        remainders.append((exact % base, -i))
    left = discount_cents - sum(shares)
    for _rem, neg_i in sorted(remainders, reverse=True)[:left]:
        shares[-neg_i] += 1
    return shares


async def find_code(conn, site_id, code: str, *, lock: bool = False) -> Optional[dict]:
    row = await conn.fetchrow(
        f"SELECT {PROMO_COLS} FROM cappe_promo_codes WHERE site_id = $1 AND code = $2"
        + (" FOR UPDATE" if lock else ""),
        site_id, code,
    )
    return dict(row) if row else None


async def used_by(conn, promo_id, email: Optional[str]) -> bool:
    if not email:
        return False
    return bool(await conn.fetchval(
        "SELECT 1 FROM cappe_promo_redemptions WHERE promo_code_id = $1 "
        "AND lower(customer_email) = lower($2) AND status = 'active'",
        promo_id, email,
    ))


async def redeem(conn, *, promo: dict, site_id, order_id, email: Optional[str], discount_cents: int) -> None:
    """Count one use. Caller holds the code's row lock (find_code(lock=True))."""
    await conn.execute(
        "INSERT INTO cappe_promo_redemptions (promo_code_id, site_id, order_id, customer_email, discount_cents) "
        "VALUES ($1, $2, $3, $4, $5)",
        promo["id"], site_id, order_id, email, discount_cents,
    )
    await conn.execute(
        "UPDATE cappe_promo_codes SET redemption_count = redemption_count + 1, updated_at = NOW() WHERE id = $1",
        promo["id"],
    )


def refuse(reason: str) -> HTTPException:
    return HTTPException(status_code=422, detail=reason)


def line_total(line: Any) -> int:
    return int(line["unit_price_cents"]) * int(line["quantity"]) - int(line.get("promo_discount_cents") or 0)
