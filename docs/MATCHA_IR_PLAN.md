# Matcha IR — Standalone Incident Reporting Product

## Context

The existing IR system (`server/app/matcha/routes/ir_incidents.py`, 39 endpoints) is platform-tied: it lives behind `require_admin_or_client` and assumes a fully-onboarded matcha-recruit company with the entire platform sidebar. This plan ships a self-service product targeted at HR admins of companies that only need incident reporting — distinct marketing/signup, simplified onboarding, paid SaaS subscription, and a backward-compatible upgrade path back into the full platform (ER copilot, compliance, policies) without data migration.

Good news from exploration: the IR backend (services, tables, anonymous reporting, OSHA logs, AI analysis) is already cleanly company-scoped and decoupled from ER/policies. Almost every dependency we need (feature flags, `register_business`, employee CSV upload, anonymous-token reporting, Stripe service) already exists. The work is mostly:

1. New front door (`/ir` landing + signup + Stripe checkout)
2. Guided onboarding wizard (company → employees with UIDs → anonymous reporting → done)
3. IR-only dashboard layout that hides non-incident nav
4. New Stripe price + subscription handler
5. One small DB column for employee UIDs

Naturally backward-compatible: enabling additional flags on the same company turns on ER copilot / compliance / policies and the existing IR data flows through without migration.

## Settled architecture decisions

- **Same app, separate route** — no new server, no subdomain. New marketing/signup pages at `/ir`, dashboard reuses `/app/incidents` with a stripped layout.
- **Tier signal = `companies.signup_source` + `enabled_features.incidents`.** Both required. IR-only ⇔ `signup_source='ir_only_self_serve'` AND `enabled_features.incidents=true`. Bespoke customers keep `signup_source='bespoke'` regardless of feature flag shape, so they never accidentally get the slim layout.
- **Flat paid SaaS** — Stripe subscription required at signup. Free trial is optional v1.5.
- **Employee UID = HR-internal reference** — badge/employee number, not a login. Stored on `employees` table, used to resolve involved employees in IR forms.
- **Auth role**: existing `client` role; no new role.

## Backend changes

### Migrations
- **`alembic/versions/XXX_add_employee_external_uid.py`**: `ALTER TABLE employees ADD COLUMN external_uid VARCHAR(64)` plus partial unique index `(company_id, external_uid) WHERE external_uid IS NOT NULL`.
- **`alembic/versions/XXX_add_ir_subscriptions.py`**: `CREATE TABLE ir_subscriptions` mirroring `mw_subscriptions` shape (company_id FK, stripe_subscription_id, stripe_customer_id, status, current_period_end, canceled_at). Kept separate from `mw_subscriptions` so matcha-work credits stay distinct.
- **`alembic/versions/XXX_add_companies_signup_source.py`**: `ALTER TABLE companies ADD COLUMN signup_source VARCHAR(32)`. Values: `bespoke` (default for existing rows), `ir_only_self_serve`, `personal`, `invite`, `broker`. Backfill: `UPDATE companies SET signup_source = 'bespoke' WHERE signup_source IS NULL`. Disambiguates IR-only customers from bespoke customers who happen to share a feature-flag shape, so the slim layout never accidentally hides the full sidebar from a sales-led customer.

### Routes / services
- **`server/app/core/routes/auth.py:1497`** — extend `register_business()` with optional `tier='ir_only'`. When set: skip pending-approval queue (auto-approve), set `enabled_features = {"incidents": true}` only, set `signup_source='ir_only_self_serve'`, redirect into Stripe checkout instead of straight into the app. All other branches (bespoke default, invite, broker, personal) write their corresponding `signup_source` value.
- **`server/app/core/services/stripe_service.py`** — add `create_ir_subscription_checkout(company_id)` and webhook handlers:
  - `customer.subscription.created` / `invoice.payment_succeeded` → write to `ir_subscriptions`, set `companies.status='approved'`, `enabled_features.incidents=true`.
  - `customer.subscription.deleted` / `customer.subscription.updated` (status=past_due → after grace period) → flip `enabled_features.incidents=false`, mark subscription canceled.
- **`server/app/matcha/routes/ir_onboarding.py` (new)** — small companion router:
  - `GET /api/ir-onboarding/status` — current wizard step (company_info / employees / anonymous / ready).
  - `POST /api/ir-onboarding/complete` — sets `companies.ir_onboarding_completed_at`.
