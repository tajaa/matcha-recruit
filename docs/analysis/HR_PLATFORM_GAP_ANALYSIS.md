# HR Platform Gap Analysis — Employee & Onboarding System

_Internal document for product and engineering. Can be shared with prospective customers._

---

## What's Already Strong

The platform has solid coverage across the core employee lifecycle and ER/IR workflows:

- **Employee lifecycle** — Hire → onboarding state machine → active → offboarding → offboarded
- **ER Copilot** — Full case management (create, investigate, AI analysis, guidance, reports, audit trail)
- **IR Incidents** — Safety/behavioral incident reporting with AI categorization and consistency checking
- **Pre-termination risk** — 8-dimension scan with AI narrative, acknowledgment gate, outcome tracking
- **Progressive discipline** — Verbal/written/PIP/final warning/suspension tracking
- **Agency charges** — EEOC, NLRB, OSHA, state agency charge management
- **Post-termination claims** — Litigation/settlement tracking linked to pre-term checks
- **Accommodations** — ADA accommodation case management with AI suggestions
- **Leave** — FMLA eligibility + WH-381/WH-382 notice generation, state PFML programs
- **Onboarding** — Template-based tasks, Google Workspace provisioning, state machine
- **PTO** — Balance tracking, request/approval workflow
- **Experience XP** — Vibe checks, eNPS surveys, performance review cycles
- **Compliance** — Jurisdiction-aware compliance requirement scanning

---

## Identified Gaps by Priority

### Tier 1 — Legal Compliance Risk (Build First)

#### 1. I-9 / Employment Eligibility Verification

**Legal basis:** 8 U.S.C. § 1324a — federal requirement for all U.S. employers, all employees.

**What the platform currently does:** Nothing. No I-9 model, no document tracking, no re-verification reminders.

**What's missing:**
- I-9 form status tracking per employee (Section 1 employee completion, Section 2 employer verification)
- Document type, document number, issuing authority, expiration date
- Re-verification reminders when work authorization expires (e.g., EAD, TN visa)
- E-Verify case status (optional but increasingly required by state law and federal contracts)
- Audit trail for I-9 inspections (ICE, DOJ Office of Special Counsel)

**Risk of not having it:** ICE audits result in fines of $281–$2,789 per paperwork violation, $676–$5,404 per unauthorized worker. No expiration tracking means employers miss re-verification deadlines, creating knowing-hire liability.

**Applies to:** All company sizes.

---

#### 2. Retaliation Risk Detection

**Legal basis:** Title VII, ADA, FMLA, NLRA, OSHA Section 11(c), state whistleblower statutes — retaliation is the #1 charge category at the EEOC (over 55% of all charges in recent years).

**What the platform currently does:** IR/ER cases are recorded with timestamps. Discipline records exist independently. No cross-referencing.

**What's missing:**
- Logic to detect when an employee who filed an IR or ER report subsequently receives discipline, demotion, schedule change, or termination
- Risk flag surfaced in ER Copilot case view and pre-termination scan
- Timeline visualization showing protected activity → adverse action proximity
- Configurable look-back window (e.g., 90–180 days)
- Audit-ready narrative: "Employee filed harassment complaint on [date]. Termination initiated [N] days later."

**Risk of not having it:** Employers proceed with adverse actions without realizing the retaliation exposure. The pre-termination scan currently checks 8 dimensions — this should be dimension 9.

**Applies to:** All company sizes.

---

#### 3. OSHA 300/301 Log

**Legal basis:** 29 CFR 1904 — required for establishments with 10+ employees (most industries).

**What the platform currently does:** IR Incidents captures safety/behavioral incidents with AI categorization. No OSHA recordability determination, no 300 log, no 301 form.

**What's missing:**
- OSHA recordability determination logic (days away from work, restricted duty, medical treatment beyond first aid, loss of consciousness, diagnosis of significant injury)
- OSHA 300 log generation (columns: case number, employee name/job title, date, location of incident, description, classification, days away, days restricted)
- OSHA 301 form generation (Injury and Illness Incident Report) per recordable incident
- Annual 300A Summary (Feb 1–Apr 30 posting requirement)
- Electronic submission to OSHA Injury Tracking Application (ITA) for 250+ employee establishments

