# PRD: Pre-Termination Risk Checklist

**Status**: Draft
**Priority**: P1 — High
**Author**: Product
**Date**: 2026-03-07

---

## 1. Problem Statement

Wrongful termination is the **#1 EPL (Employment Practices Liability) claim type** by frequency. EEOC charge statistics show termination-related claims — wrongful discharge, constructive discharge, and retaliation for protected activity — account for roughly 45% of all employment practices claims filed annually. The average EPL claim costs $75,000–$125,000 to defend, and settlements for wrongful termination routinely exceed $200,000.

Insurance brokers selling EPL coverage to their clients need to demonstrate that those clients have **concrete risk controls** in place to reduce claim frequency. Today, the platform has no mechanism to evaluate the risk posture of an individual employee separation before it happens. Managers and HR can terminate employees without any system-level check for obvious red flags (active complaints, protected leave, missing documentation), and the platform only captures termination after the fact via the `termination_date` field on the employee record.

The offboarding flow (`POST /employees/{id}/offboarding`) creates a task checklist (access revocation, equipment return, exit interview), but this is an **operational** workflow — it handles logistics after the decision is made. There is no **risk evaluation** step before the decision.

## 2. Objective

Build a **Pre-Termination Risk Check** that automatically scans an employee's history across all platform modules when HR initiates a separation, produces a scored risk report with specific flags, and gates the offboarding workflow based on risk level.

### Success Metrics

| Metric | Target |
|--------|--------|
| Adoption | 80%+ of involuntary terminations go through the risk check within 90 days of launch |
| Flag accuracy | <10% false positive rate on high/critical flags (measured via HR override tracking) |
| Broker value | Feature cited in 50%+ of broker demo conversations as a differentiator |
| Loss prevention | Measurable reduction in ER cases filed within 90 days post-termination (baseline TBD) |

## 3. User Stories

### HR Manager / Client Admin
- **As an HR manager**, I want to see a risk summary before I proceed with terminating an employee, so I can address documentation gaps or legal risks before they become claims.
- **As an HR manager**, I want the system to flag if the employee has open complaints, active leave, or recent protected activity, so I don't inadvertently create a retaliation claim.
- **As an HR manager**, I want to see how similar situations were handled in the past, so I can ensure consistency and fairness.
- **As an HR manager**, I want a clear go/no-go recommendation with specific next steps if risk is elevated, so I know exactly what to do.

### Platform Admin
- **As a platform admin**, I want to see pre-termination risk check activity across all companies, so I can identify systemic issues and training opportunities.
- **As an admin**, I want to configure which risk dimensions are enabled and their thresholds, so I can tune the system for different client profiles.

### Insurance Broker
- **As a broker**, I want to see what percentage of my client's terminations went through a risk check, so I can quantify their risk management maturity.
- **As a broker**, I want to see the distribution of risk check outcomes (low/moderate/high/critical) and override rates, so I can assess whether the client is actually using the tool or rubber-stamping it.
- **As a broker**, I want to include pre-termination risk check metrics in underwriting summaries, so I can demonstrate concrete loss prevention controls to carriers.

## 4. Feature Design

### 4.1 Trigger Point

The risk check is triggered when HR creates an offboarding case via `POST /employees/{employee_id}/offboarding`. Before the offboarding case is created, the system runs the risk scan and returns the report alongside the case. For involuntary separations (`is_voluntary: false`), the risk check is **required** and the report must be acknowledged before proceeding. For voluntary separations, the check runs but does not gate the workflow.

**New endpoint**: `POST /employees/{employee_id}/pre-termination-check`
- Can be called independently (before offboarding) for a "what-if" analysis
- Returns the full risk report without creating an offboarding case
- Allows HR to evaluate risk before making the final decision

**Modified endpoint**: `POST /employees/{employee_id}/offboarding`
- For involuntary separations: automatically runs the pre-termination check
- If risk is high/critical: returns the risk report with `requires_acknowledgment: true`
- HR must re-submit with `risk_acknowledged: true` and `acknowledgment_notes` to proceed
- The risk report ID is stored on the offboarding case for audit trail