- **`server/app/matcha/routes/employees.py`** — extend bulk CSV upload to recognize `uid` column → write `external_uid`. Add `GET /api/employees/by-uid/{uid}` for IR form lookups.
- **`server/app/matcha/routes/ir_incidents.py`** — extend `involved_employee_ids` resolver in incident create to accept either UUIDs or UIDs and resolve UIDs server-side via the new lookup endpoint's helper.
- **Feature flags** (`server/app/core/feature_flags.py`) — confirm `incidents` is in `KNOWN_PLATFORM_ITEMS`. Default value stays `false` so non-IR companies don't get it accidentally.

### NOT changing
- `ir_incidents`, `ir_documents`, `ir_audit_log`, `ir_investigation_interviews`, `osha_annual_summaries` tables — already correctly company-scoped.
- IR services (`ir_analysis.py`, `ir_precedent.py`, `ir_consistency.py`, `ir_interview_questions.py`) — pure logic, reused as-is.
- Anonymous reporting endpoints — already token-based, reused as-is.

## Frontend changes

### New files
- `client/src/pages/landing/IrProductPage.tsx` — pitch + pricing + CTA → signup.
- `client/src/pages/auth/IrSignup.tsx` — company info form → POST `/auth/register-business?tier=ir_only` → redirect to Stripe checkout URL.
- `client/src/pages/ir-onboarding/IrOnboardingWizard.tsx` — top-level shell, drives 4 steps.
- `client/src/features/ir-onboarding/`:
  - `Step1CompanyInfo.tsx` — name + locations (reuses existing locations API).
  - `Step2Employees.tsx` — single-add form + CSV upload with `uid` column. Reuses `useBulkUpload`.
  - `Step3AnonymousReporting.tsx` — toggle + show generated link/QR (reuses existing `IRAnonymousReportingPanel` logic).
  - `Step4Done.tsx` — congrats + go-to-dashboard.
- `client/src/components/ir-only/IrLayout.tsx` — slim sidebar: Incidents / Employees / Settings / Billing.
- `client/src/utils/tier.ts` — `isIrOnlyTier(company) = company.signup_source === 'ir_only_self_serve' && company.enabled_features.incidents`. Both must match — flag shape alone is not enough, otherwise a partially-provisioned bespoke customer could fall into the slim layout. `signup_source` is exposed on the existing `/auth/me` payload.

### Modified files
- `client/src/components/Layout.tsx` — pick `IrLayout` instead of full layout when `isIrOnlyTier(companyFeatures)` returns true.
- `client/src/components/ir/IRCreateIncidentModal.tsx` — employee picker accepts UID lookup in addition to name search.
- `client/src/api/client.ts` — add `irSignup`, `getIrOnboardingStatus`, `completeIrOnboarding`, `lookupEmployeeByUid`.
- `client/src/App.tsx` (or routes file) — register `/ir`, `/ir/signup`, `/ir/onboarding/*` routes.

### Reused as-is
- `IRList.tsx`, `IRDetail.tsx`, all `client/src/components/ir/*` panels — render unchanged inside `IrLayout`.

## Stripe wiring

- **New Stripe Product**: "Matcha IR" with one Price (e.g. monthly recurring). Configure in Stripe dashboard; store price ID in `settings.stripe_ir_price_id`.
- **Checkout flow**: signup creates company in `pending` + Stripe customer → checkout session → success URL = `/ir/onboarding` → webhook activates company.
- **Webhook security**: reuse existing webhook signature verification in `stripe_service.py`.
- **Failed payments**: subscription `past_due` → keep `incidents=true` for 7-day grace period, then disable.

## Backward-compat / upgrade path

- Upgrade button in IR-only dashboard settings → "Add ER Copilot, Compliance, Policies" → Stripe customer portal → on subscription change webhook, flip additional flags in `enabled_features`. Optionally promote `signup_source` to `bespoke` once a CSM finishes white-glove license/CRM setup, which cuts over the layout from `IrLayout` to the full sidebar. No data migration required.
- All existing IR data (`ir_incidents` rows, documents, OSHA logs, anonymous reports) becomes accessible to ER copilot routes the moment `er_copilot=true` because the cross-system bridge in `er_copilot.py` already reads `ir_incidents` by `company_id`.

