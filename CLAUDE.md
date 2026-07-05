# Matcha Recruit

Four products share this codebase: **Free** (resources hub), **Matcha-lite** (paid IR/HR-records bundle), **Matcha** (full bespoke platform), and **Matcha-work** (collaborative AI workspace, web + macOS).

## Products

Differentiated at signup via `companies.signup_source` and routed in the UI by `client/src/utils/tier.ts` + `client/src/components/TenantSidebar.tsx`.

| Product | Signup page | `tier` sent | `signup_source` | Sidebar | Routes | Billing |
|---|---|---|---|---|---|---|
| **Free** | `pages/auth/ResourcesSignup.tsx` | `resources_free` | `resources_free` | `ResourcesFreeSidebar` | `/resources/*` | None — upgrade CTA |
| **Matcha-lite** | `pages/auth/MatchaLiteSignup.tsx` | `matcha_lite` | `matcha_lite` | `IrSidebar` once paid; `MatchaLitePendingSidebar` while pending | `/ir/*` | Stripe sub, headcount-based |
| **Matcha Compliance** | `pages/auth/ComplianceSignup.tsx` | `matcha_compliance` | `matcha_compliance` | `ComplianceSidebar` once paid; `CompliancePendingSidebar` while pending | `/app/compliance*` | Stripe sub, headcount + jurisdictions |
| **Matcha (platform)** | `pages/BetaRegister.tsx` (token) or admin-created post-sale | n/a | `bespoke` (default) / `invite` | `ClientSidebar` (full nav) | `/app/*` | Contract / invoice |
| **Matcha-work** | `pages/BetaRegister.tsx` (personal token) → `/work`; or inside Matcha company | n/a | `bespoke` (personal: `is_personal=true`) | `ClientSidebar` AI group; macOS app | `/work/*` | Stripe `matcha_work_personal` $20/mo or business token packs |

Sidebar dispatch in `client/src/components/TenantSidebar.tsx`. Tier-check helpers (`isIrOnlyTier`, `isMatchaLitePending`, `isResourcesFreeTier`) in `client/src/utils/tier.ts`.

### Free — resources hub
- Marketing/upgrade landing for self-serve signups. No paid features.
- All `enabled_features` off; gated by `<RequireBusinessAccount>` (`client/src/components/`).
- Backend: `server/app/core/routes/resources.py`. Public landing pages + business-gated tools (templates, state guides, calculators, audit, glossary, job descriptions).
- Free→paid path: `<UpgradeUpsellCard>` ("Talk to sales") posts to `/api/resources/upgrade/inquiry`.

### Matcha-lite — paid IR + HR records (entry tier)
- Stripe-purchasable, headcount-based (max 300 employees).
- Checkout: `POST /resources/checkout/lite` (`server/app/core/routes/resources.py`). Stripe webhook `checkout.session.completed` flips `enabled_features.incidents=true` — until then `MatchaLitePendingSidebar` shows the Subscribe CTA.
- Once paid: `incidents` + `employees` + `handbooks` (handbook **generation**) on; `IrSidebar` exposes incidents, risk insights, OSHA, handbooks, employees, company. **No** handbook audit, training, discipline, or credentialing — those moved up to **Matcha-X** (the `matcha_lite` tier overlay force-asserts `training`/`discipline` off). See the tier-bundle note under Feature Flags.
- Backend routers: `ir_incidents_router` (`/ir/incidents/*`), `ir_onboarding_router` (`/ir-onboarding/*`) in `server/app/matcha/routes/__init__.py`.
- Onboarding: `client/src/features/ir-onboarding/IrOnboardingWizard.tsx`; completion stamps `companies.ir_onboarding_completed_at`.
- Legacy `pages/auth/IrSignup.tsx` (`tier='ir_only'`, `signup_source='ir_only_self_serve'`) still wired at `/ir/signup` for private beta — also lands on `IrSidebar`.

### Matcha Compliance — standalone self-serve compliance product
- Self-serve, Stripe-purchasable product that grants the **full** `compliance` feature and nothing else. Modeled on Matcha-lite/Matcha-X: signup page → pending sidebar → Stripe checkout → webhook flips a flag → active sidebar.
- Signup: `pages/auth/ComplianceSignup.tsx` at `/compliance/signup` (`tier='matcha_compliance'`, `signup_source='matcha_compliance'`); collects headcount **+ jurisdiction count**.
- Checkout: `POST /resources/checkout/compliance` (`server/app/core/routes/resources.py`). Pricing = headcount component + per-jurisdiction surcharge (`matcha_compliance_price_cents`, `stripe_service.py` — placeholder, see TODO). Stripe webhook `checkout.session.completed` (`type='matcha_compliance'`) flips `enabled_features.compliance=true`; until then `CompliancePendingSidebar` shows the Subscribe CTA.
- Once paid: `ComplianceSidebar` (Compliance, Compliance Calendar, Company, Compliance Setup); `/app/compliance` renders the full `ComplianceFull` view (not the lite taste — `compliance` is true).
- Onboarding **reuses** `MatchaXOnboardingWizard` at `/compliance/onboarding` (locations → policies → people → build).
- Jurisdiction count persists in `company_handbook_profiles.compliance_jurisdiction_count` (migration `compljuris01`); surfaced on `/auth/me` as `profile.jurisdiction_count`.

### Matcha — full bespoke platform
- Companies created with `signup_source='bespoke'` (default) by admins post-sales call, or via `BetaRegister.tsx` invite tokens.
- Sidebar: `ClientSidebar` (Dashboard, Company, HR Ops, Compliance, Communication, Safety, AI groups).
- Routes: `/app/*` registered in `client/src/App.tsx`.
- Backend: everything under `server/app/matcha/` plus `server/app/core/`.
- Per-company access via `companies.enabled_features` JSONB. When a user URL-hops to a feature they don't have, `<FeatureGate>` (`client/src/components/FeatureGate.tsx`) renders `<UpgradeUpsellCard>` instead of a 403.

### Matcha-work — collaborative AI workspace
**Naming convention**: the **web** workspace surface (this section) is referred to as **matcha-work**; the **macOS desktop** workspace is referred to as **werk** (`platforms/desktop/Werk/`). Both share the same backend (`server/app/matcha/routes/matcha_work.py`) and `mw_*` tables — only the client differs. When asked to ship a feature, confirm which surface is meant before editing files.

