# OIG Exclusion Screening

## Context
Every healthcare employer must screen employees against the OIG's List of Excluded Individuals/Entities (LEIE) at hire and monthly thereafter. Hiring an excluded individual can result in $100K+ fines per incident. Currently this is a manual process for most orgs (download CSV, check names). Automating this in Matcha is a high-value differentiating feature.

**Good news**: The database already has `oig_status` and `oig_last_checked` columns in `employee_credentials`. The compliance registry already defines two OIG requirements. The employee creation flow already uses `background_tasks` for post-creation work.

## Implementation

### 1. OIG Screening Service (new file)
**File**: `server/app/core/services/oig_screening.py` (~150 lines)

- Download LEIE data from `https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv`
- Parse CSV into searchable structure (last_name, first_name, npi, dob, state, exclusion_type, exclusion_date)
- Cache in memory with TTL (refresh monthly or on demand)
- Match function: `screen_individual(first_name, last_name, npi=None, dob=None)`
  - Exact match on last_name + first_name → high confidence
  - NPI match → definitive (NPI is unique)
  - Fuzzy name match (Soundex/metaphone) → flag for review
- Return: `{ matched: bool, confidence: "definitive"|"high"|"possible", exclusion_type, exclusion_date, match_details }`

### 2. Wire into Employee Creation
**File**: `server/app/matcha/routes/employees.py` (~line 1145)

- After employee INSERT, add background task:
  ```python
  background_tasks.add_task(
      _perform_oig_screening,
      employee_id=row["id"],
      org_id=company_id,
      first_name=request.first_name,
      last_name=request.last_name,
  )
  ```
- The task function:
  - Calls `screen_individual()`
  - Updates `employee_credentials.oig_status` ('cleared' | 'excluded' | 'review_needed') and `oig_last_checked`
  - On match: sends email alert to company admins via `EmailService.send_email()`
  - On match: publishes Redis notification via `publish_task_error()`

### 3. API Endpoints (add to employees.py or new route file)
- `GET /employees/{id}/oig-status` — returns current screening status
- `POST /employees/{id}/oig-screen` — manually trigger re-screening
- `GET /employees/oig-summary` — company-wide summary (total screened, cleared, flagged, not checked)
- `POST /employees/oig-batch-screen` — admin: re-screen all employees (monthly)

### 4. Monthly Batch Re-screening (Celery task)
**File**: `server/app/workers/tasks/oig_screening.py` (new, ~80 lines)

- Celery periodic task, runs monthly
- Finds all employees in healthcare companies where `oig_last_checked` is >30 days old or NULL
- Re-screens each against current LEIE data
- Updates statuses, sends alerts for new matches
- Pattern: follow `compliance_checks.py` (claim-before-enqueue, configurable interval)

### 5. Frontend: OIG Status in Employee Detail
**File**: `client/src/pages/app/Employees.tsx` or employee detail component

- Show OIG screening badge on employee card: "Cleared" (green), "Excluded" (red), "Review Needed" (amber), "Not Checked" (gray)
- Show `oig_last_checked` date
- "Re-screen" button for manual trigger
- Company-wide OIG summary card on Employees dashboard

### Files to modify:
- New: `server/app/core/services/oig_screening.py` — screening logic + LEIE download/parse
- New: `server/app/workers/tasks/oig_screening.py` — monthly batch task
- Modify: `server/app/matcha/routes/employees.py` — add background task on creation + API endpoints
- Modify: employee detail UI component — display OIG status badge

### Files to reuse (don't rebuild):
- `server/app/core/services/credential_crypto.py` — decrypt NPI for matching
- `server/app/core/services/email.py` → `send_email()` — alert on exclusion match
- `server/app/workers/notifications.py` → `publish_task_error()` — real-time alert
- `server/app/database.py` — `employee_credentials.oig_status` and `oig_last_checked` already exist

### Database: No migration needed
- `oig_status VARCHAR(20) DEFAULT 'not_checked'` — already exists
- `oig_last_checked DATE` — already exists

## Verification
- Unit test: mock LEIE CSV, verify matching logic (exact, NPI, fuzzy)
- Manual: create employee, verify background screening runs, check `oig_status` updated
- Manual: trigger batch re-screen, verify all employees updated
- TypeScript: `cd client && npx tsc --noEmit`
