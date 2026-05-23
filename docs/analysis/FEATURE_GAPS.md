# HR Compliance Platform — Feature Gap Analysis

> Context: AI-powered HR compliance app targeting insurance brokers who offer it to their clients.
> Core focus areas: risk assessment, compliance, and employee relations.

---

## What's Already Built (Strong Foundation)

### Risk Assessment
- Multi-dimensional scoring: Compliance, Incidents, ER Cases, Workforce, Legislative
- Weighted composite score with bands (low / moderate / high / critical)
- AI-generated narrative reports + prioritized recommendations
- Action items with assignment, due dates, and status tracking
- Admin-configurable dimension weights

### Compliance
- Jurisdiction-aware requirements (multi-location, city/state)
- AI-powered compliance scans (SSE streaming)
- Preemption rules, upcoming legislation monitoring
- Compliance alerts with action plans
- Wage violation tracking, labor posting requirements
- Verification feedback / calibration stats

### Employee Relations (ER Copilot)
- Case management with full CRUD + case numbers
- Document upload + AI parsing
- Timeline analysis, discrepancy detection, policy check
- RAG evidence search across case documents
- Report generation
- Similar cases analysis, full audit log

### Incident Reports (IR)
- CRUD with document upload
- AI: categorization, severity, root cause, recommendations
- Precedent matching
- Consistency analytics + consistency guidance
- Trends + location hotspot analysis
- Anonymous reporting portal (`/anonymous-report`)

### HR Ops
- Employee onboarding with priorities and templates
- PTO / leave management (eligibility + notices service)
- ADA accommodations
- Internal mobility
- Policies (create, distribute, sign)
- Employee handbooks (industry templates + AI generation)
- eNPS, vibe checks, performance reviews
- Google Workspace + Slack provisioning
- Labor compliance posters (orders, fulfillment)

### Broker Channel
- Broker management admin panel
- Broker client registration flow (`RegisterBrokerClient`)
- Broker-specific API routes

---

## Feature Gaps

### 1. Broker-Specific Workflow (Highest Priority)

**Broker portfolio dashboard**
- Brokers need to see *all their clients* in one view with aggregate risk scores, not navigate each company individually
- Portfolio-level risk roll-up is a standard broker expectation
- Should surface: overall band per client, open action items, recent escalations, days since last compliance scan

**Risk score history / trending over time**
- The current snapshot is a single point in time
- Brokers need trend lines ("this client went moderate → high over 90 days") to justify coverage changes and demonstrate value to their clients
- Requires storing snapshots with timestamps rather than overwriting (or maintaining a history table)

**Automated broker alerts on risk escalation**
- When a client's risk band increases (e.g., moderate → high), the broker should be notified proactively
- Currently there is no push mechanism from client events to the broker layer

**Benchmark / peer comparison**
- "Your client is riskier than 70% of similar-sized companies in this industry"
- Brokers use this to contextualize risk for their clients and justify premium recommendations

**Broker-client relationship management**
- Can a broker manage multiple clients? Can clients transfer between brokers?
- Is there a broker-specific login/portal view vs. the standard client view?
- Needs clear data model: broker → [companies]

**One-click underwriting summary report (PDF export)**
- Standard insurance workflow: broker attaches a risk + compliance + IR summary to a submission
- ER Copilot has per-case report generation; a portfolio-level underwriting summary is missing
- Should combine: risk score + dimensions, open compliance gaps, IR trend summary, open ER cases

---

### 2. Compliance Gaps

**I-9 / E-Verify compliance**
- Extremely common in HR compliance products
- Hiring eligibility verification is a separate compliance concern from wage/hour
- Includes: I-9 completion tracking, reverification reminders, audit readiness

**EEO-1 reporting support**
- Required for federal contractors and employers with 100+ employees
- Common audit trigger; brokers selling EPL coverage want to know if clients are compliant

