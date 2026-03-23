#!/usr/bin/env python3
"""Generate a professional PDF deal proposal for Momentum Life Sciences."""

import os
from datetime import date
from weasyprint import HTML

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deals", "momentum")
VERSION = "v3"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, f"Matcha_Momentum_Proposal_{VERSION}.pdf")

# ── Config ──────────────────────────────────────────────────────────────────
CLIENT_NAME = "Momentum Life Sciences"
EMPLOYEE_COUNT = 200

# Pricing
LIST_PEPM = 15.00
PARTNER_DISCOUNT = 0.13  # 13% partner program discount
PARTNER_PEPM = LIST_PEPM * (1 - PARTNER_DISCOUNT)
PARTNER_MULT = 1 - PARTNER_DISCOUNT
VOLUME_DISCOUNT = 0.10  # 10% automatic for 500+ employees
PEPM = LIST_PEPM * (1 - VOLUME_DISCOUNT) if EMPLOYEE_COUNT >= 500 else LIST_PEPM
PLATFORM_FEE = 5_000  # annual, Growth tier (includes federal + 1 jurisdiction)
JURISDICTION_FEE = 4_000  # per additional jurisdiction/year, Growth tier
IMPL_FEE = 8_000

MONTHLY = PEPM * EMPLOYEE_COUNT
ANNUAL = MONTHLY * 12
ANNUAL_RECURRING = ANNUAL + PLATFORM_FEE  # before additional jurisdictions
YEAR1_TCV = ANNUAL_RECURRING + IMPL_FEE
TODAY = date.today().strftime("%B %d, %Y")

# ROI numbers
HARD_SAVINGS = 173_500
RISK_REDUCTION = 55_000
TOTAL_VALUE = HARD_SAVINGS + RISK_REDUCTION
NET_Y1 = TOTAL_VALUE - YEAR1_TCV
ROI_MULTIPLE = TOTAL_VALUE / YEAR1_TCV
YEAR2_NET = TOTAL_VALUE - ANNUAL_RECURRING
THREE_YEAR_INVEST = YEAR1_TCV + (ANNUAL_RECURRING * 2)
THREE_YEAR_VALUE = TOTAL_VALUE * 3
THREE_YEAR_NET = THREE_YEAR_VALUE - THREE_YEAR_INVEST

