"""Order status rules, and the one place an order becomes `refunded`.

Two problems this module exists for:

1. **Any status could follow any other.** `PATCH /orders/{id}` took one of five
   statuses and wrote it. `paid → cancelled → paid → cancelled` restocked twice
   and released the booking slots twice, because only the webhook's revive path
   ever took stock back out. `ALLOWED_TRANSITIONS` is the whole graph now, and
   it has no cycle that passes through a restock.

2. **`refunded` was a word, not a refund.** Choosing it flipped the status and
   restocked; no money moved. The status is now reached only when the refund
   ledger (`services/refunds.py`) settles the refund that brings the order's
   refunded total to its full amount — after Stripe accepted it, or when the
   Connect webhook reports one made in the Stripe dashboard. The generic PATCH
   refuses it.

Everything here is pure or takes the caller's connection; nothing talks to
Stripe, so the rules are testable without it.
"""
from __future__ import annotations

from typing import Optional

# What an owner may do by hand. Anything absent is refused.
#
#   pending   → paid       offline payment (cash, invoice). Closes the buyer's
#                          Stripe page first; stamps paid_at; issues the receipt.
#   pending   → cancelled  releases stock and booking slots.
#   paid      → fulfilled
#   fulfilled → paid       un-fulfil (mis-click); no stock or money involved.
#
# Deliberately missing:
#   paid/fulfilled → cancelled   money has been taken; the way out is a refund.
#   * → refunded                 only via the refund action (see module doc).
#   cancelled/refunded/declined → anything   terminal. Their stock and slots
#                          were handed back; re-opening would need them re-taken.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"paid", "cancelled"}),
    "paid": frozenset({"fulfilled"}),
    "fulfilled": frozenset({"paid"}),
    "cancelled": frozenset(),
    "refunded": frozenset(),
    "declined": frozenset(),
}

# Statuses that hold the customer's money — the only ones a refund applies to.
REFUNDABLE_STATUSES = ("paid", "fulfilled")


def allowed_next_statuses(current: str) -> list[str]:
    return sorted(ALLOWED_TRANSITIONS.get(current, frozenset()))


def transition_error(current: str, new: Optional[str]) -> Optional[str]:
    """Why `current → new` is refused, or None if it may proceed. `new=None`
    (a tracking-only PATCH) and `new == current` (a repeat) are always fine."""
    if new is None or new == current:
        return None
    if new == "refunded":
        return (
            "Use the Refund action to refund an order — it returns the customer's "
            "money. Changing the status alone does not."
        )
    if new in ALLOWED_TRANSITIONS.get(current, frozenset()):
        return None
    if current in REFUNDABLE_STATUSES and new == "cancelled":
        return "This order has been paid. Refund it instead of cancelling it."
    if not ALLOWED_TRANSITIONS.get(current):
        return f"A {current} order can't be changed."
    return f"A {current} order can't be moved to {new}."
