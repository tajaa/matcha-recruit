# Master-Admin Onboarding Wizard — Industry / Specialty / Location Scope (v2)

## Fit with the existing jurisdictional system

Verified directly by reading `server/app/orm/jurisdiction.py` + `requirement.py` + `handbook_service.py:_fetch_state_requirements`. The system is more mature than the v1 plan assumed:

| Existing model | Implication for wizard |
|---|---|
| `compliance_categories` w/ `slug`, `domain`, `group`, `industry_tag`, `research_mode` | **Use `slug` as Gemini's enum.** Don't invent category strings — `response_schema` enums = current `compliance_categories.slug` values, fetched at request time. |
| `PrecedenceRule` (already models federal-vs-state-vs-local precedence) | Wizard doesn't reinvent precedence. Resolution honors existing rules — `_fetch_state_requirements` already cascades by `jurisdiction_level` (state → county → city) in deterministic order. |
| `JurisdictionRequirement` w/ `canonical_key`, `category_id`, `applicable_industries`, `applicable_entity_types`, `superseded_by_id`, `status` enum, `RegulationKeyDefinition` FK | `company_compliance_scope.requirement_id` aligns. We filter `status='active'` automatically. Superseded chain handled. |
| `Jurisdiction` w/ self-ref `parent_id` cascade (US → state → county → city) | Resolve AI jurisdiction strings by `(state, county, city)` tuple lookup against existing rows — NEVER create new rows from the wizard. |
| `_fetch_state_requirements` queries via legacy text `jr.category` column (alongside newer `category_id`) | Wizard resolver should match on BOTH `category_id` AND legacy `category` text for robustness during the transition. |
| `applicable_industries` JSONB | **Unknown population coverage** — verify before relying. If sparse, scope resolver falls back to category+jurisdiction match alone. |

Net: the bank + jurisdiction taxonomy + precedence is already enterprise-grade. Wizard adds (a) per-company scope manifest, (b) AI scope expansion that PICKS from this bank, (c) gap-fill dispatch to existing research workers. **No reinvention.**

## Context

When a new business signs onto the platform, today an admin approves them and they land in the product with no pre-populated compliance scope. The Compliance, Handbook, and IR features all rely on `jurisdiction_requirements` lookups at query time, but nothing has resolved "what does THIS business need to track?" up front.

We want a **master-admin onboarding wizard** at `/admin/onboarding` that intelligently scopes a new company in one sitting:

1. Business name + industry + sub-specialty (biotech, cardiology, full-service restaurant, etc.)
2. Size: FT / PT / contractor counts — CSV upload or HRIS connect (or skip)
3. Physical locations (1..N) with optional facility attributes (e.g. "cardiology suite", "kitchen w/ grease trap")
4. **AI-driven scope expansion** via Gemini 3.1 Flash Lite: industry + specialty + locations → list of compliance categories, certifications, licenses, and jurisdiction levels the business must track
5. **Bank reconciliation**: compare the AI-expanded scope against the existing shared `jurisdiction_requirements` bank. Mark each item `existing` (already in bank) or `missing` (needs research)
6. Optional: trigger background research for `missing` items via the existing compliance/medical research Celery tasks — same workers we already use
7. Finalize → persist the company's resolved **scope manifest** (a list of references into the shared bank, never duplicates)

**Critical constraint**: ONE shared bank of policies/requirements. Two cardiology offices in the same state map to the SAME bank rows. The wizard's output is a per-company *manifest* (pointers into the bank), not new policy text. This is the architectural promise the user explicitly called out.

## Existing scaffolding we reuse (no rewrite)

