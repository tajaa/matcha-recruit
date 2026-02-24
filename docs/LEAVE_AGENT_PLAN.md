# Leave & Accommodation Compliance Agent — Feature Map

This document maps each agent capability to existing Matcha infrastructure, identifying what to extend vs. create new. Each section is independently implementable.

---

## 1. Intake (Extended Leave Requests)

**Strategy:** Extend the Employee Portal / `time_off` system.

### What Exists

**`pto_requests` table** — short-duration time off:
- Columns: `id`, `employee_id`, `request_type` (vacation/sick/personal/other), `start_date`, `end_date`, `hours`, `reason`, `status` (pending/approved/denied/cancelled), `approved_by`, `approved_at`, `denial_reason`, `created_at`, `updated_at`
- Constraint: `end_date >= start_date`

**`pto_balances` table** — annual balance tracking:
- Columns: `id`, `employee_id`, `year`, `balance_hours`, `accrued_hours`, `used_hours`, `carryover_hours`, `updated_at`
- Unique on `(employee_id, year)`

**Employee self-service routes** (`server/app/matcha/routes/employee_portal.py`):
- `GET /me/pto` → `get_pto_summary()` — returns balance + pending/approved requests
- `POST /me/pto/request` → `submit_pto_request()` — validates dates, checks overlaps, creates pending request
- `DELETE /me/pto/request/{request_id}` → `cancel_pto_request()` — cancels pending requests

**Admin PTO routes** (`server/app/matcha/routes/employees.py`):
- `GET /pto/requests` → `list_pto_requests()` — filter by status
- `PATCH /pto/requests/{request_id}` → `handle_pto_request()` — approve/deny, increments `used_hours`
- `GET /pto/summary` → `get_pto_summary_stats()`

**Pydantic models** (`server/app/matcha/models/employee.py`):
- `PTORequestType = Literal["vacation", "sick", "personal", "other"]`
- `PTORequestStatus = Literal["pending", "approved", "denied", "cancelled"]`
- `PTORequestCreate`, `PTORequestResponse`, `PTOBalanceResponse`, `PTOSummary`

**Employee fields relevant to eligibility:**
- `work_state` (VARCHAR 2) — state code for jurisdiction lookups
- `start_date` (DATE) — hire date for tenure calculations
- `employment_type` (VARCHAR 20) — full_time/part_time/contractor/intern
- `manager_id` (UUID) — for approval routing

### What to Extend

**New `leave_requests` table** — long-duration leaves separate from PTO:

```sql
CREATE TABLE leave_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    leave_type VARCHAR(30) NOT NULL,
    -- 'fmla', 'state_pfml', 'parental', 'bereavement', 'jury_duty',
    -- 'medical', 'military', 'unpaid_loa', 'ada_accommodation'
    reason TEXT,
    start_date DATE NOT NULL,
    end_date DATE,                          -- NULL = open-ended / TBD
    expected_return_date DATE,
    actual_return_date DATE,
    status VARCHAR(30) NOT NULL DEFAULT 'requested',
    -- 'requested', 'eligibility_review', 'approved', 'denied',
    -- 'active', 'extended', 'return_pending', 'completed', 'cancelled'
    intermittent BOOLEAN DEFAULT false,     -- intermittent vs continuous
    intermittent_schedule TEXT,             -- e.g., "3 days/week" or "as needed"
    hours_approved DECIMAL(8,2),            -- for intermittent tracking
    hours_used DECIMAL(8,2) DEFAULT 0,
    denial_reason TEXT,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMP,
    eligibility_data JSONB DEFAULT '{}',    -- cached eligibility check results
    jurisdiction_data JSONB DEFAULT '{}',   -- applicable jurisdiction rules
    linked_accommodation_id UUID,           -- FK to accommodation_cases if ADA-related
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

**New `employee_hours_log` table** — for FMLA 1,250-hour eligibility:

```sql
CREATE TABLE employee_hours_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    hours_worked DECIMAL(8,2) NOT NULL,
    source VARCHAR(30) DEFAULT 'manual',    -- 'manual', 'payroll_import', 'time_clock'
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(employee_id, period_start, period_end)
);
```

**New leave type literal** in `server/app/matcha/models/employee.py`:

```python
LeaveType = Literal[
    "fmla", "state_pfml", "parental", "bereavement",
    "jury_duty", "medical", "military", "unpaid_loa", "ada_accommodation"
]

