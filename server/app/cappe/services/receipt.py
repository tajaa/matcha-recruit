"""Cappe order receipts — branded PDF, sequential numbering, email.

Reuses the SSRF-safe WeasyPrint helper (`core/services/pdf.render_pdf`) and the
existing Cappe email service (attachment support). A receipt number is assigned
once, when the order is first paid (per-site counter → e.g. LUM-00042).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone
from html import escape
from uuid import UUID

from ...core.services.pdf import render_pdf
from ...database import get_connection
from .email import _email_shell, _send  # noqa: F401  (shell reused; _send kept for parity)
from ...core.services.email.client import get_email_service

logger = logging.getLogger("cappe.receipt")

_SYMBOLS = {"USD": "$", "CAD": "$", "AUD": "$", "GBP": "£", "EUR": "€"}


def _fmt(cents: int, currency: str) -> str:
    sym = _SYMBOLS.get((currency or "USD").upper(), "")
    return f"{sym}{(cents or 0) / 100:,.2f} {(currency or 'USD').upper()}" if not sym else f"{sym}{(cents or 0) / 100:,.2f}"


async def assign_receipt_number(conn, order_id: UUID, site_id: UUID) -> str:
    """Atomically allocate the next per-site receipt number and stamp it on the
    order. Idempotent — returns the existing number if already assigned."""
    existing = await conn.fetchval("SELECT receipt_number FROM cappe_orders WHERE id = $1", order_id)
    if existing:
        return existing
    row = await conn.fetchrow(
        "UPDATE cappe_sites SET receipt_seq = receipt_seq + 1 "
        "WHERE id = $1 RETURNING receipt_seq, receipt_prefix",
        site_id,
    )
    prefix = (row["receipt_prefix"] or "INV").strip() if row else "INV"
    number = f"{prefix}-{int(row['receipt_seq']):05d}"
    await conn.execute(
        "UPDATE cappe_orders SET receipt_number = $1, updated_at = NOW() WHERE id = $2",
        number, order_id,
    )
    return number


def _items_rows_html(items: list[dict], currency: str) -> str:
    out = []
    for it in items:
        opts = it.get("selected_options") or []
        if isinstance(opts, str):
            try:
                opts = json.loads(opts)
            except ValueError:
                opts = []
        opt_txt = ""
        if opts:
            names = ", ".join(escape(str(o.get("name", ""))) for o in opts if isinstance(o, dict))
            if names:
                opt_txt = f'<div style="color:#71717a;font-size:12px;">{names}</div>'
        qty = int(it.get("quantity") or 1)
        unit = int(it.get("unit_price_cents") or 0)
        out.append(
            f'<tr>'
            f'<td style="padding:8px 0;border-bottom:1px solid #eee;">{escape(str(it.get("title") or "Item"))}{opt_txt}</td>'
            f'<td style="padding:8px 0;border-bottom:1px solid #eee;text-align:center;">{qty}</td>'
            f'<td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right;">{_fmt(unit, currency)}</td>'
            f'<td style="padding:8px 0;border-bottom:1px solid #eee;text-align:right;">{_fmt(unit * qty, currency)}</td>'
            f'</tr>'
        )
    return "".join(out)


def build_receipt_html(order: dict, items: list[dict]) -> str:
    """Printable receipt document (light theme for paper / PDF)."""
    cur = order.get("currency") or "USD"
    biz = escape(str(order.get("business_name") or "Store"))
    number = escape(str(order.get("receipt_number") or "—"))
    when = order.get("paid_at") or order.get("created_at") or datetime.now(timezone.utc)
    when_txt = when.strftime("%b %-d, %Y") if hasattr(when, "strftime") else escape(str(when))
    cust = escape(str(order.get("customer_name") or order.get("customer_email") or ""))
    cust_email = escape(str(order.get("customer_email") or ""))
    subtotal = int(order.get("subtotal_cents") or 0)
    tax = int(order.get("tax_cents") or 0)
    total = int(order.get("total_cents") or (subtotal + tax))
    tax_label = escape(str(order.get("tax_label") or "Tax"))
    pay_ref = escape(str(order.get("stripe_payment_intent") or order.get("payment_ref") or ""))

    tax_row = (
        f'<tr><td style="padding:4px 0;text-align:right;color:#71717a;">{tax_label}</td>'
        f'<td style="padding:4px 0;text-align:right;width:120px;">{_fmt(tax, cur)}</td></tr>'
        if tax > 0 else ""
    )
    return f"""\
