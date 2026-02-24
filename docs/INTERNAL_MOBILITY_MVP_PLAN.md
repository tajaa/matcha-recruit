# Internal Mobility MVP Plan (Product + Technical Spec)

## 1. Objective

Build a private, low-friction internal mobility layer in Matcha so employees can discover growth opportunities inside their company before they look externally.

This MVP should increase:

- internal opportunity visibility
- employee agency over career growth
- retention through internal movement (roles and stretch projects)

## 2. Problem Summary (Qualitative)

Employees often leave not because they must leave, but because external opportunity is easier to see than internal opportunity.

Current internal tooling usually fails because:

- it feels politically risky to signal interest
- employee skills are poorly mapped beyond job title
- opportunities are not proactively surfaced
- mobility is treated as "job change only" instead of including projects and stretch work
- managers are not naturally incentivized to support movement

The product gap is not "another internal job board." The gap is trusted discovery, private intent, and low-friction matching.

## 3. Product Principles

- Privacy first: exploration must be manager-safe by default.
- Opportunity before intent: show relevant options before employee is actively searching.
- Skills over title: model capability from profile + work signals, not only HRIS title.
- Mobility spectrum: include full role moves and short-term projects.
- Explainability: recommendations should have simple, understandable reasons.

## 4. How It Works (Qualitative Behavior)

### 4.1 Employee Experience

1. Employee opens a private Mobility section in the employee portal.
2. They set career interests (target roles, departments, skills to develop, work preferences).
3. System returns an opportunity feed:
   - internal open roles
   - stretch assignments/projects
4. Each opportunity includes:
   - fit score
   - "why this matches you"
   - required vs missing skills
5. Employee can:
   - save opportunities
   - dismiss opportunities
   - apply privately to HR/talent
6. Manager is not notified during browse/save by default.

### 4.2 HR / Talent Experience

1. HR publishes opportunities (roles and projects).
2. HR sees internal applications in a dedicated review queue.
3. HR can move application states (new -> review -> shortlist -> aligned -> approved).
4. HR controls when/if manager notification happens.

### 4.3 Manager Experience (MVP)

- Managers do not see private browsing behavior.
- Manager involvement starts only after HR advances a candidate to a stage that requires it.

### 4.4 Company-Level Retention Loop

1. Employee feels growth path is visible.
2. Employee explores internally without political risk.
3. Employee moves internally (or gets project exposure) instead of leaving.

## 5. MVP Scope

In scope:

- private employee career profile
- internal opportunity feed
- save/apply workflow
- deterministic matching score (v1)
- HR/admin review queue
- feature-flagged rollout

Out of scope (later):

- automatic manager incentive systems
- full talent marketplace graph ML ranking
- deep inferred skills from all work artifacts
- cross-company mobility networks

## 6. Existing Matcha Surfaces To Reuse

- Employee portal pages and auth:
  - `client/src/pages/portal/*`
  - `server/app/matcha/routes/employee_portal.py`
- Positions and matching primitives:
  - `server/app/matcha/routes/positions.py`
  - `server/app/matcha/routes/matching.py`
  - `server/app/matcha/services/position_matcher.py`
- Feature gating:
  - `server/app/core/feature_flags.py`
  - `server/app/core/routes/admin.py`

## 7. Technical Architecture (MVP)

### 7.1 Backend

- FastAPI routes under Matcha router.
- Postgres tables for mobility profiles, opportunities, matches, applications.
- Deterministic matching service (Python) for v1.
- Optional async job endpoint to recompute matches in batch.

### 7.2 Frontend

- New portal views:
  - Mobility Home (feed)
  - Mobility Profile (interests)
  - Saved / Applied views (can start as tabs)
- Admin view:
  - Internal applications queue
  - Opportunity CRUD

### 7.3 Feature Flag

Add `internal_mobility` feature flag and gate routes/pages with existing feature framework.

## 8. Data Model (Proposed)

### 8.1 `employee_career_profiles`

