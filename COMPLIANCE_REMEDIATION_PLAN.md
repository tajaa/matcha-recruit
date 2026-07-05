# Matcha Compliance — Audit Remediation Plan

> Canonical remediation plan (approved 2026-07-04). Produced by a 5-pass audit: core service, routes/security, onboarding/HRIS mapping, data library, coverage model.

## Context

Four parallel audits (core service, routes/security, onboarding/HRIS mapping, data library) found 2 critical security holes, 2 critical correctness/product gaps, ~20 lesser issues. All critical citations re-verified firsthand. Prod pre-customer (Stripe test mode) so pricing gap flagged, not fixed.

A fifth pass evaluated the **coverage model** against the product promise — "regulatory/compliance watcher for all kinds of businesses, scoping starts at signup from business + roster" — and found the promise breaks at the first input: signup never asks what the business does, the build never reads the roster, and the category library only covers US employment law + healthcare. Phase E addresses this.

**The broken signup→scoping chain (each link verified):**
- **E0 — signup collects no industry.** `ComplianceSignup.tsx` fields: email/password/company-name/headcount/jurisdiction-count only. No wizard step (`Step1Locations`→`Step5Done`) collects it either. So `companies.industry` is NULL for every self-serve compliance customer → `_get_industry_profile` (`matcha_x_onboarding.py:304-305`) returns None → build runs generic labor-only research. The entire industry-scoping machinery (profiles, prompt contexts, category tags) is unreachable for the standalone product's own customers. Only admin-created (bespoke) companies get an industry (`admin.py:585`, `auth.py:1899`).
- **Roster never read** (Phase D): build/stream uses only manually-typed `business_locations`; `employees.work_state/work_city` ignored despite UI claiming otherwise.
- **Industry resolution = 39 free-text aliases → 7 profiles** (`compliance_service.py:76-130`); unknown → `""` silently. Finance, education, transport, agriculture, energy, construction (aliased into manufacturing), childcare, personal care, legal, real estate: unmapped.
- **Taxonomy 2/3 healthcare**: 45 categories = 12 labor + 3 supplementary + 30 healthcare-family (`zl0m1n2o3p4q` migration). Non-healthcare business gets 15 US-labor categories. Absent domains: data privacy, general cybersecurity, AML/KYC, PCI, food safety, construction codes, DOT/transport, export controls/sanctions, consumer protection/advertising, accessibility, ESG, alcohol/cannabis licensing.
- **Threshold engine unfueled**: `evaluate_trigger_conditions` (`compliance_service.py:8270`) supports headcount gt/gte triggers (FMLA-50, ACA-50, EEO-100 shaped) but no data populates `trigger_conditions`, and roster headcount is never written to `facility_attributes`.
- **International**: schema (`country_code`, national/province levels) + intl research skill exist, but onboarding forms are US-shaped (state+zip, no country), no non-US precedence model, US-only legislation feeds.
- **Freshness dormant**: `legislation_watch`/`compliance_checks`/`structured_data_fetch` scheduler rows default disabled; detected changes only create alerts, never update `jurisdiction_requirements`; `last_verified_at` = "time since manual research," not verified accuracy.
- **Silent data loss**: 8 of 10 manufacturing categories have no `compliance_categories` row; ingest silently drops their research (Phase C1).

**Confirmed clean (no action):** broker rollup scoping, PDF SSRF (`safe_url_fetcher` everywhere), worker `scheduler_settings` gates, `compliance_action_reminders` idempotency, service-layer tenant scoping, Finch worksite-preference mapping (`finch_service.py:426-431` — model for Phase D), `resolve_company_id` (admin-only override, validated), `legislation_watch.py` service structure.

**Implementation model: Sonnet 5** (user global rule — subagents too).

---

## Phase A — Security lockdown (ship first, isolated commit)

### A1. `lite_router` scope restore (CRITICAL)
`core/routes/__init__.py:64` mounts `compliance_lite_router` with **no feature gate** — comment (61-63) says intent was "calendar, locations-read, alert read/dismiss" for matcha-lite, but router carries full location CRUD. Any authed client/admin of any tier gets it.

