# Simplify Compliance: Auto-Derive Jurisdictions from Employee Addresses

## Context

The compliance system currently requires admins to manually create "business locations" on the Compliance page before compliance checks can run. But employees already provide workplace addresses (city + state) during onboarding. This is redundant — the set of unique employee workplace addresses IS the company's jurisdiction footprint.

Additionally, when an employee is added at a jurisdiction the platform doesn't yet cover (not in `jurisdiction_reference`), the system should queue it for the master admin to process. Once the admin runs compliance research for that jurisdiction, it shows up in the company's `/compliance` portal.

**Goal**: Auto-create `business_locations` from employee addresses, queue unknown jurisdictions for admin review, and simplify the Compliance UI.

## Current State

- **Employee form** has a remote/office split: remote → `work_state` only, office → free-form `address` only
- **`work_city`** column exists on employees but is only populated when compensation fields are available
- **`work_location_id`** FK to `business_locations` exists but is **never populated**
- **`jurisdiction_reference`** table has ~250 seeded cities with `has_local_ordinance` flags
- **Unknown cities** currently still create jurisdictions but skip county hierarchy + have no `has_local_ordinance` determination
- **No admin queue** for unknown/pending jurisdictions — they just get best-effort Gemini research

## Design Decisions

1. **Always collect `work_state` (required) + `work_city` (optional)** — no more remote/office split
2. **Auto-create `business_locations`** via `ensure_location_for_employee()` find-or-create
3. **Populate `work_location_id`** on every employee at create/update time
4. **Unknown jurisdiction flow**: When city+state is NOT in `jurisdiction_reference`, create the location with `coverage_status = 'pending_review'` and insert a `jurisdiction_coverage_requests` row visible to master admin
5. **Admin processes requests** → adds reference data, triggers compliance check → status flips to `'covered'` → company sees it in `/compliance`
6. **Keep manual "Add Location"** as secondary option on Compliance page
7. **Add `source` column** to `business_locations` (`'manual'` | `'employee_derived'`)
8. **Deactivate, don't delete** — last employee leaves → `is_active = false`

---

## Implementation Plan

### Step 1: Alembic Migration

**New migration file**

```sql
-- business_locations: source tracking + coverage status
ALTER TABLE business_locations
    ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS coverage_status VARCHAR(20) DEFAULT 'covered';
UPDATE business_locations SET source = 'manual' WHERE source IS NULL;
UPDATE business_locations SET coverage_status = 'covered' WHERE coverage_status IS NULL;

-- Prevent duplicate locations for same city+state within a company
CREATE UNIQUE INDEX IF NOT EXISTS idx_bl_company_city_state
    ON business_locations (company_id, LOWER(city), UPPER(state));

-- Admin queue for unknown jurisdictions
CREATE TABLE IF NOT EXISTS jurisdiction_coverage_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city VARCHAR(100) NOT NULL,
    state VARCHAR(2) NOT NULL,
    county VARCHAR(100),
    requested_by_company_id UUID NOT NULL REFERENCES companies(id),
    location_id UUID REFERENCES business_locations(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'in_progress', 'completed', 'dismissed')),
    admin_notes TEXT,
    processed_by UUID REFERENCES users(id),
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(city, state)  -- one request per jurisdiction, not per company
);
CREATE INDEX IF NOT EXISTS idx_jcr_status ON jurisdiction_coverage_requests(status);
```

### Step 2: `ensure_location_for_employee()` service function

**File**: `server/app/core/services/compliance_service.py`

```python
async def ensure_location_for_employee(
    conn, company_id: UUID, work_city: str | None, work_state: str,
    background_tasks=None,
) -> UUID | None:
```

Logic:
1. Query `business_locations` for matching `(company_id, LOWER(city), UPPER(state))`
2. If found + active → return `id`
3. If found + inactive → reactivate, return `id`
4. If not found:
   a. Check `jurisdiction_reference` for matching (city, state)
   b. **Known jurisdiction** → call `create_location()` with `source='employee_derived'`, `coverage_status='covered'` → trigger background compliance check
   c. **Unknown jurisdiction** → call `create_location()` with `source='employee_derived'`, `coverage_status='pending_review'` → INSERT into `jurisdiction_coverage_requests` (ON CONFLICT DO NOTHING for dedup) → do NOT auto-trigger compliance check
5. Return `location_id`

### Step 3: Wire into employee create

**File**: `server/app/matcha/routes/employees.py` — `create_employee()`

After the INSERT RETURNING, if `work_state` is non-null:
1. Call `ensure_location_for_employee(conn, company_id, work_city, work_state, background_tasks)`
2. UPDATE employee SET `work_location_id = <returned id>`

### Step 4: Wire into employee update

**File**: `server/app/matcha/routes/employees.py` — `update_employee()`

If `work_city` or `work_state` changed:
1. Call `ensure_location_for_employee()` for new values
2. Set `work_location_id` to the new location
3. Check if any active employees remain at old location; if none, set `is_active = false`

