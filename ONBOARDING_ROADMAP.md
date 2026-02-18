# Onboarding Roadmap — Matcha Recruit

> Goal: Reach competitive parity with Rippling/Gusto on the onboarding experience within ~20 weeks.
> This document is grounded in the current codebase state and organized as two parallel tracks:
> **Track A — Admin/HR** (workflow intelligence, compliance, analytics) and
> **Track B — New Hire Experience** (self-service portal, day-one readiness, benefits, mobile).
> Both tracks ship simultaneously. Neither can succeed without the other.

---

## Current State (What We Have)

The foundation is stronger than the Codex plan assumed. Before adding anything, we should know what already ships:

- ✅ Invitation flow (token → account creation → welcome email)
- ✅ Admin task template library (5 categories: documents, equipment, training, admin, return-to-work)
- ✅ Employee task assignment + status tracking (admin and employee views)
- ✅ Employee portal with onboarding task view (`PortalOnboarding.tsx`)
- ✅ Document upload + signature workflow
- ✅ Google Workspace auto-provisioning with retry logic
- ✅ Provisioning audit log
- ✅ Bulk CSV import + bulk invite
- ✅ Policy acknowledgment
- ✅ Return-to-work workflow (post-leave tasks)
- ✅ WebSocket real-time notifications infrastructure
- ✅ Leave/PTO with compliance eligibility

**Genuine gaps:** offboarding, benefits enrollment, conditional workflows, compliance packet automation (I-9/W-4), Slack provisioning completion, analytics, manager experience, notifications/reminders as a system, mobile portal.

---

## Competitive Release Gate (Week 1)

Before writing a line of code, define the "must-have parity" checklist that gates a competitive v1. Every item below should have a clear owner and a binary done/not-done state.

| Capability | Current | Gate Requirement |
|---|---|---|
| Preboarding (tasks before start date) | Partial | New hire can complete tasks before day 1 |
| Compliance forms | Document upload only | I-9, W-4, state-specific forms collected and stored |
| E-sign | Basic signature tracking | Legally binding e-sign with audit trail |
| Conditional workflows | None | Templates branch by role/location/type |
| IT provisioning | Google only | Google + Slack, manual override for others |
| Reminders & escalations | None | Automated reminders to new hire, manager, HR |
| Analytics | None | Funnel dashboard + time-to-ready metric |
| Offboarding | None | Exit checklist, access revocation, equipment return |
| New hire experience | Basic portal | Guided, mobile-friendly, progress-visible journey |
| Benefits enrollment | None | Plan selection with confirmation tracking |
| Lifecycle source of truth | Implicit | Canonical hire event + clear ownership boundaries |
| RBAC/governance | Partial | Role matrix for publish/override/deprovision actions |
| Security/privacy controls | Partial | PII retention, DSAR/export/delete, immutable audit evidence |
| Reliability operations | Partial | SLOs, runbooks, DLQ/retry policy, incident ownership |
| Integration contract | Google-first | Provider-agnostic API + inbound/outbound webhooks |

This scorecard is the release gate. Ship when all rows are green.

---

## Operating Model Foundations (Weeks 1–2)

This section defines non-negotiable architecture contracts. Build this first so implementation work across all phases stays consistent.

### 1) Lifecycle source of truth and handoff boundaries

- **Canonical onboarding start event:** `hire_activated`.
- A case starts when either:
  - an offer is accepted, or
  - an employee is created directly by HR.
- **Boundary contract:** ATS/offer systems own candidate lifecycle; onboarding owns employee lifecycle from `hire_activated`; payroll owns pay setup and post-hire payroll state.
- **Idempotency:** the same external hire event can be replayed safely with `source_system + source_event_id` unique key.

### 2) Canonical onboarding state machine

All onboarding APIs must enforce one shared state model:

- `prehire` -> `invited` -> `accepted` -> `in_progress` -> `ready_for_day1` -> `active`
- Exceptional states: `blocked`, `cancelled`, `offboarding_in_progress`, `offboarded`

Rules:
- Transitions are explicit and auditable.
- `ready_for_day1` requires all employee-assigned required tasks + required compliance packet complete.
- `blocked` requires a `block_reason` code (dependency, missing_document, integration_error, approval_pending, other).

### 3) RBAC and approvals model

Define and enforce role capabilities before adding advanced workflow features:

