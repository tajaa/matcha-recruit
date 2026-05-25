#!/usr/bin/env python3
"""Generate a professional PDF deal proposal for a healthcare client."""

import os
from datetime import date
from weasyprint import HTML

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deals", "onc")
VERSION = "v8"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, f"Matcha_Healthcare_Proposal_{VERSION}.pdf")

# ── Config ──────────────────────────────────────────────────────────────────
CLIENT_NAME = "The Oncology Institute"
EMPLOYEE_COUNT = 650

# Pricing
LIST_PEPM = 14.00
PARTNER_DISCOUNT = 0.13  # 13% partner program discount
PARTNER_PEPM = LIST_PEPM * (1 - PARTNER_DISCOUNT)  # $12.32
VOLUME_DISCOUNT = 0.05  # 5% automatic for 500+ employees
PEPM = LIST_PEPM * (1 - VOLUME_DISCOUNT) if EMPLOYEE_COUNT >= 500 else LIST_PEPM
PLATFORM_FEE = 10_000  # annual, Business tier (includes federal + 1 jurisdiction)
JURISDICTION_FEE = 7_500  # per additional jurisdiction/year, Business tier
IMPL_FEE = 25_000

MONTHLY = PEPM * EMPLOYEE_COUNT
ANNUAL = MONTHLY * 12
ANNUAL_RECURRING = ANNUAL + PLATFORM_FEE  # before additional jurisdictions
YEAR1_TCV = ANNUAL_RECURRING + IMPL_FEE
TODAY = date.today().strftime("%B %d, %Y")

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
    Matcha replaces manual compliance tracking, fragmented ER case management, spreadsheet-based credential monitoring, and reactive risk management with a single agentic platform. For multi-location healthcare organizations, that means jurisdiction-level compliance monitoring, incident investigations, and pre-termination risk scoring &mdash; all consolidated into one system. During implementation, Matcha builds a custom compliance and HR management system tailored to your organization &mdash; your jurisdictions, your roles, your workflows. After go-live, this system is handed off to your admin team as a fully operational CMS that you own and run independently &mdash; reducing legal exposure, eliminating manual tracking, and delivering real-time risk visibility across every facility. Every requirement is sourced from government databases and regulatory texts, with citation links and verification timestamps so your team can trust the data without independent research.
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
          <td>List Rate (Per Employee Per Month)</td>
          <td class="amount">${LIST_PEPM:.2f}</td>
        </tr>
        <tr>
          <td>Volume Discount (500+ employees)</td>
          <td class="amount">&ndash;{VOLUME_DISCOUNT:.0%}</td>
        </tr>
        <tr>
          <td>Your PEPM: ${PEPM:.2f} &times; {EMPLOYEE_COUNT} employees &times; 12 months</td>
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

  <h2>Partner Program Pricing (13% off)</h2>

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
          <td class="amount">${LIST_PEPM * 0.87:.2f}</td>
          <td class="amount">${PEPM - (LIST_PEPM * 0.87):.2f}/ee/mo</td>
        </tr>
        <tr>
          <td>Annual Employee Cost ({EMPLOYEE_COUNT} ee)</td>
          <td class="amount">${ANNUAL:,.0f}</td>
          <td class="amount">${LIST_PEPM * 0.87 * EMPLOYEE_COUNT * 12:,.0f}</td>
          <td class="amount">${ANNUAL - (LIST_PEPM * 0.87 * EMPLOYEE_COUNT * 12):,.0f}</td>
        </tr>
        <tr>
          <td>Platform Fee</td>
          <td class="amount">${PLATFORM_FEE:,.0f}</td>
          <td class="amount">${PLATFORM_FEE * 0.87:,.0f}</td>
          <td class="amount">${PLATFORM_FEE * 0.13:,.0f}</td>
        </tr>
        <tr>
          <td>Per Additional Jurisdiction</td>
          <td class="amount">${JURISDICTION_FEE:,.0f}</td>
          <td class="amount">${JURISDICTION_FEE * 0.87:,.0f}</td>
          <td class="amount">${JURISDICTION_FEE * 0.13:,.0f}</td>
        </tr>
        <tr style="background:#f5f5f7;">
          <td><strong>Annual Recurring</strong></td>
          <td class="amount"><strong>${ANNUAL_RECURRING:,.0f}</strong></td>
          <td class="amount"><strong>${(LIST_PEPM * 0.87 * EMPLOYEE_COUNT * 12) + (PLATFORM_FEE * 0.87):,.0f}</strong></td>
          <td class="amount"><strong>${ANNUAL_RECURRING - ((LIST_PEPM * 0.87 * EMPLOYEE_COUNT * 12) + (PLATFORM_FEE * 0.87)):,.0f}</strong></td>
        </tr>
        <tr>
          <td>Implementation &amp; Configuration</td>
          <td class="amount">${IMPL_FEE:,.0f}</td>
          <td class="amount">${IMPL_FEE * 0.87:,.0f}</td>
          <td class="amount">${IMPL_FEE * 0.13:,.0f}</td>
        </tr>
        <tr class="total-row">
          <td>Year 1 Total</td>
          <td class="amount">${YEAR1_TCV:,.0f}</td>
          <td class="amount">${(LIST_PEPM * 0.87 * EMPLOYEE_COUNT * 12) + (PLATFORM_FEE * 0.87) + (IMPL_FEE * 0.87):,.0f}</td>
          <td class="amount"><strong>${YEAR1_TCV - ((LIST_PEPM * 0.87 * EMPLOYEE_COUNT * 12) + (PLATFORM_FEE * 0.87) + (IMPL_FEE * 0.87)):,.0f}</strong></td>
        </tr>
        <tr class="total-row" style="border-top: 1px solid #d1d5db;">
          <td>Year 2+ Annual</td>
          <td class="amount">${ANNUAL_RECURRING:,.0f}</td>
          <td class="amount">${(LIST_PEPM * 0.87 * EMPLOYEE_COUNT * 12) + (PLATFORM_FEE * 0.87):,.0f}</td>
          <td class="amount"><strong>${ANNUAL_RECURRING - ((LIST_PEPM * 0.87 * EMPLOYEE_COUNT * 12) + (PLATFORM_FEE * 0.87)):,.0f}</strong></td>
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
          <td>Growth</td>
          <td>1&ndash;249</td>
          <td class="amount">$4,000</td>
        </tr>
        <tr>
          <td><strong>Business</strong></td>
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
    <strong>Partner Program (${PARTNER_PEPM:.2f} PEPM)</strong> &mdash; 12% discount available for organizations that commit to: quarterly video insight sessions, anonymized case study participation, anonymized data sharing for industry benchmarking, logo rights for Matcha marketing materials, one public platform review (G2 or similar) within 90 days of go-live, and annual prepayment or 2-year term commitment.<br>
    <strong>Volume Discount</strong> &mdash; 5% discount applied automatically for organizations with 500 or more employees.<br>
    Price locked for the 12-month initial term. Employee count subject to quarterly true-up.
  </p>

