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
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from .common import loads_list
from .discounts import apply_discount_cents, best_discount_percent, fetch_active_discounts, site_today
from .email import (
    build_order_items_summary,
    dashboard_url,
    send_cappe_low_stock_email,
    send_cappe_order_alert_email,
    send_cappe_order_receipt_email,
)
from .inventory import log_adjustment as _inv_log
from .options import fetch_option_groups, validate_and_price_options
from .entitlements import (
    fee_cents as entitlement_fee_cents,
    require_can_sell,
    resolve_entitlements,
)
from .stripe_connect import CappeStripeError, get_cappe_stripe


def order_subtotal(line_items: Iterable[tuple[int, int]]) -> int:
    """Sum unit_price_cents * quantity over (price, qty) pairs."""
    return sum(int(price) * int(qty) for price, qty in line_items)


def compute_shipping_cents(
    *, has_physical: bool, subtotal_cents: int, flat_cents: int,
    free_threshold_cents: int | None,
) -> int:
    """Flat per-site shipping for carts with a physical line; zero when the
    free-shipping threshold is met. Threshold compares the GOODS subtotal
    (pre-tax), matching what the buyer sees advertised ("free over $50")."""
    if not has_physical or flat_cents <= 0:
        return 0
    if free_threshold_cents is not None and subtotal_cents >= free_threshold_cents:
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
        "SELECT a.id, a.plan, a.email, a.name, a.stripe_account_id, a.stripe_charges_enabled "
        "FROM cappe_accounts a JOIN cappe_sites s ON s.account_id = a.id WHERE s.id = $1",
        site_id,
    )


async def check_recipient_send_ok(email: str | None) -> bool:
    """Per-recipient throttle for outbound transactional email on PUBLIC,
    unauthenticated endpoints (order receipts, booking confirmations). Keyed on
    the RECIPIENT (not the caller IP) so rotating source IPs can't flood one
    victim's inbox from our sender. Never blocks the underlying action — the
    order/booking is still created; only the email is skipped past the cap.
    Returns True when it's OK to send."""
    if not email:
        return False
    try:
        await check_rate_limit(email.lower(), "cappe_recipient_email", 5, 3600)
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