- `id` UUID PK
- `employee_id` UUID FK -> employees
- `org_id` UUID FK -> companies
- `target_roles` JSONB (array of strings)
- `target_departments` JSONB (array of strings)
- `skills` JSONB (array of strings)
- `interests` JSONB (array of strings)
- `mobility_opt_in` BOOLEAN default true
- `visibility` VARCHAR default `private`
- `created_at`, `updated_at`
- unique: (`employee_id`)
- indexes: (`org_id`), (`employee_id`)

### 8.2 `internal_opportunities`

- `id` UUID PK
- `org_id` UUID FK -> companies
- `type` VARCHAR check in (`role`, `project`)
- `position_id` UUID nullable FK -> positions
- `title` VARCHAR
- `department` VARCHAR nullable
- `description` TEXT
- `required_skills` JSONB
- `preferred_skills` JSONB
- `duration_weeks` INTEGER nullable
- `status` VARCHAR check in (`draft`, `active`, `closed`)
- `created_by` UUID FK -> users
- `created_at`, `updated_at`
- indexes: (`org_id`, `status`), (`type`)

### 8.3 `internal_opportunity_matches`

- `id` UUID PK
- `employee_id` UUID FK -> employees
- `opportunity_id` UUID FK -> internal_opportunities
- `match_score` FLOAT
- `reasons` JSONB
- `status` VARCHAR check in (`suggested`, `saved`, `dismissed`, `applied`)
- `created_at`, `updated_at`
- unique: (`employee_id`, `opportunity_id`)
- indexes: (`employee_id`, `status`), (`opportunity_id`)

### 8.4 `internal_opportunity_applications`

- `id` UUID PK
- `employee_id` UUID FK -> employees
- `opportunity_id` UUID FK -> internal_opportunities
- `status` VARCHAR check in (`new`, `in_review`, `shortlisted`, `aligned`, `closed`)
- `employee_notes` TEXT nullable
- `submitted_at` TIMESTAMP
- `reviewed_by` UUID nullable FK -> users
- `reviewed_at` TIMESTAMP nullable
- `manager_notified_at` TIMESTAMP nullable
- `created_at`, `updated_at`
- unique: (`employee_id`, `opportunity_id`)
- indexes: (`opportunity_id`, `status`), (`employee_id`)

## 9. API Spec (MVP)

### 9.1 Employee Portal APIs

- `GET /api/v1/portal/mobility/profile`
- `PUT /api/v1/portal/mobility/profile`
- `GET /api/v1/portal/mobility/feed?status=active`
- `POST /api/v1/portal/mobility/opportunities/{id}/save`
- `DELETE /api/v1/portal/mobility/opportunities/{id}/save`
- `POST /api/v1/portal/mobility/opportunities/{id}/apply`
- `GET /api/v1/portal/mobility/applications`

### 9.2 Admin/Client APIs

- `POST /api/internal-mobility/opportunities`
- `GET /api/internal-mobility/opportunities`
- `PATCH /api/internal-mobility/opportunities/{id}`
- `GET /api/internal-mobility/applications`
- `PATCH /api/internal-mobility/applications/{id}`
- `POST /api/internal-mobility/match/run`

## 10. Matching Spec v1 (Deterministic)

`score = required_skill_fit * 0.50 + preferred_skill_fit * 0.20 + interest_alignment * 0.20 + level_fit * 0.10`

Where:

- `required_skill_fit` = matched required skills / total required skills
- `preferred_skill_fit` = matched preferred skills / total preferred skills
- `interest_alignment` = overlap between profile interests/target roles and opportunity metadata
- `level_fit` = simple heuristic by tenure + optional experience hints

Output per match:

- `match_score` (0-100)
- `reasons` JSON:
  - `matched_skills`
  - `missing_skills`
  - `alignment_signals`

## 11. Privacy and Access Rules

- Employees:
  - can view/save/apply for their own opportunities only
  - cannot view other employees' mobility profiles or applications
- Managers:
  - do not see browsing or saved activity
  - only see involvement after HR-controlled transition
- HR/Admin/Client:
  - can manage opportunities and application workflow for their org
- All endpoints scoped by `org_id` from authenticated user context.

## 12. UX Specification (MVP)

### 12.1 Portal Mobility Feed Card

- title, department, type badge (`Role`/`Project`)
- match score pill
- "Why this match" short text
- actions: Save, Apply