- `admin`: full control (publish templates, overrides, deprovision, analytics)
- `client_hr`: create/edit employees, assign tasks, trigger provisioning, cannot change global policy controls
- `manager`: complete manager-lane tasks, view direct-report onboarding status
- `it_operator`: complete IT-lane tasks, run provider-specific provisioning/deprovisioning
- `employee`: complete employee-lane tasks only

Approval gates:
- Publishing template versions requires `admin` or delegated approver permission.
- Compliance force-complete and manual provisioning overrides require reason + actor + timestamp.

### 4) Data governance, privacy, and retention baseline

- Define PII data classes and storage boundaries (employee profile vs. compliance payloads vs. audit logs).
- Add retention schedules per artifact type (compliance forms, signatures, audit events, inactive onboarding cases).
- Add DSAR support: employee data export and deletion/anonymization flow with legal-hold bypass rules.
- Audit evidence must be append-only at storage layer (no in-place edit of signed evidence payloads).

### 5) Integration contract strategy (beyond Google/Slack)

- Create provider-agnostic endpoints:
  - `POST /provisioning/employees/{employee_id}/{provider}`
  - `POST /provisioning/employees/{employee_id}/{provider}/manual`
  - `DELETE /provisioning/employees/{employee_id}/{provider}/manual`
- Add outbound webhooks for `onboarding.case.created`, `onboarding.task.completed`, `onboarding.case.ready_for_day1`, `onboarding.case.blocked`.
- Add inbound webhook contract for ATS/HRIS/payroll hire updates with signature verification and replay protection.

### 6) Analytics instrumentation plan (starts in Week 2)

- Define event schema now: `event_name`, `case_id`, `employee_id`, `task_id`, `actor_id`, `provider`, `occurred_at`, `metadata`.
- Emit events from day one of A1/B1 so KPI backfill is not needed in A5.
- Establish event quality checks: required fields, duplicate event detection, clock skew handling.

---

## Track A — Admin & HR Intelligence

### Phase A1: Workflow Engine (Weeks 2–6)

**Problem:** Task templates are flat lists. There's no way to say "only show this task if location = California" or "this task must complete before the next one starts."

**What to build:**
- **Template conditions:** Add a `conditions` JSONB field to `onboarding_tasks`. Supported keys: `employment_type`, `work_state`, `role_type`, `department`. On `assign-all`, evaluate conditions against the employee record and skip non-matching tasks.
- **Task dependencies:** Add `depends_on_task_id` to `employee_onboarding_tasks`. The portal and admin view block dependent tasks until prerequisites are complete.
- **Assignee lanes:** Each task gets an `assignee_type` (employee / manager / HR / IT). The admin dashboard and portal filter by lane. IT tasks go to a separate IT queue view.
- **Template versioning:** Add `version` and `is_draft` to the template. Assign-all always uses the latest published version. Active employee checklists pin to the version they were assigned from.
- **State machine enforcement:** On every lifecycle mutation, validate transition against the canonical onboarding state machine and write transition event records.
- **API idempotency keys:** Add idempotency support for invite, assign-all, and case-start actions to prevent duplicate operations during retries.

**Key files:** `server/app/matcha/routes/onboarding.py`, `server/app/matcha/routes/employees.py`, `client/src/pages/OnboardingTemplates.tsx`, `client/src/pages/OnboardingCenter.tsx`

### Phase A2: Notifications & Reminders (Weeks 4–7, overlaps A1)

**Problem:** The WebSocket notification infrastructure exists but there's no scheduled reminder system. New hires fall through because nobody follows up.

**What to build:**
- **Reminder scheduler:** Celery periodic task that checks `employee_onboarding_tasks` for tasks overdue by >N days and fires reminder events. Configurable per template: `reminder_days_before_due`, `escalate_after_days`.
- **Escalation chain:** Task overdue → remind assignee (day 1) → remind manager (day 3) → alert HR (day 5). Escalation targets stored per-company.
- **Email templates:** Add to `email.py`: `send_task_reminder()`, `send_task_escalation()`, `send_manager_onboarding_summary()` (weekly digest for managers).
- **Notification preferences:** Per-user opt-in for email vs. in-app. Start with email-first, in-app as secondary.
- **Business calendar + timezone logic:** Define company timezone and business-day calendar. SLA timers, reminders, and "overdue" calculations run in company local time and skip configured non-business days.
- **Quiet hours:** Add notification quiet-hour windows by timezone to avoid overnight spam.