### 4.2 Risk Dimensions

The scan evaluates 8 dimensions, each producing a flag status (green / yellow / red) and contributing to an overall risk score.

#### Dimension 1: Active ER Cases

**Data source**: `er_cases` table
**Query**: Open ER cases where the employee is named in the case (via `intake_context` JSONB field or a new `involved_employees` relation)
**Scoring**:
- Red: Employee is the complainant or respondent in an open case with status `open` or `in_review`
- Yellow: Employee was involved in a case closed within the last 90 days
- Green: No ER case involvement in the last 12 months

**Why it matters**: Terminating someone who has an open complaint is the textbook definition of retaliation. Even if the termination is for legitimate reasons, the timing creates a presumption of retaliatory motive that is extremely difficult to overcome in litigation.

#### Dimension 2: Recent IR Involvement

**Data source**: `ir_incidents` table, `involved_employee_ids` array
**Query**: Incidents where the employee is in `involved_employee_ids` or is the reporter (`reported_by_email` matches employee email), within the last 90 days
**Scoring**:
- Red: Employee filed an incident report (safety complaint, harassment report) in the last 30 days
- Yellow: Employee was involved in an incident (witness, reporter, subject) in the last 90 days
- Green: No incident involvement in the last 90 days

**Why it matters**: An employee who recently reported a safety concern or harassment has engaged in protected activity. Termination within a short window after a report creates a strong inference of retaliation under OSHA Section 11(c), Title VII, and state whistleblower statutes.

#### Dimension 3: Leave and Accommodation Status

**Data source**: `pto_requests` table, ADA accommodation records (currently in `employees` JSONB or dedicated table TBD)
**Query**: Active or recent PTO requests with type indicators that suggest protected leave (FMLA, medical, ADA accommodation)
**Scoring**:
- Red: Employee is currently on approved leave, has a pending leave request, or has an active ADA accommodation
- Yellow: Employee returned from a medical/FMLA leave within the last 60 days
- Green: No active or recent protected leave activity

**Why it matters**: Terminating an employee during FMLA leave, shortly after they return from leave, or after requesting an ADA accommodation is per se illegal under federal law (29 USC 2615, 42 USC 12112). These cases are among the easiest for plaintiffs to win because the timing alone establishes a prima facie case.

**Implementation note**: The current PTO system uses generic `request_type` values (`vacation`, `sick`, `personal`, `other`). A future enhancement should add FMLA/medical leave tracking. For MVP, flag any employee with active `sick` leave or recent medical-related PTO patterns.

#### Dimension 4: Protected Activity Signals

**Data source**: Cross-reference across ER cases (whistleblower/retaliation categories), IR incidents (safety complaints), and any EEOC/agency charge records (new table)
**Query**: Aggregate signals of protected activity within the last 12 months
**Scoring**:
- Red: Employee has filed an EEOC charge, NLRB complaint, OSHA complaint, or internal whistleblower report
- Yellow: Employee has participated as a witness in an investigation or filed an internal complaint
- Green: No protected activity signals

**Why it matters**: Federal and state anti-retaliation statutes (Title VII Section 704, SOX Section 806, Dodd-Frank Section 922) provide broad protection for employees who engage in protected activity. Courts apply a burden-shifting framework (McDonnell Douglas) where temporal proximity alone can establish causation.

#### Dimension 5: Documentation Completeness

**Data source**: Performance review records, PIP/warning records (new), employee documents
**Query**: Check for existence and recency of performance documentation
**Scoring**:
- Red: No performance reviews on file, or last review was positive (score >= 4/5) with no subsequent documented performance issues
- Yellow: Performance reviews exist but are >12 months old, or there is one documented warning but no PIP
- Green: Recent negative performance review (<6 months) with documented PIP or progressive discipline

**Why it matters**: "At-will" employment is a defense on paper but not in practice. Juries are skeptical of terminations where the employer cannot produce contemporaneous documentation of performance issues. A positive review followed by sudden termination is the plaintiff's attorney's best exhibit. Progressive discipline (verbal warning → written warning → PIP → termination) is the standard that courts and juries expect.

