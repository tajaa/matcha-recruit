"""Render the broker Book-Pricing one-pager to HTML for WeasyPrint.

Block-based like the Broker packet; prose blocks editable, computed blocks (cover, volume-discount
schedule, client roster, book economics, signatures, disclaimer) rendered from the book quote.
Reuses the navy proposal CSS + money helpers from `deal_full_template`.
"""

from __future__ import annotations

from datetime import date
from html import escape

from .deal_book import BookInputs, BookQuote
from .deal_full_template import _CSS, _fmt_date, _m, _p


def _cover(inp: BookInputs, q: BookQuote, date_str: str) -> str:
    broker = escape(inp.broker_name)
    disc = f"{q.discount_pct}% volume discount" if q.discount_pct else "list pricing"
    return f"""<div class="cover">
  <h1>matcha</h1>
  <div class="subtitle">Risk, Compliance, Employee Relations Intelligence</div>
  <div class="product">Matcha Lite<br><strong>Book Pricing</strong></div>
  <div class="divider"></div>
  <div class="quote">"One platform for your whole book. One pooled rate."</div>
  <div class="prepared">
    <p>Prepared for <strong>{broker}</strong></p>
    <p>{q.total_seats:,} committed seats &middot; {disc}</p>
    <p>{date_str}</p>
  </div>
  <div class="footer">
    <p>Confidential &mdash; This document contains proprietary partner pricing and is intended solely for the named recipient.</p>
    <p>hey-matcha.com &middot; aaron@hey-matcha.com</p>
  </div>
</div>"""


def _t_discount(inp: BookInputs, q: BookQuote) -> str:
    tiers = inp.resolved_tiers()
    rows = []
    for i, t in enumerate(tiers):
        if i + 1 < len(tiers):
            hi = tiers[i + 1].min_seats - 1
            band = f"Up to {hi:,}" if t.min_seats == 0 else f"{t.min_seats:,}&ndash;{hi:,}"
        else:
            band = f"{t.min_seats:,}+"
        active = q.applied_tier_min is not None and t.min_seats == q.applied_tier_min
        cls = ' class="row-bold"' if active else ""
        mark = " &larr; your book" if active else ""
        rows.append(f'<tr{cls}><td style="text-align:left"><strong>{band}</strong>{mark}</td>'
                    f'<td>{t.discount_pct}%</td></tr>')
    return ('<table><thead><tr><th style="text-align:left">Committed Seats</th>'
            f'<th>Volume Discount</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


def _t_roster(q: BookQuote) -> str:
    # Per-company breakdown: monthly + annual for each client. No book total row —
    # the book-wide monthly/yearly aggregate lives in the Book Economics section.
    rows = []
    for ln in q.lines:
        monthly = round(ln.annual / 12)
        rows.append(f'<tr><td style="text-align:left">{escape(ln.name)}</td>'
                    f'<td>{ln.seats:,}</td><td>{_m(monthly)}</td><td>{_m(ln.annual)}</td></tr>')
    off = f" &mdash; {q.discount_pct}% off the {_p(q.list_pepm)} list rate" if q.discount_pct else ""
    note = (f'<p class="note">All clients are priced at the pooled rate of <strong>{_p(q.net_pepm)} PEPM</strong>'
            f'{off}, unlocked by {q.total_seats:,} committed seats.</p>')
    return ('<table><thead><tr><th style="text-align:left">Client</th><th>Seats</th>'
            f'<th>Monthly</th><th>Annual</th></tr></thead><tbody>{"".join(rows)}</tbody></table>{note}')


def _book_econ(q: BookQuote) -> str:
    # No book-wide aggregate dollar total — per-company monthly/yearly live in the roster, and a
    # large book total reads as "scary" to a broker. Lead with the pooled per-employee rate (what
    # the committed volume unlocks) and frame the win as a % below list, not a big dollar figure.
    off = (f'<span style="font-weight:600">&nbsp;&middot;&nbsp; {q.discount_pct}% below the {_p(q.list_pepm)} list rate</span>'
           if q.discount_pct else "")
    return (
        '<div class="highlight-box">'
        f'<div style="font-size:22pt;font-weight:700;line-height:1.15">{_p(q.net_pepm)}'
        f'<span style="font-size:11pt;font-weight:600;opacity:0.85"> PEPM</span></div>'
        f'<div style="margin-top:6px;font-size:10pt;font-weight:500;opacity:0.9">'
        f'Pooled rate across {q.total_seats:,} committed seats{off}</div>'
        '</div>')


def _sign(inp: BookInputs) -> str:
    broker = escape(inp.broker_name)
    return f"""<div class="signatures">
    <div class="sig-block"><h4>Matcha</h4><div class="sig-line"></div><div class="sig-label">Signature</div><div class="sig-line"></div><div class="sig-label">Name &amp; Title</div><div class="sig-line"></div><div class="sig-label">Date</div></div>
    <div class="sig-block"><h4>{broker}</h4><div class="sig-line"></div><div class="sig-label">Signature</div><div class="sig-line"></div><div class="sig-label">Name &amp; Title</div><div class="sig-line"></div><div class="sig-label">Date</div></div>
  </div>"""


def _disclaimer(date_str: str) -> str:
    return (f'<div class="disclaimer"><p>This book proposal is valid for 30 days from {date_str}. The pooled rate '
            f'is subject to the executed agreement and quarterly committed-seat true-up.</p></div>')


def _render_block(blk, inp: BookInputs, q: BookQuote, date_str: str) -> str:
    k = blk.kind
    if k in ("h2", "h3", "h4"):
        return f"<{k}>{escape(blk.text)}</{k}>"
    if k == "p":
        return f"<p>{escape(blk.text)}</p>"
    if k == "note":
        return f'<p class="note">{escape(blk.text)}</p>'
    if k == "callout":
        return f'<div class="callout">{escape(blk.text)}</div>'
    if k == "bullets":
        return '<ul class="bullet">' + "".join(f"<li>{escape(it)}</li>" for it in blk.items) + "</ul>"
    if k == "cover":
        return _cover(inp, q, date_str)
    if k == "t_discount":
        return _t_discount(inp, q)
    if k == "t_roster":
        return _t_roster(q)
    if k == "book_econ":
        return _book_econ(q)
    if k == "sign":
        return _sign(inp)
    if k == "disclaimer":
        return _disclaimer(date_str)
    return ""


def render_book_proposal_html(inp: BookInputs, q: BookQuote) -> str:
    date_str = _fmt_date(inp.proposal_date or date.today())
    blocks = inp.resolved_blocks()

    parts: list[str] = []
    page_open = False
    any_page = False

    def close_page():
        nonlocal page_open
        if page_open:
            parts.append("</div>")
            page_open = False

    for blk in blocks:
        if blk.kind == "cover":
            close_page()
            parts.append(_render_block(blk, inp, q, date_str))
            continue
        if not page_open or blk.new_page:
            close_page()
            cls = "page fresh" if (any_page and blk.new_page) else "page"
            parts.append(f'<div class="{cls}">')
            page_open = True
            any_page = True
        parts.append(_render_block(blk, inp, q, date_str))
    close_page()

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><style>{_CSS}</style></head>
<body>
{chr(10).join(parts)}
</body></html>"""
