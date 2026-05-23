# Unified Onboarding Tab Plan

## Summary
Consolidate setup + onboarding workflows into one primary navigation destination named `Onboarding` so admins/clients can:
1. Configure workspace integrations (Google now, Slack/Toast next).
2. Onboard employees from the same surface (create/import, invite, provisioning status).
3. Track onboarding progress without hopping between `Company`, `Setup`, `Employees`, and `Google Workspace` pages.

---

## Goals
- Replace fragmented setup flows with one orchestrated onboarding center.
- Keep Google Workspace provisioning first-class while leaving room for Slack/Toast.
- Reduce time-to-first-employee-onboarded.
- Preserve role safety (`admin`, `client`) and tenant boundaries.
- Keep existing endpoints working during migration (no hard cutover on day 1).

## Non-Goals (Phase 1)
- Rewriting all employee management features into onboarding.
- Removing existing routes immediately.
- Building Slack/Toast full backend integrations in the same release.

---

## Current State (Problems)
- `Setup` and `Google Workspace` are separate from `Company` and `Employees`.
- Users must context-switch across pages to finish one workflow.
- Guided tours exist, but they are page-local and don’t represent one end-to-end path.
- Provisioning visibility and employee onboarding actions are disconnected.

---

## Proposed Information Architecture

### New primary nav item
- Rename/replace `Company` (and remove standalone `Setup`) with:
  - `Onboarding` -> `/app/matcha/onboarding`

### Onboarding page sections
- `Workspace` (default)
  - Integration cards: Google Workspace, Slack (coming soon), Toast (coming soon).
  - Connection status badges, configuration entry points, and test status.
- `Employees`
  - Quick add employee, CSV import shortcut, invite actions.
  - Onboarding progress table and provisioning indicators.
- `Templates`
  - Onboarding task template management entry (reuse existing templates module).
- `Runs / Activity`
  - Provisioning run history and retry actions.

### URL strategy
- Primary route: `/app/matcha/onboarding`
- Section routing by query string: `/app/matcha/onboarding?tab=workspace|employees|templates|runs`
- Backward-compatible redirects:
  - `/app/matcha/setup` -> `/app/matcha/onboarding?tab=workspace`
  - `/app/matcha/company` -> `/app/matcha/onboarding`
  - `/app/matcha/google-workspace` remains valid (deep-link), plus entry from Onboarding.

---

## UX Flow (Target)
1. User opens `Onboarding`.
2. User configures Google Workspace in `Workspace` section.
3. User toggles auto-provision defaults.
4. User switches to `Employees` section and adds/invites employees.
5. User sees onboarding/provisioning status inline.
6. User uses `Runs` section for failures/retries.

---

## Provider Chain Behavior (Required)
- Provisioning must be provider-specific per employee, not all-or-nothing.
- Example:
  - If company has only Google connected, onboarding chain runs only Google steps.
  - If Slack is connected later, admins can run Slack onboarding for selected employees without re-running Google.
- Add per-employee actions in `Employees` section:
  - `Add Google`
  - `Add Slack`
  - `Add Toast` (when available)
  - `Retry <provider>`
- Each provider action must be idempotent:
  - If employee already provisioned for provider, show `already linked` and do not duplicate account creation.
- Employee records should show provider status matrix:
  - `google_workspace`: connected/pending/failed/manual
  - `slack`: connected/pending/failed/manual
  - `toast`: connected/pending/failed/manual

## Admin Manual Bypass (Required)
- Admins/clients can bypass automation when provisioning is done externally.
- Add per-provider manual controls:
  - `Mark as provisioned manually`
  - Optional external identity fields (`external_user_id`, `external_email`, `notes`).
- Manual entries should:
  - Skip auto-provision attempts for that provider unless admin explicitly re-runs.
  - Be auditable (`updated_by`, timestamp, reason/notes).
- UI must clearly differentiate:
  - `Auto provisioned`
  - `Manual override`
  - `Not provisioned`

---

## Frontend Implementation Plan

## Phase 1: Scaffold `Onboarding` Center
- Create `client/src/pages/OnboardingCenter.tsx`.
- Add top-level page layout with tabbed sections.
- Update navigation in `client/src/components/Layout.tsx`:
  - Add `Onboarding`.
  - Remove old standalone `Setup` nav.
- Update routing in `client/src/App.tsx`:
  - Add `/app/matcha/onboarding`.
  - Add redirects from old setup/company entry points.

Deliverable:
- Unified navigation point live with placeholder/embedded sections.

## Phase 2: Workspace section integration
- Reuse existing Google Workspace setup UI as embedded module or contained panel.
- Show provider cards:
  - Google Workspace (active)
  - Slack (placeholder)
  - Toast (placeholder)
- Add provider status summary row (connected/disconnected/error).
- Keep deep link support to full Google page for advanced settings.

