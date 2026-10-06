"""Commerce/booking helpers, plus public-order + booking-slot creation.

`order_subtotal`/`booking_quote_cents`/`normalize_to_utc`/`booking_times` are
pure (no DB, no I/O — unit-testable in isolation) money + time math, exercised
independently of the route/transaction plumbing. `validate_intake` is likewise
pure. Everything else here is DB-touching: `fetch_rate_rules`/
`resolve_booking_slot`/`create_booking_in_tx` validate + price + insert one
booking (MUST run inside a transaction — shared by the public booking intake
and booking-fulfillment order lines); `fetch_site_owner`/
`check_recipient_send_ok` are small shared fetches; `create_public_order` is
the public order-creation flow itself.
"""
import json
import logging
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence
from urllib.parse import urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from .common import loads_list, order_page_url, site_origins, url_within_origins
from .discounts import apply_discount_cents, best_discount_percent, fetch_active_discounts, site_today
from .email import (
    build_order_items_summary,
    dashboard_url,
    send_cappe_low_stock_email,
    send_cappe_order_alert_email,
    send_cappe_order_receipt_email,
)
from .inventory import log_adjustment as _inv_log
from .booking_lifecycle import booking_lock_key, lock_booking_resource
from .booking_rules import check_window as check_booking_window, time_off_overlaps
from .inventory import lock_stock_rows, release_order_bookings, restock_order
from .options import fetch_option_groups, validate_and_price_options
from .entitlements import (
    fee_cents as entitlement_fee_cents,
    require_can_sell,
    resolve_entitlements,
)
from .stripe_connect import CONNECT_CHECKOUT_TTL_SECONDS, CappeStripeError, get_cappe_stripe
from .cart import cart_totals
from .shipping import home_country, load_zones, not_shippable, resolve_destination
from .promos import allocate as allocate_promo, evaluate as evaluate_promo, find_code, normalize_code
from .promos import redeem as redeem_promo, refuse as refuse_promo, used_by as promo_used_by

logger = logging.getLogger("cappe.commerce")


def order_subtotal(line_items: Iterable[tuple[int, int]]) -> int:
    """Sum unit_price_cents * quantity over (price, qty) pairs."""
    return sum(int(price) * int(qty) for price, qty in line_items)


# Where Stripe sends a WEB buyer who backs out of the payment page
# (`routes/render.py:checkout_return`).
CHECKOUT_RETURN_PATH = "/__cappe/checkout-return"


def checkout_cancel_url(cancel_url: str, order_token: str) -> str:
    """Route a storefront `cancel_url` through the site's own checkout-return
    handler, which releases the abandoned order and then redirects on to the
    page the storefront asked for.

    The order token rides THIS url only — a server endpoint that answers with a
    redirect — and never the storefront page itself. A tenant page can carry
    the merchant's own scripts and embeds, and the token opens the buyer's
    receipt and downloads. `cancel_url` must already be origin-validated; only
    its path, query and fragment are carried over, so the redirect cannot leave
    the site.
    """
    parts = urlsplit(cancel_url)
    onward = urlunsplit(("", "", parts.path or "/", parts.query, parts.fragment))
    query = urlencode({"o": order_token, "next": onward})
    return f"{parts.scheme}://{parts.netloc}{CHECKOUT_RETURN_PATH}?{query}"


def crossed_low_stock(before: int, after: int, threshold: Optional[int]) -> bool:
    """True when a sale takes stock from above the owner's threshold to at or
    below it. The alert used to fire on `after <= threshold` alone, so once a
    product was low EVERY further sale sent another email."""
    return threshold is not None and after <= threshold < before


def build_stripe_line_items(
    line_rows: Iterable[tuple], currency: str, tax_cents: int, tax_label: str,
    line_discounts: Optional[Sequence[int]] = None,
) -> list[dict]:
    """Cart lines as Stripe `price_data` line items, plus tax as its own line
    (shipping rides `shipping_options`, not a line item — see
    build_shipping_options). Sum of these unit_amount×quantity equals
    `subtotal_cents + tax_cents`; adding `shipping_cents` from
    `shipping_options` brings the charge to `total_cents`.

    A line a promo code discounted is sent as ONE item at its discounted total
    ("Mug × 2"): its share doesn't always divide by the quantity, and Stripe
    refuses a negative "discount" line."""
    rows = list(line_rows)
    discounts = list(line_discounts or []) + [0] * len(rows)
    line_items = []
    for (_pid, title, unit, qty, *_r), off in zip(rows, discounts):
        name = (title or "Item")[:240]
        if off:
            unit_amount, quantity = int(unit) * int(qty) - int(off), 1
            name = f"{name} × {int(qty)}" if int(qty) > 1 else name
        else:
            unit_amount, quantity = int(unit), int(qty)
        line_items.append({
            "price_data": {
                "currency": currency,
                "unit_amount": unit_amount,
                "product_data": {"name": name[:250]},
            },
            "quantity": quantity,
        })
    if tax_cents and tax_cents > 0:
        line_items.append({
            "price_data": {
                "currency": currency,
                "unit_amount": int(tax_cents),
                "product_data": {"name": tax_label[:120]},
            },
            "quantity": 1,
        })
    return line_items


def compute_shipping_cents(
    *, has_physical: bool, goods_subtotal_cents: int, flat_cents: int,
    free_threshold_cents: int | None,
) -> int:
    """Flat per-site shipping for carts with a paid physical line; zero when the
    free-shipping threshold is met. Both the gate and the threshold compare the
    GOODS subtotal (physical lines, pre-tax) — the same base the tax math uses,
    and what "free shipping over $50" means to a buyer. A goods subtotal of 0
    (giveaway item, or a cart Stripe will never charge for) never ships paid."""
    if not has_physical or flat_cents <= 0 or goods_subtotal_cents <= 0:
        return 0
    if free_threshold_cents is not None and goods_subtotal_cents >= free_threshold_cents:
        return 0
    return flat_cents