**Risk of not having it:** Willful failure to maintain 300 log: $15,625/violation. Failure to post 300A: up to $15,625. Also blocks the platform from serving manufacturing, construction, healthcare, and other high-incident industries.

**Applies to:** 10+ employees (most industries). Exemptions for low-hazard industries (retail, finance, etc.) under 29 CFR 1904.2.

---

#### 4. COBRA Qualifying Event Notifications

**Legal basis:** 29 U.S.C. §§ 1161–1168 — employer must notify plan administrator within 30 days of qualifying event; administrator must notify qualified beneficiaries within 14 days (44 days total). DOL fines up to $110/day per qualified beneficiary for late notice.

**What the platform currently does:** Employee offboarding exists. No COBRA model, no qualifying event detection, no notice deadline tracking.

**What's missing:**
- Qualifying event detection triggered by: termination, reduction in hours, divorce/legal separation, dependent aging out (26), Medicare enrollment, employee death
- Automated 44-day employer notice deadline tracking from qualifying event date
- 60-day COBRA election period tracking per beneficiary
- 18/36-month continuation period tracking (varies by qualifying event)
- Integration point: offboarding flow should auto-create COBRA qualifying event record

**Risk of not having it:** $110/day/beneficiary penalty. For a 5-person family, a missed notice costs $110 × 5 × 44 days = $24,200 before any election period issues.

**Applies to:** Employers with 20+ employees on more than 50% of typical business days in the prior year.

---

#### 5. Training Compliance

**Legal basis:** California SB 1343 (sexual harassment prevention — 2+ employees, supervisors every 2 years, non-supervisors every 2 years), New York SAHPA (all employees annually), Illinois Human Rights Act (all employees annually), plus OSHA training requirements by industry, food handler certifications, forklift certification, etc.

**What the platform currently does:** Nothing. No training record model.

**What's missing:**
- Training record model: employee, training type, completion date, expiration date, provider, certificate number
- Mandatory training templates by state (harassment prevention, safety, food handler, etc.)
- Completion tracking with pass/fail and score
- Expiration alerts and auto-assignment of renewal training
- Compliance dashboard: which employees are overdue, which locations have <100% completion
- Training history for audit purposes

**Risk of not having it:** CA DFEH enforcement, OSHA citations, negligence exposure if a harassment incident occurs and training records are incomplete.

**Applies to:** Varies by state and industry. Harassment prevention: CA (2+ employees), NY (all), IL (all). Safety training: industry-dependent.

---

### Tier 2 — ER Platform Completeness

#### 6. Separation Agreement Generation

**Legal basis:** ADEA (Age Discrimination in Employment Act) — for employees 40+, waivers must include 21-day consideration period and 7-day revocation period. For group layoffs (2+ employees same program), 45-day consideration period and itemized disclosure of affected job titles/ages.

**What the platform currently does:** Offboarding tasks exist as a state machine. No separation agreement model or generation.

**What's missing:**
- Separation agreement document generation (standard terms: release of claims, severance amount, non-disparagement, COBRA, return of property, non-compete if applicable)
- ADEA period tracking: employee DOB → determine 40+ → enforce 21/45-day consideration period
- 7-day revocation period tracking (agreement not effective until revocation period expires)
- Group layoff disclosure: list of ages/titles of all employees in decision-making unit
- Electronic signature integration or PDF generation for wet signature
- Agreement status: draft → presented → consideration period → signed/revoked → effective

**Risk of not having it:** Invalid waiver = employee retains ADEA claims despite signing. Courts have voided agreements for failure to include proper language or track the waiting periods.

**Applies to:** Any company offering severance. ADEA requirements for employees 40+.

---

#### 7. Exit Interview System

**Business rationale:** Exit interview data is a primary source of voluntary turnover intelligence. Currently the platform has vibe checks and eNPS but no structured offboarding feedback capture.

**What the platform currently does:** Offboarding tasks include an `exit_interview` task type but it's a checkbox — no structured data, no form, no analytics.

