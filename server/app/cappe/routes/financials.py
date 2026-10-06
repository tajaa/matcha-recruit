"""Cappe finances — what a store took, refunded and kept.

There was nothing beyond the order list: no totals, no refunds view, no
export for an accountant, and the platform fee stored on every order was
never shown. This is read-only; every number is computed from the orders and
the refund ledger.

  * `GET /sites/{id}/financials` — totals, a day/week/month series, and the
    best-selling products for a window of days in the store's timezone and
    currency. On every plan.
  * `GET /sites/{id}/financials/export.csv` — the orders (or the refunds) in
    the window, one per row. Plan feature `financials_export`.
  * `GET /payments/balance` — the connected Stripe account's balance and
    recent payouts.

An order counts on the day it was paid (`paid_at`; `created_at` for orders
older than that column). A refund counts on the day it was made, so a refund
this month of a sale last month lowers this month — which is what the bank
account sees.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Annotated, Literal, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeFinancials
from ..services.entitlements import resolve_entitlements
from ..services.shipping import site_currency
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe
from ._shared import get_owned_site

router = APIRouter()

DEFAULT_DAYS = 30
MAX_DAYS = 731          # two years
MAX_EXPORT_ROWS = 50_000

# Orders that took money. A refunded order took it first; its refund is
# counted separately, on the day it was made.
_PAID = "o.status IN ('paid', 'fulfilled', 'refunded')"
_WHEN = "COALESCE(o.paid_at, o.created_at)"


def _tz(site) -> ZoneInfo:
    try:
        return ZoneInfo(site.get("timezone") or "UTC")
    except Exception:  # noqa: BLE001 — a bad stored zone falls back, never 500s
        return ZoneInfo("UTC")


def window(start: Optional[date], end: Optional[date], tz: ZoneInfo, today: date) -> tuple[date, date, datetime, datetime]:
    """The inclusive day range and its [from, to) instants in the store's zone.
    Default: the last 30 days up to today."""
    end = end or today
    start = start or (end - timedelta(days=DEFAULT_DAYS - 1))
    if start > end:
        raise HTTPException(status_code=422, detail="The start date must be on or before the end date.")
    if (end - start).days + 1 > MAX_DAYS:
        raise HTTPException(status_code=422, detail="Choose a window of at most two years.")
    lo = datetime.combine(start, time.min, tzinfo=tz)
    hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    return start, end, lo, hi


def periods(start: date, end: date, group: str) -> list[date]:
    """Every bucket start from `start` to `end`, so empty days still show."""
    if group == "day":
        first, step = start, None
    elif group == "week":
        first, step = start - timedelta(days=start.weekday()), None
    else:
        first, step = start.replace(day=1), "month"
    out, cur = [], first
    while cur <= end:
        out.append(cur)
        if step == "month":
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
        else:
            cur = cur + timedelta(days=1 if group == "day" else 7)
    return out


def _today(tz: ZoneInfo) -> date:
    return datetime.now(tz).date()


@router.get("/sites/{site_id}/financials", response_model=CappeFinancials)
async def financials(
    site_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
    start: Optional[date] = None,
    end: Optional[date] = None,
    group: Annotated[Literal["day", "week", "month"], Query()] = "day",
):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        tz = _tz(site)
        start, end, lo, hi = window(start, end, tz, _today(tz))
        cur = site_currency(site)
        args = (site_id, lo, hi, cur)
        totals = await conn.fetchrow(
            f"""SELECT COUNT(*) AS orders,
                       COALESCE(SUM(COALESCE(o.total_cents, o.subtotal_cents)), 0) AS gross,
                       COALESCE(SUM(o.subtotal_cents), 0) AS goods,
                       COALESCE(SUM(o.tax_cents), 0) AS tax,
                       COALESCE(SUM(o.shipping_cents), 0) AS shipping,
                       COALESCE(SUM(o.platform_fee_cents), 0) AS fees
                  FROM cappe_orders o
                 WHERE o.site_id = $1 AND {_PAID} AND {_WHEN} >= $2 AND {_WHEN} < $3
                   AND o.currency = $4""",
            *args,
        )
        refunds = await conn.fetchrow(
            """SELECT COALESCE(SUM(r.amount_cents), 0) AS amount, COUNT(*) AS n
                 FROM cappe_order_refunds r JOIN cappe_orders o ON o.id = r.order_id
                WHERE r.site_id = $1 AND r.status = 'succeeded'
                  AND r.created_at >= $2 AND r.created_at < $3 AND o.currency = $4""",
            *args,
        )
        trunc = {"day": "day", "week": "week", "month": "month"}[group]
        sales = await conn.fetch(
            f"""SELECT date_trunc('{trunc}', {_WHEN} AT TIME ZONE $5)::date AS period,
                       COUNT(*) AS orders,
                       COALESCE(SUM(COALESCE(o.total_cents, o.subtotal_cents)), 0) AS gross
                  FROM cappe_orders o
                 WHERE o.site_id = $1 AND {_PAID} AND {_WHEN} >= $2 AND {_WHEN} < $3
                   AND o.currency = $4
                 GROUP BY 1""",
            *args, str(tz),
        )
        refund_series = await conn.fetch(
            f"""SELECT date_trunc('{trunc}', r.created_at AT TIME ZONE $5)::date AS period,
                       COALESCE(SUM(r.amount_cents), 0) AS amount
                  FROM cappe_order_refunds r JOIN cappe_orders o ON o.id = r.order_id
                 WHERE r.site_id = $1 AND r.status = 'succeeded'
                   AND r.created_at >= $2 AND r.created_at < $3 AND o.currency = $4
                 GROUP BY 1""",
            *args, str(tz),
        )
        top = await conn.fetch(
            f"""SELECT (array_agg(i.product_id))[1] AS product_id, MAX(i.title) AS title,
                       SUM(i.quantity) AS units,
                       SUM(i.unit_price_cents * i.quantity - i.promo_discount_cents) AS revenue
                  FROM cappe_order_items i JOIN cappe_orders o ON o.id = i.order_id
                 WHERE o.site_id = $1 AND {_PAID} AND {_WHEN} >= $2 AND {_WHEN} < $3
                   AND o.currency = $4
                 GROUP BY COALESCE(i.product_id::text, i.title)
                 ORDER BY revenue DESC, units DESC
                 LIMIT 10""",
            *args,
        )
        other = await conn.fetchval(
            f"""SELECT COUNT(*) FROM cappe_orders o
                 WHERE o.site_id = $1 AND {_PAID} AND {_WHEN} >= $2 AND {_WHEN} < $3
                   AND o.currency <> $4""",
            *args,
        )
        ent = await resolve_entitlements(account.plan, conn=conn)

    by_sales = {r["period"]: r for r in sales}
    by_refunds = {r["period"]: r["amount"] for r in refund_series}
    series = [
        {"period": p, "orders": int((by_sales.get(p) or {}).get("orders") or 0),
         "gross_cents": int((by_sales.get(p) or {}).get("gross") or 0),
         "refunds_cents": int(by_refunds.get(p) or 0)}
        for p in periods(start, end, group)
    ]
    orders = int(totals["orders"] or 0)
    gross = int(totals["gross"] or 0)
    refunded = int(refunds["amount"] or 0)
    fees = int(totals["fees"] or 0)
    return {
        "currency": cur, "start": start, "end": end, "group": group,
        "orders": orders, "gross_cents": gross, "goods_cents": int(totals["goods"] or 0),
        "tax_cents": int(totals["tax"] or 0), "shipping_cents": int(totals["shipping"] or 0),
        "platform_fee_cents": fees, "refunds_cents": refunded, "refund_count": int(refunds["n"] or 0),
        "net_cents": gross - refunded - fees,
        "average_order_cents": gross // orders if orders else 0,
        "series": series,
        "top_products": [
            {"product_id": r["product_id"], "title": r["title"] or "Item",
             "units": int(r["units"] or 0), "revenue_cents": int(r["revenue"] or 0)}
            for r in top
        ],
        "other_currency_orders": int(other or 0),
        "export_enabled": ent.has("financials_export"),
    }


def _cell(value) -> str:
    """A CSV cell a spreadsheet won't run: text starting with a formula
    character is prefixed with an apostrophe (buyer names are typed by
    anyone)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _money(cents) -> str:
    return f"{(cents or 0) / 100:.2f}"


