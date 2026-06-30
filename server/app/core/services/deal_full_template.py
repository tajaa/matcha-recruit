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


# Curated, premium-only design options (kept tight so a cover can't be made ugly).
# Every font here is loaded by the @import in _CSS; the picker only switches among them.
COVER_TITLE_FONTS = {
    "Fraunces": "'Fraunces', serif",
    "Playfair Display": "'Playfair Display', serif",
    "Cormorant Garamond": "'Cormorant Garamond', serif",
    "Space Grotesk": "'Space Grotesk', sans-serif",
    "Inter": "'Inter', sans-serif",
}
# Each background theme carries its own gradient + corner glow so the look stays cohesive.
COVER_BG_STYLES = {
    "ink":    {"bg": "linear-gradient(157deg, #21213f 0%, #15152c 52%, #0d0d1d 100%)", "glow": "radial-gradient(circle, rgba(124,108,255,0.24) 0%, rgba(124,108,255,0) 68%)"},
    "noir":   {"bg": "linear-gradient(157deg, #232327 0%, #141416 55%, #0b0b0d 100%)", "glow": "radial-gradient(circle, rgba(255,255,255,0.10) 0%, rgba(255,255,255,0) 70%)"},
    "plum":   {"bg": "linear-gradient(157deg, #2c2042 0%, #1c142b 54%, #120c1d 100%)", "glow": "radial-gradient(circle, rgba(168,120,255,0.26) 0%, rgba(168,120,255,0) 68%)"},
    "forest": {"bg": "linear-gradient(157deg, #163027 0%, #0f1f18 54%, #0a130e 100%)", "glow": "radial-gradient(circle, rgba(86,204,150,0.20) 0%, rgba(86,204,150,0) 70%)"},
    "slate":  {"bg": "linear-gradient(157deg, #1d2736 0%, #131a25 54%, #0c1018 100%)", "glow": "radial-gradient(circle, rgba(96,165,250,0.22) 0%, rgba(96,165,250,0) 70%)"},
}


def render_cover(cover, defaults: dict, prepared_html: str) -> str:
    """Shared cover-page builder for the Broker + Book-Pricing packets.

    `cover` is an optional `CoverFields`; each field falls back to `defaults[...]` when
    blank/None. `prepared_html` is the per-tab "prepared for / seats / date" block, already
    built and escaped by the caller. Defaults may carry literal &-entities; user-supplied
    text overrides are escaped. Design knobs (font/color/bg) are whitelisted/pattern-checked
    on `CoverFields`, then emitted as a scoped <style> that overrides the _CSS defaults."""
    def g(key: str) -> str:
        val = getattr(cover, key, None) if cover is not None else None
        return escape(val) if val else defaults[key]

    # Per-cover design overrides — only emit for known-safe values.
    ov: list[str] = []
    accent = getattr(cover, "accent_color", None) if cover is not None else None
    if accent:  # pattern-validated #rrggbb on the model
        ov.append(f".cover .spine{{background:{accent}}}")
        ov.append(f".cover .divider{{background:{accent}}}")
        ov.append(f".cover .product{{color:{accent}}}")
        ov.append(f".cover .quote{{border-left-color:{accent}}}")
    tfont = getattr(cover, "title_font", None) if cover is not None else None
    if tfont in COVER_TITLE_FONTS:
        ov.append(f".cover .product strong, .cover .quote{{font-family:{COVER_TITLE_FONTS[tfont]}}}")
    bg = getattr(cover, "bg_style", None) if cover is not None else None
    if bg in COVER_BG_STYLES:
        ov.append(f".cover{{background:{COVER_BG_STYLES[bg]['bg']}}}")
        ov.append(f".cover::before{{background:{COVER_BG_STYLES[bg]['glow']}}}")
    style = f"<style>{''.join(ov)}</style>" if ov else ""

    return f"""{style}<div class="cover">
  <div class="spine"></div>
  <div class="cover-brand">
    <h1>{g('wordmark')}</h1>
    <div class="subtitle">{g('subtitle')}</div>
  </div>
  <div class="cover-lead">
    <div class="product">{g('product_line')}<br><strong>{g('product_title')}</strong></div>
    <div class="divider"></div>
    <div class="quote">&ldquo;{g('tagline')}&rdquo;</div>
  </div>
  <div class="prepared">{prepared_html}</div>
  <div class="footer">
    <p>{g('footer_note')}</p>
    <p>{g('footer_contact')}</p>
  </div>
</div>"""