**What's missing:**
- Exit interview form with configurable questions (reason for leaving, manager effectiveness, role clarity, compensation satisfaction, culture fit)
- Sentiment analysis on free-text responses
- Aggregated analytics: top reasons for departure, manager-level breakdowns, department trends
- Linkage to employee tenure, role, department, manager for cohort analysis
- Benchmark comparison (voluntary vs. involuntary, department vs. company average)

**Risk of not having it:** No structured retention intelligence. Companies lose the only moment employees give candid feedback.

**Applies to:** All company sizes.

---

#### 8. Workplace Violence Prevention Plan (WVPP)

**Legal basis:** California SB 553 (effective July 1, 2024) — requires all CA employers to establish, implement, and maintain a written WVPP. Annual review required.

**What the platform currently does:** IR Incidents captures behavioral incidents. No WVPP documentation module.

**What's missing:**
- WVPP document storage and version tracking
- Annual review workflow with acknowledgment by responsible party
- Violence risk incident escalation pathway (IR incident → WVPP review trigger)
- Employee training completion tracking for WVPP content
- Incident log specifically for workplace violence incidents (distinct from general IR incidents)

**Risk of not having it:** Cal/OSHA citations up to $25,000 for willful/repeat violations for CA employers. Negligence exposure if a violence incident occurs and WVPP was not maintained.

**Applies to:** All CA employers (SB 553). Similar requirements pending in other states.

---

#### 9. WARN Act Compliance

**Legal basis:** 29 U.S.C. §§ 2101–2109 — employers with 100+ employees must provide 60 days advance written notice before mass layoff (50+ employees at a single site within 30 days, or 33% of workforce) or plant closing. Many states have mini-WARN Acts with lower thresholds (CA: 75 employees, NY: 50 employees, NJ: 50 employees, IL: 75 employees).

**What the platform currently does:** No WARN Act tracking.

**What's missing:**
- WARN Act threshold calculator (employee count, layoff count, location)
- 60-day notice deadline tracking from planned separation date
- Required notice recipients: employees, state dislocated worker unit, local chief elected official
- Notice content generator with required elements
- State mini-WARN Act rules (lower thresholds, sometimes longer notice periods)
- Layoff event grouping to detect when individual separations aggregate to WARN threshold

**Risk of not having it:** Back pay + benefits for up to 60 days per affected employee + attorney fees. CA mini-WARN has no cap on liability.

**Applies to:** 100+ employees federally; lower thresholds in CA, NY, NJ, IL, and others.

---

#### 10. PWFA Tracking (Pregnant Workers Fairness Act)

**Legal basis:** Pregnant Workers Fairness Act (effective June 27, 2023) — requires reasonable accommodations for known limitations related to pregnancy, childbirth, or related medical conditions. Separate and distinct from ADA (no disability finding required).

**What the platform currently does:** ADA accommodations module exists. No PWFA-specific tracking.

**What's missing:**
- PWFA case type distinct from ADA accommodation cases
- Interactive process tracking specific to pregnancy-related limitations
- PWFA-specific undue hardship analysis (overlaps with ADA but different standard)
- Return-to-work planning for postpartum limitations
- EEOC charge tracking linkage (PWFA charges can be filed with EEOC)

**Risk of not having it:** EEOC began accepting PWFA charges June 2023. Mixing PWFA cases into ADA workflow creates compliance tracking gaps and potential misclassification in charge responses.

**Applies to:** Employers with 15+ employees.

---

### Tier 3 — HR Operations Maturity

#### 11. Compensation & Pay Equity

**Current state:** Schema includes `pay_rate` and `pay_classification` fields but no history tracking.

**Missing:**
- Compensation change history (salary changes, promotions, equity grants)
- Compensation bands/ranges by role and level
- Pay equity analysis: flag statistically significant pay gaps by gender, race, or other protected class within comparable roles
- CA SB 1162 / IL Equal Pay Act compliance (pay data reporting)

**Applies to:** CA SB 1162: 100+ employees. IL: 100+ employees.

---

#### 12. Background Check Tracking

**Current state:** No background check model or status tracking.

**Missing:**
- Background check request status per candidate/new hire (ordered, pending, clear, adverse action)
- FCRA adverse action workflow (pre-adverse action notice → waiting period → final adverse action)
- Vendor integration hooks (Checkr, HireRight, Sterling)
- Expiration and renewal tracking for roles requiring periodic re-screening

