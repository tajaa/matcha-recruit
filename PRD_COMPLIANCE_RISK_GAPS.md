# PRD: Compliance Risk Gap Closure (7 Features)

## Context

Matcha is an **AI-native HR risk intelligence platform** sold through insurance brokers. The core value is the closed loop: incident → investigation → risk-scored termination decision → post-termination tracking. These 7 gaps strengthen that core — they're not HRIS features, they're compliance risk features that belong in a platform like this.

Recruiting is deprecated. This is purely HR compliance/ER work.

---

## Feature 1: Retaliation Risk Detection (Dimension 9 of Pre-Term Scan)

### Why
Retaliation is the #1 EEOC charge category (>55% of all charges). The platform already has the data — IR reports, ER cases, progressive discipline, agency charges — but doesn't cross-reference them to detect retaliation patterns.

### What Exists
- Pre-term scan has 8 dimensions in `server/app/matcha/services/pre_termination_service.py`
- Dimension 4 (`scan_protected_activity`) already finds ER complaints, IR reports, and agency charges
- `progressive_discipline` table has `employee_id`, `discipline_type`, `issued_date`
- Scan functions follow a consistent pattern: `async def scan_*(employee_id, company_id, conn) -> PreTermDimensionResult`
- Score normalization: `max_possible = 240` (8 dims × 30 pts) → needs to become `270` (9 dims × 30 pts)

### Implementation

**File: `server/app/matcha/services/pre_termination_service.py`**

1. Add `scan_retaliation_risk()` as Dimension 9:
   - Query `ir_incidents` WHERE `reported_by_email` = employee's email, get dates
   - Query `er_cases` WHERE employee is `complainant` in `involved_employees`, get dates
   - Query `progressive_discipline` WHERE `employee_id` = employee, get `issued_date`
   - Query `offboarding_cases` WHERE `employee_id` = employee (termination dates)
   - For each protected activity event, check if any discipline/adverse action occurred within a configurable window (default 90 days after)
   - Red: discipline/termination within 90 days of protected activity
   - Yellow: discipline/termination within 180 days
   - Green: no temporal overlap
   - Include timeline in `details`: `[{protected_event, adverse_event, days_between}]`

2. Add to `scan_specs` list (line ~1528):
   ```python
   ("retaliation_risk", scan_retaliation_risk(employee_id, company_id, conn)),
   ```

3. Update `max_possible` from `240` to `270` (line ~1547)

4. Update module docstring to list 9 dimensions

**File: `server/app/matcha/routes/pre_termination.py`**
- No route changes needed — the scan is auto-included in the check result

**File: `server/app/matcha/routes/er_copilot.py`**
- Add a `GET /api/er/cases/{case_id}/retaliation-risk` endpoint that checks if involved employees have received adverse actions since the case was opened
- Returns: `{at_risk: bool, events: [{employee_id, event_type, event_date, days_since_case}]}`

**Frontend: update pre-term check result display** to show dimension 9

### Migration
None — reads from existing tables only.

---

## Feature 2: Training Compliance

### Why
CA SB 1343 (harassment prevention, 2+ employees), NY SAHPA (all employees annually), IL Human Rights Act (all employees annually). A compliance platform that can scan jurisdiction requirements but can't track whether training was completed is incomplete.

### Implementation

**Migration: `server/alembic/versions/XXX_add_training_compliance.py`**

```sql
CREATE TABLE IF NOT EXISTS training_requirements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    training_type VARCHAR(50) NOT NULL,  -- harassment_prevention, safety, food_handler, osha, custom
    jurisdiction VARCHAR(50),            -- CA, NY, IL, federal, or NULL for company-wide
    frequency_months INTEGER,            -- recurrence interval (24 for CA harassment = every 2 years)
    applies_to VARCHAR(50) DEFAULT 'all', -- all, supervisors, non_supervisors, department:{name}
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS training_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    requirement_id UUID REFERENCES training_requirements(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    training_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'assigned',  -- assigned, in_progress, completed, expired, waived
    assigned_date DATE NOT NULL DEFAULT CURRENT_DATE,
    due_date DATE,
    completed_date DATE,
    expiration_date DATE,  -- computed from completed_date + frequency_months
    provider VARCHAR(255),
    certificate_number VARCHAR(100),
    score DECIMAL(5,2),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_training_records_company ON training_records(company_id);
CREATE INDEX idx_training_records_employee ON training_records(employee_id);
CREATE INDEX idx_training_records_status ON training_records(status);
CREATE INDEX idx_training_records_due_date ON training_records(due_date);
CREATE INDEX idx_training_requirements_company ON training_requirements(company_id);
```

