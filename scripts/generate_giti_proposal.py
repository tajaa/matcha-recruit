#!/usr/bin/env python3
"""Generate a professional PDF deal proposal for Giti Tire."""

import os
from datetime import date
from weasyprint import HTML

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deals", "giti")
VERSION = "v1"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, f"Matcha_Giti_Proposal_{VERSION}.pdf")

# ── Config ──────────────────────────────────────────────────────────────────
CLIENT_NAME = "Giti Tire"
EMPLOYEE_COUNT = 900
LIST_PEPM = 14.00
PEPM = 11.00
DISCOUNT_AMT = LIST_PEPM - PEPM
PARTNER_PEPM = 9.50
IMPL_FEE = 16_000
MONTHLY = PEPM * EMPLOYEE_COUNT
ANNUAL = MONTHLY * 12
YEAR1_TCV = ANNUAL + IMPL_FEE
PARTNER_MONTHLY = PARTNER_PEPM * EMPLOYEE_COUNT
PARTNER_ANNUAL = PARTNER_MONTHLY * 12
PARTNER_YEAR1_TCV = PARTNER_ANNUAL + IMPL_FEE
TODAY = date.today().strftime("%B %d, %Y")

# ROI numbers
HARD_SAVINGS = 168_000
RISK_REDUCTION = 62_000
TOTAL_VALUE = HARD_SAVINGS + RISK_REDUCTION
NET_Y1 = TOTAL_VALUE - YEAR1_TCV
ROI_MULTIPLE = TOTAL_VALUE / YEAR1_TCV
YEAR2_NET = TOTAL_VALUE - ANNUAL
THREE_YEAR_INVEST = YEAR1_TCV + (ANNUAL * 2)
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

  .callout-box {{
    background: #fff8ed;
    border: 1px solid #f59e0b;
    border-left: 4px solid #f59e0b;
    border-radius: 4px;
    padding: 12px 16px;
    margin: 16px 0;
    font-size: 9.5pt;
    color: #1a1a2e;
  }}

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

<!-- COVER -->
<div class="cover">
  <div class="cover-accent"></div>
  <div class="cover-accent-2"></div>
  <div class="cover-top">
    <div class="logo-text">matcha</div>
    <div class="logo-sub">Risk, Compliance, Employee Relations Intelligence</div>
  </div>
  <div class="cover-middle">
    <div class="cover-title">Platform<br><strong>Service Proposal</strong></div>
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

<!-- PAGE 2: EXEC SUMMARY + PRICING -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Service Proposal &middot; {CLIENT_NAME}</div>
  </div>

  <h1>Executive Summary</h1>

  <div class="executive-summary">
    Matcha is an agentic workforce risk management platform built for manufacturing organizations operating at the intersection of heavy OSHA compliance, active labor relations, and multi-department workforce management. For Giti Tire, that means jurisdiction-level compliance monitoring across federal and multi-state OSHA requirements, incident tracking across a large production floor, proactive employment relations case management, and pre-termination risk intelligence&mdash;all in a single platform. Every requirement is sourced from government databases and regulatory texts, with citation links and verification timestamps your team can act on with confidence.
  </div>

  <h1>Investment Summary</h1>

  <div class="pricing-box">
    <table>
      <thead>
        <tr>
          <th>Line Item</th>
          <th style="text-align:right; color:#9ca3af; font-weight:500; font-size:11px;">Channel Rate</th>
          <th style="text-align:right; color:#9ca3af; font-weight:500; font-size:11px;">Partner Rate</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>List Rate (Per Employee Per Month)</td>
          <td class="amount">${LIST_PEPM:.2f}</td>
          <td class="amount">${LIST_PEPM:.2f}</td>
        </tr>
        <tr>
          <td>Discount</td>
          <td class="amount">&ndash;${DISCOUNT_AMT:.2f} (21%)</td>
          <td class="amount">&ndash;${LIST_PEPM - PARTNER_PEPM:.2f} (32%)</td>
        </tr>
        <tr>
          <td><strong>Discounted PEPM &times; {EMPLOYEE_COUNT} employees</strong></td>
          <td class="amount"><strong>${PEPM:.2f}</strong></td>
          <td class="amount"><strong>${PARTNER_PEPM:.2f}</strong></td>
        </tr>
        <tr>
          <td>Monthly Platform Cost</td>
          <td class="amount">${MONTHLY:,.2f}</td>
          <td class="amount">${PARTNER_MONTHLY:,.2f}</td>
        </tr>
        <tr>
          <td>Annual Platform Cost (12 months)</td>
          <td class="amount">${ANNUAL:,.2f}</td>
          <td class="amount">${PARTNER_ANNUAL:,.2f}</td>
        </tr>
        <tr>
          <td>One-Time Implementation &amp; Onboarding</td>
          <td class="amount">${IMPL_FEE:,.2f}</td>
          <td class="amount">${IMPL_FEE:,.2f}</td>
        </tr>
        <tr class="total-row">
          <td>Year 1 Total Contract Value</td>
          <td class="amount">${YEAR1_TCV:,.2f}</td>
          <td class="amount">${PARTNER_YEAR1_TCV:,.2f}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <p class="pricing-note">
    <strong>Channel Rate ($11.00 PEPM)</strong> — standard broker-introduced pricing, all features included, no module upsells.<br>
    <strong>Partner Rate ($9.50 PEPM)</strong> — available for organizations that commit to: quarterly video insight sessions, anonymized case study participation, anonymized data sharing for industry benchmarking, logo rights for Matcha marketing materials, one public platform review (G2 or similar) within 90 days of go-live, and annual prepayment or 2-year term commitment.<br>
    Price locked for the 12-month initial term. Employee count subject to quarterly true-up.
  </p>