@router.get("/sites/{site_id}/financials/export.csv")
async def export_financials(
    site_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
    start: Optional[date] = None,
    end: Optional[date] = None,
    kind: Annotated[Literal["orders", "refunds"], Query()] = "orders",
):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        if not (await resolve_entitlements(account.plan, conn=conn)).has("financials_export"):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Exporting your finances isn't included in your plan.",
            )
        tz = _tz(site)
        start, end, lo, hi = window(start, end, tz, _today(tz))
        if kind == "orders":
            rows = await conn.fetch(
                f"""SELECT {_WHEN} AS at, o.receipt_number, o.id, o.status, o.customer_name,
                           o.customer_email, o.currency, o.subtotal_cents, o.tax_cents,
                           o.shipping_cents, COALESCE(o.total_cents, o.subtotal_cents) AS total_cents,
                           o.promo_code, o.discount_cents,
                           o.refunded_cents, o.platform_fee_cents, o.ship_country,
                           (o.stripe_payment_intent IS NOT NULL) AS card
                      FROM cappe_orders o
                     WHERE o.site_id = $1 AND {_PAID} AND {_WHEN} >= $2 AND {_WHEN} < $3
                     ORDER BY {_WHEN}
                     LIMIT {MAX_EXPORT_ROWS}""",
                site_id, lo, hi,
            )
        else:
            rows = await conn.fetch(
                f"""SELECT r.created_at AS at, o.receipt_number, o.id, r.amount_cents, o.currency,
                           r.source, r.reason, r.stripe_refund_id, o.customer_email
                      FROM cappe_order_refunds r JOIN cappe_orders o ON o.id = r.order_id
                     WHERE r.site_id = $1 AND r.status = 'succeeded'
                       AND r.created_at >= $2 AND r.created_at < $3
                     ORDER BY r.created_at
                     LIMIT {MAX_EXPORT_ROWS}""",
                site_id, lo, hi,
            )
    buf = io.StringIO()
    out = csv.writer(buf)
    if kind == "orders":
        out.writerow(["Date", "Order", "Status", "Customer", "Email", "Currency", "Goods", "Tax",
                      "Shipping", "Total", "Refunded", "Platform fee", "Ships to", "Paid by",
                      "Promo code", "Discount"])
        for r in rows:
            out.writerow([_cell(v) for v in (
                r["at"].astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                r["receipt_number"] or str(r["id"])[:8].upper(), r["status"], r["customer_name"],
                r["customer_email"], r["currency"], _money(r["subtotal_cents"]), _money(r["tax_cents"]),
                _money(r["shipping_cents"]), _money(r["total_cents"]), _money(r["refunded_cents"]),
                _money(r["platform_fee_cents"]), r["ship_country"], "card" if r["card"] else "offline",
                r.get("promo_code"), _money(r.get("discount_cents")),
            )])
    else:
        out.writerow(["Date", "Order", "Amount", "Currency", "Made in", "Reason", "Stripe refund", "Email"])
        for r in rows:
            out.writerow([_cell(v) for v in (
                r["at"].astimezone(tz).strftime("%Y-%m-%d %H:%M"),
                r["receipt_number"] or str(r["id"])[:8].upper(), _money(r["amount_cents"]), r["currency"],
                {"dashboard": "Gummfit", "manual": "Gummfit (offline)", "stripe": "Stripe",
                 "dispute": "Dispute", "legacy": "Gummfit"}.get(r["source"], r["source"]),
                r["reason"], r["stripe_refund_id"], r["customer_email"],
            )])
    name = f"{site.get('slug') or 'store'}-{kind}-{start.isoformat()}-to-{end.isoformat()}.csv"
    return Response(
        content=buf.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"},
    )


@router.get("/payments/balance")
async def payments_balance(account: CappeAccount = Depends(require_cappe_account)):
    """The connected Stripe account's balance and last payouts."""
    async with get_connection() as conn:
        acct_id = await conn.fetchval("SELECT stripe_account_id FROM cappe_accounts WHERE id = $1", account.id)
    if not acct_id:
        return {"connected": False, "available": [], "pending": [], "payouts": []}
    try:
        return {"connected": True, **(await get_cappe_stripe().connected_balance(acct_id))}
    except CappeStripeError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Couldn't reach Stripe for your balance. Try again in a moment.",
        )