### 12.2 Profile Form Fields

- target roles
- target departments
- skills
- interests
- mobility opt-in toggle
- privacy statement ("Private to HR/Talent by default")

### 12.3 Application Confirmation

- clear copy that manager is not automatically notified at this stage

## 13. Delivery Plan (3 Sprints)

### Sprint 1

- DB migration(s) for 4 mobility tables
- feature flag (`internal_mobility`)
- backend: profile + opportunity CRUD + feed read
- seeded demo data

### Sprint 2

- portal mobility UI (profile + feed + save/apply)
- basic admin application queue
- deterministic matching service and persistence

### Sprint 3

- batch recompute endpoint/job
- analytics tiles
- tighter validation and error states
- audit logging for sensitive transitions

## 14. Success Metrics

- profile completion rate
- opportunity feed adoption (weekly active viewers)
- save rate and apply rate per opportunity view
- median HR response SLA
- internal move conversion
- leakage incidents (target: zero manager-visibility violations)

## 15. Risks and Mitigations

- Risk: Low trust in confidentiality
  - Mitigation: explicit privacy copy + strict endpoint scoping + audit logs
- Risk: Poor recommendation quality
  - Mitigation: deterministic explainable v1 + iterative weight tuning
- Risk: Opportunity supply too low
  - Mitigation: support both full roles and short-term projects from day one

## 16. Open Questions

- Should managers ever see "interest intent" before HR approval, and under what policy?
- Should project opportunities be sourced only by HR, or also by team leads?
- What minimum data is required to auto-create mobility profiles for existing employees?
- Which status transition should trigger manager notification by default?

## 17. Implementation Kickoff (Execution Plan)

This section turns the plan into concrete engineering work items in this repository.

### 17.1 Sprint 1 Goals (Build First Vertical Slice)

1. Create DB schema for internal mobility entities.
2. Add feature flag and admin toggle support.
3. Add backend APIs for:
   - employee profile (read/write)
   - employee feed (read)
   - save/apply actions
   - admin opportunity CRUD
4. Add basic portal UI:
   - mobility feed page
   - mobility profile form
5. Add admin queue page for internal applications.

### 17.2 Delivery Strategy

1. Ship backend and DB first.
2. Wire frontend once stable endpoint contracts are in place.
3. Keep matching deterministic for v1.
4. Hide all new UI behind `internal_mobility` feature flag.

## 18. File-Level Implementation Map

### 18.1 Backend: Database and Feature Flags

1. Add migration file:
   - `server/alembic/versions/<new_revision>_add_internal_mobility_tables.py`
2. Update default company feature map:
   - `server/app/core/feature_flags.py`
3. Allow admin toggle:
   - `server/app/core/routes/admin.py` (add `internal_mobility` to `KNOWN_FEATURES`)

### 18.2 Backend: Matcha Domain

1. Add models:
   - `server/app/matcha/models/internal_mobility.py`
2. Add deterministic matcher service:
   - `server/app/matcha/services/internal_mobility_matcher.py`
3. Add routes:
   - `server/app/matcha/routes/internal_mobility.py`
4. Register router:
   - `server/app/matcha/routes/__init__.py`
5. Add portal endpoints (either in new route file or `employee_portal.py`):
   - `server/app/matcha/routes/employee_portal.py`

### 18.3 Frontend: Types and API Clients

1. Add types:
   - `client/src/types/index.ts`
2. Add portal API methods:
   - `client/src/api/portal.ts`
3. Add admin/client API methods:
   - `client/src/api/client.ts`

### 18.4 Frontend: Pages and Navigation

1. Add portal pages:
   - `client/src/pages/portal/PortalMobility.tsx`
   - `client/src/pages/portal/PortalMobilityProfile.tsx` (or combine into one tabbed page)
2. Add admin page:
   - `client/src/pages/InternalMobilityAdmin.tsx`
3. Add routes:
   - `client/src/App.tsx`
4. Add quick links:
   - `client/src/pages/portal/PortalHome.tsx`
5. Add optional left-nav item for admin/client:
   - `client/src/components/Layout.tsx`