**Implementation note**: The platform currently has performance reviews but no formal PIP/warning tracking. The MVP can check for performance review existence and recency. Phase 2 adds a progressive discipline tracker.

#### Dimension 6: Tenure and Timing

**Data source**: `employees.start_date`, `employees.termination_date` (for pattern analysis), company benefit vesting schedules (new)
**Query**: Calculate tenure length, check proximity to benefit milestones
**Scoring**:
- Red: Employee tenure >10 years (long-tenured employees generate higher sympathy damages), OR termination is within 6 months of a benefits vesting milestone
- Yellow: Employee tenure 5-10 years
- Green: Employee tenure <5 years with no approaching vesting milestones

**Why it matters**: Long-tenured employees receive significantly higher jury verdicts. Termination suspiciously close to a vesting milestone (pension, stock options, retirement eligibility) creates an inference of intentional deprivation of benefits under ERISA Section 510. Even without ERISA, juries are deeply unsympathetic to employers who terminate long-tenured employees.

#### Dimension 7: Consistency Check

**Data source**: Historical offboarding cases and pre-termination checks for the same company
**Query**: Find employees who were terminated for similar reasons (same category, same department, similar tenure) and compare treatment
**Scoring**:
- Red: Similar employees in similar situations were given warnings or retained — this employee is being treated differently
- Yellow: Insufficient data to determine consistency (fewer than 3 comparable cases)
- Green: Treatment is consistent with how similar situations were handled

**Why it matters**: Disparate treatment is the foundation of discrimination claims. If an employer terminated a minority employee for a policy violation but gave a non-minority employee a warning for the same violation, that inconsistency is direct evidence of discriminatory intent. The IR consistency analytics engine already implements this pattern — the same approach applies here.

**Implementation note**: Leverage the existing `ir_consistency.py` service patterns. The consistency check needs a minimum number of prior cases to be meaningful — the system should clearly state when there is insufficient data rather than giving a false "green."

#### Dimension 8: Manager Risk Profile

**Data source**: Aggregate manager-level metrics from ER cases, IR incidents, offboarding cases, and employee turnover
**Query**: For the employee's direct manager (`employees.manager_id`), compute: ER case rate, IR rate, turnover rate, and compare to peer managers in the same company
**Scoring**:
- Red: Manager's termination rate or ER case rate is >2x the company average
- Yellow: Manager's rates are 1.5-2x the company average
- Green: Manager's rates are at or below the company average

**Why it matters**: A disproportionate number of terminations, complaints, or incidents under a single manager is a pattern that plaintiff's attorneys actively look for. It suggests either a management problem (hostile work environment) or a documentation/process problem (manager is terminating without following procedure). Either way, it's a risk signal that should be surfaced before another termination proceeds.

### 4.3 Scoring and Output

#### Overall Score Calculation

Each dimension produces a score:
- Green: 0 points
- Yellow: 15 points
- Red: 30 points

Maximum possible score: 240 (all 8 dimensions red). Normalized to 0-100 scale.

**Band thresholds** (aligned with existing company risk assessment):
| Score | Band | Workflow Impact |
|-------|------|-----------------|
| 0-25 | Low | Proceed with offboarding normally |
| 26-50 | Moderate | Warning displayed, proceed with acknowledgment |
| 51-75 | High | Requires HR director sign-off, legal review recommended |
| 76-100 | Critical | Requires HR director + executive sign-off, legal review required |

#### Risk Report Output