Deliverable:
- Users can do all Google setup from Onboarding context.

## Phase 3: Employee onboarding section
- Integrate quick actions:
  - Add employee
  - Bulk import
  - Send invite(s)
- Include table with:
  - Invite state
  - Onboarding task progress
  - Provider provisioning statuses (Google/Slack/Toast)
- Provide direct action buttons:
  - Add provider to employee (Google/Slack/Toast)
  - Retry provider run
  - Mark provider as manual
  - Open employee detail

Deliverable:
- Employee onboarding executed directly from Onboarding page.

## Phase 4: Templates + Activity sections
- `Templates` tab:
  - Link/embedded view to onboarding templates management.
- `Runs` tab:
  - Show provisioning runs with status timeline.
  - Retry action with clear error surface.

Deliverable:
- Full operational loop in one place.

## Phase 5: Guided walkthrough
- Add new guide key: `onboarding-center`.
- Add `Show Me` trigger in Onboarding header.
- Steps should cover:
  - Workspace provider status
  - Configure Google
  - Auto-provision toggles
  - Add employee
  - Invite action
  - Provisioning run status/retry

Deliverable:
- One end-to-end onboarding wizard matching the unified flow.

---

## Backend/API Plan

## Reuse existing APIs first
- Keep current provisioning APIs:
  - `/provisioning/google-workspace/status`
  - `/provisioning/google-workspace/connect`
  - `/provisioning/employees/{employee_id}/google-workspace`
  - `/provisioning/runs/{run_id}/retry`
- Keep current employee/onboarding template endpoints.
- Extend provisioning model to support provider-scoped employee actions:
  - `POST /provisioning/employees/{employee_id}/{provider}`
  - `POST /provisioning/runs/{run_id}/retry`
  - `POST /provisioning/employees/{employee_id}/{provider}/manual` (mark manual)
  - `DELETE /provisioning/employees/{employee_id}/{provider}/manual` (clear manual override)

## Optional aggregator API (recommended)
- Add `/onboarding/overview` for page hydration:
  - Company summary
  - Integration statuses by provider
  - Employee onboarding metrics
  - Recent provisioning runs
- Benefits:
  - Fewer round trips
  - Easier consistent loading/error handling

---

## Data Model/Config Strategy
- Introduce provider registry config in frontend:
  - `provider_id`, `display_name`, `status`, `cta`, `availability`
- Keep `integration_connections` as source of truth.
- Keep/extend `external_identities` as provider-per-employee truth table.
- Add/confirm `provisioning_mode` per provider identity:
  - `auto` | `manual`
- Preserve tenant-scoped secrets and encrypted storage behavior.

---

## Permissions and Security
- Route and API remain restricted to `admin` and `client`.
- Maintain tenant isolation for all integration and onboarding data.
- Continue to avoid exposing secret material in UI.
- Ensure retries/provision actions are audited (`triggered_by`, timestamps, errors).

---

## Migration and Rollout

## Step 1: Soft launch
- Add new `Onboarding` page without removing old pages.
- Add redirects from old `Setup` entry points.
- Keep old deep links functional.

## Step 2: Adoption window
- In-app nudges/banners on old pages -> “Moved to Onboarding”.
- Monitor usage and failure metrics.

## Step 3: Consolidation
- Remove deprecated nav items after adoption target is met.
- Keep route redirects for backward compatibility.

---

## Testing Plan

## Frontend tests
- Route tests:
  - `/app/matcha/onboarding` loads correctly.
  - Legacy routes redirect correctly.
- Wizard tests:
  - `Show Me` appears and covers all core targets.
- Role tests:
  - `admin/client` allowed, others denied.

## Integration/manual tests
- Configure Google successfully.
- Fail connection test and recover.
- Add employee -> invite -> provisioning run visibility.
- Retry failed run from Activity tab.
- Multi-tenant validation (company isolation).

---

## Success Metrics
- Reduce clicks/pages from setup to first invited employee.
- Increase percent of companies completing workspace configuration.
- Decrease provisioning setup support requests.
- Increase successful first-run provisioning rate.

---

## Risks and Mitigations
- Risk: page becomes too dense.
  - Mitigation: tabbed sections + progressive disclosure.
- Risk: duplicated behavior between legacy pages and new center.
  - Mitigation: shared components/hooks, redirects, phased removal.
- Risk: provisioning failures become more visible.
  - Mitigation: clear status/error copy + retry affordances + run history.

---

## Execution Breakdown (Suggested Tickets)
1. FE: Add Onboarding route, nav item, legacy redirects.
2. FE: Build OnboardingCenter shell + tabs.
3. FE: Embed Workspace cards + Google status/actions.
4. FE: Employee onboarding quick actions + status table.
5. FE: Templates and Activity tabs.
6. FE: Add unified `onboarding-center` wizard.
7. BE: (Optional) `/onboarding/overview` aggregator endpoint.
8. QA: E2E + role + tenant isolation passes.
9. Release: soft launch + telemetry.