- Surface: `client/src/pages/work/*` + `client/src/layouts/WorkLayout.tsx`. Mounted at `/work/*` in `App.tsx`.
- Backend: `server/app/matcha/routes/matcha_work.py`, `server/app/matcha/services/project_service.py`. Tables prefixed `mw_*`.
- macOS desktop client (**werk**): `platforms/desktop/Werk/` (SwiftUI). Xcode project name is still `Matcha.xcodeproj` and bundle ID `com.ahnimal.matcha` — App Store identity is unchanged; only the working directory and conceptual product name differ. `AppState.isPlusActive` from `Subscription.isPersonalPlus` controls Plus features.
- **Personal mode**: user `role='individual'`. Signup via `BetaRegister.tsx` (`/auth/beta?token=…`) → redirected to `/work`. Stripe sub `matcha_work_personal` ($20/mo) via `POST /api/checkout/personal` (`server/app/matcha/routes/billing.py`).
- **Business mode**: user `role='client'` inside a Matcha company. Token packs purchased via `POST /api/checkout`. Sidebar entry in `ClientSidebar.tsx` AI group → `/work`.
- Surfaces inside: projects, threads, channels (real-time WebSocket), inbox (DMs), people/connections, anonymous incident report intake.
- Stripe-gated sub-features: `paid_channel_creator`, `channel_job_postings` in `server/app/core/feature_flags.py`.

### Auxiliary surfaces (share codebase, not products)
- **Admin** — `AdminSidebar`, `/admin/*` routes; internal tooling (companies, jurisdiction data, payer data, broker mgmt).
- **Broker** — `BrokerSidebar`, `/broker/*` routes; HR brokers managing multiple client companies.
- **Candidate / Employee portals** — public-token routes (`/candidate-interview/:token`, `/s/:token`); employee self-service through `employee_portal_router`.
- **Public anonymous report** — `/report/:token` (`server/app/matcha/routes/inbound_email.py`); per-company token-gated, reusable form (poster-friendly — not single-use; `/request-info` stays single-use).

## Repo layout — products map