**OSHA recordkeeping (300/300A/301 logs)**
- The IR module tracks incidents but there is no explicit OSHA log management
- Should include: automatic OSHA 300 log population from IR data, 300A annual summary reminders, OSHA reporting threshold alerts (incidents requiring notification within 8/24 hours)

**Training completion tracking**
- Harassment prevention training, safety training, etc. are both compliance requirements and risk mitigation measures insurers care about
- Currently there is no feature to assign, track, or report on mandatory training completion

---

### 3. Employee Relations Gaps

**Pre-termination / separation risk module**
- Wrongful termination is a top EPL (employment practices liability) claim type
- A pre-termination checklist / risk flag before a separation would be highly valuable for brokers selling EPL coverage
- Should flag: active ER cases involving the employee, recent IR involvement, FMLA/ADA accommodation history, protected class signals, documentation completeness

**Settlement / outcome tracking on ER cases**
- ER cases track status but not financial outcomes (settlements, attorney fees, litigation costs)
- Brokers and underwriters want loss history to assess EPL exposure
- Should include: outcome type (resolved internally, EEOC charge, litigation, settlement), monetary amount, date closed

**Demand letter / EEOC charge intake**
- Formal legal triggers (EEOC charges, NLRB complaints, demand letters) should have a dedicated intake path separate from general ER cases
- Different workflow, urgency, and documentation requirements

**Whistleblower / retaliation case tagging**
- Needs a distinct category within ER cases
- Specific legal implications (anti-retaliation protections under SOX, Dodd-Frank, state laws)
- Should trigger heightened documentation requirements and supervisor recusal logic

---

### 4. Analytics & Risk Attribution Gaps

**Manager-level risk attribution**
- If one manager generates 80% of ER cases or incidents, that is a key risk signal
- The IR consistency analytics partially address this but explicit manager-level reporting (ER cases per manager, IR rate per manager, turnover per manager) is absent
- This is also valuable for coaching and early intervention before claims occur

**Workers' comp incident → claim linkage**
- The IR system is where incidents start; insurers want to know if incidents become claims
- A "claim filed?" flag + claim number field on incidents would close the loop
- Enables loss ratio analysis: incidents vs. actual claims vs. cost

**Rolling compliance score history**
- Compliance check logs exist but there is no time-series visualization of compliance posture over time per location
- Brokers need to show improvement (or deterioration) to insurers

---

## Priority Recommendations for the Broker Channel

If picking the highest-impact gaps for the "insurance broker selling this to clients" use case:

| Priority | Feature | Why |
|----------|---------|-----|
| 1 | Broker portfolio dashboard | Core broker workflow — seeing all clients at once |
| 2 | Risk score history / trending | Brokers need trend data for renewals and client conversations |
| 3 | One-click underwriting summary (PDF) | Required for policy submissions; closes the insurance workflow loop |
| 4 | Pre-termination risk checklist | EPL is the primary liability covered; this reduces the highest-frequency claim type (see detailed spec below) |
| 5 | Workers' comp incident → claim linkage | Closes the loop between the platform and actual insurance losses |
| 6 | OSHA recordkeeping | Regulatory requirement that naturally integrates with the existing IR module |
| 7 | Settlement / outcome tracking | Loss history is foundational to underwriting; currently invisible |
| 8 | Automated broker alerts on risk escalation | Proactive value delivery to brokers without them having to log in |

---

## Detailed Spec: Pre-Termination Risk Checklist

### Why This Matters

Wrongful termination is the **#1 EPL claim type** by frequency. EEOC data shows termination-related charges (wrongful discharge, constructive discharge, retaliation for reporting) account for ~45% of all employment practices claims. For brokers selling EPL coverage, a client that runs every termination through a structured risk check is a materially better risk — and that's a selling point for both the platform and the policy.

The goal isn't to prevent all terminations — it's to ensure they're **well-documented, legally defensible, and free of obvious red flags** before they happen.

### What It Does