HTML_CONTENT = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: letter;
    margin: 0;
  }}

  * {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
  }}

  body {{
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #1a1a2e;
    font-size: 10.5pt;
    line-height: 1.55;
  }}

  /* ── Cover Page ─────────────────────────────────────────────── */
  .cover {{
    page-break-after: always;
    height: 100vh;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    background: linear-gradient(165deg, #1a1a2e 0%, #2d2d3f 40%, #3d3d52 100%);
    color: white;
    padding: 0;
    position: relative;
    overflow: hidden;
  }}

  .cover-accent {{
    position: absolute;
    top: -120px;
    right: -120px;
    width: 500px;
    height: 500px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.04);
  }}

  .cover-accent-2 {{
    position: absolute;
    bottom: -80px;
    left: -80px;
    width: 350px;
    height: 350px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.03);
  }}

  .cover-top {{
    padding: 60px 65px 0 65px;
    position: relative;
    z-index: 1;
  }}

  .logo-text {{
    font-size: 32pt;
    font-weight: 700;
    letter-spacing: -0.5px;
  }}

  .logo-sub {{
    font-size: 10pt;
    letter-spacing: 3px;
    text-transform: uppercase;
    opacity: 0.7;
    margin-top: 4px;
  }}

  .cover-middle {{
    padding: 0 65px;
    position: relative;
    z-index: 1;
  }}

  .cover-title {{
    font-size: 28pt;
    font-weight: 300;
    line-height: 1.2;
    margin-bottom: 16px;
    letter-spacing: -0.3px;
  }}

  .cover-title strong {{
    font-weight: 700;
  }}

  .cover-divider {{
    width: 60px;
    height: 3px;
    background: rgba(255, 255, 255, 0.5);
    margin: 24px 0;
  }}

  .cover-meta {{
    font-size: 11pt;
    opacity: 0.85;
    line-height: 1.8;
  }}

  .cover-bottom {{
    padding: 0 65px 50px 65px;
    position: relative;
    z-index: 1;
  }}

  .cover-footer {{
    font-size: 8.5pt;
    opacity: 0.5;
    border-top: 1px solid rgba(255, 255, 255, 0.15);
    padding-top: 16px;
  }}

  /* ── Content Pages ──────────────────────────────────────────── */
  .page {{
    page-break-after: always;
    padding: 55px 60px;
    position: relative;
  }}

  .page:last-child {{
    page-break-after: avoid;
  }}

  .page-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #1a1a2e;
    padding-bottom: 10px;
    margin-bottom: 32px;
  }}

  .page-header-logo {{
    font-size: 11pt;
    font-weight: 700;
    color: #1a1a2e;
    letter-spacing: -0.3px;
  }}

  .page-header-right {{
    font-size: 8pt;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 1.5px;
  }}

  h1 {{
    font-size: 20pt;
    font-weight: 700;
    color: #1a1a2e;
    margin-top: 8px;
    margin-bottom: 22px;
    letter-spacing: -0.3px;
  }}

  h2 {{
    font-size: 13pt;
    font-weight: 700;
    color: #1a1a2e;
    margin-top: 28px;
    margin-bottom: 14px;
    padding-bottom: 6px;
    border-bottom: 1px solid #d1d5db;
  }}

  h3 {{
    font-size: 11pt;
    font-weight: 700;
    color: #1a1a2e;
    margin-top: 16px;
    margin-bottom: 6px;
  }}

  p {{
    margin-bottom: 10px;
  }}

  .executive-summary {{
    background: #f5f5f7;
    border-left: 4px solid #1a1a2e;
    padding: 18px 22px;
    margin-bottom: 24px;
    font-size: 11pt;
    line-height: 1.65;
    color: #1a1a2e;
  }}

  /* ── Pricing Table ──────────────────────────────────────────── */
  .pricing-box {{
    border: 1px solid #d1d5db;
    border-radius: 6px;
    overflow: hidden;
    margin: 8px 0 20px 0;
  }}

  .pricing-box table {{
    width: 100%;
    border-collapse: collapse;
  }}

  .pricing-box th {{
    background: #1a1a2e;
    color: white;
    padding: 10px 18px;
    text-align: left;
    font-size: 9.5pt;
    text-transform: uppercase;
    letter-spacing: 1px;
  }}

  .pricing-box td {{
    padding: 11px 18px;
    border-bottom: 1px solid #e5e7eb;
    font-size: 10.5pt;
  }}

  .pricing-box tr:last-child td {{
    border-bottom: none;
  }}

  .pricing-box .total-row td {{
    background: #f5f5f7;
    font-weight: 700;
    font-size: 11.5pt;
    border-top: 2px solid #1a1a2e;
    padding: 13px 18px;
  }}

  .pricing-box .amount {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }}

  .pricing-note {{
    font-size: 9pt;
    color: #6b7280;
    margin-top: 12px;
    margin-bottom: 8px;
    font-style: italic;
  }}

  /* ── Feature Lists ──────────────────────────────────────────── */
  .feature-block {{
    margin-bottom: 16px;
  }}

  .feature-block p {{
    margin-bottom: 4px;
    padding-left: 2px;
  }}

  .feature-name {{
    font-weight: 700;
    color: #1a1a2e;
  }}

  ul {{
    padding-left: 20px;
    margin-bottom: 10px;
  }}

  li {{
    margin-bottom: 4px;
  }}

  /* ── Implementation Timeline ────────────────────────────────── */
  .timeline-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0 16px 0;
    font-size: 10pt;
  }}

  .timeline-table th {{
    background: #1a1a2e;
    color: white;
    padding: 9px 14px;
    text-align: left;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }}

  .timeline-table td {{
    padding: 10px 14px;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: top;
  }}

  .timeline-table tr:nth-child(even) td {{
    background: #f9fafb;
  }}

  .timeline-table .phase {{
    font-weight: 700;
    color: #1a1a2e;
    white-space: nowrap;
  }}

  .timeline-table .cost {{
    text-align: right;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }}

  /* ── Contract Terms ─────────────────────────────────────────── */
  .terms-list {{
    list-style: none;
    padding: 0;
  }}

  .terms-list li {{
    padding: 7px 0;
    border-bottom: 1px solid #f3f4f6;
    display: flex;
  }}

  .terms-list li:last-child {{
    border-bottom: none;
  }}

  .term-label {{
    font-weight: 700;
    color: #1a1a2e;
    min-width: 180px;
    flex-shrink: 0;
  }}

  /* ── ROI Table ──────────────────────────────────────────────── */
  .roi-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0 16px 0;
    font-size: 10pt;
  }}

  .roi-table th {{
    background: #1a1a2e;
    color: white;
    padding: 9px 14px;
    text-align: left;
    font-size: 9pt;
    text-transform: uppercase;
    letter-spacing: 0.8px;
  }}

  .roi-table td {{
    padding: 10px 14px;
    border-bottom: 1px solid #e5e7eb;
    vertical-align: top;
  }}

  .roi-table tr:nth-child(even) td {{
    background: #f9fafb;
  }}

  .roi-highlight {{
    background: #f5f5f7;
    border: 1px solid #1a1a2e;
    border-radius: 4px;
    padding: 14px 18px;
    margin-top: 12px;
    text-align: center;
    font-size: 12pt;
    font-weight: 700;
    color: #1a1a2e;
  }}

  /* ── Signature Block ────────────────────────────────────────── */
  .signature-section {{
    margin-top: 36px;
    display: flex;
    gap: 48px;
  }}

  .sig-block {{
    flex: 1;
  }}

  .sig-line {{
    border-bottom: 1px solid #1a1a2e;
    margin-bottom: 4px;
    height: 40px;
  }}

  .sig-label {{
    font-size: 9pt;
    color: #6b7280;
  }}

  .footer-note {{
    margin-top: 30px;
    padding-top: 16px;
    border-top: 1px solid #e5e7eb;
    font-size: 8.5pt;
    color: #9ca3af;
    text-align: center;
  }}
