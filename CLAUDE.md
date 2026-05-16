# Matcha Recruit

Four products share this codebase: **Free** (resources hub), **Matcha-lite** (paid IR/HR-records bundle), **Matcha** (full bespoke platform), and **Matcha-work** (collaborative AI workspace, web + macOS).

## Products

Differentiated at signup via `companies.signup_source` and routed in the UI by `client/src/utils/tier.ts` + `client/src/components/TenantSidebar.tsx`.

| Product | Signup page | `tier` sent | `signup_source` | Sidebar | Routes | Billing |
|---|---|---|---|---|---|---|
| **Free** | `pages/auth/ResourcesSignup.tsx` | `resources_free` | `resources_free` | `ResourcesFreeSidebar` | `/resources/*` | None — upgrade CTA |
| **Matcha-lite** | `pages/auth/MatchaLiteSignup.tsx` | `matcha_lite` | `matcha_lite` | `IrSidebar` once paid; `MatchaLitePendingSidebar` while pending | `/ir/*` | Stripe sub, headcount-based |
| **Matcha (platform)** | `pages/BetaRegister.tsx` (token) or admin-created post-sale | n/a | `bespoke` (default) / `invite` | `ClientSidebar` (full nav) | `/app/*` | Contract / invoice |
| **Matcha-work** | `pages/BetaRegister.tsx` (personal token) → `/work`; or inside Matcha company | n/a | `bespoke` (personal: `is_personal=true`) | `ClientSidebar` AI group; macOS app | `/work/*` | Stripe `matcha_work_personal` $20/mo or business token packs |

Sidebar dispatch in `client/src/components/TenantSidebar.tsx`. Tier-check helpers (`isIrOnlyTier`, `isMatchaLitePending`, `isResourcesFreeTier`) in `client/src/utils/tier.ts`.

### Free — resources hub
- Marketing/upgrade landing for self-serve signups. No paid features.
- All `enabled_features` off; gated by `<RequireBusinessAccount>` (`client/src/components/`).
- Backend: `server/app/core/routes/resources.py`. Public landing pages + business-gated tools (templates, state guides, calculators, audit, glossary, job descriptions).
- Free→paid path: `<UpgradeUpsellCard>` ("Talk to sales") posts to `/api/resources/upgrade/inquiry`.

### Matcha-lite — paid IR + HR records + discipline
- Stripe-purchasable, headcount-based (max 300 employees).
- Checkout: `POST /resources/checkout/lite` (`server/app/core/routes/resources.py`). Stripe webhook `checkout.session.completed` flips `enabled_features.incidents=true` — until then `MatchaLitePendingSidebar` shows the Subscribe CTA.
- Once paid: `enabled_features.incidents`, `employees`, `discipline` are on; `IrSidebar` exposes incidents, employees, discipline, company.
- Backend routers: `ir_incidents_router` (`/ir/incidents/*`), `ir_onboarding_router` (`/ir-onboarding/*`) in `server/app/matcha/routes/__init__.py`.
- Onboarding: `client/src/features/ir-onboarding/IrOnboardingWizard.tsx`; completion stamps `companies.ir_onboarding_completed_at`.
- Legacy `pages/auth/IrSignup.tsx` (`tier='ir_only'`, `signup_source='ir_only_self_serve'`) still wired at `/ir/signup` for private beta — also lands on `IrSidebar`.

### Matcha — full bespoke platform
- Companies created with `signup_source='bespoke'` (default) by admins post-sales call, or via `BetaRegister.tsx` invite tokens.
- Sidebar: `ClientSidebar` (Dashboard, Company, HR Ops, Compliance, Communication, Safety, AI groups).
- Routes: `/app/*` registered in `client/src/App.tsx`.
- Backend: everything under `server/app/matcha/` plus `server/app/core/`.
- Per-company access via `companies.enabled_features` JSONB. When a user URL-hops to a feature they don't have, `<FeatureGate>` (`client/src/components/FeatureGate.tsx`) renders `<UpgradeUpsellCard>` instead of a 403.