When a manager or HR initiates a separation (voluntary or involuntary), the system runs an automated risk scan across the employee's history on the platform and produces a risk report with a go/no-go recommendation.

### Risk Dimensions Checked

| Dimension | What It Scans | Red Flag Example |
|-----------|---------------|------------------|
| **Active ER cases** | Open ER Copilot cases involving this employee | Employee has an open harassment complaint — terminating now looks retaliatory |
| **Recent IR involvement** | Incidents filed by or about this employee in last 90 days | Employee filed a safety complaint 2 weeks ago — retaliation risk |
| **FMLA / ADA / Leave status** | Active leave, recent accommodation requests, pending leave requests | Employee is on intermittent FMLA — termination during protected leave |
| **Protected activity signals** | Recent complaints, whistleblower reports, union activity, EEOC charges | Employee participated in a wage complaint — protected concerted activity |
| **Documentation completeness** | Performance reviews, PIPs, written warnings, coaching notes in the system | No documented performance issues — "at-will" won't save you in front of a jury |
| **Tenure & timing** | Length of service, proximity to vesting/benefits milestones, recent promotion/raise | 19-year employee terminated 6 months before pension vesting |
| **Consistency check** | Similar situations with other employees — were they treated the same? | Last 3 employees who did the same thing got warnings, this one is being fired |
| **Manager risk profile** | Manager's ER case rate, IR rate, turnover rate vs. peers | This manager has 4x the termination rate of peer managers |

### Output: Pre-Termination Risk Report

- **Risk score** (low / moderate / high / critical) — same band system as company risk assessment
- **Flag summary** — each dimension gets a green/yellow/red status with explanation
- **Recommended actions before proceeding** — e.g., "Consult employment counsel," "Complete PIP documentation," "Wait until FMLA leave concludes"
- **AI narrative** — Gemini-generated plain-language summary of the risk posture, suitable for sharing with in-house counsel or the broker

### Workflow Integration

1. **Trigger**: HR clicks "Initiate Separation" on an employee profile (new button)
2. **Scan**: System runs the 8-dimension check automatically (async, ~5-10 seconds)
3. **Review**: HR sees the risk report with flags and recommendations
4. **Decision gate**:
   - **Low risk**: Proceed with standard offboarding flow
   - **Moderate risk**: System recommends documentation review; proceed with acknowledgment
   - **High/Critical risk**: System recommends legal review; requires manager + HR director sign-off before proceeding
5. **Audit trail**: The risk report, decision, and sign-offs are stored permanently — this becomes evidence of good faith if a claim is filed later

### What Already Exists That This Builds On

- **ER Copilot** — case data for the employee (open cases, history)
- **IR module** — incident involvement (filed by, filed about, witness)
- **Leave management** — FMLA/ADA status, active accommodations
- **Performance reviews** — review history, scores
- **Employee records** — tenure, department, manager
- **Risk assessment service** — scoring engine, band system, Gemini narrative generation
- **Incident consistency analytics** — the consistency check pattern already exists for IR

### Value to the Broker Channel

- **Underwriting**: "100% of our client's terminations go through a pre-separation risk check" is a concrete risk mitigation control
- **Loss prevention**: Catching a retaliation-risk termination before it happens saves $50K-$500K+ in litigation costs
- **Renewal justification**: Trend data on pre-termination checks (% flagged, % resolved before proceeding) demonstrates program effectiveness
- **Differentiation**: Most HR compliance tools don't have this — it's a feature that directly maps to insurance outcomes

---

## Notes

The core compliance, ER, and IR infrastructure is genuinely strong. The main gaps are:
1. The **broker-as-intermediary workflow** — brokers need a layer above individual client views
2. **Closing the loop between incidents and insurance outcomes** — the platform tracks incidents and cases but not what they cost, whether claims were filed, or how they resolved financially
3. **Hiring-side compliance** — I-9, EEO-1, and training completion are conspicuously absent from an otherwise thorough compliance module