| Need | What exists | Path |
|---|---|---|
| Federal/state/county/city taxonomy | `jurisdictions` w/ cascade via `parent_id` | `server/app/orm/jurisdiction.py:35` |
| Shared policy bank | `jurisdiction_requirements` w/ `applicable_industries` JSONB | `server/app/orm/requirement.py:33` |
| Industry → NAICS lookup | `INDUSTRY_TO_SECTOR` dict | `server/app/matcha/services/wc_benchmarks.py:41` |
| Per-state requirement fetcher | `_fetch_state_requirements` | `server/app/core/services/handbook_service.py:1398` |
| Generic compliance research worker | `run_compliance_check_task` | `server/app/workers/tasks/compliance_checks.py:125` |
| Medical-specific research worker | `run_medical_compliance_research` (17 healthcare categories) | `server/app/workers/tasks/medical_compliance_research.py:52` |
| Locations + facility attrs | `business_locations` + `facility_attributes` JSONB | `server/app/core/models/compliance.py:109` |
| Company demographics blob | `company_handbook_profiles.{headcount, remote_workers, minors, tipped, …}` | already populated by signup |
| Gemini client w/ retry + JSON parse + grounded search + model fallback | `GeminiComplianceService._call_with_retry` | `server/app/core/services/gemini_compliance.py:585` |
| Wizard UX pattern (enum-driven step + ORDER + advance) | `IrOnboardingWizard` | `client/src/features/ir-onboarding/IrOnboardingWizard.tsx` |
| AdminSidebar entry pattern + `/admin/*` route block | `AdminSidebar.tsx`, `App.tsx` admin section | `client/src/components/AdminSidebar.tsx`, `client/src/App.tsx:175` |
| HRIS client (ADP-style, mock mode available) | `hris_service.py` | `server/app/matcha/services/hris_service.py` |
| Reusable file/CSV upload primitive | `FileUpload` | `client/src/components/ui/FileUpload.tsx` |

## Schema additions

### `onboarding_sessions`
Tracks an in-progress wizard run. Master-admin owns it. Persists step state so a wizard can be resumed. **Company is created at Step 3 (Locations), not at Finalize** — this resolves the "dispatch-research has no company_id" race that v1 had, and lets gap-fill workers run against a real company row even before the wizard is finalized.
```sql
CREATE TABLE onboarding_sessions (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  schema_version  INT  NOT NULL DEFAULT 1,            -- bump on shape change
  created_by      UUID NOT NULL REFERENCES users(id),
  company_id      UUID REFERENCES companies(id),     -- NULL until Step 3
  owner_email     TEXT,                              -- set in Step 1, invite issued at finalize
  owner_user_id   UUID REFERENCES users(id),         -- populated after invite accepted or admin links existing
  invite_token    TEXT,                              -- unique signup token issued at finalize
  idempotency_key TEXT UNIQUE,                       -- client-provided uuid; gates company-create + finalize
  step            TEXT NOT NULL DEFAULT 'basics',    -- basics|size|locations|scope|gaps|review|done
  basics          JSONB NOT NULL DEFAULT '{}'::jsonb,
  size            JSONB NOT NULL DEFAULT '{}'::jsonb,
  locations       JSONB NOT NULL DEFAULT '[]'::jsonb,
  ai_scope        JSONB,
  resolved_scope  JSONB,
  status          TEXT NOT NULL DEFAULT 'in_progress', -- in_progress|finalized|abandoned
  created_at      TIMESTAMP DEFAULT NOW(),
  updated_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_onboarding_sessions_created_by ON onboarding_sessions(created_by);
CREATE INDEX idx_onboarding_sessions_company_id ON onboarding_sessions(company_id);
```

### `company_compliance_scope`
Per-company manifest — the durable output of onboarding. References shared bank rows, never duplicates them. `location_id` is **NOT NULL** with a synthetic "company-wide" sentinel location for federal-only requirements (resolves the v1 multi-state gotcha where a CA wage law would attach to a TX site).
```sql
CREATE TABLE company_compliance_scope (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id               UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  requirement_id           UUID NOT NULL REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
  location_id              UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
  scope_level              TEXT NOT NULL,                              -- federal|state|county|city|company_wide
  source                   TEXT NOT NULL DEFAULT 'onboarding_wizard', -- onboarding_wizard|manual|drift
  status                   TEXT NOT NULL DEFAULT 'active',            -- active|removed
  admin_reviewed_by        UUID REFERENCES users(id),                 -- master-admin who confirmed (for gap-research dispatch)
  added_at                 TIMESTAMP DEFAULT NOW(),
  UNIQUE (company_id, requirement_id, location_id)
);
CREATE INDEX idx_company_scope_company ON company_compliance_scope(company_id);
CREATE INDEX idx_company_scope_requirement ON company_compliance_scope(requirement_id);
```

Wizard creates one **company-wide** sentinel row in `business_locations` per company (`is_company_wide=true` flag or address fields all NULL) when federal scope applies — keeps the FK invariant clean.

