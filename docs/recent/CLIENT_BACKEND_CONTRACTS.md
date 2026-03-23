# Client ↔ Backend API Contracts

Complete reference for rebuilding the frontend. Every endpoint, request/response shape, field name, validation rule, and backend behavior documented.

**Auth pattern**: All authenticated endpoints require `Authorization: Bearer <access_token>` header. Tokens stored in `localStorage` as `matcha_access_token` / `matcha_refresh_token`. On 401, client auto-refreshes via `/api/auth/refresh` and retries.

**Company scoping**: Client/employee users see only their company's data. Admins see all.

**Date formats**: ISO 8601 — dates as `YYYY-MM-DD`, datetimes as `YYYY-MM-DDTHH:MM:SSZ`.

---

## Table of Contents

1. [Auth & Settings](#1-auth--settings)
2. [Dashboard](#2-dashboard)
3. [Employee Management](#3-employee-management)
4. [Onboarding](#4-onboarding)
5. [PTO Management](#5-pto-management)
6. [Leave Management](#6-leave-management)
7. [Training](#7-training)
8. [Accommodations](#8-accommodations)
9. [I-9 Verification](#9-i-9-verification)
10. [COBRA](#10-cobra)
11. [Separations](#11-separations)
12. [Pre-Termination](#12-pre-termination)
13. [Compliance](#13-compliance)
14. [ER Copilot](#14-er-copilot)
15. [IR Incidents](#15-ir-incidents)
16. [Offer Letters](#16-offer-letters)
17. [Policies](#17-policies)
18. [Handbooks](#18-handbooks)
19. [Employee Portal](#19-employee-portal)
20. [Broker Portal](#20-broker-portal)
21. [Admin Panel](#21-admin-panel)
22. [AI Chat](#22-ai-chat)
23. [Risk Assessment](#23-risk-assessment)
24. [Matcha Work](#24-matcha-work)
25. [Blog](#25-blog)
26. [Interviews & Tutor](#26-interviews--tutor)

---

## 1. Auth & Settings

### POST `/api/auth/login`
No auth required.

**Request:**
```json
{ "email": "EmailStr", "password": "string" }
```

**Response:** `TokenResponse`
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 3600,
  "user": {
    "id": "UUID", "email": "string",
    "role": "admin|client|candidate|employee|broker",
    "is_active": true, "created_at": "datetime", "last_login": "datetime|null"
  }
}
```
- Case-insensitive email lookup. Updates `last_login` async.
- **401** invalid credentials, **403** account disabled.

### POST `/api/auth/refresh`
No auth required.

**Request:** `{ "refresh_token": "string" }`
**Response:** Same `TokenResponse` — new access AND refresh tokens. Client must update both.

### POST `/api/auth/register/business`
No auth. Primary registration flow for companies.

**Request:**
```json
{
  "company_name": "string",
  "industry": "string|null",
  "company_size": "string|null",
  "headcount": "int (min 1)",
  "email": "EmailStr",
  "password": "string (min 8)",
  "name": "string",
  "phone": "string|null",
  "job_title": "string|null",
  "invite_token": "string|null",
  "broker_ref": "string|null"
}
```

**Response:** `TokenResponse` + `{ "company_status": "approved|pending", "message": "string" }`

- Auto-approves if `invite_token` or `broker_ref` valid, else `status='pending'`.
- Grants 250 free Matcha Work credits.
- Seeds `company_handbook_profiles`.
- Links to broker if `broker_ref` slug found.

### POST `/api/auth/register/client`
No auth. Register client linked to existing company.

**Request:** `{ "email", "password", "name", "company_id": "UUID", "phone?", "job_title?" }`
**Response:** `TokenResponse`

### POST `/api/auth/register/employee`
No auth.

**Request:** `{ "email", "password", "first_name", "last_name", "company_id": "UUID", "work_state?", "employment_type?", "start_date?" }`
**Response:** `TokenResponse`

### POST `/api/auth/register/candidate`
No auth.

**Request:** `{ "email", "password", "name", "phone?" }`
**Response:** `TokenResponse`. Links to existing candidates record if email matches.

### POST `/api/auth/register/admin`
Requires `admin` role.

**Request:** `{ "email", "password", "name" }`
**Response:** `TokenResponse`

### POST `/api/auth/register/test-account`
Requires `admin`. Provisions demo account with seeded data.

**Request:** `{ "company_name?", "industry?", "company_size?", "email", "password?", "name", "phone?", "job_title?" }`
**Response:** `{ "status", "company_id", "user_id", "email", "password", "generated_password": bool, "seeded_manager_email?", "seeded_employee_email?", "seeded_portal_password?" }`

### GET `/api/auth/me`
Requires auth. Returns full profile + onboarding state + visible features.

**Response:**
```json
{
  "user": { "id", "email", "role" },
  "profile": {
    // Role-specific. Client profile includes:
    "company_id", "company_name", "company_status", "industry",
    "healthcare_specialties": [], "enabled_features": {},
    "name", "phone", "job_title", "email"
  },
  "onboarding_needed": {
    "company_profile": bool, "compliance": bool, "employees": bool,
    "policies": bool, "offer_letters": bool, "integrations": bool
  },
  "visible_features": ["compliance", "employees", ...]
}
```

Onboarding flags computed from data existence (not stored).

### POST `/api/auth/logout`
Auth required. Currently a no-op. Returns `{ "status": "logged_out" }`.

### POST `/api/auth/change-password`
**Request:** `{ "current_password", "new_password" }` (min 8 chars)
**Response:** `{ "status": "password_changed" }`

### POST `/api/auth/change-email`
**Request:** `{ "password", "new_email" }`
**Response:** `{ "status": "email_changed", "access_token", "refresh_token", "expires_in" }` — new tokens with updated email.

### PUT `/api/auth/profile`
**Request:** `{ "name?", "phone?" }`
**Response:** `{ "status": "profile_updated" }`

### GET `/api/auth/business-invite/{token}`
No auth. Validates invite token. Returns `{ "valid": bool, "company_name", "invitation_expires_at" }`.

### GET `/api/auth/broker-branding/{broker_key}`
No auth. Returns broker white-label config (logo, colors, display name, support info).

### GET `/api/auth/broker-client-invite/{token}`
No auth. Returns `{ "valid", "broker_name", "company_name", "contact_email", "invite_expires_at" }`.

### POST `/api/auth/broker-client-invite/{token}/accept`
No auth. **Request:** `{ "password", "name?", "phone?", "job_title?" }`
**Response:** `{ "status": "activated", "user_id", "email", "company_id", "company_name", "access_token", "refresh_token" }`

### POST `/api/auth/broker/accept-terms`
Requires `broker` role. **Request:** `{ "terms_version?" }`
**Response:** `{ "status": "accepted", "broker_id", "terms_version", "accepted_at" }`

---

## 2. Dashboard

### GET `/api/dashboard/stats`
Auth: admin or client.

**Response:**
```json
{
  "active_policies": "int",
  "pending_signatures": "int",
  "total_employees": "int",
  "compliance_rate": "float (0-100)",
  "pending_incidents": [{ "id", "title", "severity", "status", "occurred_at" }],
  "recent_activity": [{ "type", "title", "description", "timestamp" }],
  "incident_summary": { "open", "critical", "high", "medium", "low", "recent_7_days" },
  "wage_alerts": { "hourly_violations", "salary_violations", "locations_affected" },
  "critical_compliance_alerts": "int",
  "warning_compliance_alerts": "int",
  "er_case_summary": { "open", "investigating", "pending_action" },
  "stale_policies": { "count", "oldest_days" }
}
```

### GET `/api/dashboard/notifications`
Auth: admin or client. **Query:** `limit` (1-100, default 30), `offset` (default 0).

**Response:** `{ "items": [{ "id", "type", "title", "subtitle", "severity", "status", "created_at", "link" }], "total" }`

Types: incident, employee, offer_letter, er_case, handbook, compliance_alert, credential_expiry. 30-day window.

### GET `/api/dashboard/credential-expirations`
Auth: admin or client. 90-day lookahead.

**Response:** `{ "summary": { "expired", "critical", "warning" }, "expirations": [{ "employee_id", "employee_name", "job_title", "credential_type", "credential_label", "expiry_date", "severity" }] }`

### GET `/api/dashboard/upcoming`
Auth: admin or client. **Query:** `days` (1-365, default 90).

**Response:** `{ "items": [{ "category", "title", "subtitle", "date", "days_until", "severity", "link" }], "total" }`

Categories: compliance, credential, training, cobra, policy, ir, er, i9, separation, onboarding, legislation, requirement. Sorted by urgency.

---

## 3. Employee Management

Base path: `/api/employees`

### GET `/`
Auth: admin or client. **Query:** `status?`, `employment_status?`, `search?` (min 1, max 200), `department?`, `employment_type?`, `work_state?`, `work_city?`, `manager_id?`

**Response:** `EmployeeListResponse[]`
```json
{
  "id": "UUID", "email": "string", "work_email?", "personal_email?",
  "first_name", "last_name", "work_state?", "employment_type?",
  "start_date?", "termination_date?", "manager_id?", "manager_name?",
  "user_id?", "invitation_status?",
  "pay_classification?": "hourly|exempt", "pay_rate?": "float",
  "work_city?", "job_title?", "department?",
  "employment_status?": "active|on_leave|suspended|on_notice|furloughed|terminated|offboarded",
  "status_changed_at?", "status_reason?", "created_at"
}
```

### POST `/`
Auth: admin or client.

**Request:**
```json
{
  "email?": "EmailStr (legacy alias for work_email)",
  "work_email?": "EmailStr",
  "personal_email?": "EmailStr",
  "first_name": "string (required)",
  "last_name": "string (required)",
  "work_state?", "address?", "employment_type?",
  "start_date?": "YYYY-MM-DD",
  "manager_id?": "UUID",
  "skip_google_workspace_provisioning": "bool (default false)",
  "skip_invitation": "bool (default false)",
  "pay_classification?": "hourly|exempt",
  "pay_rate?": "Decimal (>=0, requires pay_classification)",
  "work_city?", "job_title?", "department?"
}
```

**Response:** `EmployeeDetailResponse` (all list fields + phone, address, emergency_contact, updated_at)

**Side effects:** Auto-assigns onboarding templates. Syncs location to compliance. Optionally sends invitation email and triggers Google Workspace provisioning.

### GET `/departments`
Returns array of distinct department name strings.

### GET `/locations`
Returns `[{ "state", "city" }]`.

### GET `/onboarding-progress`
Returns `{ [employee_id]: { "total", "completed", "pending", "has_onboarding" } }`.

### GET `/{employee_id}`
Full employee detail. **Response:** `EmployeeDetailResponse`

### PUT `/{employee_id}`
Update employee. All fields optional. **Response:** `EmployeeDetailResponse`

### DELETE `/{employee_id}`
Delete employee.

### POST `/{employee_id}/invite`
Send/resend invitation email.

### POST `/{employee_id}/status`
Change employment status. **Request:** `{ "status": "active|on_leave|...", "reason?" }`

---

## 4. Onboarding

Base path: `/api/onboarding`

### GET `/state-machine`
**Response:** `{ "states": [], "transitions": {}, "block_reasons": [], "event_schema_version", "event_required_fields": [], "event_optional_fields": [] }`

### GET `/analytics`
**Response:**
```json
{
  "generated_at": "datetime",
  "funnel": { "invited", "accepted", "started", "completed", "ready_for_day1" },
  "kpis": { "time_to_ready_p50_days?", "time_to_ready_p90_days?", "completion_before_start_rate?", "automation_success_rate?", "manual_intervention_rate?" },
  "bottlenecks": [{ "task_title", "overdue_count", "avg_days_overdue" }]
}
```

### GET `/templates`
**Query:** `category?` (documents|equipment|training|admin|return_to_work|priority), `is_active?`

**Response:** `OnboardingTaskTemplateResponse[]`
```json
{
  "id", "org_id", "title", "description?", "category", "is_employee_task": bool,
  "due_days": int, "is_active": bool, "sort_order": int,
  "link_type?": "policy|handbook|url", "link_id?", "link_label?", "link_url?",
  "created_at", "updated_at"
}
```

### POST `/templates`
**Request:** `{ "title", "description?", "category?" (default "admin"), "is_employee_task?" (default false), "due_days?" (default 7), "sort_order?", "link_type?", "link_id?", "link_label?", "link_url?" }`

### PUT `/templates/{template_id}`
All fields optional. **Response:** template.

### DELETE `/templates/{template_id}`
**Response:** `{ "message" }`

### GET `/notification-settings`
**Response:** `{ "email_enabled", "hr_escalation_emails": [], "reminder_days_before_due", "escalate_to_manager_after_days", "escalate_to_hr_after_days", "timezone", "auto_send_invitation" }`

### PUT `/notification-settings`
Same shape as GET, all fields required. **Response:** same.

---

## 5. PTO Management

Base path: `/api/pto`

### GET `/balances`
Auth: admin or client. **Query:** `employee_id?`, `year?`

**Response:** `PTOBalance[]`
```json
{ "id", "employee_id", "year", "balance_hours", "accrued_hours", "used_hours", "carryover_hours", "updated_at" }
```

### POST `/balances`
**Request:** `{ "employee_id", "year", "balance_hours", "accrued_hours?", "carryover_hours?" }`

### GET `/requests`
**Query:** `status?` (pending|approved|denied|cancelled), `employee_id?`
**Response:** `PTORequest[]` with `{ "id", "employee_id", "request_type", "start_date", "end_date", "hours", "reason?", "status", "approved_by?", "approved_at?", "denied_reason?", "created_at" }`

### PATCH `/requests/{request_id}`
**Request:** `{ "action": "approve|deny", "denied_reason?" }`
**Response:** `{ "message", "status" }`

### GET `/summary`
Auth: admin or client. Company-wide PTO summary.

---

## 6. Leave Management

Base path: `/api/employees/leave`

**Leave types:** fmla, state_pfml, parental, bereavement, jury_duty, medical, military, unpaid_loa

### GET `/requests`
**Query:** `status?` (requested|approved|denied|active|completed|cancelled), `leave_type?`

**Response:** `LeaveRequestAdmin[]`
```json
{
  "id", "employee_id", "org_id", "leave_type", "reason?",
  "start_date", "end_date?", "expected_return_date?", "actual_return_date?",
  "status", "intermittent": bool, "intermittent_schedule?",
  "hours_approved?", "hours_used?", "denial_reason?",
  "reviewed_by?", "reviewed_at?", "notes?", "employee_name?",
  "created_at", "updated_at"
}
```

### GET `/requests/{leaveId}`
Single leave request.

### PATCH `/requests/{leaveId}`
**Request:** `{ "action": "approve|deny|activate|complete|extend", "denial_reason?", "end_date?", "expected_return_date?", "actual_return_date?", "hours_approved?", "notes?" }`
**Response:** `{ "message", "status" }`

### GET `/requests/{leaveId}/eligibility`
Returns eligibility data (FMLA, state programs).

### GET `/requests/{leaveId}/deadlines`
**Response:** `LeaveDeadline[]` — `{ "id", "leave_request_id", "deadline_type", "due_date", "status": "pending|completed|overdue|waived", "escalation_level", "completed_at?", "notes?", "created_at", "updated_at" }`

### PATCH `/requests/{leaveId}/deadlines/{deadlineId}`
**Request:** `{ "action": "complete|waive", "notes?" }`

### POST `/requests/{leaveId}/notices`
**Request:** `{ "notice_type": "fmla_eligibility_notice|fmla_designation_notice|state_leave_notice|return_to_work_notice" }`
**Response:** `LeaveNoticeDocument`

### POST `/requests/{leaveId}/return-checkin`
**Request:** `{ "returning": bool, "action?": "extend|new_leave", "new_end_date?", "new_expected_return_date?", "new_leave_type?", "new_start_date?", "notes?" }`

### POST `/api/employees/{employeeId}/leave/place`
Admin places employee on leave. **Request:** `{ "leave_type", "start_date", "end_date?", "expected_return_date?", "reason?", "notes?" }`
**Response:** `{ "leave_id", "employment_status" }`

### GET `/api/employees/{employeeId}/leave/eligibility`
Employee-specific eligibility check.

### GET `/{employeeId}/requests`
Leave history for specific employee. **Query:** `status?`

### POST `/api/employees/{employeeId}/onboarding/assign-rtw/{leaveId}`
Assign return-to-work onboarding tasks.

---

## 7. Training

Base path: `/api/training`

### POST `/requirements`
**Request:** `{ "title", "description?", "training_type": "harassment_prevention|safety|food_handler|osha|custom", "jurisdiction?", "frequency_months?", "applies_to?" (default "all") }`

### GET `/requirements`
**Query:** `is_active?` (default true). **Response:** requirement array.

### PUT `/requirements/{requirement_id}`
All fields optional.

### DELETE `/requirements/{requirement_id}`
Soft delete (is_active=false). **Response:** `{ "status": "deleted", "requirement_id" }`

### POST `/records`
**Request:** `{ "employee_id": "UUID", "requirement_id?", "title", "training_type", "due_date?", "provider?", "notes?" }`

**Response:** Training record with status: assigned|in_progress|completed|expired|waived.

### POST `/records/bulk-assign`
**Request:** `{ "requirement_id": "UUID" }`
Assigns to all active employees. **Response:** `{ "assigned_count", "requirement_id", "message?" }`

### GET `/records`
**Query:** `employee_id?`, `status?`, `overdue?` (bool)

### PUT `/records/{record_id}`
**Request:** `{ "status?", "completed_date?", "expiration_date?", "provider?", "certificate_number?", "score?", "notes?" }`
Auto-sets completed_date to today if status="completed". Auto-computes expiration from frequency.

### GET `/compliance`
Training compliance dashboard. **Response:** `[{ "requirement_id", "title", "training_type", "jurisdiction?", "frequency_months?", "total_assigned", "completed", "overdue" }]`

### GET `/overdue`
**Response:** `[{ "record_id", "training_title", "training_type", "due_date?", "assigned_date?", "status", "employee_id", "first_name", "last_name", "email" }]`

---

## 8. Accommodations

Base path: `/api/accommodations`

### POST `/`
**Request:** `{ "employee_id", "linked_leave_id?", "title", "description?", "disability_category?", "requested_accommodation?" }`

**Response:** `AccommodationCaseResponse`
```json
{
  "id", "case_number" (auto-generated), "org_id", "employee_id", "linked_leave_id?",
  "title", "description?", "disability_category?",
  "status": "requested|approved|denied|closed",
  "requested_accommodation?", "approved_accommodation?", "denial_reason?",
  "undue_hardship_analysis?", "assigned_to?", "created_by",
  "document_count", "created_at", "updated_at", "closed_at?"
}
```

### GET `/`
**Query:** `status?`, `employee_id?`. **Response:** `{ "cases": [], "total" }`

### GET `/employees`
Returns `[{ "id", "first_name", "last_name", "email" }]` for dropdown.

### GET `/{case_id}`, PUT `/{case_id}`, DELETE `/{case_id}`
Standard CRUD. Auto-sets `closed_at` on status="closed".

### POST `/{case_id}/documents`
Multipart form-data. **Fields:** `file` (max 50MB), `document_type?` (medical_certification|accommodation_request_form|interactive_process_notes|job_description|hardship_analysis|approval_letter|other).
Allowed extensions: .pdf, .docx, .doc, .txt, .csv, .json, .png, .jpg, .jpeg.

### GET `/{case_id}/documents`, DELETE `/{case_id}/documents/{doc_id}`

### AI Analysis (POST to generate, GET to retrieve):
- `/{case_id}/analysis/suggestions` — accommodation suggestions
- `/{case_id}/analysis/hardship` — undue hardship analysis
- `/{case_id}/analysis/job-functions` — essential job function analysis

### GET `/{case_id}/audit-log`
**Query:** `limit` (1-500, default 100), `offset`. **Response:** `{ "entries": [{ "id", "case_id", "user_id", "action", "entity_type?", "entity_id?", "details?", "ip_address?", "created_at" }], "total" }`

---

## 9. I-9 Verification

Base path: `/api/i9`

### POST `/`
**Request:** `{ "employee_id", "notes?" }`
**Response:** I-9 record with status: pending_section1|pending_section2|complete|reverification_needed|reverified.

### GET `/`
**Query:** `status?`, `expiring_within_days?`

### GET `/expiring`
**Query:** `days` (default 90). Returns I-9 records + employee info.

### GET `/incomplete`
**Response:** `{ "no_record": [employees without I-9], "incomplete": [I-9 records not complete] }`

### GET `/compliance-summary`
**Response:** `{ "total_employees", "complete_count", "incomplete_count", "expiring_soon_count", "overdue_count", "completion_rate" }`

### GET `/{employee_id}`
I-9 record by employee.

### PUT `/{record_id}`
Auto-advances status: section1_completed → pending_section2, section2_completed → complete.

---

## 10. COBRA

Base path: `/api/cobra`

### POST `/events`
**Request:**
```json
{
  "employee_id": "UUID",
  "event_type": "termination|reduction_in_hours|divorce|dependent_aging_out|medicare_enrollment|employee_death",
  "event_date": "date",
  "beneficiary_count": "int (default 1)",
  "notes?", "offboarding_case_id?"
}
```

**Response:** COBRA event with auto-computed deadlines:
- `employer_notice_deadline`: event_date + 30 days
- `administrator_notice_deadline`: event_date + 44 days
- `election_deadline`: admin_deadline + 60 days
- `continuation_months`: 18 (standard) or 36 (extended events: divorce, dependent_aging_out, medicare, death)

### GET `/events`
**Query:** `status?`, `overdue?` (bool — past employer notice deadline with notice unsent)

### GET `/overdue`
Returns events + employee info + `days_overdue`.

### GET `/dashboard`
**Response:** `{ "pending_notices", "overdue_count", "upcoming_deadlines": [], "total_active" }`

### GET `/events/{event_id}`, PUT `/events/{event_id}`
Update auto-sets dates: employer_notice_sent=true → sets date to today. election_received=true → status="elected". election_received=false → status="waived".

---

## 11. Separations

Base path: `/api/separations`

### POST `/`
**Request:**
```json
{
  "employee_id", "offboarding_case_id?", "pre_term_check_id?",
  "severance_amount?", "severance_weeks?", "severance_description?",
  "additional_terms?": "dict", "employee_age_at_separation?": "int",
  "is_group_layoff": "bool (default false)",
  "decisional_unit?", "group_disclosure?": "list", "notes?"
}
```

**Response:** Separation agreement. ADEA auto-computed if age >= 40. Consideration period: 45 days (group) or 21 days (individual) if ADEA applicable.

Status flow: draft → presented → consideration_period → signed → effective (or revoked)

### GET `/`
**Query:** `status?`, `employee_id?`. Returns agreements + `employee_name`.

### GET `/{agreement_id}`, PUT `/{agreement_id}`

### PUT `/{agreement_id}/present`
Must be "draft". Sets presented_date=today, consideration_deadline.

### PUT `/{agreement_id}/sign`
If ADEA, enforces consideration period. Sets signed_date=today, revocation_deadline (default +7 days).

### PUT `/{agreement_id}/revoke`
Must be "signed" and within revocation period. Sets revoked_date=today.

### GET `/{agreement_id}/status`
Returns countdown timers: `days_remaining_consideration`, `days_remaining_revocation`, `is_effective`.

---

## 12. Pre-Termination

Base path: `/api/pre-termination`

### Progressive Discipline

**POST `/discipline`**
```json
{
  "employee_id", "discipline_type": "verbal_warning|written_warning|pip|final_warning|suspension",
  "issued_date", "description?", "expected_improvement?", "review_date?"
}
```
Status: active|completed|expired|escalated.

**GET `/discipline/employee/{employee_id}`**, **GET `/discipline/search?q=name`**, **GET `/discipline/{record_id}`**
**PATCH `/discipline/{record_id}`**, **DELETE `/discipline/{record_id}`** (204)

### Agency Charges

**POST `/agency-charges`**
```json
{
  "employee_id", "charge_type": "eeoc|nlrb|osha|state_agency|other",
  "filing_date", "charge_number?", "agency_name?", "description?"
}
```
Status: filed|investigating|mediation|resolved|dismissed|litigated.

**GET `/agency-charges/employee/{employee_id}`**, **GET `/agency-charges/search?q=name`**
**GET `/agency-charges/{charge_id}`**, **PATCH `/agency-charges/{charge_id}`**, **DELETE** (204)

### Post-Termination Claims

**POST `/claims`**
```json
{ "employee_id", "pre_termination_check_id?", "claim_type", "filed_date", "description?" }
```
Status: filed|investigating|mediation|settled|dismissed|litigated|judgment.

**GET `/claims/employee/{employee_id}`**, **GET `/claims/company`**
**GET `/claims/{claim_id}`**, **PATCH `/claims/{claim_id}`**, **DELETE `/claims/{claim_id}`**

---

## 13. Compliance

Base path: `/api/compliance`

### GET `/jurisdictions`
Returns all jurisdictions with data. **Response:** `[{ "city", "state", "county?", "has_local_ordinance" }]`
Redis cached (3600s TTL).

### POST `/locations`
**Request:** `{ "name?", "address?", "city" (required), "state" (required), "county?", "zipcode?" }`
**Query:** `company_id?` (admin override)

Triggers background compliance check if repository coverage incomplete. **Response:** location object.

### GET `/locations`
**Response:** `BusinessLocation[]` — includes `requirements_count`, `unread_alerts_count`, `employee_count`, `employee_names[]`, `data_status`, `coverage_status`, `has_local_ordinance`.

### GET `/locations/{location_id}`, PUT `/locations/{location_id}`, DELETE `/locations/{location_id}`

### POST `/locations/{location_id}/check` (SSE)
Triggers compliance check with real-time progress streaming.

**SSE Event Types:**
```
{ "type": "heartbeat" }
{ "type": "progress", "message", "phase": "fetching_repository|verifying|researching|saving", "progress": 0-100, "timestamp" }
{ "type": "new_requirement", "requirement_id", "category", "title", "jurisdiction_level", "current_value" }
{ "type": "alert_generated", "alert_id", "title", "severity": "info|warning|critical", "message" }
{ "type": "error", "message" }
[DONE]
```

**3-tier research:** Tier 1: jurisdiction_requirements table → Tier 2: parent jurisdiction cache → Tier 3: Gemini AI (admin only). Heartbeat every 8s.

### GET `/locations/{location_id}/requirements`
**Query:** `category?`, `company_id?`

**Response:** `RequirementResponse[]`
```json
{
  "id", "category", "rate_type?" (for minimum_wage: general|tipped|healthcare|...),
  "applicable_industries?": [], "jurisdiction_level": "federal|state|county|city",
  "jurisdiction_name", "title", "description?", "current_value?", "numeric_value?",
  "source_url?", "source_name?", "effective_date?", "previous_value?", "last_changed_at?",
  "affected_employee_count?", "affected_employee_names?": [],
  "min_wage_violation_count?", "is_pinned?"
}
```

### GET `/alerts`
**Query:** `status?` (unread|read|dismissed|actioned), `severity?` (info|warning|critical), `limit?` (default 50)

**Response:** `ComplianceAlert[]` — includes `alert_type` (change|new_requirement|upcoming_legislation|deadline_approaching), `verification_sources[]`, `confidence_score`, `affected_employee_count`.

### PUT `/alerts/{alert_id}/read`
### PUT `/alerts/{alert_id}/dismiss`
Optional body: `{ "is_false_positive?", "correction_reason?": "misread_date|wrong_jurisdiction|hallucination|outdated_source", "admin_notes?" }`

### PUT `/alerts/{alert_id}/action-plan`
**Request:** `{ "action_owner_id?", "next_action?", "action_due_date?", "recommended_playbook?", "estimated_financial_impact?", "mark_actioned?" }`

### POST `/alerts/{alert_id}/feedback`
Calibration feedback. **Request:** `{ "actual_is_change": bool, "admin_notes?", "correction_reason?" }`

### GET `/summary`
**Response:** `{ "total_locations", "total_requirements", "unread_alerts", "critical_alerts", "recent_changes": [], "auto_check_locations", "upcoming_deadlines": [] }`

### GET `/dashboard`
**Query:** `horizon_days?` (30|60|90|180|365, default 90)
**Response:** KPIs + `coming_up[]` items with `sla_state`, `action_owner`, `affected_employee_count`, `impact_basis`.

### GET `/locations/{location_id}/check-log`
**Query:** `limit?` (default 20). Returns check history.

### GET `/locations/{location_id}/upcoming-legislation`
Returns legislation items with `days_until_effective`, `confidence` (0-1).

### GET `/calibration/stats`
**Query:** `category?`, `days?` (default 30). Returns confidence bucket accuracy stats.

### PUT `/legislation/{legislation_id}/assign`
**Request:** `{ "location_id" (required), "action_owner_id?", "action_due_date?" }`. Creates alert on-demand if needed. **Response:** `{ "alert_id" }`

### GET `/assignable-users`
Returns `[{ "id", "name", "email", "role" }]`.

### POST `/requirements/{requirement_id}/pin`
**Request:** `{ "is_pinned": bool }`. **Response:** `{ "id", "title", "is_pinned" }`

### GET `/pinned-requirements`
Returns pinned requirements with location context.

---

## 14. ER Copilot

Base path: `/api/er-copilot`

### POST `/`
**Request:**
```json
{
  "title": "string (1-255, required)",
  "description?": "string (up to 5000)",
  "intake_context?": "dict",
  "category?": "harassment|discrimination|safety|retaliation|policy_violation|misconduct|wage_hour|other",
  "involved_employees?": [{ "employee_id": "UUID", "role": "complainant|respondent|witness" }]
}
```

**Response:** `ERCaseResponse` — case_number auto-generated (ER-YYYY-MM-XXXX format). Status: open|in_review|pending_determination|closed. Outcome: termination|disciplinary_action|retraining|no_action|resignation|other.

### GET `/`
**Query:** `status?`. **Response:** `{ "cases": [], "total" }`

### GET `/metrics`
**Query:** `days?` (1-365, default 30). **Response:** `{ "period_days", "total_cases", "by_status": {}, "by_category": {}, "by_outcome": {}, "trend": [{ "date", "count" }] }`

### GET `/by-employee/{employee_id}`
### GET `/{case_id}`, PUT `/{case_id}`, DELETE `/{case_id}`

If status='closed', sets closed_at. Triggers risk assessment refresh on any mutation.

### POST `/{case_id}/documents`
Multipart: `file` (max 50MB, .pdf/.docx/.doc/.txt/.csv/.json), `document_type?` (transcript|policy|email|other).
Returns document with `processing_status`: pending|processing|completed|failed. Async text extraction + chunking for RAG.

### GET `/{case_id}/documents`, DELETE `/{case_id}/documents/{document_id}`

### POST `/{case_id}/notes`
**Request:** `{ "note_type?": "general|question|answer|guidance|system", "content": "string (1-10000)", "metadata?" }`
### GET `/{case_id}/notes`

### POST `/{case_id}/export`
**Request:** `{ "password": "string (4-128)" }`. Returns password-protected PDF stream.

### POST `/{case_id}/export/share`
**Request:** `{ "password": "string (4-128)", "expires_in_days?": "0-365" }`
**Response:** `{ "token", "url": "/shared/er-export/{token}", "expires_at?", "created_at" }`

### GET `/{case_id}/export/links`
### DELETE `/{case_id}/export/links/{link_id}`

### Public share endpoints (no auth):
- **GET `/shared/er-export/{token}/info`** — `{ "filename", "created_at", "expired" }`
- **POST `/shared/er-export/{token}/download`** — `{ "password" }` → PDF stream. Rate limited: 5 failed attempts/15min → 429.

### AI Analysis (all POST, streaming responses):

**POST `/{case_id}/analysis/timeline`** → events with dates, participants, confidence, evidence quotes + gaps

**POST `/{case_id}/analysis/discrepancies`** → contradictions, credibility notes, severity ratings

**POST `/{case_id}/analysis/policy-check`** → policy violations with evidence

**POST `/{case_id}/analysis/guidance`** → recommendation cards with actions (run_analysis|open_tab|search_evidence|upload_document) + determination signals

**POST `/{case_id}/analysis/outcomes`** → determination (substantiated|unsubstantiated|inconclusive) + recommended actions

**POST `/{case_id}/search`** — evidence search
**Request:** `{ "query": "string", "top_k?": "1-20 (default 5)" }`
**Response:** `{ "results": [{ "chunk_id", "content", "speaker?", "source_file", "document_type", "similarity": "0-1" }], "query", "total_chunks" }`

---

## 15. IR Incidents

Base path: `/api/incidents`

### POST `/`
**Request:**
```json
{
  "title": "string (1-255, required)",
  "description?",
  "incident_type": "safety|behavioral|property|near_miss|other (required)",
  "severity?": "critical|high|medium|low (default medium)",
  "occurred_at": "datetime (required)",
  "location?": "string (0-255)",
  "reported_by_name": "string (required)",
  "reported_by_email?",
  "witnesses?": [{ "name", "contact?", "statement?" }],
  "category_data?": "dict",
  "location_id?", "involved_employee_ids?": "UUID[]"
}
```

**Response:** `IRIncidentResponse` — incident_number auto-generated (IR-YYYY-MM-XXXX). Status: reported|investigating|action_required|resolved|closed.

### GET `/`
**Query:** `status?`, `incident_type?`, `severity?`, `location?` (fuzzy), `from_date?`, `to_date?`, `search?` (ILIKE on title/description), `limit?` (1-200, default 50), `offset?`
**Response:** `{ "incidents": [], "total" }`

### GET `/{incident_id}`, PUT `/{incident_id}`, DELETE `/{incident_id}`
Status change to resolved/closed auto-sets `resolved_at`. Queues email notifications.

### POST `/{incident_id}/documents`
Multipart: `file`, `document_type?` (photo|form|statement|other). Extensions: .pdf, .doc, .docx, .txt, .png, .jpg, .jpeg, .gif, .csv, .json.

### GET `/{incident_id}/documents`, DELETE `/{incident_id}/documents/{document_id}`

### Anonymous Reporting:
- **GET `/anonymous-reporting/status`** → `{ "token?", "enabled", "used" }`
- **POST `/anonymous-reporting/generate`** → generates/regenerates token
- **DELETE `/anonymous-reporting/disable`**

### OSHA Logging:
- **GET `/osha/300-log?year=YYYY`** → OSHA 300 log entries
- **GET `/osha/300-log/csv?year=YYYY`** → CSV download
- **GET `/osha/301/{incident_id}`** → OSHA 301 form data
- **GET `/osha/300a?year=YYYY`** → annual summary (deaths, days away, injuries by type, etc.)

### AI Analysis (all POST, cached):
- `/{incident_id}/analysis/categorization` → `{ "suggested_type", "confidence", "reasoning" }`
- `/{incident_id}/analysis/severity` → `{ "suggested_severity", "factors": [], "reasoning" }`
- `/{incident_id}/analysis/root-cause` → `{ "primary_cause", "contributing_factors": [], "prevention_suggestions": [] }`
- `/{incident_id}/analysis/recommendations` → `{ "recommendations": [{ "action", "priority": "immediate|short_term|long_term" }] }`
- `/{incident_id}/analysis/precedent` → similar incidents with `similarity_score` breakdown

---

## 16. Offer Letters

Base path: `/api/offer-letters`

### GET `/`
Auth: admin or client. Returns all offers for company. Redis cached.

### POST `/`
**Request:**
```json
{
  "candidate_name": "string (1-255, required)",
  "position_title": "string (1-255, required)",
  "company_name?", "salary?", "bonus?", "stock_options?",
  "start_date?", "employment_type?" (default "Full-Time Exempt"),
  "location?" (default "Remote"), "benefits?",
  "manager_name?", "manager_title?", "expiration_date?",
  "benefits_medical": bool, "benefits_medical_coverage?": "int (0-100)",
  "benefits_medical_waiting_days?" (default 0),
  "benefits_dental": bool, "benefits_vision": bool,
  "benefits_401k": bool, "benefits_401k_match?",
  "benefits_wellness?", "benefits_pto_vacation": bool,
  "benefits_pto_sick": bool, "benefits_holidays": bool, "benefits_other?",
  "contingency_background_check": bool, "contingency_credit_check": bool,
  "contingency_drug_screening": bool,
  "company_logo_url?",
  "salary_range_min?": "float (>=0)", "salary_range_max?": "float (>=0)",
  "candidate_email?", "max_negotiation_rounds?": "int (1-10, default 3)"
}
```

Status: draft|sent|accepted|rejected|expired.

### GET `/{offer_id}`, PATCH `/{offer_id}`

### POST `/plus/recommendation`
Salary guidance AI. Requires `offer_letters_plus` feature flag.

**Request:** `{ "role_title": "2-120 chars", "city": "2-120 chars", "state?", "years_experience": "0-40", "employment_type?" }`
**Response:** `{ "role_family", "normalized_city", "salary_low", "salary_mid", "salary_high", "bonus_target_pct_low", "bonus_target_pct_high", "equity_guidance", "confidence": "0.70-0.95", "rationale": [] }`

Backend uses lookup tables (ROLE_KEYWORDS, CITY_ALIASES, ROLE_BASE_RANGES) with multipliers. Not AI-generated.

### POST `/{offer_id}/send-range`
**Request:** `{ "candidate_email": "EmailStr", "salary_range_min": "float (>0)", "salary_range_max": "float (>0)" }`

Generates `candidate_token` (urlsafe, 32 chars), sets 7-day expiry. Sends email with magic link. Status → "sent".

### GET `/candidate/{token}` (PUBLIC)
No auth. Returns limited offer view for candidate. **410** if expired, **404** if not found.

### POST `/candidate/{token}/submit-range` (PUBLIC)
No auth. **Request:** `{ "range_min": "float (>=0)", "range_max": "float (>=0)" }`

**Matching logic:** overlap = max(employer_min, candidate_min) to min(employer_max, candidate_max).
- If overlap exists → "matched", midpoint salary, status → "accepted"
- Else → "no_match_low" or "no_match_high"

Sends result email to employer.

### POST `/{offer_id}/re-negotiate`
**Request:** `{ "salary_range_min?", "salary_range_max?" }`

Preconditions: offer in no_match state, rounds remaining. Generates new token, increments round, sends new email.

### GET `/{offer_id}/pdf`
Returns PDF stream (WeasyPrint). Includes logo, benefits, contingencies, signature blocks.

### POST `/{offer_id}/logo`
Multipart: `file` (image/* only). Uploads to S3. **Response:** `{ "url" }`

---

## 17. Policies

Base path: `/api/policies`

### GET `/`
**Query:** `status?` (draft|active|archived)

### POST `/`
Multipart form-data: `title`, `description?`, `content?` (default ""), `version?` (default "1.0"), `status?` (default "draft"), `file?`

**Response:** `PolicyResponse` — includes `signature_count`, `pending_signatures`, `signed_count`.

### GET `/{policy_id}`, PUT `/{policy_id}`, DELETE `/{policy_id}`

### POST `/{policy_id}/signatures`
Batch send signature requests.
**Request:** `[{ "name", "email": "EmailStr", "type": "candidate|employee|external", "id?": "UUID" }]`
**Response:** `{ "message", "signatures": count }`

Creates tokens (32-char urlsafe, 7-day expiry). Sends emails in background.

### GET `/{policy_id}/signatures`
**Response:** `PolicySignatureResponse[]` — status: pending|signed|declined|expired.

### DELETE `/signatures/{signature_id}`
Cancel signature request.

### POST `/signatures/{signature_id}/resend`
Refreshes expiry (+7 days), resends email.

---

## 18. Handbooks

Base path: `/api/handbooks`

### GET `/`
**Response:** `HandbookListItemResponse[]` — includes `pending_changes_count`, `scope_states[]`.

### GET `/profile`, PUT `/profile`
Company handbook profile (legal_name, headcount, various workforce booleans like remote_workers, tipped_employees, union_employees, etc.)

### GET `/auto-scopes`
Derives scopes from employee locations. Returns `[{ "state", "city?", "zipcode?", "location_id?" }]`

### POST `/upload`
Multipart: `file`. Uploads to S3. Returns `{ "url", "filename", "company_id" }`.

### POST `/`
**Request:**
```json
{
  "title": "2-500 chars",
  "mode": "single_state|multi_state",
  "source_type": "template|upload",
  "industry?",
  "scopes": [{ "state": "2-letter", "city?", "zipcode?", "location_id?" }],
  "profile": { /* company profile fields */ },
  "custom_sections?": [{ "section_key", "title", "content", "section_order", "section_type", "jurisdiction_scope" }],
  "guided_answers?": {},
  "file_url?",
  "create_from_template?": true,
  "auto_scope_from_employees?": false
}
```

Validation: single_state=1 scope, multi_state=2+ scopes.

### POST `/guided-draft`
AI-powered draft generation. Requires "handbooks" feature.

**Request:** `{ "title?", "mode", "scopes", "profile", "industry?", "answers": {}, "existing_custom_sections": [] }`
**Response:** `{ "industry", "summary", "clarification_needed", "questions": [{ "id", "question", "placeholder?", "required" }], "profile_updates": {}, "suggested_sections": [{ "section_key", "title", "content", "section_order", "section_type", "jurisdiction_scope" }] }`

429 if rate limited. Iterative: provide answers to skip clarification.

### Wizard Draft (per-user, per-company):
- **GET `/wizard-draft`** → draft state or null
- **PUT `/wizard-draft`** → `{ "state": {} }` — arbitrary state dict
- **DELETE `/wizard-draft`**

### GET `/{handbook_id}`
Full detail with sections. **Response:** includes `sections[]` (section_key, title, content, section_order, section_type, jurisdiction_scope, last_reviewed_at).

### PUT `/{handbook_id}`

### POST `/{handbook_id}/publish`
Sets status="active", published_at=NOW(), creates version record.

### POST `/{handbook_id}/archive`

### Changes (from freshness checks):
- **GET `/{handbook_id}/changes`** → pending/accepted/rejected change requests with proposed_content, rationale, source_url
- **POST `/{handbook_id}/changes/{change_id}/accept`**
- **POST `/{handbook_id}/changes/{change_id}/reject`**

### POST `/{handbook_id}/distribute`
**Request:** `{ "employee_ids?": [] }` — empty = all active employees.
**Response:** `{ "handbook_id", "handbook_version", "assigned_count", "skipped_existing_count", "distributed_at" }`

### GET `/{handbook_id}/distribution-recipients`
**Response:** `[{ "employee_id", "name", "email", "invitation_status?", "already_assigned" }]`

### GET `/{handbook_id}/acknowledgements`
**Response:** `{ "handbook_id", "handbook_version", "assigned_count", "signed_count", "pending_count", "expired_count" }`

### Freshness:
- **GET `/{handbook_id}/freshness-check/latest`** → check results + findings
- **POST `/{handbook_id}/freshness-check`** → triggers new check

### GET `/{handbook_id}/coverage`
**Response:** strength_score (0-100), state-by-state coverage, missing_sections with priority.

### POST `/{handbook_id}/sections/{section_id}/mark-reviewed`
Sets last_reviewed_at=NOW().

### GET `/{handbook_id}/pdf`
Template → generated PDF. Upload → original file from S3.

---

## 19. Employee Portal

Base path: `/api/v1/portal`

### GET `/me`
**Response:** `{ "employee": EmployeeResponse, "pto_balance", "pending_tasks_count", "pending_documents_count", "pending_pto_requests_count" }`

### PATCH `/me`
**Request:** `{ "phone?", "address?", "emergency_contact?" }` — employee self-service profile update.

### PTO:
- **GET `/me/pto`** — PTO summary
- **POST `/me/pto/request`** — `{ "start_date", "end_date", "hours", "reason?", "request_type?" }`
- **DELETE `/me/pto/request/{requestId}`** — cancel

### Leave:
- **GET `/me/leave`** — `{ "requests": [], "total" }`. Query: `status_filter?`
- **GET `/me/leave/{leaveId}`**
- **POST `/me/leave/request`** — `{ "leave_type", "start_date", "end_date?", "expected_return_date?", "reason?", "intermittent?", "intermittent_schedule?" }`
- **DELETE `/me/leave/{leaveId}`** — cancel. Returns `{ "status", "leave_id" }`
- **GET `/me/leave/eligibility`**

### Documents:
- **GET `/me/documents`** — Query: `status_filter?`
- **GET `/me/documents/{documentId}`**
- **POST `/me/documents/{documentId}/sign`** — `{ "signature_data" }`

### Policies:
- **GET `/me/../policies`** — Query: `q?` (search)
- **GET `/me/../policies/{policyId}`**

### Tasks:
- **GET `/me/tasks`** — pending documents, PTO, onboarding tasks

### Priority Tasks:
- **GET `/me/priorities`**
- **PATCH `/me/priorities/{taskId}`** — `{ "notes?" }`

### Internal Mobility:
- **GET `/me/mobility/profile`** — `{ "target_roles", "target_departments", "skills", "interests", "mobility_opt_in" }`
- **PUT `/me/mobility/profile`**
- **GET `/me/mobility/feed`** — Query: `status_filter?` (default "active")
- **POST `/me/mobility/opportunities/{id}/save`**
- **DELETE `/me/mobility/opportunities/{id}/save`**
- **POST `/me/mobility/opportunities/{id}/dismiss`**
- **POST `/me/mobility/opportunities/{id}/apply`** — `{ "employee_notes?" }`

---

## 20. Broker Portal

Base path: `/api/brokers`

### POST `/client-setups`
**Request:**
```json
{
  "company_name", "industry?", "company_size?", "headcount?",
  "contact_name?", "contact_email?", "contact_phone?",
  "preconfigured_features": "dict[bool]",
  "onboarding_template": "dict",
  "link_permissions": "dict",
  "invite_immediately": bool,
  "invite_expires_days": "1-90 (default 14)"
}
```
**Response:** `{ "status", "setup", "invite_email_sent?", "invite_email_error?" }`

### PATCH `/client-setups/{setupId}`
### GET `/client-setups`
**Query:** `status?`

### POST `/client-setups/{setupId}/send-invite`
**Request:** `{ "expires_days": "1-90 (default 14)" }`. Generates invite token, sends email.

### POST `/client-setups/{setupId}/cancel`
### POST `/client-setups/expire-stale`

### Reporting:
- **GET `/reporting/portfolio`** — setup counts by status, feature adoption
- **GET `/reporting/handbook-coverage`** — handbook coverage summary per client
- **GET `/referred-clients`** — `{ "broker_slug", "total", "clients": [] }`

---

## 21. Admin Panel

Base path: `/api/admin`

### GET `/overview`
Platform stats: companies with employee counts.

### GET `/api-usage`
Gemini API usage stats.

### Business Registrations:
- **GET `/business-registrations`** — Query: `status?`. Returns registrations + owner info + approver
- **GET `/business-registrations/{company_id}`**
- **PATCH `/business-registrations/{company_id}`** — update company/owner details
- **POST `/business-registrations/{company_id}/approve`** — sends approval email
- **POST `/business-registrations/{company_id}/reject`** — `{ "reason" }` — sends rejection email

### Business Invites:
- **GET `/business-invites`**
- **POST `/business-invites`** — `{ "note?", "expires_days?" (1-90, default 7) }` → `{ "token", "invite_url" }`
- **DELETE `/business-invites/{invite_id}`**

### Company Features:
- **GET `/company-features`** — all companies with enabled_features
- **PATCH `/company-features/{company_id}`** — `{ "feature", "enabled": bool }`

Known features: policies, handbooks, compliance, employees, er_copilot, incidents, time_off, accommodations, interview_prep, matcha_work, risk_assessment, training, i9, cobra, separation_agreements

### Companies:
- **GET `/companies`** — with user_count, location_count
- **GET `/companies/{company_id}`** — full detail + users + jurisdictions
- **GET `/companies/{company_id}/employees`**
- **GET `/employees/{employee_id}`** — includes healthcare credentials (decrypted)
- **PATCH `/companies/{company_id}`**
- **DELETE `/companies/{company_id}`** — soft delete

### Credits:
- **POST `/companies/{company_id}/credits`** — `{ "credits": int, "description" }` → balance + transaction

### Candidate Management:
- **GET `/candidates/beta`** — candidates with beta features, session stats
- **PATCH `/candidates/{user_id}/beta`** — `{ "feature", "enabled" }`
- **POST `/candidates/{user_id}/tokens`** — `{ "amount": "int (>0)" }` → `{ "new_total" }`
- **PUT `/candidates/{user_id}/roles`** — `{ "roles": [] }`
- **GET `/candidates/{user_id}/sessions`** — interview prep sessions

### Brokers (admin CRUD):
- **POST `/brokers`** — create broker organization
- **GET `/brokers`** — list all
- **PATCH `/brokers/{broker_id}`** — update
- **PUT `/brokers/{broker_id}/contract`** — set contract terms
- **PUT `/brokers/{broker_id}/companies/{company_id}`** — link company to broker
- **GET `/brokers/{broker_id}/branding`**, **PUT `/brokers/{broker_id}/branding`** — white-label config
- **GET `/brokers/{broker_id}/companies/{company_id}/transitions`** — link state transitions
- **POST `/brokers/{broker_id}/companies/{company_id}/transitions`** — create transition
- **PATCH `/brokers/{broker_id}/companies/{company_id}/transitions/{transition_id}`**

### Jurisdictions (admin data management):
- **POST `/jurisdictions`** — create jurisdiction
- **GET `/jurisdictions`** — list with requirement counts
- **GET `/jurisdictions/{jurisdiction_id}`** — full requirements
- **DELETE `/jurisdictions/{jurisdiction_id}`**
- **GET `/jurisdictions/data-overview`** — coverage stats
- **POST `/jurisdictions/cleanup-duplicates`**
- **PATCH `/jurisdictions/requirements/{requirement_id}`** — edit requirement
- **POST `/jurisdictions/requirements/{requirement_id}/bookmark`**
- **GET `/jurisdictions/requirements/bookmarked`**
- **PUT `/jurisdictions/requirements/reorder`**
- **POST `/jurisdictions/{jurisdiction_id}/check`** — trigger Gemini research
- **POST `/jurisdictions/{jurisdiction_id}/check-specialty`** — specialty research
- **POST `/jurisdictions/{jurisdiction_id}/check-medical-compliance`** — healthcare compliance research
- **POST `/jurisdictions/top-metros/check`** — batch research

### Schedulers:
- **GET `/schedulers`**, **PATCH `/schedulers/{task_key}`**, **POST `/schedulers/{task_key}/trigger`**
- **GET `/schedulers/stats`**, **GET `/schedulers/locations`**, **PATCH `/schedulers/locations/{location_id}`**

### Posters:
- **GET `/posters/templates`**, **POST `/posters/templates/{jurisdiction_id}`**, **POST `/posters/generate-all`**
- **GET `/posters/orders`**, **GET `/posters/orders/{order_id}`**, **PATCH `/posters/orders/{order_id}`**

### Platform Settings:
- **GET `/platform-settings`**
- **GET/PUT `/platform-settings/features`** — visible feature list
- **PUT `/platform-settings/matcha-work-model-mode`**
- **PUT `/platform-settings/jurisdiction-research-model-mode`**
- **GET/PUT `/platform-settings/er-similarity-weights`**

### Industry Profiles:
- **GET `/industry-profiles`**, **POST**, **PUT `/{profile_id}`**, **DELETE `/{profile_id}`**

### Jurisdiction Requests:
- **GET `/jurisdiction-requests`**, **POST `/{request_id}/process`**, **POST `/{request_id}/dismiss`**

### Research Queue:
- **GET `/research-queue`**, **POST `/research-queue/{jurisdiction_id}/research`**

### Error Logs:
- **GET `/error-logs`**, **DELETE `/error-logs`**

---

## 22. AI Chat

Separate JWT system. Base path: `/api/chat`

### Auth:
- **POST `/auth/register`** — `{ "email", "password", "first_name", "last_name" }` → `ChatTokenResponse`
- **POST `/auth/login`** — `{ "email", "password" }` → `ChatTokenResponse` — `{ "access_token", "refresh_token", "user" }`
- **POST `/auth/refresh`** — `{ "refresh_token" }`
- **GET `/auth/me`** — returns `ChatUserPublic` { id, email, first_name, last_name, avatar_url, bio, last_seen }

### Rooms:
- **GET `/rooms`** — Query: `current_user?`. Returns rooms with `unread_count`, `member_count`, `is_member`
- **GET `/rooms/{slug}`**
- **POST `/rooms/{slug}/join`**, **POST `/rooms/{slug}/leave`**
- **GET `/rooms/{slug}/members`**
- **POST `/rooms/{slug}/mark-read`**

### Messages:
- **GET `/rooms/{slug}/messages`** — Query: `limit` (1-100, default 50), `cursor` (base64). Cursor-based pagination.
  **Response:** `{ "messages": [], "next_cursor", "has_more" }`
- **POST `/rooms/{slug}/messages`** — `{ "content" }`
- **PATCH `/rooms/{slug}/messages/{message_id}`** — `{ "content" }` (owner only)
- **DELETE `/rooms/{slug}/messages/{message_id}`** (owner only)

### WebSocket:
**WS** at `{VITE_CHAT_API_URL}` converted from http(s) to ws(s). Token via chat access token.

---

## 23. Risk Assessment

Base path: `/api/risk-assessment`

### Access Matrix

| Endpoint group | client / employee | admin |
|---|---|---|
| `GET /` | ✅ own company snapshot | ✅ any company via `?company_id=` |
| `GET /history` | ✅ | ✅ + `?company_id=` |
| `GET /monte-carlo` | ✅ | ✅ + `?company_id=` |
| `GET /cohorts` | ✅ | ✅ + `?company_id=` |
| `GET /benchmarks` | ✅ | ✅ + `?company_id=` |
| `GET /anomalies` | ✅ | ✅ + `?company_id=` |
| `GET/POST/PUT /action-items` | ✅ own company | ✅ |
| `GET /assignable-users` | ✅ | ✅ |
| `GET/PUT /admin/weights` | ❌ | ✅ |
| `POST /admin/run/{company_id}` | ❌ | ✅ |
| `POST /admin/monte-carlo/{company_id}` | ❌ | ✅ |

### Architecture Notes
- **Snapshot pattern**: Admin triggers computation; the result is stored once. Client always reads the latest stored snapshot — no live computation on client requests.
- **`company_id` query param**: Admin-only override on all read endpoints. For client/employee roles the param is ignored and their own company is used.
- **Gemini AI**: Generates `report` (narrative string) and `recommendations[]` during snapshot computation (`POST /admin/run/{company_id}`).
- **Cost of Risk**: Nested inside each dimension as `dimensions.{dim}.raw_data.cost_of_risk` — a `CostOfRisk` object with line-item array.
- **Dimension weights**: Stored in `platform_settings` table, adjustable via admin weights endpoints. Default: `compliance=0.30`, `incidents=0.25`, `er_cases=0.25`, `workforce=0.15`, `legislative=0.05`.

---

### TypeScript Types

```typescript
// ── Shared primitives ──────────────────────────────────────────────────

interface CostLineItem {
  label: string;
  amount: number;          // USD estimate
  basis: string;           // explanation of how the amount was derived
}

interface CostOfRisk {
  total: number;
  items: CostLineItem[];
}

interface DimensionResult {
  score: number;           // 0–100
  weight: number;          // e.g. 0.30
  weighted_score: number;
  details: Record<string, unknown>;   // dimension-specific sub-metrics
  raw_data: {
    cost_of_risk?: CostOfRisk;
    [key: string]: unknown;
  };
}

interface RiskRecommendation {
  dimension: string;       // "compliance" | "incidents" | "er_cases" | "workforce" | "legislative"
  priority: "high" | "medium" | "low";
  title: string;
  guidance: string;
}

interface RiskAssessmentResult {
  overall_score: number;   // 0–100
  overall_band: "Low" | "Moderate" | "High" | "Critical";
  dimensions: {
    compliance: DimensionResult;
    incidents: DimensionResult;
    er_cases: DimensionResult;
    workforce: DimensionResult;
    legislative: DimensionResult;
  };
  weights: {
    compliance: number;
    incidents: number;
    er_cases: number;
    workforce: number;
    legislative: number;
  };
  computed_at: string;     // ISO datetime
  report?: string;         // Gemini narrative
  recommendations: RiskRecommendation[];
}

// ── History ────────────────────────────────────────────────────────────

interface RiskHistoryEntry {
  computed_at: string;
  overall_score: number;
  overall_band: string;
  dimension_scores: {
    compliance: number;
    incidents: number;
    er_cases: number;
    workforce: number;
    legislative: number;
  };
}

// ── Monte Carlo ────────────────────────────────────────────────────────

interface MonteCarloCategoryResult {
  category: string;
  expected_loss: number;
  p50: number;
  p75: number;
  p90: number;
  p95: number;
}

interface MonteCarloAggregateResult {
  expected_loss: number;
  p50: number;
  p75: number;
  p90: number;
  p95: number;
  histogram: Array<{ bin_start: number; bin_end: number; frequency: number }>;
}

interface MonteCarloResult {
  simulations: number;            // number of iterations run
  aggregate: MonteCarloAggregateResult;
  by_category: MonteCarloCategoryResult[];
  computed_at: string;
}

// ── Cohorts ────────────────────────────────────────────────────────────

interface CohortResult {
  cohort_key: string;             // e.g. "Engineering", "2023-Q1"
  dimension: string;
  score: number;
  count: number;                  // number of employees in cohort
}

// ── Benchmarks ────────────────────────────────────────────────────────

interface BenchmarkMetric {
  dimension: string;
  company_score: number;
  industry_median: number;
  industry_p25: number;
  industry_p75: number;
  percentile_rank: number;        // 0–100, where company falls vs peers
}

interface BenchmarkResult {
  naics_code: string;
  naics_label: string;
  peer_count: number;
  metrics: BenchmarkMetric[];
  computed_at: string;
}

// ── Anomaly Detection ─────────────────────────────────────────────────

interface MetricTimeSeries {
  metric: string;
  points: Array<{ date: string; value: number }>;
}

interface AnomalyItem {
  metric: string;
  detected_at: string;
  value: number;
  expected_range: [number, number];
  sigma: number;                  // standard deviations from mean
  dimension: string;
}

interface AnomalyDetectionResult {
  anomalies: AnomalyItem[];
  time_series: MetricTimeSeries[];
  months_analyzed: number;
}

// ── Action Items ──────────────────────────────────────────────────────

interface RiskActionItem {
  id: number;
  company_id: number;
  title: string;
  description?: string;
  source_type?: "wage_violation" | "er_case" | string;
  source_ref?: string;
  assigned_to?: number;           // user_id
  assigned_to_name?: string;      // resolved display name
  due_date?: string;              // ISO date
  status: "open" | "completed";
  created_at: string;
  updated_at: string;
}

interface RiskActionItemCreate {
  title: string;
  description?: string;
  source_type?: string;
  source_ref?: string;
  assigned_to?: number;
  due_date?: string;
}

interface RiskActionItemUpdate {
  assigned_to?: number;
  due_date?: string;
  status?: "open" | "completed";
  title?: string;
  description?: string;
}

// ── Assignable Users ──────────────────────────────────────────────────

interface AssignableUser {
  id: number;
  name: string;
  email: string;
  role: string;
}
```

---

### Endpoints

#### `GET /`
Auth: admin or client/employee.
**Query:** `company_id?` (admin-only override)
**Response:** `RiskAssessmentResult`

#### `GET /history`
**Query:** `months` (int, 1–36, default 12)
**Response:** `RiskHistoryEntry[]` — ordered oldest → newest

#### `GET /monte-carlo`
**Query:** `company_id?` (admin-only)
**Response:** `MonteCarloResult` — pulled from latest stored snapshot

#### `GET /cohorts`
**Query:** `dimension` — `"department" | "location" | "hire_quarter" | "tenure"`, `company_id?` (admin-only)
**Response:** `CohortResult[]`

#### `GET /benchmarks`
**Query:** `company_id?` (admin-only)
**Response:** `BenchmarkResult`

#### `GET /anomalies`
**Query:** `months` (int, 6–36, default 24), `company_id?` (admin-only)
**Response:** `AnomalyDetectionResult`

#### `GET /action-items`
**Query:** `status` — `"open"` (default) | `"all"`
**Response:** `RiskActionItem[]`

#### `POST /action-items`
**Body:** `RiskActionItemCreate`
**Response:** `RiskActionItem`

#### `PUT /action-items/{item_id}`
**Body:** `RiskActionItemUpdate`
**Response:** `RiskActionItem`

#### `GET /assignable-users`
Returns company owner + all users with admin role for the company.
**Response:** `AssignableUser[]`

#### Admin: `GET /admin/weights`
**Response:**
```typescript
{
  compliance: number;
  incidents: number;
  er_cases: number;
  workforce: number;
  legislative: number;   // all five must sum to 1.0
}
```

#### Admin: `PUT /admin/weights`
**Body:** same shape as above (all five fields required, must sum to 1.0)
**Response:** updated weights object

#### Admin: `POST /admin/run/{company_id}`
Triggers full snapshot computation: scores all 5 dimensions, runs Gemini for `report` + `recommendations`, persists result.
**Response:** `RiskAssessmentResult`

#### Admin: `POST /admin/monte-carlo/{company_id}`
Re-runs Monte Carlo simulation for the company's latest snapshot and updates stored simulation result.
**Response:** `MonteCarloResult`

---

## 24. Matcha Work

Base path: `/api/matcha-work`

### Threads:
- **POST `/threads`** — `{ "title?", "initial_message?", "task_type?" }` → creates AI conversation thread
- **GET `/threads`** — Query: `status?`, `limit?`, `offset?`
- **GET `/threads/{threadId}`** — full detail with `current_state` (document data), `messages[]`, `versions[]`
- **PATCH `/threads/{threadId}`** — `{ "title" }`
- **DELETE `/threads/{threadId}`** — archives

### Elements:
- **GET `/elements`** — finalized documents. Query: `status?`, `limit?`, `offset?`

### Messaging:
- **POST `/threads/{threadId}/messages`** — `{ "content" }` → `{ "message", "updated_state", "version_created" }`
- **POST `/threads/{threadId}/messages/stream`** (SSE) — `{ "content", "slide_index?" }` → events: message_content, state_update, complete

### Versions:
- **GET `/threads/{threadId}/versions`** — document version history
- **POST `/threads/{threadId}/revert`** — `{ "version" }`

### Save & Finalize:
- **POST `/threads/{threadId}/save-draft`**
- **POST `/threads/{threadId}/finalize`**

### PDF:
- **GET `/threads/{threadId}/pdf`** — Query: `version?` → `{ "pdf_url", "version" }`

### Uploads:
- **POST `/threads/{threadId}/logo`** — multipart image → `{ "logo_url" }`
- **POST `/threads/{threadId}/handbook/upload`** — multipart PDF/DOC/DOCX (max 10MB) → SSE stream with handbook_progress events

### Usage & Billing:
- **GET `/usage/summary`** — Query: `period_days` (default 30)
- **GET `/billing/balance`** — `{ "available_tokens", "credits", "subscription" }`
- **GET `/billing/packs`** — available credit packs
- **POST `/billing/checkout`** — `{ "pack_id", "auto_renew?", "success_url?", "cancel_url?" }` → `{ "checkout_url" }`
- **GET `/billing/subscription`** — status, dates
- **DELETE `/billing/subscription`** — cancel
- **GET `/billing/transactions`** — Query: `limit?`, `offset?`

### Review Requests:
- **GET `/threads/{threadId}/review-requests`**
- **POST `/threads/{threadId}/review-requests/send`** — `{ "recipient_emails?", "custom_message?" }`
- **GET `/public/review-requests/{token}`** (no auth)
- **POST `/public/review-requests/{token}/submit`** (no auth) — `{ "feedback", "rating?" }`

### Handbook Signatures:
- **POST `/threads/{threadId}/handbook/send-signatures`** — `{ "handbook_id", "employee_ids?" }`

### Presentations:
- **POST `/threads/{threadId}/presentation/generate`**
- **GET `/threads/{threadId}/presentation/pdf`** → `{ "pdf_url" }`

---

## 25. Blog

Base path: `/api/blogs`

### Public:
- **GET `/`** — Query: `page` (default 1), `limit` (default 10), `status?`, `tag?`. **Response:** `{ "items": [], "total" }`
- **GET `/{slug}`** — Query: `session_id?` (for guest likes). Includes `liked_by_me`.
- **POST `/{slug}/like`** — `{ "session_id?" }` → `{ "likes_count", "liked" }`
- **GET `/{slug}/comments`** — approved only, ASC order
- **POST `/{slug}/comments`** — `{ "content", "author_name?" }` — auto-approved for users, pending for guests

### Admin:
- **POST `/`** — `{ "title", "slug", "content", "excerpt?", "cover_image?", "status", "tags": [], "meta_title?", "meta_description?" }`
- **PUT `/{id}`** — all fields optional
- **DELETE `/{id}`**
- **POST `/upload`** — multipart image → `{ "url" }`
- **GET `/comments/pending`** — all pending comments
- **PATCH `/comments/{id}`** — update comment status

---

## 26. Interviews & Tutor

### Interview Creation:
**POST `/api/companies/{company_id}/interviews`** (no auth)
**Request:** `{ "interviewer_name", "interviewer_role", "interview_type": "candidate|culture|screening" }`
**Response:** `{ "interview_id", "websocket_url", "ws_auth_token" }`

### Tutor Sessions:
**POST `/api/tutor/sessions`** (requires auth)
**Request:** `{ "mode": "interview_prep|language_test|culture|screening|candidate", "company_id?", "language?", "interview_role?", "is_practice?", "duration_minutes?" }`
**Response:** `{ "interview_id", "websocket_url", "ws_auth_token?", "max_session_duration_seconds" }`

Candidate mode checks beta access + token balance.

### WebSocket:
**WS `/ws/interview/{interview_id}`** — Auth: `Authorization: Bearer {ws_auth_token}`
Audio: PCM 16-bit signed, 16kHz mono. Control messages: start, audio, text_input, stop.

### Analysis:
- **POST `/api/interviews/{id}/analyze`** — trigger analysis generation
- **GET `/api/interviews/{id}/analysis`** — retrieve stored analysis

---

## Common Patterns

### Error Response Format
```json
{ "detail": "Error message" }
```
Status codes: 400 (validation), 401 (auth), 403 (forbidden), 404 (not found), 410 (expired), 413 (file too large), 429 (rate limit), 500 (server error).

### File Upload
All uploads go to S3 via `get_storage()`. Max 50MB for documents, 10MB for handbook uploads. Returns S3/CloudFront URL.

### Caching
Offer letters and jurisdictions cached in Redis. Invalidated on write. Admin requests may bypass cache.

### Email
Async via background tasks (non-blocking). Fails gracefully with warnings logged.

### PDF Generation
WeasyPrint for offer letters and handbooks. Returns streaming response.

### Feature Flags
Companies have `enabled_features` (JSONB). Checked via `require_feature()` dependency or `hasFeature()` on client. Known features listed under Admin Panel section.