```json
{
  "id": "uuid",
  "employee_id": "uuid",
  "company_id": "uuid",
  "overall_score": 62,
  "overall_band": "high",
  "dimensions": {
    "er_cases": {
      "status": "red",
      "score": 30,
      "summary": "Employee is the complainant in ER-2026-0042 (open, harassment complaint filed 2026-02-15)",
      "details": { "open_cases": [...], "recent_closed_cases": [...] }
    },
    "ir_involvement": {
      "status": "green",
      "score": 0,
      "summary": "No incident involvement in the last 90 days",
      "details": {}
    },
    "leave_status": {
      "status": "yellow",
      "score": 15,
      "summary": "Employee returned from sick leave 45 days ago (2026-01-21 to 2026-01-28)",
      "details": { "recent_leave": [...] }
    },
    "protected_activity": {
      "status": "red",
      "score": 30,
      "summary": "Employee filed internal harassment complaint (ER-2026-0042) — protected activity under Title VII",
      "details": { "signals": [...] }
    },
    "documentation": {
      "status": "yellow",
      "score": 15,
      "summary": "Last performance review was 14 months ago (2024-12-15, score: 3.8/5). No documented PIP or progressive discipline.",
      "details": { "last_review": {...}, "warnings": [], "pips": [] }
    },
    "tenure_timing": {
      "status": "green",
      "score": 0,
      "summary": "Employee tenure: 2.3 years. No approaching benefit milestones.",
      "details": { "tenure_years": 2.3, "start_date": "2023-11-15" }
    },
    "consistency": {
      "status": "yellow",
      "score": 15,
      "summary": "Insufficient comparable cases (2 similar terminations found, minimum 3 required for analysis)",
      "details": { "comparable_cases": 2, "minimum_required": 3 }
    },
    "manager_profile": {
      "status": "green",
      "score": 0,
      "summary": "Manager termination rate (1.2/yr) is below company average (1.8/yr)",
      "details": { "manager_term_rate": 1.2, "company_avg_rate": 1.8 }
    }
  },
  "recommended_actions": [
    "Do NOT proceed with termination while ER-2026-0042 is open — high retaliation risk",
    "Consult employment counsel before proceeding",
    "Document specific, objective performance deficiencies before initiating separation",
    "Ensure any performance issues cited are unrelated to the protected complaint"
  ],
  "ai_narrative": "This separation presents HIGH risk due to the employee's active harassment complaint...",
  "computed_at": "2026-03-07T14:30:00Z",
  "acknowledged": false,
  "acknowledged_by": null,
  "acknowledged_at": null,
  "acknowledgment_notes": null
}
```

### 4.4 AI Narrative Generation

After scoring, the system calls Gemini to generate a plain-language narrative. This follows the same pattern as `generate_recommendations()` in `risk_assessment_service.py`.

**Prompt structure**:
- Input: dimension scores, flag details, employee tenure, separation reason
- Output: 2-3 paragraph narrative suitable for sharing with in-house counsel or a broker
- Tone: objective, legally precise, avoids definitive legal conclusions ("this creates risk" not "this is illegal")
- Includes: specific statutes that may be implicated, recommended next steps, estimated risk exposure range

### 4.5 Audit Trail

Every pre-termination risk check is stored permanently, regardless of whether the separation proceeds. This serves two purposes:

1. **Legal defense**: If a claim is filed, the employer can demonstrate they evaluated risk in good faith before proceeding. "We ran a systematic risk check, identified the potential issues, consulted counsel, and documented our legitimate business reasons" is a strong defense posture.

2. **Pattern analysis**: Aggregate data on risk checks (how many, what flags, what outcomes) feeds into the broker portfolio dashboard and underwriting summaries.

**Stored data**:
- Full risk report (all dimensions, scores, details)
- Whether the separation proceeded
- Who acknowledged the risk (if high/critical)
- Any notes from the acknowledger
- Outcome (if the termination was ultimately completed, modified, or abandoned)
- Link to the offboarding case (if created)

## 5. Data Model

### New Tables

