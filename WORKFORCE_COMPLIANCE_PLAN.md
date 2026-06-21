# Workforce Compliance bundle — build plan

_2026-06-20 · business-first risk inputs that also flip 3 EPL factors derived_

## Context
The broker **EPL readiness** lens leaves 5 factors *broker-attested* because the business platform never captured them. This builds the 3 most law-driven as **business-first compliance trackers** — **pay transparency**, **AI hiring-tool bias audits**, **biometric/BIPA consent**.

Each is a legal obligation the tenant must meet anyway (so it's genuinely actionable for the business, not broker-only data-entry), and each flips its EPL factor **attested → derived** as a byproduct (richer broker scoring, automatic). Off-platform broker clients keep all-attested (no business data) — unchanged.

Grounded in WTW _Insurance Marketplace Realities 2026_ p.85–86: underwriters now ask about pay-transparency compliance, "test and audit AI tools on a regular basis", and use "separate questionnaires for biometrics".

## Design decision — one umbrella feature, not three
New flag **`workforce_compliance`** (default off; admin-toggle via the existing per-company features endpoint; **not** tier-bundled). One business page with 3 sections. Pay-transparency is a **lightweight standalone** tracker (static `PAY_TRANSPARENCY_STATES` constant ∩ the company's `business_locations.state`) — **not** the heavy Pro `compliance` engine — so the bundle stays cohesive + non-Pro. (Future: Pro users could fold it into the jurisdiction engine.)

## Schema — migration `wfcomp01` (3 per-company tables; mirror accommodations/credentialing)
- **`hiring_ai_audits`** — `company_id, tool_name, vendor, last_audit_date, cadence_days (default 365), next_due_date, is_overdue, notes`. next_due/is_overdue computed on write (credentialing-expiry pattern). UNIQUE(company_id, tool_name).
- **`biometric_consent_points`** — `company_id, location_id?, collection_type, purpose, consent_obtained_date, consent_method, retention_policy, is_active, notes`.
- **`pay_transparency_status`** — `company_id, state, status (compliant|action_needed|na), postings_include_ranges bool, note, updated_at`; UNIQUE(company_id, state).

## Backend
- **`routes/workforce_compliance.py`** mounted `/workforce-compliance`, `dependencies=[Depends(require_feature("workforce_compliance"))]`:
  - AI audits CRUD · biometric points CRUD · pay-transparency GET status (required states = constant ∩ locations, merged with stored rows) + PUT per-state status.
  - `GET /summary` → counts + the 3 business-facing sub-scores (the tenant's own actionable view: overdue audits, states needing action, points missing consent).
- **`models/workforce_compliance.py`** — Pydantic Create/Update/Response.
- **`services/workforce_compliance.py`** — static `PAY_TRANSPARENCY_STATES` (CA, CO, WA, NY, IL, …) + `derive_*` helpers (read each table → 0–100 score + detail, or `None` when feature off / nothing declared).

## EPL flip — `services/epl_readiness.py`
- `BUSINESS_DERIVABLE = {pay_transparency, biometrics_bipa, ai_hiring_audit}`.
- In `compute_epl_readiness` (tenant path): when `merge_company_features` has `workforce_compliance` on, compute these 3 from business data via the new service helpers; each factor that yields a value becomes **derived** (business score + detail), else falls back to the broker attestation (today's behavior). Track per-factor actual source; return dynamic `derived_max`/`attested_max` (the 55/45 split shifts when factors flip).
- **`assess_from_statuses`** (off-platform) **unchanged** — all 10 attested.

## Frontend
- **`pages/app/WorkforceCompliance.tsx`** — 3 sections, each showing the business its own actionable flags (required states not compliant · overdue AI audits · points missing consent).
- **`api/workforceCompliance.ts`** wrappers; route in **`App.tsx`** wrapped in `<FeatureGate flag="workforce_compliance">`; **`ClientSidebar.tsx`** Compliance-group entry gated by `hasFeature`.
- **`BrokerClientDetail.tsx`** EPL tab — use `derived_max`/`attested_max` instead of hardcoded 55/45 denominators.

## Deferred (v2)
Overdue-audit Celery reminder (fields exist; mirror `compliance_action_reminders` + a disabled `scheduler_settings` row); MVR via credentialing ("Safety bundle"); pay-equity (HRIS).

## Verification
`./scripts/migrate-dev.sh`; admin-toggle `workforce_compliance` on for a dev company; add an overdue AI tool + a biometric point w/o consent + mark a pay-transparency state `action_needed`; confirm the **business page** surfaces those flags; confirm that company's **broker EPL detail** shows the 3 factors as *derived* with business scores (and `derived_max` shifted); confirm an **off-platform** client's EPL stays all-attested. `py_compile` + `tsc --noEmit` + `pytest tests/ir_incidents` (dummy GUSTO env) green; smoke `compute_epl_readiness` against the toggled dev company.

## Key files
`alembic/versions/wfcomp01_*.py` · `core/feature_flags.py` · `matcha/routes/workforce_compliance.py` (+ `routes/__init__.py` mount) · `matcha/models/workforce_compliance.py` · `matcha/services/workforce_compliance.py` · `matcha/services/epl_readiness.py` · `client/src/pages/app/WorkforceCompliance.tsx` · `client/src/api/workforceCompliance.ts` · `client/src/App.tsx` · `client/src/components/ClientSidebar.tsx` · `client/src/pages/broker/BrokerClientDetail.tsx` · `client/src/data/adminUpdates.ts` + `CLAUDE.md` flag row.
