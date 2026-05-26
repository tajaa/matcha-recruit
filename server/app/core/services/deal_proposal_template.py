"""Render a single-page Matcha pricing proposal (Mid + Max) to HTML for WeasyPrint.

CSS + structure ported from deals/la-nonprofit/LA_NonProfit_Pricing_OnePager_v2.1.html.
The Lite card from the source is dropped; only Mid + Max are rendered, with the selected
tier highlighted (`.tier.feature`). All money lines come from the pricing engine
(`deal_pricing.compute_quote`) so the PDF and the live UI never drift.
"""

from __future__ import annotations

from datetime import date
from html import escape

from .deal_pricing import DealInputs, DealQuote, HR_PARTNER_MONTHLY

# Tier feature bullets (verbatim from the v2.1 onepager).
_LITE_BULLETS = [
    ("Incident Reporting", "workplace &amp; field safety intake, photo/witness capture, anonymous channel"),
    ("IR Analysis", "AI categorization, severity scoring, cross-incident pattern detection"),
    ("OSHA 300 / 300A Logs", "recordable tracking, auto-tallied, audit-ready export"),
]
_MID_BULLETS = [
    ("Compliance Engine", "continuous Fed + state + local tracking, mapped to your sites &amp; roles"),
    ("Legislative Tracker", "alerts on min-wage, sick-leave &amp; fair-workweek changes before they take effect"),
    ("License &amp; Training Tracking", "auto expiry alerts &amp; renewal automation for every credential"),
]
_MAX_BULLETS = [
    ("ER Copilot", "AI assistive investigations: auto timelines, discrepancy flags, instant policy lookup, counsel-ready case export"),
    ("Risk Assessment", "quantitative exposure modeling &amp; board-ready risk dashboard"),
    ("Matcha Work", "assistive AI workspace: draft handbooks &amp; policy, research law, chat with your live HR data"),
    ("White-Glove Implementation", "full gap analysis, data migration &amp; dedicated HR-partner onboarding"),
]
_MAX_WHY = (
    "Covers the whole risk surface — ER investigations, quantitative exposure modeling, and an "
    "assistive AI workspace — and ships with the human HR partner who's done it before."
)


def _fmt(n: int) -> str:
    return f"${n:,}"


def _fmt_date(d: date) -> str:
    return d.strftime("%B %-d, %Y")


def _build_up_rows(q: DealQuote, broker_label: str) -> str:
    """The per-tier price build-up (subscription → onboarding → discounts → net)."""
    onb_val = "None" if q.onboarding == 0 else f"+{_fmt(q.onboarding)}"
    rows = [
        f'<div class="r std"><span>Subscription / yr</span><span>{_fmt(q.subscription_yr)}</span></div>',
        f'<div class="r"><span>Onboarding</span><span>{onb_val}</span></div>',
    ]
    has_discount = q.broker_disc or q.partner_disc
    if has_discount:
        rows.append(f'<div class="r sub"><span>Subtotal</span><span>{_fmt(q.subtotal)}</span></div>')
        if q.broker_disc:
            rows.append(
                f'<div class="r"><span>&minus;10% {escape(broker_label)}</span>'
                f'<span>&minus;{_fmt(q.broker_disc)}</span></div>'
            )
        if q.partner_disc:
            rows.append(
                f'<div class="r"><span>&minus;5% partner</span>'
                f'<span>&minus;{_fmt(q.partner_disc)}</span></div>'
            )
    rows.append(
        f'<div class="r net"><span>Your price</span>'
        f'<span>{_fmt(q.your_price_yr)}<span class="yr"> /yr</span></span></div>'
    )
    save = ""
    if q.you_save_yr:
        save = f'<span class="save">You save {_fmt(q.you_save_yr)} / yr</span>'
    return "".join(rows) + save


def _bullets(items: list[tuple[str, str]]) -> str:
    return "".join(f"<li><b>{name}</b> &mdash; {desc}</li>" for name, desc in items)