```sql
CREATE TABLE pre_termination_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    initiated_by UUID NOT NULL REFERENCES users(id),

    -- Scoring
    overall_score INT NOT NULL,
    overall_band VARCHAR(20) NOT NULL CHECK (overall_band IN ('low', 'moderate', 'high', 'critical')),
    dimensions JSONB NOT NULL,  -- Full dimension breakdown (see 4.3)

    -- AI narrative
    ai_narrative TEXT,
    recommended_actions JSONB,  -- Array of action strings

    -- Acknowledgment (for high/critical)
    requires_acknowledgment BOOLEAN NOT NULL DEFAULT false,
    acknowledged BOOLEAN NOT NULL DEFAULT false,
    acknowledged_by UUID REFERENCES users(id),
    acknowledged_at TIMESTAMPTZ,
    acknowledgment_notes TEXT,

    -- Outcome tracking
    outcome VARCHAR(30) CHECK (outcome IN ('proceeded', 'modified', 'abandoned', 'pending')),
    offboarding_case_id UUID REFERENCES offboarding_cases(id) ON DELETE SET NULL,

    -- Separation context
    separation_reason TEXT,
    is_voluntary BOOLEAN NOT NULL DEFAULT false,

    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pre_term_checks_employee ON pre_termination_checks(employee_id, computed_at DESC);
CREATE INDEX idx_pre_term_checks_company ON pre_termination_checks(company_id, computed_at DESC);
CREATE INDEX idx_pre_term_checks_band ON pre_termination_checks(company_id, overall_band);
```

### Modified Tables

```sql
-- offboarding_cases: add reference to the risk check
ALTER TABLE offboarding_cases
    ADD COLUMN IF NOT EXISTS pre_termination_check_id UUID REFERENCES pre_termination_checks(id);

-- er_cases: add involved_employees array for cross-referencing
-- (currently employee linkage is only via intake_context JSONB which is unstructured)
ALTER TABLE er_cases
    ADD COLUMN IF NOT EXISTS involved_employee_ids UUID[] DEFAULT '{}';
```

## 6. API Design

### Endpoints

#### `POST /employees/{employee_id}/pre-termination-check`

Run a pre-termination risk check without creating an offboarding case. Used for "what-if" analysis.

**Auth**: `require_admin_or_client`
**Request body**:
```json
{
  "separation_reason": "Performance — failed to meet Q4 targets",
  "is_voluntary": false
}
```

**Response**: Full risk report (see 4.3 output schema)

**Async behavior**: The dimension scans run in parallel (they query independent tables). The AI narrative is generated after scoring completes. Total expected time: 3-8 seconds depending on data volume and Gemini response time. Use SSE streaming for the AI narrative portion (same pattern as compliance scans).

#### `GET /employees/{employee_id}/pre-termination-checks`

List all prior pre-termination checks for an employee.

**Auth**: `require_admin_or_client`
**Response**: Array of risk reports, sorted by `computed_at DESC`

#### `POST /pre-termination-checks/{check_id}/acknowledge`

Acknowledge a high/critical risk check to allow the offboarding to proceed.

**Auth**: `require_admin_or_client` (must be a different user than the one who initiated the check for high/critical)
**Request body**:
```json
{
  "notes": "Consulted with employment counsel (Jane Smith, 2026-03-06). Counsel confirmed termination is defensible based on documented PIP failure and unrelated to the ER complaint. Proceeding with standard separation."
}
```

#### `PATCH /pre-termination-checks/{check_id}/outcome`

Update the outcome after a decision is made.

**Auth**: `require_admin_or_client`
**Request body**:
```json
{
  "outcome": "proceeded"
}
```

#### `GET /pre-termination-checks/analytics`

Aggregate analytics for the company (or broker portfolio).

**Auth**: `require_admin_or_client` (admin can pass `company_id` query param)
**Response**:
```json
{
  "total_checks": 47,
  "by_band": { "low": 28, "moderate": 12, "high": 5, "critical": 2 },
  "by_outcome": { "proceeded": 35, "modified": 4, "abandoned": 3, "pending": 5 },
  "override_rate": 0.14,
  "avg_score": 31,
  "most_common_red_flags": [
    { "dimension": "documentation", "count": 18 },
    { "dimension": "er_cases", "count": 7 }
  ],
  "period": "last_12_months"
}
```

### Modified Endpoints

#### `POST /employees/{employee_id}/offboarding` (modified)

For involuntary separations (`is_voluntary: false`):

1. If no `pre_termination_check_id` is provided, automatically run the check
2. If the check result is high/critical and `risk_acknowledged` is not `true`, return the risk report with HTTP 409:
   ```json
   {
     "detail": "Pre-termination risk check required",
     "risk_report": { ... },
     "requires_acknowledgment": true
   }
   ```