---

## Recommendation
Implement in phased rollout with backward-compatible redirects first.  
This gives immediate UX simplification with low migration risk and keeps existing operational flows intact while we unify the experience.

---

## Concrete Ticket Checklist (FE + BE + QA)

## FE Tickets

- [x] `ONB-FE-01` Create unified onboarding route and nav entry
Owner: Frontend  
Depends on: none  
Scope: Add `/app/matcha/onboarding`, expose `Onboarding` in primary nav, keep old routes as redirects.  
Acceptance Criteria:
1. `/app/matcha/onboarding` is accessible for `admin` and `client`.
2. `/app/matcha/setup` redirects to `/app/matcha/onboarding?tab=workspace`.
3. `/app/matcha/company` redirects to `/app/matcha/onboarding`.
4. Navigation no longer exposes standalone `Setup`.

- [x] `ONB-FE-02` Build `OnboardingCenter` shell with tab state
Owner: Frontend  
Depends on: `ONB-FE-01`  
Scope: Implement top-level page with tabs `workspace`, `employees`, `templates`, `runs` and query-param persistence.  
Acceptance Criteria:
1. Tab state persists in URL query string.
2. Page reload returns user to same tab.
3. Empty/loading/error states render for each tab section.

- [x] `ONB-FE-03` Workspace tab with provider cards
Owner: Frontend  
Depends on: `ONB-FE-02`  
Scope: Show cards for Google (active), Slack (placeholder), Toast (placeholder), with status badges and CTA actions.  
Acceptance Criteria:
1. Google card reflects live status from API.
2. Slack/Toast cards show explicit “coming soon” or “not connected”.
3. Google card CTA opens configure flow.

- [ ] `ONB-FE-04` Employee table with provider status matrix
Owner: Frontend  
Depends on: `ONB-FE-02`, `ONB-BE-02`  
Scope: In Employees tab, show per-employee provider states (`google_workspace`, `slack`, `toast`) and onboarding progress.  
Acceptance Criteria:
1. Status values render: `connected`, `pending`, `failed`, `manual`, `not_provisioned`.
2. Sorting/filtering by provider status works.
3. Row action menu includes provider-specific actions.

- [ ] `ONB-FE-05` Provider actions per employee (add/retry/manual)
Owner: Frontend  
Depends on: `ONB-FE-04`, `ONB-BE-03`, `ONB-BE-04`  
Scope: Add row-level actions: `Add Google`, `Add Slack`, `Retry Provider`, `Mark Manual`, `Clear Manual`.  
Acceptance Criteria:
1. Actions call provider-specific endpoints.
2. Optimistic UI or refresh flow updates row states correctly.
3. Manual override visibly differs from automated state.

- [ ] `ONB-FE-06` Bulk actions for selected employees
Owner: Frontend  
Depends on: `ONB-FE-05`, `ONB-BE-05`  
Scope: Allow bulk provider add/retry/manual for selected employees.  
Acceptance Criteria:
1. Multi-select action bar appears when rows are selected.
2. Bulk operation returns per-employee result summary.
3. Failed entries are clearly reported without blocking successful ones.

- [ ] `ONB-FE-07` Runs/Activity tab
Owner: Frontend  
Depends on: `ONB-FE-02`, `ONB-BE-06`  
Scope: Show provisioning runs timeline with provider filter and retry button.  
Acceptance Criteria:
1. Runs list includes status, provider, triggered_by, timestamps.
2. Retry action available for retry-eligible states.
3. Error payload is readable and not raw/unhelpful JSON.

- [ ] `ONB-FE-08` Unified onboarding walkthrough
Owner: Frontend  
Depends on: `ONB-FE-03`, `ONB-FE-04`, `ONB-FE-07`  
Scope: Add `onboarding-center` guide key and `Show Me` wizard for full flow.  
Acceptance Criteria:
1. Wizard steps include workspace config, employee actions, runs/retry.
2. No critical step target is missing in default admin/client viewport.
3. Guide can be replayed and dismissed safely.

- [ ] `ONB-FE-09` Legacy page banners and migration nudges
Owner: Frontend  
Depends on: `ONB-FE-01`  
Scope: Add non-blocking banners on old pages pointing to Onboarding Center.  
Acceptance Criteria:
1. Banner appears on legacy routes.
2. CTA deep-links to relevant `tab`.
3. Banner can be dismissed per user.

## BE Tickets

- [ ] `ONB-BE-01` Provider registry and capability metadata
Owner: Backend  
Depends on: none  
Scope: Define supported providers and allowed actions by environment/company.  
Acceptance Criteria:
1. Registry returns provider id, display name, enabled state, capabilities.
2. Unsupported providers are safely rejected server-side.