**File: `server/app/matcha/routes/training.py`** (new)

Routes (all gated by `require_feature("training")`):
- `POST /api/training/requirements` — create training requirement
- `GET /api/training/requirements` — list company requirements
- `PUT /api/training/requirements/{id}` — update requirement
- `DELETE /api/training/requirements/{id}` — deactivate requirement
- `POST /api/training/records` — assign training to employee(s)
- `POST /api/training/records/bulk-assign` — assign requirement to all matching employees
- `GET /api/training/records` — list records with filters (employee, status, overdue)
- `PUT /api/training/records/{id}` — update record (mark complete, add certificate)
- `GET /api/training/compliance` — compliance dashboard: per-requirement completion rates, overdue counts, employees missing mandatory training
- `GET /api/training/overdue` — employees with overdue training (for alerts/notifications)

**File: `server/app/matcha/routes/__init__.py`**
- Import and mount: `matcha_router.include_router(training_router, prefix="/training", tags=["training"], dependencies=[Depends(require_feature("training"))])`

**File: `server/app/matcha/services/pre_termination_service.py`**
- In `scan_documentation()` (Dimension 5), add a check: does the employee have overdue mandatory training? If yes, add to documentation gaps.

**Frontend: `client/src/pages/TrainingCompliance.tsx`** (new)
- Training requirements table (company-level)
- Employee training records table with status badges
- Compliance dashboard: grid showing requirement × employee completion
- Overdue alerts section
- Bulk assign modal

**Feature flag:** Add `"training"` to `enabled_features` options.

---

## Feature 3: I-9 Employment Eligibility Tracking

### Why
Federal requirement (8 U.S.C. § 1324a) for every U.S. employee. ICE fines $281–$2,789 per paperwork violation. A compliance platform without I-9 tracking has a credibility gap with brokers.

### Implementation

**Migration: `server/alembic/versions/XXX_add_i9_tracking.py`**

```sql
CREATE TABLE IF NOT EXISTS i9_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    status VARCHAR(30) NOT NULL DEFAULT 'pending_section1',
    -- section1: employee info (completed by employee)
    section1_completed_date DATE,
    -- section2: employer verification (completed by employer within 3 business days of hire)
    section2_completed_date DATE,
    section2_completed_by UUID REFERENCES users(id),
    document_title VARCHAR(100),       -- e.g. "US Passport", "EAD + Driver's License"
    list_used VARCHAR(10),             -- list_a, list_b_c (List A alone, or List B + C)
    document_number VARCHAR(100),
    issuing_authority VARCHAR(100),
    expiration_date DATE,              -- NULL for non-expiring docs (US passport cards, etc.)
    -- section3: reverification (when work auth expires)
    reverification_date DATE,
    reverification_document VARCHAR(100),
    reverification_expiration DATE,
    reverification_by UUID REFERENCES users(id),
    -- E-Verify (optional)
    everify_case_number VARCHAR(50),
    everify_status VARCHAR(30),        -- initial, referred, employment_authorized, final_nonconfirmation
    -- metadata
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(employee_id)  -- one active I-9 per employee
);

CREATE INDEX idx_i9_records_company ON i9_records(company_id);
CREATE INDEX idx_i9_records_expiration ON i9_records(expiration_date);
CREATE INDEX idx_i9_records_status ON i9_records(status);
```

**Status flow:** `pending_section1` → `pending_section2` → `complete` → `reverification_needed` → `reverified`

**File: `server/app/matcha/routes/i9.py`** (new)

Routes:
- `POST /api/i9` — create I-9 record for employee
- `GET /api/i9` — list I-9 records for company (with filters: status, expiring_within_days)
- `GET /api/i9/{employee_id}` — get I-9 for specific employee
- `PUT /api/i9/{id}` — update I-9 (complete section 1/2, add reverification)
- `GET /api/i9/expiring` — employees with documents expiring within N days (default 90)
- `GET /api/i9/incomplete` — employees missing I-9 or with incomplete sections
- `GET /api/i9/compliance-summary` — completion rate, overdue count, expiring soon count