</style>
</head>
<body>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- COVER PAGE                                                            -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="cover">
  <div class="cover-accent"></div>
  <div class="cover-accent-2"></div>

  <div class="cover-top">
    <div class="logo-text">matcha</div>
    <div class="logo-sub">Risk, Compliance, Employee Relations Intelligence</div>
  </div>

  <div class="cover-middle">
    <div class="cover-title">
      Platform<br>
      <strong>Service Proposal</strong>
    </div>
    <div class="cover-divider"></div>
    <div style="font-size: 10pt; font-style: italic; opacity: 0.75; margin-bottom: 18px; letter-spacing: 0.2px;">&ldquo;Manage your risk or your risk will manage you.&rdquo;</div>
    <div class="cover-meta">
      Prepared for <strong>{CLIENT_NAME}</strong><br>
      {EMPLOYEE_COUNT} Employees &middot; Full Platform Access<br>
      {TODAY}
    </div>
  </div>

  <div class="cover-bottom">
    <div class="cover-footer">
      Confidential &mdash; This document contains proprietary pricing and is intended solely for the named recipient.<br>
      hey-matcha.com &middot; aaron@hey-matcha.com
    </div>
  </div>
</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- PAGE 2: EXECUTIVE SUMMARY + PRICING                                   -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Service Proposal &middot; {CLIENT_NAME}</div>
  </div>

  <h1>Executive Summary</h1>

  <div class="executive-summary">
    Matcha is an agentic workforce risk management platform built for life sciences organizations navigating complex, multi-layered regulatory environments. From FDA-regulated compliance monitoring and credentialing management to pre-termination risk scoring and employment relations investigations, Matcha consolidates fragmented HR operations into a single platform&mdash;reducing regulatory exposure, eliminating manual tracking, and delivering real-time risk visibility across every site and research facility. Every requirement is sourced from government databases and regulatory texts, with citation links and verification timestamps so your team can trust the data without independent research.
  </div>

  <h1>Investment Summary</h1>

  <div class="pricing-box">
    <table>
      <thead>
        <tr>
          <th>Line Item</th>
          <th style="text-align:right">Annual</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>PEPM Rate: ${PEPM:.2f} &times; {EMPLOYEE_COUNT} employees &times; 12 months</td>
          <td class="amount">${ANNUAL:,.2f}</td>
        </tr>
        <tr>
          <td>Platform Fee (includes federal compliance + 1 jurisdiction)</td>
          <td class="amount">${PLATFORM_FEE:,.2f}</td>
        </tr>
        <tr style="background:#f5f5f7;">
          <td><strong>Annual Recurring</strong></td>
          <td class="amount"><strong>${ANNUAL_RECURRING:,.2f}</strong></td>
        </tr>
        <tr>
          <td>Implementation &amp; Configuration (one-time, Year 1 only)</td>
          <td class="amount">${IMPL_FEE:,.2f}</td>
        </tr>
        <tr class="total-row">
          <td>Year 1 Total (before additional jurisdictions)</td>
          <td class="amount">${YEAR1_TCV:,.2f}</td>
        </tr>
        <tr class="total-row" style="border-top: 1px solid #d1d5db;">
          <td>Year 2+ Annual (recurring only)</td>
          <td class="amount">${ANNUAL_RECURRING:,.2f}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <p class="pricing-note" style="margin-top:6px; margin-bottom:0;">
    Implementation &amp; Configuration is a one-time fee. Subsequent years require only the annual recurring cost. Professional onboarding services for new locations, jurisdictions, or organizational changes are available on a fee-for-service basis&mdash;a schedule will be provided upon request.
  </p>

  <h2>Partner Program Pricing ({PARTNER_DISCOUNT:.0%} off)</h2>

  <div class="pricing-box">
    <table>
      <thead>
        <tr>
          <th></th>
          <th style="text-align:right">Standard</th>
          <th style="text-align:right">Partner</th>
          <th style="text-align:right">You Save</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>PEPM Rate</td>
          <td class="amount">${PEPM:.2f}</td>
          <td class="amount">${PEPM * PARTNER_MULT:.2f}</td>
          <td class="amount">${PEPM * PARTNER_DISCOUNT:.2f}/ee/mo</td>
        </tr>
        <tr>
          <td>Annual Employee Cost ({EMPLOYEE_COUNT} ee)</td>
          <td class="amount">${ANNUAL:,.0f}</td>
          <td class="amount">${ANNUAL * PARTNER_MULT:,.0f}</td>
          <td class="amount">${ANNUAL * PARTNER_DISCOUNT:,.0f}</td>
        </tr>
        <tr>
          <td>Platform Fee</td>
          <td class="amount">${PLATFORM_FEE:,.0f}</td>
          <td class="amount">${PLATFORM_FEE * PARTNER_MULT:,.0f}</td>
          <td class="amount">${PLATFORM_FEE * PARTNER_DISCOUNT:,.0f}</td>
        </tr>
        <tr>
          <td>Per Additional Jurisdiction</td>
          <td class="amount">${JURISDICTION_FEE:,.0f}</td>
          <td class="amount">${JURISDICTION_FEE * PARTNER_MULT:,.0f}</td>
          <td class="amount">${JURISDICTION_FEE * PARTNER_DISCOUNT:,.0f}</td>
        </tr>
        <tr style="background:#f5f5f7;">
          <td><strong>Annual Recurring</strong></td>
          <td class="amount"><strong>${ANNUAL_RECURRING:,.0f}</strong></td>
          <td class="amount"><strong>${ANNUAL_RECURRING * PARTNER_MULT:,.0f}</strong></td>
          <td class="amount"><strong>${ANNUAL_RECURRING * PARTNER_DISCOUNT:,.0f}</strong></td>
        </tr>
        <tr>
          <td>Implementation &amp; Configuration</td>
          <td class="amount">${IMPL_FEE:,.0f}</td>
          <td class="amount">${IMPL_FEE * PARTNER_MULT:,.0f}</td>
          <td class="amount">${IMPL_FEE * PARTNER_DISCOUNT:,.0f}</td>
        </tr>
        <tr class="total-row">
          <td>Year 1 Total</td>
          <td class="amount">${YEAR1_TCV:,.0f}</td>
          <td class="amount">${YEAR1_TCV * PARTNER_MULT:,.0f}</td>
          <td class="amount"><strong>${YEAR1_TCV * PARTNER_DISCOUNT:,.0f}</strong></td>
        </tr>
        <tr class="total-row" style="border-top: 1px solid #d1d5db;">
          <td>Year 2+ Annual</td>
          <td class="amount">${ANNUAL_RECURRING:,.0f}</td>
          <td class="amount">${ANNUAL_RECURRING * PARTNER_MULT:,.0f}</td>
          <td class="amount"><strong>${ANNUAL_RECURRING * PARTNER_DISCOUNT:,.0f}</strong></td>
        </tr>
      </tbody>
    </table>
  </div>

  <p class="pricing-note" style="margin-top:8px;">
    Partner Program requires: quarterly video insight sessions, anonymized case study participation, anonymized data sharing for industry benchmarking, logo rights for Matcha marketing materials, one public platform review (G2 or similar) within 90 days of go-live, and annual prepayment or 2-year term commitment.
  </p>

  <h2>Jurisdiction Fee Schedule</h2>

  <div class="pricing-box">
    <table>
      <thead>
        <tr>
          <th>Client Tier</th>
          <th>Headcount</th>
          <th style="text-align:right">Per Additional Jurisdiction / Year</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><strong>Growth</strong></td>
          <td>1&ndash;249</td>
          <td class="amount">$4,000</td>
        </tr>
        <tr>
          <td>Business</td>
          <td>250&ndash;999</td>
          <td class="amount">$7,500</td>
        </tr>
        <tr>
          <td>Enterprise</td>
          <td>1,000+</td>
          <td class="amount">$10,000</td>
        </tr>
      </tbody>
    </table>
  </div>

  <p class="pricing-note">
    First jurisdiction included in Platform Fee. Federal compliance (OSHA, FLSA, FMLA, ADA, EEOC) included at no additional charge. A Jurisdiction is any U.S. state, city, county, or municipality in which Client has employees and which imposes distinct compliance obligations. Industry-specific regulatory bodies (e.g., state medical boards, DEA registration sites) requiring distinct compliance configuration are each treated as an additional Jurisdiction and scoped during implementation.<br><br>
    <strong>Partner Program (${PARTNER_PEPM:.2f} PEPM)</strong> &mdash; {PARTNER_DISCOUNT:.0%} discount available for organizations that commit to: quarterly video insight sessions, anonymized case study participation, anonymized data sharing for industry benchmarking, logo rights for Matcha marketing materials, one public platform review (G2 or similar) within 90 days of go-live, and annual prepayment or 2-year term commitment.<br>
    <strong>Volume Discount</strong> &mdash; 10% PEPM discount applied automatically for organizations with 500 or more employees.<br>
    Price locked for the 12-month initial term. Employee count subject to quarterly true-up.
  </p>

