# Onboarding Implementation Plan (3 Phases)

This is the execution breakdown for delivering competitive onboarding in 3 implementation phases, based on `ONBOARDING_ROADMAP.md`.

## Phase Summary

| Phase | Weeks | Target Outcome | Gate |
|---|---|---|---|
| Phase 1 | 1–6 | Stable onboarding foundation + workflow core | Workflow engine beta-ready |
| Phase 2 | 7–13 | Automated execution + compliance + manager/new-hire depth | Compliance and reminders operational |
| Phase 3 | 14–20 | Full lifecycle parity + analytics + GA hardening | GA launch readiness |

---

## Phase 1 (Weeks 1–6): Foundation + Workflow Core

### Objectives
- Establish canonical lifecycle ownership and onboarding state machine.
- Replace flat checklist behavior with workflow-aware assignment.
- Ship a first-day-ready new-hire portal baseline.

### In Scope
- Operating model contracts:
  - canonical `hire_activated` case-start event
  - lifecycle state machine
  - RBAC + approval permissions
  - provider-agnostic provisioning API contract
  - onboarding event schema and instrumentation
- Workflow engine v1:
  - template conditions
  - task dependencies
  - assignee lanes (`employee`, `manager`, `HR`, `IT`)
  - template versioning/publish model
  - idempotency keys for invite/assign/case-start actions
- New-hire portal v1:
  - progress header
  - priority ordering
  - dependency lock states
  - start-date countdown
  - responsive/mobile baseline
- Controlled rollout:
  - feature flags
  - beta cohort (3–5 companies)

### Exit Criteria
- 100% of new onboarding cases are created with canonical states and transition events.
- `assign-all` is idempotent and version-pinned.
- Portal onboarding baseline works on mobile and desktop without regression.
- Core events for KPI measurement are emitted and queryable.
- Beta cohort can run onboarding end-to-end without manual DB intervention.

---

## Phase 2 (Weeks 7–13): Automation + Compliance + Manager/New-Hire Depth

### Objectives
- Prevent onboarding drop-off with reminders/escalations.
- Make compliance packet completion first-class and auditable.
- Add manager execution surfaces and benefits enrollment.

### In Scope
- Reminders and escalation system:
  - periodic reminder jobs
  - escalation chain (assignee -> manager -> HR)
  - notification preferences
  - business-calendar/timezone/quiet-hours logic
- Compliance packet automation:
  - structured forms (I-9, W-4, state withholding, direct deposit)
  - completion status + evidence storage
  - correction/amendment handling
  - e-sign metadata and audit artifacts
  - compliance packet export
  - optional E-Verify feature flag gate
- Manager experience:
  - manager onboarding widget
  - manager task lane
  - meeting task + buddy assignment flow
- Benefits enrollment v1:
  - plan catalog and enrollment workflow
  - enrollment window controls
  - admin summary + carrier CSV export
- Integration depth:
  - complete Slack provisioning implementation to parity with Google control model

### Exit Criteria
- Reminder delivery success is consistently above target in production.
- Required compliance forms are trackable and auditable per employee.
- Managers can see and complete manager-lane tasks with reminders.
- Benefits enrollment works end-to-end for configured companies.
- Slack provisioning supports connect/run/status/retry/manual override flows.

---

## Phase 3 (Weeks 14–20): Lifecycle Completion + Analytics + GA Hardening

### Objectives
- Complete lifecycle parity (onboarding, cross-boarding, offboarding, rehire).
- Deliver operational analytics and governance controls.
- Prove production reliability and launch broadly.

### In Scope
- Lifecycle completion:
  - offboarding cases + checklists
  - deprovisioning orchestration
  - cross-boarding role-change flows
  - rehire and transfer/legal-entity workflows
- Analytics and controls:
  - onboarding funnel and bottleneck dashboards
  - KPI cards (time-to-ready, completion-before-start, automation success, manual intervention)
  - template governance controls (publish/archive/diff/approval gates)
- Reliability and operations hardening:
  - SLOs and alerting
  - DLQ and replay tooling
  - runbooks and ownership model
  - failure drills and rollback playbooks
- Rollout:
  - phased expansion from beta to general availability
  - migration/backfill validation for legacy records

### Exit Criteria
- Offboarding and cross-boarding are production workflows, not manual procedures.
- Analytics endpoints and dashboards support operational decision-making.
- SLOs are met for a sustained period (minimum 2 release cycles).
- Rollout completed with no Sev1 onboarding incidents during expansion.
- Roadmap release gate is fully green.

---

## Program Controls (All Phases)

- Weekly steering review:
  - phase status
  - blocker log
  - metric trend check
  - go/no-go decisions
- Change control:
  - all scope changes tied to release gate impact
  - explicit tradeoff notes in decision log
- Deployment safety:
  - feature-flagged releases by company cohort
  - rollback path documented before each production cut
- Quality bar:
  - API tests
  - workflow integration tests
  - migration/backfill verification
  - key-path manual QA for admin, manager, and new-hire personas

---

## Immediate Next Steps (Next 7 Days)

1. Lock owners and acceptance criteria for all Phase 1 items.
2. Finalize lifecycle state machine and RBAC matrix as implementation contracts.
3. Define onboarding event schema and analytics ingestion tables.
4. Set up feature flags and select beta cohort companies.
5. Start A1/B1 implementation with idempotency + versioned workflow assignment first.