### `certifications_catalog` + `company_certifications`
**Promoted from Phase 2 — included in Phase 1.** The v1 plan deferred these, but Step 4 (AI scope) outputs certifications, and Step 6 (Review) shows them. With no table they'd be lost. Same shared-bank pattern as requirements.
```sql
CREATE TABLE certifications_catalog (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug               TEXT UNIQUE NOT NULL,                  -- 'clia_lab', 'cardiology_abim'
  name               TEXT NOT NULL,                         -- 'CLIA Lab Certificate'
  issuing_authority  TEXT,                                  -- 'CMS', 'ABIM'
  scope_level        TEXT NOT NULL,                         -- federal|state|specialty
  industry_tag       TEXT,                                  -- maps to compliance_categories.industry_tag
  renewal_months     INT,                                   -- typical renewal cycle
  description        TEXT,
  source_url         TEXT,
  created_at         TIMESTAMP DEFAULT NOW()
);
CREATE TABLE company_certifications (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  certification_id UUID NOT NULL REFERENCES certifications_catalog(id),
  location_id     UUID REFERENCES business_locations(id) ON DELETE CASCADE,
  source          TEXT NOT NULL DEFAULT 'onboarding_wizard',
  status          TEXT NOT NULL DEFAULT 'required',         -- required|on_file|expired|removed
  added_at        TIMESTAMP DEFAULT NOW(),
  UNIQUE (company_id, certification_id, location_id)
);
```
Mirror approach to licenses (`licenses_catalog` + `company_licenses`) — same shape, separate tables to keep the cert/license semantic distinction. Together: 4 catalog/manifest tables (compliance_scope, scope-catalog already exists, certifications, licenses).

## Backend (Phase 1)

### Service: `server/app/core/services/onboarding_scope_ai.py` (new)

Wraps Gemini 3.1 Flash Lite for two structured-output calls:

**Specialty controlled vocab** lives in this module too: `INDUSTRY_SPECIALTIES = { 'healthcare': ['cardiology', 'oncology', 'primary_care', ...], 'hospitality': ['full_service_restaurant', 'fast_casual', 'hotel', ...], 'biotech': [...], ... }`. Step 1 UI uses this for a typeahead so admin can't free-type "Cardiology - interventional" three different ways. Resolved to a stable slug stored in `basics.specialty`.

1. **`expand_scope(basics, locations) -> dict`** — Given industry + specialty + per-location facility attributes, returns:
   ```json
   {
     "naics_sector": "62",
     "compliance_categories": [
       {"category_slug": "osha_general", "scope": "federal", "reason": "..."},
       {"category_slug": "infection_control", "scope": "state", "reason": "..."}
     ],
     "required_certifications": [
       {"slug": "clia_lab", "name": "CLIA Lab Certificate", "issuing_authority": "CMS", "renewal_period_months": 24}
     ],
     "required_licenses": [
       {"slug": "pharmacy_permit", "name": "Pharmacy Permit", "scope": "state", "renewal_period_months": 12}
     ],
     "applicable_jurisdictions": [
       {"state": "US", "county": null, "city": null},
       {"state": "CA", "county": null, "city": null},
       {"state": "TX", "county": "Travis", "city": "Austin"}
     ]
   }
   ```
   Uses `_call_with_retry` pattern from `gemini_compliance.py`. JSON schema enforced via `response_mime_type=application/json` + `response_schema`. The `category_slug` enum is populated live from `SELECT slug FROM compliance_categories ORDER BY sort_order` at request time.

2. **`map_to_bank(ai_scope, conn) -> dict`** — Resolves AI output against the existing bank:
   - **Category resolution**: AI emits `compliance_categories.slug` (enum supplied via `response_schema`). SQL `JOIN compliance_categories c ON c.slug = ANY($1::text[])`.
   - **Jurisdiction resolution**: AI emits `(state, county?, city?)` tuples. SQL lookup against `jurisdictions` rows. Multiple matches (Springfield problem) → push to a "needs disambiguation" bucket the admin resolves in Step 5.
   - **Status filter**: only `jurisdiction_requirements.status = 'active'` (excludes superseded).
   - **Precedence honor**: leverages existing `PrecedenceRule` table to drop rows preempted by a higher jurisdiction — same logic `_fetch_state_requirements` uses; extract into a shared helper if not already.
   - Returns `{ existing: [requirement_id, ...], missing: [{category_slug, jurisdiction_tuple, why}, ...], ambiguous: [{candidates, why}, ...] }`. Pure SQL — no Gemini.

