"""Booking status rules, and the facts a status change needs about a booking.

The owner's status PATCH used to write any of four statuses over any other.
Re-confirming a cancelled booking took its slot back without checking whether
someone had booked it since — a silent double-booking, or a 500 when the
unique index caught it. Setting "confirmed" on a request skipped the approval
stamp and the customer's email. Nothing told the customer when the business
cancelled.

`ALLOWED_TRANSITIONS` is the whole graph for the PATCH. A slot is held by
`pending` and `confirmed` (the double-book index's predicate); every move
below either keeps the hold, or gives it up for good — none takes a released
slot back, so none needs an overlap re-check.

Pure, or takes the caller's connection; nothing here sends email itself.
"""
from __future__ import annotations

from typing import Optional

# pending   → confirmed   approve (same as the Accept action: stamps approved_at
#                          and emails the customer when it was a request)
# pending   → cancelled   release the slot
# confirmed → cancelled   release the slot; the customer is told
# confirmed → completed   the appointment happened
#
# Deliberately missing:
#   cancelled / declined → anything   the slot was released and may be taken
#   completed → anything              history
#   * → declined                      the Decline action (reason + email)
#   * → pending                       a confirmed booking is not "unconfirmed"
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"confirmed", "cancelled"}),
    "confirmed": frozenset({"cancelled", "completed"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "declined": frozenset(),
}

# Statuses that hold a slot on the calendar.
HOLDING_STATUSES = ("pending", "confirmed")


def transition_error(current: str, new: Optional[str]) -> Optional[str]:
    """Why `current → new` is refused, or None if it may proceed. A repeat of
    the current status is always fine (a double-click)."""
    if new is None or new == current:
        return None
    if new in ALLOWED_TRANSITIONS.get(current, frozenset()):
        return None
    if new == "declined":
        return "Use Decline to turn down a booking request."
    if current in ("cancelled", "declined"):
        return (
            f"A {current} booking can't be reopened — its time may have been booked since. "
            "Create a new booking instead."
        )
    if not ALLOWED_TRANSITIONS.get(current):
        return f"A {current} booking can't be changed."
    return f"A {current} booking can't be moved to {new}."


def booking_lock_key(*, site_id, booking_type_id, staff_id, location_id) -> str:
    """The resource two bookings contend for, as a lock name.

    Mirrors the overlap rule in `commerce.resolve_booking_slot`: a staffed
    booking contends for the STAFF MEMBER (across every service they offer); an
    unstaffed one for its (location, service) slot. Two requests that could
    overlap always compute the same key, so the advisory lock serialises
    exactly the check-then-insert that used to race.
    """
    if staff_id is not None:
        return f"cappe-booking:staff:{staff_id}"
    return f"cappe-booking:slot:{site_id}:{location_id or '-'}:{booking_type_id}"


async def lock_booking_resource(conn, key: str) -> None:
    """Serialise booking writes on one resource until the transaction ends.

    The overlap check is a read followed by an insert. The unique index only
    catches an identical start on an identical (service, staff, location), so
    two requests for one stylist — a haircut at 10:00 and a colour at 10:00,
    or 10:00 and 10:30 — both passed the read and both inserted. With this lock
    the second request waits, then sees the first booking. MUST be called
    inside the transaction that inserts or moves the booking.
    """
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", key)


async def linked_order(conn, booking_id) -> Optional[dict]:
    """The shop order a booking was bought through, if any: {id, status}."""
    row = await conn.fetchrow(
        """SELECT o.id, o.status
             FROM cappe_order_items oi
             JOIN cappe_orders o ON o.id = oi.order_id
            WHERE oi.booking_id = $1
            ORDER BY o.created_at DESC
            LIMIT 1""",
        booking_id,
    )
    return dict(row) if row else None


def holds_money(order: Optional[dict]) -> bool:
    """Whether a linked order has taken the customer's money (and so needs a
    refund, not just a cancelled booking)."""
    return bool(order) and order.get("status") in ("paid", "fulfilled")