**File: `server/app/matcha/routes/__init__.py`**
- Mount under `/api/i9`

**Integration points:**
- **Onboarding**: when employee is created, auto-create I-9 record with `pending_section1` status. Add I-9 as onboarding task.
- **Pre-term scan**: in `scan_documentation()`, check if I-9 is complete. Missing I-9 = documentation gap.
- **Compliance dashboard**: I-9 completion rate as a compliance metric.

**Frontend: `client/src/pages/I9Management.tsx`** (new)
- I-9 status table (complete, pending, expiring, overdue)
- Expiration alert cards
- Per-employee I-9 detail drawer
- Bulk incomplete list

**Feature flag:** Add `"i9"` to `enabled_features` options.

---

## Feature 4: OSHA 300/301 Log

### Why
Required for 10+ employee companies (29 CFR 1904). IR incidents already exist with AI categorization. Adding OSHA recordability determination and log generation extends an existing module into an industry-unlocking feature (manufacturing, healthcare, construction).

### What Exists
- `ir_incidents` table with `incident_type` (safety, behavioral, property, near_miss, other)
- `SafetyData` model already has: `body_parts`, `injury_type`, `treatment`, `lost_days`, `equipment_involved`, `osha_recordable` (boolean field already exists!)
- AI analysis already does categorization and severity

### Implementation

**Migration: `server/alembic/versions/XXX_add_osha_fields.py`**

```sql
-- Add OSHA-specific columns to ir_incidents
ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS osha_recordable BOOLEAN;
ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS osha_case_number VARCHAR(20);
ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS osha_classification VARCHAR(30);
  -- death, days_away, restricted_duty, medical_treatment, loss_of_consciousness, significant_injury
ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS days_away_from_work INTEGER DEFAULT 0;
ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS days_restricted_duty INTEGER DEFAULT 0;
ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS date_of_death DATE;
ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS osha_form_301_data JSONB;

-- OSHA 300A annual summary cache
CREATE TABLE IF NOT EXISTS osha_annual_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    establishment_name VARCHAR(255),
    total_cases INTEGER DEFAULT 0,
    total_deaths INTEGER DEFAULT 0,
    total_days_away_cases INTEGER DEFAULT 0,
    total_restricted_cases INTEGER DEFAULT 0,
    total_other_recordable INTEGER DEFAULT 0,
    total_days_away INTEGER DEFAULT 0,
    total_days_restricted INTEGER DEFAULT 0,
    total_injuries INTEGER DEFAULT 0,
    total_skin_disorders INTEGER DEFAULT 0,
    total_respiratory INTEGER DEFAULT 0,
    total_poisonings INTEGER DEFAULT 0,
    total_hearing_loss INTEGER DEFAULT 0,
    total_other_illnesses INTEGER DEFAULT 0,
    average_employees INTEGER,
    total_hours_worked INTEGER,
    certified_by VARCHAR(255),
    certified_title VARCHAR(255),
    certified_date DATE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(company_id, year)
);
```

**File: `server/app/matcha/routes/ir_incidents.py`** (extend)

New endpoints:
- `PUT /api/ir/incidents/{id}/osha` — set OSHA recordability determination + classification + days away/restricted
- `GET /api/ir/incidents/osha/300-log` — generate OSHA 300 log for year (query param: `year`)
  - Returns JSON array of all recordable incidents with required 300 columns
- `GET /api/ir/incidents/osha/300-log/csv` — export as CSV matching OSHA 300 format
- `GET /api/ir/incidents/osha/301/{id}` — generate 301 form data for a specific incident
- `GET /api/ir/incidents/osha/300a` — generate annual 300A summary for year
- `POST /api/ir/incidents/{id}/osha/determine` — AI-assisted recordability determination
  - Use Gemini to analyze incident details against OSHA recordability criteria
  - Returns: `{recordable: bool, classification: str, reasoning: str}`

**File: `server/app/matcha/models/ir_incident.py`** (extend)
- Add `OshaRecordabilityUpdate` model
- Add `Osha300LogEntry`, `Osha300ASummary`, `Osha301Form` response models