**Key files:** `server/app/core/services/email.py`, `server/app/matcha/workers/`, `server/app/matcha/routes/employees.py`

### Phase A3: Compliance Packet Automation (Weeks 8–12)

**Problem:** Document upload exists but compliance forms (I-9, W-4, state withholding, direct deposit, policy sign-offs) are not first-class onboarding steps — they're just file uploads with no validation or completeness tracking.

**What to build:**
- **Compliance form catalog:** A set of structured form definitions (not just PDF uploads) for I-9, W-4, state withholding by `work_state`, direct deposit authorization. Each form has required fields, validation rules, and a completed/incomplete state.
- **Form completion tracking:** `onboarding_compliance_forms` table: `employee_id`, `form_type`, `status`, `completed_at`, `data` (JSONB), `file_url`.
- **Jurisdiction awareness:** On employee create, auto-attach the correct state withholding form based on `work_state`. Leverage the existing compliance service in `server/app/core/services/compliance_service.py`.
- **E-sign audit trail:** Extend the existing `policy_signatures` pattern to include IP address, timestamp, and user agent for legal defensibility. Generate a PDF audit record on completion.
- **Export:** `GET /employees/{id}/compliance-packet` returns a ZIP of all signed forms for a given employee. Used for audits and offboarding.
- **I-9 operational workflow detail:** Model I-9 section completion milestones, due windows, correction/amendment flow, reverification reminders, and late-completion exception logging.
- **W-4/state withholding corrections:** Support amendment submissions with prior-version retention and reason codes.
- **Optional E-Verify phase gate:** Keep behind feature flag; allow async case creation/status sync once compliance maturity is proven.

**Key files:** `server/app/core/services/compliance_service.py`, `server/app/matcha/routes/employee_portal.py`, `client/src/pages/portal/PortalDocuments.tsx`

### Phase A4: Offboarding & Cross-boarding (Weeks 13–16)

**Problem:** Offboarding is completely absent. This is a competitive gap and a compliance/security risk — access revocation and equipment return have no workflow.

**What to build:**
- **Offboarding case:** `POST /employees/{id}/offboard` creates an offboarding case with last-day, reason, and voluntary/involuntary flag.
- **Offboarding checklist:** Mirror the onboarding template system with offboarding-specific categories: `access_revocation`, `equipment_return`, `knowledge_transfer`, `exit_interview`, `final_payroll`, `benefits_termination`.
- **Provisioning teardown:** Extend `onboarding_orchestrator.py` to run deprovision steps (disable Google Workspace account, remove Slack workspace membership) when offboarding case is created.
- **Cross-boarding:** A lightweight "role change" event that re-triggers relevant onboarding tasks (new access grants, new policy acknowledgments) without re-running the full onboarding flow.
- **Rehire flow:** Reopen prior employee profile where allowed, preserve historical records, create new onboarding case with rehire template variant.
- **Transfer/legal-entity flow:** Support internal transfer between departments/entities/locations with selective task regeneration and compliance packet delta rules.

**Key files:** `server/app/matcha/services/onboarding_orchestrator.py`, `server/app/matcha/routes/employees.py`, `client/src/pages/OnboardingCenter.tsx`

### Phase A5: Analytics & Controls (Weeks 17–20)

**Problem:** No visibility into whether onboarding is working. "Time to first-day-ready" is a KPI with no dashboard.

**What to build:**
- **Funnel metrics:** For each employee, track: `invited_at`, `accepted_at`, `first_task_completed_at`, `all_tasks_completed_at`, `compliance_complete_at`. Expose as `GET /onboarding/analytics`.
- **Bottleneck dashboard:** Show which tasks have the highest overdue rate, which templates get skipped most, which employees are at risk of missing start date.
- **KPI cards:** Time to first-day-ready (p50/p90), % complete before start date, automation success rate (provisioning), manual intervention rate, form error rate.
- **Admin controls:** Template governance — publish/archive/version templates. Change management: editing a live template shows a diff and requires confirmation. Role-based access for who can create vs. publish templates.
- **Operational SLOs:** Define targets for onboarding API availability, worker processing latency, reminder dispatch success, and provisioning completion latency.
- **Runbooks + incident ownership:** Add documented triage flows for failed provisioning bursts, reminder backlog growth, and compliance form processing failures.
- **Failure isolation:** Add dead-letter queues + replay tooling for onboarding events/tasks.