<!doctype html><html><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 28mm 20mm; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif; color:#18181b; }}
</style></head><body>
  <div style="display:flex;justify-content:space-between;align-items:flex-start;">
    <div><div style="font-size:22px;font-weight:700;">{biz}</div>
      <div style="color:#71717a;font-size:13px;margin-top:2px;">Receipt</div></div>
    <div style="text-align:right;font-size:13px;color:#3f3f46;">
      <div><b>{number}</b></div><div>{when_txt}</div>
      <div style="color:#16a34a;font-weight:600;margin-top:4px;">PAID</div></div>
  </div>
  <div style="margin:20px 0 8px;font-size:13px;color:#3f3f46;">
    <div style="color:#71717a;">Billed to</div><div>{cust}</div>
    {f'<div style="color:#71717a;">{cust_email}</div>' if cust and cust_email and cust != cust_email else ''}
  </div>
  <table style="width:100%;border-collapse:collapse;font-size:14px;margin-top:8px;">
    <thead><tr style="color:#71717a;font-size:12px;text-transform:uppercase;">
      <th style="text-align:left;padding:6px 0;border-bottom:2px solid #18181b;">Item</th>
      <th style="text-align:center;padding:6px 0;border-bottom:2px solid #18181b;">Qty</th>
      <th style="text-align:right;padding:6px 0;border-bottom:2px solid #18181b;">Price</th>
      <th style="text-align:right;padding:6px 0;border-bottom:2px solid #18181b;">Amount</th>
    </tr></thead>
    <tbody>{_items_rows_html(items, cur)}</tbody>
  </table>
  <table style="width:100%;margin-top:14px;font-size:14px;"><tbody>
    <tr><td style="padding:4px 0;text-align:right;color:#71717a;">Subtotal</td>
      <td style="padding:4px 0;text-align:right;width:120px;">{_fmt(subtotal, cur)}</td></tr>
    {tax_row}
    <tr><td style="padding:8px 0;text-align:right;font-weight:700;border-top:2px solid #18181b;">Total</td>
      <td style="padding:8px 0;text-align:right;font-weight:700;border-top:2px solid #18181b;">{_fmt(total, cur)}</td></tr>
  </tbody></table>
  {f'<div style="margin-top:16px;font-size:12px;color:#a1a1aa;">Payment ref: {pay_ref}</div>' if pay_ref else ''}
  <div style="margin-top:28px;font-size:11px;color:#a1a1aa;text-align:center;">Powered by Gummfit</div>
</body></html>"""


async def render_order_receipt_pdf(conn, order_id: UUID) -> tuple[dict, bytes] | None:
    """Load an order + its items + site/tax context and render the receipt PDF.
    Returns (order_dict, pdf_bytes) or None if the order is missing."""
    order = await conn.fetchrow(
        """SELECT o.id, o.customer_email, o.customer_name, o.currency, o.subtotal_cents,
                  o.tax_cents, o.total_cents, o.receipt_number, o.payment_ref,
                  o.stripe_payment_intent, o.paid_at, o.created_at, o.site_id,
                  s.name AS business_name, s.tax_label
             FROM cappe_orders o JOIN cappe_sites s ON s.id = o.site_id
            WHERE o.id = $1""",
        order_id,
    )
    if order is None:
        return None
    item_rows = await conn.fetch(
        "SELECT title, unit_price_cents, quantity, selected_options "
        "FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
        order_id,
    )
    od = dict(order)
    items = [dict(r) for r in item_rows]
    html = build_receipt_html(od, items)
    pdf = await asyncio.to_thread(render_pdf, html)
    return od, pdf


async def email_receipt(order: dict, pdf: bytes) -> None:
    """Email the PDF receipt to the customer (best-effort)."""
    to_email = order.get("customer_email")
    if not to_email:
        return
    number = order.get("receipt_number") or "receipt"
    biz = order.get("business_name") or "your order"
    total = int(order.get("total_cents") or order.get("subtotal_cents") or 0)
    cur = order.get("currency") or "USD"
    body = (
        f'<p style="margin:0 0 12px;color:#d4d4d8;font-size:14px;">Thanks for your purchase from '
        f'{escape(str(biz))}. Your receipt <b>{escape(str(number))}</b> ({_fmt(total, cur)}) is attached.</p>'
    )
    html = _email_shell(f"Your receipt from {escape(str(biz))}", body, footer=escape(str(biz)))
    text = f"Thanks for your purchase from {biz}. Receipt {number} — {_fmt(total, cur)} attached."
    att = [{
        "filename": f"{number}.pdf",
        "content": base64.b64encode(pdf).decode("ascii"),
        "disposition": "attachment",
    }]
    try:
        await get_email_service().send_email_with_fallback(
            to_email=to_email, to_name=order.get("customer_name"),
            subject=f"Receipt {number} — {biz}",
            html_content=html, text_content=text, attachments=att,
        )
    except Exception:
        logger.exception("Cappe receipt email failed for %s", to_email)


async def issue_receipt_for_paid_order(order_id: UUID, site_id: UUID) -> None:
    """Full post-payment receipt flow: assign number → render PDF → email.
    Best-effort; never raises (called from the webhook)."""
    try:
        async with get_connection() as conn:
            await assign_receipt_number(conn, order_id, site_id)
            rendered = await render_order_receipt_pdf(conn, order_id)
        if rendered is None:
            return
        order, pdf = rendered
        await email_receipt(order, pdf)
    except Exception:
        logger.exception("Cappe receipt issuance failed for order %s", order_id)