### Matcha-work — collaborative AI workspace
**Naming convention**: the **web** workspace surface (this section) is referred to as **matcha-work**; the **macOS desktop** workspace is referred to as **werk** (`desktop/Werk/`). Both share the same backend (`server/app/matcha/routes/matcha_work.py`) and `mw_*` tables — only the client differs. When asked to ship a feature, confirm which surface is meant before editing files.

- Surface: `client/src/pages/work/*` + `client/src/layouts/WorkLayout.tsx`. Mounted at `/work/*` in `App.tsx`.
- Backend: `server/app/matcha/routes/matcha_work.py`, `server/app/matcha/services/project_service.py`. Tables prefixed `mw_*`.
- macOS desktop client (**werk**): `desktop/Werk/` (SwiftUI). Xcode project name is still `Matcha.xcodeproj` and bundle ID `com.ahnimal.matcha` — App Store identity is unchanged; only the working directory and conceptual product name differ. `AppState.isPlusActive` from `Subscription.isPersonalPlus` controls Plus features.
- **Personal mode**: user `role='individual'`. Signup via `BetaRegister.tsx` (`/auth/beta?token=…`) → redirected to `/work`. Stripe sub `matcha_work_personal` ($20/mo) via `POST /api/checkout/personal` (`server/app/matcha/routes/billing.py`).
- **Business mode**: user `role='client'` inside a Matcha company. Token packs purchased via `POST /api/checkout`. Sidebar entry in `ClientSidebar.tsx` AI group → `/work`.
- Surfaces inside: projects, threads, channels (real-time WebSocket), inbox (DMs), people/connections, anonymous incident report intake.
- Stripe-gated sub-features: `paid_channel_creator`, `channel_job_postings` in `server/app/core/feature_flags.py`.

### Auxiliary surfaces (share codebase, not products)
- **Admin** — `AdminSidebar`, `/admin/*` routes; internal tooling (companies, jurisdiction data, payer data, broker mgmt).
- **Broker** — `BrokerSidebar`, `/broker/*` routes; HR brokers managing multiple client companies.
- **Candidate / Employee portals** — public-token routes (`/candidate-interview/:token`, `/s/:token`); employee self-service through `employee_portal_router`.
- **Public anonymous report** — `/report/:token` (`server/app/matcha/routes/inbound_email.py`); per-company token-gated single-use form.

## Stack

- **Framework**: FastAPI + uvicorn (async)
- **Database**: PostgreSQL via asyncpg (connection pool)
- **Background jobs**: Celery + Redis
- **AI**: Google Gemini via `GEMINI_API_KEY` (Vertex used only for Gemini Live API in voice interviews)
- **Storage**: S3 + CloudFront (`server/app/core/services/storage.py`)
- **Auth**: JWT
- **Deployment**: AWS EC2 — Nginx reverse proxy + Postgres on dedicated EC2 (acts as RDS, runs directly on host, not Docker).

## Database

**⚠️ CRITICAL: The database is a PRODUCTION PostgreSQL on a remote EC2 instance (3.101.83.217), NOT a local container.** `DATABASE_URL` in `.env` connects to it (typically via SSH tunnel from `dev-remote.sh`). Treat every database operation as production.

**NEVER do any of the following without explicit user approval:**
- CREATE ROLE / DROP ROLE
- CREATE TABLE / DROP TABLE on real tables
- Run Alembic migrations (`alembic upgrade head`)
- Any DDL (ALTER TABLE, CREATE INDEX, etc.) directly
- Write tests that create/drop tables, roles, or modify schema on the live DB
- Assume you can freely experiment with the database

**For integration tests that need DB access:** write them to be run manually by the user, and use temporary/test data that won't affect production. Never auto-run DB-mutating tests.

**SSH access to DB server:** `ssh -i roonMT-arm.pem ec2-user@3.101.83.217`
**DB name in production:** `matcha` (not `matcha_recruit`)
**DB user:** `matcha` (currently superuser — this is part of the RLS problem)