Which frontend pairs with which backend package (don't re-derive this):

| Product | Frontend | Backend | Identity / tables | Domain |
|---|---|---|---|---|
| **Matcha** (Free / Lite / Essentials / X / Compliance / Pro) | `client/` — main SPA (hey-matcha.com) | `server/app/core/` + `server/app/matcha/` at `/api` | `users` + `companies` (`signup_source`, `enabled_features`) | HR compliance, IR/OSHA, ER, employees, broker risk tooling |
| **Matcha-work** (web) | `client/src/pages/work/*` at `/work/*` (+ `/werk`, `/werk-lite` route trees over the same pages) | `server/app/matcha/routes/matcha_work.py` | `mw_*` tables | Collaborative AI workspace |
| **Werk** (macOS) | `platforms/desktop/Werk/` (SwiftUI; project still `Matcha.xcodeproj`) | same matcha-work backend | `mw_*` tables | Desktop surface of matcha-work — confirm which surface (web vs desktop) before editing |
| **Cappe** | inside `client/` — host-routed on gummfit.com (`client/src/utils/cappeHost.ts`, pages in `client/src/pages/cappe/`) | `server/app/cappe/` at `/api/cappe` (+ unprefixed tenant renderer on `*.gummfit.com`) | `cappe_accounts`, JWT `scope=cappe`, `cappe_*` tables (no matcha tenant model) | Website builder + domain reselling |
| **Tell-Us** | `client/tellus/` — separate Vite app (React 19), served by the same frontend nginx at `/tellus/` | `server/app/tellus/` at `/api/tellus` | `tellus_accounts` (consumer + brand), JWT `scope=tellus`, `tellus_*` tables | Rewards-for-feedback |
| **MatchaTutor** (iOS) | `platforms/ios/` (SwiftUI, dormant) | matcha-work language-tutor endpoints | — | Language tutor |
| **Ops agent** | `agent-ui/` (Preact; build copied into `server/agent/static/` by `build-and-push.sh`) | `server/agent/` — standalone service :9100 (not part of `app/`) | — | Internal leads/ops console |

Cross-product import rule: `cappe/` and `tellus/` import only from `app/core/*` (shared db pool, email, storage, auth, redis). One documented exception: `tellus/services/geo.py` reuses `matcha.services.property_cat.geocode` (single US Census geocoder — keep its signature stable).

## Stack

- **Framework**: FastAPI + uvicorn (async)
- **Database**: PostgreSQL via asyncpg (connection pool)
- **Background jobs**: Celery + Redis
- **AI**: Google Gemini via `GEMINI_API_KEY` (native Google AI; Vertex removed)
- **Storage**: S3 + CloudFront (`server/app/core/services/storage.py`)
- **Auth**: JWT
- **Deployment**: AWS EC2 — Nginx reverse proxy + Postgres on dedicated EC2 (acts as RDS, runs directly on host, not Docker).

## Database

**Prod is moving to RDS (2026-06-09, cutover pending).** `matcha-prod` RDS (PG 15.18, encrypted, app VPC) holds a verified clone of prod; the app EC2 still points at the old `:5433` container until `DATABASE_URL` is flipped there. All DBs use name `matcha`, user `matcha`. Full workflow + scripts in `docs/ops/DB_WORKFLOW.md`.

| Instance | Where | Role | Who connects |
|---|---|---|---|
| `matcha-prod` RDS | `matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com:5432` (app VPC) | **PROD** (post-cutover) | app EC2 only (SG-locked); laptop via app-EC2 tunnel → `localhost:5434`. `rds.force_ssl=1` → `sslmode=require` |
| `matcha-postgres-prod` container | DB EC2 `3.101.83.217` `:5433` | **PROD until cutover**, frozen after | app EC2; hey-matcha.com |
| `matcha-postgres` container | DB EC2 `3.101.83.217` `:5432` | **DEV** (+ 8 other apps' DBs) | laptop via `dev-remote.sh` SSH tunnel |

**⚠️ Treat both the RDS instance and `matcha-postgres-prod` (:5433) as live production.** Local dev (`dev-remote.sh`, `DATABASE_URL`) connects to the **dev** container (:5432). The DB EC2 is a **different VPC** and cannot route to RDS — everything that reaches RDS goes through the app EC2 (`54.177.107.107`); laptop tools use an SSH tunnel on `localhost:5434` (`PROD_DATABASE_URL` in `server/.env`; old container kept as `PROD_LEGACY_DATABASE_URL`).

**NEVER do the following without explicit user approval — especially against prod (RDS or :5433):**
- CREATE ROLE / DROP ROLE
- CREATE TABLE / DROP TABLE on real tables
- `alembic upgrade head` against prod
- Any DDL (ALTER TABLE, CREATE INDEX, etc.) directly
- Tests that create/drop/alter tables, roles, or schema on a live DB
- Assume you can freely experiment with either DB

**For integration tests that need DB access:** write them to be run manually by the user, use reserved-domain test data, never auto-run DB-mutating tests.

### Schema + data flow — keep dev and prod in sync (both directions)

Schema is managed via Alembic migrations in `server/alembic/versions/`; `server/app/database.py:init_db()` only bootstraps a fresh DB (it does **not** run migrations). The two DBs drift unless synced deliberately:

- **Schema, dev → prod:** author migration → `./scripts/migrate-dev.sh` (applies to dev :5432) → test → `./scripts/migrate-prod.sh` (applies the same revision to RDS prod via app-EC2 tunnel; `--legacy` targets the old :5433 container — pre-cutover a live-prod migration needs **both**). Applying to only one DB is the drift that caused real `UndefinedColumnError` 500s. `alembic_version` must match afterward.
- **Data, prod → dev:** `./scripts/refresh-dev-from-prod.sh` — **anonymized** clone of RDS prod into dev (dump on app EC2, streamed via laptop to the DB EC2; `--legacy-source` clones the old :5433 container host-side instead). `--dry-run` previews into a staging DB without swapping. After a scrubbed run, **every dev user's password becomes `devpass123`**; PII is scrubbed by `scripts/sql/anonymize_dev.sql`.
- **Anonymization gate — currently OFF (pre-customer).** `SKIP_ANONYMIZE=1` in `server/.env` makes the refresh clone prod → dev **verbatim** (real emails + passwords, every account logs in) — fine while there's no customer PII. **Turn it back ON the moment real customers exist:** delete/unset `SKIP_ANONYMIZE` in `server/.env` (default = on/scrubbed), then re-run `./scripts/refresh-dev-from-prod.sh` — dev re-anonymizes. To keep *your own* logins working after re-enabling, list them in `DEV_PRESERVE_EMAILS` (comma-sep, env or `server/.env`) — those keep real email + password while everyone else is scrubbed. Details in `docs/ops/DB_WORKFLOW.md`.
- **Backups:** host cron `~/backup-to-s3.sh` (every 12h) → `s3://matcha-recruit-backups/postgres/` (SSE-AES256); inspect/restore via `./scripts/backups.sh`.

**SSH:** `ssh -i secrets/roonMT-arm.pem ec2-user@3.101.83.217` (DB host) · `ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107` (app host).

## Directory Structure

```
server/
├── run.py                          # Entry point (uvicorn)
├── app/
│   ├── main.py                     # App init, router mounting, lifespan
│   ├── config.py                   # Pydantic settings from env
│   ├── database.py                 # asyncpg pool + init_db()
│   ├── dependencies.py             # Shared auth dependencies
│   ├── protocol.py                 # AI WS / streaming protocol shapes
│   ├── core/                       # Auth, admin, compliance, AI chat, policies, resources
│   │   ├── models/
│   │   ├── routes/
│   │   └── services/
│   ├── matcha/                     # Recruiting + HR domain (incl. matcha-work)
│   │   ├── models/
│   │   ├── routes/                 # Router zoo — see routes/CLAUDE.md
│   │   │   ├── ir_incidents/       # Package (split 2026-05-16) — see ir_incidents/CLAUDE.md
│   │   │   ├── employees/          # 13-file package (split 2026-05-16) — see employees/CLAUDE.md
│   │   │   ├── er_copilot.py       # 4,111 lines (split candidate)
│   │   │   ├── matcha_work.py      # 8,902 lines (cohesive — not a split candidate)
│   │   │   └── … 25 others
│   │   ├── services/
│   │   └── workers/
│   ├── workers/                    # Celery app + scheduled tasks
│   ├── orm/                        # SQLAlchemy helpers (limited use)
│   └── uploads/                    # Local-only upload temp dir
├── tests/
└── alembic/

client/src/
├── api/                            # API client layer (client.ts, chatClient.ts, etc.)
├── components/                     # Shared + product-specific UI
│   ├── ClientSidebar.tsx           # Full Matcha platform sidebar
│   ├── TenantSidebar.tsx           # Dispatcher → ClientSidebar / IrSidebar / ResourcesFreeSidebar
│   ├── AdminSidebar.tsx, BrokerSidebar.tsx
│   ├── FeatureGate.tsx, UpgradeUpsellCard.tsx
│   ├── ir-only/                    # IrSidebar + lite-tier shells
│   ├── resources-free/             # Free-tier sidebar + upgrade panel
│   ├── channels/, inbox/, work/    # Matcha-work surfaces
│   ├── ir/, er/, compliance/, employees/, dashboard/, handbook/, …
│   └── ui/                         # Generic primitives (Button, Input, …)
├── features/                       # Feature-based modules
│   ├── discipline/
│   └── ir-onboarding/
├── hooks/                          # Domain-specific hooks
│   ├── compliance/, discipline/, employees/, er/, ir/, risk-assessment/
│   └── single-file utilities (useMe, useChannelNotifications, useSidebarBadges, …)
├── layouts/                        # WorkLayout, etc.
├── pages/                          # Route-level pages
│   ├── admin/, app/, auth/, broker/, landing/, shared/, work/
│   └── BetaRegister.tsx, Login.tsx, Landing.tsx, ResetPassword.tsx, SSOCallback.tsx
├── types/                          # Shared TypeScript types
├── utils/                          # Pure utilities (incl. tier.ts)
├── data/                           # Static / seed data
└── generated/                      # Auto-generated types (do not edit)
```

## Frontend ↔ Backend Connection

**API base URL**: `VITE_API_URL` env var, falls back to `/api` (proxied in dev via Vite).

**Auth flow**:
1. Login/register POSTs to `/api/auth/*` → returns `access_token` + `refresh_token`
2. Tokens stored in `localStorage` as `matcha_access_token` / `matcha_refresh_token`
3. All requests attach `Authorization: Bearer <access_token>` header
4. On 401, `client/src/api/client.ts` automatically refreshes via `/api/auth/refresh` and retries
5. Auth state lives in `client/src/hooks/useMe.ts` — exposes `user`, `hasRole()`, `hasFeature()`, `companyFeatures`

**WebSocket**: Chat / channels / matcha-work AI streams use WebSocket — handled in `api/chatClient.ts` and `Services/ChannelsWebSocket.swift` (desktop). Same JWT as HTTP.

## User Roles

Defined in `server/app/core/models/auth.py:7`:

| Role | Description |
|---|---|
| `admin` | Platform admin, full access |
| `client` | Business user (linked to a company) — "business admin" |
| `candidate` | Job seeker |
| `employee` | Company employee (HR portal) |
| `broker` | HR broker managing multiple client companies |
| `creator` | Matcha-work creator role (channel ownership) |
| `agency` | Agency tenant role |
| `individual` | Personal Matcha-work user (no company) |
| `gumfit_admin` | Legacy, dead — references a discontinued sister product |

**Auth dependencies** are split across two files:
- `server/app/core/dependencies.py` — `require_admin`, `require_candidate`
- `server/app/matcha/dependencies.py` — `require_client`, `require_employee`, `require_admin_or_client`

**Company approval flow**: Business registers → `status='pending'` → admin approves → features enabled. `status IS NULL` is treated as approved for legacy rows.

## Feature Flags

Defined in `server/app/core/feature_flags.py` as `DEFAULT_COMPANY_FEATURES`. Per-company overrides live in `companies.enabled_features` JSONB; `merge_company_features()` overlays them on top of these defaults.

| Flag | Default | Purpose |
|---|---|---|
| `handbooks` | ✅ | Employee handbook **generator** (Lite keeps this) |
| `handbook_audit` | ❌ | Handbook **audit** / gap analyzer as an in-app feature — distinct from `handbooks`. Matcha-X + Pro only (granted via X tier overlay + stored on bespoke signup). The public lead-gen analyzer is unaffected: `handbook_gap_analyzer._resolve_caller_tier` reads this flag to decide teaser (free/Lite) vs full report+PDF (X/Pro). |
| `accommodations` | ✅ | Accommodation case mgmt |
| `risk_assessment` | ✅ | Risk-assessment dashboard |
| `discipline` | ✅ | Progressive discipline workflow |
| `matcha_work` | ❌ | Projects / threads / channels |
| `training` | ❌ | Training programs |
| `i9` | ❌ | I-9 compliance |
| `cobra` | ❌ | COBRA admin |
| `separation_agreements` | ❌ | Separation doc workflow |
| `credential_templates` | ❌ | Credentialing / license tracking. Default-off, but in the **Matcha-X** bundle (tier overlay) and **Pro** (stored on bespoke signup). |
| `compliance` | ❌ | Full Compliance feature. The self-serve **paid gate** for the standalone **Matcha Compliance** product (flipped on by the Stripe webhook; `signup_source='matcha_compliance'`), and the **Pro** power-tools flag (stored at bespoke signup — live re-research, alerts/action-plans, AI ask, wage-violations, payer policies). Default-off so `require_feature("compliance")` is well-defined for every company; **NOT** in any tier overlay (a paid gate flipped by payment, like `incidents`). |
| `compliance_lite` | ❌ | **Read-only** "taste" of Compliance for **Matcha-X** (tier overlay). Surfaces the per-location requirements + jurisdiction stack + summary + upcoming-legislation the onboarding build wrote; Pro power-tools render locked. Distinct from full `compliance` (Pro, stored at bespoke signup — live re-research, alerts/action-plans, AI ask, wage-violations, payer policies). Gating: read-only GETs moved to `compliance.py:shared_router`, mounted under `require_any_feature("compliance","compliance_lite")`; all mutating/power endpoints stay on the `compliance`-gated `router`. FE reuses `pages/app/Compliance.tsx` tier-shaped by `isLite` + `<FeatureGate anyOf={['compliance','compliance_lite']}>`. |
| `hris_import` | ❌ | HRIS sync — legacy umbrella; gates treat it as "both providers" |
| `hris_gusto` | ❌ | HRIS via Gusto OAuth (direct) |
| `hris_finch` | ❌ | HRIS via Finch unified API (Rippling, BambooHR, ADP, …) |
| `hris_deductions` | ❌ | Deductions/benefits **write**-back via Finch — requests the `benefits` product at connect; gates `/provisioning/hris/benefits` (provider must support it) |
| `paid_channel_creator` | ❌ | Stripe-gated paid channels |
| `channel_job_postings` | ❌ | Stripe-gated job postings in channels |
| `benefits_admin` | ❌ | Employee-benefits broker tooling — source-agnostic roster ingest (Finch + CSV), eligibility-exception detection (new-hire gaps + termination premium leaks), renewal-risk radar. Gates company-facing `/benefits/*`; broker rollups live under `/broker/benefits/*` (broker-role gated). Daily Celery `benefit_eligibility_sync` (scheduler row, default off). |
| `werk_lite` | ❌ | **Werk Lite** — standalone business work-chat surface at `/werk-lite` with its **own login** (`/werk-lite/login` → same `/api/auth/login`, lands all roles on `/werk-lite`; `WerkLiteAuthGuard` redirects unauthenticated there, not the main `/login`). Channel chat + LiveKit audio/video calls + collaborative kanban boards only (Slack/Teams-style). **Whole-company** access, not admin-only: business admins (`role='client'`) AND employees (`role='employee'`) — `/auth/me` carries `enabled_features` for both. Boards are matcha-work projects, so the kanban backend needs `matcha_work` too — a Werk-Lite company needs **both** `werk_lite` + `matcha_work`. Employee board access is via the new `require_company_member` dep on the project view + task/subtask routes (company-scoped); board *creation*/rename stays admin/client. Entry: `<FeatureGate flag="werk_lite">` + a `ClientSidebar` AI-group entry (admins). Not in any tier overlay. |
| `werk_lite_calls_all_members` | ❌ | Werk Lite call-start policy. `false` = only admins/business-admins start calls; `true` = any channel member starts. Joining is always open to members. Only consulted for `werk_lite` companies, in `channel_calls.start_call` (which also skips the per-user Werk Pro gate for werk-lite). |
| `workforce_compliance` | ❌ | Business-first employment-practices risk trackers — per-state **pay-transparency** posting compliance, **AI hiring-tool bias-audit** register (cadence/overdue), **biometric/BIPA** consent inventory, and a **pay-equity study** register (cadence/overdue). Gates `/workforce-compliance/*` + the `/app/workforce-compliance` page. Each is a legal obligation the tenant tracks for itself; together they flip the broker EPL factors (`pay_transparency`/`ai_hiring_audit`/`biometrics_bipa`/`pay_equity`) from attested → derived in `epl_readiness.compute_epl_readiness`. Default off; admin-toggle; NOT in any tier overlay. |
| `risk_profile` | ❌ | **Client-facing risk portal** — the business's own composite **risk index** (0–100, WC + EPL + compliance weighted roll-up via `services/risk_index.py`) + component breakdown + top fixes. Gates `/risk-profile` + the `/app/risk-profile` page. Same engine the broker sees at `/broker/risk-index[/{id}]` (broker-role gated, no flag). Also serves the **submission-readiness** score (`services/submission_readiness.py`, `GET /risk-profile/readiness`) — a data→underwriter-ready *completeness* checklist (distinct from risk quality: "finish these N items → tighter terms"); the broker submission packet PDF carries the same readiness banner. No new tables. Default off; admin-toggle; NOT bundled. |
| `resident_care` | ❌ | **Healthcare/senior-living resident-care risk asset** — safety-program register (fall-prevention/infection-control/abuse-prevention/…), MVR-review tracking (hire + annual), credentialing currency, and an insurer-facing asset PDF. Gates `/resident-care/*` + the `/app/resident-care` page. Default off; admin-toggle (vertical); NOT bundled. |
| `controls_evidence` | ❌ | **Universal "Proof of Controls" register + underwriter packet** (WTW p.85). Auto-compiles 8 risk controls from data already held — anti-harassment policy+signatures, training, discipline, ER cases, multi-state wage-hour (reusing `epl_readiness.compute_epl_readiness` factors), plus IR/OSHA incident-response, credentialing currency, and safety programs — and lets the company verify/annotate each (`company_control_evidence`, migration `ctrlev01`) and export a Proof-of-Controls PDF (`services/controls_evidence.py`). Gates `/controls-evidence/*` + the `/app/controls-evidence` page. Broker side **extends the submission PDF** with a controls section + `GET /broker/clients/{id}/controls.pdf|controls-evidence` (broker-role gated). Generalizes `resident_care` to any employer; does NOT replace it (safety_programs is one shared control). Default off; admin-toggle; NOT bundled. |
| `limit_adequacy` | ❌ | **Limit-adequacy + contract review** (gap-analysis #6/#28; WTW "benchmarking + contractual-limit review = essential tool"). Company records the limits it carries (`company_coverage_lines`) + uploads customer/vendor/lease contracts whose insurance requirements Gemini extracts (`services/contract_parser.py`, PDF parsed-and-discarded → `company_contracts.requirements` JSONB), and the engine (`services/limit_adequacy.py`) diffs them per casualty line → **hard** grounded gaps ("carry $1M GL, a contract requires $2M") + a directional size/venue **baseline** (not a peer benchmark — we don't have peer-limit data) + endorsement-gap flags (AI/WOS/P&NC). Migration `limadq01`. Gates `/limit-adequacy/*` + the `/app/limit-adequacy` page. Broker side **extends the submission PDF** with a limit section + `GET /broker/clients/{id}/limits.pdf|limit-adequacy` (broker-role gated). Default off; admin-toggle; NOT bundled. |
| `driver_risk` | ❌ | **Driver-risk / fleet MVR scoring** (gap-analysis #15; commercial-auto entry). Generalizes MVR tracking off the healthcare-only `resident_care` vertical to any employer with drivers — scores each driver clean/marginal/high-risk from employer-recorded MVR data (license status, moving violations, at-fault accidents, major violations) → a fleet grade (A–D) + insurer PDF (`services/driver_risk.py`). **Reuses** the `mvr_reviews` table (migration `driverrisk01` adds scoring columns; `resident_care` keeps its currency view on the same rows — not duplicated). Gates `/driver-risk/*` + the `/app/driver-risk` page. Directional (employer-entered MVR, not a pulled motor-vehicle record). Default off; admin-toggle; NOT bundled. |
| `property` | ❌ | **Commercial property (P-side)** — the property analog of the casualty stack. Tenant **Statement of Values** (`company_property_buildings`, migration `prop01`): per-building COPE (construction/occupancy/protection/exposure) + values (building/contents/BI/replacement/insured) → **TIV**, **insurance-to-value (ITV)**, and a **COPE grade** (`services/property_sov.py`). Property **limits** ride the limit-adequacy engine (`line='property'`) and property **loss runs** ride loss-development (same `line`) — the 4 line whitelists widened, no new line tables. A **property component** plugs into the composite `risk_index`. **Geocoded catastrophe** (`property_building_perils` + `coastal_wind_tier`): per-building flood (FEMA NFHL) / quake (USGS) / wildfire (USFS) / wind tiers via a best-effort Celery task (`property_cat_refresh`, scheduler-gated). Broker parity: `/broker/property-portfolio`, off-platform `broker_external_property` snapshot, and a submission-packet property section. Gates `/property/*` + the `/app/property` page (+ broker property surfaces). Default off; admin-toggle; NOT bundled. |
| `ir_voice_intake` | ❌ | **Voice dictation on the IR create form** (all IR products — shared `IRCreateIncidentModal`). Optional "Dictate" button: the reporter records a spoken account → one Gemini multimodal call transcribes + extracts the form fields (`services/ir_voice_parser.py`) → prefills description / reporter / date / location / witnesses + a suggested type/severity hint, which the user **reviews and edits before submitting** (never auto-creates — it's a legal record). Audio captured as WAV via the existing PCM AudioWorklet (Gemini rejects `MediaRecorder` webm/opus). Gates `POST /ir/incidents/voice/parse` (2-segment, stacks on the `incidents` gate) + the button (`hasFeature('ir_voice_intake')`). Default off; admin-toggle; NOT bundled. |
| `handbook_watch` | ❌ | **Scheduled handbook-freshness monitoring** ("handbook watch") — the paid, automated tier of the freshness stack. Gates ONLY the per-company sweep in the `handbook_freshness` Celery worker + its alert emails (worker SQL filters on the stored flag; the global `scheduler_settings['handbook_freshness']` row remains the kill-switch). The manual `POST /handbooks/{id}/freshness-check` stays free with `handbooks`; findings render in the existing `HandbookFreshnessPanel`. Sold as a **Lite-family add-on** (own Stripe sub, `matcha_lite_addon` checkout — see `services/lite_addons.py`); available to both `matcha_lite` and `matcha_lite_essentials`. A paid gate like `incidents`, so NOT in any tier overlay (merged == stored). Default off; admin-toggle. |
| `legal_defense` | ❌ | **Legal Pilot builder** (full Matcha / Pro). An admin opens a **legal matter** (subpoena / class action / EEOC / single-plaintiff / audit), then converses with a **grounded** AI that pulls the company's own records across every enabled subsystem — IR/OSHA, ER cases, compliance, discipline, training, handbooks/policy-signatures, accommodations + the immutable `*_audit_log` trails — and maps them to the defense theory. Exports an **attorney-facing evidence packet**: a defense-memo PDF that **cites only real records** (anti-hallucination gate: `validate_citations` drops any cited ID not in the retrieved corpus; the appendix is rendered deterministically from DB rows, reusing `claims_readiness` IR/ER builders) **+ a ZIP bundle** of the underlying source documents (fetched from S3 via `storage.download_file`, with a `manifest.txt` of any skipped). Multi-turn chat is SSE-streamed; matters + transcript + packets persist (`legal_matters` / `legal_matter_messages` / `legal_matter_packets`, migration `legaldef01`). Read-only over evidence; every generation/download is audit-logged (`legal_matter_audit_log`). Gates `/legal-pilot/*` + the `/app/legal-pilot` page (routes renamed from `legal-defense` → `legal-pilot`; flag name `legal_defense` and `legal_matter*` tables kept as-is). Default off; admin-toggle; NOT bundled. |
| `osha_logs` | ✅ | OSHA 300/301/300A logs within IR (`ir_incidents/osha.py`). Default on (existing behavior, unchanged) — forced **off** for the no-roster `matcha_lite_essentials` config (no employee roster to log injured persons against). Gates the osha.py sub-router (additional gate stacked on top of `incidents` at the `ir_incidents/__init__.py` include, not the parent mount) + the `/app/ir/osha` page + the OSHA Logs sidebar entry. |

`incidents` and `employees` are not in the defaults — they're flipped on by tier-specific flows (Matcha-lite Stripe webhook, IR-only signup) or admin toggle.

**Tier bundles** (read-time via `TIER_REQUIRED_FEATURES` overlay in `feature_flags.py`, except Pro which stores at signup):
- **Lite** (`matcha_lite`) = `incidents` (paid) + `employees` + `handbooks` (generation). `training`/`discipline` force-asserted **off** here; no `handbook_audit`/`credential_templates`.
- **Lite Essentials** (`matcha_lite_essentials`) = a signup-time choice on the *same* `/lite/signup` page/checkout as standard Lite (not a separate product/route) — `incidents` (paid) + `handbooks`, but `employees` and `osha_logs` force-asserted **off** (no employee roster: no CSV/HRIS import, no roster picker on the incident form, no OSHA 300 logs — reporter/witness capture still works via the no-roster `ir_people` index). Priced as its own row in `matcha_lite_pricing` (`product_code='matcha_lite_essentials'`), cheaper than standard Lite. Chosen via a checkbox on `MatchaLiteSignup.tsx` → `lite_essentials` on the registration request → routes to this signup_source instead of `matcha_lite`.
- **Matcha-X** (`matcha_x`) = Lite + `training` + `discipline` + `handbook_audit` + `credential_templates` + `compliance_lite` (read-only Compliance taste) — all forced on via overlay.
- **Pro** (`bespoke`/`invite`/`broker`) = full `DEFAULT_COMPANY_FEATURES` + `incidents` + `handbook_audit` + `credential_templates`, stored at signup (toggleable per-company; not an overlay, so it doesn't leak to personal Werk which shares `signup_source='bespoke'`).
- **Matcha Compliance** (`matcha_compliance`) = full `compliance` only, nothing else bundled. `compliance` is **not** in any overlay — it's the Stripe-gated paid flag (flipped by `checkout.session.completed`), exactly like `incidents` gates Lite/X. Onboarding reuses `MatchaXOnboardingWizard`.

## Key Modules

- **Compliance** (`core/services/compliance_service.py`) — Jurisdiction-aware compliance checking with Gemini AI; preemption rules, tiered data (structured → repository → Gemini research).
- **AI Chat** (`core/services/ai_chat.py`) — WebSocket chat with local Qwen model or Gemini.
- **Matcha Work** (`matcha/routes/matcha_work.py` + `services/project_service.py`, `services/matcha_work_ai.py`) — projects, threads, channels, inbox, AI directives.
- **Channels** (`matcha/services/channels_service.py`, `mw_channels*` tables) — real-time WebSocket messaging, paid channels, member presence.
- **IR Incidents** (`matcha/routes/ir_incidents/` — 10-file package since 2026-05-16; see `ir_incidents/CLAUDE.md`) — safety/behavioral incident reporting + AI analysis. Public anonymous intake at `routes/inbound_email.py`.
- **Discipline** (`matcha/routes/discipline.py` + `services/discipline_engine.py`, signature provider abstraction in `services/signature_provider.py`).
- **ER Copilot** (`matcha/routes/er_copilot.py`) — employment-relations case mgmt.
- **Risk Assessment** (`matcha/routes/risk_assessment.py`).
- **Interviews** (`matcha/services/`) — voice interviews via Gemini Live API.

## Background Workers (Celery)

Celery worker container `matcha-worker` runs everything that can't run inline. Single concurrency, restarts after 5 tasks (`--max-tasks-per-child=5`) to recycle memory. `task_acks_late=True` + `max_retries=3` so OOM-killed tasks retry.

Scheduling model: no celery-beat. The worker container runs continuously (`restart: unless-stopped`); an hourly host cron (`docker restart matcha-worker`) re-fires `@worker_ready` in `app/workers/celery_app.py`, which re-dispatches the periodic tasks on startup. Each scheduled task is gated by a `scheduler_settings` row, defaulting to disabled. (The old `matcha-worker.timer` 15-min duty-cycle units still exist in `~/matcha/deploy/` on the app EC2 but are disabled — the continuous worker serves ad-hoc tasks with no queue latency.)

**Periodic / scheduled** (`app/workers/tasks/`):
- `compliance_checks` — per-location Gemini scans
- `compliance_action_reminders` — nudges for open requirements
- `legislation_watch` — Gemini-grounded legislation deltas
- `leave_deadline_checks`, `leave_agent_orchestration` — leave-of-absence tracking
- `onboarding_reminders` — new-hire task chases
- `discipline_expiry` — auto-close stale discipline records
- `handbook_freshness` — re-evaluate handbooks against current law
- `pattern_recognition` — cross-incident analysis
- `auto_archive` — close-out abandoned projects
- `newsletter_scheduler` — periodic digest send
- `structured_data_fetch` — pull authoritative regulator feeds

**Heavy ad-hoc** (dispatched from routes):
- `healthcare_research`, `oncology_research`, `medical_compliance_research` — deep Gemini research jobs (memory-heavy bursts)
- `er_analysis` (5 tasks) — incident pattern + risk inference
- `er_document_processing` — DOC/PDF parsing
- `risk_assessment` — quantitative analysis runs
- `interview_analysis` — post-call transcript scoring

**Stays inline in FastAPI (NOT on worker)**: WebSocket chat streams, voice interview WS (Gemini Live), PDF render via WeasyPrint (`asyncio.to_thread` in `routes/matcha_work.py`), all CRUD, Stripe webhooks, auth.

PDF render is intentionally inline because the desktop client awaits the bytes — but it is the dominant memory consumer in the backend container. If backend memory pressure recurs, moving `_render_project_pdf` to a celery task and `.get(timeout=60)` is the obvious next step.

## Host nginx on the app EC2 (deploy/nginx/)

Host-level nginx server blocks on the app EC2 (`/etc/nginx/conf.d/`) are hand-managed; the repo source of truth is `deploy/nginx/` (`matcha.conf`, `cappe.conf` — apply via scp per `deploy/nginx/README.md`, they are NOT touched by `build-and-push.sh`/`update-ec2.sh`).

**Blue-green rule (critical):** deploys alternate frontend `8082↔8083` / backend `8002↔8003` and **remove the old container**. Every server block must `proxy_pass` to the `matcha_frontend` / `matcha_backend` upstream groups (defined in `matcha.conf`; active port written to `/etc/nginx/upstream/matcha-*-active.conf` by the deploy scripts) — **never hardcode a port**. A hardcoded `:8082` in `cappe.conf` is how gummfit.com 502'd to the maintenance page after a swap (fixed 2026-07-02).

Retired/backup configs go to `/etc/nginx/conf.d/archive/` (nginx only globs `*.conf`). Legacy `oceaneca.conf` was retired there 2026-07-01 — `gummfit.com` belongs to `cappe.conf` (Cappe); if oceaneca.com ever revives, restore from archive minus its gummfit.com server blocks.

**Primary script**: `./scripts/dev-remote.sh` — SSH-tunnels the **dev** Postgres container from EC2 (`3.101.83.217:5432` → `matcha-postgres`, not prod), starts Redis tunnel, backend on `:8001`, frontend on `:5174`, local chat model on `:8080`. Requires `secrets/roonMT-arm.pem`. To sync dev/prod see the Database section + `docs/ops/DB_WORKFLOW.md`.

**⚠️ `dev-remote.sh`'s frontend runs on `:5174` (tmux session `matcha-dev-remote`) — it is almost always already running.** If you spin up your own throwaway `npm run dev` (e.g. to screenshot-verify a change), do NOT clean it up with a port-pattern `pkill -f "vite --port ..."` — that regex also matches the user's real dev-remote.sh frontend process (same command line) and kills it. Track your own process by PID (`$!` / a pidfile) and `kill` that PID specifically instead.

**Alternative**: `./scripts/dev.sh` — references a discontinued sister product; do not use.

```bash
# Server only (assumes DB tunnel open):
cd server && python3 run.py     # :8001

# Tests
cd server && python3 -m pytest tests/ -v
```

## Code Modification Rules

- Before modifying any function, component, or class, you MUST identify and read all files that import or depend on it.
- If a task involves data fetching, database schemas, or global state, you are required to load the entire schema and all relevant model files into your context *before* proposing or executing changes.

## Test Data — Email Domains (CRITICAL)

NEVER invent realistic-looking fake email domains for test data (e.g. `@medcenter.com`, `@acmecorp.io`, `@somehospital.org`). These resolve in DNS, Gmail attempts delivery, and bounce-storms flood the sender mailbox for 48 hours.

ALWAYS use RFC 2606 / RFC 6761 reserved domains — guaranteed non-deliverable:

- `@example.com`, `@example.org`, `@example.net`
- `@<anything>.test` (e.g. `@acme.test`, `@hospital.test`)
- `@<anything>.invalid`
- `@<anything>.localhost`

Examples:
- `jane.doe@example.com` ✅
- `nurse1@hospital.test` ✅
- `admin@matcha.invalid` ✅
- `jane.doe@medcenter.com` ❌ (real-looking, real bounces)

This applies anywhere test data is generated: seed scripts, CSV templates, fixture files, mock data, demo employees, README examples, anything Claude writes into the codebase or types into the live UI.

The server (`server/app/core/services/email.py`) hard-blocks sends to these reserved domains as a defense-in-depth guard, but the rule above is the primary mitigation — don't invent realistic fake domains in the first place.

## Symbol Map — Where Things Live

Quick lookup for frequently-touched code. Saves grepping the same things repeatedly. Format: `description → file_path:symbol`.

### Auth + identity

- JWT auth flow + token refresh → `client/src/api/client.ts`
- User state + role/feature checks → `client/src/hooks/useMe.ts` (`useMe()`, `hasRole()`, `hasFeature()`)
- Backend auth deps → `server/app/core/dependencies.py` (`require_admin`, `require_candidate`) + `server/app/matcha/dependencies.py` (`require_client`, `require_employee`, `require_admin_or_client`, `get_client_company_id`)
- Public-token interview WS auth → `server/app/core/services/auth.py:create_interview_ws_token`
- Tier helpers → `client/src/utils/tier.ts` (`isIrOnlyTier`, `isMatchaLitePending`, `isResourcesFreeTier`)
- Sidebar dispatch (the only place that picks shell) → `client/src/components/TenantSidebar.tsx`

### Email + notifications

- Email service (Gmail API + MailerSend) → `server/app/core/services/email.py` (`EmailService`, `get_email_service()`)
- Reserved-domain guard (blocks `@example.com` / `*.test` / `*.invalid`) → `server/app/core/services/email.py:_is_reserved_test_domain`
- Employee invitation send → `server/app/core/services/email.py:send_employee_invitation_email` (callsite: `server/app/matcha/routes/employees/_shared.py:_send_invitation_with_conn`)
- IR lifecycle notifications → `server/app/matcha/routes/ir_incidents/_shared.py:send_ir_notifications_task`
- Onboarding reminder cron → `server/app/workers/tasks/onboarding_reminders.py`

### Feature gating + tiers

- Backend default flags → `server/app/core/feature_flags.py:DEFAULT_COMPANY_FEATURES`
- Backend feature dep → `server/app/matcha/dependencies.py:require_feature`
- Frontend gate → `client/src/components/FeatureGate.tsx` (renders `<UpgradeUpsellCard>` instead of 403)
- Upgrade upsell card → `client/src/components/UpgradeUpsellCard.tsx`

### IR (Incident Reporting)

- Backend package overview → `server/app/matcha/routes/ir_incidents/CLAUDE.md`
- IR orchestrator (Gemini prompt + intent detection) → `server/app/matcha/services/ir_ai_orchestrator.py:generate_guidance`
- IR Copilot panel (frontend) → `client/src/components/ir/IRCopilotPanel.tsx`
- IR Copilot card schema → `client/src/components/ir/IRCopilotCard.tsx:5` (`CopilotCardAction.type` union)
- IR Copilot close-incident helper (server) → `server/app/matcha/routes/ir_incidents/copilot.py:_close_incident_via_copilot`
- IR analysis runners (categorize / severity / root-cause / etc.) → `server/app/matcha/routes/ir_incidents/ai_analysis.py`
- Policy mapping helpers → `server/app/matcha/routes/ir_incidents/ai_analysis.py:_auto_map_policy_violations` + `_get_handbook_policy_entries`
- Anonymous IR intake → `server/app/matcha/routes/inbound_email.py` (public `/report/:token` endpoint)
- Anonymous report token mgmt → `server/app/matcha/routes/ir_incidents/anonymous_reporting.py`
- IR detail page → `client/src/pages/app/IRDetail.tsx`
- Security survey question bank → `client/src/components/ir/data/security_survey_questions.ts` (IDs are persisted in `ir_surveys.responses` JSONB — keep stable)

### Employees

- Employee CRUD → `server/app/matcha/routes/employees/crud.py` (10 routes; package split 2026-05-16 — see `server/app/matcha/routes/employees/CLAUDE.md`)
- Bulk CSV upload → `server/app/matcha/routes/employees/bulk_upload.py:bulk_upload_employees_csv`
- Send invitation → `server/app/matcha/routes/employees/_shared.py:_send_invitation_with_conn` (callable from single + bulk + multi-batch paths)
- Auto-invitation toggle (per-company setting) → `onboarding_notification_settings.auto_send_invitation` column
- Bulk upload modal (frontend) → `client/src/components/employees/BulkUploadModal.tsx`
- Multi-batch add modal (frontend) → `client/src/components/employees/MultiBatchModal.tsx`

### Billing + Stripe

- Stripe checkout endpoints → `server/app/core/routes/resources.py` (matcha-lite: `POST /resources/checkout/lite` + `/compliance` + `/lite-addon` + `/lite-upgrade`) + `server/app/matcha/routes/billing.py` (matcha-work)
- Stripe webhook handler → `server/app/core/routes/stripe_webhook.py:stripe_webhook` mounted at `POST /api/webhooks/stripe` (NOT billing.py). Routes on `event_type` + `metadata.type`; `checkout.session.completed` w/ `type='matcha_lite'` flips `enabled_features.incidents=true`; `customer.subscription.deleted` flips it back. Top-level dedupe via `stripe_webhook_events` (fail-closed).
- Personal Matcha-work checkout → `server/app/matcha/routes/billing.py:POST /api/checkout/personal`
- Token packs → `server/app/matcha/routes/billing.py:POST /api/checkout`
- Lite checkout redirect is **URL-based** — backend returns `checkout_url`, FE does `window.location.href = checkout_url` (`TenantSidebar.tsx`); **no `loadStripe`/publishable key/`redirectToCheckout` anywhere**, so swapping Stripe keys needs no frontend rebuild. Lite pricing = DB table `matcha_lite_pricing` (`services/matcha_lite_pricing.py`, admin-configurable; code fallback `$50/block-of-10`, min 1/max 300).

**Prod Stripe config (keys, accounts, mode) — non-obvious:**
- Prod Stripe keys live in **`~/matcha/.env.backend` on the app EC2** (`54.177.107.107`), read at container start via `docker run --env-file .env.backend`. NOT in the repo, NOT in AWS Secrets Manager (the `AWS_SECRETS_MANAGER_SECRET_ID` path in `config.py:load_settings` exists but is unused — prod uses the plain `.env.backend`). Local dev keys are in `server/.env`.
- **No deploy script overwrites `.env.backend`** — `update-ec2.sh` only scps `docker-compose.yml` + runs `deploy-backend-bluegreen.sh` (which pulls `:latest` and `--env-file`s the host `.env.backend`). So a host-side key edit **persists across `build-and-push.sh` + `update-ec2.sh`**. To reload env without shipping new code, recreate the backend container pinned to its current image id (skip `docker pull`) — the bluegreen script always pulls `:latest`.
- **Two Stripe accounts** (keys are per-account): dev/local = **Matcha Technologies LLC** (`acct_1S2GdG…`), prod historically = **Ahnimal** (`acct_1QcZE2…`, the legacy/discontinued sister product). As of 2026-07-04 prod `.env.backend` was switched to **Matcha Technologies LLC test-mode** keys (backup of the old Ahnimal keys at `~/matcha/.env.backend.bak.ahnimal-*`). Test webhook endpoint in the Matcha-Tech account → `https://hey-matcha.com/api/webhooks/stripe` (events: `checkout.session.completed`, `customer.subscription.deleted`, `invoice.paid`, `checkout.session.expired`).
- **Prod is in Stripe TEST mode** (pre-customer) — real cards are rejected. **Before go-live:** put Matcha-Tech **live** keys in `.env.backend` + register a **live** webhook endpoint (different `whsec_`) in the Matcha-Tech live dashboard, then recreate the backend. Test/live keys + webhook endpoints are per-mode and must be swapped as a matched pair (secret key + webhook secret + endpoint) or activation webhooks fail signature.

### Compliance + jurisdictions

- Compliance check service → `server/app/core/services/compliance_service.py`
- Jurisdiction-aware preemption logic → same file, search `preemption`
- Compliance research worker → `server/app/workers/tasks/compliance_checks.py`
- Legislation watch cron → `server/app/workers/tasks/legislation_watch.py`

### Matcha-work (collaborative AI workspace)

- Web surface → `client/src/pages/work/*` + `client/src/layouts/WorkLayout.tsx`
- macOS desktop client → `platforms/desktop/Werk/` (SwiftUI, bundle `com.ahnimal.matcha`)
- Backend routes → `server/app/matcha/routes/matcha_work.py` (8,902 lines — cohesive WS/AI surface, not a split candidate)
- Project service → `server/app/matcha/services/project_service.py`
- AI directives → `server/app/matcha/services/matcha_work_ai.py`
- Channels (WS) → `server/app/matcha/services/channels_service.py` + `mw_channels*` tables

### Database access

- Connection pool helper → `server/app/database.py:get_connection`
- Schema bootstrap (reference only — use Alembic for changes) → `server/app/database.py:init_db`
- Alembic migrations → `server/alembic/versions/*`

### Routing assembly

- Backend route aggregator → `server/app/matcha/routes/__init__.py`
- Frontend route registration → `client/src/App.tsx`
- IR-incidents package router → `server/app/matcha/routes/ir_incidents/__init__.py` (re-exports `crud.router` as the package router)

## Claude Code Setup

This repo is configured for Claude Code with subtree docs, hooks, and project slash commands. The setup is captured in `docs/plans/CLAUDE_CODE_PLAN.md`.

### Subtree CLAUDE.md files (auto-load by directory)

| Path | Loads when editing in… |
|---|---|
| `CLAUDE.md` (this file) | anywhere |
| `server/CLAUDE.md` | `server/**` |
| `server/app/matcha/routes/CLAUDE.md` | `server/app/matcha/routes/**` — the router-zoo index |
| `server/app/matcha/routes/ir_incidents/CLAUDE.md` | inside the IR package — captures the 2026-05-16 split |
| `client/CLAUDE.md` | `client/**` |

Subtree docs compose with this root file. When working in a subtree, the nearer doc has the specific conventions; this root has the cross-cutting product/database/test-data rules.

### Project slash commands (`/<name>`)

Repo-shared scaffolding lives in `.claude/commands/*.md`:

- `/add-feature-flag <name> <default>` — wires backend `DEFAULT_COMPANY_FEATURES` + CLAUDE.md table row + router/endpoint gate + `<FeatureGate>` + sidebar entry
- `/new-router <slug>` — scaffolds a FastAPI router with tenant-isolation pattern + asyncpg + audit-log + Pydantic models + mount in `routes/__init__.py`
- `/add-bulk-upload <entity>` — scaffolds the CSV-template + multipart upload pair. **Encodes the 2026-05-15 medcenter.com bounce-storm lessons**: defaults `send_invitations=False` on both backend and frontend, CSV template uses RFC 2606 reserved domains
- Compliance research commands (`/research-jurisdiction`, `/fill-gaps`, etc.) — pre-existing, for jurisdiction data work

### Post-edit hook

`.claude/hooks/post-edit-python.sh` runs after every `Edit`/`Write`/`MultiEdit`. On `.py` files it runs `python3 -m py_compile` (silent on success, surfaces `SyntaxError` with file+line on failure) plus an optional `ruff check` if installed. No TypeScript check at the hook level — `npx tsc --noEmit` is too slow per-edit; run manually.

Wired in `.claude/settings.json` (shared) — personal allowlist lives in `.claude/settings.local.json` (gitignored).

### Tool-level ignore (`.claudeignore`)

Explore/Grep agents skip generated/built/binary artifacts: `node_modules/`, `client/dist/`, `client/.vite/`, `__pycache__/`, `venv/`, `.pytest_cache/`, `client/src/generated/` (auto-regenerated), lock files, snapshots, Xcode build dirs, DaVinci cache, and secrets (`*.pem`, `*.env`, `token.json`).

## Dead References (ignore)

These are legacy artifacts from a discontinued sister product. Do **not** propose changes, cleanup, or modifications to them unless explicitly asked:

- `scripts/dev.sh` — references a `gummfit-agency/` directory that no longer exists. Use `scripts/dev-remote.sh` instead.
- `scripts/build-and-push.sh` — **still in active daily use** by the user for ECR pushes. The gumfit/gumm-local optional targets in it are dead, but the matcha backend/frontend/agent paths are live. Don't propose deleting it.
- `gumfit_admin` role in `server/app/core/models/auth.py` `UserRole` literal — kept for historical type safety; no live users.
- Any `Gummfit` / `gumfit` string in scripts, docs, or config.