LeaveStatus = Literal[
    "requested", "eligibility_review", "approved", "denied",
    "active", "extended", "return_pending", "completed", "cancelled"
]
```

**New routes** added to `employee_portal.py` (employee self-service):
- `POST /me/leave/request` — submit extended leave request
- `GET /me/leave` — list my leave requests
- `GET /me/leave/{leave_id}` — leave request details + status timeline

**New routes** added to `employees.py` (admin/client):
- `GET /leave/requests` — list all leave requests (filter by status, type)
- `GET /leave/requests/{leave_id}` — full leave case detail
- `PATCH /leave/requests/{leave_id}` — approve/deny/update status
- `GET /leave/requests/{leave_id}/timeline` — status change history

### Feature Flag

`time_off` (already exists in `KNOWN_FEATURES`)

### Files to Modify

| File | Changes |
|------|---------|
| `server/app/matcha/models/employee.py` | Add `LeaveType`, `LeaveStatus`, request/response models |
| `server/app/matcha/routes/employee_portal.py` | Add employee leave request endpoints |
| `server/app/matcha/routes/employees.py` | Add admin leave management endpoints |
| New migration | Create `leave_requests` and `employee_hours_log` tables |

---

## 2. Jurisdiction-Aware Eligibility

**Strategy:** Extend the Compliance system with leave-specific categories.

### What Exists

**Compliance categories** (`server/app/core/models/compliance.py`):
```python
class ComplianceCategory(str, Enum):
    minimum_wage = "minimum_wage"
    overtime = "overtime"
    sick_leave = "sick_leave"
    workers_comp = "workers_comp"
    business_license = "business_license"
    tax_rate = "tax_rate"
    posting_requirements = "posting_requirements"
```

**Jurisdiction hierarchy** (`server/app/core/services/compliance_service.py`):
- Priority: city (1) → county (2) → state (3) → federal (4)
- `state_preemption_rules` table controls local override allowance per `(state, category)`
- `_filter_with_preemption()` — drops local requirements when preempted
- Employee `work_state` field already links employees to jurisdictions

**Tiered data strategy:**
1. Tier 1: Structured data sources
2. Tier 2: `jurisdiction_requirements` repository cache (freshness check via `last_verified_at`)
3. Tier 2.5: County data reuse when city has no local ordinance
4. Tier 3: Gemini AI research as fallback

**Key tables:**
- `business_locations` — city, state, county, zipcode, auto_check scheduling
- `compliance_requirements` — per-location requirements with jurisdiction_level
- `jurisdiction_reference` — city→county mapping, `has_local_ordinance` flag
- `jurisdictions` — repository index with freshness tracking
- `jurisdiction_requirements` — cached research results

**Category normalization** (`_normalize_category()`): strips spaces/hyphens, lowercases

### What to Extend

**New compliance categories** added to the enum:

```python
# Add to ComplianceCategory:
fmla = "fmla"
state_pfml = "state_pfml"          # State paid family/medical leave (CA PFL, NY PFL, WA PFML, etc.)
parental_leave = "parental_leave"  # State-mandated parental beyond FMLA
bereavement_leave = "bereavement_leave"
military_leave = "military_leave"  # USERRA + state supplements
```

**New preemption seeds** for leave categories:

```sql
-- FMLA is federal floor, states can exceed
INSERT INTO state_preemption_rules (state, category, allows_local_override) VALUES
('CA', 'fmla', true),           -- CFRA exceeds FMLA
('CA', 'state_pfml', true),     -- Local supplements allowed
('NY', 'state_pfml', true),
('WA', 'state_pfml', true),
('OR', 'state_pfml', true);
```

**New `leave_eligibility_service.py`** — cross-references employee data against jurisdiction requirements:

```python
class LeaveEligibilityService:

    async def check_fmla_eligibility(employee_id: UUID) -> FMLAEligibility:
        """
        FMLA eligibility requires:
        1. Employer has 50+ employees within 75 miles
        2. Employee worked 12+ months
        3. Employee worked 1,250+ hours in last 12 months
        Returns: {eligible: bool, reasons: [], hours_worked_12mo: Decimal,
                  months_employed: int, employee_count_75mi: int}
        """

    async def check_state_leave_eligibility(
        employee_id: UUID, leave_type: str, work_state: str
    ) -> StateLeaveEligibility:
        """
        Cross-reference employee against state-specific leave laws.
        Uses compliance_service to fetch jurisdiction requirements for the
        leave category, then checks employee tenure/hours against thresholds.
        Returns: {eligible: bool, state_program: str, requirements: [],
                  benefits: {wage_replacement_pct, max_weeks, job_protection: bool}}
        """

    async def get_all_applicable_leaves(employee_id: UUID) -> list[ApplicableLeave]:
        """
        For a given employee, return all leave types they may be eligible for
        based on their work_state + tenure + hours.
        Checks: federal FMLA, state PFML, state parental, bereavement mandates.
        """