Model: prefer `gemini-3.1-flash-lite-preview` (already used in `matcha_work.py`). Fall back to `gemini_compliance.py` `mode=lite` model selection (already handles model unavailability).

### Routes: extend `server/app/core/routes/admin.py`

All gated by `require_admin` AND a new dep `require_master_admin` (checks `users.is_master_admin` flag or `metadata->>'master_admin' = 'true'` — verify existing flag during impl; if absent, use `require_admin` w/ a TODO).

```
POST   /admin/onboarding/sessions                       # body: {idempotency_key}
GET    /admin/onboarding/sessions                       # list in-progress + finalized
GET    /admin/onboarding/sessions/{id}
PATCH  /admin/onboarding/sessions/{id}                  # save step data; re-runs map_to_bank on resume if stale
POST   /admin/onboarding/sessions/{id}/create-company   # NEW: provisions companies + locations row at Step 3
POST   /admin/onboarding/sessions/{id}/expand           # run Gemini expand_scope → ai_scope
POST   /admin/onboarding/sessions/{id}/resolve          # SQL map_to_bank → resolved_scope
POST   /admin/onboarding/sessions/{id}/dispatch-research # body: {approved_missing_ids: [...]} — admin gate
POST   /admin/onboarding/sessions/{id}/finalize         # issues invite token; writes scope rows; flips status='finalized'
POST   /admin/onboarding/sessions/{id}/abandon          # sets status='abandoned' (24h reaper purges)
```

**Flow change vs v1**: `create-company` fires at end of Step 3, NOT at finalize. This means:
- `companies`, `business_locations`, `company_handbook_profiles` all exist before Gemini scope expansion
- `dispatch-research` can pass a real `company_id` + `location_id` to existing `run_compliance_check_task` / `run_medical_compliance_research` workers
- If admin abandons mid-flow, a reaper job (Celery beat-less, runs every 30 min via systemd-restart pattern that matches existing workers/celery_app.py) marks status='abandoned' and soft-deletes the company if no scope rows were written

`finalize` (now thinner):
1. INSERT into `company_compliance_scope` — one row per (company, requirement_id, location_id) from `resolved_scope.existing`. Each row stamped with `admin_reviewed_by = current_user.id`
2. INSERT into `company_certifications` + `company_licenses` from `ai_scope` (catalogs auto-populate from AI output via upsert-by-slug)
3. Generate invite token + create `business_registrations` row OR direct `invitations` row referencing `owner_email`; email the invite via existing invite-email machinery (reuse `invitations_router`)
4. Mark `onboarding_sessions.step='done'`, `status='finalized'`

**Idempotency**: `POST /sessions` requires `idempotency_key` (uuid) header or body field. UNIQUE constraint on `onboarding_sessions.idempotency_key` ensures a second click returns the same session. `finalize` is naturally idempotent — re-running just no-ops on the scope INSERT (UNIQUE constraint).

**Admin review gate for research dispatch**: Step 5 UI shows each `missing` requirement w/ a checkbox. `dispatch-research` body carries `approved_missing_ids` — only approved items dispatch. Solves the "AI hallucination pollutes bank" risk.

### CSV / HRIS step (size import)

- **CSV**: client-side parse via `papaparse`. Admin uploads, sees a column-mapping panel (auto-detects common headers like `employment_type`, `status`, `class`, falls back to dropdown). Output: `{ ft, pt, contractor, unknown }` totals only.
- **HRIS**: reuse `hris_service.test_connection()` + `fetch_workers()`. Mock mode in dev. Production requires existing `hris_import` feature flag; if flag off, show "HRIS connect locked — toggle in Features Admin OR use CSV". Returns same totals.
- **No employee-row import in Phase 1** — totals only. Full row import remains gated behind `hris_import` flag.
- **Skip**: explicit "skip + enter manually" button → numeric inputs.

## Frontend