**Key files:** `server/app/matcha/routes/onboarding.py`, new `server/app/matcha/routes/onboarding_analytics.py`

---

## Track B — New Hire Experience

This track runs in parallel with Track A. Every phase in Track A should have a corresponding new hire surface.

### Phase B1: First-Day-Ready Portal (Weeks 2–6, parallel to A1)

**Problem:** `PortalOnboarding.tsx` exists but is a flat task list. There's no sense of progress, urgency, or guided journey. A Rippling new hire sees a clear "3 of 7 steps complete" with an estimated completion time and a prominent "what's next."

**What to build:**
- **Progress header:** Big, clear progress indicator at the top of the portal. "You're 60% onboarded. 3 tasks left before your start date."
- **Priority ordering:** Tasks sorted by: due date ASC, then by `assignee_type == 'employee'` first. Manager and IT tasks shown separately in a "waiting on others" section.
- **Dependency visualization:** If Task B depends on Task A, don't show B until A is done. Show a "locked" state with "complete X first."
- **Day-of countdown:** "Your start date is in 4 days" banner when within 7 days of `start_date`.
- **Mobile-first layout:** The portal pages need a responsive audit. New hires frequently onboard on mobile. `PortalOnboarding.tsx`, `PortalDocuments.tsx`, and `AcceptInvitation.tsx` need mobile-specific layouts.

**Key files:** `client/src/pages/portal/PortalOnboarding.tsx`, `client/src/pages/AcceptInvitation.tsx`

### Phase B2: Compliance Forms for the New Hire (Weeks 8–12, parallel to A3)

**Problem:** From the new hire's perspective, filling out an I-9 or W-4 should feel like a guided, step-by-step experience — not uploading a PDF.

**What to build:**
- **In-portal form wizard:** Step-by-step form UI for each compliance form type. Pre-fill what we know (name, address from employee record). Validation before submission.
- **"Complete your paperwork" section:** Dedicated section in `PortalDocuments.tsx` for compliance forms, separate from general documents. Shows completion status for each required form.
- **E-sign flow:** Native in-portal signature experience (draw or type). Generates a signed PDF with audit metadata. No third-party dependency for basic e-sign — reserve DocuSign integration for complex documents.
- **Completion confirmation:** After all compliance forms done, show a "Paperwork complete ✓" milestone in the progress header.

**Key files:** `client/src/pages/portal/PortalDocuments.tsx`, new `client/src/components/ComplianceFormWizard.tsx`

### Phase B3: Benefits Enrollment (Weeks 10–14)

**Problem:** Benefits enrollment is the most glaring gap relative to Rippling/Gusto. New hires expect to select their health plan, 401k contribution, and dependents as part of onboarding. Currently absent.

**What to build:**
- **Benefits catalog:** Admin-managed list of benefit plans (health, dental, vision, 401k) with plan type, cost, and enrollment window. Stored in `benefit_plans` table.
- **Enrollment workflow:** New hire portal page `PortalBenefits.tsx`: show available plans, let employee select, add dependents, confirm. Store in `benefit_enrollments` table.
- **Onboarding integration:** Benefits enrollment becomes an onboarding task of type `benefits`. Auto-assigned to new hires if the company has plans configured. Blocks "first-day-ready" status until complete.
- **Enrollment window enforcement:** Open enrollment only during `enrollment_open_until` window. After window, read-only view.
- **Admin view:** HR sees enrollment summary — who's enrolled, who's missing, what's pending carrier submission.
- **Carrier export (v1 simple):** CSV export of enrollments for manual carrier submission. EDI integration is a future phase.

**New files:** `server/app/matcha/routes/benefits.py`, `client/src/pages/portal/PortalBenefits.tsx`, `client/src/pages/Benefits.tsx` (admin)

### Phase B4: Manager Experience (Weeks 6–10, parallel to A2)

**Problem:** Managers are assigned new hires but have no dedicated view of their team's onboarding status, no prompts to complete their own tasks (equipment requests, intro meetings), and no escalation path.

