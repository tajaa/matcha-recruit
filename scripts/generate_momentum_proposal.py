#!/usr/bin/env python3
"""Generate a professional PDF deal proposal for Momentum Life Sciences."""

import os
from datetime import date
from weasyprint import HTML

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deals", "momentum")
VERSION = "v5"
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
IMPL_FEE = 10_000

MONTHLY = PEPM * EMPLOYEE_COUNT
ANNUAL = MONTHLY * 12
ANNUAL_RECURRING = ANNUAL + PLATFORM_FEE  # before additional jurisdictions
YEAR1_TCV = ANNUAL_RECURRING + IMPL_FEE
TODAY = "March 20, 2026"

# Jurisdiction estimate (midpoint of 4-8 range for ROI calculations)
EST_JURISDICTIONS = 6
EST_JURISDICTION_COST = EST_JURISDICTIONS * JURISDICTION_FEE
ANNUAL_RECURRING_EST = ANNUAL_RECURRING + EST_JURISDICTION_COST
YEAR1_TCV_EST = ANNUAL_RECURRING_EST + IMPL_FEE

# ROI numbers (using estimated jurisdiction midpoint)
HARD_SAVINGS = 224_000
RISK_REDUCTION = 75_000
TOTAL_VALUE = HARD_SAVINGS + RISK_REDUCTION
NET_Y1 = TOTAL_VALUE - YEAR1_TCV_EST
ROI_MULTIPLE = TOTAL_VALUE / YEAR1_TCV_EST
YEAR2_NET = TOTAL_VALUE - ANNUAL_RECURRING_EST
THREE_YEAR_INVEST = YEAR1_TCV_EST + (ANNUAL_RECURRING_EST * 2)
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
    Matcha replaces manual compliance tracking, fragmented ER case management, spreadsheet-based credential monitoring, and reactive risk management with a single agentic platform. For Momentum Life Sciences, that means U.S. federal and state jurisdiction-level compliance monitoring, multi-state licensure and Scope of Practice tracking, HIPAA and patient privacy compliance, employment law across every operating state, and employment relations case management. For teams with international operations or sponsor relationships, Matcha extends the same coverage to applicable international regulatory frameworks. During implementation, Matcha builds a custom compliance and HR management system tailored to your organization &mdash; your jurisdictions, your roles, your workflows. After go-live, this system is handed off to your admin team as a fully operational CMS that you own and run independently. From compliance tracking and sponsor audit readiness to ER investigations, pre-termination risk scoring, and intelligent policy documents, Matcha consolidates fragmented HR operations into a single platform &mdash; reducing regulatory exposure, eliminating manual tracking, and giving your HR team real-time visibility across every clinical engagement site and field operations team. Every requirement is sourced from government databases and regulatory texts, with citation links and verification timestamps so your team can trust the data without independent research.
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
        <tr>
          <td>Estimated additional jurisdictions (4&ndash;8 jurisdictions &times; ${JURISDICTION_FEE:,.0f})</td>
          <td class="amount">${JURISDICTION_FEE*4:,.0f}&ndash;${JURISDICTION_FEE*8:,.0f}</td>
        </tr>
        <tr style="background:#f5f5f7;">
          <td><strong>Annual Recurring</strong></td>
          <td class="amount"><strong>${ANNUAL_RECURRING + JURISDICTION_FEE*4:,.0f}&ndash;${ANNUAL_RECURRING + JURISDICTION_FEE*8:,.0f}</strong></td>
        </tr>
        <tr>
          <td>Implementation &amp; Configuration (one-time, Year 1 only)</td>
          <td class="amount">${IMPL_FEE:,.2f}</td>
        </tr>
        <tr class="total-row">
          <td>Year 1 Total</td>
          <td class="amount">${YEAR1_TCV + JURISDICTION_FEE*4:,.0f}&ndash;${YEAR1_TCV + JURISDICTION_FEE*8:,.0f}</td>
        </tr>
        <tr class="total-row" style="border-top: 1px solid #d1d5db;">
          <td>Year 2+ Annual (recurring only)</td>
          <td class="amount">${ANNUAL_RECURRING + JURISDICTION_FEE*4:,.0f}&ndash;${ANNUAL_RECURRING + JURISDICTION_FEE*8:,.0f}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <p class="pricing-note" style="margin-top:6px; margin-bottom:0;">
    Implementation &amp; Configuration is a one-time fee. Subsequent years require only the annual recurring cost. Exact jurisdiction count determined during Discovery &amp; Gap Analysis (Weeks 1&ndash;2). Federal compliance is included at no additional charge. Professional onboarding services for new locations, jurisdictions, or organizational changes are available on a fee-for-service basis&mdash;a schedule will be provided upon request.
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
        <tr>
          <td>Estimated additional jurisdictions (4&ndash;8 jurisdictions)</td>
          <td class="amount">${JURISDICTION_FEE*4:,.0f}&ndash;${JURISDICTION_FEE*8:,.0f}</td>
          <td class="amount">${JURISDICTION_FEE*4 * PARTNER_MULT:,.0f}&ndash;${JURISDICTION_FEE*8 * PARTNER_MULT:,.0f}</td>
          <td class="amount">${JURISDICTION_FEE*4 * PARTNER_DISCOUNT:,.0f}&ndash;${JURISDICTION_FEE*8 * PARTNER_DISCOUNT:,.0f}</td>
        </tr>
        <tr style="background:#f5f5f7;">
          <td><strong>Annual Recurring</strong></td>
          <td class="amount"><strong>${ANNUAL_RECURRING + JURISDICTION_FEE*4:,.0f}&ndash;${ANNUAL_RECURRING + JURISDICTION_FEE*8:,.0f}</strong></td>
          <td class="amount"><strong>${(ANNUAL_RECURRING + JURISDICTION_FEE*4) * PARTNER_MULT:,.0f}&ndash;${(ANNUAL_RECURRING + JURISDICTION_FEE*8) * PARTNER_MULT:,.0f}</strong></td>
          <td class="amount"><strong>${(ANNUAL_RECURRING + JURISDICTION_FEE*4) * PARTNER_DISCOUNT:,.0f}&ndash;${(ANNUAL_RECURRING + JURISDICTION_FEE*8) * PARTNER_DISCOUNT:,.0f}</strong></td>
        </tr>
        <tr>
          <td>Implementation &amp; Configuration</td>
          <td class="amount">${IMPL_FEE:,.0f}</td>
          <td class="amount">${IMPL_FEE * PARTNER_MULT:,.0f}</td>
          <td class="amount">${IMPL_FEE * PARTNER_DISCOUNT:,.0f}</td>
        </tr>
        <tr class="total-row">
          <td>Year 1 Total</td>
          <td class="amount">${YEAR1_TCV + JURISDICTION_FEE*4:,.0f}&ndash;${YEAR1_TCV + JURISDICTION_FEE*8:,.0f}</td>
          <td class="amount">${(YEAR1_TCV + JURISDICTION_FEE*4) * PARTNER_MULT:,.0f}&ndash;${(YEAR1_TCV + JURISDICTION_FEE*8) * PARTNER_MULT:,.0f}</td>
          <td class="amount"><strong>${(YEAR1_TCV + JURISDICTION_FEE*4) * PARTNER_DISCOUNT:,.0f}&ndash;${(YEAR1_TCV + JURISDICTION_FEE*8) * PARTNER_DISCOUNT:,.0f}</strong></td>
        </tr>
        <tr class="total-row" style="border-top: 1px solid #d1d5db;">
          <td>Year 2+ Annual</td>
          <td class="amount">${ANNUAL_RECURRING + JURISDICTION_FEE*4:,.0f}&ndash;${ANNUAL_RECURRING + JURISDICTION_FEE*8:,.0f}</td>
          <td class="amount">${(ANNUAL_RECURRING + JURISDICTION_FEE*4) * PARTNER_MULT:,.0f}&ndash;${(ANNUAL_RECURRING + JURISDICTION_FEE*8) * PARTNER_MULT:,.0f}</td>
          <td class="amount"><strong>${(ANNUAL_RECURRING + JURISDICTION_FEE*4) * PARTNER_DISCOUNT:,.0f}&ndash;${(ANNUAL_RECURRING + JURISDICTION_FEE*8) * PARTNER_DISCOUNT:,.0f}</strong></td>
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
    First jurisdiction included in Platform Fee. A Jurisdiction is any U.S. state, city, county, or municipality in which Client has employees and which imposes distinct compliance obligations. Jurisdiction count and the specific compliance categories covered within each are scoped during Discovery &amp; Gap Analysis.<br><br>
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
    <p><span class="feature-name">Compliance Engine</span> &mdash; Agentic jurisdiction research across federal, state, and local levels. Multi-location and multi-site support with preemption rule analysis. Tiered data approach: structured requirements, curated repository, and agentic research for emerging regulations. For Momentum Life Sciences &mdash; whose HR and compliance team is responsible for managing workforce compliance across a national clinical field operation spanning all 50 states &mdash; this means <strong>automated tracking of state-specific nursing board Scope of Practice changes and multi-state licensure renewals</strong>, continuous monitoring of HIPAA patient privacy obligations, GxP compliance requirements for sponsor program operations, and applicable employment law across every operating state. When a state nursing board updates the permissible scope for RN-level patient coaching or a sponsor adjusts clinical protocol standards, the engine surfaces the change mapped to the affected employee population before the next sponsor audit or FDA program review &mdash; all in a single dashboard rather than siloed across compliance, legal, and field operations teams.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Policies &amp; Handbooks</span> &mdash; Intelligent policy documents tailored to specific jurisdictions and clinical engagement environments. Electronic signature collection with audit trails. Auto-research fills jurisdiction-specific topics during handbook creation. For Momentum, this includes HIPAA and patient privacy acknowledgment policies, clinical protocol and specialty medication handling guidelines, conflict of interest and sponsor relationship policies, and applicable patient data use policies &mdash; all generated from the jurisdiction and program profile rather than drafted from scratch by legal. When a new operating state comes online or a sponsor updates its program requirements, the handbook auto-updates the affected sections and triggers bulk re-acknowledgment for impacted employees, keeping the training record current without a manual policy revision cycle.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Legislative Tracker</span> &mdash; Intelligent monitoring of regulatory changes across jurisdictions with pattern detection for coordinated legislative activity. For Momentum Life Sciences, the tracker is focused on <strong>telehealth and employment law</strong> &mdash; delivering <strong>real-time alerts on changes to state telehealth regulations and Nursing Licensure Compact (NLC) state requirements</strong>. When a state enacts new rules governing remote patient coaching sessions or modifies its NLC participation, Momentum&rsquo;s HR and compliance teams receive an immediate alert mapped to the affected workforce &mdash; enabling rapid operational decisions without waiting for manual legal review. Pattern detection also flags when multiple states simultaneously advance legislation on telehealth reimbursement, non-compete enforceability for healthcare workers, or patient privacy standards, giving HR and legal teams coordinated visibility rather than discovering the changes state by state after they pass.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Risk Assessment</span> &mdash; Multi-method organizational risk modeling: 5-dimension live risk scoring (compliance, incidents, ER cases, workforce, legislative), Monte Carlo simulation across 10,000 iterations to produce probability distributions of annual loss exposure, statistical anomaly detection using rolling mean and standard deviation on time-series metrics, and NAICS-benchmarked peer comparison sourced from BLS, OSHA, EEOC, and QCEW. Executive-ready reports with cohort heat maps across departments, locations, and tenure. For a 200-person home-office organization whose compliance surface scales with the complexity of a national clinical field operation &mdash; not just headcount &mdash; a single EEOC charge or sponsor audit finding on workforce practices can affect biopharma contract renewals and client relationships. The board-ready risk report translates operational HR data into the language that audit committees and executive leadership expect to see in a risk register. Monte Carlo outputs provide a defensible loss-probability range for employment practices liability insurance renewal discussions and allow the CFO to set litigation reserves based on statistical modeling rather than gut instinct.</p>
  </div>

  <h2>Investigations &amp; Risk</h2>

  <div class="feature-block">
    <p><span class="feature-name">Incident Reports</span> &mdash; Intelligent safety and behavioral incident reporting. OSHA 300 and 300A log generation with CSV export. Anonymous reporting support. Covers patient safety events, field safety incidents, Adverse Event (AE) reporting obligations, clinical protocol deviations, and behavioral incidents. Trend analytics and pattern detection across clinical engagement sites and field operations. As the W-2 employer of its field professionals, Momentum holds OSHA 300 recordkeeping responsibility for incidents across its entire workforce &mdash; that recordkeeping function lives with the home-office compliance and HR team. In a clinical services setting, the system tracks Adverse Event (AE) reporting timelines required under sponsor agreements, clinical protocol deviations during in-home patient visits, and patient education errors related to the self-administration of specialty medications &mdash; all in a single incident record that automatically evaluates OSHA 300 recordability. Trend analytics can surface whether incidents cluster around a specific specialty medication protocol, patient population, or geographic deployment &mdash; enabling targeted SOP improvements before an incident escalates to a sponsor audit finding or regulatory complaint.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ER Copilot</span> &mdash; Employment relations case management that <strong>acts as an active guide and a &ldquo;second set of eyes&rdquo; throughout complex investigations</strong>. Powered by AI-driven document analysis, it <strong>walks you through the case, automatically constructing timelines and flagging discrepancies</strong>. It eliminates manual cross-referencing by <strong>instantly identifying specific policy violations</strong>&mdash;no more digging through the employee handbook; the system finds it for you, while simultaneously surfacing any relevant jurisdictional laws.</p>
    <p>In a field-based organization where program managers and account executives operate across state lines managing sponsor relationships and patient programs, ER Copilot centralizes the case record for disputes involving alleged patient privacy violations, sponsor relationship misconduct, or field compliance failures &mdash; matters where the documentary timeline is as important to the outcome as the underlying facts. When a case requires outside employment counsel or litigation hold coordination, secure, encrypted PDF export links deliver a complete, date-stamped record in a form attorneys can immediately use, compressing weeks of document collection into hours.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ADA Accommodations</span> &mdash; Interactive process workflow management with intelligent accommodation suggestions, undue hardship assessment, and job function analysis. For Momentum, accommodation requests often involve program managers, account executives, and clinical program directors whose roles carry travel obligations, client site responsibilities, and multi-state operational demands. The essential functions analysis must be grounded in the specific sponsor program context and operational requirements of the role &mdash; not a generic job description. The platform&rsquo;s job function analysis integrates the specific responsibilities and requirements of each position to identify feasible modifications &mdash; producing documentation that satisfies both EEOC and applicable state standards simultaneously.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Pre-Termination Intelligence</span> &mdash; 9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before separation decisions. AI-generated narrative memo suitable for counsel review. For Momentum, the system flags when a proposed termination involves a program manager, account executive, or clinical director who recently raised a HIPAA concern, flagged a sponsor compliance issue, or reported a patient safety concern internally &mdash; categories that trigger retaliation protection under OSHA Section 11(c), applicable state whistleblower statutes, and patient safety reporting protections. At a company where a single high-profile retaliation claim could affect sponsor confidence or biopharma client relationships, this pre-decisional check is the highest-leverage risk control available.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Separation Agreements</span> &mdash; OWBPA-compliant agreement generation with proper consideration periods (21/45 day) and revocation window tracking. Group layoff disclosure support. For Momentum, separation agreements routinely include sponsor confidentiality confirmations and non-solicitation provisions &mdash; documents that are frequently assembled manually from multiple templates under time pressure when a departure is unexpected. The platform generates a complete, jurisdiction-compliant separation package from a single workflow, with the OWBPA disclosures, consideration period tracking, and revocation window built in so nothing is inadvertently omitted.</p>
  </div>

  <h2>Workforce Management</h2>

  <div class="feature-block">
    <p><span class="feature-name">Employee Directory &amp; Bulk Import</span> &mdash; Centralized employee records with CSV bulk upload, batch creation, Google Workspace and Slack account provisioning for new hires.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Onboarding</span> &mdash; Custom onboarding templates built during implementation and tailored to Momentum&rsquo;s specific roles and compliance requirements. Matcha handles the initial onboarding build-out, then hands off the template system to your admin team &mdash; giving you full control to create, modify, and run future onboarding cohorts independently. Supports role-specific workflows with progress analytics, funnel metrics, bottleneck identification, and completion tracking.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Compliance &amp; Operations Dashboard</span> &mdash; In a fast-paced clinical engagement environment, missing a regulatory shift, a license renewal, or a mandated drug-safety training update isn&rsquo;t just an administrative error&mdash;it&rsquo;s a compliance risk that can disrupt active patient programs and trigger sponsor audit findings. The dashboard acts as your operational command center, giving you a centralized, real-time view of your team&rsquo;s status. At a glance, you can monitor upcoming regulatory changes, track exactly when an employee&rsquo;s leave of absence (LOA) is coming to an end, and review outstanding incident reports or ER Copilot action items. To ensure nothing slips through the cracks, the system features a dual-alert system, pushing proactive notifications directly to your dashboard and sending them straight to your email.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Automated License &amp; Training Tracking</span> &mdash; Managing credentials across a clinical engagement organization shouldn&rsquo;t rely on manual spreadsheets. Some of Momentum&rsquo;s home-office staff hold clinical credentials of their own &mdash; clinical program directors, medical directors &mdash; with multi-state licensure requirements. All 200 employees require HIPAA certification and OIG anti-kickback compliance training mandated by sponsors. Matcha features a dedicated tracking engine for all employee licenses, certifications, and mandatory compliance training. It automatically monitors every expiry date and acts as an intelligent early warning system &mdash; emailing both the employee and their manager when a credential is approaching expiration, with a secure direct link to upload the renewed document. Automated follow-ups escalate as deadlines approach. If a credential expires, Matcha immediately alerts designated compliance personnel, ensuring your team remains fully certified and sponsor audit-ready without manual oversight.</p>
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
  <p>Total duration: 7&ndash;8 weeks. During implementation, Matcha builds a custom compliance and HR management system configured to your jurisdictions, roles, and workflows. At go-live, this system is handed off to your admin team as a fully operational CMS &mdash; your team owns it and runs it independently from that point forward. Your dedicated Customer Success Manager guides every phase.</p>

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
        <td class="cost">$3,000</td>
        <td>Organizational mapping, HRIS audit, clinical engagement site inventory, regulatory gap analysis &mdash; audit HIPAA compliance programs, sponsor agreement obligations, state nursing board licensure coverage, NLC compact participation map, GxP training records, telehealth deployment footprint</td>
      </tr>
      <tr>
        <td class="phase">Configuration &amp; Templating</td>
        <td>Weeks 3&ndash;4</td>
        <td class="cost">$3,000</td>
        <td>Location/jurisdiction setup, compliance baseline scan, build role-specific onboarding templates (program director, account executive, clinical program manager, operations staff, HR and compliance personnel), credential and nursing license expiration workflows, HIPAA training record workflows, handbook and policy document ingestion</td>
      </tr>
      <tr>
        <td class="phase">Data Migration &amp; Manual Run</td>
        <td>Weeks 5&ndash;6</td>
        <td class="cost">$2,000</td>
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
        <td class="cost">$500</td>
        <td>Production cutover, CSM handoff, post-launch monitoring</td>
      </tr>
    </tbody>
  </table>

  <h2>Security &amp; Infrastructure</h2>

  <ul class="terms-list">
    <li><span class="term-label">HIPAA Compliance</span> Platform infrastructure and data handling practices are designed to support HIPAA compliance. BAA available upon request. PHI is encrypted in transit and at rest and never used for model training or third-party sharing.</li>
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

  <p style="margin-bottom: 14px;">Patient support and HCP engagement organizations carry a disproportionately high compliance burden relative to their headcount. Operating across multiple states with sponsor-driven program obligations means navigating HIPAA requirements, Nursing Licensure Compact (NLC) participation rules, state-specific Scope of Practice variations, and multi-jurisdiction employment law &mdash; all managed by a home-office HR team rather than a large legal department. EEOC charges in healthcare services have increased as the sector has expanded, and the DOL has prioritized wage and hour enforcement in healthcare services organizations where contractor classifications and multi-state operations have come under scrutiny.</p>

  <table class="roi-table">
    <thead>
      <tr>
        <th>Estimated Annual Cost</th>
        <th style="text-align:right">Industry Estimate</th>
        <th style="text-align:right">Estimated Savings</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Outside employment counsel</td>
        <td style="text-align:right">$95,000/yr</td>
        <td style="text-align:right"><strong>$52,000</strong></td>
      </tr>
      <tr>
        <td>ER cases sent to outside counsel (2&ndash;3/yr)</td>
        <td style="text-align:right">$50,000/yr</td>
        <td style="text-align:right"><strong>$35,000</strong></td>
      </tr>
      <tr>
        <td>HR staff time on compliance tasks</td>
        <td style="text-align:right">$160,000/yr</td>
        <td style="text-align:right"><strong>$85,000</strong></td>
      </tr>
      <tr>
        <td>Handbook &amp; policy legal review</td>
        <td style="text-align:right">$18,000/yr</td>
        <td style="text-align:right"><strong>$14,000</strong></td>
      </tr>
      <tr>
        <td>Adverse event &amp; field incident recordkeeping</td>
        <td style="text-align:right">$28,000/yr</td>
        <td style="text-align:right"><strong>$18,000</strong></td>
      </tr>
      <tr>
        <td>Nursing license &amp; compliance training tracking</td>
        <td style="text-align:right">$28,000/yr</td>
        <td style="text-align:right"><strong>$20,000</strong></td>
      </tr>
      <tr style="background:#f5f5f7;">
        <td><strong>Annual hard savings</strong></td>
        <td></td>
        <td style="text-align:right"><strong>${HARD_SAVINGS:,.0f}</strong></td>
      </tr>
    </tbody>
  </table>

  <p style="font-size:9pt; color:#6b7280; margin-top:8px;">Savings driven by ER Copilot handling investigations internally, the Compliance Engine automating nursing board and jurisdiction monitoring, and Pre-Termination Intelligence reducing matters requiring attorney involvement. HR compliance staff time savings reflect automation of nursing license tracking, HIPAA compliance verification workflows, and multi-state regulatory monitoring.</p>
  <p style="font-size:8.5pt; color:#9ca3af; margin-top:6px; font-style:italic;">Cost estimates are modeled from industry benchmarks for healthcare services organizations of comparable size and regulatory complexity. Actual costs may vary based on your current vendor relationships, internal staffing, and operational model.</p>

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
        <td>Annual recurring (est. 6 jurisdictions)</td>
        <td style="text-align:right">${ANNUAL_RECURRING_EST:,.0f}</td>
        <td style="text-align:right">${ANNUAL_RECURRING_EST:,.0f}</td>
        <td style="text-align:right">${ANNUAL_RECURRING_EST:,.0f}</td>
        <td style="text-align:right">${ANNUAL_RECURRING_EST*3:,.0f}</td>
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
        <td style="text-align:right"><strong>${YEAR1_TCV_EST:,.0f}</strong></td>
        <td style="text-align:right"><strong>${ANNUAL_RECURRING_EST:,.0f}</strong></td>
        <td style="text-align:right"><strong>${ANNUAL_RECURRING_EST:,.0f}</strong></td>
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