---

#### 13. Workers' Compensation

**Current state:** IR Incidents captures safety incidents but no workers' comp correlation.

**Missing:**
- Workers' comp claim record linked to IR incident
- Claim status tracking (reported, open, closed, denied)
- Modified duty / return-to-work plan tracking
- Days away from work correlation with OSHA 300 log
- State-specific first report of injury form generation

---

#### 14. Pay Transparency Compliance

**Legal basis:** CA SB 1162, NY Labor Law § 194-b, WA SB 5761, CO EPEWA — require salary ranges in job postings and/or upon request.

**Missing:**
- Pay range fields on job postings
- Compliance check: flag job postings without pay ranges in covered jurisdictions
- Pay range disclosure tracking for internal promotions (some states require)

---

### Tier 4 — FMLA Form Gaps (Quick Wins)

The platform currently generates WH-381 (Notice of Eligibility & Rights) and WH-382 (Designation Notice). Missing:

| Form | Description | When Used |
|------|-------------|-----------|
| **WH-380-E** | Certification of Health Care Provider (Employee's Own Condition) | Sent to employee's provider for employee's own serious health condition |
| **WH-380-F** | Certification of Health Care Provider (Family Member) | Sent to provider for family member's serious health condition |
| **WH-384** | Certification for Military Family Leave (Qualifying Exigency) | Military deployment-related leave |
| **WH-385** | Certification for Serious Injury or Illness (Military Caregiver) | Caregiver leave for covered servicemember |
| **WH-385-V** | Certification for Serious Injury or Illness (Veteran) | Caregiver leave for covered veteran |

Note: WH-380-E/F are the most commonly needed and should be prioritized.

---

## Employee Management & Onboarding Operational Gaps

The gaps above are legal/compliance-focused. This section covers **day-to-day HR operations** — the things that make or break whether the platform can replace BambooHR, Rippling, or Gusto for employee management.

### Employee Profile Completeness

**Current state:** The employee record has basics (name, email, phone, address, job title, department, manager, pay rate, pay classification, emergency contact as unstructured JSONB).

**Missing fields that real HR platforms need:**

| Category | Missing Fields |
|----------|---------------|
| **Personal** | Date of birth, gender, pronouns, ethnicity/race (for EEO reporting), veteran status, disability status |
| **Tax** | SSN (encrypted), federal W-4 elections (filing status, allowances, additional withholding), state withholding elections |
| **Identity** | Citizenship status, visa type/expiration (if applicable), driver's license number/state |
| **Emergency contacts** | Currently unstructured JSONB — should be typed records with name, relationship, phone, email, priority order. Support multiple contacts |
| **Dependents** | Spouse/domestic partner, children — needed for benefits enrollment, COBRA, life insurance beneficiary designation |
| **Direct deposit** | Bank name, routing number, account number (encrypted), split deposit percentages |

**Why it matters:** Without these, you can't do benefits enrollment, tax form generation, EEO-1 reporting, or payroll integration. Every customer will ask "where do I enter their SSN?" on day one.

---

### Benefits Administration (Complete Void)

**Current state:** Nothing. No benefits model, no enrollment, no tracking.

**What's needed:**

- **Plan definitions** — medical, dental, vision, life, disability, 401k, FSA, HSA, commuter benefits
- **Enrollment periods** — open enrollment windows, new hire enrollment (typically 30-60 days from start), qualifying life events (marriage, birth, divorce, loss of other coverage)
- **Employee elections** — plan selection, dependent coverage, beneficiary designations
- **Eligibility rules** — full-time only, waiting periods, hours thresholds
- **Costs** — employer contribution, employee premium, pre-tax vs post-tax deductions
- **Carrier integration** — EDI 834 feeds or API connections to insurance carriers

**Priority:** This is the single biggest gap for the platform as an employee management system. However, it's also the most complex to build — many platforms punt this to payroll/benefits vendors (Gusto, Justworks, TriNet) and integrate rather than build.

**Recommendation:** Start with **benefits tracking** (what plans exist, what each employee elected, costs) rather than full enrollment workflow. This covers 80% of what HR admins need without building a carrier integration layer.

---

### Compensation History & Job Changes

**Current state:** `pay_rate` and `pay_classification` exist as flat fields. No history. No change log.

**What's needed:**

- **Compensation change log** — effective date, old rate → new rate, reason (merit increase, promotion, market adjustment, annual review, equity grant), approved by
- **Title/role change history** — effective date, old title → new title, old department → new department
- **Promotion/transfer workflow** — manager or HR initiates → approval chain → effective on date → auto-update employee record
- **Compensation bands** — min/mid/max by role and level, compa-ratio calculation per employee

**Why it matters:** "When was this person's last raise?" and "Show me all promotions this year" are questions every HR team asks weekly. Without history, the platform is just a static directory.

---

### Document Management Gaps

**Current state:** `employee_documents` table exists with signing workflow (draft → pending_signature → signed → expired). Good foundation.

**What's missing:**

- **Document categorization** — no structured types. Need: offer letter, employment agreement, W-4, state tax form, I-9, handbook acknowledgment, policy sign-off, NDA, IP assignment, non-compete, arbitration agreement, background check consent, direct deposit form
- **Version tracking** — when handbook v2 is published, which employees acknowledged v1 vs v2?
- **Bulk generation** — generate W-4 or handbook acknowledgment for all employees, track completion
- **Expiration enforcement** — expiration date field exists but no automated workflow (no reminders, no status change, no re-signing trigger)
- **Audit-ready views** — "show me all employees who haven't signed the updated handbook" or "who's missing their W-4?"

---

### Employee Status Tracking

**Current state:** Onboarding state machine is solid (prehire → invited → accepted → in_progress → ready_for_day1 → active → offboarding → offboarded). But after "active" there's a gap.

**Missing intermediate statuses:**

| Status | Description |
|--------|-------------|
| **On leave** | Employee is on FMLA/PFML/personal leave. Leave requests exist but don't change employee status |
| **Suspended** | Placed on administrative leave pending investigation. Progressive discipline tracks suspensions but doesn't set employee status |
| **On notice** | Employee has given resignation notice or been given termination notice. No notice period tracking |
| **Furloughed** | Temporary unpaid leave (distinct from termination). No model for this |
| **Rehire eligible** | After offboarding — flag for whether they can be rehired. No field for this |

**Why it matters:** An "active" employee on FMLA leave looks the same as one working full-time. This creates confusion in headcount reporting, benefits eligibility, and PTO accrual.

---

### Manager Self-Service

**Current state:** Managers can be assigned via `manager_id`. Backend supports some manager operations. But there's no dedicated manager experience.

**Missing:**

- **Manager dashboard** — direct reports at a glance (headcount, PTO status, pending approvals, upcoming reviews, onboarding progress)
- **Approval queue** — PTO requests, comp change requests, document sign-offs pending manager action
- **Direct report org view** — who reports to me, who reports to them
- **1:1 scheduling and notes** — no meeting tracker, talking point templates, or follow-up capture
- **Manager-initiated actions** — request a raise for a direct report, initiate a PIP, nominate for promotion

**Why it matters:** Managers are the primary daily users of an HR platform after employees themselves. Without manager workflows, HR becomes the bottleneck for every action.

---

### Organizational Structure

**Current state:** `manager_id` on employee record, `department` as a string field. No formal org hierarchy.

**Missing:**

- **Department/team as entities** — currently just strings, so "Engineering" and "engineering" are different departments. Need a departments table with head/lead, cost center, parent department
- **Locations as entities** — `work_city` and `work_state` are strings. Need a locations table for office management, headcount by location, state-specific compliance
- **Org chart visualization** — no UI to see reporting structure
- **Cost centers / business units** — no concept of cost allocation
- **Dotted-line reporting** — only supports single manager, no matrix org support
- **Team membership** — no concept of cross-functional teams distinct from departments

---

### Onboarding Task Gaps

**Current state:** Template-based tasks with categories (documents, equipment, training, admin). Google Workspace and Slack auto-provisioning. Solid state machine with blocking support.

**Missing tasks that real onboarding needs:**

| Task | Notes |
|------|-------|
| **W-4 completion** | Federal tax withholding. Currently no tax form workflow |
| **State tax form** | State-specific withholding. Not tracked |
| **Direct deposit setup** | No bank info collection |
| **Benefits enrollment** | No benefits module to connect to |
| **Background check clearance** | No status tracking. Onboarding may need to block until cleared |
| **Drug test clearance** | Same — no model |
| **Laptop/hardware ordering** | Equipment category exists but no inventory tracking, no shipping status, no IT ticket integration |
| **Badge/key card provisioning** | Physical access — no tracking |
| **Parking/building access** | Facility management gap |
| **Manager welcome meeting** | Scheduling, not just a checkbox |
| **Buddy/mentor assignment** | No mentor model |

---

### Offboarding Gaps

**Current state:** Offboarding cases with task categories (access revocation, equipment return, knowledge transfer, exit interview, final payroll, benefits termination). Pre-termination risk scan.

**Missing:**

| Gap | Description |
|-----|-------------|
| **Final paycheck tracking** | No final pay date, no accrued PTO payout calculation (required by state law — CA requires same-day for involuntary, 72 hours for voluntary) |
| **Equipment return tracking** | Task category exists but no serial number, asset tag, return shipping status, or depreciation |
| **IT access audit** | No comprehensive list of systems to deprovision (beyond Google/Slack) — SaaS app access, VPN, code repos, cloud consoles |
| **Knowledge transfer plan** | Just a task category. No structured handoff document, successor assignment, or deadline tracking |
| **Unemployment insurance prep** | No documentation package for UI claims (separation reason, last day worked, earnings history) |
| **Reference policy** | No flag for whether company will provide references, what can be disclosed |
| **Rehire eligibility** | No field on offboarding case or employee record |

---

### Payroll Integration (Missing Entirely)

**Current state:** No payroll export, sync, or integration.

**What's needed (at minimum):**

- **Payroll export** — CSV/API export of employee data in format compatible with ADP, Gusto, Paychex, Rippling
- **Change feed** — new hires, terminations, pay rate changes, address changes, tax election changes pushed to payroll
- **Pay stub storage** — employees should be able to view pay stubs in the portal
- **Tax form distribution** — W-2, 1099 annual distribution

**Recommendation:** Don't build payroll. Build a **payroll sync connector** that pushes employee changes to the payroll provider. Start with Gusto API (most common for SMB customers).

---

### Audit Trail

**Current state:** Some operations log actor_id and timestamps. No comprehensive change history.

**What's needed:**

- **Field-level change log** — who changed what field, old value → new value, when, why
- **Login/access audit** — who viewed which employee records (important for HIPAA-adjacent benefit info)
- **Bulk action audit** — who ran a CSV import, what changed
- **Report generation** — "show all changes to employee X in the last 90 days"

---

### EEO & Demographic Reporting

**Current state:** No demographic data collection beyond what's needed for employment.

**What's needed for EEO-1 reporting (100+ employees, or federal contractors):**

- Race/ethnicity (per EEOC categories)
- Gender
- Job category (per EEO-1 Component 1 categories)
- Pay band (for Component 2, if reinstated)
- Veteran status (VETS-4212 for federal contractors)
- Disability status (Section 503 for federal contractors)

**Important:** Demographic data must be collected **voluntarily** and stored **separately** from hiring decision data. Self-identification forms should be distinct from the employment application.

---

## Revised Recommended Build Order

Adding employee management gaps to the original legal compliance priorities:

| # | Feature | Type | Justification |
|---|---------|------|---------------|
| 1 | Retaliation Detection | Compliance | Lowest build cost, highest legal exposure |
| 2 | Employee Profile Enhancement | Operations | Add DOB, SSN, structured emergency contacts, dependents. Foundation for everything else |
| 3 | Compensation History | Operations | Job change log, pay change log with effective dates. Small schema change, high daily value |
| 4 | Department/Location Entities | Operations | Replace string fields with proper tables. Enables reporting, compliance scoping |
| 5 | Training Compliance | Compliance | New module, required by CA/NY/IL |
| 6 | Document Management Enhancement | Operations | Categorization, version tracking, bulk generation, expiration workflows |
| 7 | I-9 Tracking | Compliance | Standalone module, affects every employee |
| 8 | Manager Dashboard | Operations | Direct reports view, approval queue, pending actions |
| 9 | Employee Status Tracking | Operations | On leave, suspended, furloughed, notice period states |
| 10 | OSHA 300 Log | Compliance | Extends IR incidents |
| 11 | COBRA Administration | Compliance | Triggered by offboarding events |
| 12 | Benefits Tracking (Lightweight) | Operations | Plan definitions + employee elections. Not full enrollment |
| 13 | Payroll Sync Connector | Operations | Start with Gusto API |
| 14 | Audit Trail | Operations | Field-level change log |
| 15 | Separation Agreement | Compliance | ADEA period tracking |
| 16 | Exit Interview | Operations | Structured capture + analytics |
| 17 | EEO Reporting | Compliance | Required for 100+ employees |

---

## Recommended Build Order

| # | Feature | Tier | Justification |
|---|---------|------|---------------|
| 1 | Retaliation Detection | 1 | Lowest build cost, highest legal exposure, builds on existing IR/ER data |
| 2 | Training Compliance | 1 | New module but high demand, required by CA/NY/IL |
| 3 | I-9 Tracking | 1 | Standalone module, affects every employee record |
| 4 | OSHA 300 Log | 1 | Extends existing IR incidents, enables industrial sector customers |
| 5 | COBRA Administration | 1 | Triggered by existing offboarding events, high penalty exposure |
| 6 | FMLA Missing Forms | 4 | Quick wins — WH-380-E/F especially needed |
| 7 | Separation Agreement | 2 | Extends offboarding, ADEA period tracking critical |
| 8 | Exit Interview | 2 | Completes the offboarding loop, enables retention analytics |
| 9 | PWFA Tracking | 2 | Separate from ADA in existing accommodations module |
| 10 | WARN Act | 2 | Required for mid-market customers (100+ employees) |

---

## Files to Create/Modify

### New Backend Routes
- `server/app/matcha/routes/training.py` — Training records, certifications, compliance tracking
- `server/app/matcha/routes/i9.py` — I-9 form tracking and re-verification
- `server/app/matcha/routes/cobra.py` — COBRA qualifying events and election tracking
- `server/app/matcha/routes/separation.py` — Separation agreement generation and signing

### Extend Existing Routes
- `server/app/matcha/routes/ir_incidents.py` — Add OSHA recordability, 300/301 log endpoints
- `server/app/matcha/routes/employees.py` — Offboard trigger → COBRA qualifying event
- `server/app/matcha/routes/er_copilot.py` — Add retaliation risk flagging
- `server/app/matcha/routes/pre_termination.py` — Add WARN Act check, COBRA trigger, separation agreement step
- `server/app/matcha/routes/leave.py` — Add WH-380-E/F, WH-384, WH-385 generation

### New Frontend Pages
- `client/src/pages/TrainingCompliance.tsx` — Training records dashboard and completion tracking
- `client/src/pages/I9Management.tsx` — I-9 tracking and re-verification alerts
- `client/src/pages/SeparationAgreements.tsx` — Agreement generation and period tracking

### Alembic Migrations Needed
- `training_records`, `training_templates` tables
- `i9_forms` table
- `cobra_events`, `cobra_elections` tables
- `separation_agreements` table (extend offboarding_cases)
- `exit_interview_responses` table

---

## Test Scenarios

- **Retaliation detection:** File IR incident, then add discipline record → verify flag appears in ER Copilot case and pre-term scan
- **I-9 tracking:** Create employee, complete I-9 with EAD expiration date → verify re-verification reminder fires before expiration
- **OSHA recordability:** Create safety incident with "days away from work" attribute → verify it appears on 300 log export
- **COBRA:** Terminate employee → verify qualifying event created with 44-day employer notice deadline
- **Separation agreement (ADEA):** Initiate offboarding for employee born before [today - 40 years] → verify 21-day consideration period and 7-day revocation period are tracked, agreement blocked from finalizing during revocation window
- **Training compliance:** Assign harassment prevention training to CA employee, mark incomplete after due date → verify compliance dashboard flags the gap