**What to build:**
- **Manager dashboard widget:** In the existing manager/admin view, a "Your new hires" card that shows: name, start date, % complete, which tasks are blocked waiting on manager.
- **Manager task lane:** Tasks with `assignee_type == 'manager'` surface in a dedicated manager view. Managers get email reminders for their own pending tasks (not the employee's).
- **Intro meeting task:** Built-in task type `meeting` with calendar link generation. Manager completes by confirming meeting was held.
- **Buddy assignment:** Optional `buddy_employee_id` field on onboarding case. Buddy receives a single email with an intro checklist (coffee chat, team tour, Slack intro).

**Key files:** `client/src/pages/OnboardingCenter.tsx`, `server/app/matcha/routes/employees.py`

---

## Migration & Rollout Strategy

**This is the section the Codex plan omitted.**

Existing customers have live onboarding tasks assigned under the current flat-template model. The workflow engine (Phase A1) must be backwards-compatible:

1. **No breaking changes to existing assignments.** When template conditions are added, existing `employee_onboarding_tasks` rows without a version pin continue to work as-is.
2. **Version pin on assign-all.** The new `assign-all` stamps a `template_version` on each assigned task. Old rows without a version are treated as v0 (legacy, no conditions, no dependencies).
3. **Opt-in to new features.** Conditional templates and dependency chains are only activated on templates that explicitly define them. Blank `conditions` = always assign (current behavior preserved).
4. **Phased rollout:** Ship phases A1/B1 to a beta cohort of 3–5 companies first. Instrument heavily. Only proceed to A2 after validating that the workflow engine is stable under real usage.
5. **Data migration:** For offboarding (Phase A4), we need to ensure that any `termination_date` already set on employees gets backfilled into an offboarding case record.
6. **State migration:** Legacy employees without explicit onboarding state are backfilled deterministically (`user_id IS NULL` -> `invited` or `prehire`; `user_id IS NOT NULL` -> `active` unless offboarding signals exist).
7. **Feature flags + rollback:** Every major phase ships behind per-company flags with documented rollback steps and data-safe fallback behavior.

---

## Hard KPIs (Track from Day One)

| Metric | Target | Source |
|---|---|---|
| Time to first-day-ready (p50) | < 3 business days | `all_tasks_completed_at - invited_at` |
| % complete before start date | > 80% | `all_tasks_completed_at < start_date` |
| Provisioning automation success rate | > 95% | `onboarding_runs` table |
| Manual intervention rate | < 10% | Runs that required manual override |
| Compliance form completion rate | > 90% | `onboarding_compliance_forms` |
| New hire portal engagement | > 70% task complete within 48h of invite | `employee_onboarding_tasks` |
| Manager task completion rate | > 85% | Tasks with `assignee_type = 'manager'` |
| Reminder delivery success rate | > 98% | Notification job telemetry |
| SLA breach rate (critical tasks) | < 5% | State machine + task due events |
| API/worker incident MTTR | < 2h | Incident runbook logs |

---

## Reliability & Operations (Program-Wide)

These run across all phases, not just A5:

- **SLOs:** Set and monitor SLOs for onboarding API, workers, and provider integrations starting in week 2.
- **DLQ policy:** Any failed task after max retries goes to DLQ with structured error code and replay UI/API.
- **On-call ownership:** Assign primary + secondary owner for onboarding incidents by phase.
- **Chaos/failure drills:** Quarterly drill for provider outage and queue backlog recovery.
- **Audit of manual overrides:** Weekly report of overrides by actor/reason to detect misuse.

---

## Phasing Summary

| Weeks | Track A | Track B |
|---|---|---|
| 1–2 | Release gate + lifecycle/state/RBAC/data contracts | Portal baseline + instrumentation hooks |
| 2–6 | Conditional workflows + template versioning | First-day-ready portal redesign |
| 4–7 | Reminders + escalation system | Manager dashboard + buddy assignment |
| 8–12 | Compliance packet automation + e-sign | In-portal compliance form wizard |
| 10–14 | — | Benefits enrollment |
| 13–16 | Offboarding + cross-boarding | Offboarding employee checklist |
| 17–20 | Analytics + admin controls | — |

**Total scope: ~20 weeks.** Tracks A and B ship features to production continuously — not as a big-bang release at week 20.

---

## What We Are Explicitly Not Building (Yet)

- Third-party e-sign integration (DocuSign, HelloSign) — native e-sign covers 90% of cases
- EDI carrier integration for benefits — CSV export first
- Background check orchestration — out of scope for onboarding v1
- Device management / MDM integration — too deep in IT ops
- LMS / training content hosting — link to external LMS, don't host it
- Multi-language support — English-only for v1