Schema is managed via Alembic migrations in `server/alembic/versions/`. Tables are also bootstrapped in `server/app/database.py:init_db()` for fresh setups. When adding new tables, use Alembic migrations.

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
│   │   ├── routes/                 # ir_incidents, matcha_work, discipline, er_copilot, …
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
| `handbooks` | ✅ | Employee handbook generator |
| `accommodations` | ✅ | Accommodation case mgmt |
| `risk_assessment` | ✅ | Risk-assessment dashboard |
| `discipline` | ✅ | Progressive discipline workflow |
| `matcha_work` | ❌ | Projects / threads / channels |
| `training` | ❌ | Training programs |
| `i9` | ❌ | I-9 compliance |
| `cobra` | ❌ | COBRA admin |
| `separation_agreements` | ❌ | Separation doc workflow |
| `credential_templates` | ❌ | Credentialing templates |
| `hris_import` | ❌ | HRIS sync |
| `paid_channel_creator` | ❌ | Stripe-gated paid channels |
| `channel_job_postings` | ❌ | Stripe-gated job postings in channels |

`incidents` and `employees` are not in the defaults — they're flipped on by tier-specific flows (Matcha-lite Stripe webhook, IR-only signup) or admin toggle.

## Key Modules

- **Compliance** (`core/services/compliance_service.py`) — Jurisdiction-aware compliance checking with Gemini AI; preemption rules, tiered data (structured → repository → Gemini research).
- **AI Chat** (`core/services/ai_chat.py`) — WebSocket chat with local Qwen model or Gemini.
- **Matcha Work** (`matcha/routes/matcha_work.py` + `services/project_service.py`, `services/matcha_work_ai.py`) — projects, threads, channels, inbox, AI directives.
- **Channels** (`matcha/services/channels_service.py`, `mw_channels*` tables) — real-time WebSocket messaging, paid channels, member presence.
- **IR Incidents** (`matcha/routes/ir_incidents.py`) — safety/behavioral incident reporting + AI analysis. Public anonymous intake at `routes/inbound_email.py`.
- **Discipline** (`matcha/routes/discipline.py` + `services/discipline_engine.py`, signature provider abstraction in `services/signature_provider.py`).
- **ER Copilot** (`matcha/routes/er_copilot.py`) — employment-relations case mgmt.
- **Risk Assessment** (`matcha/routes/risk_assessment.py`).
- **Interviews** (`matcha/services/`) — voice interviews via Gemini Live API.

## Background Workers (Celery)

Celery worker container `matcha-worker` runs everything that can't run inline. Single concurrency, restarts after 5 tasks (`--max-tasks-per-child=5`) to recycle memory. `task_acks_late=True` + `max_retries=3` so OOM-killed tasks retry.

Scheduling model: no celery-beat. A systemd timer on the EC2 host restarts the worker every 15 min, and `@worker_ready` in `app/workers/celery_app.py` re-dispatches the periodic tasks on startup. Each scheduled task is gated by a `scheduler_settings` row, defaulting to disabled.

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

## Local Development

**Primary script**: `./scripts/dev-remote.sh` — SSH-tunnels Postgres from EC2 (`3.101.83.217:5432`), starts Redis tunnel, backend on `:8001`, frontend on `:5174`, local chat model on `:8080`. Requires `roonMT-arm.pem` at repo root.

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

## Dead References (ignore)

These are legacy artifacts from a discontinued sister product. Do **not** propose changes, cleanup, or modifications to them unless explicitly asked:

- `scripts/dev.sh` and `build-and-push.sh` — reference a `gummfit-agency/` directory that no longer exists. Use `scripts/dev-remote.sh` instead.
- `gumfit_admin` role in `server/app/core/models/auth.py` `UserRole` literal — kept for historical type safety; no live users.
- Any `Gummfit` / `gumfit` string in scripts, docs, or config.