Fix in `server/app/core/routes/compliance.py`:
- Move `@lite_router.post("/locations")` (:141), `.put("/locations/{id}")` (:333), `.delete` (:370), `.patch(".../facility-attributes")` (:1100) → `router` (full-`compliance`-gated). Keep GETs (:100, :238, :284, :563, :1127) + alert read/dismiss (:619, :660) on `lite_router`.
- Gate `lite_router` mount (`__init__.py:64`) with `require_any_feature("compliance", "compliance_lite", "incidents")` — preserves matcha-lite-calendar intent (lite's paid flag = `incidents`; calendar entry `IrSidebar.tsx:23` commented but planned) while closing Free-tier access.
- Verified safe: Matcha-X onboarding creates locations via its own `/matcha-x-onboarding` routes (`matcha_x_onboarding.py:167`); Matcha Compliance product has full `compliance` flag.

### A2. Gemini cost-abuse via location create (HIGH)
`create_location_endpoint` (`compliance.py:141-172`) unconditionally schedules `run_compliance_check_background` (`allow_live_research=True` default — live Gemini) when repo coverage incomplete. Fix: check merged features (`merge_company_features`) before `add_task`; pass `allow_live_research=has_full_compliance` so non-Pro tenants get repository-only backfill (functional once B1 lands).

### A3. Rate-limit Gemini-calling routes (HIGH)
`compliance.py` never imports existing `check_rate_limit` (`rate_limiter.py`, used `resources.py:1043`). Add per-company limits: `POST /locations/{id}/check`, `/ask`, `/payer-policies/ask`, `/payer-policies/research`, `/protocol-analysis`, `POST /locations`. Follow `resources.py` pattern.

### A4. IDOR in `assign_legislation_endpoint` (MEDIUM)
`compliance.py:846-918` inserts body-supplied `location_id` into `compliance_alerts` without ownership check. Fix: `SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2` before insert; 404 on mismatch.

### A5. Admin cherry-pick ownership check (MEDIUM)
`compliance_service.py` `admin_add_requirement_to_location` (~:9052) + `_batch` (~:9091): verify `location_id` belongs to `company_id` (batch docstring admits it doesn't). Same check as A4; remove docstring disclaimer.

---

## Phase B — Engine correctness

### B1. Dead-`elif` disabling repo-refresh backfill (CRITICAL)
`compliance_service.py:4673/:4798` (`run_compliance_check_stream`) and `:7472/:7537` (`run_compliance_check_background`):
```python
if not used_repository and allow_live_research:   # Tier-3 live Gemini
...
elif not used_repository and allow_live_research: # unreachable — identical condition
```
The `elif` body is the "repository-only mode, trigger source-of-truth refresh" path (emits `repository_refresh`, sets `used_repository=True`). Fix both: `elif not used_repository and not allow_live_research:`. Callers passing `False`: Celery `compliance_checks.py:22-27` (primary automated path), `admin_onboarding.py:918-922,1110`. Read full surrounding block before flipping — verify elif body still coherent.

### B2. Silent preemption relabel (MEDIUM)
`_filter_with_preemption` (`compliance_service.py:3955-3970`): state-preempted category with no state row → relabels strongest local row as `jurisdiction_level='state'`, only a `print()`. Fix: keep promotion, add in-payload provenance marker (`promoted_from_level='city'`) + `logger.warning`; surface in requirement payloads. No DDL.

### B3. Bare `except Exception` on preemption lookups (MEDIUM)
Four `_research_{healthcare,oncology,life_sciences,medical_compliance}_..._for_jurisdiction` helpers (~:1749, :1955, :2080, :2207, :8868): narrow `except Exception: preemption_rules = {}` → `except asyncpg.UndefinedTableError` + `logger.warning` fallback.

### B4. Dead code removal (LOW)
`run_compliance_check` (`compliance_service.py:5427`) — zero callers, delete.

### B5. Library permanence — research-once, query-forever (HIGH, user directive)
**What already exists (keep, don't rebuild):** every research path writes back to the shared `jurisdiction_requirements` library — Gemini live research upserts at `compliance_service.py:1643` + `:2516` (keyed `UNIQUE(jurisdiction_id, requirement_key)`, tagged with category/level/source_url/source_name/source_tier), and Claude fill-gaps scripts write via the ingest scripts. Schema already carries the change-tracking fields the directive asks for: `effective_date`, `expiration_date` (= "date due to change"), `previous_value`, `change_status`, `last_changed_at`, `last_verified_at` (`database.py:3007-3031`). No DDL needed.

**What to change — kill TTL-driven re-research:** `_is_jurisdiction_fresh` (`compliance_service.py:1277-1287`, age `< threshold_days`) currently makes stored data expire — beyond ~90 days (`:4796` `max(auto_check_interval, 90)`; `:1417/:1436` floors) the engine treats the library as stale and re-runs Gemini even when nothing changed. Under the new model:
- Repository hit whenever rows EXIST for the jurisdiction, regardless of age — stored policy is truth until a future diff-scheduler says otherwise. Implement by short-circuiting the freshness check to an existence check (keep the function; make `threshold_days` effectively infinite via a single module-level setting so the future scheduler can restore selective re-checks without re-plumbing).
- Keep **gap-driven** research: `_missing_required_categories` (cache-miss backfill for categories never researched) still triggers research — that's library growth, not re-search.
- The `compliance_checks` Celery task becomes the future diff-scheduler's home (already default-disabled — matches "schedulers LATER"). Do not enable.
- Verify `_save`'s stale-row cleanup (`:2497`, removes rows absent from the latest research result set) only runs inside an actual research pass — under query-forever it can't fire spuriously, but confirm no read path calls it.

**Populate change-dates going forward:** research prompts (Gemini) + fill-gaps skill docs instructed to emit `effective_date`/`expiration_date` (or typical change cadence, e.g. minimum wage → Jan 1) per requirement. Future scheduler then re-queries only `WHERE expiration_date <= now()` — the diff mechanism the directive defers.

**Invariant (document in code + skills):** any new research path MUST upsert into `jurisdiction_requirements` — never per-company-only storage; C2's fail-loud ingest enforces the script side.

**Deferred (flag, don't build):** most-protective-wins applies only to `minimum_wage` (`_filter_by_jurisdiction_priority`) — legal-domain product decision. ~1700-line `stream`/`background` duplication (why B1 exists twice) — extract-shared-core as separate follow-up.

---

## Phase C — Data hygiene + tooling

### C1. 8 orphaned manufacturing categories (CRITICAL data loss) — ⚠️ migration approval
`admin.py:3615-3618` defines 10 manufacturing categories; only `quality_systems` + `supply_chain` seeded (`u6v7w8x9y0z1:50-68`). Ingest (`ingest_research_md.py:203-208`, `ingest_gap_fill.py:526-527`) silently skips unknown categories — research for other 8 (incl. `environmental_compliance`) thrown away. Fix: data-only Alembic migration seeding the 8 (mirror `u6v7w8x9y0z1` pattern). **`./scripts/migrate-dev.sh` then `./scripts/migrate-prod.sh` — user approval before prod.**

### C2. Ingest fails loudly
Both ingest scripts: unknown category → collect, print summary, exit non-zero.

### C3. Stale `matcha-recruit` paths break every research skill
All `.claude/commands/fill-gaps*.md`, `bootstrap-jurisdiction.md`, `research-jurisdiction*.md`: `cd .../matcha-recruit/server` → `.../matcha/server`. Sed sweep + spot-check.

### C4. Kill life-sciences vaporware in `fill-gaps.md`
6-category "Life Sciences" group exists in no migration/script. Remove or mark "not built."

### C5. Derive `REQUIRED_CATEGORIES` from DB
`admin.py:3344-3363` hardcoded list is why C1 went unnoticed. Replace with query against `compliance_categories` (cached). Check all readers first.

---

## Phase D — Roster-driven jurisdictions (feature work, phased)

Self-serve build (`matcha_x_onboarding.py:295-303`) reads **only** `business_locations`; never `employees.work_state/work_city`. `Step3People.tsx:86` claims otherwise. Correct logic stranded in admin-only `enrich_company_from_roster` (`admin_onboarding.py:797-966`).

### D1. Stopgap (ship with A/B): honest UI + skipped counts
- Fix `Step3People.tsx:86` copy until D3.
- `_collect_roster` (`admin_onboarding.py:573-613`): surface count of employees dropped for `work_state IS NULL`.

### D2. CSV work-location validation (MEDIUM)
`bulk_upload.py:~309-353`: validate `work_state` (2-letter US or blank), report per-row failures + missing-location count in response summary.

### D3. Roster-driven self-serve build (LARGE)
- Lift `_collect_roster` + jurisdiction-derivation into shared service (`compliance_service.py` or new `roster_jurisdictions.py`).
- `build/stream` unions roster-derived jurisdictions with typed locations; stream progress events; show skipped-employee count in build UI.
- Wire `_resolve_county_from_zip` (`compliance_service.py:571`) into `_get_or_create_jurisdiction` (:1107) — zip collected in Step1, currently unused; county resolves only via city-name match (`:586`).

### D4. Post-onboarding drift detection (MODERATE)
After employee create/update/bulk/HRIS-sync: `work_state` not in company's jurisdiction set → `compliance_alert` ("roster implies jurisdiction X not in your build") — alert only, never auto-research. Reconcile `compliance_jurisdiction_count` (signup-declared) vs computed; mismatch banner.

**Deferred:** multi-state employees (single `work_state` column), per-jurisdiction pricing (headcount-only despite marketing — `stripe_service.py:632/646`; revisit at go-live), per-row confidence field.

---

## Phase E — Universal coverage model ("any business, globally")

**Guiding principle: fail loud on coverage gaps.** System won't enumerate all law everywhere day one; it must never present thin coverage as complete. Every resolution step (industry, categories, jurisdiction, country) gets an explicit "could NOT cover" surface.

### E0. Collect industry at signup + onboarding (MODERATE — do first, unblocks everything)
- `ComplianceSignup.tsx`: add structured industry picker (drives E2's canonical set; until E2 lands, use the 7 existing profiles + "other"); send with registration; persist to `companies.industry` (registration INSERT already carries it — `auth.py:1899` — so self-serve payloads just need the field).
- Onboarding wizard: confirm/refine industry step (or fold into Step1) — company may be multi-line-of-business; build (`matcha_x_onboarding.py:304`) already consumes it once non-NULL.
- Backfill prompt for existing NULL-industry companies (banner → picker).

### E1. Coverage honesty layer (MODERATE — cheap, compounding)
- `_resolve_industry` → `""` becomes explicit `industry_unresolved` state: UI banner ("coverage limited to general employment law — tell us your industry"), admin rollup of unresolved companies.
- Build/report output gains **coverage manifest**: categories checked / skipped + why (no industry profile, category unseeded, no jurisdiction data, trigger unmet, US-only). Reuse `jurisdiction_data_overview` machinery (`admin.py:3367-3586`) per-company.

### E2. Industry resolution overhaul (MODERATE)
- Replace 39-alias map with canonical industry table on standard taxonomy (NAICS 2-digit sectors, ~20 rows — covers "any business" definitionally), each mapping to category groups + research context + entity-type defaults. Structured picker, not free text.
- Extend existing `industry_compliance_profiles` (`_get_industry_profile`, `compliance_service.py:298-325`) rather than new schema where possible. ⚠️ DDL needs approval.
- Backfill via alias map; unresolved → E1 banner.

### E3. Category taxonomy expansion (LARGE — phased by domain)
Priority order (each = data-only migration + research-skill doc; C5 auto-includes in coverage math): **1)** data_privacy (state acts, GDPR-family, biometric) **2)** general_business (registration, sales-tax nexus, consumer protection, advertising, accessibility) **3)** food_safety + alcohol **4)** financial_services (AML/KYC/licensing) **5)** construction (own profile, un-aliased from manufacturing) **6)** transport/logistics (DOT/CDL). Complete orphaned manufacturing 8 first (C1). Federal/national rows before state fan-out; existing fill-gaps skill pattern (paths fixed by C3).

