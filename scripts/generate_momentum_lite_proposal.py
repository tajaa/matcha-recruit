#!/usr/bin/env python3
"""Generate the Matcha Lite PDF proposal for Momentum Life Sciences.

Mirrors the CSS shell of generate_momentum_proposal.py (the Platform
proposal) so the Lite deck reads as a sibling document. Content focuses
on what Lite delivers — the companion Platform proposal covers the
fuller scope, so this deck does not enumerate what's omitted.
"""

import os
from weasyprint import HTML

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "deals", "momentum")
VERSION = "v1"
HTML_OUT = os.path.join(OUTPUT_DIR, f"Matcha_Momentum_Lite_Proposal_{VERSION}.html")
PDF_OUT = os.path.join(OUTPUT_DIR, f"Matcha_Momentum_Lite_Proposal_{VERSION}.pdf")

CLIENT_NAME = "Momentum Life Sciences"
EMPLOYEE_COUNT = 200
MONTHLY = 2_000   # ceil(200/10) * $100
ANNUAL = MONTHLY * 12
TODAY = "May 14, 2026"

HTML_CONTENT = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{ size: letter; margin: 0; }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #1a1a2e;
    font-size: 10.5pt;
    line-height: 1.55;
  }}

  /* ── Cover ─────────────────────────────────────────────── */
  .cover {{
    page-break-after: always;
    height: 100vh;
    display: flex; flex-direction: column; justify-content: space-between;
    background: linear-gradient(165deg, #1a1a2e 0%, #2d2d3f 40%, #3d3d52 100%);
    color: white; padding: 0; position: relative; overflow: hidden;
  }}
  .cover-accent {{
    position: absolute; top: -120px; right: -120px; width: 500px; height: 500px;
    border-radius: 50%; background: rgba(255,255,255,0.04);
  }}
  .cover-accent-2 {{
    position: absolute; bottom: -80px; left: -80px; width: 350px; height: 350px;
    border-radius: 50%; background: rgba(255,255,255,0.03);
  }}
  .cover-top {{ padding: 60px 65px 0 65px; position: relative; z-index: 1; }}
  .logo-text {{ font-size: 32pt; font-weight: 700; letter-spacing: -0.5px; }}
  .logo-sub {{
    font-size: 10pt; letter-spacing: 3px; text-transform: uppercase;
    opacity: 0.7; margin-top: 4px;
  }}
  .cover-middle {{ padding: 0 65px; position: relative; z-index: 1; }}
  .cover-eyebrow {{
    display: inline-block; padding: 4px 10px; border: 1px solid rgba(255,255,255,0.35);
    border-radius: 999px; font-size: 8.5pt; letter-spacing: 2px; text-transform: uppercase;
    opacity: 0.85; margin-bottom: 18px;
  }}
  .cover-title {{
    font-size: 28pt; font-weight: 300; line-height: 1.2; margin-bottom: 16px;
    letter-spacing: -0.3px;
  }}
  .cover-title strong {{ font-weight: 700; }}
  .cover-divider {{ width: 60px; height: 3px; background: rgba(255,255,255,0.5); margin: 24px 0; }}
  .cover-meta {{ font-size: 11pt; opacity: 0.85; line-height: 1.8; }}
  .cover-bottom {{ padding: 0 65px 50px 65px; position: relative; z-index: 1; }}
  .cover-footer {{
    font-size: 8.5pt; opacity: 0.5; border-top: 1px solid rgba(255,255,255,0.15);
    padding-top: 16px;
  }}

  /* ── Content pages ──────────────────────────────────────── */
  .page {{ page-break-after: always; padding: 55px 60px; position: relative; }}
  .page:last-child {{ page-break-after: avoid; }}
  .page-header {{
    display: flex; justify-content: space-between; align-items: center;
    border-bottom: 2px solid #1a1a2e; padding-bottom: 10px; margin-bottom: 28px;
  }}
  .page-header-logo {{ font-size: 11pt; font-weight: 700; color: #1a1a2e; letter-spacing: -0.3px; }}
  .page-header-right {{ font-size: 8pt; color: #6b7280; text-transform: uppercase; letter-spacing: 1.5px; }}

  h1 {{ font-size: 20pt; font-weight: 700; color: #1a1a2e; margin-top: 4px; margin-bottom: 18px; letter-spacing: -0.3px; }}
  h2 {{
    font-size: 13pt; font-weight: 700; color: #1a1a2e;
    margin-top: 24px; margin-bottom: 12px; padding-bottom: 6px;
    border-bottom: 1px solid #d1d5db;
  }}
  h3 {{ font-size: 11pt; font-weight: 700; color: #1a1a2e; margin-top: 14px; margin-bottom: 6px; }}
  p {{ margin-bottom: 9px; }}

  .executive-summary {{
    background: #f5f5f7; border-left: 4px solid #1a1a2e;
    padding: 16px 20px; margin-bottom: 20px;
    font-size: 10.5pt; line-height: 1.6; color: #1a1a2e;
  }}

  /* ── Pricing ────────────────────────────────────────────── */
  .pricing-box {{
    border: 1px solid #d1d5db; border-radius: 6px; overflow: hidden;
    margin: 8px 0 18px 0;
  }}
  .pricing-box table {{ width: 100%; border-collapse: collapse; }}
  .pricing-box th {{
    background: #1a1a2e; color: white; padding: 10px 18px; text-align: left;
    font-size: 9.5pt; text-transform: uppercase; letter-spacing: 1px;
  }}
  .pricing-box th.amount, .pricing-box td.amount {{ text-align: right; }}
  .pricing-box td {{ padding: 11px 18px; border-bottom: 1px solid #e5e7eb; font-size: 10.5pt; }}
  .pricing-box tr:last-child td {{ border-bottom: none; }}
  .pricing-box .total-row td {{
    background: #f5f5f7; font-weight: 700; font-size: 11.5pt;
    border-top: 2px solid #1a1a2e; padding: 13px 18px;
  }}
  .pricing-box .amount {{
    text-align: right; font-variant-numeric: tabular-nums; font-weight: 600;
  }}
  .pricing-note {{
    font-size: 9pt; color: #6b7280; margin-top: 10px; margin-bottom: 6px;
    font-style: italic;
  }}

  /* ── Lists ──────────────────────────────────────────────── */
  ul {{ padding-left: 20px; margin-bottom: 10px; }}
  li {{ margin-bottom: 4px; }}
  .feature-block {{ margin-bottom: 14px; }}
  .feature-name {{ font-weight: 700; color: #1a1a2e; }}

  /* ── Onboarding steps ───────────────────────────────────── */
  .step {{
    margin-bottom: 12px; padding-left: 36px; position: relative;
  }}
  .step-number {{
    position: absolute; left: 0; top: 0; width: 26px; height: 26px;
    background: #1a1a2e; color: white; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 11pt; font-weight: 700;
  }}
  .step-title {{ font-weight: 700; color: #1a1a2e; margin-bottom: 2px; }}

  /* ── Contract terms ─────────────────────────────────────── */
  .terms-list {{ list-style: none; padding: 0; }}
  .terms-list li {{
    padding: 7px 0; border-bottom: 1px solid #f3f4f6; display: flex; gap: 12px;
  }}
  .terms-list li:last-child {{ border-bottom: none; }}
  .term-label {{ font-weight: 700; color: #1a1a2e; min-width: 200px; flex-shrink: 0; }}

  /* ── Signature ──────────────────────────────────────────── */
  .signature-section {{ margin-top: 32px; display: flex; gap: 48px; }}
  .sig-block {{ flex: 1; }}
  .sig-line {{
    border-bottom: 1px solid #1a1a2e; margin-bottom: 4px; height: 38px;
  }}
  .sig-label {{ font-size: 9pt; color: #6b7280; }}
  .footer-note {{
    margin-top: 26px; padding-top: 14px; border-top: 1px solid #e5e7eb;
    font-size: 8pt; color: #9ca3af; text-align: center; line-height: 1.5;
  }}
</style>
</head>
<body>

<!-- ─────── COVER ─────── -->
<div class="cover">
  <div class="cover-accent"></div>
  <div class="cover-accent-2"></div>
  <div class="cover-top">
    <div class="logo-text">matcha</div>
    <div class="logo-sub">Risk · Compliance · Employee Relations</div>
  </div>
  <div class="cover-middle">
    <div class="cover-eyebrow">Matcha Lite · Self-Serve Tier</div>
    <div class="cover-title">Service Proposal for<br><strong>{CLIENT_NAME}</strong></div>
    <div class="cover-divider"></div>
    <div class="cover-meta">
      {EMPLOYEE_COUNT} home-office employees<br>
      Incident reporting · Employee records · Progressive discipline<br>
      Prepared {TODAY}
    </div>
  </div>
  <div class="cover-bottom">
    <div class="cover-footer">
      hey-matcha.com &nbsp;·&nbsp; aaron@hey-matcha.com<br>
      Confidential. Pricing intended solely for the named recipient.
    </div>
  </div>
</div>

<!-- ─────── PAGE 1: Executive Summary + Investment ─────── -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha · lite</div>
    <div class="page-header-right">{CLIENT_NAME} · {TODAY}</div>
  </div>

  <h1>Executive Summary</h1>

  <div class="executive-summary">
    Matcha Lite is the self-serve incident-reporting and HR-records bundle from the Matcha platform. Defensible records of safety and behavioral events, a clean employee directory, and progressive discipline workflows &mdash; live in your environment within thirty minutes of subscribing.
  </div>

  <p>For {CLIENT_NAME}, Lite addresses the operational layer first. Every Adverse Event, sponsor protocol deviation, near-miss in a HomeHealth visit, or behavioral incident on the home-office floor lands in a single intake. Anonymous channel available. AI-summarized for triage. OSHA 300 and 300A logs generated automatically.</p>

  <p>Your home-office staff records are unified out of CSV chaos. Your discipline conversations carry a date-stamped paper trail that your eventual outside counsel doesn&rsquo;t have to reconstruct.</p>

  <p>What sits behind every record: AI agents that triage incidents, draft summaries, suggest discipline steps from your prior practice, and surface trend patterns across reports. Your team stops maintaining spreadsheets and starts responding to flagged signals.</p>

  <h2>Investment Summary</h2>
  <p class="pricing-note">Self-serve subscription via Stripe. No implementation fee. No PEPM. No per-jurisdiction billing. Cancel anytime via the billing portal.</p>

  <div class="pricing-box">
    <table>
      <tr>
        <th>Line Item</th>
        <th class="amount">Monthly</th>
        <th class="amount">Annual</th>
      </tr>
      <tr>
        <td>Matcha Lite subscription ({EMPLOYEE_COUNT} employees)</td>
        <td class="amount">${MONTHLY:,}.00</td>
        <td class="amount">${ANNUAL:,}.00</td>
      </tr>
      <tr>
        <td>Implementation / configuration</td>
        <td class="amount">&mdash;</td>
        <td class="amount">Included (self-serve wizard)</td>
      </tr>
      <tr class="total-row">
        <td>Year 1 Total</td>
        <td class="amount">${MONTHLY:,}.00 / mo</td>
        <td class="amount">${ANNUAL:,}.00</td>
      </tr>
    </table>
  </div>

  <p><strong>Pricing rule:</strong> $100 per 10-employee block per month. At {EMPLOYEE_COUNT} employees you are billed for {EMPLOYEE_COUNT // 10} blocks. Adding employees up to the next block triggers the next $100/mo increment at quarterly true-up.</p>
</div>

<!-- ─────── PAGE 2 + 3: What Lite Includes ─────── -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha · lite</div>
    <div class="page-header-right">What&rsquo;s Included</div>
  </div>

  <h1>What Lite Delivers</h1>

  <h2>Incident Reporting</h2>
  <p>The same AI-driven incident intake that powers the Matcha Platform.</p>
  <ul>
    <li><span class="feature-name">Anonymous + named intake.</span> Public per-company report URL (token-gated, single-use) for whistleblower-style submissions. Internal report flow for managers and HR.</li>
    <li><span class="feature-name">AI summary on every incident.</span> Auto-generated narrative, severity classification, witness extraction, and policy-trigger detection.</li>
    <li><span class="feature-name">OSHA 300 / 300A log generation.</span> Recordability evaluated automatically when incident facts are entered. CSV export for your annual posting.</li>
    <li><span class="feature-name">AE and protocol-deviation tracking.</span> The same intake handles Adverse Event documentation timelines under sponsor agreements, near-miss tracking for in-home patient visits, and needlestick / sharps records for HomeHealth procedures &mdash; all in one record type.</li>
    <li><span class="feature-name">Trend analytics.</span> Pattern detection across incident type, location, and time window to flag clusters before they become sponsor audit findings.</li>
    <li><span class="feature-name">IR Copilot.</span> Conversational copilot that walks an HR user through incident triage &mdash; drafts the closing summary, proposes corrective actions, surfaces relevant prior incidents, and closes the case with a date-stamped audit trail.</li>
    <li><span class="feature-name">Discipline integration.</span> When an incident warrants a written warning or PIP, the discipline record is created from the incident with the relevant facts pre-populated.</li>
  </ul>

  <h2>Employee Records</h2>
  <p>Centralized employee directory replacing the spreadsheet patchwork most 200-person operations live with.</p>
  <ul>
    <li><span class="feature-name">Bulk CSV import.</span> One-shot migration from your current source-of-truth (HRIS export, payroll, spreadsheet).</li>
    <li><span class="feature-name">Onboarding workflows.</span> Task-based templates organized by role &mdash; HIPAA training acknowledgment, conflict-of-interest attestation, sponsor program training assignments.</li>
    <li><span class="feature-name">Document storage.</span> I-9, W-4, signed offer letters, training certificates &mdash; encrypted at rest, role-scoped access.</li>
    <li><span class="feature-name">Status tracking.</span> Active, on leave, terminated. LOA start/end dates with dashboard reminders.</li>
  </ul>
</div>

<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha · lite</div>
    <div class="page-header-right">What&rsquo;s Included</div>
  </div>

  <h2>Progressive Discipline Workflow</h2>
  <p>The Matcha discipline engine, integrated with the IR intake and the employee record.</p>
  <ul>
    <li><span class="feature-name">Discipline ladder.</span> Verbal &rarr; Written &rarr; Final &rarr; Termination, with templated language per step.</li>
    <li><span class="feature-name">Auto-expiry of stale records.</span> Discipline steps roll off after the configured retention window (typically 12 months) so prior conduct does not unfairly compound forever.</li>
    <li><span class="feature-name">Signature capture.</span> Employee acknowledgment with timestamp and IP trail.</li>
    <li><span class="feature-name">Tied to employee record.</span> Every discipline step lives on the employee&rsquo;s file &mdash; pulled into pre-termination conversations and accessible to authorized HR users only.</li>
  </ul>

  <h2>HR Resource Hub</h2>
  <p>Everything in the public Matcha Resources hub, accessible inside Lite without an additional subscription.</p>
  <ul>
    <li><span class="feature-name">State-by-state guides.</span> Pay transparency, leave laws, sick time, termination rules &mdash; all 50 states + DC. Updated as legislation changes.</li>
    <li><span class="feature-name">Editable templates.</span> Offer letters, PIPs, terminations, severance agreements.</li>
    <li><span class="feature-name">50+ job descriptions</span> across industries &mdash; including healthcare and patient-services roles relevant to {CLIENT_NAME}&rsquo;s home-office hiring.</li>
    <li><span class="feature-name">HR calculators.</span> PTO accrual, turnover cost, overtime, total comp.</li>
    <li><span class="feature-name">12-question compliance audit.</span> Posters, handbooks, I-9s, classification, leave, harassment, lactation, pay transparency &mdash; gap report delivered to your inbox.</li>
    <li><span class="feature-name">Glossary + state-tagged content</span> for quick reference during HR conversations.</li>
  </ul>
</div>

<!-- ─────── PAGE 4: Onboarding + Contract Terms ─────── -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha · lite</div>
    <div class="page-header-right">Onboarding &amp; Terms</div>
  </div>

  <h1>Self-Serve Onboarding</h1>
  <p>Lite has no implementation phase, no Discovery engagement, no Configuration sprint. The full path from sign-up to in-use is approximately 30 minutes:</p>

  <div class="step">
    <div class="step-number">1</div>
    <div class="step-title">Subscribe</div>
    <div>Open the Matcha Lite Stripe checkout link. Card capture only &mdash; no contract negotiation.</div>
  </div>
  <div class="step">
    <div class="step-number">2</div>
    <div class="step-title">Onboarding wizard</div>
    <div>A guided walk-through configures your company profile, primary jurisdiction (Indiana for HQ-based reporting), employee CSV upload, and IR intake settings.</div>
  </div>
  <div class="step">
    <div class="step-number">3</div>
    <div class="step-title">Invite your HR admin(s)</div>
    <div>Role-based access controls assign IR, employee records, and discipline permissions.</div>
  </div>
  <div class="step">
    <div class="step-number">4</div>
    <div class="step-title">Publish your anonymous report URL</div>
    <div>Single-use, token-gated; share with your workforce via email or your existing comms channel.</div>
  </div>

  <p>That is the entirety of go-live. There is no professional services engagement to schedule, no kickoff call required.</p>
  <p>If you would like a 30-minute walk-through with a Matcha team member before subscribing, that session is available at no charge &mdash; but it is optional. Lite is designed to be in use before that call could be scheduled.</p>

  <h2>Contract Terms</h2>
  <ul class="terms-list">
    <li><span class="term-label">Initial Term</span><span>Month-to-month. No annual commitment.</span></li>
    <li><span class="term-label">Cancellation</span><span>Self-serve via Stripe billing portal at any time. Effective at the end of the current paid month.</span></li>
    <li><span class="term-label">Pricing Lock</span><span>$100 per 10-employee block per month locked while subscription is active.</span></li>
    <li><span class="term-label">Headcount True-Up</span><span>Quarterly. Adjustments effective the first day of the following month.</span></li>
    <li><span class="term-label">Data Export</span><span>Full JSON + CSV export available at any time from the admin dashboard.</span></li>
    <li><span class="term-label">Data Retention on Cancel</span><span>Data preserved for 90 days post-cancellation; permanent deletion on written request or after 90 days.</span></li>
    <li><span class="term-label">Uptime</span><span>99.5% target platform availability.</span></li>
    <li><span class="term-label">Data Security</span><span>TLS 1.2+ in transit, AES-256 at rest. AWS US-based data residency.</span></li>
    <li><span class="term-label">Support</span><span>Email support, M&ndash;F 9 a.m. &ndash; 5 p.m. ET.</span></li>
  </ul>
</div>

<!-- ─────── PAGE 5: Acceptance ─────── -->
<div class="page">
  <div class="page-header">
    <div class="page-header-logo">matcha · lite</div>
    <div class="page-header-right">Acceptance</div>
  </div>

  <h1>Acceptance</h1>

  <p>By proceeding with the self-serve checkout link below (or signing this proposal), {CLIENT_NAME} acknowledges the scope, pricing, and terms above.</p>

  <div class="signature-section">
    <div class="sig-block">
      <div class="sig-line"></div>
      <div class="sig-label">Matcha &mdash; Signature, Name &amp; Title, Date</div>
    </div>
    <div class="sig-block">
      <div class="sig-line"></div>
      <div class="sig-label">{CLIENT_NAME} &mdash; Signature, Name &amp; Title, Date</div>
    </div>
  </div>

  <div class="footer-note">
    This proposal is valid for 30 days from {TODAY}. Pricing is locked while the subscription is active and subject to quarterly headcount true-up.
    Matcha is a compliance research and workforce risk intelligence platform. It is not a substitute for legal counsel and does not constitute legal advice, medical guidance, or regulatory certification.
  </div>
</div>

</body>
</html>
"""


def main() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)
    HTML(string=HTML_CONTENT).write_pdf(PDF_OUT)
    print(f"Wrote {HTML_OUT}")
    print(f"Wrote {PDF_OUT}")


if __name__ == "__main__":
    main()