</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- PAGE 3: PLATFORM CAPABILITIES                                         -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Platform Capabilities</div>
  </div>

  <h1>Platform Capabilities</h1>

  <h2>Compliance &amp; Legal</h2>

  <div class="feature-block">
    <p><span class="feature-name">Compliance Engine</span> &mdash; Agentic jurisdiction research across federal, state, and local levels. Multi-location and multi-site support with preemption rule analysis. Tiered data approach: structured requirements, curated repository, and agentic research for emerging regulations including FDA workforce mandates, state biotech licensing, and export control updates. For a life sciences company operating across research, clinical, and commercial functions, this means continuous monitoring of FDA GxP workforce training requirements, state occupational health and safety standards for laboratory environments, and applicable ITAR/EAR workforce compliance obligations — in a single dashboard rather than siloed across safety, legal, and HR teams. When the FDA updates its guidance on GCP training requirements for clinical research staff or a state modifies biosafety cabinet certification intervals, the engine surfaces the change mapped to the affected team before the next regulatory inspection or sponsor audit.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Policies &amp; Handbooks</span> &mdash; AI-powered policy documents tailored to specific jurisdictions and research environments. Electronic signature collection with audit trails. Auto-research fills jurisdiction-specific topics during handbook creation. In a life sciences environment, this includes GCP/GLP training acknowledgment policies, lab safety protocols, conflict of interest and IP assignment policies, and applicable export control awareness policies — all generated from the jurisdiction and industry profile rather than drafted from scratch by legal. When a new state laboratory location comes online or the FDA updates its clinical investigator guidance, the handbook auto-updates the affected sections and triggers bulk re-acknowledgment for impacted employees, keeping the training record current without a manual policy revision cycle.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Legislative Tracker</span> &mdash; Intelligent monitoring of regulatory changes across jurisdictions with pattern detection for coordinated legislative activity. Covers FDA guidance updates, state biotech regulations, and employment law changes. For Momentum Life Sciences, this means automatic alerts when the FDA publishes new draft guidance on clinical investigator qualification standards or when a state enacts changes to its bioresearch facility permitting requirements — changes that directly affect workforce training obligations and cannot be caught by monitoring a single federal register feed. Pattern detection also flags when multiple states simultaneously advance legislation on trade secret protections, non-compete enforceability, or laboratory worker safety standards, giving HR and legal teams coordinated visibility rather than discovering the laws state by state after they pass.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Risk Assessment</span> &mdash; Multi-method organizational risk modeling: 5-dimension live risk scoring (compliance, incidents, ER cases, workforce, legislative), Monte Carlo simulation across 10,000 iterations to produce probability distributions of annual loss exposure, statistical anomaly detection using rolling mean and standard deviation on time-series metrics, and NAICS-benchmarked peer comparison sourced from BLS, OSHA, EEOC, and QCEW. Executive-ready reports with cohort heat maps across departments, locations, and tenure. For a 200-person life sciences company where a single EEOC charge or FDA Form 483 workforce-related observation can affect investor confidence and IND/NDA timelines, the board-ready risk report translates operational HR data into the language that audit committees and Series B/C investors expect to see in a risk register. Monte Carlo outputs provide a defensible loss-probability range for employment practices liability insurance renewal discussions and allow the CFO to set litigation reserves based on statistical modeling rather than gut instinct.</p>
  </div>

  <h2>Investigations &amp; Risk</h2>

  <div class="feature-block">
    <p><span class="feature-name">Incident Reports</span> &mdash; Intelligent safety and behavioral incident reporting. OSHA 300 and 300A log generation with CSV export. Anonymous reporting support. Covers biosafety incidents, lab accidents, chemical exposure events, and behavioral incidents. Trend analytics and pattern detection across sites. In a life sciences setting, the system tracks BSL-2/BSL-3 exposure events, chemical spills, needlestick and sharps injuries, and near-miss events in a single incident record that automatically evaluates OSHA 300 recordability — eliminating the risk of a recordkeeping citation when OSHA conducts a programmed laboratory inspection. Trend analytics can surface whether chemical exposure incidents cluster around a specific reagent, protocol, or shift, enabling targeted engineering control or SOP improvements before an incident escalates to a workers' comp claim or OSHA complaint.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ER Copilot</span> &mdash; Employment relations case management that acts as an active guide and a &ldquo;second set of eyes&rdquo; throughout complex investigations. Powered by AI-driven document analysis, it walks you through the case, automatically constructing timelines and flagging discrepancies. It eliminates manual cross-referencing by instantly identifying specific policy violations&mdash;no more digging through the employee handbook; the system finds it for you, while simultaneously surfacing any relevant jurisdictional laws.</p>
    <p>In a research-intensive company where IP ownership and confidentiality are core employment terms, ER Copilot centralizes the case record for disputes involving alleged IP misappropriation, competitive activity, or research misconduct&mdash;matters where the documentary timeline is as important to the outcome as the underlying facts. When a case requires outside employment counsel or litigation hold coordination, secure, encrypted PDF export links deliver a complete, date-stamped record in a form attorneys can immediately use, compressing weeks of document collection into hours.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ADA Accommodations</span> &mdash; Interactive process workflow management with intelligent accommodation suggestions, undue hardship assessment, and job function analysis. In a life sciences environment, accommodation requests often involve laboratory workers seeking modifications to chemical exposure tasks or physical safety requirements — situations where the essential functions analysis must be grounded in the specific biosafety and regulatory context of the role, not a generic job description. The platform's job function analysis integrates the specific physical and environmental requirements of laboratory positions, including biosafety level constraints and personal protective equipment mandates, to identify feasible modifications that do not create a direct threat — producing documentation that satisfies both EEOC and OSHA standards simultaneously.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Pre-Termination Intelligence</span> &mdash; 9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before separation decisions. AI-generated narrative memo suitable for counsel review. For a life sciences company, the system flags when a proposed termination involves an employee who recently raised a research integrity concern, filed an OSHA laboratory safety complaint, or requested accommodation — categories that trigger retaliation protection under OSHA Section 11(c), FDA whistleblower regulations, and applicable state statutes. At a company where a single high-profile retaliation claim could affect investor sentiment, regulatory relationships, or IND credibility, this pre-decisional check is the highest-leverage risk control available.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Separation Agreements</span> &mdash; OWBPA-compliant agreement generation with proper consideration periods (21/45 day) and revocation window tracking. Group layoff disclosure support. In a life sciences company, separation agreements routinely include IP assignment confirmations and non-solicitation provisions — documents that are frequently assembled manually from multiple templates under time pressure when a departure is unexpected. The platform generates a complete, jurisdiction-compliant separation package from a single workflow, with the OWBPA disclosures, consideration period tracking, and revocation window built in so nothing is inadvertently omitted.</p>
  </div>

  <h2>Workforce Management</h2>

  <div class="feature-block">
    <p><span class="feature-name">Employee Directory &amp; Bulk Import</span> &mdash; Centralized employee records with CSV bulk upload, batch creation, Google Workspace and Slack account provisioning for new hires.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Onboarding</span> &mdash; Task-based onboarding templates organized by category. Supports role-specific workflows for research scientists, lab technicians, clinical staff, and QA. Progress analytics with funnel metrics, bottleneck identification, and completion tracking.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Compliance &amp; Operations Dashboard</span> &mdash; In a fast-paced biotech environment, missing a regulatory shift or a scheduling detail isn&rsquo;t just an administrative error&mdash;it&rsquo;s a compliance risk that can disrupt critical research. The dashboard acts as your operational command center, giving you a centralized, real-time view of your team&rsquo;s status. At a glance, you can monitor upcoming regulatory changes, track exactly when an employee&rsquo;s leave of absence (LOA) is coming to an end, and review outstanding incident reports or ER Copilot action items. To ensure nothing slips through the cracks, the system features a dual-alert system, pushing proactive notifications directly to your dashboard and sending them straight to your email.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Automated License &amp; Training Tracking</span> &mdash; Managing the specialized credentials required for clinical and laboratory work shouldn&rsquo;t rely on manual spreadsheets. As your comprehensive HR platform, Matcha features a dedicated tracking engine for all employee licenses, certifications, and mandatory compliance training. Matcha automatically monitors every expiry date and acts as an intelligent early warning system. When a credential is approaching its expiration, the platform automatically emails both the employee and their manager with a reminder. This alert includes a secure, direct link for the employee to easily upload their renewed document straight into the platform. As the deadline gets closer, it sends automated follow-ups to ensure action is being taken. If a credential actually expires, Matcha immediately alerts the designated compliance personnel, ensuring your research teams remain fully certified, safe, and audit-ready without the manual oversight.</p>
  </div>

  <h2>Agentic Document Workspace (Matcha Work)</h2>

  <div class="feature-block">
    <p>Chat-driven document creation with threading, iterative drafts, and internal data search mode for cross-referencing organizational information. Supports performance reviews, workbooks, onboarding plans, presentations, handbooks, and policies.</p>
    <p><span class="feature-name">Chat with Your Data</span> &mdash; Query your employee records, incident logs, compliance requirements, and ER cases directly. Surface patterns and pull ad-hoc reports without exporting to spreadsheets.</p>
    <p><span class="feature-name">Chain of Reasoning Compliance Querying</span> &mdash; Multi-step compliance analysis that walks through regulatory logic step by step&mdash;citing sources, applying preemption rules, and surfacing gaps&mdash;before returning a final answer. <strong>Monthly usage credits included.</strong></p>
  </div>