- [ ] `ONB-BE-02` Employee provider status endpoint
Owner: Backend  
Depends on: `ONB-BE-01`  
Scope: Return per-employee provider status matrix and onboarding summary fields.  
Acceptance Criteria:
1. Endpoint returns statuses for each provider per employee.
2. Response scoped to requesting user’s tenant/company.
3. Pagination and filtering supported for large employee sets.

- [ ] `ONB-BE-03` Provider-scoped trigger endpoint
Owner: Backend  
Depends on: `ONB-BE-01`  
Scope: Implement `POST /provisioning/employees/{employee_id}/{provider}` with idempotency.  
Acceptance Criteria:
1. Existing provisioned identity does not create duplicate account.
2. Repeated requests return deterministic state.
3. Response includes run id and initial status.

- [ ] `ONB-BE-04` Manual override endpoints
Owner: Backend  
Depends on: `ONB-BE-02`  
Scope: Implement mark/clear manual provisioning endpoints for provider per employee.  
Acceptance Criteria:
1. Manual state stores actor, timestamp, and reason/notes.
2. Auto-provision skips manual-marked provider by default.
3. Clearing manual state re-enables normal automation.

- [ ] `ONB-BE-05` Bulk provider operations
Owner: Backend  
Depends on: `ONB-BE-03`, `ONB-BE-04`  
Scope: Bulk add/retry/manual operations for multiple employees with partial success handling.  
Acceptance Criteria:
1. Supports mixed result sets without transactional all-or-nothing failure.
2. Response includes per-employee status and error reason.
3. Input validation rejects cross-tenant employee IDs.

- [ ] `ONB-BE-06` Runs feed endpoint enhancements
Owner: Backend  
Depends on: existing runs model  
Scope: Standardize run list payload for activity UI with provider and retry eligibility metadata.  
Acceptance Criteria:
1. Runs include retry eligibility boolean.
2. Filters for provider/status/date range are supported.
3. Payload includes friendly error summaries.

- [ ] `ONB-BE-07` Optional onboarding overview aggregator
Owner: Backend  
Depends on: `ONB-BE-02`, `ONB-BE-06`  
Scope: Add `/onboarding/overview` for consolidated FE hydration.  
Acceptance Criteria:
1. Returns workspace provider statuses, employee metrics, and recent runs.
2. Compatible with partial data availability.
3. p95 latency target documented and met in staging.

## QA Tickets

- [ ] `ONB-QA-01` Role and access matrix validation
Owner: QA  
Depends on: FE/BE route and endpoint tickets  
Scope: Verify access boundaries for `admin`, `client`, `employee`, `candidate`, unauthenticated users.  
Acceptance Criteria:
1. `admin/client` allowed on onboarding routes/APIs.
2. Other roles blocked with expected behavior.
3. No privilege escalation via direct endpoint calls.

- [ ] `ONB-QA-02` Tenant isolation test suite
Owner: QA  
Depends on: `ONB-BE-02` through `ONB-BE-05`  
Scope: Cross-company data and action isolation for status views and provisioning actions.  
Acceptance Criteria:
1. Cannot read or mutate another company’s employees/providers.
2. Bulk endpoints reject mixed-tenant payloads.

- [ ] `ONB-QA-03` Provider chain scenarios
Owner: QA  
Depends on: `ONB-FE-05`, `ONB-BE-03`, `ONB-BE-04`  
Scope: Validate chain logic and late provider additions.  
Acceptance Criteria:
1. Google-only company provisions only Google.
2. Slack added later can be provisioned for existing employees.
3. Already-provisioned provider is idempotent.
4. Manual override suppresses automatic run until cleared.

- [ ] `ONB-QA-04` End-to-end onboarding flow
Owner: QA  
Depends on: all FE/BE core tickets  
Scope: Full path from workspace connect -> employee add/import -> invite -> provider run -> retry/manual override.  
Acceptance Criteria:
1. Full path completes with expected statuses.
2. Runs tab reflects each transition accurately.
3. Audit metadata visible where required.

- [ ] `ONB-QA-05` Wizard and usability regression
Owner: QA  
Depends on: `ONB-FE-08`  
Scope: Validate `Show Me` walkthrough and ensure no skipped critical fields/targets.  
Acceptance Criteria:
1. All target anchors found for default viewport.
2. Wizard does not skip provider credential blocks.
3. Keyboard and close behaviors work as expected.

## Release Gates

- [ ] `ONB-REL-01` Staging signoff
Criteria:
1. FE and BE ticket acceptance complete.
2. QA critical path and tenant isolation passed.
3. No P1/P2 open defects.

- [ ] `ONB-REL-02` Production rollout
Criteria:
1. Redirects active for legacy routes.
2. Monitoring dashboards and alerts enabled for provisioning failure rate.
3. Rollback plan documented and tested.
