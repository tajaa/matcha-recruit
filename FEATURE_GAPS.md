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
| 4 | Pre-termination risk checklist | EPL is the primary liability covered; this reduces the highest-frequency claim type |
| 5 | Workers' comp incident → claim linkage | Closes the loop between the platform and actual insurance losses |
| 6 | OSHA recordkeeping | Regulatory requirement that naturally integrates with the existing IR module |
| 7 | Settlement / outcome tracking | Loss history is foundational to underwriting; currently invisible |
| 8 | Automated broker alerts on risk escalation | Proactive value delivery to brokers without them having to log in |

---

## Notes

The core compliance, ER, and IR infrastructure is genuinely strong. The main gaps are:
1. The **broker-as-intermediary workflow** — brokers need a layer above individual client views
2. **Closing the loop between incidents and insurance outcomes** — the platform tracks incidents and cases but not what they cost, whether claims were filed, or how they resolved financially
3. **Hiring-side compliance** — I-9, EEO-1, and training completion are conspicuously absent from an otherwise thorough compliance module