</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- PAGE 4: IMPLEMENTATION + TERMS                                        -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Implementation &amp; Terms</div>
  </div>

  <h1>Implementation Timeline</h1>
  <p>Total duration: 7&ndash;8 weeks. Your dedicated Customer Success Manager guides every phase.</p>

  <table class="timeline-table">
    <thead>
      <tr>
        <th>Phase</th>
        <th>Timeline</th>
        <th style="text-align:right">Investment</th>
        <th>Activities</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td class="phase">Discovery &amp; Gap Analysis</td>
        <td>Weeks 1&ndash;2</td>
        <td class="cost">$5,000</td>
        <td>Organizational mapping, HRIS audit, site inventory, regulatory gap analysis &mdash; audit FDA compliance programs (GCP/GLP/GMP), IRB protocols and training records, DEA registrations, biosafety committee requirements, export control classifications (ITAR/EAR), state biotech licensing</td>
      </tr>
      <tr>
        <td class="phase">Configuration &amp; Templating</td>
        <td>Weeks 3&ndash;4</td>
        <td class="cost">$4,500</td>
        <td>Location/jurisdiction setup, compliance baseline scan, build role-specific onboarding templates (research scientist, lab tech, clinical staff, QA/regulatory affairs), credential and certification expiration workflows, FDA training record workflows, handbook and policy document ingestion</td>
      </tr>
      <tr>
        <td class="phase">Data Migration &amp; Manual Run</td>
        <td>Weeks 5&ndash;6</td>
        <td class="cost">$3,000</td>
        <td>Employee data import, training record migration, run first onboarding cohort manually using templates to validate completeness and regulatory alignment</td>
      </tr>
      <tr>
        <td class="phase">UAT &amp; Automation</td>
        <td>Week 7</td>
        <td class="cost">$1,500</td>
        <td>Admin training, user acceptance testing, convert validated manual workflows to automated ingestion pipelines</td>
      </tr>
      <tr>
        <td class="phase">Go-Live</td>
        <td>Week 8</td>
        <td class="cost">$1,000</td>
        <td>Production cutover, CSM handoff, post-launch monitoring</td>
      </tr>
    </tbody>
  </table>

  <h2>Security &amp; Infrastructure</h2>

  <ul class="terms-list">
    <li><span class="term-label">SSO / SAML 2.0</span> Enterprise single sign-on via SAML 2.0. Compatible with Okta, Azure AD, OneLogin, and any SAML-compliant identity provider. Per-company configuration with auto-provisioning.</li>
    <li><span class="term-label">Role-Based Access</span> Granular role-based access controls across admin, HR, supervisor, and employee roles. Department and location-scoped visibility for multi-site organizations.</li>
    <li><span class="term-label">Uptime</span> 99.5% target platform availability with automated health monitoring and incident alerting.</li>
    <li><span class="term-label">Data Security</span> All data encrypted in transit (TLS 1.2+) and at rest (AES-256). Infrastructure hosted on AWS with US-based data residency.</li>

    <li><span class="term-label">Data Retention</span> Full data export available at any time. Data deleted within 30 days of contract termination upon written request.</li>
  </ul>

  <h1>Contract Terms</h1>

  <ul class="terms-list">
    <li><span class="term-label">Initial Term</span> 12 months from go-live date</li>
    <li><span class="term-label">Price Lock</span> PEPM rate of ${PEPM:.2f}, Platform Fee of ${PLATFORM_FEE:,.2f}, and Jurisdiction Fee of ${JURISDICTION_FEE:,.2f} locked for the initial 12-month term</li>
    <li><span class="term-label">Platform Fee</span> ${PLATFORM_FEE:,.2f}/year includes federal compliance monitoring and one jurisdiction</li>
    <li><span class="term-label">Jurisdiction Fees</span> ${JURISDICTION_FEE:,.2f} per additional jurisdiction per year, scoped during implementation</li>
    <li><span class="term-label">Partner Program</span> {PARTNER_DISCOUNT:.0%} discount (${PARTNER_PEPM:.2f} PEPM) with quarterly video insights, anonymized case study &amp; data sharing, logo rights, public review within 90 days, and annual prepayment or 2-year term</li>
    <li><span class="term-label">Volume Discount</span> 10% PEPM discount applied automatically for 500+ employees</li>
    <li><span class="term-label">Auto-Renewal</span> Automatic 12-month renewal periods</li>
    <li><span class="term-label">Opt-Out Notice</span> 60-day written notice required before any renewal period</li>
    <li><span class="term-label">Employee True-Up</span> Quarterly adjustment based on active employee headcount</li>
    <li><span class="term-label">Matcha Work Credits</span> Monthly credits included</li>
    <li><span class="term-label">Dedicated CSM</span> Assigned at contract signing through go-live and beyond</li>
    <li><span class="term-label">Value Validation</span> 90-day post-go-live review to confirm platform adoption and ROI</li>
    <li><span class="term-label">Renewal Pricing</span> May adjust with 60-day written notice prior to renewal</li>
  </ul>

