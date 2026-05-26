"""Render the full multi-page Matcha service proposal to HTML for WeasyPrint.

CSS ported from deals/la-nonprofit/LA_NonProfit_Proposal_v1.html (~10 pages). The document is
a list of editable `Block`s (`deal_full.py`); prose blocks render as their text, "computed"
blocks (cover, pricing tables, signatures, disclaimer) render server-side from the pricing
inputs. The same renderer drives both the in-app preview and the downloaded PDF.
"""

from __future__ import annotations

from datetime import date
from html import escape

from .deal_full import Block, FullDealInputs, FullQuote


def _m(n: int) -> str:
    return f"${n:,}"


def _p(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_date(d: date) -> str:
    return d.strftime("%B %-d, %Y")


# ── Computed-block renderers ──────────────────────────────────────────────────
def _cover(inp: FullDealInputs, date_str: str) -> str:
    company = escape(inp.company_name)
    loc = escape(inp.location.strip())
    line2 = f"{inp.headcount:,} Employees"
    if loc:
        line2 += f" &middot; {loc}"
    line2 += " &middot; Full Platform Access"
    return f"""<div class="cover">
  <h1>matcha</h1>
  <div class="subtitle">Risk, Compliance, Employee Relations Intelligence</div>
  <div class="product">Platform<br><strong>Service Proposal</strong></div>
  <div class="divider"></div>
  <div class="quote">"Manage your risk or your risk will manage you."</div>
  <div class="prepared">
    <p>Prepared for <strong>{company}</strong></p>
    <p>{line2}</p>
    <p>{date_str}</p>
  </div>
  <div class="footer">
    <p>Confidential &mdash; This document contains proprietary pricing and is intended solely for the named recipient.</p>
    <p>hey-matcha.com &middot; aaron@hey-matcha.com</p>
  </div>
</div>"""


def _t_pepm(q: FullQuote) -> str:
    rows = [f'<tr class="row-step"><td style="text-align:left">Standard PEPM rate</td><td>{_p(q.rack_pepm)}</td></tr>']
    if q.volume_applied:
        rows.append(f'<tr class="row-step"><td style="text-align:left">Less 10% volume discount <em>(automatic at 500+ employees)</em></td><td>&minus;{_p(q.volume_pepm_cut)}</td></tr>')
        rows.append(f'<tr class="row-sub"><td style="text-align:left">Subtotal</td><td>{_p(q.subtotal_pepm)}</td></tr>')
    if q.bp_rate_pct:
        rows.append(f'<tr class="row-step"><td style="text-align:left">Less {q.bp_rate_pct}% Broker + Partner discount</td><td>&minus;{_p(q.bp_pepm_cut)}</td></tr>')
    rows.append(f'<tr class="row-total"><td style="text-align:left">Your locked PEPM rate</td><td>{_p(q.your_pepm)}</td></tr>')
    return (f'<table><thead><tr><th style="text-align:left">Build-up</th><th>Rate per employee / month</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def _t_costs(inp: FullDealInputs, q: FullQuote) -> str:
    extra = ""
    if q.extra_jurisdiction_cost:
        extra = (f'<tr><td style="text-align:left">Additional jurisdictions ({q.jurisdictions_extra} &times; {_m(q.juris_fee)})</td>'
                 f'<td class="calc-cell">{q.juris_tier} tier</td><td><strong>{_m(q.extra_jurisdiction_cost)}</strong></td></tr>')
    return f"""<table><thead><tr><th style="text-align:left">Line Item</th><th style="text-align:right">How it&rsquo;s calculated</th><th>Annual</th></tr></thead><tbody>
      <tr><td style="text-align:left">Platform usage (all {q.headcount:,} employees)</td><td class="calc-cell">{_p(q.your_pepm)} &times; {q.headcount:,} &times; 12 months</td><td><strong>{_m(q.annual_employee_your)}</strong></td></tr>
      <tr><td style="text-align:left">Platform fee (first jurisdiction included)</td><td class="calc-cell">flat annual fee</td><td><strong>{_m(q.platform_fee_your)}</strong></td></tr>
      {extra}
      <tr><td style="text-align:left">HR Advisory &mdash; Basic (1 session/month)</td><td class="calc-cell">&mdash;</td><td><strong>Included w/ Partner</strong></td></tr>
      <tr class="row-bold"><td style="text-align:left">Annual Recurring</td><td class="calc-cell"></td><td>{_m(q.annual_recurring_your)}</td></tr>
      <tr><td style="text-align:left">Implementation &amp; Configuration (one-time, Year 1 only)</td><td class="calc-cell">flat one-time fee</td><td><strong>{_m(q.implementation_your)}</strong></td></tr>
      <tr class="row-total"><td style="text-align:left">Year 1 Total</td><td class="calc-cell">{_m(q.annual_recurring_your)} + {_m(q.implementation_your)}</td><td>{_m(q.year1_your)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Year 2+ Annual (recurring only)</td><td class="calc-cell">recurring only</td><td>{_m(q.year2_your)}</td></tr>
    </tbody></table>"""


def _hr_rate() -> str:
    return """<table><thead><tr><th style="text-align:left">HR Advisory Tier</th><th style="text-align:left">What&rsquo;s Included</th><th>Annual Rate</th></tr></thead><tbody>
      <tr><td style="text-align:left"><strong>Basic</strong></td><td style="text-align:left">1 session/month (12/year, 45 min each)</td><td><strong>Included w/ Partner</strong></td></tr>
      <tr><td style="text-align:left"><strong>Consulting Retainer</strong></td><td style="text-align:left">4 sessions/month (48/year, 60 min each)</td><td><strong>$12,000/yr</strong></td></tr>
      <tr><td style="text-align:left"><strong>On-Demand</strong></td><td style="text-align:left">Additional sessions beyond your included allotment</td><td><strong>$650/session</strong></td></tr>
    </tbody></table>"""


def _t_savings(q: FullQuote) -> str:
    return f"""<table><thead><tr><th style="text-align:left">Line Item</th><th>Standard List</th><th>Your Price</th><th>You Save</th></tr></thead><tbody>
      <tr><td style="text-align:left">PEPM rate</td><td>{_p(q.rack_pepm)}</td><td><strong>{_p(q.your_pepm)}</strong></td><td>{_p(q.pepm_save)} / ee / mo</td></tr>
      <tr><td style="text-align:left">Annual employee cost ({q.headcount:,} employees)</td><td>{_m(q.annual_employee_standard)}</td><td><strong>{_m(q.annual_employee_your)}</strong></td><td>{_m(q.annual_employee_save)}</td></tr>
      <tr><td style="text-align:left">Platform fee (first jurisdiction included)</td><td>{_m(q.platform_fee_standard)}</td><td><strong>{_m(q.platform_fee_your)}</strong></td><td>{_m(q.platform_save)}</td></tr>
      <tr class="row-bold"><td style="text-align:left">Annual Recurring</td><td>{_m(q.annual_recurring_standard)}</td><td><strong>{_m(q.annual_recurring_your)}</strong></td><td>{_m(q.recurring_save)}</td></tr>
      <tr><td style="text-align:left">Implementation &amp; Configuration</td><td>{_m(q.implementation_standard)}</td><td><strong>{_m(q.implementation_your)}</strong></td><td>{_m(q.implementation_save)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Year 1 Total</td><td>{_m(q.year1_standard)}</td><td><strong>{_m(q.year1_your)}</strong></td><td>{_m(q.year1_save)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Year 2+ Annual</td><td>{_m(q.annual_recurring_standard)}</td><td><strong>{_m(q.annual_recurring_your)}</strong></td><td>{_m(q.recurring_save)}</td></tr>
    </tbody></table>"""


def _t_jurisdiction(inp: FullDealInputs, q: FullQuote) -> str:
    company = escape(inp.company_name)
    return f"""<table><thead><tr><th style="text-align:left">Client Tier</th><th style="text-align:left">Headcount</th><th>Per Additional Jurisdiction / Year</th></tr></thead><tbody>
      <tr><td style="text-align:left">Growth</td><td style="text-align:left">1&ndash;249</td><td>$3,200</td></tr>
      <tr><td style="text-align:left"><strong>Business</strong></td><td style="text-align:left"><strong>250&ndash;999</strong></td><td><strong>$7,500</strong></td></tr>
      <tr><td style="text-align:left">Enterprise</td><td style="text-align:left">1,000+</td><td>$10,000</td></tr>
    </tbody></table>
    <p class="note">At {q.headcount:,} employees, {company} is in the <strong>{q.juris_tier}</strong> tier &mdash; additional jurisdictions are billed at {_m(q.juris_fee)}/year each. Price locked for the 12-month initial term. Employee count subject to quarterly true-up.</p>"""


def _t_roi(q: FullQuote) -> str:
    return f"""<table><thead><tr><th style="text-align:left"></th><th>Year 1</th><th>Year 2</th><th>Year 3</th><th>3-Year Total</th></tr></thead><tbody>
      <tr><td style="text-align:left">Annual recurring</td><td>{_m(q.annual_recurring_your)}</td><td>{_m(q.annual_recurring_your)}</td><td>{_m(q.annual_recurring_your)}</td><td>{_m(q.annual_recurring_your * 3)}</td></tr>
      <tr><td style="text-align:left">Implementation</td><td>{_m(q.implementation_your)}</td><td>&mdash;</td><td>&mdash;</td><td>{_m(q.implementation_your)}</td></tr>
      <tr class="row-bold"><td style="text-align:left">Total investment</td><td>{_m(q.year1_your)}</td><td>{_m(q.year2_your)}</td><td>{_m(q.year2_your)}</td><td>{_m(q.year1_your + q.year2_your * 2)}</td></tr>
      <tr><td style="text-align:left">Hard savings</td><td>{_m(q.roi_hard_savings)}</td><td>{_m(q.roi_hard_savings)}</td><td>{_m(q.roi_hard_savings)}</td><td>{_m(q.roi_hard_savings * 3)}</td></tr>
      <tr><td style="text-align:left">Risk reduction value</td><td>{_m(q.roi_risk_reduction)}</td><td>{_m(q.roi_risk_reduction)}</td><td>{_m(q.roi_risk_reduction)}</td><td>{_m(q.roi_risk_reduction * 3)}</td></tr>
      <tr class="row-bold"><td style="text-align:left">Total value delivered</td><td>{_m(q.roi_total_value)}</td><td>{_m(q.roi_total_value)}</td><td>{_m(q.roi_total_value)}</td><td>{_m(q.roi_total_value * 3)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Net savings</td><td>{_m(q.roi_net_year1)}</td><td>{_m(q.roi_net_year2)}</td><td>{_m(q.roi_net_year2)}</td><td>{_m(q.roi_net_3yr)}</td></tr>
    </tbody></table>
    <div class="highlight-box">Year 1 ROI: {q.roi_multiple}&times; &nbsp;&middot;&nbsp; Platform pays for itself by month {q.roi_payback_month} &nbsp;&middot;&nbsp; 3-year net savings: {_m(q.roi_net_3yr)}</div>"""


def _sign(inp: FullDealInputs) -> str:
    company = escape(inp.company_name)
    return f"""<div class="signatures">
    <div class="sig-block"><h4>Matcha</h4><div class="sig-line"></div><div class="sig-label">Signature</div><div class="sig-line"></div><div class="sig-label">Name &amp; Title</div><div class="sig-line"></div><div class="sig-label">Date</div></div>
    <div class="sig-block"><h4>{company}</h4><div class="sig-line"></div><div class="sig-label">Signature</div><div class="sig-line"></div><div class="sig-label">Name &amp; Title</div><div class="sig-line"></div><div class="sig-label">Date</div></div>
  </div>"""


def _disclaimer(date_str: str) -> str:
    return f"""<div class="disclaimer">
    <p>This proposal is valid for 30 days from {date_str}. Pricing is based on the employee count provided and subject to quarterly true-up.</p>
    <p>Matcha is a compliance research and workforce risk intelligence platform. It is not a substitute for legal counsel, and does not constitute legal advice or regulatory certification.</p>
  </div>"""


def _render_block(blk: Block, inp: FullDealInputs, q: FullQuote, date_str: str) -> str:
    k = blk.kind
    if k in ("h2", "h3", "h4"):
        return f"<{k}>{escape(blk.text)}</{k}>"
    if k == "p":
        return f"<p>{escape(blk.text)}</p>"
    if k == "note":
        return f'<p class="note">{escape(blk.text)}</p>'
    if k == "callout":
        return f'<div class="callout">{escape(blk.text)}</div>'
    if k == "highlight":
        return f'<div class="highlight-box">{escape(blk.text)}</div>'
    if k == "bullets":
        lis = "".join(f"<li>{escape(it)}</li>" for it in blk.items)
        return f'<ul class="bullet">{lis}</ul>'
    if k == "t_pepm":
        return _t_pepm(q)
    if k == "t_costs":
        return _t_costs(inp, q)
    if k == "hr_rate":
        return _hr_rate()
    if k == "t_savings":
        return _t_savings(q)
    if k == "t_jurisdiction":
        return _t_jurisdiction(inp, q)
    if k == "t_roi":
        return _t_roi(q)
    if k == "sign":
        return _sign(inp)
    if k == "disclaimer":
        return _disclaimer(date_str)
    return ""


_CSS = """
  @page { size: letter; margin: 0.55in 0; }
  @page cover-page { size: letter; margin: 0; background: #1a1a2e; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #1a1a2e; font-size: 10.5pt; line-height: 1.55; }
  .cover { page: cover-page; page-break-after: always; background: #1a1a2e; color: white; height: 11in; padding: 80px 70px 60px; position: relative; overflow: hidden; }
  .cover::after { content: ''; position: absolute; top: -120px; right: -120px; width: 500px; height: 500px; border-radius: 50%; background: rgba(255,255,255,0.03); }
  .cover::before { content: ''; position: absolute; bottom: -80px; left: -80px; width: 400px; height: 400px; border-radius: 50%; background: rgba(255,255,255,0.02); }
  .cover h1 { font-size: 42pt; font-weight: 800; letter-spacing: -1px; margin-bottom: 4px; }
  .cover .subtitle { font-size: 8pt; letter-spacing: 5px; text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 6px; }
  .cover .product { font-size: 22pt; font-weight: 300; color: rgba(255,255,255,0.8); }
  .cover .product strong { font-weight: 700; color: white; display: block; font-size: 30pt; }
  .cover .divider { width: 60px; height: 3px; background: #6c63ff; margin: 30px 0; }
  .cover .quote { font-style: italic; color: rgba(255,255,255,0.6); font-size: 12pt; margin-bottom: 40px; }
  .cover .prepared { font-size: 11pt; }
  .cover .prepared strong { font-size: 13pt; }
  .cover .prepared p { margin: 4px 0; color: rgba(255,255,255,0.85); }
  .cover .footer { position: absolute; bottom: 60px; left: 70px; color: rgba(255,255,255,0.35); font-size: 8.5pt; }
  .cover .footer p { margin: 3px 0; }
  .page { padding: 8px 60px 28px; }
  .page.fresh { page-break-before: always; }
  h2, h3, h4 { page-break-after: avoid; }
  table, .callout, .highlight-box, .signatures, ul.bullet { page-break-inside: avoid; }
  tr { page-break-inside: avoid; }
  thead { display: table-header-group; }
  h2 { font-size: 22pt; font-weight: 700; color: #1a1a2e; margin-bottom: 18px; margin-top: 6px; }
  h3 { font-size: 13pt; font-weight: 700; color: #1a1a2e; margin-top: 22px; margin-bottom: 10px; }
  h4 { font-size: 11pt; font-weight: 700; color: #1a1a2e; margin-top: 16px; margin-bottom: 6px; }
  p, li { margin-bottom: 8px; color: #333; }
  .callout { border-left: 3px solid #1a1a2e; padding: 16px 20px; background: #f8f8fa; margin: 16px 0; font-size: 10pt; color: #444; line-height: 1.6; }
  .highlight-box { background: #1a1a2e; color: white; padding: 14px 24px; border-radius: 4px; margin: 16px 0; font-size: 11pt; font-weight: 600; }
  table { width: 100%; border-collapse: collapse; margin: 14px 0 20px; font-size: 9.5pt; }
  thead th { background: #1a1a2e; color: white; padding: 10px 14px; text-align: left; font-size: 7.5pt; letter-spacing: 2px; text-transform: uppercase; font-weight: 600; }
  thead th:last-child, thead th:nth-child(n+2) { text-align: right; }
  tbody td { padding: 9px 14px; border-bottom: 1px solid #eee; }
  tbody td:last-child, tbody td:nth-child(n+2) { text-align: right; }
  tbody tr:last-child td { border-bottom: none; }
  .row-bold td { font-weight: 700; border-top: 2px solid #1a1a2e; padding-top: 12px; }
  .row-total td { font-weight: 700; font-size: 10.5pt; border-top: 2px solid #1a1a2e; padding-top: 12px; }
  .row-step td { color: #555; }
  .row-sub td { font-weight: 600; border-top: 1px solid #ccc; }
  .note { font-size: 8.5pt; color: #777; font-style: italic; line-height: 1.5; margin: 10px 0; }
  .note strong { color: #555; }
  .signatures { display: flex; gap: 60px; margin-top: 30px; }
  .sig-block { flex: 1; }
  .sig-block h4 { font-size: 12pt; margin-bottom: 18px; }
  .sig-line { border-bottom: 1px solid #333; margin-bottom: 6px; height: 26px; }
  .sig-label { font-size: 8.5pt; color: #888; margin-bottom: 12px; }
  .disclaimer { font-size: 8pt; color: #999; font-style: italic; text-align: center; padding-top: 12px; border-top: 1px solid #ddd; margin-top: 16px; line-height: 1.5; }
  ul.bullet { padding-left: 18px; margin: 10px 0; }
  ul.bullet li { margin-bottom: 6px; }
  .calc-cell { text-align: right; color: #666; font-size: 9pt; }
"""


def render_full_proposal_html(inp: FullDealInputs, q: FullQuote) -> str:
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
            parts.append(_cover(inp, date_str))
            continue
        if not page_open or blk.new_page:
            close_page()
            cls = "page fresh" if (any_page and blk.new_page) else "page"
            parts.append(f'<div class="{cls}">')
            page_open = True
            any_page = True
        parts.append(_render_block(blk, inp, q, date_str))
    close_page()

    body = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><style>{_CSS}</style></head>
<body>
{body}
</body></html>"""