</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- PAGE 3: PLATFORM CAPABILITIES (1 of 2)                                -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Platform Capabilities</div>
  </div>

  <h1>Platform Capabilities</h1>

  <h2>Compliance &amp; Legal</h2>

  <div class="feature-block">
    <p><span class="feature-name">Compliance Engine</span> &mdash; Agentic jurisdiction research across federal, state, and local levels. Multi-location support with preemption rule analysis. Tiered data approach: structured requirements, curated repository, and Agentic research for emerging regulations. For an oncology practice operating across multiple states, this means continuous monitoring of CMS Conditions of Participation, state radiation control program requirements, and applicable Joint Commission standards — all in a single dashboard with citation links rather than scattered across regulatory agency websites. When CMS publishes updated Oncology Care Model guidance or a state modifies chemo handling disposal rules, the engine surfaces the change and maps it to the affected facility before the next survey cycle.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Policies &amp; Handbooks</span> &mdash; AI-powered policy documents tailored to specific jurisdictions. Electronic signature collection with audit trails. Auto-research fills jurisdiction-specific topics during handbook creation. In an oncology setting, this includes HIPAA workforce policies, radiation safety acknowledgments, chemotherapy handling protocols required by OSHA's Hazardous Drugs standard, and state-specific mandated reporter obligations — all generated from the jurisdiction profile rather than drafted from scratch by HR. Electronic acknowledgment collection creates the documented workforce training record that Joint Commission surveyors and state licensing boards expect to see during on-site reviews.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Legislative Tracker</span> &mdash; Intelligent monitoring of regulatory changes across jurisdictions with pattern detection for coordinated legislative activity. In the oncology sector, this includes tracking CMS reimbursement rule changes that carry workforce compliance implications, state prior authorization reform laws affecting clinical staffing decisions, and No Surprises Act regulatory updates. Pattern detection flags when multiple states simultaneously advance bills affecting healthcare workforce requirements — giving compliance and HR teams time to prepare before the effective date rather than reacting after publication.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Risk Assessment</span> &mdash; Multi-method organizational risk modeling: 5-dimension live risk scoring (compliance, incidents, ER cases, workforce, legislative), Monte Carlo simulation across 10,000 iterations to produce probability distributions of annual loss exposure, statistical anomaly detection using rolling mean and standard deviation on time-series metrics, and NAICS-benchmarked peer comparison sourced from BLS, OSHA, EEOC, and QCEW. Executive-ready reports with cohort heat maps across departments, locations, and tenure. Given that healthcare accounts for 21% of all EEOC charges filed nationally, the peer benchmarking dimension is particularly revealing — allowing The Oncology Institute to compare its EEOC charge rate per thousand employees against the NAICS 621 ambulatory care cohort rather than against an industry-averaged baseline that obscures the true sectoral risk. Monte Carlo loss projections give the CFO a defensible dollar range for D&amp;O risk reporting and employment practices liability insurance negotiations.</p>
  </div>

  <h2>Investigations &amp; Risk</h2>

  <div class="feature-block">
    <p><span class="feature-name">Incident Reports</span> &mdash; Intelligent safety and behavioral incident reporting. OSHA 300 and 300A log generation with CSV export. Anonymous reporting support. Trend analytics and pattern detection across locations. For an oncology practice, incident tracking covers chemotherapy spill and exposure events, needle-stick injuries, patient-handling musculoskeletal incidents, and behavioral events — all in a single system with OSHA 300 recordability determinations built into the intake workflow. Trend analytics across clinic locations can surface whether a particular infusion room or shift configuration is driving a disproportionate share of hazardous drug exposure incidents, enabling targeted corrective action before an OSHA inspection or workers' comp audit.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ER Copilot</span> &mdash; Employment relations case management that <strong>acts as an active guide and a &ldquo;second set of eyes&rdquo; throughout complex investigations</strong>. Powered by AI-driven document analysis, it <strong>walks you through the case, automatically constructing timelines and flagging discrepancies</strong>. It eliminates manual cross-referencing by <strong>instantly identifying specific policy violations</strong>&mdash;no more digging through the employee handbook; the system finds it for you, while simultaneously surfacing any relevant jurisdictional laws.</p>
    <p>In a clinical setting, ER Copilot handles the documentation-heavy investigations that arise from patient complaint-triggered HR cases, license-based discipline matters, and FMLA interference claims. These categories are elevated in healthcare due to the emotional intensity of clinical work and the complexity of FMLA interactions with shift-based schedules. When a case does reach outside employment counsel, secure, encrypted PDF export links deliver a complete, chronological record in a form attorneys can immediately use, drastically cutting preliminary review time and the associated billable hours.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ADA Accommodations</span> &mdash; Interactive process workflow management with intelligent accommodation suggestions, undue hardship assessment, and job function analysis. In oncology settings, accommodation requests frequently involve radiation exposure limitations for pregnant technologists, physical lifting restrictions for nurses, or schedule modifications for employees managing their own chronic conditions — each requiring a role-specific essential functions analysis rather than a generic response. The interactive process workflow documents every communication and decision point, creating a defensible record that withstands EEOC scrutiny even when accommodation is ultimately denied on undue hardship grounds.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Pre-Termination Intelligence</span> &mdash; 9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before separation decisions. AI-generated narrative memo suitable for counsel review. For a healthcare employer, this means the system automatically flags when a proposed termination involves an employee who recently filed an OSHA hazardous drug complaint, requested FMLA, or raised a patient safety concern — categories that trigger whistleblower protection under Section 11(c) of OSHA, FMLA, and the False Claims Act respectively. Catching those facts before a termination decision is finalized is far less expensive than litigating a retaliation claim after the employee files with DOL or HHS.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Separation Agreements</span> &mdash; OWBPA-compliant agreement generation with proper consideration periods (21/45 day) and revocation window tracking. Group layoff disclosure support. In a healthcare system that may periodically restructure care delivery teams across facilities, the group layoff disclosure automation handles the OWBPA requirement to disclose the ages and job titles of all employees in the decisional unit — a step that is frequently omitted in healthcare RIFs and renders the released claims unenforceable. The built-in revocation tracking replaces informal email chains with a documented, timestamped process that satisfies both OWBPA and any applicable state law analog.</p>
  </div>

  <h2>Workforce Management</h2>

  <div class="feature-block">
    <p><span class="feature-name">Employee Directory &amp; Bulk Import</span> &mdash; Centralized employee records with CSV bulk upload, batch creation, Google Workspace and Slack account provisioning for new hires.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Onboarding</span> &mdash; Custom onboarding templates built during implementation and tailored to your organization&rsquo;s specific roles, credential requirements, and compliance workflows. Matcha handles the initial onboarding build-out, then hands off the template system to your admin team &mdash; giving you full control to create, modify, and run future onboarding cohorts independently. Supports credential and license verification gates, HIPAA workforce training, and role-specific workflows with progress analytics, funnel metrics, bottleneck identification, and completion tracking.</p>
  </div>

  <h2>Agentic Document Workspace (Matcha Work)</h2>

  <div class="feature-block">
    <p>Chat-driven document creation with threading, iterative drafts, and internal data search mode for cross-referencing organizational information. Supports performance reviews, workbooks, onboarding plans, presentations, handbooks, and policies.</p>
    <p><span class="feature-name">Chat with Your Data</span> &mdash; Query your employee records, incident logs, compliance requirements, and ER cases directly. Surface patterns and pull ad-hoc reports without exporting to spreadsheets.</p>
    <p><span class="feature-name">Chain of Reasoning Compliance Querying</span> &mdash; Multi-step compliance analysis that walks through regulatory logic step by step&mdash;citing sources, applying preemption rules, and surfacing gaps&mdash;before returning a final answer. <strong>Monthly usage credits included.</strong></p>
  </div>