### Step 5: Wire into bulk CSV upload

**File**: `server/app/matcha/routes/employees.py` — `bulk_upload_employees_csv()`

After each employee INSERT, if `work_state` present:
1. Call `ensure_location_for_employee()` (deduplicates via find-or-create)
2. Set `work_location_id` on the new employee

### Step 6: Admin — jurisdiction coverage request endpoints

**File**: `server/app/core/routes/admin.py`

New endpoints:
- `GET /admin/jurisdiction-requests` — list pending/in-progress requests, joined with company name + employee count at that location
- `POST /admin/jurisdiction-requests/{id}/process` — admin triggers compliance research for the jurisdiction:
  1. Optionally add to `jurisdiction_reference` (city, state, county, has_local_ordinance)
  2. Run `run_compliance_check_background()` on the associated location
  3. Set `coverage_status = 'covered'` on the business_location
  4. Set request `status = 'completed'`
- `POST /admin/jurisdiction-requests/{id}/dismiss` — mark as dismissed (e.g., invalid city)

### Step 7: Protect locations with employees from deletion

**File**: `server/app/core/services/compliance_service.py` — `delete_location()`

Before deleting, check if active employees have `work_location_id` pointing to this location. If so, reject with clear error.

### Step 8: Frontend — Employee form changes

**Files**: `client/src/pages/Employees.tsx`, `client/src/hooks/employees/useEmployeeForm.ts`, `client/src/hooks/employees/useBatchWizard.ts`

- Remove `workLocationMode` / `batchWorkLocationMode` (remote/office) toggle
- Always show **State** dropdown (required) + **City** text input (optional)
- Keep free-form `address` field as optional ("Building/floor/suite")
- Remove `complianceAPI.getLocations()` dependency from employee form

### Step 9: Frontend — Compliance page updates

**File**: `client/src/pages/Compliance.tsx`

- Show "Auto-derived" badge on `source = 'employee_derived'` locations
- Show "Pending coverage" badge on `coverage_status = 'pending_review'` locations (amber, with tooltip: "Platform admin is reviewing this jurisdiction")
- Update empty state: "Locations are auto-created when employees are onboarded."
- Block deletion of locations with active employees
- "Add Location" button stays as secondary

### Step 10: Frontend — Admin jurisdiction requests page

**File**: `client/src/pages/admin/Jurisdictions.tsx` (add tab) or new page

- New "Coverage Requests" tab on the admin Jurisdictions page
- Shows table of pending requests: city, state, requesting company, employee count, date
- "Process" button → opens panel to:
  - Set `has_local_ordinance` (yes/no)
  - Set county (optional)
  - Trigger compliance check
- "Dismiss" button for invalid entries

### Step 11: Simplify impact calculation

**File**: `server/app/core/services/compliance_service.py` — `get_employee_impact_for_location()`

Replace heuristic with FK query:
```sql
SELECT ... FROM employees
WHERE org_id = $1 AND work_location_id = $2 AND termination_date IS NULL
```
Keep state-estimate as fallback for `work_location_id IS NULL` (legacy).

---

## Files to Modify

| File | Changes |
|---|---|
| `server/alembic/versions/<new>.py` | Migration: `source`, `coverage_status` on business_locations + `jurisdiction_coverage_requests` table |
| `server/app/core/services/compliance_service.py` | `ensure_location_for_employee()`, protect `delete_location()`, simplify impact calc |
| `server/app/matcha/routes/employees.py` | Wire location sync into create, update, bulk upload |
| `server/app/core/routes/admin.py` | Jurisdiction coverage request endpoints |
| `client/src/pages/Employees.tsx` | Remove remote/office split, always collect state+city |
| `client/src/hooks/employees/useEmployeeForm.ts` | Remove `workLocationMode`, update validation |
| `client/src/hooks/employees/useBatchWizard.ts` | Remove `batchWorkLocationMode` |
| `client/src/pages/Compliance.tsx` | Source badges, pending coverage badge, updated empty state |
| `client/src/pages/admin/Jurisdictions.tsx` | Coverage requests tab with process/dismiss actions |

## Verification

1. Create employee with known city+state (e.g., San Francisco, CA) → `business_locations` auto-created with `coverage_status='covered'` → compliance check triggers → shows in `/compliance`
2. Create employee with unknown city+state (e.g., Bozeman, MT) → location created with `coverage_status='pending_review'` → `jurisdiction_coverage_requests` row created → shows as "Pending coverage" in `/compliance`
3. Admin processes the request → compliance check runs → status flips to `covered` → company now sees full compliance data
4. Second employee at same city+state → no duplicate location, shares `work_location_id`
5. Update employee city → new location created, old deactivated if empty
6. Bulk CSV with employees across 3 states → 3 locations created, unknown ones queued
7. Delete location with active employees → blocked
8. Manual "Add Location" still works
