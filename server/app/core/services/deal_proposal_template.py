"""Matcha pricing-proposal renderers for WeasyPrint.

Two layouts, selected by `DealInputs.template`:

- `render_proposal_html` ("standard") — the navy/purple 3-tier comparison ported from
  deals/la-nonprofit/LA_NonProfit_Pricing_OnePager_v2.1.html. The default.
- `render_lite_proposal_html` ("lite_edition") — alternate green single-tier Lite one-pager
  (copy from deals/lite_proposal_copy.md). Selected explicitly, not auto-applied to the Lite tier.

All money lines come from the pricing engine (`deal_pricing.compute_quote`) so the PDF and
the live UI never drift.
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
                f'<div class="r"><span>&minus;{q.broker_pct}% {escape(broker_label)}</span>'
                f'<span>&minus;{_fmt(q.broker_disc)}</span></div>'
            )
        if q.partner_disc:
            rows.append(
                f'<div class="r"><span>&minus;{q.partner_pct}% partner</span>'
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
            parts.append(f"{escape(broker_label)} <b>(&minus;{ref.broker_pct}%)</b>")
        if ref.partner_disc:
            parts.append(f"Partner <b>(&minus;{ref.partner_pct}%)</b>")
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


# ── Lite Edition — single-tier full-page proposal ─────────────────────────────
# Copy verbatim from deals/lite_proposal_copy.md (the "Matcha Lite — Lite Edition"
# one-pager). Used when the recommended tier is "lite".


def _lite_buildup(q: DealQuote, broker_label: str) -> str:
    rows = [f'<div class="ln"><span>Standard / yr</span><span>{_fmt(q.subscription_yr)}</span></div>']
    if q.onboarding:
        rows.append(f'<div class="ln"><span>Setup</span><span>+{_fmt(q.onboarding)}</span></div>')
    if q.broker_disc:
        rows.append(f'<div class="ln disc"><span>&minus;{q.broker_pct}% {escape(broker_label)}</span><span>&minus;{_fmt(q.broker_disc)}</span></div>')
    if q.partner_disc:
        rows.append(f'<div class="ln disc"><span>&minus;{q.partner_pct}% partner</span><span>&minus;{_fmt(q.partner_disc)}</span></div>')
    save = ""
    if q.you_save_yr:
        save = f'<div class="save">YOU SAVE {_fmt(q.you_save_yr)} &middot; {q.discount_pct}% OFF</div>'
    return "".join(rows) + save


# ── Lite Edition editable document ────────────────────────────────────────────
# Prose blocks are editable; "card" is computed from the Lite quote. `column` places
# blocks in the 2-column layout. Kinds: lead, h2, h3, h2c (centered), p, pc (centered),
# bullets ("Label: text" → bold label), card (computed).
LITE_COMPUTED_KINDS = {"card"}

DEFAULT_LITE_BLOCKS: list[dict] = [
    {"id": "lead", "kind": "lead", "column": "",
     "text": "A lite commitment that compounds into real risk insight. Incident capture built for the modern "
             "workforce, turning “we should track this” into a live, audit-ready record."},
    {"id": "card", "kind": "card", "column": "left"},
    {"id": "audit_h", "kind": "h3", "column": "left", "text": "Audit-Ready Compliance"},
    {"id": "audit_p", "kind": "p", "column": "left",
     "text": "Your OSHA 300, 300A, and 301 logs are available with a single click."},
    {"id": "audit_b", "kind": "bullets", "column": "left", "items": [
        "Multi-Location Management: Seamlessly track and report across different sites with centralized oversight.",
        "Reporting: Pull reports by date, location, and incident type to prep for board meetings, broker reviews, or renewal packages.",
    ]},
    {"id": "assist_h", "kind": "h3", "column": "left", "text": "Assistive, Not Unattended"},
    {"id": "assist_p", "kind": "p", "column": "left",
     "text": "Our AI is built to research, draft, and surface patterns, but it never acts alone. It flags exposure "
             "early so your team can make the final call. Every decision stays with your people."},
    {"id": "inc_h", "kind": "h2", "column": "right", "text": "What Lite Includes"},
    {"id": "copilot_h", "kind": "h3", "column": "right", "text": "The Reporting Copilot: Your Assistive Intake Partner"},
    {"id": "copilot_b", "kind": "bullets", "column": "right", "items": [
        "Conversational Intake: Type naturally to report incidents across Safety, Behavioral, Near Miss, Property, and more.",
        "Dynamic Guidance: As you provide details, the Copilot updates its guidance in real-time, asking the right follow-up questions to identify root causes.",
        "Compliance Guardrails: Automatically flags OSHA-reportable events and logs recordable details, including days away from work and restricted duty.",
        "Evidence Vault: Upload photos, witness statements, and documents directly to the incident record. Export any incident to a professional PDF with one click.",
    ]},
    {"id": "analysis_h", "kind": "h3", "column": "right", "text": "Incident Analysis & Theme Detection"},
    {"id": "analysis_b", "kind": "bullets", "column": "right", "items": [
        "Pattern Recognition: AI surfaces recurring themes and suggests actionable improvements for your team to review.",
        "Hotspot Monitoring: Immediately identify which locations are trending above baseline to prioritize your safety resources.",
        "Workers Comp Posture: See the direct financial narrative of your safety data with premium impact estimates based on your TRIR and DART trends.",
    ]},
    {"id": "hris_h", "kind": "h2c", "column": "right", "text": "HRIS Connect"},
    {"id": "hris_p", "kind": "pc", "column": "right",
     "text": "Auro Connect for supported vendors, CSV upload for out of network vendors."},
    {"id": "agree_h", "kind": "h2c", "column": "right", "text": "Agreement"},
    {"id": "agree_p", "kind": "pc", "column": "right",
     "text": "12-month initial term · all rates locked for the term · quarterly headcount true-up · 60-day opt-out."},
]


def _lite_card_html(quote_lite: DealQuote, broker_label: str) -> str:
    setup_note = "no setup fees" if quote_lite.onboarding == 0 else "setup included"
    return f"""<div class="card">
          <div class="tag">Your Tier &middot; Locked for the Term</div>
          <div class="name">{escape(quote_lite.tier_label)}</div>
          <div class="pepm">${quote_lite.pepm}.00 PEPM &middot; {setup_note}</div>
          {_lite_buildup(quote_lite, broker_label)}
          <div class="net"><span class="lbl">Your Price</span><span class="amt">{_fmt(quote_lite.your_price_yr)}<span class="yr">/yr</span></span></div>
        </div>"""


def _lite_bullets(items: list[str]) -> str:
    lis = []
    for it in items:
        if ": " in it:
            lab, rest = it.split(": ", 1)
            lis.append(f"<li><b>{escape(lab)}:</b> {escape(rest)}</li>")
        else:
            lis.append(f"<li>{escape(it)}</li>")
    return f"<ul>{''.join(lis)}</ul>"


def _lite_block_html(b, quote_lite: DealQuote, broker_label: str) -> str:
    k = b.kind
    if k == "h3":
        return f"<h3>{escape(b.text)}</h3>"
    if k == "h2":
        return f"<h2>{escape(b.text)}</h2>"
    if k == "h2c":
        return f'<h2 style="text-align:center">{escape(b.text)}</h2>'
    if k == "p":
        return f'<p class="sec">{escape(b.text)}</p>'
    if k == "pc":
        return f'<p style="text-align:center">{escape(b.text)}</p>'
    if k == "bullets":
        return _lite_bullets(b.items)
    if k == "card":
        return _lite_card_html(quote_lite, broker_label)
    return ""


def render_lite_proposal_html(inp: DealInputs, quote_lite: DealQuote) -> str:
    from .deal_pricing import Block

    proposal_date = inp.proposal_date or date.today()
    date_str = _fmt_date(proposal_date)
    broker_label = (inp.broker_name or "Broker").strip() if inp.broker else "Broker"
    company = escape(inp.company_name).upper()

    blocks = inp.lite_blocks if inp.lite_blocks is not None else [Block(**b) for b in DEFAULT_LITE_BLOCKS]
    lead = next((b for b in blocks if b.kind == "lead"), None)
    lead_html = f'<p class="lead">{escape(lead.text)}</p>' if lead else ""
    left_html = "".join(_lite_block_html(b, quote_lite, broker_label) for b in blocks if b.column == "left")
    right_html = "".join(_lite_block_html(b, quote_lite, broker_label) for b in blocks if b.column == "right")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: letter; margin: 0; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: Georgia, 'Times New Roman', serif; color: #2c3318; background: #ece3cf; font-size: 9pt; line-height: 1.4; }}
  .mono {{ font-family: 'Courier New', monospace; }}
  /* HEADER */
  .head {{ background: #2f3b1c; color: #ece3cf; padding: 13px 44px 15px; position: relative; }}
  .head .eyebrow {{ display: flex; justify-content: space-between; font-family: 'Courier New', monospace; font-size: 7pt; letter-spacing: 2.5px; text-transform: uppercase; color: rgba(236,227,207,0.65); }}
  .head h1 {{ font-size: 40pt; font-weight: 700; line-height: 0.88; margin-top: 5px; letter-spacing: -1px; }}
  .head h1 .lite {{ display: block; font-style: italic; font-size: 26pt; color: #c2a24e; font-weight: 400; }}
  .head .tag {{ font-style: italic; font-size: 11pt; margin-top: 7px; color: #ece3cf; }}
  .head .rail {{ position: absolute; right: 44px; bottom: 15px; text-align: right; font-family: 'Courier New', monospace; font-size: 7.5pt; letter-spacing: 1.5px; color: rgba(236,227,207,0.8); line-height: 1.7; }}
  .head .rail .lab {{ text-transform: uppercase; }}
  .head .rail .it {{ font-style: italic; }}
  /* GOLD META BAND */
  .meta {{ background: #b8923f; color: #2f3b1c; padding: 8px 44px; display: flex; justify-content: space-between; font-family: 'Courier New', monospace; font-size: 8.5pt; letter-spacing: 2px; text-transform: uppercase; font-weight: 700; }}
  /* BODY */
  .body {{ padding: 14px 44px 0; }}
  .lead {{ font-size: 12pt; line-height: 1.4; margin-bottom: 13px; }}
  .lead i {{ font-style: italic; }}
  .lead .hl {{ font-style: italic; color: #8a6d24; }}
  .cols {{ display: flex; gap: 34px; align-items: flex-start; }}
  .col {{ flex: 1; }}
  /* TIER CARD */
  .card {{ background: #2f3b1c; color: #ece3cf; border-radius: 4px; padding: 13px 18px 14px; margin-bottom: 14px; }}
  .card .tag {{ font-family: 'Courier New', monospace; font-size: 6.5pt; letter-spacing: 1.8px; text-transform: uppercase; color: #c2a24e; }}
  .card .name {{ font-size: 30pt; font-weight: 700; line-height: 1; margin: 2px 0; }}
  .card .pepm {{ font-family: 'Courier New', monospace; font-style: italic; color: #c2a24e; font-size: 9pt; margin-bottom: 12px; }}
  .card .ln {{ display: flex; justify-content: space-between; font-family: 'Courier New', monospace; font-size: 11pt; padding: 2px 0; }}
  .card .ln.disc {{ color: #c2a24e; }}
  .card .net {{ display: flex; justify-content: space-between; align-items: baseline; border-top: 1px solid rgba(236,227,207,0.3); margin-top: 10px; padding-top: 12px; }}
  .card .net .lbl {{ font-family: 'Courier New', monospace; font-size: 8.5pt; letter-spacing: 1.5px; text-transform: uppercase; color: #c2a24e; line-height: 1.1; max-width: 70px; }}
  .card .net .amt {{ font-size: 30pt; font-weight: 700; }}
  .card .net .amt .yr {{ font-size: 11pt; font-weight: 400; }}
  .card .save {{ font-family: 'Courier New', monospace; font-size: 9pt; letter-spacing: 1px; text-align: center; border-top: 1px solid rgba(236,227,207,0.3); margin-top: 12px; padding-top: 12px; }}
  /* SECTIONS */
  h2 {{ font-family: 'Courier New', monospace; font-size: 10pt; letter-spacing: 2.5px; text-transform: uppercase; color: #8a6d24; margin-bottom: 9px; }}
  h3 {{ font-size: 11pt; font-weight: 700; color: #2c3318; margin: 10px 0 4px; }}
  h3:first-child {{ margin-top: 0; }}
  p.sec {{ font-size: 9.5pt; margin-bottom: 5px; }}
  ul {{ list-style: none; }}
  li {{ font-size: 9.5pt; padding-left: 14px; position: relative; margin-bottom: 4px; line-height: 1.35; }}
  li::before {{ content: '\\2022'; position: absolute; left: 2px; color: #8a6d24; }}
  li b {{ font-style: italic; font-weight: 700; }}
  .centered {{ text-align: center; }}
  .centered h2 {{ text-align: center; }}
  .centered p {{ font-size: 9.5pt; }}
  /* FOOTER */
  .conf {{ text-align: center; font-family: 'Courier New', monospace; font-size: 7.5pt; letter-spacing: 0.5px; color: #6b6a52; margin: 13px 44px 0; padding-top: 11px; border-top: 1px solid rgba(44,51,24,0.18); }}
  .foot {{ background: #b8923f; color: #2f3b1c; padding: 9px 44px; display: flex; justify-content: space-between; align-items: center; font-family: 'Courier New', monospace; font-size: 8pt; letter-spacing: 1px; margin-top: 11px; }}
  .foot .talk {{ font-family: Georgia, serif; font-style: italic; }}
</style>
</head>
<body>

  <div class="head">
    <div class="eyebrow"><span>Risk Management &middot; Made Simple</span><span>Proposal &mdash; Lite Edition</span></div>
    <h1>Matcha<span class="lite">Lite</span></h1>
    <div class="tag">A Low-Friction Entry to High-Impact Risk Management.</div>
    <div class="rail"><div class="lab">Edition &middot; Lite</div><div class="it">Pricing Proposal &middot; MMXXVI</div></div>
  </div>

  <div class="meta">
    <span>{company} &nbsp;&middot;&nbsp; {inp.headcount:,} Employees</span>
    <span>{date_str}</span>
  </div>

  <div class="body">
    {lead_html}
    <div class="cols">
      <div class="col">{left_html}</div>
      <div class="col">{right_html}</div>
    </div>
  </div>

  <div class="conf">Confidential &mdash; proprietary pricing for the named recipient. Valid 30 days from {date_str}.</div>
  <div class="foot">
    <span>DIRECT &nbsp; aaron@hey-matcha.com</span>
    <span class="talk">&larr; Let&rsquo;s talk &rarr;</span>
    <span>WEB &nbsp; hey-matcha.com</span>
  </div>

</body>
</html>"""