**Frontend: extend IR Incidents page**
- Add "OSHA" tab to IRList page
- OSHA recordability toggle on incident detail
- 300 Log table view with CSV export button
- 300A summary card
- AI recordability determination button

No new feature flag — this is part of the existing `incidents` feature.

---

## Feature 5: COBRA Qualifying Event Tracking

### Why
Employer must notify plan administrator within 30 days of qualifying event; admin must notify beneficiaries within 14 days (44-day total). DOL fines $110/day per qualified beneficiary for late notice. Offboarding already triggers — we just need to capture the COBRA event.

### Implementation

**Migration: `server/alembic/versions/XXX_add_cobra_tracking.py`**

```sql
CREATE TABLE IF NOT EXISTS cobra_qualifying_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    -- termination, reduction_in_hours, divorce, dependent_aging_out, medicare_enrollment, employee_death
    event_date DATE NOT NULL,
    -- deadlines
    employer_notice_deadline DATE NOT NULL,      -- event_date + 30 days
    administrator_notice_deadline DATE NOT NULL,  -- event_date + 44 days
    election_deadline DATE NOT NULL,              -- administrator_notice + 60 days
    -- continuation period
    continuation_months INTEGER NOT NULL DEFAULT 18, -- 18 or 36 depending on event
    continuation_end_date DATE NOT NULL,
    -- tracking
    employer_notice_sent BOOLEAN DEFAULT false,
    employer_notice_sent_date DATE,
    administrator_notified BOOLEAN DEFAULT false,
    administrator_notified_date DATE,
    election_received BOOLEAN,        -- NULL = pending, true = elected, false = waived
    election_received_date DATE,
    -- status
    status VARCHAR(30) NOT NULL DEFAULT 'pending_notice',
    -- pending_notice, notice_sent, election_pending, elected, waived, expired, terminated
    beneficiary_count INTEGER DEFAULT 1,
    notes TEXT,
    offboarding_case_id UUID REFERENCES offboarding_cases(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_cobra_events_company ON cobra_qualifying_events(company_id);
CREATE INDEX idx_cobra_events_employee ON cobra_qualifying_events(employee_id);
CREATE INDEX idx_cobra_events_deadline ON cobra_qualifying_events(employer_notice_deadline);
CREATE INDEX idx_cobra_events_status ON cobra_qualifying_events(status);
```

**File: `server/app/matcha/routes/cobra.py`** (new)

Routes:
- `POST /api/cobra/events` — create qualifying event (manual, or auto-triggered)
- `GET /api/cobra/events` — list events with filters (status, overdue)
- `GET /api/cobra/events/{id}` — get event detail
- `PUT /api/cobra/events/{id}` — update status (notice sent, election received)
- `GET /api/cobra/overdue` — events past deadline that haven't been actioned
- `GET /api/cobra/dashboard` — summary: pending notices, overdue count, upcoming deadlines

**Integration with offboarding:**

**File: `server/app/matcha/routes/employees.py`** (extend)
- When an offboarding case is created (`POST /employees/{id}/offboard`), check if company has 20+ employees. If yes, auto-create COBRA qualifying event with:
  - `event_type`: `termination` (involuntary) or `termination` (voluntary)
  - `event_date`: `last_day` from offboarding case
  - `employer_notice_deadline`: event_date + 30 days
  - `administrator_notice_deadline`: event_date + 44 days
  - `election_deadline`: administrator_notice_deadline + 60 days
  - `continuation_months`: 18 (standard for termination/reduction in hours)
  - Link `offboarding_case_id`

**Frontend: COBRA section within Employees or as standalone tab**
- Upcoming deadlines dashboard
- Event status cards with action buttons (mark notice sent, record election)
- Overdue alerts (red badges)

**Feature flag:** Add `"cobra"` to `enabled_features` options (or bundle with `employees`).

---

## Feature 6: Separation Agreements + ADEA Period Tracking

### Why
ADEA (Age Discrimination in Employment Act) requires 21-day consideration + 7-day revocation period for employees 40+. Group layoffs require 45-day consideration + itemized disclosure. Courts void agreements that don't track these periods correctly. This is a natural extension of the pre-termination → offboarding flow.

### Implementation

**Migration: `server/alembic/versions/XXX_add_separation_agreements.py`**

