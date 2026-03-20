#!/usr/bin/env python3
"""Generate a professional PDF deal proposal for 360 Behavioral Life Sciences."""

import os
from datetime import date
from weasyprint import HTML

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deals", "behavioral")
VERSION = "v1"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, f"Matcha_360Behavioral_Proposal_{VERSION}.pdf")

# ── Config ──────────────────────────────────────────────────────────────────
CLIENT_NAME = "360 Behavioral Life Sciences"
EMPLOYEE_COUNT = 2600
FT_COUNT = 600
PT_COUNT = 2000
LIST_PEPM = 14.00
PEPM = 11.00
DISCOUNT_AMT = LIST_PEPM - PEPM
PARTNER_PEPM = 9.50
IMPL_FEE = 20_000
MONTHLY = PEPM * EMPLOYEE_COUNT
ANNUAL = MONTHLY * 12
YEAR1_TCV = ANNUAL + IMPL_FEE
PARTNER_MONTHLY = PARTNER_PEPM * EMPLOYEE_COUNT
PARTNER_ANNUAL = PARTNER_MONTHLY * 12
PARTNER_YEAR1_TCV = PARTNER_ANNUAL + IMPL_FEE
TODAY = date.today().strftime("%B %d, %Y")

# ROI numbers
HARD_SAVINGS = 408_500
RISK_REDUCTION = 100_000
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

  .workforce-note {{
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    padding: 10px 16px;
    margin-bottom: 16px;
    font-size: 9.5pt;
    color: #374151;
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
      {EMPLOYEE_COUNT:,} Employees &middot; Full Platform Access<br>
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
    Matcha is an agentic workforce risk management platform built for multi-location behavioral health organizations managing high-turnover, clinically licensed workforces across complex regulatory environments. From HIPAA compliance monitoring and practitioner credential tracking to pre-termination risk scoring and employment relations case management, Matcha consolidates fragmented HR operations into a single platform&mdash;reducing regulatory exposure, eliminating manual tracking, and delivering real-time risk visibility across every care site. Every requirement is sourced from government databases and regulatory texts, with citation links and verification timestamps so your team can trust the data without independent research.
  </div>

  <div class="workforce-note">
    <strong>Workforce composition:</strong> {FT_COUNT} benefit-eligible full-time employees + {PT_COUNT:,} part-time employees = {EMPLOYEE_COUNT:,} total &middot; Pricing applies uniformly across all active employees at the flat PEPM rate.
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
          <td><strong>Discounted PEPM &times; {EMPLOYEE_COUNT:,} employees</strong></td>
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
    <p><span class="feature-name">Compliance Engine</span> &mdash; Agentic jurisdiction research across federal, state, and local levels. Covers HIPAA workforce requirements, state behavioral health licensing mandates, Medicaid/Medicare provider compliance, mandated reporter obligations, and applicable employment law across all operating locations. Multi-location support with preemption rule analysis. For a multi-state behavioral health organization, this means a single dashboard that tracks each state's licensed professional counselor scope-of-practice requirements, Medicaid managed care workforce credentialing standards, and applicable employment law simultaneously — without HR manually monitoring each state agency's website. When a state updates its mandated reporter training recertification interval or Medicaid reimbursement eligibility criteria for LCSW-supervised staff, the engine surfaces the change mapped to the affected facilities before the next licensing renewal cycle.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Policies &amp; Handbooks</span> &mdash; Agentic policy documents tailored to behavioral health environments and applicable jurisdictions. Covers HIPAA workforce policies, patient safety and rights, mandated reporter obligations, crisis intervention protocols, and employment policies for mixed full-time and part-time workforces. Electronic signature collection with audit trails. In a behavioral health setting where staff routinely handle Protected Health Information across multiple care settings, the electronic acknowledgment trail creates the documented HIPAA workforce training record that HHS Office for Civil Rights auditors expect during a HIPAA investigation — without HR chasing down paper sign-off sheets. Because Medicaid accreditation surveys often require demonstration of written crisis intervention policies acknowledged by all clinical staff, the platform's bulk acknowledgment workflow ensures no one falls through the cracks when a policy is updated.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Legislative Tracker</span> &mdash; Agentic monitoring of regulatory changes across jurisdictions including state behavioral health licensing updates, Medicaid reimbursement policy changes, and employment law developments with pattern detection for coordinated legislative activity. For a behavioral health organization operating in multiple states, this means automatic alerts when states update supervision hour requirements for licensure-track clinicians or when Medicaid managed care contracts revise credentialing timelines — changes that directly affect who can be billed for services and at what rate. Pattern detection also flags when multiple states simultaneously introduce legislation expanding mental health parity enforcement or telehealth prescribing authority, giving clinical operations teams lead time to adapt staffing models before the laws take effect.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Risk Assessment</span> &mdash; Multi-method organizational risk modeling: 5-dimension live risk scoring (compliance, incidents, ER cases, workforce, legislative), Monte Carlo simulation across 10,000 iterations to produce probability distributions of annual loss exposure, statistical anomaly detection on time-series metrics, and NAICS-benchmarked peer comparison sourced from BLS, OSHA, EEOC, and QCEW. Executive-ready reports with cohort heat maps across departments, locations, and tenure. Behavioral health organizations consistently show elevated workforce risk scores due to high turnover, patient aggression incidents, and the emotional burnout that drives FMLA and ADA accommodation volume — this platform benchmarks those metrics against the NAICS 6222 (psychiatric and substance abuse hospitals) and 6241 (individual and family services) peer groups so leadership understands whether their risk profile is sector-normal or an outlier requiring intervention. Monte Carlo projections translate the risk score into a dollar range that can inform employment practices liability insurance coverage decisions and board-level risk disclosures.</p>
  </div>

  <h2>Investigations &amp; Risk</h2>

  <div class="feature-block">
    <p><span class="feature-name">Incident Reports</span> &mdash; Agentic safety and behavioral incident reporting covering patient-on-worker violence, workplace injuries, HIPAA breaches, and behavioral incidents. OSHA 300 and 300A log generation with CSV export. Anonymous reporting support. Trend analytics and pattern detection across care sites — critical for organizations where worker injury rates from patient aggression exceed general industry averages. The intake workflow includes OSHA 300 recordability determination at the point of report, so staff and supervisors do not need to interpret the standard themselves — a particularly important safeguard when the reporting employee is a licensed clinician who is excellent at patient care documentation but unfamiliar with OSHA's first-aid versus medical treatment distinction. Trend analytics can also surface whether patient aggression incidents cluster by program type, shift, or individual worker — enabling proactive de-escalation training interventions rather than responding incident by incident.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ER Copilot</span> &mdash; Employment relations case management with agentic document analysis. Timeline construction and discrepancy detection. Encrypted PDF report generation. Secure shared export links for external counsel. Designed for high-volume ER environments driven by elevated turnover and the emotionally complex nature of behavioral health work. In behavioral health, ER cases frequently involve clinical staff accused of boundary violations or therapeutic misconduct — matters where the documentary record must be both thorough and legally privileged, making the encrypted case workspace and counsel export link particularly critical. The timeline construction feature is especially valuable in these cases because it surfaces gaps and inconsistencies in supervisor documentation before those gaps appear in a state licensing board complaint or plaintiff's attorney deposition.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ADA Accommodations</span> &mdash; Interactive process workflow management with agentic accommodation suggestions, undue hardship assessment, and job function analysis. Particularly relevant in behavioral health where accommodation requests from staff intersect with patient care requirements. A clinician requesting an accommodation for their own mental health condition creates a fact pattern that is both legally sensitive and operationally complex — the platform guides the interactive process without exposing confidential medical information to supervisors who have no need to know the underlying diagnosis. When accommodation is denied because it would require eliminating an essential patient-facing function, the undue hardship documentation provides the specific, role-based rationale that the EEOC requires, rather than a vague reference to "operational needs."</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Pre-Termination Intelligence</span> &mdash; 9-dimension agentic risk assessment scanning legal, compliance, and organizational factors before separation decisions. Agentic-generated narrative memo suitable for counsel review. Essential for high-turnover environments where separation volume amplifies the probability of a poorly-documented termination becoming a claim. In behavioral health, the system flags when a proposed termination involves an employee who has filed a patient safety complaint with a state licensing board or reported a HIPAA concern — both protected activities that can support a retaliation claim under state whistleblower statutes or the HIPAA enforcement framework. At scale, this check on every separation decision is the difference between a defensible termination record and a pattern of retaliation claims that a plaintiff's attorney uses to support a class action.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Separation Agreements</span> &mdash; OWBPA-compliant agreement generation with proper consideration periods (21/45 day) and revocation window tracking. Group layoff disclosure support. For a behavioral health organization that frequently restructures programs due to Medicaid contract changes or grant funding cycles, OWBPA-compliant group layoff disclosures are a recurring operational need, not a one-time event — and the platform's automated disclosure generation eliminates the risk of executing an invalid release because someone miscounted the ages in the decisional unit table. Digital delivery and revocation tracking replace the certified mail process that HR teams find most difficult to execute consistently when managing terminations across multiple care sites simultaneously.</p>
  </div>

  <h2>Workforce Management</h2>

  <div class="feature-block">
    <p><span class="feature-name">Employee Directory &amp; Bulk Import</span> &mdash; Centralized employee records supporting large mixed workforces with CSV bulk upload, batch creation, and Google Workspace and Slack account provisioning for new hires. Built to handle the high-volume onboarding and offboarding cycles typical of behavioral health organizations. In a sector where annual turnover rates routinely exceed 30%, a system that can process a cohort of 20 new clinicians in a single bulk import — triggering role-specific onboarding workflows, credential collection tasks, and HIPAA training assignments automatically — is the difference between a functioning HR team and one that is permanently behind on manual data entry. The centralized directory also creates the audit-ready employee record that Medicaid managed care accreditation surveys require when reviewers ask to see documentation of workforce credentialing and supervision status.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Onboarding</span> &mdash; Task-based onboarding templates organized by role and employment type. Supports role-specific workflows for licensed clinicians (LCSW, LPC, LMFT, BCBA, psychologist), case managers, crisis counselors, administrative staff, and part-time clinicians. Credential and license expiration tracking built in. Progress analytics with funnel metrics and completion tracking across all sites. The credential expiration tracking layer is particularly valuable in behavioral health, where a lapsed LCSW license or expired CPR certification can create both patient safety liability and Medicaid billing compliance exposure — the platform proactively surfaces renewal deadlines 90, 60, and 30 days in advance rather than discovering expirations during a payer audit. When a crisis counselor's mandated reporter certification lapses and a reportable event occurs during that window, the gap in the training record becomes a liability; this system closes that gap before it opens.</p>
  </div>

  <h2>Agentic Document Workspace (Matcha Work)</h2>

  <div class="feature-block">
    <p>Chat-driven document creation with threading, iterative drafts, and internal data search mode. Supports ER case memos, HIPAA policy drafting, onboarding plans, handbooks, separation documentation, and compliance research for complex multi-state behavioral health regulatory questions.</p>
    <p><span class="feature-name">Chat with Your Data</span> &mdash; Ask questions directly against your employee records, incident logs, compliance requirements, and ER cases. Surface patterns, pull ad-hoc reports, and get answers without exporting to spreadsheets. A compliance officer can ask "which staff members have patient-aggression incidents in the last 12 months and are also currently in an open ADA accommodation case" and receive an immediately actionable cross-reference — the kind of data correlation that reveals whether aggression-related injuries are concentrated among workers with accommodation needs who may require a different intervention approach. Clinical operations leaders can query onboarding completion status across all sites to identify which programs are most at risk of a Medicaid audit finding due to incomplete training records.</p>
    <p><span class="feature-name">Chain of Reasoning Compliance Querying</span> &mdash; Multi-step compliance analysis that walks through regulatory logic step by step&mdash;citing sources, applying preemption rules, and surfacing gaps&mdash;before returning a final answer. Designed for complex federal/state interactions where a single lookup is not enough. For a multi-state behavioral health organization, this means asking whether a proposed supervision structure for unlicensed mental health practitioners in a new state satisfies both the state's scope-of-practice statute and the applicable Medicaid managed care credentialing standard — and receiving a cited, step-by-step analysis rather than a general answer that leaves the compliance team uncertain. <strong>Monthly usage credits included.</strong></p>
  </div>

</div>

<!-- PAGE 4: IMPLEMENTATION + TERMS -->
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
        <td class="cost">$6,000</td>
        <td>Organizational mapping across all care sites, HRIS audit, location inventory, regulatory gap analysis &mdash; audit HIPAA workforce compliance programs, state practitioner licensing requirements across operating states, mandated reporter training records, credential expiration status, existing onboarding and offboarding documentation</td>
      </tr>
      <tr>
        <td class="phase">Configuration &amp; Templating</td>
        <td>Weeks 3&ndash;4</td>
        <td class="cost">$6,000</td>
        <td>Multi-location jurisdiction setup, compliance baseline scan, build role-specific onboarding templates (licensed clinicians, BCBA, case manager, crisis counselor, admin, part-time clinical staff), credential and license expiration workflows, HIPAA training workflows, mandated reporter workflows, handbook ingestion</td>
      </tr>
      <tr>
        <td class="phase">Data Migration &amp; Manual Run</td>
        <td>Weeks 5&ndash;6</td>
        <td class="cost">$4,500</td>
        <td>Full employee data import for {EMPLOYEE_COUNT:,} employees across both full-time and part-time classifications, historical records migration, policy document ingestion, run first onboarding cohort manually across multiple role types to validate completeness and regulatory alignment</td>
      </tr>
      <tr>
        <td class="phase">UAT &amp; Automation</td>
        <td>Week 7</td>
        <td class="cost">$2,000</td>
        <td>Multi-site admin and manager training, user acceptance testing across role types, convert validated manual workflows to automated ingestion pipelines</td>
      </tr>
      <tr>
        <td class="phase">Go-Live</td>
        <td>Week 8</td>
        <td class="cost">$1,500</td>
        <td>Production cutover, CSM handoff, post-launch monitoring across all sites</td>
      </tr>
    </tbody>
  </table>

  <h1>Contract Terms</h1>

  <ul class="terms-list">
    <li><span class="term-label">Initial Term</span> 12 months from go-live date</li>
    <li><span class="term-label">Price Lock</span> PEPM rate of $11.00 locked for the initial 12-month term</li>
    <li><span class="term-label">Partner Rate</span> $9.50 PEPM available with quarterly video insights, anonymized case study &amp; data sharing, logo rights, public review within 90 days, and annual prepayment or 2-year term</li>
    <li><span class="term-label">Data Security</span> HIPAA-compliant infrastructure with executed BAAs (AWS and Google Cloud); encrypted in transit (TLS/SSL enforced) and at rest</li>
    <li><span class="term-label">Auto-Renewal</span> Automatic 12-month renewal periods</li>
    <li><span class="term-label">Opt-Out Notice</span> 60-day written notice required before any renewal period</li>
    <li><span class="term-label">Employee True-Up</span> Quarterly adjustment based on active employee headcount across all employment types</li>
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

  <p style="margin-bottom: 14px;">Behavioral health is one of the highest-risk employment environments in the country. Annual staff turnover rates of 30&ndash;50% mean HR teams are in a near-constant cycle of onboarding, offboarding, and credential re-verification. Patient-on-worker violence rates in behavioral health settings are among the highest of any sector. EEOC charge rates in health services run at <strong>2&times; the national average</strong>, and multi-state licensing complexity creates compliance exposure that scales with every new care site. The DOL recovered <strong>$53 million in back wages from healthcare employers in FY2025</strong>, with behavioral health operators increasingly targeted for wage and hour violations tied to part-time scheduling and overtime practices.</p>

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
        <td style="text-align:right">$180,000/yr</td>
        <td style="text-align:right"><strong>$117,000</strong></td>
      </tr>
      <tr>
        <td>ER cases sent to outside counsel (8/yr)</td>
        <td style="text-align:right">$144,000/yr</td>
        <td style="text-align:right"><strong>$104,000</strong></td>
      </tr>
      <tr>
        <td>HR staff time on compliance tasks</td>
        <td style="text-align:right">$210,000/yr</td>
        <td style="text-align:right"><strong>$115,500</strong></td>
      </tr>
      <tr>
        <td>Handbook &amp; policy legal review</td>
        <td style="text-align:right">$20,000/yr</td>
        <td style="text-align:right"><strong>$17,000</strong></td>
      </tr>
      <tr>
        <td>OSHA &amp; incident admin &amp; reporting</td>
        <td style="text-align:right">$28,000/yr</td>
        <td style="text-align:right"><strong>$22,000</strong></td>
      </tr>
      <tr>
        <td>Compliance training &amp; certification tracking</td>
        <td style="text-align:right">$45,000/yr</td>
        <td style="text-align:right"><strong>$33,000</strong></td>
      </tr>
      <tr style="background:#f5f5f7;">
        <td><strong>Annual hard savings</strong></td>
        <td></td>
        <td style="text-align:right"><strong>${HARD_SAVINGS:,.0f}</strong></td>
      </tr>
    </tbody>
  </table>

  <p style="font-size:9pt; color:#6b7280; margin-top:8px;">Savings driven by ER Copilot eliminating outside counsel fees on routine investigations, Pre-Termination Intelligence reducing claim exposure in a high-turnover environment, the Compliance Engine automating multi-state licensing and HIPAA monitoring, and Incident Reports replacing manual OSHA log preparation across all care sites.</p>

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
    Year 1 ROI: {ROI_MULTIPLE:.1f}&times; &middot; Platform pays for itself by month 9 &middot; 3-year net savings: ${THREE_YEAR_NET:,.0f}
  </div>

  <h1 style="margin-top: 28px;">Dedicated Support</h1>

  <ul>
    <li><strong>Customer Success Manager</strong> assigned at contract signing through go-live and beyond</li>
    <li>Multi-site admin and manager training sessions included in implementation</li>
    <li>Ongoing CSM check-ins post go-live</li>
    <li>Platform support for new site rollouts, headcount changes, and feature adoption</li>
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