</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- PAGE 5: IMPLEMENTATION + TERMS                                        -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Implementation &amp; Terms</div>
  </div>

  <h1>Implementation Timeline</h1>
  <p>Total duration: 6&ndash;8 weeks. During implementation, Matcha builds a custom compliance and HR management system configured to your jurisdictions, roles, and workflows. At go-live, this system is handed off to your admin team as a fully operational CMS &mdash; your team owns it and runs it independently from that point forward. Your dedicated Customer Success Manager guides every phase.</p>

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
        <td class="cost">$4,500</td>
        <td>Organizational mapping, HRIS audit, location inventory, regulatory gap analysis &mdash; audit existing documentation, certifications, and licenses against oncology-specific requirements (radiation safety certs, chemo handling training, CRT licensing)</td>
      </tr>
      <tr>
        <td class="phase">Configuration &amp; Templating</td>
        <td>Weeks 3&ndash;4</td>
        <td class="cost">$4,000</td>
        <td>Location/jurisdiction setup, compliance baseline scan, build role-specific onboarding templates (rad tech, RN, pharmacist, physicist), credential expiration workflows, handbook ingestion</td>
      </tr>
      <tr>
        <td class="phase">Data Migration &amp; Manual Run</td>
        <td>Weeks 5&ndash;6</td>
        <td class="cost">$2,500</td>
        <td>Employee data import, historical records migration, policy document ingestion, run first onboarding cohort manually using templates to validate completeness</td>
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
    <li><span class="term-label">Partner Program</span> 12% discount (${PARTNER_PEPM:.2f} PEPM) with quarterly video insights, anonymized case study &amp; data sharing, logo rights, public review within 90 days, and annual prepayment or 2-year term</li>
    <li><span class="term-label">Volume Discount</span> 5% discount applied automatically for 500+ employees</li>
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
<!-- PAGE 6: ROI + SUPPORT + SIGNATURES                                    -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">ROI &amp; Support</div>
  </div>

  <h1>Return on Investment</h1>

  <p style="margin-bottom: 14px;">Healthcare is the #1 most-targeted industry by the EEOC &mdash; <strong>21% of all charges filed nationally</strong>, despite representing roughly 10% of the workforce. Healthcare employers face EEOC charges at <strong>2&times; the rate of any other industry</strong>, and the Department of Labor recovered <strong>$53 million in back wages from healthcare employers in FY2025 alone</strong>.</p>

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
        <td style="text-align:right">$98,000/yr</td>
        <td style="text-align:right"><strong>$37,000</strong></td>
      </tr>
      <tr>
        <td>ER cases sent to outside counsel (4/yr)</td>
        <td style="text-align:right">$72,000/yr</td>
        <td style="text-align:right"><strong>$40,000</strong></td>
      </tr>
      <tr>
        <td>HR staff time on compliance tasks</td>
        <td style="text-align:right">$130,000/yr</td>
        <td style="text-align:right"><strong>$36,000</strong></td>
      </tr>
      <tr>
        <td>Handbook &amp; policy legal review</td>
        <td style="text-align:right">$8,000/yr</td>
        <td style="text-align:right"><strong>$6,500</strong></td>
      </tr>
      <tr>
        <td>OSHA incident admin &amp; reporting</td>
        <td style="text-align:right">$15,000/yr</td>
        <td style="text-align:right"><strong>$8,500</strong></td>
      </tr>
      <tr>
        <td>Compliance training &amp; certification tracking</td>
        <td style="text-align:right">$8,000/yr</td>
        <td style="text-align:right"><strong>$4,000</strong></td>
      </tr>
      <tr style="background:#f5f5f7;">
        <td><strong>Annual hard savings</strong></td>
        <td></td>
        <td style="text-align:right"><strong>$132,000</strong></td>
      </tr>
    </tbody>
  </table>

  <p style="font-size:9pt; color:#6b7280; margin-top:8px;">Savings driven by ER Copilot handling investigations internally instead of at outside counsel rates, the Compliance Engine automating jurisdiction monitoring, and Pre-Termination Intelligence reducing matters requiring attorney involvement.</p>

  <div class="roi-highlight">
    Year 1 ROI: 1.9&times; &middot; Platform pays for itself by month 6 &middot; 3-year net savings: $302,000
  </div>

  <h1 style="margin-top: 32px;">Dedicated Support</h1>

  <ul>
    <li><strong>Customer Success Manager</strong> assigned at contract signing through go-live and beyond</li>
    <li>Admin and manager training sessions included in implementation</li>
    <li>Ongoing CSM check-ins post go-live</li>
    <li>Platform support for configuration changes, new location rollouts, and feature adoption</li>
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