def _minute_multiplier(
    minute_t: time, weekday: int, rules: Sequence[dict]
) -> float:
    """Highest multiplier among rules covering this wall-clock minute, else 1.0.

    A rule matches when its weekday is None (every day) or equals `weekday`, and
    its [start_time, end_time) window contains `minute_t`. Overlapping rules take
    the max so a 2x extended-hours rule always wins over a baseline rule."""
    best = 1.0
    for r in rules:
        rw = r.get("weekday")
        if rw is not None and int(rw) != weekday:
            continue
        if r["start_time"] <= minute_t < r["end_time"]:
            m = float(r["multiplier"])
            if m > best:
                best = m
    return best


def booking_quote_cents(
    base_price_cents: int,
    pricing_mode: str,
    local_start: datetime,
    local_end: datetime,
    rules: Optional[Sequence[dict]] = None,
) -> int:
    """Price a booking.

    - flat   → `base_price_cents` regardless of length (today's behavior).
    - hourly → `base_price_cents` is the base rate per HOUR; each minute of the
      booking is charged at base/60 times the highest matching rate-rule
      multiplier (e.g. after-8pm = 2x). Summed and rounded to whole cents.

    `local_start`/`local_end` are wall-clock in the site timezone (a booking
    can't span midnight, enforced upstream), so weekday is taken from the start.
    """
    base = int(base_price_cents or 0)
    if pricing_mode != "hourly":
        return base
    rules = rules or []
    weekday = local_start.weekday()  # Mon=0..Sun=6
    per_minute = Decimal(base) / Decimal(60)
    total = Decimal(0)
    cursor = local_start
    step = timedelta(minutes=1)
    # Iterate minutes of the booking; bounded (<= 1440) since no midnight span.
    while cursor < local_end:
        mult = _minute_multiplier(cursor.time(), weekday, rules)
        total += per_minute * Decimal(str(mult))
        cursor += step
    return int(total.to_integral_value())