## Critical files

| File | Purpose |
|------|---------|
| `server/app/core/routes/auth.py:1497` | Add `tier='ir_only'` branch to `register_business` |
| `server/app/core/services/stripe_service.py` | `create_ir_subscription_checkout` + webhook handler |
| `server/app/core/feature_flags.py` | Confirm `incidents` in `KNOWN_PLATFORM_ITEMS` |
| `server/app/matcha/dependencies.py:392` | `require_feature("incidents")` already exists; reused |
| `server/app/matcha/routes/employees.py` | CSV upload + UID column + `GET /by-uid/{uid}` |
| `server/app/matcha/routes/ir_incidents.py` | Resolve UIDs in `involved_employee_ids` on create |
| `server/app/matcha/routes/ir_onboarding.py` (new) | Wizard status + complete endpoints |
| `client/src/pages/landing/IrProductPage.tsx` (new) | Marketing landing |
| `client/src/pages/auth/IrSignup.tsx` (new) | Signup → Stripe |
| `client/src/features/ir-onboarding/*` (new) | 4-step wizard |
| `client/src/components/ir-only/IrLayout.tsx` (new) | Slim nav |
| `client/src/components/Layout.tsx` | Layout selection by tier |
| `client/src/utils/tier.ts` (new) | `isIrOnlyTier` helper |

## Build order

1. **Schema** — employee `external_uid` migration + `ir_subscriptions` table. Run against prod only after explicit approval (per CLAUDE.md DB safety rules).
2. **Backend signup + Stripe** — `register_business` extension, Stripe checkout, webhook. Test in Stripe test mode with the existing webhook tunnel.
3. **Onboarding endpoints** — status + complete, employee CSV with UID, `GET /by-uid/{uid}`.
4. **Frontend onboarding wizard** — wire each step against the new endpoints.
5. **Tier-aware layout** — `IrLayout` + `isIrOnlyTier`. Ensure full-platform companies still see the standard sidebar.
6. **Marketing + signup pages**.
7. **Upgrade flow** — settings page button + Stripe customer-portal redirect.

## Verification

- **End-to-end signup**: hit `/ir/signup` with a fresh email → company created `pending` with `signup_source='ir_only_self_serve'` → Stripe test card `4242 4242 4242 4242` → webhook fires → `companies.status='approved'`, `enabled_features={"incidents":true}` → land on onboarding wizard.
- **Tier isolation**: spin up two test companies — one with `signup_source='bespoke'` and `enabled_features={"incidents":true}` only, one with `signup_source='ir_only_self_serve'` and same flags. Confirm the bespoke one renders the full sidebar and the IR-only one renders `IrLayout`. Same flag shape, different layouts.
- **Onboarding**: walk all 4 steps. Confirm `employees` rows have `external_uid`, anonymous report token persisted, `ir_onboarding_completed_at` set.
- **Incident create with UID**: in IRCreateIncidentModal, type the UID → employee resolved → submit → `ir_incidents.involved_employee_ids` contains UUIDs, not UID strings.
- **Anonymous report**: generate token, open in incognito, submit → row appears in IR list.
- **AI analysis**: trigger categorize / severity / root-cause / recommendations on the new incident — Gemini calls succeed (services unchanged).
- **OSHA**: file an OSHA-recordable incident → `/osha/300-log` and `/osha/300a` render.
- **Upgrade simulation**: manually flip `enabled_features.er_copilot=true` for the test company → reload → full sidebar appears, existing IR data visible from ER copilot routes.
- **Subscription cancel**: cancel sub in Stripe → webhook → `enabled_features.incidents=false` → billing-required state instead of dashboard.
- **Tests**: integration tests for `register_business(tier='ir_only')`, webhook handler with signed mock event, employee CSV with UID column, `GET /employees/by-uid/{uid}`. No DB-mutating tests against prod (per CLAUDE.md).

## Out of scope (separate tracks)

- Self-service downgrade (full → IR-only) — manual for v1.
- Multi-product Stripe upgrades inside one customer record (use Stripe customer portal).
- Branding split / white-label.
- Mobile app for incident reporting.
- SAML/SSO for IR-only tier.