### E4. Threshold applicability wiring (MODERATE)
- Write roster-derived `employee_count` (company + per-location) into `facility_attributes` on employee CRUD/CSV/HRIS sync (piggybacks D4 hook).
- Seed `trigger_conditions` for classic headcount statutes (FMLA 50, COBRA 20, EEO-1 100, ACA 50, WARN 100 + state mini-WARNs) — data-only updates.
- Research skills emit `trigger_conditions` + `applicable_entity_types` going forward.

### E5. International self-serve (LARGE — gate behind demand)
- Step1 country selector; non-US skips state/zip validation, creates `national`/`province` jurisdictions via existing intl helpers.
- Non-US precedence: "national baseline + local additions, no preemption" v1 (matches intl skill docs); EU-directive layering out of scope v1, stated in manifest.
- Roster: country-aware work-location (extends D2 — accept ISO country + subdivision).
- Defer build until non-US prospect; manifest says "US only" meanwhile.

### E6. Diff-schedulers (DEFERRED per user directive — design note only)
Library is permanent truth (B5) until these exist. When built later: `compliance_checks` worker re-queries only requirements with `expiration_date <= now()` (or per-category typical-change cadence); `legislation_watch` alerts gain one-click "re-research this category"; diffs update `previous_value`/`change_status`/`last_changed_at` (columns already exist). Not in scope now — B5's setting is the single knob to flip.