</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- PAGE 5: ROI + SIGNATURES                                              -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">ROI &amp; Support</div>
  </div>

  <h1>Return on Investment</h1>

  <p style="margin-bottom: 14px;">Life sciences employers carry a disproportionately high compliance burden relative to their headcount. FDA-regulated workforce requirements, multi-state licensure, IRB training mandates, and DEA registrations intersect with standard employment law&mdash;creating a compliance surface that scales with regulatory complexity, not just headcount. EEOC charges in research and development have increased as the sector has expanded, and the DOL has prioritized wage and hour enforcement in biotech and pharma as shift work and contractor classifications have come under scrutiny.</p>

  <table class="roi-table">
    <thead>
      <tr>
        <th>What You Spend Today</th>
        <th style="text-align:right">Current Cost</th>
        <th style="text-align:right">You Save</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Outside employment counsel</td>
        <td style="text-align:right">$65,000/yr</td>
        <td style="text-align:right"><strong>$42,000</strong></td>
      </tr>
      <tr>
        <td>ER cases sent to outside counsel (2/yr)</td>
        <td style="text-align:right">$36,000/yr</td>
        <td style="text-align:right"><strong>$26,000</strong></td>
      </tr>
      <tr>
        <td>HR staff time on compliance tasks</td>
        <td style="text-align:right">$120,000/yr</td>
        <td style="text-align:right"><strong>$66,000</strong></td>
      </tr>
      <tr>
        <td>Handbook &amp; policy legal review</td>
        <td style="text-align:right">$12,000/yr</td>
        <td style="text-align:right"><strong>$10,500</strong></td>
      </tr>
      <tr>
        <td>OSHA &amp; biosafety incident admin</td>
        <td style="text-align:right">$18,000/yr</td>
        <td style="text-align:right"><strong>$14,000</strong></td>
      </tr>
      <tr>
        <td>Compliance training &amp; certification tracking</td>
        <td style="text-align:right">$20,000/yr</td>
        <td style="text-align:right"><strong>$15,000</strong></td>
      </tr>
      <tr style="background:#f5f5f7;">
        <td><strong>Annual hard savings</strong></td>
        <td></td>
        <td style="text-align:right"><strong>${HARD_SAVINGS:,.0f}</strong></td>
      </tr>
    </tbody>
  </table>

  <p style="font-size:9pt; color:#6b7280; margin-top:8px;">Savings driven by ER Copilot handling investigations internally, the Compliance Engine automating FDA and jurisdiction monitoring, and Pre-Termination Intelligence reducing matters requiring attorney involvement. HR compliance staff time savings reflect automation of GxP training tracking, credential expiration workflows, and multi-jurisdiction regulatory monitoring.</p>

  <table class="roi-table" style="margin-top: 20px;">
    <thead>
      <tr>
        <th></th>
        <th style="text-align:right">Year 1</th>
        <th style="text-align:right">Year 2</th>
        <th style="text-align:right">Year 3</th>
        <th style="text-align:right">3-Year Total</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Annual recurring (PEPM + platform fee)</td>
        <td style="text-align:right">${ANNUAL_RECURRING:,.0f}</td>
        <td style="text-align:right">${ANNUAL_RECURRING:,.0f}</td>
        <td style="text-align:right">${ANNUAL_RECURRING:,.0f}</td>
        <td style="text-align:right">${ANNUAL_RECURRING*3:,.0f}</td>
      </tr>
      <tr>
        <td>Implementation</td>
        <td style="text-align:right">${IMPL_FEE:,.0f}</td>
        <td style="text-align:right">&mdash;</td>
        <td style="text-align:right">&mdash;</td>
        <td style="text-align:right">${IMPL_FEE:,.0f}</td>
      </tr>
      <tr>
        <td><strong>Total investment</strong></td>
        <td style="text-align:right"><strong>${YEAR1_TCV:,.0f}</strong></td>
        <td style="text-align:right"><strong>${ANNUAL_RECURRING:,.0f}</strong></td>
        <td style="text-align:right"><strong>${ANNUAL_RECURRING:,.0f}</strong></td>
        <td style="text-align:right"><strong>${THREE_YEAR_INVEST:,.0f}</strong></td>
      </tr>
      <tr>
        <td>Hard savings</td>
        <td style="text-align:right">${HARD_SAVINGS:,.0f}</td>
        <td style="text-align:right">${HARD_SAVINGS:,.0f}</td>
        <td style="text-align:right">${HARD_SAVINGS:,.0f}</td>
        <td style="text-align:right">${HARD_SAVINGS*3:,.0f}</td>
      </tr>
      <tr>
        <td>Risk reduction value</td>
        <td style="text-align:right">${RISK_REDUCTION:,.0f}</td>
        <td style="text-align:right">${RISK_REDUCTION:,.0f}</td>
        <td style="text-align:right">${RISK_REDUCTION:,.0f}</td>
        <td style="text-align:right">${RISK_REDUCTION*3:,.0f}</td>
      </tr>
      <tr style="background:#f5f5f7;">
        <td><strong>Total value delivered</strong></td>
        <td style="text-align:right"><strong>${TOTAL_VALUE:,.0f}</strong></td>
        <td style="text-align:right"><strong>${TOTAL_VALUE:,.0f}</strong></td>
        <td style="text-align:right"><strong>${TOTAL_VALUE:,.0f}</strong></td>
        <td style="text-align:right"><strong>${THREE_YEAR_VALUE:,.0f}</strong></td>
      </tr>
      <tr style="background:#f5f5f7;">
        <td><strong>Net savings</strong></td>
        <td style="text-align:right"><strong>${NET_Y1:,.0f}</strong></td>
        <td style="text-align:right"><strong>${YEAR2_NET:,.0f}</strong></td>
        <td style="text-align:right"><strong>${YEAR2_NET:,.0f}</strong></td>
        <td style="text-align:right"><strong>${THREE_YEAR_NET:,.0f}</strong></td>
      </tr>
    </tbody>
  </table>

  <div class="roi-highlight">
    Year 1 ROI: {ROI_MULTIPLE:.1f}&times; &middot; Platform pays for itself by month 3 &middot; 3-year net savings: ${THREE_YEAR_NET:,.0f}
  </div>

  <h1 style="margin-top: 32px;">Dedicated Support</h1>

  <ul>
    <li><strong>Customer Success Manager</strong> assigned at contract signing through go-live and beyond</li>
    <li>Admin and manager training sessions included in implementation</li>
    <li>Ongoing CSM check-ins post go-live</li>
    <li>Platform support for configuration changes, new site rollouts, and feature adoption</li>
  </ul>

  <div class="signature-section">
    <div class="sig-block">
      <p style="font-weight: 700; margin-bottom: 24px;">Matcha</p>
      <div class="sig-line"></div>
      <p class="sig-label">Signature</p>
      <div style="height: 12px;"></div>
      <div class="sig-line"></div>
      <p class="sig-label">Name &amp; Title</p>
      <div style="height: 12px;"></div>
      <div class="sig-line"></div>
      <p class="sig-label">Date</p>
    </div>
    <div class="sig-block">
      <p style="font-weight: 700; margin-bottom: 24px;">{CLIENT_NAME}</p>
      <div class="sig-line"></div>
      <p class="sig-label">Signature</p>
      <div style="height: 12px;"></div>
      <div class="sig-line"></div>
      <p class="sig-label">Name &amp; Title</p>
      <div style="height: 12px;"></div>
      <div class="sig-line"></div>
      <p class="sig-label">Date</p>
    </div>
  </div>

  <div class="footer-note">
    This proposal is valid for 30 days from {TODAY}. Pricing is based on the employee count provided and subject to quarterly true-up.<br><br>
    <em>Matcha is a compliance research and workforce risk intelligence platform. It is not a substitute for legal counsel, and does not constitute legal advice, medical guidance, or regulatory certification. All compliance data is sourced from public regulatory databases and provided for informational purposes.</em>
  </div>

</div>

</body>
</html>
"""


def main():
    print(f"Generating proposal PDF...")
    html = HTML(string=HTML_CONTENT)
    html.write_pdf(OUTPUT_PATH)
    print(f"Done: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
