"""The buyer's order page — `/order/<token>` on the store's own host.

Where a buyer lands after paying, and what every order email links to. It used
to not exist: a paying buyer was sent back to the product page with nothing to
say the payment worked, a buyer of a digital product had no way to reach the
file they had paid for, and a buyer whose order needed approval had no way to
pay once it was approved.

Server-rendered from the order, in the site's theme, with none of the site's
own blocks: only our markup and our scripts run here. The token is in the URL,
so the response is never cached and never sends a referrer (see the route).
Everything a buyer or merchant typed is escaped.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Optional

from ..email import fmt_money, format_when
from .page import render_site_html

_ORDER_JS = (Path(__file__).parent / "assets" / "order.js").read_text(encoding="utf-8")

# Statuses after which what was bought is released to the buyer.
RELEASED = ("paid", "fulfilled")


def _safe_link(url: Any) -> Optional[str]:
    """Only http(s) links are rendered as links (a deliverable URL is
    owner-supplied and already https-validated; this is the second check)."""
    value = str(url or "").strip()
    return value if value.lower().startswith(("https://", "http://")) else None


def order_state(order: dict, *, takes_cards: bool, now: datetime) -> dict:
    """What the page says and offers for an order, as plain data.

    Returns {"headline", "lead", "can_pay", "poll"}: `can_pay` shows the Pay
    button; `poll` re-checks the order for a few seconds (a buyer back from
    Stripe usually arrives before the payment webhook does)."""
    status = order["status"]
    store = order.get("site_name") or "the store"
    total = fmt_money(order.get("total_cents") or order.get("subtotal_cents") or 0, order.get("currency") or "USD")
    owes = (order.get("subtotal_cents") or 0) > 0
    pay_by = order.get("pay_by")
    if status == "paid":
        return {"headline": "Thank you — your order is confirmed",
                "lead": f"{store} has your order. A receipt is on its way to your email.",
                "can_pay": False, "poll": False}
    if status == "fulfilled":
        return {"headline": "Your order is complete",
                "lead": f"{store} has fulfilled your order.", "can_pay": False, "poll": False}
    if status == "refunded":
        return {"headline": "This order was refunded", "lead": f"{store} refunded this order.",
                "can_pay": False, "poll": False}
    if status == "declined":
        reason = order.get("decline_reason")
        return {"headline": f"{store} couldn't accept this order",
                "lead": "It was cancelled and you were not charged." + (f" Reason: {reason}" if reason else ""),
                "can_pay": False, "poll": False}
    if status == "cancelled":
        return {"headline": "This order was cancelled",
                "lead": "Nothing more will be charged for it.", "can_pay": False, "poll": False}
    # pending
    if order.get("requires_approval"):
        return {"headline": f"Waiting for {store} to approve your order",
                "lead": ("You haven't been charged. If they accept it, you'll get an email with a link to pay."
                         if takes_cards and owes else "They'll email you once they've reviewed it."),
                "can_pay": False, "poll": False}
    if not owes:
        return {"headline": "Your order is confirmed", "lead": f"{store} has your order.",
                "can_pay": False, "poll": False}
    if not takes_cards:
        return {"headline": "Order received",
                "lead": f"{store} will be in touch about payment and delivery. Nothing has been charged.",
                "can_pay": False, "poll": False}
    if pay_by is not None:
        if pay_by < now:
            return {"headline": "The time to pay for this order has passed",
                    "lead": f"Contact {store} if you'd still like it.", "can_pay": False, "poll": False}
        return {"headline": f"{store} accepted your order",
                "lead": f"Pay {total} to complete it by {format_when(pay_by, order.get('timezone'))}.",
                "can_pay": True, "poll": False}
    # A card order that hasn't been confirmed paid: usually the buyer is back
    # from Stripe a moment before the webhook. Check again for a little while;
    # if they never finished paying, they can pay from here.
    return {"headline": "Confirming your payment…",
            "lead": "This usually takes a few seconds. If you didn't finish paying, you can pay below.",
            "can_pay": True, "poll": True}


def _items_html(order: dict, items: list[dict]) -> str:
    released = order["status"] in RELEASED
    tz = order.get("timezone")
    currency = order.get("currency") or "USD"
    rows = []
    for it in items:
        opts = ", ".join(str(o.get("name")) for o in (it.get("selected_options") or []) if o.get("name"))
        extra = []
        if it.get("booking_starts_at"):
            extra.append(f'<div class="cz-order__note">{escape(format_when(it["booking_starts_at"], tz))}</div>')
        download = _safe_link(it.get("download_url")) if released else None
        if download:
            extra.append(f'<a class="cz-btn cz-btn--ghost cz-order__get" href="{escape(download, quote=True)}" '
                         f'rel="noopener noreferrer" target="_blank">Download</a>')
        deliverable = _safe_link(it.get("deliverable_url")) if released else None
        if deliverable:
            extra.append(f'<a class="cz-btn cz-btn--ghost cz-order__get" href="{escape(deliverable, quote=True)}" '
                         f'rel="noopener noreferrer" target="_blank">Open your delivery</a>')
        elif it.get("fulfillment") == "digital" and not released:
            extra.append('<div class="cz-order__note">Your download appears here once payment is confirmed.</div>')
        line_total = (it.get("unit_price_cents") or 0) * (it.get("quantity") or 1)
        rows.append(
            '<li class="cz-order__item"><div class="cz-order__line">'
            f'<span>{escape(str(it.get("quantity") or 1))} × {escape(str(it.get("title") or "Item"))}'
            + (f'<span class="cz-order__opts">{escape(opts)}</span>' if opts else "")
            + f'</span><span>{escape(fmt_money(line_total, currency))}</span></div>'
            + "".join(extra) + "</li>"
        )
    return f'<ul class="cz-order__items">{"".join(rows)}</ul>'


def _totals_html(order: dict) -> str:
    cur = order.get("currency") or "USD"
    discount = int(order.get("discount_cents") or 0)
    rows = [("Subtotal", (order.get("subtotal_cents") or 0) + discount)]
    if discount:
        code = order.get("promo_code")
        rows.append((f"Discount ({code})" if code else "Discount", -discount))
    if order.get("tax_cents"):
        rows.append((order.get("tax_label") or "Tax", order["tax_cents"]))
    if order.get("shipping_cents"):
        rows.append((order.get("shipping_label") or "Shipping", order["shipping_cents"]))
    body = "".join(
        f"<div><dt>{escape(label)}</dt><dd>{'−' if c < 0 else ''}{escape(fmt_money(abs(c), cur))}</dd></div>"
        for label, c in rows
    )
    total = order.get("total_cents") or order.get("subtotal_cents") or 0
    body += f'<div class="cz-order__total"><dt>Total</dt><dd>{escape(fmt_money(total, cur))}</dd></div>'
    if order.get("refunded_cents"):
        body += f"<div><dt>Refunded</dt><dd>−{escape(fmt_money(order['refunded_cents'], cur))}</dd></div>"
    return f'<dl class="cz-order__totals">{body}</dl>'


def _shipping_html(order: dict) -> str:
    parts = []
    ship = order.get("shipping_address") if isinstance(order.get("shipping_address"), dict) else None
    if ship:
        addr = ship.get("address") if isinstance(ship.get("address"), dict) else {}
        lines = [ship.get("name"), addr.get("line1"), addr.get("line2"),
                 " ".join(x for x in (addr.get("city"), addr.get("state"), addr.get("postal_code")) if x),
                 addr.get("country")]
        parts.append('<div><h2 class="cz-order__h">Shipping to</h2><p>'
                     + "<br>".join(escape(str(x)) for x in lines if x) + "</p></div>")
    track = " ".join(x for x in (order.get("carrier"), order.get("tracking_number")) if x)
    if track:
        parts.append(f'<div><h2 class="cz-order__h">Tracking</h2><p>{escape(track)}</p></div>')
    return f'<div class="cz-order__ship">{"".join(parts)}</div>' if parts else ""


def _reviews_html(items: list[dict]) -> str:
    """A review form for each product in a paid order — a verified purchase.
    Products already reviewed from this order, or no longer sold, are left out."""
    seen, forms = set(), []
    for it in items:
        pid = it.get("product_id")
        if not pid or not it.get("reviewable") or it.get("reviewed") or str(pid) in seen:
            continue
        seen.add(str(pid))
        stars = "".join(f'<option value="{n}">{"★" * n}</option>' for n in (5, 4, 3, 2, 1))
        forms.append(
            f'<form class="cz-order__review" data-czreview data-product="{escape(str(pid), quote=True)}">'
            f'<div class="cz-order__line"><b>{escape(str(it.get("title") or "Item"))}</b>'
            f'<select class="cz-field" data-rating aria-label="Rating">{stars}</select></div>'
            '<textarea class="cz-field" data-body rows="2" maxlength="2000" required '
            'placeholder="What did you think?" aria-label="Your review"></textarea>'
            '<input class="cz-field" data-name maxlength="120" required placeholder="Your name" aria-label="Your name" />'
            '<button class="cz-btn cz-btn--ghost" type="submit">Post review</button>'
            '<p class="cz-msg" role="status"></p></form>'
        )
    if not forms:
        return ""
    return ('<div class="cz-order__reviews"><h2 class="cz-order__h">Review what you bought</h2>'
            '<p class="cz-order__note">Reviews from this page are marked as a verified purchase. '
            'The store approves them before they appear.</p>' + "".join(forms) + "</div>")


def render_order_page(site: dict, nav: list[dict], order: dict, items: list[dict], *,
                      token: str, takes_cards: bool, now: datetime, clear_cart: bool,
                      reviews_open: bool = False) -> str:
    """The whole order page. `order` carries the order row plus `site_name`,
    `timezone`, `tax_label`, `shipping_label`; `items` the receipt-shaped lines
    (`download_url` / `deliverable_url` are shown only once released)."""
    state = order_state(order, takes_cards=takes_cards, now=now)
    total = fmt_money(order.get("total_cents") or order.get("subtotal_cents") or 0, order.get("currency") or "USD")
    ref = order.get("receipt_number") or f"#{str(order['id'])[:8].upper()}"
    pay = ""
    if state["can_pay"]:
        pay = ('<div class="cz-order__pay">'
               f'<button class="cz-btn cz-btn--solid" data-czpay>Pay {escape(total)}</button>'
               '<p class="cz-msg" data-czpay-msg role="status"></p></div>')
    receipt = ""
    if order["status"] in RELEASED:
        receipt = (f'<p><a href="/api/cappe/public/orders/{escape(token, quote=True)}/receipt.pdf" '
                   'target="_blank" rel="noopener noreferrer">Download your receipt (PDF)</a></p>')
    body = (
        f'<section class="cz-order"><div class="cz-wrap cz-order__wrap" data-czorder '
        f'data-token="{escape(token, quote=True)}" data-poll="{1 if state["poll"] else 0}" '
        f'data-clear-cart="{1 if clear_cart else 0}">'
        f'<p class="cz-eyebrow">Order {escape(ref)}</p>'
        f'<h1 class="cz-order__title">{escape(state["headline"])}</h1>'
        f'<p class="cz-order__lead">{escape(state["lead"])}</p>'
        f"{pay}{_items_html(order, items)}{_totals_html(order)}{_shipping_html(order)}{receipt}"
        f"{_reviews_html(items) if reviews_open and order['status'] in RELEASED else ''}"
        "</div></section>"
    )
    return render_site_html(
        site, {"title": "Your order", "slug": "__order", "content": {}}, nav,
        body_override=body,
        extra_head='<meta name="robots" content="noindex,nofollow" /><meta name="referrer" content="no-referrer" />',
        extra_body_end=f"<script>{_ORDER_JS}</script>",
    )
