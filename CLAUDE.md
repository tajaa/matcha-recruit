# Matcha Recruit

Four products share this codebase: **Free** (resources hub), **Matcha-lite** (paid IR/HR-records bundle), **Matcha** (full bespoke platform), and **Matcha-work** (collaborative AI workspace, web + macOS).

## Git worktrees

Use temporary worktrees when they are useful for isolating concurrent work from
the main checkout. Once a PR is submitted (or the isolated work is abandoned),
verify that its changes are committed and pushed, then immediately remove that
exact worktree. Never leave a submitted PR branch checked out in a worktree, and
never remove another user or agent's worktree.

## Products

Differentiated at signup via `companies.signup_source` and routed in the UI by `client/src/utils/tier.ts` + `client/src/components/sidebars/TenantSidebar.tsx`.

| Product | Signup page | `tier` sent | `signup_source` | Sidebar | Routes | Billing |
|---|---|---|---|---|---|---|
| **Free** | `pages/auth/ResourcesSignup.tsx` | `resources_free` | `resources_free` | `ResourcesFreeSidebar` | `/resources/*` | None — upgrade CTA |
| **Matcha-lite** | `pages/auth/MatchaLiteSignup.tsx` | `matcha_lite` | `matcha_lite` | `IrSidebar` once paid; `MatchaLitePendingSidebar` while pending | `/ir/*` | Stripe sub, headcount-based |
| **Matcha Compliance** | `pages/auth/ComplianceSignup.tsx` | `matcha_compliance` | `matcha_compliance` | `ComplianceSidebar` once paid; `CompliancePendingSidebar` while pending | `/app/compliance*` | Stripe sub, headcount + jurisdictions |
| **Matcha (platform)** | `pages/BetaRegister.tsx` (token) or admin-created post-sale | n/a | `bespoke` (default) / `invite` | `ClientSidebar` (full nav) | `/app/*` | Contract / invoice |
| **Matcha-work** | `pages/BetaRegister.tsx` (personal token) → `/work`; or inside Matcha company | n/a | `bespoke` (personal: `is_personal=true`) | `ClientSidebar` AI group; macOS app | `/work/*` | Stripe `matcha_work_personal` $20/mo or business token packs |

Sidebar dispatch in `client/src/components/sidebars/TenantSidebar.tsx`. Tier-check helpers (`isIrOnlyTier`, `isMatchaLitePending`, `isResourcesFreeTier`) in `client/src/utils/tier.ts`.

### Free — resources hub
Marketing/upgrade landing for self-serve signups, no paid features, gated by `<RequireBusinessAccount>`.

### Matcha-lite — paid IR + HR records (entry tier)
Stripe headcount-based (max 300). Grants `incidents`+`employees`+`handbooks` (generation). No audit/training/discipline/credentialing — those are Matcha-X.

### Matcha Compliance — standalone self-serve compliance product
Stripe headcount + jurisdiction-count pricing; grants only `compliance`. Reuses the Matcha-X onboarding wizard.

### Matcha — full bespoke platform
`signup_source='bespoke'` (default) or invite token. `ClientSidebar` full nav, `/app/*` routes.

### Matcha-work — collaborative AI workspace
Web `/work/*` + macOS **Espresso** (`platforms/desktop/Espresso/`) share one backend (`routes/matcha_work/`) and `mw_*` tables — confirm which surface before editing. Personal ($20/mo Stripe) or business (token-pack) mode.

### Custom products — the admin product builder (`/admin/products`)
Data-driven alternative to the ~10-touchpoint hardcoded products above — composed at `/admin/products`, live at `/p/<slug>/signup`. Materialized (not overlaid) grants, `product:<slug>` signup_source namespacing, per-seat/block/flat/free/contact-sales pricing.

Full mechanics (routers, endpoints, migrations, invariants) for every product above: `docs/PRODUCTS.md`.


### Auxiliary surfaces (share codebase, not products)
- **Admin** — `AdminSidebar`, `/admin/*` routes; internal tooling (companies, jurisdiction data, payer data, broker mgmt).
- **Broker** — `BrokerSidebar`, `/broker/*` routes; HR brokers managing multiple client companies.
- **Candidate / Employee portals** — public-token routes (`/candidate-interview/:token`, `/s/:token`); employee self-service through `employee_portal_router`.
- **Public anonymous report** — `/report/:token` (`server/app/matcha/routes/intake/inbound_email.py`); per-company token-gated, reusable form (poster-friendly — not single-use; `/request-info` stays single-use).

## Repo layout — products map