### Files
- `client/src/pages/admin/AdminOnboarding.tsx` — list of in-progress sessions + "New Onboarding" CTA
- `client/src/pages/admin/AdminOnboardingWizard.tsx` — the wizard shell w/ step enum + ORDER + advance(), matching `IrOnboardingWizard` pattern
- `client/src/features/admin-onboarding/Step1Basics.tsx`
- `client/src/features/admin-onboarding/Step2Size.tsx`
- `client/src/features/admin-onboarding/Step3Locations.tsx`
- `client/src/features/admin-onboarding/Step4Scope.tsx` (shows AI expand spinner → results)
- `client/src/features/admin-onboarding/Step5Gaps.tsx` (existing-vs-missing + dispatch-research button)
- `client/src/features/admin-onboarding/Step6Review.tsx` (manifest summary + Finalize)
- `client/src/api/adminOnboarding.ts` — typed wrappers around all 9 endpoints

### Sidebar + route
- Add `{ to: '/admin/onboarding', icon: Wand2, label: 'Onboarding' }` to `AdminSidebar.tsx` right after the existing `Companies` entry
- Add two routes inside the `/admin` block in `App.tsx`:
  ```tsx
  <Route path="onboarding" element={<AdminOnboarding />} />
  <Route path="onboarding/:sessionId" element={<AdminOnboardingWizard />} />
  ```

### Step UX
- Each step lives in a single `<WizardShell>` with a left-rail step indicator (numbered, ✓ on completed, glowing on active) and right pane for the form
- AI steps (Step4Scope) show a streaming-status indicator while the Gemini call runs
- Resume support: clicking an in-progress session from the index resumes at `step`

## Gemini prompt (sketch — Step4 expand_scope)

```
You are scoping a NEW BUSINESS for compliance tracking.

INPUT:
  Industry: {industry}
  Specialty: {specialty}
  NAICS sector (if known): {naics}
  Locations:
{locations_yaml}

For each location, list the compliance categories, required certifications,
and required licenses that THIS business must track. Distinguish federal,
state, county, and city scope. Be specific: "Cardiology practice in Travis
County, TX" is NOT the same scope as "general medical practice in California".

Return ONLY JSON matching this schema (response_mime_type=application/json,
response_schema enforces category_slug enum):
{json_schema}

Rules:
- compliance_categories.category_slug MUST be from this controlled list:
  {categories_list_from_db}
- required_certifications + required_licenses: pick well-known names. Skip
  if speculative. Provide stable slug + display name.
- applicable_jurisdictions: emit as {state, county, city} tuples. Use ISO
  state codes (CA, TX). county/city null when scope is broader.
- Only list jurisdictions whose laws actually bind this business.
```

Gemini call uses `response_mime_type='application/json'` so we get strict JSON. Grounded search ON (Google Search tool) so it can pull current state-specific requirements when its parametric knowledge is weak.

## Verification

1. **Schema migration** — Alembic revision creates the tables. NEVER auto-run (per CLAUDE.md). User runs `alembic upgrade head` manually.
2. **Wizard happy path (hospitality)** — Onboard "Joe's Diner" w/ industry=hospitality + 2 CA locations. Confirm Gemini returns OSHA-general + state-specific food-safety + minimum-wage requirements. Bank already has CA min-wage — should resolve as `existing`. Confirm `company_compliance_scope` has rows pointing at the right `jurisdiction_requirements` IDs.
3. **Wizard happy path (medical/cardiology)** — Onboard "Heart Care Austin" w/ industry=healthcare + specialty=cardiology + TX location. Confirm Gemini adds CLIA, HIPAA, TX medical board, infection control. Bank likely has only some — confirm `missing` list surfaces correctly + clicking "Dispatch research" enqueues `run_medical_compliance_research` for each missing category.
4. **Shared-bank invariant** — Onboard a SECOND cardiology practice in TX. Confirm `company_compliance_scope` for co#2 references the SAME `requirement_id`s as co#1 — no new rows in `jurisdiction_requirements`.
5. **Resume support** — Start a wizard, complete steps 1-3, refresh browser, click the session in the index, confirm it resumes on step 4.
6. **HRIS mock connect** — In Step2, choose HRIS, confirm mock connector returns three sample employees → counts populate.
7. **Idempotency** — Submit `POST /sessions` twice w/ same idempotency_key. Second call returns same session id, no dupe.
8. **Multi-state scope_level integrity** — Onboard 1 CA + 1 TX location. Confirm CA wage requirement attaches to CA location row only (not TX), federal OSHA attaches to company-wide sentinel.
9. **Admin review gate** — Step 5: 3 `missing` items. Approve only 1. Confirm only that 1's research worker is enqueued.
10. **Type-check** — `npx tsc --noEmit` clean.
11. **Backend smoke** — `python -c "from app.core.routes.admin import router; from app.core.services.onboarding_scope_ai import expand_scope, map_to_bank"`.

