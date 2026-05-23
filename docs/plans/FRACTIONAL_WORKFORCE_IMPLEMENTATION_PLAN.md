# Fractional Workforce Management Implementation Plan

## Objective
Build a new "Fractional Ops" capability so businesses can effectively manage fractional employees/contractors beyond compliance, including planning, execution, financial control, and lifecycle management.

## 1) Product Definition (Week 0)
- Target users: SMB and mid-market companies using part-time/fractional talent.
- Core jobs to be done:
  - Onboard quickly
  - Track scope and capacity
  - Control spend
  - Prove ROI
  - Offboard cleanly
- Commercial decision to lock early:
  - Billing unit (`per active fractional worker` or `per managed assignment`)

## 2) Phase 1: Foundation + Visibility (Weeks 1-4)
- Create module: `Fractional Ops`
- Core entities:
  - Worker profile
  - Assignment
  - Capacity plan
  - Contract window
  - Manager/owner
- Onboarding workflow:
  - Create worker
  - Link manager
  - Set hours per week
  - Set start/end date
  - Define initial scope
- Alerts:
  - Expiring contracts
  - Over-allocation
  - Unassigned critical function
- Initial dashboard:
  - Active workers
  - Total weekly capacity
  - Contracts expiring in 30 days
  - Utilization bands
- Exit criteria:
  - Company admin can create/manage fractional workers and view portfolio status in one place.

## 3) Phase 2: Execution + Financial Controls (Weeks 5-8)
- Weekly operating cadence:
  - Status updates
  - Blockers
  - Next-week plan
  - Decision log
- Time and budget controls:
  - Time entry
  - Approvals
  - Rate cards
  - Budget burn vs plan
- Deliverable tracking:
  - Milestones
  - Due dates
  - Completion confidence
  - At-risk flags
- Invoicing support:
  - Export approved hours/cost by period
- Exit criteria:
  - Teams can run weekly operations and finance can reconcile cost to outcomes.

## 4) Phase 3: ROI + Lifecycle Automation (Weeks 9-12)
- Performance scorecards:
  - KPI attainment
  - Deadline hit rate
  - Cost per outcome
- Renewal intelligence:
  - Keep/expand/replace recommendation based on trends
- Offboarding automation:
  - Access revocation checklist
  - Documentation handoff
  - Knowledge transfer log
- Conversion insight:
  - "Fractional to full-time" readiness signal
- Exit criteria:
  - Leadership can quantify value and manage renewals/offboarding without spreadsheet operations.

## 5) Data Model (Start in Phase 1, Expand in Phase 2/3)
- `fractional_workers`
- `fractional_assignments`
- `fractional_capacity_weeks`
- `fractional_status_updates`
- `fractional_time_entries`
- `fractional_budgets`
- `fractional_milestones`
- `fractional_access_grants`
- `fractional_handoffs`
- `fractional_renewal_reviews`

## 6) API and UI Scope
- Backend:
  - CRUD and workflow endpoints under a dedicated `fractional` route group
- Frontend pages:
  - `Overview`
  - `Workers`
  - `Assignments`
  - `Weekly Ops`
  - `Budget`
  - `Renewals`
- UX:
  - Add wizard parity with existing modules:
    - First-run setup wizard
    - Weekly checklist wizard
    - Offboarding wizard

## 7) Permissions Model
- Master admin:
  - Tenant-wide visibility
  - Configuration
  - Feature flags
- Company admin/client:
  - Full company control
- Manager:
  - Manage assigned workers
  - Approve time
- Fractional contributor:
  - Submit updates/time
  - View only own assignments
- Finance approver:
  - Approve budget/time
  - Export reports

## 8) Integrations
- Compliance:
  - Worker classification guardrails (1099 vs employee risk signals)
- Identity and access:
  - Start/end-date-driven provisioning and revocation
- Notifications:
  - Weekly update reminders
  - Budget threshold alerts
  - Renewal window alerts

## 9) Success Metrics
- Time to onboard a fractional worker
- Percent of workers with on-time weekly updates
- Budget variance reduction
- Renewal rate of fractional engagements
- Adoption shift from spreadsheets to in-platform workflows

## 10) Immediate Next Build Step
Ship the Phase 1 skeleton this week:
- Database tables
- API endpoints
- `Fractional Ops` navigation
- Onboarding wizard
- Overview dashboard

This creates a usable backbone quickly while Phases 2 and 3 layer execution workflows and ROI automation.