```

### Feature Flag

`compliance` (already exists)

### Files to Modify

| File | Changes |
|------|---------|
| `server/app/core/models/compliance.py` | Add new leave categories to `ComplianceCategory` enum |
| `server/app/core/services/compliance_service.py` | Add leave categories to Gemini research prompts, add preemption seed data |
| New `server/app/matcha/services/leave_eligibility_service.py` | Eligibility checking logic |
| New migration | Seed `state_preemption_rules` with leave categories |

---

## 3. Notice Generation

**Strategy:** Extend the existing WeasyPrint PDF generation pattern from offer letters.

### What Exists

**Offer letter PDF generation** (`server/app/matcha/routes/offer_letters.py`):
- `_generate_offer_letter_html(offer: dict) -> str` — builds complete HTML with embedded CSS
- `_safe(value)` — HTML-escapes all user data
- `_generate_benefits_text(offer)` / `_generate_contingencies_text(offer)` — generates readable text sections
- PDF output: `HTML(string=html_content).write_pdf()` via WeasyPrint
- Response: `StreamingResponse` with `application/pdf` content type

**Document signing** (`server/app/matcha/routes/employee_portal.py:557-632`):
- `sign_document()` — captures `signature_data` (base64) + `signature_ip` (client IP)
- Updates `employee_documents` table: `status='signed'`, `signed_at=NOW()`
- Syncs to `policy_signatures` via `SignatureService.sync_employee_document_signature()`

**`employee_documents` table:**
- Columns: `id`, `org_id`, `employee_id`, `doc_type`, `title`, `description`, `storage_path`, `content`, `status` (draft/pending_signature/signed/expired), `expires_at`, `signed_at`, `signed_ip`, `created_at`, `updated_at`

**S3 upload** (`server/app/core/services/storage.py`):
- `StorageService.upload_file(file_bytes, filename, prefix, content_type)` → returns CloudFront URL
- Key format: `{prefix}/{uuid_hex}{ext}`

### What to Create

**New `leave_notices_service.py`** — reuses the `_generate_*_html()` pattern:

```python
class LeaveNoticesService:

    def generate_fmla_eligibility_notice_html(
        employee: dict, eligibility: FMLAEligibility, company: dict
    ) -> str:
        """
        WH-381 equivalent: Notice of Eligibility and Rights & Responsibilities.
        Must be provided within 5 business days of leave request or learning of
        qualifying reason.
        """

    def generate_fmla_designation_notice_html(
        employee: dict, leave_request: dict, company: dict
    ) -> str:
        """
        WH-382 equivalent: Designation Notice.
        Must be provided within 5 business days of having enough info to determine
        if leave qualifies.
        """

    def generate_ada_interactive_process_letter_html(
        employee: dict, accommodation_case: dict, company: dict
    ) -> str:
        """
        Letter acknowledging accommodation request and initiating interactive process.
        """

    def generate_return_to_work_notice_html(
        employee: dict, leave_request: dict, conditions: dict
    ) -> str:
        """
        Notice of return-to-work requirements (fitness-for-duty cert, etc.)
        """

    async def create_and_store_notice(
        notice_type: str, html_generator: Callable, **kwargs
    ) -> EmployeeDocumentResponse:
        """
        1. Generate HTML via the appropriate generator
        2. Convert to PDF via WeasyPrint
        3. Upload to S3 with prefix="leave-notices"
        4. Insert into employee_documents with status='pending_signature'
        5. Return document record
        """
```

**Notice types for `employee_documents.doc_type`:**
- `fmla_eligibility_notice`
- `fmla_designation_notice`
- `ada_interactive_process`
- `return_to_work_notice`
- `state_leave_notice` (state-specific equivalents)

### Feature Flag

`time_off` (already exists)

### Files to Create/Modify

| File | Changes |
|------|---------|
| New `server/app/matcha/services/leave_notices_service.py` | HTML generators + PDF creation + S3 upload + document record |
| `server/app/matcha/routes/employee_portal.py` | Employee can view/sign leave notices via existing `/me/documents` endpoints |
| `server/app/matcha/routes/employees.py` | Admin endpoint to manually generate a notice for a leave case |

---

## 4. Deadline Tracking

**Strategy:** Extend the compliance auto-check and Celery scheduled task patterns.

### What Exists

**Auto-check scheduling** on `business_locations`:
- `auto_check_enabled` (BOOLEAN, default true)
- `auto_check_interval_days` (INTEGER, default 7)
- `next_auto_check` (TIMESTAMP)
- Logic: when enabled, `next_auto_check = NOW() + INTERVAL '1 day' * interval_days`

**Celery tasks** (`server/app/workers/tasks/compliance_checks.py`):
```python
@celery_app.task(bind=True, max_retries=2)
def run_compliance_check_task(self, location_id, company_id, check_type="scheduled") -> dict