## Resolved gaps from v1 review

| v1 issue | v2 resolution |
|---|---|
| No owner-user provisioning | `owner_email` captured in Step 1, invite token issued at Finalize via existing invite machinery |
| Dispatch-research race (no company_id) | `create-company` fires at Step 3, well before Step 5 dispatch |
| Certs/licenses had no storage | `certifications_catalog` + `company_certifications` (+ same for licenses) promoted into Phase 1 |
| Idempotency missing | `idempotency_key` UNIQUE on `onboarding_sessions`; finalize naturally idempotent via UNIQUE constraint on scope rows |
| AI category vs DB mismatch | Gemini `response_schema` uses `compliance_categories.slug` enum, fetched live |
| Jurisdiction string parser fragile | AI emits `(state, county?, city?)` tuples; SQL lookup w/ "ambiguous" bucket for multi-match cases |
| `location_id` optional → multi-state bug | NOT NULL + `scope_level` column + synthetic company-wide sentinel location |
| Free-text specialty | Controlled vocab `INDUSTRY_SPECIALTIES` in `onboarding_scope_ai.py`; typeahead in Step 1 |
| Parallel company-create paths | Wizard becomes canonical admin path; existing signup-approval still works (unchanged) but admin creation now flows through wizard |
| CSV column-mapping UX missing | Column-mapping panel in Step 2 w/ auto-detect + manual fallback |
| Master-admin vs admin role | Add `require_master_admin` dep; if no flag exists, use `require_admin` w/ TODO |
| JSONB schema versioning | `schema_version` INT on sessions; bump on shape change |
| AI hallucination → bank pollution | Step 5 admin checkbox gate; only `approved_missing_ids` dispatch research |
| No audit trail | Every state transition writes to existing audit table (reuse `log_audit` pattern from `ir_incidents.py`) |
| Cost framing | ~$0.10–0.40/wizard. 10 onboardings/day → $30–120/mo. Bounded by admin-trigger frequency |
| HRIS mock prod behavior | Production gates HRIS step on `hris_import` feature flag — explicit lock message if off |
| Resume edge case (stale resolved_scope) | PATCH endpoint re-runs `map_to_bank` on resume if session older than 7 days |

## Out of Scope (Phase 2+)

- Full HRIS employee import (rows into `employees` table) — Phase 1 stops at headcount totals
- Certifications/licenses CRUD UI in the rest of the product — Phase 1 captures them in scope but the surfacing UI in /app/compliance is later
- Drift detection (jurisdiction adds a new requirement → automatically pull into existing companies' scope) — design hook is `source='drift'` on the table but the worker that triggers it is Phase 2
- Multi-tenant brokers running onboarding for their book — Phase 1 is admin-only, master-admin role
- Editing a company's scope after finalize (add/remove requirements) — Phase 2 management UI; for now scope is finalize-and-done
- Cost: Gemini calls bill against the same `GEMINI_API_KEY`. Phase 1 is admin-triggered so volume is bounded; no rate limit added beyond what `_call_with_retry` already enforces

## Critical Files

**New (backend)**:
- `server/alembic/versions/<n>_onboarding_sessions_and_scope.py`
- `server/app/core/services/onboarding_scope_ai.py`

**New (frontend)**:
- `client/src/pages/admin/AdminOnboarding.tsx`
- `client/src/pages/admin/AdminOnboardingWizard.tsx`
- `client/src/features/admin-onboarding/Step{1..6}*.tsx`
- `client/src/api/adminOnboarding.ts`

**Modified**:
- `server/app/core/routes/admin.py` — add the 9 wizard endpoints
- `client/src/components/AdminSidebar.tsx` — add Onboarding entry
- `client/src/App.tsx` — add the two routes
