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


def best_discount_percent(
    discounts: Sequence[dict],
    *,
    kind: str,                       # 'booking_type' or 'product'
    target_id: Optional[str],
    on_date: date,
) -> int:
    """Highest applicable percent-off for one offering, else 0.

    A discount applies when it's active, within its date window on `on_date`,
    and its scope matches — `all` (everything), or the matching scope+target.
    """
    best = 0
    for d in discounts:
        if not d.get("active"):
            continue
        if not _in_window(d, on_date):
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
    """Reduce a price by `percent_off` percent, rounded to whole cents."""
    pct = max(0, min(int(percent_off or 0), 90))
    if pct == 0:
        return int(cents)
    return int(round(int(cents) * (100 - pct) / 100))


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
        "SELECT percent_off, scope, target_id, active, starts_on, ends_on "
        "FROM cappe_discounts WHERE site_id = $1 AND active = true",
        site_id,
    )
    return [
        {
            "percent_off": r["percent_off"], "scope": r["scope"],
            "target_id": str(r["target_id"]) if r["target_id"] else None,
            "active": r["active"], "starts_on": r["starts_on"], "ends_on": r["ends_on"],
        }
        for r in rows
    ]
