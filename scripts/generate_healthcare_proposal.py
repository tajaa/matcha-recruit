#!/usr/bin/env python3
"""Generate a professional PDF deal proposal for a healthcare client."""

import os
from datetime import date
from weasyprint import HTML

OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = "v2"
OUTPUT_PATH = os.path.join(OUTPUT_DIR, f"Matcha_Healthcare_Proposal_{VERSION}.pdf")

# ── Config ──────────────────────────────────────────────────────────────────
CLIENT_NAME = "Healthcare Institute"
EMPLOYEE_COUNT = 650
PEPM = 9.00
IMPL_FEE = 15_000
MONTHLY = PEPM * EMPLOYEE_COUNT
ANNUAL = MONTHLY * 12
YEAR1_TCV = ANNUAL + IMPL_FEE
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
    background: linear-gradient(165deg, #064e3b 0%, #065f46 40%, #047857 100%);
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
    border-bottom: 2px solid #064e3b;
    padding-bottom: 10px;
    margin-bottom: 32px;
  }}

  .page-header-logo {{
    font-size: 11pt;
    font-weight: 700;
    color: #064e3b;
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
    color: #064e3b;
    margin-bottom: 18px;
    letter-spacing: -0.3px;
  }}

  h2 {{
    font-size: 13pt;
    font-weight: 700;
    color: #064e3b;
    margin-top: 24px;
    margin-bottom: 10px;
    padding-bottom: 4px;
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
    background: #f0fdf4;
    border-left: 4px solid #064e3b;
    padding: 18px 22px;
    margin-bottom: 24px;
    font-size: 11pt;
    line-height: 1.65;
    color: #1a1a2e;
  }}

  /* ── Pricing Table ──────────────────────────────────────────── */
  .pricing-box {{
    border: 2px solid #064e3b;
    border-radius: 6px;
    overflow: hidden;
    margin: 16px 0 20px 0;
  }}

  .pricing-box table {{
    width: 100%;
    border-collapse: collapse;
  }}

  .pricing-box th {{
    background: #064e3b;
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
    background: #f0fdf4;
    font-weight: 700;
    font-size: 11.5pt;
    border-top: 2px solid #064e3b;
  }}

  .pricing-box .amount {{
    text-align: right;
    font-variant-numeric: tabular-nums;
    font-weight: 600;
  }}

  .pricing-note {{
    font-size: 9pt;
    color: #6b7280;
    margin-top: 8px;
    font-style: italic;
  }}

  /* ── Feature Lists ──────────────────────────────────────────── */
  .feature-block {{
    margin-bottom: 14px;
  }}

  .feature-block p {{
    margin-bottom: 4px;
    padding-left: 2px;
  }}

  .feature-name {{
    font-weight: 700;
    color: #064e3b;
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
    background: #064e3b;
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
    color: #064e3b;
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
    color: #064e3b;
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
    background: #064e3b;
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
    background: #f0fdf4;
    border: 1px solid #064e3b;
    border-radius: 4px;
    padding: 14px 18px;
    margin-top: 12px;
    text-align: center;
    font-size: 12pt;
    font-weight: 700;
    color: #064e3b;
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
    <div class="logo-sub">Recruiting &amp; HR Platform</div>
  </div>

  <div class="cover-middle">
    <div class="cover-title">
      Platform<br>
      <strong>Service Proposal</strong>
    </div>
    <div class="cover-divider"></div>
    <div class="cover-meta">
      Prepared for <strong>{CLIENT_NAME}</strong><br>
      {EMPLOYEE_COUNT} Employees &middot; Full Platform Access<br>
      {TODAY}
    </div>
  </div>

  <div class="cover-bottom">
    <div class="cover-footer">
      Confidential &mdash; This document contains proprietary pricing and is intended solely for the named recipient.
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
    Matcha is an AI-powered HR and compliance platform built for multi-location organizations in regulated industries. For healthcare employers managing complex jurisdiction requirements, credentialing, incident tracking, and workforce compliance, Matcha consolidates fragmented HR operations into a single platform&mdash;reducing legal exposure, eliminating manual tracking, and delivering real-time compliance visibility across every facility.
  </div>

  <h1>Investment Summary</h1>

  <div class="pricing-box">
    <table>
      <thead>
        <tr>
          <th>Line Item</th>
          <th style="text-align:right">Amount</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>Per Employee Per Month (PEPM) &times; {EMPLOYEE_COUNT} employees</td>
          <td class="amount">${PEPM:.2f}</td>
        </tr>
        <tr>
          <td>Monthly Platform Cost</td>
          <td class="amount">${MONTHLY:,.2f}</td>
        </tr>
        <tr>
          <td>Annual Platform Cost (12 months)</td>
          <td class="amount">${ANNUAL:,.2f}</td>
        </tr>
        <tr>
          <td>One-Time Implementation &amp; Onboarding</td>
          <td class="amount">${IMPL_FEE:,.2f}</td>
        </tr>
        <tr class="total-row">
          <td>Year 1 Total Contract Value</td>
          <td class="amount">${YEAR1_TCV:,.2f}</td>
        </tr>
      </tbody>
    </table>
  </div>

  <p class="pricing-note">
    All platform features included at the flat PEPM rate&mdash;no module upsells or per-feature charges.
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
    <p><span class="feature-name">Compliance Engine</span> &mdash; AI-powered jurisdiction research across federal, state, and local levels. Multi-location support with preemption rule analysis. Automated wage and hour monitoring. Tiered data approach: structured requirements, curated repository, and AI-generated research for emerging regulations.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Policies &amp; Handbooks</span> &mdash; AI-generated policy documents tailored to specific jurisdictions. Electronic signature collection with audit trails. Auto-research fills jurisdiction-specific topics during handbook creation.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">I-9 / E-Verify</span> &mdash; Employment eligibility verification tracking, document management, expiration monitoring, and compliance summary dashboard.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">COBRA Administration</span> &mdash; Qualifying event tracking with auto-computed deadlines for employer notice, administrator notification, election periods, and continuation coverage.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Training &amp; Certifications</span> &mdash; Requirement creation, bulk assignment, expiration monitoring, and compliance dashboard with completion rates by requirement.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Legislative Tracker</span> &mdash; AI-powered monitoring of regulatory changes across jurisdictions with pattern detection for coordinated legislative activity.</p>
  </div>

  <h2>Workforce Management</h2>

  <div class="feature-block">
    <p><span class="feature-name">Employee Directory &amp; Bulk Import</span> &mdash; Centralized employee records with CSV bulk upload, batch creation, Google Workspace and Slack account provisioning for new hires.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Onboarding</span> &mdash; Task-based onboarding templates organized by category. Progress analytics with funnel metrics, bottleneck identification, and completion tracking across the organization.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">PTO &amp; Leave Management</span> &mdash; FMLA eligibility tracking, state-level Paid Family &amp; Medical Leave (PFML) support, hours-based accrual tracking, and self-service request workflows.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Offer Letters</span> &mdash; AI-powered salary guidance by role and market. Customizable templates with company branding and logo. Magic-link electronic signing for candidates. Multi-round salary range negotiation. PDF generation.</p>
  </div>

</div>

<!-- ═══════════════════════════════════════════════════════════════════════ -->
<!-- PAGE 4: PLATFORM CAPABILITIES (2 of 2)                                -->
<!-- ═══════════════════════════════════════════════════════════════════════ -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha</div>
    <div class="page-header-right">Platform Capabilities</div>
  </div>

  <h2>Investigations &amp; Risk</h2>

  <div class="feature-block">
    <p><span class="feature-name">IR Incidents</span> &mdash; AI-categorized safety and behavioral incident reporting. OSHA 300 and 300A log generation with CSV export. Anonymous reporting support. Trend analytics and pattern detection across locations.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ER Copilot</span> &mdash; Employment relations case management with AI-powered document analysis. Timeline construction and discrepancy detection. Encrypted PDF report generation. Secure shared export links for external counsel.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">ADA Accommodations</span> &mdash; Interactive process workflow management with AI-powered accommodation suggestions, undue hardship assessment, and job function analysis.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Pre-Termination Intelligence</span> &mdash; 9-dimension AI risk assessment scanning legal, compliance, and organizational factors before separation decisions. AI-generated narrative memo suitable for counsel review.</p>
  </div>

  <div class="feature-block">
    <p><span class="feature-name">Separation Agreements</span> &mdash; OWBPA-compliant agreement generation with proper consideration periods (21/45 day) and revocation window tracking. Group layoff disclosure support.</p>
  </div>

  <h2>Analytics &amp; Culture</h2>

  <div class="feature-block">
    <p><span class="feature-name">Risk Assessment</span> &mdash; Monte Carlo simulation-based organizational risk modeling. Cohort heat maps across departments, locations, and tenure. Anomaly detection. Executive-ready report generation with benchmarking against industry peers.</p>
  </div>

  <h2>AI Document Workspace (Matcha Work)</h2>

  <div class="feature-block">
    <p>Chat-driven document creation with threading, iterative drafts, and internal data search mode for cross-referencing organizational information. Supports offer letters, reviews, workbooks, onboarding plans, presentations, handbooks, and policies. <strong>$75/month usage credit included.</strong></p>
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
        <td class="phase">Discovery</td>
        <td>Weeks 1&ndash;2</td>
        <td class="cost">$3,000</td>
        <td>Organizational mapping, HRIS audit, location inventory, compliance gap analysis</td>
      </tr>
      <tr>
        <td class="phase">Configuration</td>
        <td>Weeks 3&ndash;4</td>
        <td class="cost">$4,500</td>
        <td>Location setup, compliance baseline scan, leave policy configuration, existing handbook ingestion &amp; compliance review</td>
      </tr>
      <tr>
        <td class="phase">Data Migration</td>
        <td>Weeks 5&ndash;6</td>
        <td class="cost">$3,750</td>
        <td>Employee data import, historical records migration, existing handbook and policy ingestion</td>
      </tr>
      <tr>
        <td class="phase">UAT &amp; Training</td>
        <td>Week 7</td>
        <td class="cost">$2,250</td>
        <td>Admin and manager training sessions, user acceptance testing, parallel run</td>
      </tr>
      <tr>
        <td class="phase">Go-Live</td>
        <td>Week 8</td>
        <td class="cost">$1,500</td>
        <td>Production cutover, CSM handoff, post-launch monitoring</td>
      </tr>
    </tbody>
  </table>

  <h1>Contract Terms</h1>

  <ul class="terms-list">
    <li><span class="term-label">Initial Term</span> 12 months from go-live date</li>
    <li><span class="term-label">Price Lock</span> PEPM rate of $9.00 locked for the initial 12-month term</li>
    <li><span class="term-label">Auto-Renewal</span> Automatic 12-month renewal periods</li>
    <li><span class="term-label">Opt-Out Notice</span> 60-day written notice required before any renewal period</li>
    <li><span class="term-label">Employee True-Up</span> Quarterly adjustment based on active employee headcount</li>
    <li><span class="term-label">Matcha Work Credits</span> $75/month included; overage at $0.10/1K tokens</li>
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

  <table class="roi-table">
    <thead>
      <tr>
        <th>Current Cost Center</th>
        <th>Without Matcha</th>
        <th>With Matcha</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Outside employment counsel</td>
        <td>$150,000&ndash;$350,000+/yr</td>
        <td>Reduced 40&ndash;60% via AI-guided compliance and ER Copilot</td>
      </tr>
      <tr>
        <td>Manual compliance tracking</td>
        <td>$85,000&ndash;$170,000/yr (1&ndash;2 FTE)</td>
        <td>Automated, real-time monitoring</td>
      </tr>
      <tr>
        <td>Audit remediation</td>
        <td>$10,000&ndash;$100,000+ per event</td>
        <td>Proactive detection reduces exposure</td>
      </tr>
      <tr>
        <td>EEOC/DOL claim defense</td>
        <td>$15,000&ndash;$50,000 per claim</td>
        <td>Pre-termination intelligence reduces claim risk</td>
      </tr>
      <tr>
        <td>Multi-location handbook maintenance</td>
        <td>$5,000&ndash;$20,000/yr (legal review)</td>
        <td>AI-generated, jurisdiction-aware, auto-updated</td>
      </tr>
      <tr>
        <td>Incident tracking &amp; OSHA reporting</td>
        <td>Manual, error-prone</td>
        <td>Automated categorization and log generation</td>
      </tr>
    </tbody>
  </table>

  <div class="roi-highlight">
    Estimated annual risk reduction: $200,000&ndash;$500,000+
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