def normalize_to_utc(dt: datetime) -> datetime:
    """Treat a naive datetime as UTC; leave aware datetimes unchanged."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def booking_times(starts_at: datetime, duration_minutes: int, tz_name: str | None) -> dict:
    """Resolve a booking's UTC span and its wall-clock representation in the
    site's timezone. `spans_midnight` flags a window the simple TIME-based
    availability check can't represent."""
    start = normalize_to_utc(starts_at)
    end = start + timedelta(minutes=int(duration_minutes))
    try:
        tz = ZoneInfo(tz_name or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    return {
        "start_utc": start,
        "end_utc": end,
        "local_start": local_start,
        "local_end": local_end,
        "weekday": local_start.weekday(),  # Mon=0 .. Sun=6
        "spans_midnight": local_end.date() != local_start.date(),
    }


def validate_intake(intake_fields: list, answers: dict) -> None:
    """Reject a service/booking purchase whose required intake answers are
    missing. Answers are anonymous client input — keep it bounded + don't trust."""
    if len(json.dumps(answers)) > 8000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Intake answers too large")
    for field in intake_fields or []:
        if isinstance(field, dict) and field.get("required"):
            key = field.get("key")
            val = answers.get(key) if isinstance(answers, dict) else None
            if val is None or (isinstance(val, str) and not val.strip()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required answer: {field.get('label') or key}",
                )


async def fetch_site_owner(conn, site_id):
    """The site owner's account (email/name + Stripe-Connect status), for creator
    notifications and storefront checkout. Returns None if the site (or its
    account) is gone.

    `id` and `plan` are selected because the storefront checkout resolves the
    owner's entitlements from them — the platform take rate is per-plan, so the
    plan must be in hand at the point the fee is computed."""
    return await conn.fetchrow(
        "SELECT a.id, a.plan, a.email, a.name, a.status, a.stripe_account_id, "
        "a.stripe_charges_enabled "
        "FROM cappe_accounts a JOIN cappe_sites s ON s.account_id = a.id WHERE s.id = $1",
        site_id,
    )


async def check_recipient_send_ok(email: str | None, *, bucket: str = "cappe_recipient_email", limit: int = 5) -> bool:
    """Per-recipient throttle for outbound transactional email on PUBLIC,
    unauthenticated endpoints (order receipts, booking confirmations). Keyed on
    the RECIPIENT (not the caller IP) so rotating source IPs can't flood one
    victim's inbox from our sender. Never blocks the underlying action — the
    order/booking is still created; only the email is skipped past the cap.
    Returns True when it's OK to send.

    `bucket` separates kinds of mail that must not starve each other: a
    shopper's sign-in codes used to share one budget with receipts and booking
    emails, so a busy hour of orders left them unable to sign in at all."""
    if not email:
        return False
    try:
        await check_rate_limit(email.lower(), bucket, limit, 3600)
        return True
    except HTTPException:
        return False


async def fetch_rate_rules(conn, site_id, booking_type_id, location_id=None) -> list[dict]:
    """Rate rules in effect for a booking type at a location (its own + site-wide
    NULL ones; this location's + shared NULL-location ones)."""
    rows = await conn.fetch(
        """SELECT weekday, start_time, end_time, multiplier FROM cappe_rate_rules
           WHERE site_id = $1 AND (booking_type_id IS NULL OR booking_type_id = $2)
             AND (location_id IS NULL OR location_id = $3)""",
        site_id, booking_type_id, location_id,
    )
    return [dict(r) for r in rows]


def _anchor_local(dt, tz_name):
    """A naive datetime from the widget is the visitor's pick in the SITE's
    timezone (availability is site-local) — anchor it there.

    Duplicated (not imported) from `routes/public.py`'s own `_anchor_local`:
    that one has callers outside booking-slot resolution and stays there —
    this is the same six lines kept service-side so `resolve_booking_slot`
    doesn't reach back into the route layer for it."""
    if dt.tzinfo is not None:
        return dt
    try:
        return dt.replace(tzinfo=ZoneInfo(tz_name or "UTC"))
    except Exception:
        return dt.replace(tzinfo=timezone.utc)


class OutsideAvailability(HTTPException):
    """The requested time falls in none of the availability windows that apply.

    Its own type so the "any available" loop can tell "this stylist doesn't
    work then" (try the next one) from a request that is wrong for everyone.
    That loop only moved on after a 409, so on a salon where each stylist has
    their own hours, every slot that came from anyone but the first stylist
    failed with a 400.
    """

    def __init__(self, detail: str = "Time is outside availability"):
        super().__init__(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


class TimeOff(OutsideAvailability):
    """The time falls in a closed period (`cappe_time_off`). A kind of
    "outside availability", so the "any available" loop moves on to the next
    staff member when only this one is off."""

    def __init__(self):
        super().__init__("That time isn't available. Choose another.")


async def resolve_booking_slot(
    conn, site, btype, starts_at, ends_at_override=None, exclude_booking_id=None, staff_id=None,
    location_id=None, tz=None, owner=False,
):
    """Validate availability + overlap and price a booking window. Returns
    {s_utc, e_utc, quote_cents, requires_approval, booking_status}; raises 4xx on
    a bad/taken slot. `exclude_booking_id` skips one booking from the overlap
    check (for in-place reschedule). `staff_id` scopes availability + overlap to
    one staff member (None = the legacy shared calendar). MUST run inside a
    transaction.

    `btype` must carry duration_minutes, price_cents, pricing_mode,
    requires_approval. For an hourly type the buyer may pass `ends_at_override`
    to book a variable-length window; otherwise the type's duration is used.
    `location_id`/`tz` scope availability + overlap + pricing to one location and
    use that location's timezone (None → site timezone).

    The service's minimum notice and horizon, the opening hours and time off
    (`booking_rules`) bind customers; `owner=True` — a booking the owner makes
    or moves — skips them. Nobody skips the double-booking check."""
    tz = tz or site["timezone"]
    starts_at = _anchor_local(starts_at, tz)
    pricing_mode = btype.get("pricing_mode", "flat")

    if ends_at_override is not None and pricing_mode == "hourly":
        ends_at_override = _anchor_local(ends_at_override, tz)
        duration_min = (ends_at_override - starts_at).total_seconds() / 60
        if duration_min <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End time must be after start")
        if duration_min > 1440:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking is too long")
    else:
        duration_min = btype["duration_minutes"]

    bt = booking_times(starts_at, duration_min, tz)
    s_utc, e_utc = bt["start_utc"], bt["end_utc"]

    now_utc = await conn.fetchval("SELECT NOW()")
    if s_utc <= now_utc and not owner:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a future time")
    if bt["spans_midnight"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking can't span midnight")
    if not owner:
        await _customer_rules(conn, site, btype, bt, s_utc, e_utc, now_utc, staff_id, location_id)

    # Lock + overlap: below, for everyone.
    await _lock_and_check_overlap(conn, site, btype, s_utc, e_utc, exclude_booking_id, staff_id, location_id)

    # Price the booked window (flat → base; hourly → per-minute × rate rules),
    # then apply the best active discount judged on today (location timezone).
    rules = await fetch_rate_rules(conn, site["id"], btype["id"], location_id)
    quote_cents = booking_quote_cents(
        btype.get("price_cents") or 0, pricing_mode, bt["local_start"], bt["local_end"], rules
    )
    discounts = await fetch_active_discounts(conn, site["id"])
    pct = best_discount_percent(
        discounts, kind="booking_type", target_id=str(btype["id"]),
        on_date=site_today(now_utc, tz), location_id=location_id,
    )
    quote_cents = apply_discount_cents(quote_cents, pct)

    requires_approval = bool(btype.get("requires_approval")) and not owner
    return {
        "s_utc": s_utc, "e_utc": e_utc, "quote_cents": quote_cents,
        "requires_approval": requires_approval,
        # Approval-required types land 'pending' (creator queue); others
        # auto-confirm so an open calendar books straight through. The owner's
        # own booking is confirmed: they are the approval.
        "booking_status": "pending" if requires_approval else "confirmed",
    }


async def _customer_rules(conn, site, btype, bt, s_utc, e_utc, now_utc, staff_id, location_id) -> None:
    """What binds a customer's booking but not the owner's: notice + horizon,
    the opening hours, and time off."""
    check_booking_window(btype, s_utc, now_utc)
    window = await conn.fetchval(
        """SELECT 1 FROM cappe_availability
           WHERE site_id = $1 AND weekday = $2
             AND start_time <= $3 AND end_time >= $4
             AND (booking_type_id IS NULL OR booking_type_id = $5)
             AND (staff_id IS NULL OR staff_id = $6)
             AND (location_id IS NULL OR location_id = $7)
           LIMIT 1""",
        site["id"], bt["weekday"], bt["local_start"].time(), bt["local_end"].time(),
        btype["id"], staff_id, location_id,
    )
    if not window:
        raise OutsideAvailability()
    if await time_off_overlaps(conn, site["id"], start_utc=s_utc, end_utc=e_utc,
                               staff_id=staff_id, location_id=location_id):
        raise TimeOff()


async def _lock_and_check_overlap(conn, site, btype, s_utc, e_utc, exclude_booking_id, staff_id, location_id) -> None:
    """Lock the contended resource, then refuse an overlapping booking."""
    # Overlap is per shared RESOURCE, not per booking type. A staffed booking's
    # resource is the STAFF MEMBER — a person can't be in two places at once, so
    # they conflict with ANY overlapping booking of theirs regardless of service
    # type (this is the bug being fixed: the old `booking_type_id = $2` narrowing
    # let one staffer offering two types be double-booked for the same window
    # under each type). An UNstaffed booking has no person to contend for, so it
    # falls back to the (location, type) slot it occupies — that way two
    # resource-less service types can still run in parallel, while a second
    # booking of the SAME offering in the same slot is still blocked.
    # The check below is a read; the insert that follows it is a write. Two
    # requests for the same resource used to both pass the read — the unique
    # index only catches an identical start on an identical service — so the
    # resource is locked first and the second request waits for the first.
    await lock_booking_resource(conn, booking_lock_key(
        site_id=site["id"], booking_type_id=btype["id"], staff_id=staff_id, location_id=location_id,
    ))
    # The gap kept between two bookings is the larger of their two buffers. It
    # used to be only the NEW booking's, so a no-buffer service could be booked
    # straight up against one that needs half an hour to turn the room around.
    buf_min = int(btype.get("buffer_minutes") or 0)
    overlap = await conn.fetchval(
        """SELECT 1 FROM cappe_bookings b
             LEFT JOIN cappe_booking_types obt ON obt.id = b.booking_type_id
           WHERE b.site_id = $1 AND b.status IN ('pending', 'confirmed')
             AND ($5::uuid IS NULL OR b.id <> $5)
             AND (
                   ($6::uuid IS NOT NULL AND b.staff_id = $6)
                OR ($6::uuid IS NULL AND b.staff_id IS NULL
                    AND b.location_id IS NOT DISTINCT FROM $8
                    AND b.booking_type_id = $2)
             )
              AND tstzrange(b.starts_at, b.ends_at)
                  && tstzrange(
                       $3::timestamptz - (GREATEST($7::integer, COALESCE(obt.buffer_minutes, 0)) * interval '1 minute'),
                       $4::timestamptz + (GREATEST($7::integer, COALESCE(obt.buffer_minutes, 0)) * interval '1 minute')
                     )
           LIMIT 1""",
        site["id"], btype["id"], s_utc, e_utc, exclude_booking_id, staff_id, buf_min, location_id,
    )
    if overlap:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")


async def create_booking_in_tx(
    conn, site, btype, starts_at, customer_name, customer_email, note,
    ends_at_override=None, rider_acknowledged=False, rider_snapshot=None, staff_id=None,
    location_id=None, tz=None, owner=False, hold=False,
):
    """Validate + price + insert a booking. MUST run inside a transaction.
    Shared by the public booking intake, booking-fulfillment order lines and
    the owner's own bookings (`owner=True`, see resolve_booking_slot).

    `hold=True`: the booking waits for a payment (a deposit, or a booking line
    in a card order) — `pending`, its slot kept, until the order is paid
    (`booking_payments.confirm_paid_bookings`) or released."""
    slot = await resolve_booking_slot(
        conn, site, btype, starts_at, ends_at_override, staff_id=staff_id, location_id=location_id, tz=tz,
        owner=owner,
    )
    if hold:
        slot["booking_status"] = "pending"
    try:
        return await conn.fetchrow(
            """INSERT INTO cappe_bookings
                   (site_id, booking_type_id, staff_id, location_id, customer_name, customer_email, starts_at, ends_at,
                    note, status, requires_approval, quoted_price_cents,
                    rider_acknowledged, rider_snapshot)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
               RETURNING id, status, starts_at, ends_at, quoted_price_cents, requires_approval, access_token""",
            site["id"], btype["id"], staff_id, location_id, customer_name, customer_email, slot["s_utc"], slot["e_utc"],
            note, slot["booking_status"], slot["requires_approval"], slot["quote_cents"],
            bool(rider_acknowledged), json.dumps(rider_snapshot or []),
        )
    except Exception as exc:
        if "idx_cappe_bookings_no_doublebook" in str(exc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")
        raise


async def release_unpaid_order(order_id, site_id) -> bool:
    """Cancel a still-`pending` order and hand back everything it was holding:
    stock, variant stock, booking slots. Status-guarded, so it is a no-op for
    an order that has since been paid or released. Opens its own connection."""
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "UPDATE cappe_orders SET status = 'cancelled', updated_at = NOW() "
                "WHERE id = $1 AND site_id = $2 AND status = 'pending' RETURNING id",
                order_id, site_id,
            )
            if row is None:
                return False
            await restock_order(conn, site_id=site_id, order_id=order_id, reason="restock")
            await release_order_bookings(conn, order_id=order_id)
    return True


async def release_abandoned_checkout(token: str) -> str:
    """A buyer came back from Stripe's payment page without paying: close the
    page and hand back what their order was holding. Returns

      * ``"released"``  — the order was pending on an open page; now cancelled.
      * ``"paid"``      — the buyer DID finish checkout; nothing is released and
                          the paid webhook decides the order.
      * ``"unchanged"`` — nothing to do (unknown token, already settled or
                          released, or an order that never went to Stripe —
                          those belong to the owner, not to a browser redirect).

    Follows the payments invariant: the Stripe page is closed FIRST and the
    order released only once Stripe confirms nobody can pay it. No connection
    is held across the Stripe call. Raises `CappeStripeError` if Stripe cannot
    be reached — the order is then left exactly as it was.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT o.id, o.site_id, o.status, o.stripe_session_id, a.stripe_account_id, o.pay_by
                 FROM cappe_orders o
                 JOIN cappe_sites s ON s.id = o.site_id
                 JOIN cappe_accounts a ON a.id = s.account_id
                WHERE o.access_token = $1""",
            token,
        )
    if (
        row is None
        or row["status"] != "pending"
        or not row["stripe_session_id"]
        or not row["stripe_account_id"]
    ):
        return "unchanged"
    state = await get_cappe_stripe().expire_checkout_session(
        row["stripe_account_id"], row["stripe_session_id"]
    )
    if state != "expired":
        return "paid"
    if row["pay_by"] is not None:
        # An order the owner approved stays open until its pay-by date: the
        # buyer can come back to the order page and pay. Only the page closes.
        return "unchanged"
    return "released" if await release_unpaid_order(row["id"], row["site_id"]) else "unchanged"


def bind_return_urls(success_url, cancel_url, site, token):
    """Point already origin-validated Stripe return URLs at this order.

    * The app return (`/__cappe/app-return`) carries the token to the app.
    * A web buyer who pays lands on the order page (`/order/<token>`), which
      confirms the order and holds its downloads — the storefront used to
      send them back to the product page with nothing to say it worked.
    * A web buyer who backs out goes through the checkout-return handler,
      which hands the held stock and slots straight back.

    Bound after origin validation, because the token does not exist when the
    storefront asks for checkout. Each link stays on the host the buyer used.
    """
    out = []
    for field, value in (("success", success_url), ("cancel", cancel_url)):
        if not value:
            out.append(value)
            continue
        parsed = urlsplit(value)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if parsed.path == "/__cappe/app-return":
            out.append(f"{origin}/__cappe/app-return?o={token}&r={field}")
        elif field == "success":
            out.append(order_page_url(site, token, origin=origin))
        else:
            out.append(checkout_cancel_url(value, token))
    return out[0], out[1]


async def open_order_checkout(
    *, order, line_rows, owner, owner_ent, success_url, cancel_url, email,
    shopper=None, has_physical, tax_label, shipping_label, line_discounts=None,
):
    """Open a Stripe Checkout page for an existing order and record it as the
    order's current page. Shared by order creation and by "Pay now" on an order
    the owner approved, so both charge exactly what the order says.

    `line_rows` are (product_id, title, unit_price_cents, quantity, ...) — the
    prices FROZEN on the order, never the live product. Raises
    CappeStripeError; holds no connection across the Stripe call.
    """
    pay_total = order["subtotal_cents"]
    cur = (order["currency"] or "USD").lower()
    # Per-plan take rate, computed ONCE here and handed to Stripe, so the number
    # persisted on the order is the same number Stripe actually takes.
    fee = entitlement_fee_cents(pay_total, owner_ent.platform_fee_bps)
    # Tax as its own line so the charged amount equals the receipt total. The
    # platform fee stays on the goods subtotal.
    line_items = build_stripe_line_items(line_rows, cur, order["tax_cents"], tax_label, line_discounts)
    customer_id = None
    if shopper:
        from .shopper_customers import connected_customer
        customer_id = await connected_customer(shopper, owner["stripe_account_id"])
    sess = await get_cappe_stripe().create_checkout_session(
        account_id=owner["stripe_account_id"],
        currency=cur,
        line_items=line_items,
        application_fee_cents=fee,
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"order_id": str(order["id"]), "platform_fee_cents": str(fee)},
        customer_email=email or None,
        **({"customer_id": customer_id} if customer_id else {}),
        collect_shipping_address=has_physical,
        # The country the order was priced for, and only that one: an address
        # anywhere else would ship somewhere the shipping and tax weren't for.
        ship_countries=[order["ship_country"]] if has_physical and order.get("ship_country") else None,
        expires_in_seconds=CONNECT_CHECKOUT_TTL_SECONDS,
        shipping_option=(
            {
                "label": shipping_label if order["shipping_cents"] > 0 else "Free shipping",
                "amount_cents": order["shipping_cents"],
            }
            if has_physical else None
        ),
    )
    async with get_connection() as conn:
        await conn.execute(
            "UPDATE cappe_orders SET stripe_session_id = $1, platform_fee_cents = $2, "
            "checkout_opened_at = NOW(), updated_at = NOW() WHERE id = $3",
            sess.get("id"), fee, order["id"],
        )
    return sess


class PayRefused(HTTPException):
    """Why "Pay now" can't open a payment page for this order."""

    def __init__(self, detail: str, status_code: int = status.HTTP_409_CONFLICT):
        super().__init__(status_code=status_code, detail=detail)


async def pay_for_order(token: str) -> dict:
    """Open a payment page for a pending order the buyer holds the token to —
    the "Pay now" on the order page, used after the owner approves an order
    (which is never sent to Stripe before that).

    The order's current page, if any, is closed first: one payable page per
    order. If the buyer already finished paying on it, nothing new is opened.
    Prices come from the order, never the live products. Returns
    {"checkout_url": ...}.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT o.id, o.site_id, o.status, o.requires_approval, o.subscription_id, o.pay_by,
                      o.subtotal_cents, o.tax_cents, o.shipping_cents, o.total_cents, o.currency,
                      o.customer_email, o.stripe_session_id, o.access_token,
                      COALESCE(o.ship_country, s.home_country) AS ship_country,
                      o.pay_by IS NOT NULL AND o.pay_by < NOW() AS overdue,
                      s.name AS site_name, s.slug, s.subdomain, s.custom_domain,
                      s.tax_label, s.shipping_label,
                      a.id AS owner_id, a.plan, a.status AS owner_status, a.email AS owner_email,
                      a.name AS owner_name, a.stripe_account_id, a.stripe_charges_enabled
                 FROM cappe_orders o
                 JOIN cappe_sites s ON s.id = o.site_id
                 JOIN cappe_accounts a ON a.id = s.account_id
                WHERE o.access_token = $1""",
            token,
        )
        if row is None:
            raise PayRefused("Order not found", status.HTTP_404_NOT_FOUND)
        if row["status"] != "pending":
            raise PayRefused(
                "This order has already been paid." if row["status"] in ("paid", "fulfilled")
                else "This order is no longer open."
            )
        if row["subscription_id"] is not None:
            raise PayRefused("This order is billed by a subscription.")
        if row["requires_approval"]:
            raise PayRefused("The store hasn't approved this order yet. You'll get an email when it does.")
        if row["overdue"]:
            raise PayRefused("The time to pay for this order has passed. Contact the store to order again.")
        if row["subtotal_cents"] <= 0:
            raise PayRefused("There's nothing to pay for this order.")
        if (row["owner_status"] or "active") != "active" or not (
            row["stripe_account_id"] and row["stripe_charges_enabled"]
        ):
            raise PayRefused("This store isn't taking card payments online. They'll be in touch about payment.")
        owner_ent = await resolve_entitlements(row["plan"], conn=conn)
        require_can_sell(owner_ent)
        items = await conn.fetch(
            "SELECT product_id, title, unit_price_cents, quantity, fulfillment, promo_discount_cents "
            "FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
            row["id"],
        )
    if row["stripe_session_id"]:
        state = await get_cappe_stripe().expire_checkout_session(
            row["stripe_account_id"], row["stripe_session_id"],
        )
        if state != "expired":
            raise PayRefused("Your payment is already being processed — check your email for the receipt.")
    site = {"subdomain": row["subdomain"], "custom_domain": row["custom_domain"]}
    page = order_page_url(site, token)
    line_rows = [(it["product_id"], it["title"], it["unit_price_cents"], it["quantity"], it["fulfillment"])
                 for it in items]
    sess = await open_order_checkout(
        order=row, line_rows=line_rows, owner=row, owner_ent=owner_ent,
        success_url=page, cancel_url=page, email=row["customer_email"],
        has_physical=any(it["fulfillment"] == "physical" for it in items),
        tax_label=row["tax_label"] or "Tax", shipping_label=row["shipping_label"] or "Shipping",
        line_discounts=[int(it.get("promo_discount_cents") or 0) for it in items],
    )
    return {"checkout_url": sess.get("url")}