@celery_app.task(bind=True, max_retries=1)
def enqueue_scheduled_compliance_checks(self) -> dict
    # Dispatcher: finds locations due for check, enqueues individual tasks

@celery_app.task(bind=True, max_retries=1)
def run_deadline_escalation(self) -> dict
    # Re-evaluates deadline severities for upcoming legislation
```

**Celery config** (`server/app/workers/celery_app.py`):
- Broker: Redis
- Task time limit: 600s hard / 540s soft
- Late acknowledgment, prefetch=1
- Default retry: 60s, max retries: 3

**Notification patterns** (`server/app/workers/notifications.py`):
- Redis pub/sub: `publish_task_complete()`, `publish_task_progress()`, `publish_task_error()`

### What to Create

**New `leave_deadlines` table:**

```sql
CREATE TABLE leave_deadlines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    leave_request_id UUID REFERENCES leave_requests(id) ON DELETE CASCADE,
    accommodation_case_id UUID,          -- FK added after accommodations table exists
    org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    deadline_type VARCHAR(50) NOT NULL,
    -- 'eligibility_notice_due', 'designation_notice_due',
    -- 'certification_due', 'recertification_due',
    -- 'fitness_for_duty_due', 'response_window_closing',
    -- 'return_date', 'interactive_process_followup'
    due_date DATE NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    -- 'pending', 'completed', 'overdue', 'waived'
    escalation_level INTEGER DEFAULT 0,  -- 0=none, 1=warning sent, 2=overdue sent, 3=escalated to admin
    completed_at TIMESTAMP,
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_leave_deadlines_due_date ON leave_deadlines(due_date);
CREATE INDEX idx_leave_deadlines_status ON leave_deadlines(status);
CREATE INDEX idx_leave_deadlines_leave_request ON leave_deadlines(leave_request_id);
```

**New Celery task** (`server/app/workers/tasks/leave_deadline_checks.py`):

```python
@celery_app.task(bind=True, max_retries=2)
def check_leave_deadlines(self) -> dict:
    """
    Runs daily (Celery beat). For each pending deadline:
    1. If due_date is within 2 business days and escalation_level == 0:
       → Send warning email, set escalation_level = 1
    2. If due_date has passed and escalation_level < 2:
       → Send overdue email, set escalation_level = 2, status = 'overdue'
    3. If overdue for 3+ days and escalation_level < 3:
       → Escalate to admin, set escalation_level = 3
    Returns: {checked: int, warnings_sent: int, overdue_flagged: int, escalated: int}
    """

@celery_app.task(bind=True, max_retries=1)
def create_leave_deadlines(self, leave_request_id: str) -> dict:
    """
    Called when a leave request is approved. Creates all applicable deadlines:
    - FMLA eligibility notice: 5 business days from request
    - FMLA designation notice: 5 business days from sufficient info
    - Medical certification: 15 calendar days from request
    - Recertification: per schedule (30 days, 6 months, etc.)
    - Return date: leave end_date
    """