```sql
CREATE TABLE IF NOT EXISTS separation_agreements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    offboarding_case_id UUID REFERENCES offboarding_cases(id),
    pre_term_check_id UUID REFERENCES pre_termination_checks(id),
    -- agreement details
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    -- draft, presented, consideration_period, signed, revoked, effective, expired, void
    severance_amount DECIMAL(12,2),
    severance_weeks INTEGER,
    severance_description TEXT,
    additional_terms JSONB,           -- non-compete, non-disparagement, etc.
    -- ADEA compliance (if employee is 40+)
    employee_age_at_separation INTEGER,
    is_adea_applicable BOOLEAN DEFAULT false,
    is_group_layoff BOOLEAN DEFAULT false,
    -- period tracking
    presented_date DATE,
    consideration_period_days INTEGER, -- 21 (individual) or 45 (group layoff)
    consideration_deadline DATE,       -- presented_date + consideration_period_days
    signed_date DATE,
    revocation_period_days INTEGER DEFAULT 7,
    revocation_deadline DATE,          -- signed_date + 7 days
    effective_date DATE,               -- revocation_deadline + 1 day (if not revoked)
    revoked_date DATE,
    -- group layoff disclosure (ADEA/OWBPA)
    decisional_unit TEXT,              -- description of the group
    group_disclosure JSONB,            -- [{job_title, age, selected_for_layoff: bool}]
    -- metadata
    created_by UUID REFERENCES users(id),
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_separation_agreements_company ON separation_agreements(company_id);
CREATE INDEX idx_separation_agreements_employee ON separation_agreements(employee_id);
CREATE INDEX idx_separation_agreements_status ON separation_agreements(status);
```

**File: `server/app/matcha/routes/separation.py`** (new)

Routes:
- `POST /api/separation-agreements` — create agreement (auto-compute ADEA if employee DOB is available, otherwise require `employee_age_at_separation`)
- `GET /api/separation-agreements` — list for company
- `GET /api/separation-agreements/{id}` — detail
- `PUT /api/separation-agreements/{id}` — update (present, record signature, record revocation)
- `PUT /api/separation-agreements/{id}/present` — mark as presented, start consideration period
- `PUT /api/separation-agreements/{id}/sign` — record signature, start revocation period
- `PUT /api/separation-agreements/{id}/revoke` — record revocation
- `GET /api/separation-agreements/{id}/status` — current status with period countdown
  - Returns: `{status, days_remaining_consideration, days_remaining_revocation, is_effective}`

**Validation rules (enforced server-side):**
- Cannot mark `signed` before `consideration_deadline`
- Cannot mark `effective` before `revocation_deadline`
- If `revoked_date` is set, status → `revoked`, agreement is void
- If `is_group_layoff` and `is_adea_applicable`, require `group_disclosure` JSONB

**Integration:**
- When offboarding case is involuntary, prompt to create separation agreement
- Link to pre-termination check results

**Frontend: `client/src/pages/SeparationAgreements.tsx`** (new, or tab within offboarding)
- Agreement creation form with ADEA auto-detection
- Timeline visualization: presented → consideration period countdown → signed → revocation countdown → effective
- Group layoff disclosure table
- Status badges: "In Consideration (14 days remaining)", "Revocation Period (3 days remaining)", "Effective"

---

## Feature 7: Employee Status Tracking (Schema Enhancement)

### Why
An "active" employee on FMLA leave looks the same as one working full-time. This matters because the pre-termination scan should treat them differently, headcount reports should distinguish them, and compliance checks (e.g., COBRA eligibility) depend on employment status.

### Implementation

**Migration: `server/alembic/versions/XXX_add_employee_status.py`**

```sql
ALTER TABLE employees ADD COLUMN IF NOT EXISTS employment_status VARCHAR(30) DEFAULT 'active';
-- active, on_leave, suspended, on_notice, furloughed, terminated, offboarded

-- Backfill existing employees
UPDATE employees SET employment_status = 'terminated' WHERE termination_date IS NOT NULL;
UPDATE employees SET employment_status = 'active' WHERE employment_status IS NULL;

ALTER TABLE employees ADD COLUMN IF NOT EXISTS status_changed_at TIMESTAMP;
ALTER TABLE employees ADD COLUMN IF NOT EXISTS status_reason TEXT;
```