</div>

<!-- PAGE 3: PLATFORM CAPABILITIES -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Platform Capabilities</div>
  </div>

  <h1>Platform Capabilities</h1>

  <h2>Compliance &amp; Legal</h2>

  <div class="feature-block">
    <p><span class="feature-name">Compliance Engine</span> &mdash; Jurisdiction research across federal and state levels for all active locations. Covers state-plan and federal OSHA standards, FLSA, NLRA, and applicable environmental and chemical exposure regulations. Multi-location support with preemption rule analysis and tiered data approach for emerging regulatory changes. For a South Carolina manufacturer operating under federal OSHA alongside states with their own approved plans, this means a single dashboard that surfaces the controlling standard at each facility without manual cross-referencing. Chemical process change at one plant? The engine flags updated PEL requirements and SDS obligations in the affected jurisdiction before a coordinator even opens a browser.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Policies &amp; Handbooks</span> &mdash; Policy documents tailored to manufacturing environments across all active jurisdictions. Covers OSHA-mandated written programs (HazCom, LOTO, Respiratory Protection, Hearing Conservation), employment policies, and NLRA-compliant solicitation and communication policies. Electronic signature collection with audit trails. In a unionized or pre-petition environment, having electronically signed, timestamped acknowledgments of solicitation and no-distribution policies is a frontline defense if those policies are challenged at the NLRB. When a new state location comes online, the handbook auto-generates with jurisdiction-specific provisions already populated — no starting from a blank template.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Legislative Tracker</span> &mdash; Real-time monitoring of regulatory changes across federal and state-plan OSHA, NLRB guidance, and multi-state employment law with pattern detection for coordinated legislative activity. For a tire manufacturer, this means automatic alerts when OSHA proposes updates to chemical exposure limits for compounds like carbon black or styrene-butadiene, giving safety teams lead time to update SOPs before enforcement deadlines. Pattern detection also flags when multiple states simultaneously introduce "right to organize" or heat illness prevention bills — letting HR get ahead of coordinated legislative waves rather than reacting jurisdiction by jurisdiction.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Risk Assessment</span> &mdash; Multi-method organizational risk modeling: 5-dimension live risk scoring (compliance, incidents, ER cases, workforce, legislative), Monte Carlo simulation across 10,000 iterations to produce probability distributions of annual loss exposure, statistical anomaly detection using rolling mean and standard deviation on time-series metrics, and NAICS-benchmarked peer comparison sourced from BLS, OSHA, EEOC, and QCEW. Executive-ready reports with cohort heat maps across departments, shifts, and tenure. For Giti's multi-plant footprint, this means seeing at a glance which facility is carrying disproportionate OSHA incident rate risk relative to NAICS 3262 (rubber products) peers — before an OSHA programmed inspection targets it. Monte Carlo outputs translate that risk into a dollar range your CFO can use in budget conversations, grounded in your own historical data.</p>
  </div>

  <h2>Investigations &amp; Risk</h2>

  <div class="feature-block">
    <p><span class="feature-name">Incident Reports</span> &mdash; Agentic safety and behavioral incident reporting designed for high-volume manufacturing environments. OSHA 300 and 300A log generation with CSV export. Anonymous reporting support. Covers machine incidents, chemical exposure events, ergonomic injuries, near-misses, and behavioral incidents. Trend analytics and pattern detection across shifts and departments. In a tire plant environment, the system can correlate ergonomic strain incidents by production line and shift to identify equipment or scheduling patterns driving injury clusters — giving the safety team data to act on before OSHA receives an employee complaint. OSHA 300 logs are maintained in real time and exportable in the required format, eliminating the end-of-year scramble to reconstruct recordable incidents from scattered emails and paper forms.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ER Copilot</span> &mdash; Employment relations case management with agentic document analysis. Timeline construction and discrepancy detection. Encrypted PDF report generation. Secure shared export links for external counsel. Particularly valuable in active labor relations environments where documentation quality determines outcomes. In a manufacturing setting with shift supervisors making real-time discipline decisions, ER Copilot creates a centralized, searchable case record that prevents inconsistent treatment claims — the most common gateway to NLRA and Title VII exposure. When a grievance escalates to arbitration, the encrypted case export gives outside counsel a complete, timestamped record in minutes rather than weeks of document collection.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ADA Accommodations</span> &mdash; Interactive process workflow management with agentic accommodation suggestions, undue hardship assessment, and job function analysis for physical manufacturing roles. In a plant environment where most jobs carry essential physical functions — lifting, standing, operating machinery — the system analyzes job descriptions to surface feasible modifications like duty reassignment or shift changes without requiring HR to build the legal case from scratch. Undue hardship analysis includes the specific cost and operational factors relevant to production-floor roles, producing a documented record that satisfies the EEOC's interactive process standard.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Pre-Termination Intelligence</span> &mdash; 9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before separation decisions. Critical in manufacturing environments with active labor relations activity, where termination timing and documentation are subject to heightened scrutiny. Agentic-generated narrative memo suitable for counsel review. The system flags when a proposed termination falls within 90 days of a protected activity (OSHA complaint, NLRA organizing activity, workers' comp filing) — the exact window that triggers heightened NLRB and OSHA retaliation scrutiny. That single check, applied consistently across 900 employees and multiple facilities, eliminates the most common source of six-figure wrongful termination exposure in manufacturing.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Separation Agreements</span> &mdash; OWBPA-compliant agreement generation with proper consideration periods (21/45 day) and revocation window tracking. Group layoff disclosure support. For a manufacturer conducting a reduction in force across multiple facilities, the system automatically generates the required OWBPA group layoff disclosures listing decisional unit, eligibility factors, job titles, and ages of affected and retained employees — a form that outside counsel typically charges $3,000–$8,000 to draft. Electronic delivery and revocation tracking are built in, creating a complete compliance record without HR managing certified mail or chasing returned documents.</p>
  </div>

  <h2>Workforce Management</h2>

  <div class="feature-block">
    <p><span class="feature-name">Employee Directory &amp; Bulk Import</span> &mdash; Centralized employee records with CSV bulk upload, batch creation, Google Workspace and Slack account provisioning for new hires. For a 900-person, multi-plant workforce with production floor, maintenance, warehouse, and office populations, bulk import eliminates the manual entry bottleneck when bringing a new shift or facility online. A single HRIS export can populate the entire directory, trigger onboarding task assignments by department and role, and provision system access — all in one operation.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Onboarding</span> &mdash; Task-based onboarding templates organized by role and shift. Supports OSHA-mandated pre-floor training workflows (HazCom, LOTO, PPE, machine-specific orientation) as well as office and supervisory onboarding. Progress analytics with funnel metrics, bottleneck identification, and completion tracking. For a plant that onboards production floor employees in cohorts, the system can enforce a gate — no badge access or machine assignment until OSHA pre-floor training tasks are marked complete and verified — reducing both OSHA citation risk and workers' comp exposure from undertrained new hires. Completion dashboards give safety managers a real-time view of training status across all shifts without pulling reports from multiple systems.</p>
  </div>

  <h2>Agentic Document Workspace (Matcha Work)</h2>

  <div class="feature-block">
    <p>Chat-driven document creation with threading, iterative drafts, and internal data search mode. Supports OSHA written program drafting, ER case memos, onboarding plans, handbooks, and policies.</p>
    <p><span class="feature-name">Chat with Your Data</span> &mdash; Ask questions directly against your employee records, incident logs, compliance requirements, and ER cases. Surface patterns, pull ad-hoc reports, and get answers without exporting to spreadsheets. A safety manager can ask "which production line has the highest rate of ergonomic incidents in the past six months" and receive a cited, filterable answer in seconds rather than building a pivot table. HR business partners can query ER case data by supervisor to spot patterns of inconsistent discipline before they become a class action.</p>
    <p><span class="feature-name">Chain of Reasoning Compliance Querying</span> &mdash; Multi-step compliance analysis that walks through regulatory logic step by step&mdash;citing sources, applying preemption rules, and surfacing gaps&mdash;before returning a final answer. Designed for complex federal/state interactions where a single lookup is not enough. For a South Carolina manufacturer, this means asking whether the state-plan OSHA PSM standard applies to a rubber vulcanization process and what it requires beyond the federal baseline — and receiving a step-by-step analysis with CFR and SC regulation citations rather than a $400/hour outside consultant call. <strong>Monthly usage credits included.</strong></p>
  </div>