```

### Feature Flag

`time_off` (already exists)

### Files to Create/Modify

| File | Changes |
|------|---------|
| New migration | Create `leave_deadlines` table |
| New `server/app/workers/tasks/leave_deadline_checks.py` | Deadline checking + escalation tasks |
| `server/app/workers/celery_app.py` | Register new beat schedule entry for daily deadline checks |

---

## 5. Accommodation Cases (Interactive Process)

**Strategy:** New feature modeled after ER Copilot case management.

### What Exists (ER Copilot Analog)

**`er_cases` table** — case lifecycle model:
- Status: `open → in_review → pending_determination → closed`
- Fields: `case_number` (ER-YYYY-MM-SUFFIX), `title`, `description`, `status`, `company_id`, `created_by`, `assigned_to`, `closed_at`

**`er_case_documents` table** — evidence tracking:
- Fields: `document_type` (transcript/policy/email/other), `filename`, `file_path`, `processing_status` (pending/processing/completed/failed), `pii_scrubbed`

**`er_case_analysis` table** — AI analysis caching:
- Fields: `analysis_type` (timeline/discrepancies/policy_check/summary/determination), `analysis_data` (JSONB), `source_documents`
- Unique on `(case_id, analysis_type)`

**`er_audit_log` table** — immutable audit trail:
- Fields: `case_id`, `user_id`, `action`, `entity_type`, `entity_id`, `details` (JSONB), `ip_address`

**AI patterns** (`server/app/matcha/services/er_analyzer.py`):
- Gemini 2.5 Flash with structured JSON prompts
- Analysis types: timeline, discrepancies, policy_check, summary, determination
- Retry logic with schema validation
- Celery async with sync fallback

### What to Create

**New `accommodation_cases` table:**

```sql
CREATE TABLE accommodation_cases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_number VARCHAR(50) NOT NULL UNIQUE,   -- AC-YYYY-MM-SUFFIX
    org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
    linked_leave_id UUID REFERENCES leave_requests(id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    disability_category VARCHAR(50),
    -- 'physical', 'cognitive', 'sensory', 'mental_health',
    -- 'chronic_illness', 'pregnancy', 'other'
    status VARCHAR(50) NOT NULL DEFAULT 'requested',
    -- 'requested', 'interactive_process', 'medical_review',
    -- 'approved', 'denied', 'implemented', 'review', 'closed'
    requested_accommodation TEXT,              -- employee's initial request
    approved_accommodation TEXT,               -- what was actually approved
    denial_reason TEXT,
    undue_hardship_analysis TEXT,              -- if denied, document hardship reasoning
    assigned_to UUID REFERENCES users(id),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP
);
```

**New `accommodation_documents` table:**

```sql
CREATE TABLE accommodation_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES accommodation_cases(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL,
    -- 'medical_certification', 'accommodation_request_form',
    -- 'interactive_process_notes', 'job_description',
    -- 'hardship_analysis', 'approval_letter', 'other'
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    mime_type VARCHAR(100),
    file_size INTEGER,
    uploaded_by UUID REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**New `accommodation_analysis` table:**

```sql
CREATE TABLE accommodation_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID NOT NULL REFERENCES accommodation_cases(id) ON DELETE CASCADE,
    analysis_type VARCHAR(50) NOT NULL,
    -- 'accommodation_suggestions', 'hardship_assessment',
    -- 'job_function_analysis', 'comparable_cases'
    analysis_data JSONB NOT NULL,
    generated_by UUID REFERENCES users(id),
    generated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(case_id, analysis_type)
);
```

**New `accommodation_audit_log` table:**

```sql
CREATE TABLE accommodation_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    case_id UUID REFERENCES accommodation_cases(id) ON DELETE SET NULL,
    user_id UUID REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(50),
    entity_id UUID,
    details JSONB,
    ip_address VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
```

**New routes** (`server/app/matcha/routes/accommodations.py`):

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/accommodations` | POST | Create accommodation case |
| `/api/accommodations` | GET | List cases (filter by status, employee) |
| `/api/accommodations/{case_id}` | GET | Case detail |
| `/api/accommodations/{case_id}` | PUT | Update case (status, assigned_to, accommodation details) |
| `/api/accommodations/{case_id}` | DELETE | Delete case + cascaded data |
| `/api/accommodations/{case_id}/documents` | POST | Upload document |
| `/api/accommodations/{case_id}/documents` | GET | List documents |
| `/api/accommodations/{case_id}/analysis/suggestions` | POST | AI: suggest reasonable accommodations |
| `/api/accommodations/{case_id}/analysis/hardship` | POST | AI: assess undue hardship |
| `/api/accommodations/{case_id}/audit-log` | GET | Audit trail |

**New service** (`server/app/matcha/services/accommodation_service.py`):

```python
class AccommodationService:

    async def suggest_accommodations(case_id: UUID) -> dict:
        """
        Gemini analysis: given disability category, job functions, and requested
        accommodation, suggest reasonable accommodations with EEOC/JAN references.
        Returns: {suggestions: [{accommodation, rationale, implementation_steps,
                  cost_estimate, effectiveness_rating}], references: []}
        """

    async def assess_undue_hardship(case_id: UUID) -> dict:
        """
        Gemini analysis: evaluate potential undue hardship per ADA factors
        (cost, employer resources, facility impact, operational disruption).
        Returns: {hardship_likely: bool, factors: [], reasoning, alternatives: []}
        """

    async def analyze_job_functions(case_id: UUID) -> dict:
        """
        Identify essential vs. marginal job functions relevant to the accommodation.
        Returns: {essential_functions: [], marginal_functions: [],
                  functions_affected_by_disability: [], modification_options: []}
        """
```

### Feature Flag

**New:** `accommodations` — add to `KNOWN_FEATURES` in `server/app/core/routes/admin.py`

### Files to Create

| File | Purpose |
|------|---------|
| New `server/app/matcha/models/accommodation.py` | Pydantic models for cases, documents, analysis |
| New `server/app/matcha/routes/accommodations.py` | REST endpoints, follows ER Copilot patterns |
| New `server/app/matcha/services/accommodation_service.py` | AI analysis service |
| New migration | Create all 4 accommodation tables |
| `server/app/core/routes/admin.py` | Add `accommodations` to `KNOWN_FEATURES` |
| `server/app/matcha/routes/__init__.py` | Mount new router |

---

## 6. Return-to-Work

**Strategy:** Extend the Onboarding system with a `return_to_work` category.

### What Exists

**`onboarding_tasks` table** (templates):
- Columns: `id`, `org_id`, `title`, `description`, `category`, `is_employee_task`, `due_days`, `is_active`, `sort_order`, `created_at`, `updated_at`
- Categories constrained to: `documents`, `equipment`, `training`, `admin`

**`employee_onboarding_tasks` table** (assigned instances):
- Columns: `id`, `employee_id`, `task_id`, `title`, `description`, `category`, `is_employee_task`, `due_date`, `status` (pending/completed/skipped), `completed_at`, `completed_by`, `notes`, `created_at`, `updated_at`
- Same category constraint

**Template system** (`server/app/matcha/routes/onboarding.py`):
- 12 default templates auto-seeded on first access
- Templates are per-company (`org_id` scoped)
- `is_employee_task` flag — true = employee sees it in portal, false = HR/admin task

**Assignment flow** (`server/app/matcha/routes/employees.py:1004-1299`):
- `POST /employees/{id}/onboarding/assign-all` — assigns all active templates
- Due date calculated: `employee.start_date + timedelta(days=template.due_days)`
- `PATCH /employees/{id}/onboarding/{task_id}` — mark completed/skipped

**Employee portal** (`server/app/matcha/routes/employee_portal.py`):
- `GET /me/tasks` → `get_pending_tasks()` — shows pending onboarding + PTO approval tasks

### What to Extend

**Add `return_to_work` category** — migration to alter the CHECK constraint:

```sql
ALTER TABLE onboarding_tasks
    DROP CONSTRAINT check_category,
    ADD CONSTRAINT check_category CHECK (
        category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work')
    );

ALTER TABLE employee_onboarding_tasks
    DROP CONSTRAINT check_onboarding_category,
    ADD CONSTRAINT check_onboarding_category CHECK (
        category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work')
    );
```

**RTW default templates** — seeded alongside onboarding defaults:

| Category | Title | Description | is_employee_task | due_days |
|----------|-------|-------------|------------------|----------|
| return_to_work | Fitness-for-Duty Certification | Submit medical clearance from healthcare provider | true | 0 |
| return_to_work | Modified Duty Agreement | Review and sign modified duty or accommodation plan | true | 1 |
| return_to_work | Accommodation Review | Meet with HR to review workplace accommodations | false | 3 |
| return_to_work | Gradual Return Schedule | Confirm phased return-to-work schedule | false | 1 |
| return_to_work | Benefits Reinstatement Review | Verify benefits and leave balances are current | false | 5 |
| return_to_work | Manager Check-in | Schedule return meeting with direct manager | true | 3 |

**New assignment function** — link RTW tasks to leave cases:

```python
async def assign_rtw_tasks(employee_id: UUID, leave_request_id: UUID):
    """
    When a leave request transitions to 'return_pending':
    1. Fetch active 'return_to_work' templates for the company
    2. Calculate due_date from expected_return_date (not start_date)
    3. Create employee_onboarding_tasks linked to the leave case
    """
```

**Add `leave_request_id` column** to `employee_onboarding_tasks`:

```sql
ALTER TABLE employee_onboarding_tasks
    ADD COLUMN leave_request_id UUID REFERENCES leave_requests(id) ON DELETE SET NULL;
```

### Feature Flag

`employees` (already exists)

### Files to Modify

| File | Changes |
|------|---------|
| `server/app/matcha/routes/onboarding.py` | Add RTW default templates to seed function |
| `server/app/matcha/routes/employees.py` | Add `assign_rtw_tasks()` helper, expose optional RTW filter |
| `server/app/matcha/routes/employee_portal.py` | `get_pending_tasks()` includes RTW tasks |
| New migration | Alter category constraints, add `leave_request_id` column |

---

## 7. Notifications

**Strategy:** Extend existing email patterns and background tasks.

### What Exists

**Email service** (`server/app/core/services/email.py`):
- `EmailService` class — MailerSend API, async httpx client
- Existing notification functions:
  - `send_compliance_change_notification_email(to_email, to_name, company_name, location_name, changed_requirements_count, jurisdictions)`
  - `send_ir_incident_notification_email(to_email, to_name, company_name, incident_id, incident_number, incident_title, event_type, current_status, changed_by_email, previous_status, location_name, occurred_at)`
  - `send_employee_invitation_email(to_email, to_name, company_name, token, expires_at)`

**Background task patterns:**
- FastAPI `BackgroundTasks` for fire-and-forget email sends (used in IR incidents)
- Celery tasks for scheduled/recurring work (compliance checks)
- Redis pub/sub for real-time progress updates (`publish_task_complete`, etc.)

### What to Extend

**New email functions** added to `server/app/core/services/email.py`:

```python
async def send_leave_request_notification_email(
    self,
    to_email: str,
    to_name: Optional[str],
    company_name: str,
    employee_name: str,
    leave_type: str,
    event_type: str,      # 'submitted', 'approved', 'denied', 'deadline_approaching',
                          # 'notice_ready', 'return_pending'
    leave_id: str,
    start_date: str,
    end_date: Optional[str] = None,
    deadline_date: Optional[str] = None,
    deadline_type: Optional[str] = None,
) -> bool:
    """
    Subjects by event_type:
    - submitted: "{company}: Leave request from {employee_name}"
    - approved: "{company}: Your leave request has been approved"
    - denied: "{company}: Leave request update"
    - deadline_approaching: "{company}: Action needed — {deadline_type} due {deadline_date}"
    - notice_ready: "{company}: Document ready for signature"
    - return_pending: "{company}: Return-to-work tasks assigned"
    """

async def send_accommodation_notification_email(
    self,
    to_email: str,
    to_name: Optional[str],
    company_name: str,
    case_number: str,
    event_type: str,      # 'case_opened', 'action_needed', 'determination_made',
                          # 'interactive_meeting_scheduled'
    employee_name: Optional[str] = None,
    details: Optional[str] = None,
) -> bool:
    """
    Subjects by event_type:
    - case_opened: "{company}: Accommodation request received ({case_number})"
    - action_needed: "{company}: Action needed on accommodation {case_number}"
    - determination_made: "{company}: Accommodation determination for {case_number}"
    """
```

**Notification triggers** (integrated into route handlers via `BackgroundTasks`):

| Event | Recipients | Email Function |
|-------|-----------|----------------|
| Leave request submitted | Manager + HR admins | `send_leave_request_notification_email(event_type='submitted')` |
| Leave approved/denied | Employee | `send_leave_request_notification_email(event_type='approved'/'denied')` |
| Deadline approaching (2 days) | Responsible party | `send_leave_request_notification_email(event_type='deadline_approaching')` |
| Notice ready for signature | Employee | `send_leave_request_notification_email(event_type='notice_ready')` |
| RTW tasks assigned | Employee | `send_leave_request_notification_email(event_type='return_pending')` |
| Accommodation case opened | HR admins | `send_accommodation_notification_email(event_type='case_opened')` |
| Interactive process action needed | Assigned HR | `send_accommodation_notification_email(event_type='action_needed')` |
| Accommodation determined | Employee | `send_accommodation_notification_email(event_type='determination_made')` |

### Feature Flag

None — cross-cutting concern. Notifications fire when the parent feature's actions occur.

### Files to Modify

| File | Changes |
|------|---------|
| `server/app/core/services/email.py` | Add `send_leave_request_notification_email()`, `send_accommodation_notification_email()` |

---

## 8. The Agent Orchestrator

**Strategy:** New service that ties all components together autonomously.

### What Exists

No direct analog, but the patterns are established:
- Compliance auto-checks run autonomously on schedule (Celery beat → dispatcher → per-location tasks)
- IR incident creation triggers background AI categorization + notification
- ER document upload triggers async processing pipeline (parse → chunk → embed)

### What to Create

**New `leave_agent.py`** (`server/app/matcha/services/leave_agent.py`):

```python
class LeaveAgent:
    """
    Orchestrates the leave & accommodation lifecycle autonomously.
    Called by route handlers and Celery tasks — never directly by API consumers.
    """

    async def on_leave_request_created(self, leave_request_id: UUID):
        """
        Triggered when an employee submits a leave request.
        Pipeline:
        1. Run eligibility check (LeaveEligibilityService)
        2. Store eligibility_data on the leave_request
        3. If eligible → auto-transition to 'eligibility_review'
        4. Generate required notices (FMLA eligibility notice if applicable)
        5. Create leave_deadlines (eligibility notice: 5 business days, etc.)
        6. Send notifications (employee: confirmation, manager: review needed)
        """

    async def on_leave_request_approved(self, leave_request_id: UUID):
        """
        Triggered when admin approves a leave request.
        Pipeline:
        1. Generate designation notice (if FMLA)
        2. Create remaining deadlines (certification, return date)
        3. Notify employee (approved + next steps)
        4. If medical certification needed → set 15-day deadline
        """

    async def on_leave_status_changed(self, leave_request_id: UUID, new_status: str):
        """
        Generic status transition handler.
        - 'active' → start tracking leave usage
        - 'extended' → recalculate deadlines, notify
        - 'return_pending' → assign RTW tasks, set fitness-for-duty deadline
        - 'completed' → close out deadlines, archive
        """

    async def on_deadline_approaching(self, deadline_id: UUID):
        """
        Called by the check_leave_deadlines Celery task.
        Pipeline:
        1. Determine deadline type and responsible party
        2. Send appropriate notification
        3. If overdue → escalate (re-notify, flag in dashboard, alert admin)
        """

    async def on_accommodation_request_created(self, case_id: UUID):
        """
        Triggered when an accommodation case is opened.
        Pipeline:
        1. Notify HR admins
        2. Auto-suggest accommodations via Gemini
        3. Create interactive process deadline (respond within reasonable time)
        4. If linked to leave → cross-reference leave status
        """

    async def on_accommodation_stalled(self, case_id: UUID):
        """
        Called by periodic check when a case has been in 'interactive_process'
        for 14+ days without updates.
        Pipeline:
        1. Flag case as needing attention
        2. Notify assigned HR + escalate to admin if already flagged
        """

    async def on_return_to_work(self, leave_request_id: UUID):
        """
        Triggered when employee's return date approaches (7 days before).
        Pipeline:
        1. Assign RTW onboarding tasks
        2. Send return preparation notice to employee
        3. Notify manager of upcoming return
        4. If accommodation exists → include accommodation review in RTW tasks
        """
```

**Celery integration** — the orchestrator is called from:

1. **Route handlers** (synchronous triggers):
   - Leave request creation → `on_leave_request_created()`
   - Leave approval → `on_leave_request_approved()`
   - Status changes → `on_leave_status_changed()`
   - Accommodation creation → `on_accommodation_request_created()`

2. **Celery beat tasks** (scheduled triggers):
   - `check_leave_deadlines` → calls `on_deadline_approaching()` for each due deadline
   - New `check_stalled_accommodations` → calls `on_accommodation_stalled()` for stale cases
   - New `check_upcoming_returns` → calls `on_return_to_work()` 7 days before return dates

**Integration pattern** — each route handler wraps orchestrator calls in `BackgroundTasks`:

```python
@router.post("/leave/requests")
async def create_leave_request(
    ...,
    background_tasks: BackgroundTasks,
):
    # 1. Insert leave_request record
    # 2. Enqueue orchestrator
    background_tasks.add_task(
        leave_agent.on_leave_request_created, leave_request_id
    )
    return leave_request
```

### Files to Create

| File | Purpose |
|------|---------|
| New `server/app/matcha/services/leave_agent.py` | Orchestrator service |
| New `server/app/workers/tasks/leave_agent_tasks.py` | Celery beat entries for scheduled orchestration |

---

## Implementation Order

Recommended sequence (each section is independently implementable, but this order minimizes blocked work):

1. **Section 1: Intake** — `leave_requests` table and basic CRUD (foundation for everything)
2. **Section 2: Eligibility** — can be built once leave types exist
3. **Section 5: Accommodations** — independent feature, no dependencies on 1-2
4. **Section 3: Notices** — needs leave_requests from #1
5. **Section 4: Deadlines** — needs leave_requests from #1
6. **Section 6: Return-to-Work** — needs leave_requests from #1
7. **Section 7: Notifications** — cross-cutting, add as each feature lands
8. **Section 8: Orchestrator** — ties everything together, implement last

Sections 1-2, 3-4, and 5-6 can be parallelized in pairs.

---

## Migration Plan

All new tables go in a single migration or staged migrations:

```
alembic revision -m "add_leave_and_accommodation_tables"
```

Tables created:
- `leave_requests`
- `employee_hours_log`
- `leave_deadlines`
- `accommodation_cases`
- `accommodation_documents`
- `accommodation_analysis`
- `accommodation_audit_log`

Alterations:
- `onboarding_tasks.category` constraint: add `return_to_work`
- `employee_onboarding_tasks.category` constraint: add `return_to_work`
- `employee_onboarding_tasks`: add `leave_request_id` column
- `state_preemption_rules`: seed leave-related rows
- `KNOWN_FEATURES`: add `accommodations` (code change, not migration)