def _tier_card(
    q: DealQuote,
    *,
    is_feature: bool,
    pepm_note: str,
    div_label: str,
    bullets_html: str,
    broker_label: str,
    inc_line: str = "",
    why: str = "",
    tag: str = "",
) -> str:
    cls = "tier feature" if is_feature else "tier"
    tag_html = f'<div class="tag">{tag}</div>' if tag else '<div class="tag"></div>'
    inc_html = f'<li class="inc">{inc_line}</li>' if inc_line else ""
    why_html = f'<div class="why"><b>Why {q.tier_label} for you:</b> {why}</div>' if why else ""
    note = "no onboarding fee" if q.onboarding == 0 else pepm_note
    return f"""
      <div class="{cls}">
        {tag_html}
        <div class="name">{q.tier_label}</div>
        <div class="pepm"><b>${q.pepm}</b> PEPM &middot; {note}</div>
        <div class="rb">
          {_build_up_rows(q, broker_label)}
        </div>
        <div class="div">{div_label}</div>
        <ul>
          {bullets_html}
          {inc_html}
        </ul>
        {why_html}
      </div>"""


def render_proposal_html(inp: DealInputs, quotes: dict[str, DealQuote]) -> str:
    proposal_date = inp.proposal_date or date.today()
    date_str = _fmt_date(proposal_date)
    broker_label = (inp.broker_name or "Broker").strip() if inp.broker else "Broker"
    company = escape(inp.company_name)
    quote_lite, quote_mid, quote_max = quotes["lite"], quotes["mid"], quotes["max"]

    # Savings banner (only when a discount applies; uses Max as the discount reference).
    ref = quote_max
    if ref.discount_pct:
        parts = []
        if ref.broker_disc:
            parts.append(f"{escape(broker_label)} <b>(&minus;10%)</b>")
        if ref.partner_disc:
            parts.append("Partner <b>(&minus;5%)</b>")
        detail = " + ".join(parts) + ", applied to subscription &amp; onboarding and locked for the term."
        svband = f"""
    <div class="svband">
      <div class="t">Your pricing &mdash; {ref.discount_pct}% below list</div>
      <div class="d">{detail}</div>
    </div>"""
    else:
        svband = ""

    lite_card = _tier_card(
        quote_lite,
        is_feature=(inp.tier == "lite"),
        pepm_note="guided onboarding",
        div_label="Includes",
        bullets_html=_bullets(_LITE_BULLETS),
        broker_label=broker_label,
        tag="Recommended &mdash; best fit" if inp.tier == "lite" else "",
    )
    mid_card = _tier_card(
        quote_mid,
        is_feature=(inp.tier == "mid"),
        pepm_note="guided onboarding",
        div_label="Everything in Lite, plus",
        bullets_html=_bullets(_MID_BULLETS),
        inc_line="Incident Reporting, IR Analysis, OSHA logs",
        broker_label=broker_label,
        tag="Recommended &mdash; best fit" if inp.tier == "mid" else "",
    )
    max_card = _tier_card(
        quote_max,
        is_feature=(inp.tier == "max"),
        pepm_note="white-glove implementation",
        div_label="Everything in Mid, plus",
        bullets_html=_bullets(_MAX_BULLETS),
        broker_label=broker_label,
        why=_MAX_WHY if inp.tier == "max" else "",
        tag="Recommended &mdash; best fit" if inp.tier == "max" else "",
    )

    addon = ""
    if inp.hr_partner_addon:
        addon = f"""
  <div class="addon">
    <div class="l">
      <div class="t">Add-On &mdash; <span>HR Partner</span></div>
      <div class="d">A dedicated senior HR practitioner on standing call &mdash; bi-weekly 45-minute working
        sessions to review open ER cases, pressure-test decisions, and steer strategy. An extra human layer on
        top of the platform. Available on any tier; <em>bundled with Max onboarding</em>.</div>
    </div>
    <div class="r">
      <div class="price">{_fmt(HR_PARTNER_MONTHLY)}<span> / mo</span></div>
    </div>
  </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: letter; margin: 0; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #1a1a2e; font-size: 8pt; line-height: 1.38; }}
  .sheet {{ padding: 0; }}
  .band {{ background: #1a1a2e; color: white; padding: 13px 40px 10px; position: relative; overflow: hidden; }}
  .band::after {{ content: ''; position: absolute; top: -90px; right: -70px; width: 230px; height: 230px; border-radius: 50%; background: rgba(108,99,255,0.10); }}
  .band h1 {{ font-size: 24pt; font-weight: 800; letter-spacing: -0.5px; }}
  .band .sub {{ font-size: 6.3pt; letter-spacing: 3.5px; text-transform: uppercase; color: rgba(255,255,255,0.55); margin: 2px 0 9px; }}
  .band .meta {{ font-size: 8.6pt; color: rgba(255,255,255,0.9); }}
  .band .meta strong {{ font-weight: 700; }}
  .accent {{ width: 44px; height: 3px; background: #6c63ff; margin: 8px 0; }}
  .body {{ padding: 11px 40px 0; }}
  .lead {{ font-size: 8.6pt; color: #333; margin-bottom: 8px; line-height: 1.46; }}
  .lead strong {{ color: #1a1a2e; }}
  .lead .hl {{ color: #6c63ff; font-weight: 700; }}
  .svband {{ background: #f3f2ff; border: 1px solid #d9d6ff; border-radius: 5px; padding: 6px 13px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; }}
  .svband .t {{ font-weight: 800; color: #4a43c9; font-size: 8.2pt; }}
  .svband .d {{ color: #6a66a0; font-size: 7.4pt; }}
  .svband .d b {{ color: #4a43c9; }}
  .tiers {{ display: flex; gap: 10px; align-items: stretch; }}
  .tier {{ flex: 1 1 0; border: 1px solid #e0e0ea; border-radius: 6px; padding: 10px 12px 12px; }}
  .tier.feature {{ border: 1.8px solid #6c63ff; background: #fbfaff; flex: 1.12 1 0; }}
  .tier .tag {{ font-size: 5.7pt; letter-spacing: 1.2px; text-transform: uppercase; font-weight: 800; color: #6c63ff; min-height: 9px; margin-bottom: 2px; white-space: nowrap; }}
  .tier .name {{ font-size: 11.5pt; font-weight: 800; color: #1a1a2e; line-height: 1; }}
  .tier .pepm {{ font-size: 7.2pt; color: #888; margin: 2px 0 7px; }}
  .tier .pepm b {{ color: #1a1a2e; font-weight: 700; }}
  .rb {{ font-size: 7pt; border-top: 1px solid #eee; padding-top: 6px; }}
  .rb .r {{ display: flex; justify-content: space-between; padding: 0.8px 0; color: #8a8a96; }}
  .rb .r.std {{ color: #555; font-weight: 600; }}
  .rb .r.sub {{ color: #555; font-weight: 700; border-top: 1px solid #eee; margin-top: 2px; padding-top: 3px; }}
  .rb .r.net {{ color: #1a1a2e; font-weight: 800; font-size: 11pt; border-top: 1px solid #ddd; margin-top: 4px; padding-top: 5px; }}
  .rb .r.net .yr {{ font-size: 6.4pt; font-weight: 600; color: #999; }}
  .save {{ font-size: 6.7pt; font-weight: 700; color: #2e9e6b; background: #ecf9f2; border-radius: 3px; padding: 2px 6px; margin: 6px 0 0; display: block; }}
  .tier .div {{ font-size: 6.1pt; letter-spacing: 0.7px; text-transform: uppercase; color: #aaa; font-weight: 700; margin: 8px 0 5px; }}
  .tier ul {{ list-style: none; }}
  .tier ul li {{ font-size: 7.3pt; color: #444; padding-left: 11px; position: relative; margin-bottom: 4px; line-height: 1.3; }}
  .tier ul li::before {{ content: ''; position: absolute; left: 0; top: 4px; width: 4px; height: 4px; background: #6c63ff; border-radius: 50%; }}
  .tier ul li b {{ color: #1a1a2e; }}
  .tier ul li.inc {{ color: #999; font-style: italic; }}
  .tier ul li.inc::before {{ background: #ccc; }}
  .tier .why {{ font-size: 7pt; color: #4a43c9; background: #f3f2ff; border-radius: 4px; padding: 6px 8px; margin-top: 8px; line-height: 1.35; }}
  .tier .why b {{ color: #2f2a8f; }}
  .addon {{ background: #1a1a2e; color: white; margin: 14px 40px 0; padding: 11px 18px; border-radius: 5px; display: flex; justify-content: space-between; align-items: center; }}
  .addon .l .t {{ font-size: 9.5pt; font-weight: 800; }}
  .addon .l .t span {{ color: #9b95ff; }}
  .addon .l .d {{ font-size: 7.6pt; color: rgba(255,255,255,0.78); margin-top: 2px; max-width: 470px; line-height: 1.4; }}
  .addon .r {{ text-align: right; white-space: nowrap; padding-left: 16px; }}
  .addon .r .price {{ font-size: 13pt; font-weight: 800; }}
  .addon .r .price span {{ font-size: 7.4pt; font-weight: 600; color: rgba(255,255,255,0.6); }}
  .section {{ padding: 13px 40px 0; }}
  h2 {{ font-size: 7.8pt; letter-spacing: 2px; text-transform: uppercase; color: #1a1a2e; border-bottom: 2px solid #1a1a2e; padding-bottom: 4px; margin-bottom: 9px; }}
  .pillars {{ display: flex; gap: 18px; }}
  .pillar {{ flex: 1; border-top: 2px solid #6c63ff; padding-top: 6px; }}
  .pillar .t {{ font-weight: 700; color: #1a1a2e; font-size: 8pt; margin-bottom: 2px; }}
  .pillar .d {{ color: #555; font-size: 7.2pt; line-height: 1.3; }}
  .foot {{ padding: 10px 40px 0; margin-top: 12px; font-size: 6.9pt; color: #999; border-top: 1px solid #eee; display: flex; justify-content: space-between; align-items: center; white-space: nowrap; }}
  .foot strong {{ color: #666; }}
  .conf {{ font-size: 7.1pt; color: #555; font-weight: 600; }}
  .conf b {{ color: #1a1a2e; text-transform: uppercase; letter-spacing: 0.6px; }}
</style>
</head>
<body>
<div class="sheet">

  <div class="band">
    <h1>matcha</h1>
    <div class="sub">Assistive Risk, Compliance &amp; Employee Relations</div>
    <div class="accent"></div>
    <div class="meta">Pricing Proposal &mdash; <strong>{company}</strong> &nbsp;&middot;&nbsp; {inp.headcount:,} Employees &nbsp;&middot;&nbsp; {date_str}</div>
  </div>

  <div class="body">
    <p class="lead">Matcha is <span class="hl">assistive risk management</span> &mdash; it tracks every jurisdiction, assists the investigation workflow, and monitors credentials in real time, surfacing what needs attention before it becomes exposure. But <strong>assistive isn&rsquo;t unattended: every decision is made by your team.</strong> State-of-the-science AI coupled with the judgment of people who&rsquo;ve spent their careers in the HR, compliance, and employee-relations seat &mdash; all in one platform.</p>
    {svband}
    <div class="tiers">
      {lite_card}
      {mid_card}
      {max_card}
    </div>
  </div>
  {addon}

  <div class="section">
    <h2>Why Matcha &mdash; Not Just Software</h2>
    <div class="pillars">
      <div class="pillar"><div class="t">People Strategy</div><div class="d">Compensation, handbooks, performance, and org design &mdash; guided by seasoned HR practitioners.</div></div>
      <div class="pillar"><div class="t">Governance, Risk &amp; Compliance</div><div class="d">Frameworks tailored to your jurisdiction and stage &mdash; built to scale, audit-ready from day one.</div></div>
      <div class="pillar"><div class="t">Employee Relations</div><div class="d">Run investigations, resolve conflict, and build case strategy in-platform &mdash; backed by employment-law expertise, your team in the lead.</div></div>
      <div class="pillar"><div class="t">Assistive AI, Built In</div><div class="d">AI researches, drafts, and surfaces what matters across your live data &mdash; cited, sourced, and reviewed by humans before anyone acts.</div></div>
    </div>
  </div>

  <div class="foot">
    <span><strong>hey-matcha.com</strong> &middot; aaron@hey-matcha.com</span>
    <span class="conf"><b>Confidential</b> &mdash; named recipient only &middot; do not distribute &middot; valid 30 days from {date_str}</span>
  </div>

</div>
</body>
</html>"""