**File: `server/app/matcha/routes/employees.py`** (extend)
- Add `PUT /api/employees/{id}/status` — change employment status with reason
  - Validates transitions (can't go from `terminated` to `on_leave`)
  - Records `status_changed_at` and `status_reason`
- Update employee list endpoint to support filtering by `employment_status`
- Update offboarding flow to set status to `on_notice` when case is created, `terminated`/`offboarded` when completed

**Integration points:**
- **Pre-term scan** `scan_leave_status()`: check `employment_status` field in addition to PTO requests
- **Leave routes**: when leave is approved, set `employment_status = 'on_leave'`; when leave ends, set back to `active`
- **Progressive discipline**: when suspension is issued, set `employment_status = 'suspended'`
- **COBRA**: `employment_status` change to `terminated` triggers COBRA check
- **Employee list UI**: status badge column, filter by status

**Frontend:** Update Employees page to show status badges and filter dropdown.

---

## Feature Flag Updates

Add to the feature flag system (`enabled_features` JSONB):
- `training` — Training compliance module
- `i9` — I-9 tracking module
- `cobra` — COBRA event tracking
- `separation_agreements` — Separation agreement generation

Features that don't need flags (extend existing modules):
- Retaliation detection (part of pre-term scan, always on)
- OSHA 300 log (part of IR incidents)
- Employee status (schema-level, always on)

---

## Router Mounting Summary

**File: `server/app/matcha/routes/__init__.py`**

Add imports and mounts for:
```python
from .training import router as training_router
from .i9 import router as i9_router
from .cobra import router as cobra_router
from .separation import router as separation_router

matcha_router.include_router(training_router, prefix="/training", tags=["training"],
    dependencies=[Depends(require_feature("training"))])
matcha_router.include_router(i9_router, prefix="/i9", tags=["i9"],
    dependencies=[Depends(require_feature("i9"))])
matcha_router.include_router(cobra_router, prefix="/cobra", tags=["cobra"],
    dependencies=[Depends(require_feature("cobra"))])
matcha_router.include_router(separation_router, prefix="/separation-agreements", tags=["separation"],
    dependencies=[Depends(require_feature("separation_agreements"))])
```

---

## Build Order

| # | Feature | Type | Effort | Dependencies |
|---|---------|------|--------|-------------|
| 1 | Retaliation Detection | Extend pre_termination_service.py | Small (1 function + score update) | None |
| 2 | Employee Status | Migration + extend employees.py | Small (schema + 1 endpoint) | None |
| 3 | Training Compliance | New module | Medium (migration + routes + frontend) | None |
| 4 | I-9 Tracking | New module | Medium (migration + routes + frontend) | None |
| 5 | OSHA 300 Log | Extend IR incidents | Medium (migration + endpoints + AI determination) | None |
| 6 | COBRA Event Tracking | New module | Medium (migration + routes + offboarding integration) | Employee Status (#2) |
| 7 | Separation Agreements | New module | Medium (migration + routes + ADEA logic + frontend) | Employee Status (#2) |

Items 1–2 can ship immediately. Items 3–5 are independent and can be built in parallel. Items 6–7 depend on #2 for status tracking.

---

## Verification

1. **Retaliation detection**: Create employee → file IR incident → add progressive discipline record 30 days later → run pre-term check → verify dimension 9 shows red flag with "discipline 30 days after incident report"
2. **Employee status**: Create employee → approve FMLA leave → verify status changes to `on_leave` → end leave → verify status returns to `active`
3. **Training compliance**: Create harassment prevention requirement (CA, 24-month frequency) → assign to employee → verify overdue after due date → mark complete → verify expiration set 24 months out
4. **I-9 tracking**: Create employee → auto-creates I-9 record → complete section 1 & 2 → set EAD expiration 6 months out → verify appears in "expiring within 90 days" list at month 3
5. **OSHA 300 log**: Create safety incident with `lost_days: 5` → run AI recordability determination → mark recordable → verify appears on 300 log export → verify 300A summary counts
6. **COBRA**: Company has 25 employees → initiate offboarding → verify COBRA qualifying event auto-created with correct deadlines → mark notice sent → record election
7. **Separation agreement (ADEA)**: Employee age 52 → create separation agreement → verify 21-day consideration period auto-set → present agreement → verify cannot mark signed before deadline → sign on day 22 → verify 7-day revocation countdown starts → verify effective date is day 29
