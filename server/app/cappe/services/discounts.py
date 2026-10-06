"""Discount resolution + application.

A creator sets promotional discounts (percent off) scoped to everything, one
booking type, or one product, each gated by an `active` flag and an optional
date window. At quote/order time the *single best* matching discount applies —
discounts don't stack — and it's applied on top of any rate-rule pricing.

`best_discount_percent`/`apply_discount_cents`/`site_today` are pure (no DB,
no I/O — unit-testable in isolation); `fetch_active_discounts` is the one
DB-touching fetch that feeds them.
"""
from datetime import date, timezone
from typing import Optional, Sequence
from zoneinfo import ZoneInfo


def _in_window(d: dict, on_date: date) -> bool:
    s, e = d.get("starts_on"), d.get("ends_on")
    if s and on_date < s:
        return False
    if e and on_date > e:
        return False
    return True


def _at_location(d: dict, kind: str, location_id) -> bool:
    """Whether a discount is in force where the sale happens.

    A discount with no location applies everywhere. One created for a location
    applies to bookings AT that location only — and never to products: the
    online shop has no location, so "10% off at the Mission salon" used to take
    10% off everything the shop sold.
    """
    where = d.get("location_id")
    if where is None:
        return True
    if kind != "booking_type" or location_id is None:
        return False
    return str(where) == str(location_id)


def best_discount_percent(
    discounts: Sequence[dict],
    *,
    kind: str,                       # 'booking_type' or 'product'
    target_id: Optional[str],
    on_date: date,
    location_id=None,                # the booking's location, when it has one
) -> int:
    """Highest applicable percent-off for one offering, else 0.

    A discount applies when it's active, within its date window on `on_date`,
    in force at `location_id` (see `_at_location`), and its scope matches —
    `all` (everything), or the matching scope+target.
    """
    best = 0
    for d in discounts:
        if not d.get("active"):
            continue
        if not _in_window(d, on_date):
            continue
        if not _at_location(d, kind, location_id):
            continue
        scope = d.get("scope")
        if scope == "all":
            pass
        elif scope == kind and target_id is not None and str(d.get("target_id")) == str(target_id):
            pass
        else:
            continue
        pct = int(d.get("percent_off") or 0)
        if pct > best:
            best = pct
    return min(best, 90)


def apply_discount_cents(cents: int, percent_off: int) -> int:
    """Reduce a price by `percent_off` percent, rounded HALF-UP to whole cents.

    Integer arithmetic on purpose. This used to be `round(x / 100)`, which is
    banker's rounding in Python (2.5 → 2) while the storefront script priced
    the button with JavaScript's `Math.round` (2.5 → 3): on any price that
    lands on half a cent the page showed one amount and the order charged
    another. `(n + 50) // 100` is half-up for the non-negative integers this
    takes, and the storefront (`render/assets/store.js`) computes the same
    expression — `tests/cappe/test_cappe_pricing.py` pins the two together.
    """
    pct = max(0, min(int(percent_off or 0), 90))
    if pct == 0:
        return int(cents)
    return (int(cents) * (100 - pct) + 50) // 100


def site_today(now_utc, tz_name) -> date:
    """Today's date in the site's timezone — discount eligibility is judged on
    when the booking/order is *made*, not the appointment date."""
    try:
        return now_utc.astimezone(ZoneInfo(tz_name or "UTC")).date()
    except Exception:
        return now_utc.astimezone(timezone.utc).date()


async def fetch_active_discounts(conn, site_id) -> list[dict]:
    """Active discounts for a site, shaped for `best_discount_percent`."""
    rows = await conn.fetch(
        "SELECT percent_off, scope, target_id, active, starts_on, ends_on, location_id "
        "FROM cappe_discounts WHERE site_id = $1 AND active = true",
        site_id,
    )
    return [
        {
            "percent_off": r["percent_off"], "scope": r["scope"],
            "target_id": str(r["target_id"]) if r["target_id"] else None,
            "active": r["active"], "starts_on": r["starts_on"], "ends_on": r["ends_on"],
            "location_id": str(r["location_id"]) if r["location_id"] else None,
        }
        for r in rows
    ]