</div>

<!-- PAGE 4: IMPLEMENTATION + TERMS -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Implementation &amp; Terms</div>
  </div>

  <h1>Implementation Timeline</h1>
  <p>Total duration: 6&ndash;8 weeks. Your dedicated Customer Success Manager guides every phase.</p>

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
        <td class="cost">$3,500</td>
        <td>Organizational mapping, HRIS audit, shift structure inventory, regulatory gap analysis &mdash; audit existing OSHA written programs (HazCom, LOTO, Respiratory Protection, Hearing Conservation, Benzene/Butadiene exposure programs), incident log history, state-plan compliance status across active jurisdictions, and NLRA-related policy documentation</td>
      </tr>
      <tr>
        <td class="phase">Configuration &amp; Templating</td>
        <td>Weeks 3&ndash;4</td>
        <td class="cost">$3,500</td>
        <td>Jurisdiction setup (federal + multi-state OSHA for all active locations), compliance baseline scan, build role-specific onboarding templates (production floor, maintenance, quality, warehouse, supervisory), OSHA pre-floor training workflows, NLRA-compliant policy templates, handbook ingestion</td>
      </tr>
      <tr>
        <td class="phase">Data Migration &amp; Manual Run</td>
        <td>Weeks 5&ndash;6</td>
        <td class="cost">$2,500</td>
        <td>Employee data import, OSHA 300 log migration, historical incident records, policy document ingestion, run first onboarding cohort manually using templates to validate completeness</td>
      </tr>
      <tr>
        <td class="phase">UAT &amp; Automation</td>
        <td>Week 7</td>
        <td class="cost">$1,000</td>
        <td>Admin and supervisor training, user acceptance testing, convert validated manual workflows to automated ingestion pipelines</td>
      </tr>
      <tr>
        <td class="phase">Go-Live</td>
        <td>Week 8</td>
        <td class="cost">$1,000</td>
        <td>Production cutover, CSM handoff, post-launch monitoring</td>
      </tr>
    </tbody>
  </table>

  <h1>Contract Terms</h1>

  <ul class="terms-list">
    <li><span class="term-label">Initial Term</span> 12 months from go-live date</li>
    <li><span class="term-label">Price Lock</span> PEPM rate of $11.00 locked for the initial 12-month term</li>
    <li><span class="term-label">Partner Rate</span> $9.50 PEPM available with quarterly video insights, anonymized case study &amp; data sharing, logo rights, public review within 90 days, and annual prepayment or 2-year term</li>
    <li><span class="term-label">Data Security</span> Encrypted in transit (TLS/SSL enforced) and at rest</li>
    <li><span class="term-label">Auto-Renewal</span> Automatic 12-month renewal periods</li>
    <li><span class="term-label">Opt-Out Notice</span> 60-day written notice required before any renewal period</li>
    <li><span class="term-label">Employee True-Up</span> Quarterly adjustment based on active employee headcount</li>
    <li><span class="term-label">Matcha Work Credits</span> Monthly credits included</li>
    <li><span class="term-label">Dedicated CSM</span> Assigned at contract signing through go-live and beyond</li>
    <li><span class="term-label">Value Validation</span> 90-day post-go-live review to confirm platform adoption and ROI</li>
    <li><span class="term-label">Renewal Pricing</span> May adjust with 60-day written notice prior to renewal</li>
  </ul>