def _order_ship_country(body, address, site_cfg) -> str:
    """Where a physical order ships: the country the bag was priced for, else
    the typed address's country, else the store's home country (all an app
    that predates shipping zones ever sends). A typed address in another
    country than the one priced is refused rather than quietly re-priced."""
    requested = getattr(body, "ship_country", None)
    typed = address.country if address is not None else None
    if requested and typed and typed != requested:
        raise HTTPException(
            status_code=422,
            detail=f"Your address is in {typed}, but your order was priced for shipping to {requested}. "
                   "Pick the same country for both.",
        )
    return requested or typed or home_country(site_cfg)


async def create_public_order(site, body, background, *, shopper=None) -> dict:
    """Create an order for a mixed cart (physical / digital / service /
    booking). Prices + totals are recomputed server-side from the live product
    rows. The order lands `pending` and is handed to Stripe Checkout when the
    business has Connect ready (the paid webhook flips it); without Connect it
    stays `pending` for the owner to advance by hand. Inventory is decremented
    only for physical lines; booking lines create a scheduled booking; service
    lines validate intake answers. All in one transaction.

    `site` is the route's already-`_published_site`-resolved row. Opens its own
    connection (closed before the Stripe Checkout call below, so a slow/failed
    call to Stripe never holds a pooled connection) — mirrors the original
    route's own two-connection shape.
    """
    email = shopper["email"] if shopper else str(body.customer_email).strip().lower()

    async with get_connection() as conn:
        discounts = await fetch_active_discounts(conn, site["id"])
        today = site_today(await conn.fetchval("SELECT NOW()"), site["timezone"])
        # Owner + entitlements are resolved BEFORE the transaction opens, for
        # two reasons.
        #
        # 1. `get_catalog` swallows read errors so entitlements can fail OPEN to
        #    legacy behaviour — but swallowing a Postgres error inside an open
        #    transaction does not fail open. The transaction is already aborted,
        #    and the next statement raises InFailedSQLTransactionError. In the
        #    exact case the fallback exists for (code deployed ahead of
        #    zzzzcappe26, so the catalog table is missing) every storefront
        #    order would 500 — the opposite of what the fallback promises.
        # 2. `fetch_site_owner` already returns the plan, so hoisting it means
        #    one query serves both the selling gate and the fee below.
        owner = await fetch_site_owner(conn, site["id"])
        # A suspended or deleted account's storefront takes no orders. The
        # subscription checkout already required an active owner; the one-off
        # path did not, so a suspended merchant could keep selling.
        if owner is None or (owner.get("status") or "active") != "active":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This store isn't taking orders right now.",
            )
        owner_ent = await resolve_entitlements(owner["plan"] if owner else None, conn=conn)
        takes_cards = bool(owner and owner["stripe_account_id"] and owner["stripe_charges_enabled"])
        async with conn.transaction():
            order_currency = None
            order_requires_approval = False  # any line needing creator review holds the whole order
            low_stock_hits: list[tuple[str, int]] = []  # (product name, balance) for the owner alert
            # (product_id, title, unit_price, qty, fulfillment, intake_answers, booking_id)
            line_rows = []
            on_sale: list[bool] = []  # per line: an automatic discount applied (no promo code on top)
            # Batch-load option groups for every product in the cart once, instead
            # of one query per line item inside the loop below (N+1).
            opt_groups_by_product = await fetch_option_groups(
                conn, [it.product_id for it in body.items]
            )
            # Take every stock lock up front, in id order. The per-line
            # `FOR UPDATE`s below then re-lock rows this transaction already
            # holds, so two carts listing the same products in opposite order
            # queue instead of deadlocking.
            await lock_stock_rows(
                conn, site_id=site["id"],
                product_ids=[it.product_id for it in body.items],
                option_ids=[oid for it in body.items for oid in (it.selected_option_ids or [])],
            )
            for item in body.items:
                product = await conn.fetchrow(
                    "SELECT id, name, price_cents, currency, inventory, low_stock_threshold, "
                    "status, fulfillment, booking_type_id, requires_approval, intake_fields "
                    "FROM cappe_products WHERE id = $1 AND site_id = $2 FOR UPDATE",
                    item.product_id, site["id"],
                )
                if product is None or product["status"] != "active":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product unavailable")
                if order_currency is None:
                    order_currency = product["currency"]
                elif product["currency"] != order_currency:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mixed currencies not supported")
                if product["requires_approval"]:
                    order_requires_approval = True

                f = product["fulfillment"]
                qty = item.quantity
                booking_id = None
                intake = item.intake_answers or {}
                # What this line takes off the shelf — written to the order line
                # so a later restock credits exactly this and nothing else.
                # None on non-physical lines: there is nothing to reverse.
                stock_taken = False if f == "physical" else None
                options_taken: list | None = [] if f == "physical" else None

                if f == "physical":
                    thr = product["low_stock_threshold"]
                    if product["inventory"] is not None:
                        new_bal = await conn.fetchval(
                            "UPDATE cappe_products SET inventory = inventory - $1, updated_at = NOW() "
                            "WHERE id = $2 AND inventory >= $1 RETURNING inventory",
                            qty, item.product_id,
                        )
                        if new_bal is None:
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=f"Insufficient stock for {product['name']}",
                            )
                        stock_taken = True
                        await _inv_log(
                            conn, site_id=site["id"], product_id=item.product_id,
                            delta=-qty, balance_after=new_bal, reason="sale",
                        )
                        if crossed_low_stock(new_bal + qty, new_bal, thr):
                            low_stock_hits.append((product["name"], new_bal))
                    # Per-variant stock: decrement each selected option that tracks it.
                    for oid in (item.selected_option_ids or []):
                        opt = await conn.fetchrow(
                            "SELECT name, inventory FROM cappe_product_options "
                            "WHERE id = $1 AND site_id = $2 FOR UPDATE",
                            oid, site["id"],
                        )
                        inv = opt["inventory"] if opt else None
                        if inv is None:
                            continue  # untracked variant
                        if inv < qty:
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=f"Insufficient stock for {product['name']} (selected option)",
                            )
                        await conn.execute(
                            "UPDATE cappe_product_options SET inventory = $1 WHERE id = $2", inv - qty, oid
                        )
                        options_taken.append(oid)
                        await _inv_log(
                            conn, site_id=site["id"], product_id=item.product_id, option_id=oid,
                            delta=-qty, balance_after=inv - qty, reason="sale",
                        )
                        # Variants have no threshold of their own; the product's
                        # is the owner's "tell me when it is this low".
                        if crossed_low_stock(inv, inv - qty, thr):
                            low_stock_hits.append((f"{product['name']} — {opt['name']}", inv - qty))
                elif f == "service":
                    validate_intake(loads_list(product["intake_fields"]), intake)
                elif f == "digital":
                    pass  # delivered via the receipt download once paid/fulfilled
                elif f == "booking":
                    if product["booking_type_id"] is None:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking not configured")
                    if item.starts_at is None:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pick a time for the booking")
                    btype = await conn.fetchrow(
                        "SELECT id, duration_minutes, status, price_cents, pricing_mode, requires_approval, "
                        "buffer_minutes, min_notice_minutes, max_advance_days "
                        "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
                        product["booking_type_id"], site["id"],
                    )
                    if btype is None or btype["status"] != "active":
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking unavailable")
                    if btype["requires_approval"]:
                        order_requires_approval = True
                    validate_intake(loads_list(product["intake_fields"]), intake)
                    # Paid by card: held until the payment lands, instead of
                    # confirmed for an order that may never be paid.
                    booking = await create_booking_in_tx(
                        conn, site, btype, item.starts_at, body.customer_name, email, body.note,
                        hold=takes_cards and (product["price_cents"] or 0) > 0,
                    )
                    booking_id = booking["id"]

                # Server-authoritative option pricing: validate the selected
                # option ids against this product's live groups, fold the signed
                # deltas into the unit price BEFORE the discount, snapshot the
                # choice for the order line.
                try:
                    opt_delta, opt_snapshot = validate_and_price_options(
                        opt_groups_by_product.get(item.product_id, []), item.selected_option_ids,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                dpct = best_discount_percent(
                    discounts, kind="product", target_id=str(item.product_id), on_date=today,
                )
                unit_price = apply_discount_cents(max(0, product["price_cents"] + opt_delta), dpct)
                line_rows.append(
                    (item.product_id, product["name"], unit_price, qty, f, intake, booking_id,
                     opt_snapshot, item.selected_option_ids or [], stock_taken, options_taken)
                )
                on_sale.append(bool(dpct))

            subtotal = order_subtotal((unit, qty) for (_, _, unit, qty, *_rest) in line_rows)

            # Selling gate, BEFORE the order row exists. It cannot live on the
            # Stripe branch below: that branch degrades to a manual pending
            # order on any Stripe failure, so "never connect Stripe" would
            # itself be the workaround for selling without a paid plan.
            # Scoped to paid carts on purpose — $0 bookings, RSVPs and lead-gen
            # forms are the free tier's whole value and must keep working.
            # `owner_ent` was resolved above the transaction; see the note there.
            if subtotal > 0:
                require_can_sell(owner_ent)

            # A promo code: checked and counted under its row lock, split over
            # the lines with no automatic discount, before tax and shipping.
            promo_code = normalize_code(getattr(body, "promo_code", None))
            promo, discount = None, 0
            shares = [0] * len(line_rows)
            if promo_code:
                if not owner_ent.has("promo_codes"):
                    raise refuse_promo("This store doesn't take promo codes.")
                promo = await find_code(conn, site["id"], promo_code, lock=True)
                line_totals = [unit * qty for (_p, _t, unit, qty, *_r) in line_rows]
                eligible = [not sale and total > 0 for sale, total in zip(on_sale, line_totals)]
                discount, reason = evaluate_promo(
                    promo, eligible_cents=sum(t for t, ok in zip(line_totals, eligible) if ok),
                    on_date=today, currency=order_currency or "USD",
                )
                if reason:
                    raise refuse_promo(reason)
                if promo["once_per_customer"] and await promo_used_by(conn, promo["id"], email):
                    raise refuse_promo("You've already used that code.")
                shares = allocate_promo(discount, line_totals, eligible)
                subtotal -= discount

            # Tax (per-site rate, physical lines only) + shipping come from the
            # same `cart_totals` the public quote endpoint uses, so a quote and
            # the order it becomes can never disagree. Tax is added as a Stripe
            # line item below so the charge matches the receipt total.
            tax_cfg = await conn.fetchrow(
                "SELECT tax_rate_bps, tax_label, shipping_flat_cents, "
                "shipping_free_threshold_cents, shipping_label, home_country "
                "FROM cappe_sites WHERE id = $1", site["id"]
            )
            cfg = dict(tax_cfg) if tax_cfg else {}
            tax_label = cfg.get("tax_label") or "Tax"
            shipping_label = cfg.get("shipping_label") or "Shipping"
            has_physical = any(f == "physical" for (_p, _t, _u, _q, f, *_r) in line_rows)
            address = getattr(body, "shipping_address", None) if has_physical else None
            ship_country, destination = None, None
            if has_physical:
                ship_country = _order_ship_country(body, address, cfg)
                destination = resolve_destination(
                    cfg, await load_zones(conn, site["id"], owner_ent), ship_country,
                )
                if destination is None:
                    raise not_shippable(ship_country)
            totals = cart_totals([
                {"unit_price_cents": unit, "quantity": qty, "fulfillment": fulfillment, "promo_discount_cents": share}
                for (_pid, _title, unit, qty, fulfillment, *_rest), share in zip(line_rows, shares)
            ], cfg, destination)
            tax_cents, shipping_cents, total_cents = totals["tax_cents"], totals["shipping_cents"], totals["total_cents"]
            order = await conn.fetchrow(
                """INSERT INTO cappe_orders
                       (site_id, customer_email, customer_name, status, subtotal_cents, tax_cents,
                        shipping_cents, total_cents, currency, note, requires_approval, shipping_address,
                        ship_country, promo_code, discount_cents)
                   VALUES ($1, $2, $3, 'pending', $4, $5, $6, $7, $8, $9, $10, $11::jsonb, $12, $13, $14)
                   RETURNING id, status, subtotal_cents, tax_cents, shipping_cents, total_cents,
                             currency, access_token, requires_approval, ship_country""",
                site["id"], email, body.customer_name, subtotal, tax_cents, shipping_cents,
                total_cents, order_currency or "USD", body.note, order_requires_approval,
                # The buyer's address, when the storefront asked for it (a
                # physical order the store collects payment for itself — Stripe
                # collects it otherwise, and the paid webhook fills it in).
                # Stored in Stripe's shape so the dashboard reads one format.
                json.dumps(address.as_stripe_shape(ship_country)) if address is not None else None,
                ship_country, promo_code if promo else None, discount,
            )
            if promo:
                await redeem_promo(
                    conn, promo=promo, site_id=site["id"], order_id=order["id"], email=email,
                    discount_cents=discount,
                )
            if shopper:
                await conn.execute("UPDATE cappe_orders SET shopper_id=$1 WHERE id=$2 AND site_id=$3",
                                   shopper["id"], order["id"], site["id"])
            for (product_id, title, unit_price, qty, f, intake, booking_id, opt_snapshot, sel_ids,
                 stock_taken, options_taken), share in zip(line_rows, shares):
                await conn.execute(
                    """INSERT INTO cappe_order_items
                           (order_id, site_id, product_id, title, unit_price_cents, quantity,
                            fulfillment, intake_answers, selected_options, booking_id, selected_option_ids,
                            stock_decremented, decremented_option_ids, promo_discount_cents)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::uuid[], $14)""",
                    order["id"], site["id"], product_id, title, unit_price, qty,
                    f, json.dumps(intake), json.dumps(opt_snapshot), booking_id, sel_ids,
                    stock_taken, options_taken, share,
                )

    # Low-stock alert to the owner (stock was decremented at order creation,
    # regardless of the payment path below).
    if low_stock_hits and owner and owner["email"]:
        background.add_task(
            send_cappe_low_stock_email, owner["email"], owner["name"], site["name"],
            low_stock_hits, dashboard_url(f"/sites/{site['id']}/shop"),
        )

    # Stripe renders success/cancel URLs on its own hosted checkout page, and
    # this route is anonymous — so an attacker could point a real, branded
    # Stripe page at any address they like. The storefront widget only ever
    # knows its own published origin; anything else falls back to the site's
    # canonical home rather than 400-ing a buyer mid-purchase.
    allowed_origins = site_origins(site)
    site_home = f"{allowed_origins[0]}/" if allowed_origins else None
    return_urls_requested = bool(body.success_url and body.cancel_url)
    success_url = url_within_origins(body.success_url, allowed_origins) or site_home
    cancel_url = url_within_origins(body.cancel_url, allowed_origins) or site_home
    if return_urls_requested and (success_url != body.success_url or cancel_url != body.cancel_url):
        logger.warning(
            "cappe checkout: off-site return URL rejected for site %s", site["id"]
        )
    success_url, cancel_url = bind_return_urls(success_url, cancel_url, site, order["access_token"])
    # An order that waits for the owner's approval is NOT sent to Stripe now.
    # It used to be: the buyer was charged at once, the order went `paid` and
    # dropped out of the approval queue — "approve each order" approved
    # nothing. It stays pending; accepting it emails the buyer a link to pay
    # (POST /public/orders/{token}/pay).
    can_pay = bool(
        order["subtotal_cents"] > 0 and not order["requires_approval"]
        and owner and owner["stripe_account_id"] and owner["stripe_charges_enabled"]
        and return_urls_requested and success_url and cancel_url
    )
    checkout_url = None
    if can_pay:
        try:
            sess = await open_order_checkout(
                order=order, line_rows=line_rows, owner=owner, owner_ent=owner_ent,
                success_url=success_url, cancel_url=cancel_url, email=email, shopper=shopper,
                has_physical=has_physical, tax_label=tax_label, shipping_label=shipping_label,
                line_discounts=shares,
            )
            checkout_url = sess.get("url")
        except CappeStripeError as exc:
            # The buyer asked to pay by card and we could not open the payment
            # page. Falling through to the unpaid flow told them "Order
            # placed", emailed a receipt for money never taken, and left stock
            # held by an order the abandoned-order reaper cannot see (it has no
            # Stripe session). Undo the order and say what actually happened.
            logger.error(
                "cappe checkout: could not open Stripe Checkout for order %s (site %s): %s",
                order["id"], site["id"], exc,
            )
            await release_unpaid_order(order["id"], site["id"])
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Card payments are temporarily unavailable, so your order was not placed "
                       "and you have not been charged. Please try again in a few minutes.",
            )

    if not checkout_url:
        # Legacy / unpaid flow: notify now (receipt → customer, alert → creator).
        items_summary = build_order_items_summary(
            [{"title": t, "quantity": q} for (_pid, t, _u, q, *_r) in line_rows]
        )
        # Per-recipient throttle: this receipt goes to a caller-supplied address on
        # an unauthenticated endpoint, so cap sends per recipient to stop IP-rotating
        # email-bomb abuse. The order is created regardless; only the email is gated.
        if email and await check_recipient_send_ok(email):
            takes_cards = bool(owner and owner["stripe_account_id"] and owner["stripe_charges_enabled"])
            background.add_task(
                send_cappe_order_receipt_email, email, body.customer_name, site["name"],
                items_summary, order["total_cents"], order["currency"], order["requires_approval"],
                order_page_url(site, order["access_token"]),
                # Who settles the money next, which the email has to say.
                "free" if order["subtotal_cents"] <= 0 else ("card_after_approval" if takes_cards else "store"),
            )
        if owner and owner["email"]:
            background.add_task(
                send_cappe_order_alert_email, owner["email"], owner["name"], site["name"],
                body.customer_name, order["total_cents"], order["currency"],
                dashboard_url(f"/sites/{site['id']}/orders"),
            )

    return {
        "order_id": str(order["id"]),
        "order_token": order["access_token"],
        "status": order["status"],
        "subtotal_cents": order["subtotal_cents"],
        "currency": order["currency"],
        "requires_approval": order["requires_approval"],
        "checkout_url": checkout_url,
    }
