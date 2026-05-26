"""Render the broker partner-program packet to HTML for WeasyPrint.

Block-based like the Full Deal; prose blocks editable, computed blocks (cover, margin-tier table,
wholesale rate card, book economics, sample client, signatures, disclaimer) rendered from the
broker quote. Reuses the navy proposal CSS + money helpers from `deal_full_template`.
"""

from __future__ import annotations

from datetime import date
from html import escape

from .deal_broker import BrokerInputs, BrokerQuote
from .deal_full_template import _CSS, _fmt_date, _m, _p


def _cover(inp: BrokerInputs, q: BrokerQuote, date_str: str) -> str:
    broker = escape(inp.broker_name)
    return f"""<div class="cover">
  <h1>matcha</h1>
  <div class="subtitle">Risk, Compliance, Employee Relations Intelligence</div>
  <div class="product">Partner Program<br><strong>Broker Edition</strong></div>
  <div class="divider"></div>
  <div class="quote">"Sell risk management. Keep the margin."</div>
  <div class="prepared">
    <p>Prepared for <strong>{broker}</strong></p>
    <p>{q.book_employees:,} committed seats &middot; {escape(q.tier_label)} tier ({q.margin_pct}% margin)</p>
    <p>{date_str}</p>
  </div>
  <div class="footer">
    <p>Confidential &mdash; This document contains proprietary partner pricing and is intended solely for the named recipient.</p>
    <p>hey-matcha.com &middot; aaron@hey-matcha.com</p>
  </div>
</div>"""


def _t_tiers(inp: BrokerInputs, q: BrokerQuote) -> str:
    rows = []
    for t in inp.resolved_tiers():
        hi = "10,000,000" if t.max_employees >= 10_000_000 else f"{t.max_employees:,}"
        band = f"{t.min_employees:,}&ndash;{hi}" if t.max_employees < 10_000_000 else f"{t.min_employees:,}+"
        cls = ' class="row-bold"' if t.label == q.tier_label else ""
        mark = " &larr; your tier" if t.label == q.tier_label else ""
        rows.append(f'<tr{cls}><td style="text-align:left"><strong>{escape(t.label)}</strong>{mark}</td>'
                    f'<td style="text-align:left">{band}</td><td>{t.margin_pct}%</td></tr>')
    return ('<table><thead><tr><th style="text-align:left">Tier</th><th style="text-align:left">Committed Seats</th>'
            f'<th>Your Margin</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


def _t_wholesale(q: BrokerQuote) -> str:
    rows = []
    for w in q.wholesale:
        mark = ' class="row-bold"' if w.tier == q.representative_tier else ""
        rows.append(f'<tr{mark}><td style="text-align:left"><strong>{escape(w.tier_label)}</strong></td>'
                    f'<td>{_p(w.list_pepm)}</td><td>{_p(w.cost_pepm)}</td><td>{_p(w.spread_pepm)}</td></tr>')
    return ('<table><thead><tr><th style="text-align:left">Platform</th><th>List PEPM</th><th>Your Cost</th>'
            f'<th>Your Spread / ee / mo</th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


def _book_econ(q: BrokerQuote) -> str:
    rep_label = {"lite": "Lite", "mid": "Mid", "max": "Max"}[q.representative_tier]
    return (f'<div class="highlight-box">At {q.book_employees:,} committed seats on {rep_label}, your spread is '
            f'{_p(q.representative_spread)} / ee / mo &nbsp;&middot;&nbsp; Annual margin: '
            f'{_p(q.representative_spread)} &times; {q.book_employees:,} &times; 12 = {_m(q.book_annual_margin)}</div>')


def _t_sample(q: BrokerQuote) -> str:
    return f"""<table><thead><tr><th style="text-align:left">Sample Client</th><th>Detail</th></tr></thead><tbody>
      <tr><td style="text-align:left">Client</td><td>{escape(q.sample_client_name)} &middot; {q.sample_client_headcount:,} employees</td></tr>
      <tr><td style="text-align:left">Platform tier</td><td>{escape(q.sample_client_tier_label)} ({_p(q.sample_client_list_pepm)} PEPM list)</td></tr>
      <tr><td style="text-align:left">Client pays (annual)</td><td>{_m(q.sample_client_annual)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Your margin on this client (annual)</td><td>{_m(q.sample_client_margin)}</td></tr>
    </tbody></table>"""


def _sign(inp: BrokerInputs) -> str:
    broker = escape(inp.broker_name)
    return f"""<div class="signatures">
    <div class="sig-block"><h4>Matcha</h4><div class="sig-line"></div><div class="sig-label">Signature</div><div class="sig-line"></div><div class="sig-label">Name &amp; Title</div><div class="sig-line"></div><div class="sig-label">Date</div></div>
    <div class="sig-block"><h4>{broker}</h4><div class="sig-line"></div><div class="sig-label">Signature</div><div class="sig-line"></div><div class="sig-label">Name &amp; Title</div><div class="sig-line"></div><div class="sig-label">Date</div></div>
  </div>"""


def _disclaimer(date_str: str) -> str:
    return (f'<div class="disclaimer"><p>This partner proposal is valid for 30 days from {date_str}. Wholesale rates '
            f'and margin tiers are subject to the executed partner agreement and quarterly headcount true-up.</p></div>')


def _render_block(blk, inp: BrokerInputs, q: BrokerQuote, date_str: str) -> str:
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
    if k == "t_tiers":
        return _t_tiers(inp, q)
    if k == "t_wholesale":
        return _t_wholesale(q)
    if k == "book_econ":
        return _book_econ(q)
    if k == "t_sample":
        return _t_sample(q)
    if k == "sign":
        return _sign(inp)
    if k == "disclaimer":
        return _disclaimer(date_str)
    return ""


def render_broker_proposal_html(inp: BrokerInputs, q: BrokerQuote) -> str:
    date_str = _fmt_date(inp.proposal_date or date.today())
    blocks = inp.resolved_blocks()

    parts: list[str] = []
    page_open = False

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
        if not page_open:
            parts.append('<div class="page">')
            page_open = True
        parts.append(_render_block(blk, inp, q, date_str))
    close_page()

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><style>{_CSS}</style></head>
<body>
{chr(10).join(parts)}
</body></html>"""