**Phase E decisions needing user input:** NAICS vs custom taxonomy (E2); E3 domain priority order; intl now vs post-first-customer (E5).

---

## Sequencing + commit strategy

1. **Commit 1 (Phase A)** — security, ships alone. D1 copy-fix can ride along.
2. **Commit 2 (Phase B)**.
3. **Commit 3 (Phase C)** — C1 migration authored, **applied only after approval** (dev → prod).
4. **Commits 4+ (Phase D)** — D2 separate; D3 split (service extraction → build integration → zip→county); D4 own commit.
5. **Phase E** — E0 first (single field end-to-end, unblocks industry machinery immediately), then E1 (makes every later gap visible), E2, E3 domain-by-domain (own commit + migration each), E4 after D4 (shares roster hook), E6 ops toggle anytime, E5 deferred.

All on `main` (no branching without permission). Stop-point after any phase.

## Verification

- Post-edit hook: `py_compile`. After each phase: `cd server && python3 -m pytest tests/compliance/ -v` (4 files).
- A: dev server up → Free-tier token 403 on `POST /api/compliance/locations`; lite (`incidents`) still gets calendar GETs; 429 on `/ask` burst.
- B1: unit test — `allow_live_research=False` + missing categories → `repository_refresh` event emitted (both variants).
- C1: post-migration `SELECT slug FROM compliance_categories` has all 10 manufacturing; re-run one environmental ingest → rows land.
- D3: dev company with CSV employees in state with no typed location → that jurisdiction in build output.
- E0: fresh ComplianceSignup with industry picked → `companies.industry` set → build log shows industry profile applied.
- E1: dev company, unmapped industry → unresolved banner + manifest lists skipped categories with reasons.
- E4: 60 CSV employees → FMLA requirement applicable; 40 → trigger false, manifest shows "below threshold" (not silently absent).
- B5: dev jurisdiction with rows older than 90 days → compliance check hits repository (no Gemini call, assert via log/mock); jurisdiction with a missing required category → gap-backfill research still fires and upserts into `jurisdiction_requirements`.
- All test data: reserved domains (`@example.com`/`.test`), local dev DB only.