Which frontend pairs with which backend package (don't re-derive this):

| Product | Frontend | Backend | Identity / tables | Domain |
|---|---|---|---|---|
| **Matcha** (Free / Lite / Essentials / X / Compliance / Pro) | `client/` — main SPA (hey-matcha.com) | `server/app/core/` + `server/app/matcha/` at `/api` | `users` + `companies` (`signup_source`, `enabled_features`) | HR compliance, IR/OSHA, ER, employees, broker risk tooling |
| **Matcha-work** (web) | `client/src/work/*` at `/work/*` (+ `/werk`, `/werk-lite` route trees over the same pages) | `server/app/matcha/routes/matcha_work/` | `mw_*` tables | Collaborative AI workspace |
| **Espresso** (macOS, formerly Werk) | `platforms/desktop/Espresso/` (SwiftUI; project still `Matcha.xcodeproj`) | same matcha-work backend | `mw_*` tables | Desktop surface of matcha-work — confirm which surface (web vs desktop) before editing |
| **Cappe** | inside `client/` — host-routed on gummfit.com (`client/src/cappe/host.ts`, pages in `client/src/cappe/pages/`) | `server/app/cappe/` at `/api/cappe` (+ unprefixed tenant renderer on `*.gummfit.com`) | `cappe_accounts`, JWT `scope=cappe`, `cappe_*` tables (no matcha tenant model) | Website builder + domain reselling |
| **Tell-Us** | `client/tellus/` — separate Vite app (React 19), served by the same frontend nginx at `/tellus/` | `server/app/tellus/` at `/api/tellus` | `tellus_accounts` (consumer + brand), JWT `scope=tellus`, `tellus_*` tables | Rewards-for-feedback |
| **Oceanlab** | `client/oceanlab/` — separate Vite app (React 19), served by the same frontend nginx at `/oceanlab/` | `server/app/oceanlab/` at `/api/oceanlab` | static bearer `OCEANLAB_TOKEN` (env), `oceanlab_*` tables (no matcha tenant model) | Music catalog / label ingestion pipeline |
| **MatchaTutor** (iOS) | `platforms/ios/` (SwiftUI, dormant) | matcha-work language-tutor endpoints | — | Language tutor |
| **Ops agent** | `agent-ui/` (Preact; build copied into `server/agent/static/` by `build-and-push.sh`) | `server/agent/` — standalone service :9100 (not part of `app/`) | — | Internal leads/ops console |

Cross-product import rule: `cappe/`, `tellus/`, and `oceanlab/` import only from `app/core/*` (shared db pool, email, storage, auth, redis). One documented exception: `tellus/services/geo.py` reuses `matcha.services.property.property_cat.geocode` (single US Census geocoder — keep its signature stable). Verified 2026-07-27: `cappe → matcha` is 0 edges, `tellus → matcha` is that 1. `oceanlab → matcha` is 0 edges; Oceanlab uses its own sync SQLAlchemy engine and shared core storage, see `server/app/oceanlab/CLAUDE.md`.

**`werk/` is the fourth backend app and its rule is different — say so rather than assume.** `werk → matcha.services` is allowed and intentional (9 files / 59 imports, verified 2026-08-03; one deliberate module-level import at `werk/routes/channels.py:18` — don't "fix" it lazy). `matcha → werk` is exactly 2 lazy imports of `werk.routes.channels_ws.manager` — adding a third kind is the thing to refuse. Routes importing routes must stay 0 in both directions. Full edge inventory: `server/app/werk/CLAUDE.md`

## Stack

- **Framework**: FastAPI + uvicorn (async)
- **Database**: PostgreSQL via asyncpg (connection pool)
- **Background jobs**: Celery + Redis
- **AI**: Google Gemini via `GEMINI_API_KEY` (native Google AI; Vertex removed)
- **Storage**: S3 + CloudFront (`server/app/core/services/storage.py`)
- **Auth**: JWT
- **Deployment**: AWS EC2 — Nginx reverse proxy + Postgres in a container on a dedicated DB EC2.

## Database

**The RDS rollback is DONE.** Live production is `matcha-postgres-prod` (PG 15 in Docker; DB `matcha`, user `matcha`) on the dedicated `matcha-postgres-db` EC2. Verified 2026-08-23: the app host's `DATABASE_URL` points to `13.56.253.173:5433`, that EC2 and container are running, and `matcha-prod` RDS is stopped. Full workflow + scripts: `docs/ops/DB_WORKFLOW.md`.

| Instance | Where | Role | Who connects |
|---|---|---|---|
| `matcha-postgres-prod` container | `matcha-postgres-db` EC2 `13.56.253.173:5433` | **PROD — the only live one**; data on encrypted EBS mounted at `/mnt/encdb/pgdata` | app EC2; laptop tools tunnel through app EC2 to `localhost:5434`; SSL required |
| `matcha-postgres` container | **local** Docker `:5432` | **DEV** | laptop directly / `dev-remote.sh` |
| `matcha-prod` RDS | `matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com:5432` | **STOPPED cold fallback**, frozen at the 2026-08-21 rollback; not live prod | nothing unless deliberately restarted |
| Historical containers | original DB EC2 `3.101.83.217` | **RETIRED**; host stopped | nothing |

**⚠️ Prod == `13.56.253.173:5433`, nothing else.** `migrate-prod.sh`, `prod-psql.sh`, `refresh-dev-from-prod.sh`, `seed-prod.sh`, and `sync-test-tenants.sh` use that endpoint through the app EC2 (`54.177.107.107`); laptop tools terminate at `localhost:5434` using `PROD_DATABASE_URL` in `server/.env`. `--legacy` flags target the retired original host, not RDS and not live prod.

**NEVER do the following without explicit user approval — especially against prod:**
- CREATE ROLE / DROP ROLE
- CREATE TABLE / DROP TABLE on real tables
- `alembic upgrade head` against prod
- Any DDL (ALTER TABLE, CREATE INDEX, etc.) directly
- Tests that create/drop/alter tables, roles, or schema on a live DB
- Assume you can freely experiment with either DB

**For integration tests that need DB access:** write them to be run manually by the user, use reserved-domain test data, never auto-run DB-mutating tests.

### Schema + data flow — keep dev and prod in sync (both directions)

Schema is managed via Alembic migrations in `server/alembic/versions/`; `server/app/database/bootstrap/__init__.py:init_db()` only bootstraps a fresh DB (it does **not** run migrations). The two DBs drift unless synced deliberately:

- **Schema, dev → prod:** author migration → `./scripts/migrate-dev.sh` → test → `./scripts/migrate-prod.sh` (5 safety gates; `alembic_version` must match after; dev-only apply is the drift that caused real 500s). Detail: `docs/ops/DB_WORKFLOW.md`
- **Data, prod → dev:** `./scripts/refresh-dev-from-prod.sh` — anonymized clone. `SKIP_ANONYMIZE=1` currently set (pre-customer, clones verbatim); turn it back OFF the moment real customers exist (`DEV_PRESERVE_EMAILS` keeps your own logins). Detail: `docs/ops/DB_WORKFLOW.md`
- **One tenant, prod → local dev:** `./scripts/pull-tenant-from-prod.sh "Company Name" [--dry-run]` — production is read-only; replaces only that company's FK-descended local rows, reconciles referenced shared catalogs by natural key, rehearses with rollback, and takes a full local recovery dump before apply. Other tenants and non-Matcha apps are untouched. Detail: `docs/ops/DB_WORKFLOW.md`
- **Seed/demo → prod:** `./scripts/seed-prod.sh <pack> [--dry-run|--undo|--dev]` — the only sanctioned general seed/demo write path; always `--dry-run` first. The sole narrow automation exception is the fixed-shape post-deploy admin-update publisher, which accepts validated JSON (never SQL) and can touch only the two changelog tables plus their watermark. Guards + pack conventions: `docs/ops/DB_WORKFLOW.md` + `scripts/seed/README.md`; publisher trust boundary: `docs/ops/ADMIN_UPDATES_AUTOPUBLISH.md`.
- **Backups:** `pg-backup.timer` runs `deploy/backup-prod.sh` twice daily on the app EC2; every normal backend deploy installs the units and queues an extra non-blocking run. Dumps stream to `s3://matcha-recruit-backups/postgres-selfhosted/` with 7-day retention; `operational-integrity-checks.yml` validates newest-object age, size, and `pg_restore --list` after each scheduled backup. **There is no live-prod RDS PITR.** One manual EBS snapshot exists from cutover, but no recurring EBS snapshot policy. Detail: `docs/ops/DB_WORKFLOW.md`
- **Schema drift:** `schema-drift-checks.yml` (split out of `operational-integrity-checks.yml` 2026-08-26 — different cron, different runner) compares exact multi-head `alembic_version` sets from the shared local dev container and live prod. Equal heads and unexplained revision drift generate a read-only, normalized schema-only dump comparison; ancestry-explained `behind` skips the expected DDL difference. It runs on the self-hosted Mac and never starts dev Postgres. Detail: `docs/ops/DB_WORKFLOW.md`

**SSH:** app host/jump: `ssh -i secrets/roonMT-arm.pem ec2-user@54.177.107.107`; live DB host: `ssh -i secrets/roonMT-arm.pem ec2-user@13.56.253.173`. The original DB host `3.101.83.217` and stale `52.9.117.137` (`ec2-ahnimal`) are stopped legacy instances.

## Directory Structure

```
server/
├── run.py                          # Entry point (uvicorn)
├── app/
│   ├── main.py                     # App init, router mounting, lifespan
│   ├── config.py                   # Pydantic settings from env
│   ├── database/                   # asyncpg pool + init_db() bootstrap (package)
│   ├── protocol.py                 # AI WS / streaming protocol shapes
│   ├── core/                       # Auth, admin, compliance, AI chat, policies, resources
│   │   ├── models/
│   │   ├── routes/                 # see core/routes/CLAUDE.md
│   │   └── services/               # compliance_service/, email/ and compliance_pilot/
│   │                               #   are PACKAGES, not files
│   ├── matcha/                     # Recruiting + HR domain (incl. matcha-work)
│   │   ├── models/                 # mirrors services/ subdirs: ir/ er/ employees/ pilots/ …
│   │   ├── routes/                 # Router zoo — see routes/CLAUDE.md
│   │   │   ├── ir_incidents/       # Package (split 2026-05-16) — see ir_incidents/CLAUDE.md
│   │   │   │   └── osha/           # nested package (split 2026-07-27)
│   │   │   ├── employees/          # 13-file package (split 2026-05-16) — see employees/CLAUDE.md
│   │   │   ├── er_copilot/         # Package (split 2026-07-06) — see er_copilot/CLAUDE.md
│   │   │   ├── matcha_work/        # Package (split 2026-07-03) — see matcha_work/CLAUDE.md
│   │   │   ├── employee_portal/    # Package (split 2026-07-26) — see employee_portal/CLAUDE.md
│   │   │   ├── dashboard/          # Package (split 2026-07-26) — see dashboard/CLAUDE.md
│   │   │   └── … grouping folders: broker/ insurance/ pilots/ onboarding/ intake/ employee_lifecycle/
│   │   │                             work/ integrations/ employee_schedule/ labor_relations/
│   │   └── services/               # domain subdirs + _shared/ leaves (pdf, citations, gemini, text).
│   │                               #   FACADE PACKAGES: matcha_work/matcha_work_ai/, matcha_work/
│   │                               #   project_service/, broker/broker_pilot/, pilots/handbook_pilot/,
│   │                               #   pilots/hr_pilot_corpus/, risk_analytics/risk_assessment_service/
│   ├── cappe/                      # Cappe (website builder) at /api/cappe — see repo-layout table
│   ├── tellus/                     # Tell-Us (rewards-for-feedback) at /api/tellus
│   ├── oceanlab/                   # Oceanlab (music catalog / label pipeline) at /api/oceanlab
│   ├── werk/                       # Werk / Werk-Lite channels, calls, job postings
│   ├── workers/                    # Celery app + scheduled tasks
│   ├── orm/                        # SQLAlchemy helpers (limited use)
│   └── uploads/                    # Local-only upload temp dir
├── tests/
└── alembic/

client/src/                         # app-first: cappe/ and work/ are self-contained
├── cappe/                          # Cappe app — own api/pages/routes/layout/hooks
├── work/                           # matcha-work / werk / werk-lite — own api/pages/routes
│                                   # ── everything below is Matcha, the risk platform ──
├── api/                            # client.ts (THE http helper) + infra at root;
│   └── <domain>/                   # one folder per domain, named to match components/
├── components/
│   ├── ui/                         # Generic primitives (Button, Input, …)
│   ├── shared/                     # App-wide infra chrome (FeatureGate, ErrorBoundary, …)
│   ├── widgets/                    # Reusable content widgets (AiSuggest, NoteThread, …)
│   ├── sidebars/                   # ClientSidebar, TenantSidebar (tier dispatcher), Admin, Broker
│   ├── tier-sidebars/              # Ir / MatchaLitePending / ResourcesFree / Compliance shells
│   └── <domain>/                   # ir/, er/, compliance/, employees/, discipline/, matcha-x/, …
│                                   # onboarding flows live in <domain>/onboarding/
├── hooks/                          # useMe (THE auth state) + domain subdirs
├── routes/                         # Per-app route trees (AppRoutes, AdminRoutes, …)
├── layouts/                        # AppLayout
├── pages/
│   ├── app/<domain>/               # /app/* grouped by domain; AppRoutes.tsx is sole importer
│   ├── admin/, broker/             # still flat — deferred on purpose
│   └── auth/, home/, landing/, portal/, shared/, simpler-pages/
├── types/                          # Shared TypeScript types — <domain>.ts
├── utils/                          # Pure utilities (incl. tier.ts)
├── data/                           # Static / seed data
└── generated/                      # Auto-generated types (do not edit)
```

Placement rules, boundary rules between the three apps, and the deferred/follow-up list live in `client/CLAUDE.md`.

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
| `matcha_work` | ❌ | Projects / threads / private project discussion chat / workspace AI |
| `matcha_ops` | ❌ | Matcha Ops surface — company channels, calls, Events, inventory, scheduling, and channel automation |
| `matcha_ops_calls_all_members` | ❌ | Matcha Ops call-start policy — false=admins only, true=any member starts; joining remains member-only |
| `training` | ❌ | Training programs — requirement provenance + auto-assign rules (new-hire/incident/schedule). Forced ON in Matcha-X, OFF in Lite. → `server/app/matcha/services/training/CLAUDE.md` |
| `i9` | ❌ | I-9 compliance |
| `cobra` | ❌ | COBRA admin |
| `separation_agreements` | ❌ | Separation doc workflow |
| `credential_templates` | ❌ | Credentialing / license tracking. Default-off, but in the **Matcha-X** bundle (tier overlay) and **Pro** (stored on bespoke signup). |
| `compliance` | ❌ | Full Compliance feature — paid gate for standalone **Matcha Compliance** (Stripe webhook flips it) and the **Pro** power-tools flag (stored at bespoke signup: live re-research, alerts, AI ask, wage-violations, payer policies). NOT in any tier overlay — flipped by payment, like `incidents`. |
| `compliance_lite` | ❌ | Read-only Compliance taste for Matcha-X — shared GETs via `require_any_feature`; power endpoints stay `compliance`-gated. → `server/app/core/services/CLAUDE.md` |
| `hris_import` | ❌ | HRIS sync — legacy umbrella; gates treat it as "both providers" |
| `hris_gusto` | ❌ | HRIS via Gusto OAuth (direct) |
| `hris_finch` | ❌ | HRIS via Finch unified API (Rippling, BambooHR, ADP, …) |
| `hris_deductions` | ❌ | Deductions/benefits **write**-back via Finch — requests the `benefits` product at connect; gates `/provisioning/hris/benefits` (provider must support it) |
| `paid_channel_creator` | ❌ | Stripe-gated paid channels |
| `channel_job_postings` | ❌ | Stripe-gated job postings in channels |
| `benefits_admin` | ❌ | Employee-benefits broker tooling — roster ingest (Finch+CSV), eligibility-exception detection, renewal-risk radar. Gates `/benefits/*` + `/broker/benefits/*`. → `server/app/matcha/services/benefits/CLAUDE.md` |
| `werk_lite` | ❌ | Standalone business work-chat at `/werk-lite` (own login) — channels + calls + kanban, whole-company. Needs `matcha_work` too. → `server/app/werk/CLAUDE.md` |
| `werk_lite_calls_all_members` | ❌ | Werk Lite call-start policy — false=admins only, true=any member starts; joining always open. → `server/app/werk/CLAUDE.md` |
| `workforce_compliance` | ❌ | Employment-practices risk trackers (pay-transparency, AI-hiring bias audit, BIPA, pay-equity). Feeds broker EPL factors. In `matcha_x` overlay. → `server/app/matcha/services/workforce/CLAUDE.md` |
| `risk_profile` | ❌ | Client-facing composite risk index + submission-readiness score, same engine as the broker view. NOT bundled. → `server/app/matcha/services/broker/CLAUDE.md` |
| `resident_care` | ❌ | Healthcare/senior-living resident-care risk asset — safety-program register, MVR review tracking, credentialing currency, insurer PDF. NOT bundled. → `server/app/matcha/services/insurance/CLAUDE.md` |
| `controls_evidence` | ❌ | Proof-of-Controls register + underwriter PDF, auto-compiled from 8 existing risk controls. Generalizes `resident_care`. NOT bundled. → `server/app/matcha/services/insurance/CLAUDE.md` |
| `limit_adequacy` | ❌ | Limit-adequacy + contract review — carried limits vs Gemini-extracted requirements + deterministic risk-transfer verdicts. Own S3 bucket for source PDFs. NOT bundled. → `server/app/matcha/services/insurance/CLAUDE.md` |
| `driver_risk` | ❌ | Driver/fleet MVR scoring (shared `mvr_reviews` table) → fleet grade + insurer PDF. NOT bundled. → `server/app/matcha/services/insurance/CLAUDE.md` |
| `property` | ❌ | Commercial property — SOV/COPE grading, TIV/ITV, geocoded cat perils. NOT bundled. → `server/app/matcha/services/property/CLAUDE.md` |
| `ir_voice_intake` | ❌ | Voice dictation on the IR create form — Gemini prefills fields, user reviews before submit. NOT bundled. → `server/app/matcha/routes/ir_incidents/CLAUDE.md` |
| `ir_chat_intake` | ❌ | Conversational IR intake for authenticated reports and public magic links — one Gemini flash-lite call per turn asks a question, fills fields, lands on an editable review step, and never auto-submits. NOT bundled. → `server/app/matcha/routes/ir_incidents/CLAUDE.md` |
| `handbook_watch` | ❌ | Scheduled handbook-freshness sweeps + alerts (manual check stays free with `handbooks`). Lite-family paid add-on. → `server/app/workers/CLAUDE.md` |
| `legal_defense` | ❌ | Legal Pilot — grounded legal-matter chat, citation-gated defense-memo PDF + evidence ZIP. Routes `/legal-pilot/*`. NOT bundled. → `server/app/matcha/services/pilots/CLAUDE.md` |
| `handbook_pilot` | ❌ | Handbook Pilot — grounded drafting of sections/policies, citation-gated, promotes into real tables. In `matcha_x` overlay + Pro. → `server/app/matcha/services/pilots/CLAUDE.md` |
| `hr_pilot` | ❌ | HR Pilot — supervisor thread mode grounded on handbook/policy/legal-floor; deterministic hard-stop gate before any AI call. NOT bundled. → `server/app/matcha/services/pilots/CLAUDE.md` |
| `ask_hr` | ❌ | Employee Ask-HR — portal counterpart of `hr_pilot`, same corpus redacted of coworker-naming data; surface-split hard-stop classifier. Sold separately. → `server/app/matcha/services/pilots/CLAUDE.md` |
| `huume` | ❌ | Huume — bounded Gemini tool-calling agent in matcha-work threads; everything staged/confirm-first. Skills: onboarding, HR-ops, pilot bridges, incident-discipline. Needs `matcha_work`. → `server/app/matcha/services/huume/CLAUDE.md` |
| `huume_code` | ❌ | Huume in a business collab chat can open one draft PR; no code execution or default-branch writes. GitHub writes require the server-side `GITHUB_WRITE_ALLOWED_REPOS` allowlist because the PAT is global—internal/dogfood only until GitHub App tokens replace it. Needs `matcha_work`. |
| `ems` | ❌ | EMS — "@huume <what happened>" in any channel logs a structured event; admin promotes to a real IR incident (AI never auto-creates). Branded **"Ops"** in the sidebar/pill copy (Events tab lives under the Ops group with Protocol + Inventory) — flag name, tables, and URL paths unchanged. A channel bound to a `business_locations` row scopes intake to that store (`channels.location_id`). Needs `matcha_work`. → `server/app/matcha/services/ems/CLAUDE.md` |
| `analysis_pilot` | ❌ | Analysis Pilot — bring-your-own-data chat analysis (CSV/XLSX/PDF), deterministic analyzer packs + citation-gated narration. NOT bundled. → `server/app/matcha/services/pilots/CLAUDE.md` |
| `osha_logs` | ✅ | Interactive OSHA 300/301/300A recordkeeping. Default ON (off for no-roster `matcha_lite_essentials`). → `server/app/matcha/routes/ir_incidents/CLAUDE.md` |
| `osha_export` | ❌ | CSV-download-only OSHA slice for tier composition. Default OFF, additive — doesn't regress `osha_logs` tenants. → `server/app/matcha/routes/ir_incidents/CLAUDE.md` |
| `osha_auto_report` | ❌ | Electronic ITA submission, split from `osha_logs` for separate pricing. Default OFF, additive. → `server/app/matcha/routes/ir_incidents/CLAUDE.md` |
| `ir_magic_links` | ✅ | All public token IR intake. Default ON and SUBTRACTIVE — presets that stomp `enabled_features` must re-grant this explicitly (PR #103 regression). → `server/app/matcha/routes/ir_incidents/CLAUDE.md` |
| `ir_copilot` | ✅ | IR Copilot chat + AI analysis runners. Subtractive default like `ir_magic_links`; deliberately not in `FEATURE_REQUIRES`. → `server/app/matcha/routes/ir_incidents/CLAUDE.md` |
| `employee_schedule` | ❌ | Shift scheduling over the roster — templates, swap/drop/unavailability requests, forceable-409 conflict rules. Paid add-on. → `server/app/matcha/services/scheduling/CLAUDE.md` |
| `schedule_intelligence` | ❌ | Deterministic analytics over `employee_schedule` — incident correlation, Fair Workweek exposure (NYC+LA only), pretext shield, qualified coverage. NOT bundled. → `server/app/matcha/services/scheduling/CLAUDE.md` |
| `inventory` | ❌ | Channel-driven inventory tracking via `@huume` — auto-created items, append-only movement ledger, internal order queue (queued→ordered→received) with in-channel confirm; full `/work` Inventory page under the **"Ops"** sidebar group; also fully manageable by chat from Huume threads (staged movements/orders/items/receipt-attachment commits). Items are per-store (`inventory_items.location_id`) when created from a location-scoped channel; a channel with no store binding shares the legacy company-wide catalog. Bulk stock-count "Audit" sheet (`POST /inventory/audit/commit`, kind='adjust' only) ships free with this flag. NOT bundled. → `server/app/matcha/services/inventory/CLAUDE.md` |
| `inventory_voice` | ❌ | Voice dictation on the Inventory Audit sheet — a manager speaks counts ("twelve boxes of gloves...") and one Gemini multimodal call (`services/inventory/voice_audit.py`) parses them into a draft the manager reviews before saving; parse-only, never writes. Same WAV/AudioWorklet capture stack as `ir_voice_intake` (shared `hooks/useVoiceDictation.ts`). Gates `POST /inventory/audit/voice-parse` (stacks on `inventory`) + the Dictate button. Default off; admin-toggle; NOT bundled. → `server/app/matcha/services/inventory/CLAUDE.md` |
| `sales_intake` | ❌ | POS/PMIX sales export intake — direct SKU mappings, aggregated `sale` depletion, expected-on-hand breakdown, and persisted audit variance. Requires `inventory`; default off; admin-toggle; NOT bundled. → `server/app/matcha/services/inventory/CLAUDE.md` |
| `inventory_forecasting` | ❌ | Deterministic demand forecast and advisory replenishment recommendations over committed sales imports, with Square finalized-order ingestion and a rate-limited, parse-only AI scenario draft. Requires `inventory` + `sales_intake`; saves immutable forecast snapshots and never autonomously creates or approves orders—managers may stage a queued order from the plan for the existing approval flow. → `server/app/matcha/services/inventory/CLAUDE.md` |
| `inventory_waste` | ❌ | Waste & shrinkage — a `waste` movement kind + reason-code taxonomy (spoilage/expired/prep_error/overproduction/breakage/contamination/comp/recall/theft/unknown), dollarized rollups, theoretical-vs-actual usage variance, perishable lots, and guarded predictive pars. Chat capture via `@huume` never auto-creates an item and always coerces a reported `theft` to `unknown` — a personnel accusation is never minted from a Slack-style aside. Requires `inventory`; default off; admin-toggle; NOT bundled. → `server/app/matcha/services/inventory/CLAUDE.md` |
| `safety_meetings` | ❌ | AI-powered toolbox-talk records — chunked WAV transcription, Gemini summary, manager review/edit, private audio retention, and typed-name sign-off. Gates `/safety-meetings` + `/app/safety-meetings`; default off; admin-toggle; NOT bundled. |
`incidents` and `employees` are not in the defaults — they're flipped on by tier-specific flows (Matcha-lite Stripe webhook, IR-only signup) or admin toggle.

**Tier bundles** (read-time via `TIER_REQUIRED_FEATURES` overlay in `feature_flags.py`, except Pro which stores at signup):
- **Lite** (`matcha_lite`) = `incidents` (paid) + `employees` + `handbooks` (generation). `training`/`discipline` force-asserted **off** here; no `handbook_audit`/`credential_templates`.
- **Lite Essentials** (`matcha_lite_essentials`) = a checkbox on the *same* `/lite/signup` page as standard Lite (not a separate product/route) — `incidents` (paid) + `handbooks`, but `employees`/`osha_logs` force-asserted **off** (no roster: no CSV/HRIS import, no OSHA 300 logs; reporter/witness capture still works via the no-roster `ir_people` index). Own cheaper row in `matcha_lite_pricing` (`product_code='matcha_lite_essentials'`).
- **Matcha-X** (`matcha_x`) = Lite + `training` + `discipline` + `handbook_audit` + `credential_templates` + `compliance_lite` (read-only Compliance taste) + `handbook_pilot` + `workforce_compliance` (employment-practices trackers + real pay-equity gap) — all forced on via overlay.
- **Pro** (`bespoke`/`invite`/`broker`) = full `DEFAULT_COMPANY_FEATURES` + `incidents` + `handbook_audit` + `credential_templates`, stored at signup (toggleable per-company; not an overlay, so it doesn't leak to personal Espresso/matcha-work which shares `signup_source='bespoke'`).
- **Matcha Compliance** (`matcha_compliance`) = full `compliance` only, nothing else bundled. `compliance` is **not** in any overlay — it's the Stripe-gated paid flag (flipped by `checkout.session.completed`), exactly like `incidents` gates Lite/X. Onboarding reuses `MatchaXOnboardingWizard`.

## Key Modules

- **Compliance** (`core/services/compliance_service/`) — Jurisdiction-aware compliance checking with Gemini AI; preemption rules, tiered data (structured → repository → Gemini research).
- **Vertical coverage** (`core/services/vertical_coverage.py`, `vertcov01`) — auto-scopes any US industry via the shared `(jurisdiction_id, industry_tag, category)` coverage ledger; 3 triggers (X onboarding build, opt-in run-check fill, `vertcov02` sweep). Ledger/level-routing/category-vocab/never-blanket-tag invariants → full spec: `server/app/core/services/CLAUDE.md`
- **Workers are pool-free — shared service code must not assume a pool.** `celery_app.py` never calls `init_pool`; use `database.connection_or_direct()` (or an explicit `conn=`) in code that runs in both worlds — `rate_limiter` + `platform_settings` sit on every Gemini call path. Full story: `server/app/workers/CLAUDE.md`
- **Compliance data evals** (`core/services/compliance_evals/`) — read-only measurement of the `jurisdiction_requirements` catalog: 4 suites (completeness/authority/tagging/golden) rolling up to an onboarding-readiness gate; `core` (≤30 curated keys) vs `full` depth. → full spec: `server/app/core/services/CLAUDE.md`
- **AI Chat** (`core/services/ai_chat.py`) — WebSocket chat with local Qwen model or Gemini.
- **Matcha Work** (`matcha/routes/matcha_work/` package + `services/matcha_work/project_service/`, `services/matcha_work/matcha_work_ai/` package) — projects, threads, channels, inbox, AI directives.
- **Matcha Work thread modes** (`services/matcha_work/matcha_work_modes.py` — THE registry) — per-thread grounding modes, registry-driven end to end; paid modes carry `required_feature` (re-checked each turn). → full spec: `server/app/matcha/routes/matcha_work/CLAUDE.md`
- **Kanban autopr** (`.github/workflows/kanban-autopr.yml` + `scripts/kanban-autopr/`) — self-hosted-runner bot that picks a kanban card assigned to a fixed service account across four fixed Espresso projects (`todo`/`changes_requested`) and opens a draft PR; a `post-checkout` hook and a `pull_request` webhook sync the card back. → full spec: `docs/ops/KANBAN_AUTOPR.md`
- **Channels** (`werk/routes/channels.py` + `channels_ws.py`) — real-time WebSocket messaging, paid channels, member presence. No `channels_service.py`; logic lives in the two route modules (`channels_ws.py` owns `manager`, the fan-out object matcha imports back — see werk boundary rule above).
- **IR Incidents** (`matcha/routes/ir_incidents/` — 10-file package since 2026-05-16; see `ir_incidents/CLAUDE.md`) — safety/behavioral incident reporting + AI analysis. Public anonymous intake at `routes/intake/inbound_email.py`.
- **Discipline** (`routes/employee_lifecycle/discipline.py` + `services/discipline/`) — deterministic escalation ladder + a no-LLM compliance gate (protected-leave/attendance overlap in a mapped state ⇒ hard 422 block, no override; unmapped ⇒ advisory) + Gemini letter drafting (never decides legality) + incident-triggered HR-approval flow (`transition_status` is the single choke point). All on the existing `discipline` flag. → full spec: `server/app/matcha/services/discipline/CLAUDE.md`
- **ER Copilot** (`matcha/routes/er_copilot/` — 11-file package since 2026-07-06; see `er_copilot/CLAUDE.md`) — employment-relations case mgmt.
- **Risk Assessment** (`matcha/routes/risk_assessment.py`).
- **Interviews** (`matcha/services/`) — voice interviews via Gemini Live API.
- **Inventory** (`matcha/services/inventory/` + `matcha/routes/inventory.py`) — channel-driven stock tracking via `@huume` (auto-created items, append-only movement ledger, internal order queue with in-channel confirm). WS dispatch in `werk/routes/channels_ws.py:_bg_inventory_request`/`_bg_inventory_reply`, intent classification in `services/ems/intent.py`'s `INVENTORY` case. → full spec: `server/app/matcha/services/inventory/CLAUDE.md`
- **Safety meetings** (`matcha/routes/safety_meetings.py` + `matcha/services/safety_meetings/`) — chunked WAV toolbox-talk transcription, Gemini summary, manager review/edit, private audio retention, and signed record storage. The signed record is locked after typed-name confirmation; gated by `safety_meetings`.
- **Huume code** (`matcha/services/huume_code/` + `workers/tasks/huume_code.py`) — `@huume` in an eligible business collab chat runs a bounded repo-grounded agent that stages files only in memory and opens a single draft PR through the GitHub REST API.
- **Espresso project agent** (`matcha/services/matcha_work/project_agent/` + `workers/tasks/project_agent.py`) — `@espresso` in a repo-connected project discussion queues a durable, read-only repository question and posts a source-linked answer back to chat. Its generic `mw_project_agent_runs` audit lifecycle is intended to host additional project-agent task kinds; repo Q&A has no mutation tools and never moves tickets or writes GitHub.

## Background Workers (Celery)

Celery worker container `matcha-worker` runs everything that can't run inline. Single concurrency, restarts after 5 tasks (`--max-tasks-per-child=5`) to recycle memory. `task_acks_late=True` + `max_retries=3` so OOM-killed tasks retry.

Scheduling model: no celery-beat. Worker container runs continuously (`restart: unless-stopped`); the `matcha-worker.timer` systemd unit runs `docker restart matcha-worker` hourly (installed/reinstalled by `install_worker_timer()` in `scripts/update-ec2.sh` on every normal backend deploy), which re-fires `@worker_ready` in `app/workers/celery_app.py` and re-dispatches periodic tasks. Each is gated by a `scheduler_settings` row, default disabled.

**Periodic / scheduled** (`app/workers/tasks/`):
- `compliance_checks` — per-location Gemini scans
- `compliance_action_reminders` — nudges for open requirements
- `legislation_watch` — Gemini-grounded legislation deltas
- `leave_deadline_checks`, `leave_agent_orchestration` — leave-of-absence tracking
- `onboarding_reminders` — new-hire task chases
- `discipline_expiry` — auto-close stale discipline records
- `ir_deadline_alerts` — IR deadline/SLA nudges; dedup via `reminder_sent_at` + `ir_deadline_alert_log`. Detail: `server/app/workers/CLAUDE.md`
- `hr_proactive_push` — opens pre-briefed HR Pilot threads (leave returns, discipline review dates, stuck signatures); deterministic briefings, one-shot-ever dedupe (`hrpush01`). Detail: `server/app/workers/CLAUDE.md`
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

**Stays inline in FastAPI (NOT on worker)**: WebSocket chat streams, voice interview WS (Gemini Live), PDF render via WeasyPrint (`asyncio.to_thread` in `routes/matcha_work/pdf_export.py`), all CRUD, Stripe webhooks, auth.

PDF render is intentionally inline because the desktop client awaits the bytes — but it is the dominant memory consumer in the backend container. If backend memory pressure recurs, moving `_render_project_pdf` to a celery task and `.get(timeout=60)` is the obvious next step.

## Host nginx on the app EC2 (deploy/nginx/)

Host-level nginx server blocks on the app EC2 (`/etc/nginx/conf.d/`) are hand-managed; the repo source of truth is `deploy/nginx/` (`matcha.conf`, `cappe.conf` — apply via scp per `deploy/nginx/README.md`, they are NOT touched by `build-and-push.sh`/`update-ec2.sh`).

**Blue-green rule (critical):** deploys alternate frontend `8082↔8083` / backend `8002↔8003` and **remove the old container**. Every server block must `proxy_pass` to the `matcha_frontend` / `matcha_backend` upstream groups (defined in `matcha.conf`; active port written to `/etc/nginx/upstream/matcha-*-active.conf` by the deploy scripts) — **never hardcode a port**. A hardcoded `:8082` in `cappe.conf` is how gummfit.com 502'd to the maintenance page after a swap (fixed 2026-07-02).

Retired/backup configs go to `/etc/nginx/conf.d/archive/` (nginx only globs `*.conf`). Legacy `oceaneca.conf` was retired there 2026-07-01 — `gummfit.com` belongs to `cappe.conf` (Cappe); if oceaneca.com ever revives, restore from archive minus its gummfit.com server blocks.

## Deploying (`build-and-push.sh` → `update-ec2.sh`)

Normal rollout is `./scripts/build-and-push.sh && ./scripts/update-ec2.sh --matcha` (`--backend` / `--frontend` to narrow). **Emergency patch: `./scripts/build-and-push.sh --backend-only && ./scripts/update-ec2.sh --backend --hotfix`** — `--hotfix` does pull + blue/green swap and nothing else (no nginx sync, no backup trigger, no pruning, 5s worker stop instead of 60s).

**Or dispatch from the Actions tab / GitHub mobile app** (`.github/workflows/deploy.yml`, `workflow_dispatch`): pick target (`matcha`/`backend`/`frontend`) + optional hotfix toggle — same `update-ec2.sh` underneath. Build runs on the free ARM runner via OIDC; deploy job SSHs in with the same key as the laptop path; all third-party actions SHA-pinned. Detail: `docs/ops/DEPLOY.md`

Gitlink footgun (a mode-160000 clone-in-tree breaks `actions/checkout`'s credential teardown) is guarded by `scripts/tests/test_ci_guards.sh` case 7. Story: `docs/ops/DEPLOY.md`

Two deploy-slowness regressions fixed 2026-07-19 — don't reintroduce: (1) never `docker image prune -a` before the pull (pruning belongs after the swap; the pre-pull prune survives only as a `<4GB`-free-disk safety valve); (2) the deploy-triggered logical backup is queued through systemd and must stay non-blocking/non-fatal. The same service owns the twice-daily timer, preventing recurrence of the stale `~/backup-postgres.sh` target. Full mechanics + history: `docs/ops/DEPLOY.md`

**Changelog auto-publication**: every successful Matcha backend/frontend deployment dispatches `.github/workflows/admin-updates-autopublish.yml`. The self-hosted `matcha-autopr` machine verifies each PR is present in every required active image and has no pending migration, then runs `gpt-5.6-luna` at high reasoning in the credential-free msandbox to draft feature, usage, and context copy. Strict validation sits between the model and a fixed transactional publisher for production `admin_updates` / `tellus_admin_updates`; existing rows are never overwritten. The dispatch is post-swap and non-fatal to the deploy. Full trust boundary + bootstrap/recovery: `docs/ops/ADMIN_UPDATES_AUTOPUBLISH.md`.

## Logs + error tracking

**`./scripts/logs.sh backend|worker|frontend|nginx|nginx-err|errors`** tails prod (resolves the blue-green `8002`/`8003` suffix for you — don't hardcode it). But the **durable** error record is Postgres, not the container logs: `server_error_reports` (Admin → Server Errors) with fingerprint dedup + occurrence counts, and `client_error_reports` for browser-side errors. Every request carries a correlation ID — `X-Request-ID` header, `[rid=…]` on each backend log line, `context.request_id` on the error row, and a `Reference:` line on the user's crash screen.

Keep `LOG_LEVEL` at `INFO` or lower — some log calls sit at `WARNING` deliberately so the root `ERROR` DB handler doesn't double-persist them. Container logs die with each blue-green deploy unless CloudWatch shipping is on (gated behind `MATCHA_LOG_DRIVER=awslogs`; **needs an IAM instance role first — the box has none as of 2026-08-03**, and an awslogs auth failure makes containers refuse to start). Setup: `deploy/cloudwatch/README.md`. Full runbook (where every log lives, levels, alert-email behavior, CW Insights queries, known gaps): `docs/ops/LOGS.md`

**Primary script**: `./scripts/dev-remote.sh` — ensures the **local** `matcha-postgres` Docker container is up (dev Postgres moved off the DB EC2; the name is historical), starts the Redis tunnel, backend on `:8001`, frontend on `:5174`, local chat model on `:8080`. Requires `secrets/roonMT-arm.pem`. To sync dev/prod see the Database section + `docs/ops/DB_WORKFLOW.md`.

**⚠️ `dev-remote.sh`'s frontend runs on `:5174` (tmux session `matcha-dev-remote`) — it is almost always already running.** If you spin up your own throwaway `npm run dev` (e.g. to screenshot-verify a change), do NOT clean it up with a port-pattern `pkill -f "vite --port ..."` — that regex also matches the user's real dev-remote.sh frontend process (same command line) and kills it. Track your own process by PID (`$!` / a pidfile) and `kill` that PID specifically instead.

**Dev test account (full-featured Matcha-X)**: `maria.chen@example.com` / `devpass123` in the local dev DB — client role, company "Sunset Smile Dental Group" (`signup_source=matcha_x`), with `employee_schedule`/`huume`/`matcha_work`/`matcha_ops` all enabled. Locations include "Sunset Smile Dental — Downtown" (`e628e73e-1ee3-4b29-ba6d-a7e4cbc5e895`). Use it for matcha-work/Huume/schedule-editor testing instead of hunting for or creating a new company — verified working end-to-end against `/ops/schedule/editor` on 2026-08-26.

**Alternative**: `./scripts/dev.sh` — references a discontinued sister product; do not use.

**Agent sandbox**: `msandbox` (or `./scripts/agent-sandbox.sh`) runs Codex/Claude Code/OpenCode in an isolated
Docker container — no host home dir/Keychain/SSH-agent/Docker-socket — with full/no-approval execution inside
that boundary. `msandbox dev` runs this same `dev-remote.sh` with `AGENT_SANDBOX=1`. `build-and-push.sh` (needs
a Docker daemon) and Xcode/`platforms/**` builds (`scripts/xcode-build.sh`) don't run there — host only.
Full writeup: `docs/ops/AGENT_SANDBOX.md`.

```bash
# Server only (assumes DB tunnel open):
cd server && python3 run.py     # :8001

# Tests
cd server && python3 -m pytest tests/ -v
```

## Code Modification Rules

- Before modifying any function, component, or class, you MUST identify and read all files that import or depend on it.
- **When a new analytics/risk engine lands under `services/`, the same PR wires its records into whichever grounded pilots ground on that domain** (Legal / Broker / Handbook / HR / Analysis). Three of the four gaps the 2026-07-20 pilot-grounding review found were exactly this omission: a service computed something real and the pilot that should cite it never learned it existed. A corpus record is part of shipping the engine, not a follow-up.
- If a task involves data fetching, database schemas, or global state, you are required to load the entire schema and all relevant model files into your context *before* proposing or executing changes.
- When a Feature Flags row or Key Modules bullet carries a "→ full spec" pointer, read that file before working on the feature — its invariants live there now.

## Session cost hygiene

Keep per-session cost down — these are standing rules, follow them without being re-asked.

### Subagents (biggest cost driver)
- Spawn deliberately, not reflexively. One well-scoped query beats 3 parallel scouts.
- Don't spawn an Explore/search agent for a single-file lookup — use Grep/Read inline.
- A subagent should return the conclusion, not raw file dumps.

### Context size
- On a task switch, tell the user to `/clear`; mid-large-task, suggest `/compact`.
- Don't re-read files already read this session (the harness tracks file state).
- Keep reads scoped — pull the function/section needed, not the whole schema, unless the Code Modification Rules above require the full load.

### Long / loop / background sessions
- `/loop` and background agents: set an explicit stop condition — never leave one idle-running.
- Kill background agents when their work is done.

## Cloud / background sessions — code + PR only, never build/deploy

When run via the desktop app's cloud/background agent (branch prefix `claude/…`) for tasks like "review X and apply fixes": scope ends at **commit + open PR**. Never run `./scripts/build-and-push.sh`, `docker build`, `gh workflow run`, or otherwise trigger CI/deploy — the user reviews and merges by hand later, often after a token-window reset. `.github/workflows/deploy.yml` has no `pull_request` trigger at all (dropped 2026-07-24, moved to `workflow_dispatch`-only) — a PR from any session, cloud or otherwise, cannot reach it. The separate `ci.yml` (py_compile + `tsc --noEmit`, added the same day) does run on `pull_request`, but it has no Docker/deploy steps — don't add any there.

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

The server (`server/app/core/services/email/`) hard-blocks sends to these reserved domains as a defense-in-depth guard, but the rule above is the primary mitigation — don't invent realistic fake domains in the first place.

## Symbol Map — Where Things Live

Moved next to the code it indexes. Backend symbols: `server/CLAUDE.md` §"Symbol map (backend)". Frontend symbols: `client/CLAUDE.md` §"Symbol map (frontend)". Both auto-load when editing their trees.

## Claude Code Setup

This repo is configured for Claude Code with subtree docs, hooks, and project slash commands. The setup is captured in `docs/plans/CLAUDE_CODE_PLAN.md`.

### Subtree CLAUDE.md files (auto-load by directory)

| Path | Loads when editing in… |
|---|---|
| `CLAUDE.md` (this file) | anywhere |
| `server/CLAUDE.md` | `server/**` |
| `server/app/matcha/routes/CLAUDE.md` | `server/app/matcha/routes/**` — the router-zoo index |
| `server/app/matcha/routes/ir_incidents/CLAUDE.md` | inside the IR package — captures the 2026-05-16 split |
| `server/app/matcha/routes/employee_portal/CLAUDE.md` | inside the portal package — captures the 2026-07-26 split |
| `server/app/matcha/routes/dashboard/CLAUDE.md` | inside the dashboard package — captures the 2026-07-26 split |
| `server/app/core/routes/CLAUDE.md` | `server/app/core/routes/**` — the core router-zoo index, captures the 2026-07-25 split |
| `client/CLAUDE.md` | `client/**` |
| `server/app/matcha/services/huume/CLAUDE.md` | huume feature spec |
| `server/app/matcha/services/pilots/CLAUDE.md` | legal_defense/handbook_pilot/hr_pilot/ask_hr/analysis_pilot specs |
| `server/app/matcha/services/ems/CLAUDE.md` | ems feature spec |
| `server/app/matcha/services/training/CLAUDE.md` | training feature spec |
| `server/app/matcha/services/insurance/CLAUDE.md` | controls_evidence/limit_adequacy/driver_risk specs |
| `server/app/matcha/services/property/CLAUDE.md` | property feature spec |
| `server/app/matcha/services/scheduling/CLAUDE.md` | employee_schedule/schedule_intelligence specs |
| `server/app/matcha/services/workforce/CLAUDE.md` | workforce_compliance feature spec |
| `server/app/matcha/services/broker/CLAUDE.md` | risk_profile feature spec |
| `server/app/matcha/services/discipline/CLAUDE.md` | discipline module deep detail |
| `server/app/core/services/CLAUDE.md` | compliance_lite spec + vertical coverage + compliance evals |
| `server/app/workers/CLAUDE.md` | handbook_watch spec + pool-free rule + task deep detail |
| `server/app/werk/CLAUDE.md` | werk import boundary + werk_lite/werk_lite_calls_all_members specs |
| `server/app/matcha/services/benefits/CLAUDE.md` | benefits_admin feature spec |
| `server/app/matcha/services/inventory/CLAUDE.md` | inventory feature spec |

Subtree docs compose with this root file. When working in a subtree, the nearer doc has the specific conventions; this root has the cross-cutting product/database/test-data rules.

### Project slash commands (`/<name>`)

Repo-shared scaffolding lives in `.claude/commands/*.md`:

- `/add-feature-flag <name> <default>` — wires backend `DEFAULT_COMPANY_FEATURES` + CLAUDE.md table row + router/endpoint gate + `<FeatureGate>` + sidebar entry
- `/new-router <slug>` — scaffolds a FastAPI router with tenant-isolation pattern + asyncpg + audit-log + Pydantic models + mount in `routes/__init__.py`
- `/add-bulk-upload <entity>` — scaffolds the CSV-template + multipart upload pair. **Encodes the 2026-05-15 medcenter.com bounce-storm lessons**: defaults `send_invitations=False` on both backend and frontend, CSV template uses RFC 2606 reserved domains
- Compliance research commands (`/research-jurisdiction`, `/fill-gaps`, etc.) — pre-existing, for jurisdiction data work

### Post-edit hook

`.claude/hooks/post-edit-python.sh` runs after every `Edit`/`Write`/`MultiEdit`. On `.py` files it runs `python3 -m py_compile` (silent on success, surfaces `SyntaxError` with file+line on failure) plus an optional `ruff check` if installed. No TypeScript check at the hook level — a real typecheck is too slow per-edit; run `cd client && npx tsc -p tsconfig.app.json --noEmit` manually (the bare `npx tsc --noEmit` checks NOTHING — root tsconfig is `files: []` + project references, so it always exits 0).

Wired in `.claude/settings.json` (shared) — personal allowlist lives in `.claude/settings.local.json` (gitignored).

### Tool-level ignore (`.claudeignore`)

Explore/Grep agents skip generated/built/binary artifacts: `node_modules/`, `client/dist/`, `client/.vite/`, `__pycache__/`, `venv/`, `.pytest_cache/`, `client/src/generated/` (auto-regenerated), lock files, snapshots, Xcode build dirs, DaVinci cache, and secrets (`*.pem`, `*.env`, `token.json`).

## Dead References (ignore)

These are legacy artifacts from a discontinued sister product. Do **not** propose changes, cleanup, or modifications to them unless explicitly asked:

- `scripts/dev.sh` — references a `gummfit-agency/` directory that no longer exists. Use `scripts/dev-remote.sh` instead.
- `scripts/build-and-push.sh` — **still in active daily use** by the user for ECR pushes. The gumfit/gumm-local optional targets in it are dead, but the matcha backend/frontend/agent paths are live. Don't propose deleting it.
- `gumfit_admin` role in `server/app/core/models/auth.py` `UserRole` literal — kept for historical type safety; no live users.
- Any `Gummfit` / `gumfit` string in scripts, docs, or config.