async def resolve_booking_slot(
    conn, site, btype, starts_at, ends_at_override=None, exclude_booking_id=None, staff_id=None,
    location_id=None, tz=None,
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
    use that location's timezone (None → site timezone)."""
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
    if s_utc <= now_utc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a future time")
    if bt["spans_midnight"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking can't span midnight")

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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time is outside availability")

    # Overlap is per shared RESOURCE, not per booking type. A staffed booking's
    # resource is the STAFF MEMBER — a person can't be in two places at once, so
    # they conflict with ANY overlapping booking of theirs regardless of service
    # type (this is the bug being fixed: the old `booking_type_id = $2` narrowing
    # let one staffer offering two types be double-booked for the same window
    # under each type). An UNstaffed booking has no person to contend for, so it
    # falls back to the (location, type) slot it occupies — that way two
    # resource-less service types can still run in parallel, while a second
    # booking of the SAME offering in the same slot is still blocked.
    # NOTE: this app-level check is the primary guard; the DB unique index
    # (site_id, booking_type_id, staff_id, location_id, starts_at) is only an
    # exact-start backstop and does NOT enforce these cross-type semantics — a
    # GiST range-exclusion constraint would be the belt-and-suspenders follow-up.
    buf_min = int(btype.get("buffer_minutes") or 0)
    overlap = await conn.fetchval(
        """SELECT 1 FROM cappe_bookings
           WHERE site_id = $1 AND status IN ('pending', 'confirmed')
             AND ($5::uuid IS NULL OR id <> $5)
             AND (
                   ($6::uuid IS NOT NULL AND staff_id = $6)
                OR ($6::uuid IS NULL AND staff_id IS NULL
                    AND location_id IS NOT DISTINCT FROM $8
                    AND booking_type_id = $2)
             )
             AND tstzrange(starts_at, ends_at)
                 && tstzrange($3 - ($7 * interval '1 minute'), $4 + ($7 * interval '1 minute'))
           LIMIT 1""",
        site["id"], btype["id"], s_utc, e_utc, exclude_booking_id, staff_id, buf_min, location_id,
    )
    if overlap:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")

    # Price the booked window (flat → base; hourly → per-minute × rate rules),
    # then apply the best active discount judged on today (location timezone).
    rules = await fetch_rate_rules(conn, site["id"], btype["id"], location_id)
    quote_cents = booking_quote_cents(
        btype.get("price_cents") or 0, pricing_mode, bt["local_start"], bt["local_end"], rules
    )
    discounts = await fetch_active_discounts(conn, site["id"])
    pct = best_discount_percent(
        discounts, kind="booking_type", target_id=str(btype["id"]),
        on_date=site_today(now_utc, tz),
    )
    quote_cents = apply_discount_cents(quote_cents, pct)

    requires_approval = bool(btype.get("requires_approval"))
    return {
        "s_utc": s_utc, "e_utc": e_utc, "quote_cents": quote_cents,
        "requires_approval": requires_approval,
        # Approval-required types land 'pending' (creator queue); others
        # auto-confirm so an open calendar books straight through.
        "booking_status": "pending" if requires_approval else "confirmed",
    }


async def create_booking_in_tx(
    conn, site, btype, starts_at, customer_name, customer_email, note,
    ends_at_override=None, rider_acknowledged=False, rider_snapshot=None, staff_id=None,
    location_id=None, tz=None,
):
    """Validate + price + insert a booking. MUST run inside a transaction.
    Shared by the public booking intake and booking-fulfillment order lines."""
    slot = await resolve_booking_slot(
        conn, site, btype, starts_at, ends_at_override, staff_id=staff_id, location_id=location_id, tz=tz,
    )
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


async def create_public_order(site, body, background) -> dict:
    """Create a pending order for a mixed cart (physical / digital / service /
    booking). Prices + totals are recomputed server-side from the live product
    rows; payment is stubbed (order lands `pending`). Inventory is decremented
    only for physical lines; booking lines create a scheduled booking; service
    lines validate intake answers. All in one transaction.

    `site` is the route's already-`_published_site`-resolved row. Opens its own
    connection (closed before the Stripe Checkout call below, so a slow/failed
    call to Stripe never holds a pooled connection) — mirrors the original
    route's own two-connection shape.
    """
    email = str(body.customer_email).strip().lower()

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
        owner_ent = await resolve_entitlements(owner["plan"] if owner else None, conn=conn)
        async with conn.transaction():
            order_currency = None
            order_requires_approval = False  # any line needing creator review holds the whole order
            low_stock_hits: list[tuple[str, int]] = []  # (product name, balance) for the owner alert
            # (product_id, title, unit_price, qty, fulfillment, intake_answers, booking_id)
            line_rows = []
            # Batch-load option groups for every product in the cart once, instead
            # of one query per line item inside the loop below (N+1).
            opt_groups_by_product = await fetch_option_groups(
                conn, [it.product_id for it in body.items]
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

                if f == "physical":
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
                        await _inv_log(
                            conn, site_id=site["id"], product_id=item.product_id,
                            delta=-qty, balance_after=new_bal, reason="sale",
                        )
                        thr = product["low_stock_threshold"]
                        if thr is not None and new_bal <= thr:
                            low_stock_hits.append((product["name"], new_bal))
                    # Per-variant stock: decrement each selected option that tracks it.
                    for oid in (item.selected_option_ids or []):
                        inv = await conn.fetchval(
                            "SELECT inventory FROM cappe_product_options "
                            "WHERE id = $1 AND site_id = $2 FOR UPDATE",
                            oid, site["id"],
                        )
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
                        await _inv_log(
                            conn, site_id=site["id"], product_id=item.product_id, option_id=oid,
                            delta=-qty, balance_after=inv - qty, reason="sale",
                        )
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
                        "SELECT id, duration_minutes, status, price_cents, pricing_mode, requires_approval "
                        "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
                        product["booking_type_id"], site["id"],
                    )
                    if btype is None or btype["status"] != "active":
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking unavailable")
                    if btype["requires_approval"]:
                        order_requires_approval = True
                    validate_intake(loads_list(product["intake_fields"]), intake)
                    booking = await create_booking_in_tx(
                        conn, site, btype, item.starts_at, body.customer_name, email, body.note,
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
                     opt_snapshot, item.selected_option_ids or [])
                )

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

            # Tax (per-site rate, applied to physical/taxable lines only). Added
            # as a Stripe line item below so the charge matches the receipt total.
            tax_cfg = await conn.fetchrow(
                "SELECT tax_rate_bps, tax_label, shipping_flat_cents, "
                "shipping_free_threshold_cents, shipping_label "
                "FROM cappe_sites WHERE id = $1", site["id"]
            )
            tax_rate_bps = int(tax_cfg["tax_rate_bps"]) if tax_cfg else 0
            tax_label = (tax_cfg["tax_label"] if tax_cfg else None) or "Tax"
            taxable = sum(unit * qty for (_p, _t, unit, qty, f, *_r) in line_rows if f == "physical")
            tax_cents = (taxable * tax_rate_bps) // 10000 if tax_rate_bps > 0 else 0
            has_physical = any(f == "physical" for (_p, _t, _u, _q, f, *_r) in line_rows)
            shipping_cents = compute_shipping_cents(
                has_physical=has_physical,
                subtotal_cents=subtotal,
                flat_cents=int(tax_cfg["shipping_flat_cents"]) if tax_cfg else 0,
                free_threshold_cents=tax_cfg["shipping_free_threshold_cents"] if tax_cfg else None,
            )
            shipping_label = (tax_cfg["shipping_label"] if tax_cfg else None) or "Shipping"
            total_cents = subtotal + tax_cents + shipping_cents
            order = await conn.fetchrow(
                """INSERT INTO cappe_orders
                       (site_id, customer_email, customer_name, status, subtotal_cents, tax_cents,
                        shipping_cents, total_cents, currency, note, requires_approval)
                   VALUES ($1, $2, $3, 'pending', $4, $5, $6, $7, $8, $9, $10)
                   RETURNING id, status, subtotal_cents, tax_cents, shipping_cents, total_cents,
                             currency, access_token, requires_approval""",
                site["id"], email, body.customer_name, subtotal, tax_cents, shipping_cents,
                total_cents, order_currency or "USD", body.note, order_requires_approval,
            )
            for product_id, title, unit_price, qty, f, intake, booking_id, opt_snapshot, sel_ids in line_rows:
                await conn.execute(
                    """INSERT INTO cappe_order_items
                           (order_id, site_id, product_id, title, unit_price_cents, quantity,
                            fulfillment, intake_answers, selected_options, booking_id, selected_option_ids)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)""",
                    order["id"], site["id"], product_id, title, unit_price, qty,
                    f, json.dumps(intake), json.dumps(opt_snapshot), booking_id, sel_ids,
                )

    # Low-stock alert to the owner (stock was decremented at order creation,
    # regardless of the payment path below).
    if low_stock_hits and owner and owner["email"]:
        background.add_task(
            send_cappe_low_stock_email, owner["email"], owner["name"], site["name"],
            low_stock_hits, dashboard_url(f"/sites/{site['id']}/shop"),
        )

    # If the order is payable AND the business has Stripe Connect ready AND the
    # storefront passed return URLs → create a Checkout Session (direct charge on
    # the connected account, 2% platform fee). The receipt waits for the paid
    # webhook (payments.py). Otherwise fall back to the legacy pending flow.
    pay_total = order["subtotal_cents"]
    can_pay = bool(
        pay_total > 0 and owner and owner["stripe_account_id"]
        and owner["stripe_charges_enabled"] and body.success_url and body.cancel_url
    )
    checkout_url = None
    if can_pay:
        cur = (order["currency"] or "USD").lower()
        # Per-plan take rate, from the entitlements resolved once above.
        # Computed ONCE here and handed to Stripe, so the number persisted on
        # the order is the same number Stripe actually takes.
        fee = entitlement_fee_cents(pay_total, owner_ent.platform_fee_bps)
        line_items = [
            {
                "price_data": {
                    "currency": cur,
                    "unit_amount": int(unit),
                    "product_data": {"name": (title or "Item")[:250]},
                },
                "quantity": int(qty),
            }
            for (_pid, title, unit, qty, *_r) in line_rows
        ]
        # Tax as its own line so the charged amount equals the receipt total.
        # The 2% platform fee stays on the goods subtotal (amount_cents below).
        if order["tax_cents"] and order["tax_cents"] > 0:
            line_items.append({
                "price_data": {
                    "currency": cur,
                    "unit_amount": int(order["tax_cents"]),
                    "product_data": {"name": tax_label[:120]},
                },
                "quantity": 1,
            })
        try:
            sess = await get_cappe_stripe().create_checkout_session(
                account_id=owner["stripe_account_id"],
                currency=cur,
                line_items=line_items,
                application_fee_cents=fee,
                success_url=body.success_url,
                cancel_url=body.cancel_url,
                metadata={"order_id": str(order["id"]), "platform_fee_cents": str(fee)},
                customer_email=email or None,
                collect_shipping_address=has_physical,
                shipping_option=(
                    {
                        "label": shipping_label if order["shipping_cents"] > 0 else "Free shipping",
                        "amount_cents": order["shipping_cents"],
                    }
                    if has_physical else None
                ),
            )
            checkout_url = sess.get("url")
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE cappe_orders SET stripe_session_id = $1, platform_fee_cents = $2, "
                    "updated_at = NOW() WHERE id = $3",
                    sess.get("id"), fee, order["id"],
                )
        except CappeStripeError:
            checkout_url = None  # fall back to the manual pending flow below

    if not checkout_url:
        # Legacy / unpaid flow: notify now (receipt → customer, alert → creator).
        items_summary = build_order_items_summary(
            [{"title": t, "quantity": q} for (_pid, t, _u, q, *_r) in line_rows]
        )
        # Per-recipient throttle: this receipt goes to a caller-supplied address on
        # an unauthenticated endpoint, so cap sends per recipient to stop IP-rotating
        # email-bomb abuse. The order is created regardless; only the email is gated.
        if email and await check_recipient_send_ok(email):
            background.add_task(
                send_cappe_order_receipt_email, email, body.customer_name, site["name"],
                items_summary, order["subtotal_cents"], order["currency"], order["requires_approval"],
            )
        if owner and owner["email"]:
            background.add_task(
                send_cappe_order_alert_email, owner["email"], owner["name"], site["name"],
                body.customer_name, order["subtotal_cents"], order["currency"],
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
