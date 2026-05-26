"""Render the full multi-page Matcha service proposal to HTML for WeasyPrint.

Structure + CSS ported from deals/la-nonprofit/LA_NonProfit_Proposal_v1.html (~10 pages).
Pricing tables, cover meta, jurisdiction schedule, contract-terms price lock, and ROI are
parameterized from `deal_full.compute_full_pricing`. Executive Summary and the ROI intro are
editable prose (from `FullDealInputs`); capability / implementation / terms / security prose
is ported verbatim as standard boilerplate.
"""

from __future__ import annotations

from datetime import date
from html import escape

from .deal_full import FullDealInputs, FullQuote


def _m(n: int) -> str:
    return f"${n:,}"


def _p(v: float) -> str:
    return f"${v:,.2f}"


def _fmt_date(d: date) -> str:
    return d.strftime("%B %-d, %Y")


def _paras(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def _pepm_buildup(q: FullQuote) -> str:
    rows = [f'<tr class="row-step"><td style="text-align:left">Standard PEPM rate</td><td>{_p(q.rack_pepm)}</td></tr>']
    if q.volume_applied:
        rows.append(
            f'<tr class="row-step"><td style="text-align:left">Less 10% volume discount '
            f'<em>(automatic at 500+ employees)</em></td><td>&minus;{_p(q.volume_pepm_cut)}</td></tr>'
        )
        rows.append(f'<tr class="row-sub"><td style="text-align:left">Subtotal</td><td>{_p(q.subtotal_pepm)}</td></tr>')
    if q.bp_rate_pct:
        rows.append(
            f'<tr class="row-step"><td style="text-align:left">Less {q.bp_rate_pct}% Broker + Partner discount</td>'
            f'<td>&minus;{_p(q.bp_pepm_cut)}</td></tr>'
        )
    rows.append(f'<tr class="row-total"><td style="text-align:left">Your locked PEPM rate</td><td>{_p(q.your_pepm)}</td></tr>')
    return "".join(rows)


def render_full_proposal_html(inp: FullDealInputs, q: FullQuote) -> str:
    pdate = inp.proposal_date or date.today()
    date_str = _fmt_date(pdate)
    company = escape(inp.company_name)
    loc = escape(inp.location.strip())
    broker_label = (inp.broker_name or "Broker").strip() if inp.broker else "Broker"

    cover_line2 = f"{inp.headcount:,} Employees"
    if loc:
        cover_line2 += f" &middot; {loc}"
    cover_line2 += " &middot; Full Platform Access"

    exec_paras = _paras(inp.exec_summary)
    exec_callout = escape(exec_paras[0]) if exec_paras else ""
    exec_rest = "".join(f"<p>{escape(p)}</p>" for p in exec_paras[1:])
    roi_intro = "".join(f"<p>{escape(p)}</p>" for p in _paras(inp.roi_intro))

    extra_juris_row = ""
    if q.extra_jurisdiction_cost:
        extra_juris_row = (
            f'<tr><td style="text-align:left">Additional jurisdictions '
            f'({inp.jurisdictions_extra} &times; {_m(q.juris_fee)})</td>'
            f'<td class="calc-cell">{q.juris_tier} tier</td><td><strong>{_m(q.extra_jurisdiction_cost)}</strong></td></tr>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  @page {{ size: letter; margin: 0.55in 0; }}
  @page cover-page {{ size: letter; margin: 0; background: #1a1a2e; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, 'Helvetica Neue', Arial, sans-serif; color: #1a1a2e; font-size: 10.5pt; line-height: 1.55; }}
  .cover {{ page: cover-page; page-break-after: always; background: #1a1a2e; color: white; height: 11in; padding: 80px 70px 60px; position: relative; overflow: hidden; }}
  .cover::after {{ content: ''; position: absolute; top: -120px; right: -120px; width: 500px; height: 500px; border-radius: 50%; background: rgba(255,255,255,0.03); }}
  .cover::before {{ content: ''; position: absolute; bottom: -80px; left: -80px; width: 400px; height: 400px; border-radius: 50%; background: rgba(255,255,255,0.02); }}
  .cover h1 {{ font-size: 42pt; font-weight: 800; letter-spacing: -1px; margin-bottom: 4px; }}
  .cover .subtitle {{ font-size: 8pt; letter-spacing: 5px; text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 6px; }}
  .cover .product {{ font-size: 22pt; font-weight: 300; color: rgba(255,255,255,0.8); }}
  .cover .product strong {{ font-weight: 700; color: white; display: block; font-size: 30pt; }}
  .cover .divider {{ width: 60px; height: 3px; background: #6c63ff; margin: 30px 0; }}
  .cover .quote {{ font-style: italic; color: rgba(255,255,255,0.6); font-size: 12pt; margin-bottom: 40px; }}
  .cover .prepared {{ font-size: 11pt; }}
  .cover .prepared strong {{ font-size: 13pt; }}
  .cover .prepared p {{ margin: 4px 0; color: rgba(255,255,255,0.85); }}
  .cover .footer {{ position: absolute; bottom: 60px; left: 70px; color: rgba(255,255,255,0.35); font-size: 8.5pt; }}
  .cover .footer p {{ margin: 3px 0; }}
  .page {{ padding: 8px 60px 28px; }}
  .page.fresh {{ page-break-before: always; }}
  h2, h3, h4 {{ page-break-after: avoid; }}
  table, .callout, .highlight-box, .signatures, ul.bullet {{ page-break-inside: avoid; }}
  tr {{ page-break-inside: avoid; }}
  thead {{ display: table-header-group; }}
  .page-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; padding-bottom: 12px; border-bottom: 2px solid #1a1a2e; }}
  .page-header .logo {{ font-size: 13pt; font-weight: 800; color: #1a1a2e; }}
  .page-header .section-label {{ font-size: 7pt; letter-spacing: 4px; text-transform: uppercase; color: #888; }}
  h2 {{ font-size: 22pt; font-weight: 700; color: #1a1a2e; margin-bottom: 18px; }}
  h3 {{ font-size: 13pt; font-weight: 700; color: #1a1a2e; margin-top: 22px; margin-bottom: 10px; }}
  h4 {{ font-size: 11pt; font-weight: 700; color: #1a1a2e; margin-top: 16px; margin-bottom: 6px; }}
  p, li {{ margin-bottom: 8px; color: #333; }}
  .callout {{ border-left: 3px solid #1a1a2e; padding: 16px 20px; background: #f8f8fa; margin: 16px 0; font-size: 10pt; color: #444; line-height: 1.6; }}
  .highlight-box {{ background: #1a1a2e; color: white; padding: 14px 24px; border-radius: 4px; margin: 16px 0; font-size: 11pt; font-weight: 600; }}
  table {{ width: 100%; border-collapse: collapse; margin: 14px 0 20px; font-size: 9.5pt; }}
  thead th {{ background: #1a1a2e; color: white; padding: 10px 14px; text-align: left; font-size: 7.5pt; letter-spacing: 2px; text-transform: uppercase; font-weight: 600; }}
  thead th:last-child, thead th:nth-child(n+2) {{ text-align: right; }}
  tbody td {{ padding: 9px 14px; border-bottom: 1px solid #eee; }}
  tbody td:last-child, tbody td:nth-child(n+2) {{ text-align: right; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  .row-bold td {{ font-weight: 700; border-top: 2px solid #1a1a2e; padding-top: 12px; }}
  .row-total td {{ font-weight: 700; font-size: 10.5pt; border-top: 2px solid #1a1a2e; padding-top: 12px; }}
  .row-gray td {{ color: #666; font-style: italic; }}
  .row-step td {{ color: #555; }}
  .row-sub td {{ font-weight: 600; border-top: 1px solid #ccc; }}
  .note {{ font-size: 8.5pt; color: #777; font-style: italic; line-height: 1.5; margin: 10px 0; }}
  .note strong {{ color: #555; }}
  .terms-table td:first-child {{ font-weight: 700; width: 200px; vertical-align: top; }}
  .terms-table td {{ text-align: left !important; padding: 8px 14px; }}
  .signatures {{ display: flex; gap: 60px; margin-top: 30px; }}
  .sig-block {{ flex: 1; }}
  .sig-block h4 {{ font-size: 12pt; margin-bottom: 18px; }}
  .sig-line {{ border-bottom: 1px solid #333; margin-bottom: 6px; height: 26px; }}
  .sig-label {{ font-size: 8.5pt; color: #888; margin-bottom: 12px; }}
  .disclaimer {{ font-size: 8pt; color: #999; font-style: italic; text-align: center; padding-top: 12px; border-top: 1px solid #ddd; margin-top: 16px; line-height: 1.5; }}
  ul.bullet {{ padding-left: 18px; margin: 10px 0; }}
  ul.bullet li {{ margin-bottom: 6px; }}
  .two-col-table td:first-child {{ text-align: left !important; }}
  .calc-cell {{ text-align: right; color: #666; font-size: 9pt; }}
</style>
</head>
<body>

<div class="cover">
  <h1>matcha</h1>
  <div class="subtitle">Risk, Compliance, Employee Relations Intelligence</div>
  <div class="product">Platform<br><strong>Service Proposal</strong></div>
  <div class="divider"></div>
  <div class="quote">"Manage your risk or your risk will manage you."</div>
  <div class="prepared">
    <p>Prepared for <strong>{company}</strong></p>
    <p>{cover_line2}</p>
    <p>{date_str}</p>
  </div>
  <div class="footer">
    <p>Confidential &mdash; This document contains proprietary pricing and is intended solely for the named recipient.</p>
    <p>hey-matcha.com &middot; aaron@hey-matcha.com</p>
  </div>
</div>

<div class="page">
  <div class="page-header">
    <div class="logo">matcha</div>
    <div class="section-label">Service Proposal &middot; {company}</div>
  </div>

  <h2>Executive Summary</h2>
  <div class="callout">{exec_callout}</div>
  {exec_rest}

  <h2>Investment Summary</h2>
  <p>Matcha is priced <strong>per employee, per month (PEPM)</strong> &mdash; one rate that covers full platform access for every person on your team. Below is exactly how your rate is built, with no hidden steps.</p>

  <h3>Step 1 &mdash; How your per-employee rate is built</h3>
  <table>
    <thead><tr><th style="text-align:left">Build-up</th><th>Rate per employee / month</th></tr></thead>
    <tbody>{_pepm_buildup(q)}</tbody>
  </table>

  <h3>Step 2 &mdash; What that costs per year</h3>
  <table>
    <thead><tr><th style="text-align:left">Line Item</th><th style="text-align:right">How it&rsquo;s calculated</th><th>Annual</th></tr></thead>
    <tbody>
      <tr><td style="text-align:left">Platform usage (all {q.headcount:,} employees)</td><td class="calc-cell">{_p(q.your_pepm)} &times; {q.headcount:,} &times; 12 months</td><td><strong>{_m(q.annual_employee_your)}</strong></td></tr>
      <tr><td style="text-align:left">Platform fee (first jurisdiction included)</td><td class="calc-cell">flat annual fee</td><td><strong>{_m(q.platform_fee_your)}</strong></td></tr>
      {extra_juris_row}
      <tr><td style="text-align:left">HR Advisory &mdash; Basic (1 session/month)</td><td class="calc-cell">&mdash;</td><td><strong>Included w/ Partner</strong></td></tr>
      <tr class="row-bold"><td style="text-align:left">Annual Recurring</td><td class="calc-cell"></td><td>{_m(q.annual_recurring_your)}</td></tr>
      <tr><td style="text-align:left">Implementation &amp; Configuration (one-time, Year 1 only)</td><td class="calc-cell">flat one-time fee</td><td><strong>{_m(q.implementation_your)}</strong></td></tr>
      <tr class="row-total"><td style="text-align:left">Year 1 Total</td><td class="calc-cell">{_m(q.annual_recurring_your)} + {_m(q.implementation_your)}</td><td>{_m(q.year1_your)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Year 2+ Annual (recurring only)</td><td class="calc-cell">recurring only</td><td>{_m(q.year2_your)}</td></tr>
    </tbody>
  </table>
  <p class="note">All rates locked for the initial 12-month term. Implementation &amp; Configuration is a one-time fee; subsequent years require only the annual recurring cost.</p>

  <h3>HR Advisory Rate Card</h3>
  <p class="note">Basic HR Advisory (1 session/month, 45 min each) is included with your Partner Program subscription. Additional Consulting Services are available at the rates below.</p>
  <table>
    <thead><tr><th style="text-align:left">HR Advisory Tier</th><th style="text-align:left">What&rsquo;s Included</th><th>Annual Rate</th></tr></thead>
    <tbody>
      <tr><td style="text-align:left"><strong>Basic</strong></td><td style="text-align:left">1 session/month (12/year, 45 min each)</td><td><strong>Included w/ Partner</strong></td></tr>
      <tr><td style="text-align:left"><strong>Consulting Retainer</strong></td><td style="text-align:left">4 sessions/month (48/year, 60 min each)</td><td><strong>$12,000/yr</strong></td></tr>
      <tr><td style="text-align:left"><strong>On-Demand</strong></td><td style="text-align:left">Additional sessions beyond your included allotment</td><td><strong>$650/session</strong></td></tr>
    </tbody>
  </table>
</div>

<div class="page">
  <h3>Your Savings &mdash; Standard vs. Your Price</h3>
  <p class="note">The table below compares the full standard list price to your final price, line by line.</p>
  <table>
    <thead><tr><th style="text-align:left">Line Item</th><th>Standard List</th><th>Your Price</th><th>You Save</th></tr></thead>
    <tbody>
      <tr><td style="text-align:left">PEPM rate</td><td>{_p(q.rack_pepm)}</td><td><strong>{_p(q.your_pepm)}</strong></td><td>{_p(q.pepm_save)} / ee / mo</td></tr>
      <tr><td style="text-align:left">Annual employee cost ({q.headcount:,} employees)</td><td>{_m(q.annual_employee_standard)}</td><td><strong>{_m(q.annual_employee_your)}</strong></td><td>{_m(q.annual_employee_save)}</td></tr>
      <tr><td style="text-align:left">Platform fee (first jurisdiction included)</td><td>{_m(q.platform_fee_standard)}</td><td><strong>{_m(q.platform_fee_your)}</strong></td><td>{_m(q.platform_save)}</td></tr>
      <tr class="row-bold"><td style="text-align:left">Annual Recurring</td><td>{_m(q.annual_recurring_standard)}</td><td><strong>{_m(q.annual_recurring_your)}</strong></td><td>{_m(q.recurring_save)}</td></tr>
      <tr><td style="text-align:left">Implementation &amp; Configuration</td><td>{_m(q.implementation_standard)}</td><td><strong>{_m(q.implementation_your)}</strong></td><td>{_m(q.implementation_save)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Year 1 Total</td><td>{_m(q.year1_standard)}</td><td><strong>{_m(q.year1_your)}</strong></td><td>{_m(q.year1_save)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Year 2+ Annual</td><td>{_m(q.annual_recurring_standard)}</td><td><strong>{_m(q.annual_recurring_your)}</strong></td><td>{_m(q.recurring_save)}</td></tr>
    </tbody>
  </table>
  <p class="note"><strong>Volume Discount (10% off PEPM)</strong> &mdash; Applied automatically for organizations with 500 or more employees.</p>
  <p class="note"><strong>Broker Pricing (10% off)</strong> &mdash; Applied when purchasing through an authorized Matcha broker partner.</p>
  <p class="note"><strong>Partner Program (additional 5% off)</strong> &mdash; Requires quarterly business reviews, anonymized benchmarking participation, logo rights, one public platform review within 90 days of go-live, and annual prepayment or 2-year term commitment.</p>

  <h3>Jurisdiction Fee Schedule</h3>
  <p class="note">A Jurisdiction is any U.S. state, city, county, or municipality in which Client has employees and which imposes distinct compliance obligations. Local city/county ordinances are configured within their parent state jurisdiction at no additional charge; a separate state would be scoped as an additional Jurisdiction.</p>
  <table>
    <thead><tr><th style="text-align:left">Client Tier</th><th style="text-align:left">Headcount</th><th>Per Additional Jurisdiction / Year</th></tr></thead>
    <tbody>
      <tr><td style="text-align:left">Growth</td><td style="text-align:left">1&ndash;249</td><td>$3,200</td></tr>
      <tr><td style="text-align:left"><strong>Business</strong></td><td style="text-align:left"><strong>250&ndash;999</strong></td><td><strong>$7,500</strong></td></tr>
      <tr><td style="text-align:left">Enterprise</td><td style="text-align:left">1,000+</td><td>$10,000</td></tr>
    </tbody>
  </table>
  <p class="note">At {q.headcount:,} employees, {company} is in the <strong>{q.juris_tier}</strong> tier &mdash; additional jurisdictions are billed at {_m(q.juris_fee)}/year each. Price locked for the 12-month initial term. Employee count subject to quarterly true-up.</p>
</div>

<div class="page fresh">
  <div class="page-header"><div class="logo">matcha</div><div class="section-label">Platform Capabilities</div></div>
  <h2>Platform Capabilities</h2>
  <h3>Compliance &amp; Legal</h3>
  <h4>Compliance Engine</h4>
  <p>Agentic jurisdiction research across federal, state, and local levels. Multi-location and multi-site support with preemption rule analysis. Tiered data approach: structured requirements, curated repository, and agentic research for emerging regulations. The engine continuously tracks employment law together with applicable city and county ordinances &mdash; minimum-wage indexing, paid-sick-leave ordinances, fair-workweek rules, meal and rest break requirements, and background-check and mandated-reporter obligations. When a jurisdiction raises its minimum wage or a new ordinance changes scheduling or sick-leave accrual, the engine surfaces the change mapped to the affected staff before it becomes a back-pay liability. Everything tracked in a single dashboard rather than siloed across HR, finance, and leadership.</p>
  <h4>Policies &amp; Handbooks</h4>
  <p>Intelligent policy documents tailored to specific jurisdictions and program environments. Electronic signature collection with audit trails. Auto-research fills jurisdiction-specific topics during handbook creation &mdash; data-privacy acknowledgments, code-of-conduct policies, mandated-reporter policies, and jurisdiction-specific wage, leave, and harassment-prevention policies, all generated from your jurisdiction and program profile rather than drafted from scratch by counsel. When a new site comes online or a requirement updates, the handbook auto-updates the affected sections and triggers bulk re-acknowledgment for impacted staff.</p>
  <h4>Legislative Tracker</h4>
  <p>Intelligent monitoring of regulatory changes across jurisdictions with pattern detection for coordinated legislative activity &mdash; real-time alerts on minimum-wage changes, paid-sick-leave and fair-workweek updates, and new requirements affecting your workforce. When a jurisdiction advances an ordinance governing scheduling, wage, or worker protections, your HR and finance teams receive an immediate alert mapped to the affected staff, enabling budget and policy decisions before the rule takes effect.</p>
  <h4>Enterprise Risk Assessment &amp; Quantitative Analytics</h4>
  <p>Multi-method organizational risk modeling that translates abstract HR metrics into tangible financial exposure, with three analytical workspaces (Overview, Analytics, and Quantitative).</p>
  <ul class="bullet">
    <li><strong>5-Dimension Live Risk Scoring:</strong> Continuous evaluation across compliance, incidents, ER cases, workforce, and legislative metrics, with 4-week trend lines and real-time delta tracking.</li>
    <li><strong>Cost of Risk Calculation:</strong> Translates risk scores into estimated dollar exposure (wage-and-hour back pay, meal/rest-break penalties, data-privacy fines, lapsed-credential penalties, ER litigation defense, OSHA penalties).</li>
    <li><strong>NAICS Dynamic Calibration:</strong> Cost estimates calibrated using your NAICS code against public federal enforcement data (DOL WHD, OSHA, EEOC).</li>
    <li><strong>Quantitative &amp; Tail Risk Analysis:</strong> Monte Carlo simulations across 10,000 iterations producing probability distributions of annual loss exposure, with Exceedance Curve and Loss Distribution modeling.</li>
    <li><strong>Peer &amp; Cohort Intelligence:</strong> NAICS-benchmarked peer comparisons and cohort heat maps across departments, sites, and tenure.</li>
    <li><strong>Separation &amp; Pre-Termination Risk:</strong> Every involuntary termination is scored and factored into your overall organizational exposure.</li>
    <li><strong>Executive Reporting &amp; Action Items:</strong> AI-generated narrative reports, prioritized recommendations, and an Action Items tracker.</li>
  </ul>
  <p>This provides a defensible, board-ready loss-probability range for EPLI renewal discussions and lets your finance team set litigation reserves based on rigorous statistical modeling rather than gut instinct.</p>
</div>

<div class="page">
  <h3>Investigations &amp; Risk</h3>
  <h4>Incident Reports</h4>
  <p>Intelligent safety and behavioral incident reporting. OSHA 300 and 300A log generation with CSV export. Anonymous reporting support. Covers safety events, field incidents, workplace injuries, and behavioral incidents, with trend analytics and pattern detection across sites. Each incident record automatically evaluates OSHA 300 recordability, and trend analytics surface whether incidents cluster around a specific site, shift, or program &mdash; enabling targeted safety-protocol improvements before an incident escalates to a workers&rsquo;-comp claim, an OSHA citation, or a funder report.</p>
  <h4>ER Copilot</h4>
  <p>Employment relations case management that acts as an active guide and a &ldquo;second set of eyes&rdquo; throughout complex investigations. Powered by AI-driven document analysis, it walks you through the case, constructing timelines and flagging discrepancies, and instantly identifies specific policy violations while surfacing relevant jurisdictional laws. When a case requires outside counsel or a litigation hold, secure encrypted PDF export delivers a complete, date-stamped record attorneys can immediately use, compressing weeks of document collection into hours.</p>
  <h4>ADA Accommodations</h4>
  <p>Interactive process workflow management with intelligent accommodation suggestions, undue hardship assessment, and job function analysis. The platform&rsquo;s job function analysis integrates the real physical and operational requirements of each role to identify feasible modifications &mdash; producing documentation that satisfies both EEOC and state-law standards simultaneously.</p>
  <h4>Pre-Termination Intelligence</h4>
  <p>9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before separation decisions, with an AI-generated narrative memo suitable for counsel review. The system flags when a proposed termination involves a staff member who recently raised a safety concern, filed a complaint, requested accommodation, or engaged in protected concerted activity &mdash; categories that trigger retaliation protection. This pre-decisional check is the highest-leverage risk control available.</p>
</div>

<div class="page">
  <h3>Workforce Management</h3>
  <h4>Employee Directory &amp; Bulk Import</h4>
  <p>Centralized employee records with CSV bulk upload, batch creation, and Google Workspace and Slack account provisioning for new hires.</p>
  <h4>Onboarding</h4>
  <p>Task-based onboarding templates organized by category, supporting role-specific workflows &mdash; including background-check verification, required training, and confidentiality acknowledgments. Progress analytics with funnel metrics, bottleneck identification, and completion tracking.</p>
  <h4>Compliance &amp; Operations Dashboard</h4>
  <p>A centralized, real-time view of your team&rsquo;s status. At a glance, monitor upcoming regulatory changes affecting your sites, track when an employee&rsquo;s leave of absence is ending, and review outstanding incident reports or ER Copilot action items. A dual-alert system pushes proactive notifications to your dashboard and straight to your email.</p>
  <h4>Automated License &amp; Training Tracking</h4>
  <p>A dedicated tracking engine for employee licenses, certifications, and mandatory compliance training. Matcha monitors every expiry date and acts as an early-warning system: as a credential approaches expiration, it emails the staff member and their manager with a secure upload link, sends automated follow-ups, and alerts compliance personnel if a credential lapses &mdash; keeping your programs staffed by properly credentialed, audit-ready people without manual oversight.</p>

  <h3>Agentic Document Workspace (Matcha Work)</h3>
  <p>A full AI-powered workspace for creating, researching, and collaborating on HR and compliance documents. Matcha Work goes beyond simple chat &mdash; an agentic system that browses the web, extracts structured data, queries your internal records, and produces publication-ready deliverables.</p>
  <h4>Document Generation</h4>
  <p>Create performance reviews, handbooks, onboarding plans, policies, offer letters, board presentations, and reporting narratives from conversational prompts. Iterative drafting with threading. Export to PDF, DOCX, or Markdown.</p>
  <h4>Chat with Your Data</h4>
  <p>Query your live employee records, incident logs, compliance requirements, ER cases, and policy documents directly. Ask questions like &ldquo;which staff have background checks or licenses expiring in the next 90 days?&rdquo; and get immediate, sourced answers.</p>
  <h4>Chain of Reasoning Compliance Querying</h4>
  <p>Multi-step compliance analysis that walks through regulatory logic step by step &mdash; citing sources, applying preemption rules, and surfacing gaps &mdash; before returning a final answer. <strong>Monthly usage credits included.</strong></p>
</div>

<div class="page fresh">
  <div class="page-header"><div class="logo">matcha</div><div class="section-label">Implementation &amp; Terms</div></div>
  <h2>Implementation Timeline</h2>
  <p>Total duration: 7&ndash;8 weeks. Your dedicated Customer Success Manager guides every phase.</p>
  <table>
    <thead><tr><th style="text-align:left">Phase</th><th style="text-align:left">Timeline</th><th style="text-align:left; padding-left:20px">Activities</th></tr></thead>
    <tbody>
      <tr><td style="text-align:left"><strong>Discovery &amp; Gap Analysis</strong></td><td style="text-align:left">Weeks 1&ndash;2</td><td style="text-align:left; padding-left:20px">Organizational mapping, HRIS audit, site inventory, regulatory gap analysis of wage and leave coverage, background-check programs, licensure tracking, and data-confidentiality practices</td></tr>
      <tr><td style="text-align:left"><strong>Configuration &amp; Templating</strong></td><td style="text-align:left">Weeks 3&ndash;4</td><td style="text-align:left; padding-left:20px">Jurisdiction setup, compliance baseline scan, role-specific onboarding templates, credential and license expiration workflows, handbook and policy document ingestion</td></tr>
      <tr><td style="text-align:left"><strong>Data Migration &amp; Manual Run</strong></td><td style="text-align:left">Weeks 5&ndash;6</td><td style="text-align:left; padding-left:20px">Employee data import, training-record migration, first onboarding cohort run manually to validate completeness</td></tr>
      <tr><td style="text-align:left"><strong>UAT &amp; Automation</strong></td><td style="text-align:left">Week 7</td><td style="text-align:left; padding-left:20px">Admin training, user acceptance testing, convert validated manual workflows to automated pipelines</td></tr>
      <tr><td style="text-align:left"><strong>Go-Live</strong></td><td style="text-align:left">Week 8</td><td style="text-align:left; padding-left:20px">Production cutover, CSM handoff, post-launch monitoring</td></tr>
    </tbody>
  </table>
  <p class="note">Implementation phases total {_m(q.implementation_your)} &mdash; the one-time Implementation &amp; Configuration fee shown in the Investment Summary.</p>

  <h3>Security &amp; Infrastructure</h3>
  <table class="terms-table"><tbody>
    <tr><td>SSO / SAML 2.0</td><td>Enterprise single sign-on via SAML 2.0. Compatible with Okta, Azure AD, OneLogin, and any SAML-compliant identity provider.</td></tr>
    <tr><td>Role-Based Access</td><td>Granular role-based access controls across admin, HR, supervisor, and employee roles. Department and site-scoped visibility for multi-site organizations.</td></tr>
    <tr><td>Uptime</td><td>99.5% target platform availability with automated health monitoring and incident alerting.</td></tr>
    <tr><td>Data Security</td><td>All data encrypted in transit (TLS 1.2+) and at rest (AES-256). Infrastructure hosted on AWS with US-based data residency.</td></tr>
    <tr><td>Data Retention</td><td>Full data export available at any time. Data deleted within 30 days of contract termination upon written request.</td></tr>
  </tbody></table>
</div>

<div class="page fresh">
  <div class="page-header"><div class="logo">matcha</div><div class="section-label">Implementation &amp; Terms</div></div>
  <h2>Contract Terms</h2>
  <table class="terms-table"><tbody>
    <tr><td>Initial Term</td><td>12 months from go-live date</td></tr>
    <tr><td>Price Lock</td><td>PEPM rate of {_p(q.your_pepm)} and Platform Fee of {_m(q.platform_fee_your)} (first jurisdiction included) locked for the initial 12-month term.</td></tr>
    <tr><td>Platform Fee</td><td>{_m(q.platform_fee_your)}/year includes the first jurisdiction with its local ordinances (standard: {_m(q.platform_fee_standard)})</td></tr>
    <tr><td>Volume Discount</td><td>10% PEPM discount applied automatically for 500+ employees</td></tr>
    <tr><td>Broker Pricing</td><td>10% discount applied when purchasing through an authorized Matcha broker partner</td></tr>
    <tr><td>Partner Program</td><td>Additional 5% discount (15% total with Broker) with quarterly business reviews, anonymized benchmarking, logo rights, public platform review within 90 days, and annual prepayment or 2-year term commitment</td></tr>
    <tr><td>Auto-Renewal</td><td>Automatic 12-month renewal periods</td></tr>
    <tr><td>Opt-Out Notice</td><td>60-day written notice required before any renewal period</td></tr>
    <tr><td>Employee True-Up</td><td>Quarterly adjustment based on active employee headcount</td></tr>
    <tr><td>Matcha Work Credits</td><td>Monthly credits included</td></tr>
    <tr><td>Dedicated CSM</td><td>Assigned at contract signing through go-live and beyond</td></tr>
    <tr><td>Value Validation</td><td>90-day post-go-live review to confirm platform adoption and ROI</td></tr>
  </tbody></table>
</div>

<div class="page fresh">
  <div class="page-header"><div class="logo">matcha</div><div class="section-label">ROI &amp; Support</div></div>
  <h2>Return on Investment</h2>
  {roi_intro}
  <table>
    <thead><tr><th style="text-align:left"></th><th>Year 1</th><th>Year 2</th><th>Year 3</th><th>3-Year Total</th></tr></thead>
    <tbody>
      <tr><td style="text-align:left">Annual recurring</td><td>{_m(q.annual_recurring_your)}</td><td>{_m(q.annual_recurring_your)}</td><td>{_m(q.annual_recurring_your)}</td><td>{_m(q.annual_recurring_your * 3)}</td></tr>
      <tr><td style="text-align:left">Implementation</td><td>{_m(q.implementation_your)}</td><td>&mdash;</td><td>&mdash;</td><td>{_m(q.implementation_your)}</td></tr>
      <tr class="row-bold"><td style="text-align:left">Total investment</td><td>{_m(q.year1_your)}</td><td>{_m(q.year2_your)}</td><td>{_m(q.year2_your)}</td><td>{_m(q.year1_your + q.year2_your * 2)}</td></tr>
      <tr><td style="text-align:left">Hard savings</td><td>{_m(q.roi_hard_savings)}</td><td>{_m(q.roi_hard_savings)}</td><td>{_m(q.roi_hard_savings)}</td><td>{_m(q.roi_hard_savings * 3)}</td></tr>
      <tr><td style="text-align:left">Risk reduction value</td><td>{_m(q.roi_risk_reduction)}</td><td>{_m(q.roi_risk_reduction)}</td><td>{_m(q.roi_risk_reduction)}</td><td>{_m(q.roi_risk_reduction * 3)}</td></tr>
      <tr class="row-bold"><td style="text-align:left">Total value delivered</td><td>{_m(q.roi_total_value)}</td><td>{_m(q.roi_total_value)}</td><td>{_m(q.roi_total_value)}</td><td>{_m(q.roi_total_value * 3)}</td></tr>
      <tr class="row-total"><td style="text-align:left">Net savings</td><td>{_m(q.roi_net_year1)}</td><td>{_m(q.roi_net_year2)}</td><td>{_m(q.roi_net_year2)}</td><td>{_m(q.roi_net_3yr)}</td></tr>
    </tbody>
  </table>
  <div class="highlight-box">Year 1 ROI: {q.roi_multiple}&times; &nbsp;&middot;&nbsp; Platform pays for itself by month {q.roi_payback_month} &nbsp;&middot;&nbsp; 3-year net savings: {_m(q.roi_net_3yr)}</div>

  <h2>Dedicated Support</h2>
  <ul class="bullet">
    <li><strong>Customer Success Manager</strong> assigned at contract signing through go-live and beyond</li>
    <li>Admin and manager training sessions included in implementation</li>
    <li>Ongoing CSM check-ins post go-live</li>
    <li>Platform support for configuration changes, new site rollouts, and feature adoption</li>
  </ul>

  <div class="signatures">
    <div class="sig-block"><h4>Matcha</h4><div class="sig-line"></div><div class="sig-label">Signature</div><div class="sig-line"></div><div class="sig-label">Name &amp; Title</div><div class="sig-line"></div><div class="sig-label">Date</div></div>
    <div class="sig-block"><h4>{company}</h4><div class="sig-line"></div><div class="sig-label">Signature</div><div class="sig-line"></div><div class="sig-label">Name &amp; Title</div><div class="sig-line"></div><div class="sig-label">Date</div></div>
  </div>

  <div class="disclaimer">
    <p>This proposal is valid for 30 days from {date_str}. Pricing is based on the employee count provided and subject to quarterly true-up.</p>
    <p>Matcha is a compliance research and workforce risk intelligence platform. It is not a substitute for legal counsel, and does not constitute legal advice or regulatory certification.</p>
  </div>
</div>

</body>
</html>"""