</div>

<!-- PAGE 5: ROI + SIGNATURES -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">ROI &amp; Support</div>
  </div>

  <h1>Return on Investment</h1>

  <p style="margin-bottom: 14px;">Manufacturing employers carry a disproportionate OSHA and employment relations burden. Rubber and plastics manufacturing (NAICS 3262) runs a Total Recordable Incident Rate nearly double the all-industry average, EEOC charges in manufacturing have trended upward as workforces have grown, and the DOL recovered <strong>$36 million in back wages from manufacturing employers in FY2025</strong>&mdash;with overtime and shift differential violations driving the majority of claims. For employers in active labor relations environments, the cost of a single poorly-documented termination can exceed the annual platform cost many times over.</p>

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
        <td style="text-align:right">$105,000/yr</td>
        <td style="text-align:right"><strong>$63,000</strong></td>
      </tr>
      <tr>
        <td>ER cases sent to outside counsel (4/yr)</td>
        <td style="text-align:right">$72,000/yr</td>
        <td style="text-align:right"><strong>$50,000</strong></td>
      </tr>
      <tr>
        <td>HR staff time on compliance tasks</td>
        <td style="text-align:right">$120,000/yr</td>
        <td style="text-align:right"><strong>$60,000</strong></td>
      </tr>
      <tr>
        <td>Handbook &amp; policy legal review</td>
        <td style="text-align:right">$10,000/yr</td>
        <td style="text-align:right"><strong>$8,500</strong></td>
      </tr>
      <tr>
        <td>OSHA incident admin &amp; reporting</td>
        <td style="text-align:right">$22,000/yr</td>
        <td style="text-align:right"><strong>$16,500</strong></td>
      </tr>
      <tr>
        <td>Compliance training &amp; certification tracking</td>
        <td style="text-align:right">$14,000/yr</td>
        <td style="text-align:right"><strong>$10,000</strong></td>
      </tr>
      <tr style="background:#f5f5f7;">
        <td><strong>Annual hard savings</strong></td>
        <td></td>
        <td style="text-align:right"><strong>${HARD_SAVINGS:,.0f}</strong></td>
      </tr>
    </tbody>
  </table>

  <p style="font-size:9pt; color:#6b7280; margin-top:8px;">Savings driven by ER Copilot handling employment relations investigations internally, Pre-Termination Intelligence reducing exposure in a high-scrutiny labor environment, the Compliance Engine automating multi-state and federal OSHA monitoring, and Incident Reports eliminating manual OSHA 300/300A log preparation.</p>

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
        <td>Platform cost</td>
        <td style="text-align:right">${ANNUAL:,.0f}</td>
        <td style="text-align:right">${ANNUAL:,.0f}</td>
        <td style="text-align:right">${ANNUAL:,.0f}</td>
        <td style="text-align:right">${ANNUAL*3:,.0f}</td>
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
        <td style="text-align:right"><strong>${ANNUAL:,.0f}</strong></td>
        <td style="text-align:right"><strong>${ANNUAL:,.0f}</strong></td>
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
    Year 1 ROI: {ROI_MULTIPLE:.1f}&times; &middot; Platform pays for itself by month 6 &middot; 3-year net savings: ${THREE_YEAR_NET:,.0f}
  </div>

  <h1 style="margin-top: 28px;">Dedicated Support</h1>

  <ul>
    <li><strong>Customer Success Manager</strong> assigned at contract signing through go-live and beyond</li>
    <li>Admin and supervisor training sessions included in implementation</li>
    <li>Ongoing CSM check-ins post go-live</li>
    <li>Platform support for configuration changes, headcount adjustments, and feature adoption</li>
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
    This proposal is valid for 30 days from {TODAY}. Pricing is based on the employee count provided and subject to quarterly true-up.
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