3. If `risk_acknowledged: true` and `acknowledgment_notes` are provided, create the offboarding case and link the risk check
4. For low/moderate risk, create the offboarding case normally and link the risk check

**New request fields**:
```json
{
  "last_day": "2026-03-15",
  "reason": "Performance",
  "is_voluntary": false,
  "assign_default_tasks": true,
  "pre_termination_check_id": "uuid (optional, reuse existing check)",
  "risk_acknowledged": true,
  "acknowledgment_notes": "Consulted counsel, proceeding."
}
```

## 7. Frontend Design

### 7.1 Employee Profile — Separation Button

Add an "Initiate Separation" button to the employee detail view. Clicking it opens a modal:

**Separation Modal** (Step 1 — Context):
- Voluntary / Involuntary toggle
- Separation reason (free text + dropdown categories: performance, conduct, layoff/RIF, restructuring, resignation, mutual agreement)
- Proposed last day (date picker)
- "Run Risk Check" button (involuntary) / "Proceed to Offboarding" button (voluntary)

**Risk Report View** (Step 2 — appears after risk check completes):
- Overall risk band displayed prominently (color-coded: green/yellow/orange/red)
- 8 dimension cards, each showing:
  - Flag status icon (green check / yellow warning / red alert)
  - Dimension name
  - One-line summary
  - Expandable detail section
- Recommended actions as a checklist
- AI narrative section (collapsible, rendered as formatted text)
- Action buttons based on risk level:
  - **Low/Moderate**: "Proceed to Offboarding" (primary), "Cancel" (secondary)
  - **High/Critical**: "Request Sign-off" (opens acknowledgment form), "Cancel" (secondary)

**Acknowledgment Form** (Step 3 — high/critical only):
- Required: notes field explaining why the separation should proceed despite risk
- Required: checkbox confirming legal counsel was consulted (for critical)
- Submit creates the acknowledgment and the offboarding case

### 7.2 Pre-Termination Check History

On the employee profile, add a "Risk Checks" tab showing all prior pre-termination checks for that employee. Each entry shows:
- Date, initiated by, overall band, outcome
- Expandable to show full report

### 7.3 Company-Level Analytics

Add a "Separation Risk" card to the company risk assessment page showing:
- Total checks run (12-month rolling)
- Band distribution (bar chart)
- Override rate (% of high/critical checks that proceeded)
- Most common red flag dimensions
- Trend line (checks per month, avg score per month)

### 7.4 Broker Portfolio View (Future)

Add columns to the broker portfolio dashboard:
- "Risk Checks" — total checks run by the client
- "Override Rate" — % of high/critical that proceeded
- "Avg Separation Risk" — average pre-termination check score

## 8. Integration Points

### 8.1 Existing Modules Used

| Module | Data Consumed | How |
|--------|---------------|-----|
| **ER Copilot** | `er_cases` with status, category, `involved_employee_ids` | Direct DB query for open/recent cases involving the employee |
| **IR Incidents** | `ir_incidents` with `involved_employee_ids`, reporter email | Query for incidents where employee is involved or is the reporter |
| **PTO/Leave** | `pto_requests` with dates, type, status | Query for active or recent leave requests |
| **Employees** | `employees` with `start_date`, `manager_id`, `org_id` | Tenure calculation, manager identification |
| **Performance Reviews** | Review records (if review system stores per-employee data) | Check recency and score of last review |
| **Risk Assessment Service** | `_band()` function, scoring patterns | Reuse band thresholds and scoring normalization |
| **Gemini AI** | `generate_recommendations()` pattern | Same client setup, model fallback, and JSON parsing |
| **Offboarding** | `offboarding_cases`, `offboarding_tasks` | Link risk check to offboarding case, gate involuntary separations |
| **IR Consistency** | `ir_consistency.py` patterns | Adapt consistency analysis for termination consistency checking |

### 8.2 New Cross-References Needed