# ── Computed-block renderers ──────────────────────────────────────────────────
_FULL_COVER_DEFAULTS = {
    "wordmark": "matcha",
    "subtitle": "Risk, Compliance, Employee Relations Intelligence",
    "product_line": "Platform",
    "product_title": "Service Proposal",
    "tagline": "Manage your risk or your risk will manage you.",
    "footer_note": "Confidential &mdash; This document contains proprietary pricing and is intended solely for the named recipient.",
    "footer_contact": "hey-matcha.com &middot; aaron@hey-matcha.com",
}


def _cover(inp: FullDealInputs, date_str: str) -> str:
    company = escape(inp.company_name)
    loc = escape(inp.location.strip())
    line2 = f"{inp.headcount:,} Employees"
    if loc:
        line2 += f" &middot; {loc}"
    line2 += " &middot; Full Platform Access"
    prepared = (f"<p>Prepared for <strong>{company}</strong></p>"
                f"<p>{line2}</p>"
                f"<p>{date_str}</p>")
    return render_cover(None, _FULL_COVER_DEFAULTS, prepared)


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
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,600;1,9..144,400;1,9..144,500&family=Playfair+Display:ital,wght@0,500;0,600;1,500&family=Cormorant+Garamond:ital,wght@0,500;0,600;1,500&family=Space+Grotesk:wght@400;500;700&family=Inter:wght@300;400;500;600;700;800&display=swap');
  @page { size: letter; margin: 0.55in 0; }
  @page cover-page { size: letter; margin: 0; background: #1a1a2e; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Inter', -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #1a1a2e; font-size: 10.5pt; line-height: 1.55; }
  .cover { page: cover-page; page-break-after: always; background: linear-gradient(157deg, #21213f 0%, #15152c 52%, #0d0d1d 100%); color: white; height: 11in; padding: 104px 84px 62px; position: relative; overflow: hidden; }
  .cover::before { content: ''; position: absolute; top: -180px; right: -150px; width: 600px; height: 600px; border-radius: 50%; background: radial-gradient(circle, rgba(124,108,255,0.24) 0%, rgba(124,108,255,0) 68%); }
  .cover::after { content: ''; position: absolute; bottom: -140px; left: -120px; width: 480px; height: 480px; border-radius: 50%; background: radial-gradient(circle, rgba(167,139,250,0.10) 0%, rgba(167,139,250,0) 70%); }
  .cover .spine { position: absolute; top: 0; left: 0; width: 6px; height: 100%; background: linear-gradient(180deg, #7c6cff 0%, #a78bfa 100%); }
  .cover .cover-brand { position: relative; }
  .cover h1 { font-family: 'Inter'; font-size: 44pt; font-weight: 800; letter-spacing: -2px; margin-bottom: 11px; }
  .cover .subtitle { font-family: 'Inter'; font-size: 7.5pt; font-weight: 500; letter-spacing: 5.5px; text-transform: uppercase; color: rgba(255,255,255,0.5); }
  .cover .cover-lead { margin-top: 96px; position: relative; }
  .cover .product { font-family: 'Inter'; font-size: 10pt; font-weight: 600; letter-spacing: 4px; text-transform: uppercase; color: #b3a4ff; line-height: 1; }
  .cover .product strong { font-family: 'Fraunces'; font-weight: 600; color: #fff; display: block; font-size: 41pt; letter-spacing: -0.5px; line-height: 1.02; text-transform: none; margin-top: 16px; }
  .cover .divider { width: 60px; height: 3px; border-radius: 2px; background: linear-gradient(90deg, #7c6cff, #a78bfa); margin: 34px 0 30px; }
  .cover .quote { font-family: 'Fraunces'; font-style: italic; font-weight: 500; font-size: 15.5pt; color: rgba(255,255,255,0.74); line-height: 1.45; max-width: 76%; padding-left: 22px; border-left: 2px solid rgba(124,108,255,0.6); }
  .cover .prepared { position: absolute; left: 84px; right: 84px; bottom: 150px; font-size: 10.5pt; padding-top: 26px; border-top: 1px solid rgba(255,255,255,0.13); }
  .cover .prepared strong { font-weight: 600; font-size: 12.5pt; color: #fff; }
  .cover .prepared p { margin: 6px 0; color: rgba(255,255,255,0.8); }
  .cover .prepared p:first-child { letter-spacing: 0.2px; }
  .cover .footer { position: absolute; bottom: 52px; left: 84px; right: 84px; color: rgba(255,255,255,0.38); font-size: 8pt; letter-spacing: 0.3px; }
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