## 19. Sprint 1 Detailed Checklist

- [ ] Create Alembic migration for 4 mobility tables.
- [ ] Add indexes + unique constraints exactly as defined in Section 8.
- [ ] Add `internal_mobility` to feature flags (`default false` recommended for controlled rollout).
- [ ] Add backend Pydantic models for requests/responses.
- [ ] Implement `GET/PUT /api/v1/portal/mobility/profile`.
- [ ] Implement `GET /api/v1/portal/mobility/feed`.
- [ ] Implement save/dismiss/apply endpoints for employees.
- [ ] Implement admin opportunity CRUD endpoints.
- [ ] Implement admin application list/update endpoints.
- [ ] Register routes in Matcha router.
- [ ] Add TS types and API clients.
- [ ] Build employee portal mobility page (feed + actions).
- [ ] Build employee profile form page.
- [ ] Build admin queue page.
- [ ] Gate all pages and routes behind `internal_mobility` feature.
- [ ] Add backend tests for access control and org scoping.
- [ ] Add frontend smoke tests for page rendering + action calls.

## 20. Endpoint Contracts (Initial Payload Shapes)

### 20.1 `PUT /api/v1/portal/mobility/profile`

Request:

```json
{
  "target_roles": ["Senior Data Analyst", "Analytics Engineer"],
  "target_departments": ["Data", "Operations"],
  "skills": ["SQL", "Python", "Looker"],
  "interests": ["cross-functional projects", "mentorship"],
  "mobility_opt_in": true
}
```

Response:

```json
{
  "employee_id": "uuid",
  "org_id": "uuid",
  "target_roles": ["Senior Data Analyst", "Analytics Engineer"],
  "target_departments": ["Data", "Operations"],
  "skills": ["SQL", "Python", "Looker"],
  "interests": ["cross-functional projects", "mentorship"],
  "mobility_opt_in": true,
  "visibility": "private",
  "updated_at": "2026-02-21T00:00:00Z"
}
```

### 20.2 `GET /api/v1/portal/mobility/feed`

Response:

```json
{
  "items": [
    {
      "opportunity_id": "uuid",
      "type": "role",
      "title": "Operations Analyst",
      "department": "Operations",
      "description": "Drive process efficiency initiatives",
      "match_score": 78.2,
      "status": "suggested",
      "reasons": {
        "matched_skills": ["SQL", "Operations"],
        "missing_skills": ["Tableau"],
        "alignment_signals": ["target_department_match"]
      }
    }
  ],
  "total": 1
}
```

### 20.3 `POST /api/v1/portal/mobility/opportunities/{id}/apply`

Request:

```json
{
  "employee_notes": "Interested in this role for cross-functional growth."
}
```

Response:

```json
{
  "application_id": "uuid",
  "status": "new",
  "submitted_at": "2026-02-21T00:00:00Z",
  "manager_notified": false
}
```

## 21. Access-Control Matrix (Implementation)

1. Employee:
   - Can CRUD own mobility profile.
   - Can only read own feed and own applications.
2. Admin/Client:
   - Can manage opportunities and all applications for own `org_id`.
3. Manager:
   - No dedicated mobility endpoints in MVP.
4. Security rule:
   - Every query must filter by `org_id` derived from auth context.

## 22. Acceptance Criteria (Sprint 1)

1. Employee with `internal_mobility` enabled can:
   - update profile
   - view feed
   - save/apply to an opportunity
2. Employee cannot see another employee's application/profile.
3. Admin/client can:
   - create/edit/close opportunities
   - review application statuses
4. Manager is not notified on browse/save/apply by default.
5. All new APIs return 403 when feature is disabled.

## 23. Seed and Demo Data Plan

1. Seed 5-10 opportunities across `role` and `project` types.
2. Seed at least 3 employee mobility profiles with different interests.
3. Run matcher once to pre-populate feed and confirm score distribution.

## 24. Definition of Done (MVP v1)

1. Migration applied and reversible.
2. Backend endpoints implemented and tested.
3. Frontend portal and admin surfaces shipped behind feature flag.
4. Org scoping and privacy behavior validated.
5. Document updated with final endpoint paths and any deviations from this spec.