- `er_cases.involved_employee_ids` — structured employee linkage (currently only in unstructured `intake_context`)
- Employee → IR incident linkage is already via `ir_incidents.involved_employee_ids` (exists)
- Employee → PTO requests linkage is via `pto_requests.employee_id` (exists)

## 9. Implementation Plan

### Phase 1: Core Risk Engine (MVP)

**Scope**: Backend service + basic frontend

1. Create `pre_termination_checks` table (Alembic migration)
2. Add `involved_employee_ids` to `er_cases` (Alembic migration)
3. Add `pre_termination_check_id` to `offboarding_cases` (Alembic migration)
4. Build `pre_termination_service.py`:
   - 8 dimension scan functions (parallel execution via `asyncio.gather`)
   - Score normalization and band calculation
   - Gemini narrative generation
5. Build API endpoints:
   - `POST /employees/{id}/pre-termination-check`
   - `GET /employees/{id}/pre-termination-checks`
   - `POST /pre-termination-checks/{id}/acknowledge`
   - `PATCH /pre-termination-checks/{id}/outcome`
6. Modify `POST /employees/{id}/offboarding` to require risk check for involuntary
7. Frontend: separation modal with risk report view
8. Frontend: acknowledgment flow for high/critical

**MVP dimension coverage**:
- Dimensions 1-4 (ER cases, IR involvement, leave status, protected activity): full implementation
- Dimension 5 (documentation): check for performance review existence/recency only (no PIP tracking yet)
- Dimension 6 (tenure/timing): tenure calculation only (no benefit vesting tracking yet)
- Dimension 7 (consistency): basic same-reason comparison with minimum threshold
- Dimension 8 (manager profile): ER case and termination rate vs. company average

### Phase 2: Enhanced Intelligence

- Progressive discipline tracker (verbal → written → PIP → termination)
- Benefit vesting milestone tracking
- EEOC charge / agency complaint intake (dedicated table and workflow)
- Richer consistency analysis leveraging IR consistency engine patterns
- Automated follow-up: track whether a claim was filed within 12 months post-termination

### Phase 3: Broker Integration

- Broker portfolio dashboard: separation risk metrics per client
- Underwriting summary export: include pre-termination check statistics
- Automated broker alerts when a client's override rate exceeds threshold
- Benchmark: "Your client's override rate vs. platform average"

## 10. Risk and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| HR sees it as friction | Low adoption | Make voluntary separations frictionless; only gate involuntary. Show value via the narrative, not just the score. |
| False positives erode trust | Users ignore flags | Tune thresholds conservatively. Track override rates and adjust. Use "yellow" (warning) more than "red" (blocking) in early rollout. |
| Incomplete data leads to inaccurate checks | False sense of security | Clearly label dimensions with "insufficient data" rather than "green." Never say "no risk" — say "no risk signals detected in available data." |
| Legal liability from the tool itself | Platform liability if the tool says "low risk" and a claim is filed | Prominent disclaimer: "This is a risk screening tool, not legal advice. Consult employment counsel for all termination decisions." |
| Gemini narrative quality | Misleading or legally imprecise narratives | Constrain the prompt to objective observations. Include "this is not legal advice" framing. Allow HR to edit/redact the narrative before sharing. |
| Performance impact | Slow UI if scans take too long | Run dimension scans in parallel. Cache dimension data that doesn't change frequently. Use SSE for the AI narrative. Target <5s for score, <10s for full report with narrative. |

## 11. Open Questions

1. **PIP/Warning tracking**: Should Phase 1 include a lightweight progressive discipline tracker, or should documentation completeness be limited to performance review checks?
2. **Dual sign-off**: For critical risk, should the system require sign-off from someone other than the initiator (separation of duties), or is a single senior HR acknowledgment sufficient?
3. **Voluntary separation checks**: Should the system run a check on voluntary separations at all (to detect potential constructive discharge patterns), or skip entirely?
4. **Retention of narratives**: Should AI narratives be stored permanently or regenerated on demand? Permanent storage is better for audit trail but creates a discoverable document.
5. **Manager notification**: Should the system notify the employee's manager's manager (skip-level) when a high/critical check is generated, or only the HR team?
