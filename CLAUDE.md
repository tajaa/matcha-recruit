# Matcha Recruit

## Products

Three products share this codebase. Differentiated at signup via
`companies.signup_source` and routed in the UI by
`client/src/utils/tier.ts` + `client/src/components/TenantSidebar.tsx`.

| Product             | Billing             | Signup path                                    | `signup_source`        | Sidebar variant       |
|---------------------|---------------------|------------------------------------------------|------------------------|-----------------------|
| **Matcha**          | Contract / invoice  | Bespoke sales → `BetaRegister` invite token    | `bespoke` (default)    | `ClientSidebar` (full)|
| **Matcha Work**     | Stripe (subs/tokens)| `BetaRegister` (personal) or inside Matcha     | `bespoke` or personal  | `ClientSidebar` AI group / desktop app |
| **Matcha Cap**      | Stripe (one-time + free) | `IrSignup` or `ResourcesSignup`           | `ir_only_self_serve` / `resources_free` | `IrSidebar` / `ResourcesFreeSidebar` |

### Matcha — full platform
- Surface: full `ClientSidebar` nav (Dashboard, Company, HR Ops, Compliance, Communication, Safety, AI).
- Routes: `/app/*` registered in `client/src/App.tsx`.
- Backend: everything under `server/app/matcha/` plus `server/app/core/`.
- Companies created with `signup_source='bespoke'` (default) by admins after a sales call. Approved → all platform features available, gated per-company by `companies.enabled_features` JSONB.
- Discipline is an opt-in feature flag here: `enabled_features.discipline=true` per company.

### Matcha Work — collaborative workspace
- Surface: `client/src/pages/work/*` + `client/src/layouts/WorkLayout.tsx`. Mounted at `/work/*` in `App.tsx`.
- Backend: `server/app/matcha/routes/matcha_work.py`, `server/app/matcha/services/project_service.py`, tables prefixed `mw_*`.
- macOS desktop client: `desktop/Matcha/` (SwiftUI). `AppState.isPlusActive` from `Subscription.isPersonalPlus` controls Plus features.
- **Personal mode**: user `role='individual'`. Signup via `BetaRegister.tsx` (`/auth/beta?token=…`) → redirected to `/work`. Stripe subscription `matcha_work_personal` ($20/mo) via `POST /api/checkout/personal` (`server/app/matcha/routes/billing.py`).
- **Business mode**: user `role='client'` inside an existing Matcha company. Token packs purchased via `POST /api/checkout`. Sidebar entry in `ClientSidebar.tsx` AI group → `/work`.
- Stripe-gated sub-features: `paid_channel_creator`, `channel_job_postings` in `server/app/core/feature_flags.py`.

### Matcha Cap — lite self-serve bundle
Self-serve, Stripe-purchasable. Three sub-surfaces today:

**IR (Cap)**
- Signup: `client/src/pages/auth/IrSignup.tsx` → `POST /auth/register/business` with `tier='ir_only'`. Sets `companies.signup_source='ir_only_self_serve'` and turns on `enabled_features.incidents = true`, `employees = true`, `discipline = true` (the Cap bundle).
- Sidebar: `IrSidebar` (incidents / employees / company only) selected by `isIrOnlyTier()` in `client/src/utils/tier.ts`.
- Onboarding: `client/src/features/ir-onboarding/IrOnboardingWizard.tsx` (4 steps); completion stamps `companies.ir_onboarding_completed_at`.
- Backend routes: `ir_incidents_router` (`/ir/incidents/*`) and `ir_onboarding_router` (`/ir-onboarding/*`) in `server/app/matcha/routes/__init__.py`.
- Stripe upgrade: `POST /resources/upgrade/ir/checkout` (`server/app/core/routes/resources.py`) for the IR-upgrade one-time charge.

**Discipline (Cap, just shipped)**
- Sidebar entry feature-gated via `NavItem.feature='discipline'` in `client/src/components/ClientSidebar.tsx` HR Ops group.
- Backend: `server/app/matcha/routes/discipline.py`, engine in `server/app/matcha/services/discipline_engine.py`, signature provider abstraction (DocuSeal) in `server/app/matcha/services/signature_provider.py`.
- Tables: `progressive_discipline`, `discipline_policy_mapping`, `discipline_audit_log`.
- Feature flag: `enabled_features.discipline` (default `False`); `KNOWN_PLATFORM_ITEMS` in `server/app/core/routes/admin.py` includes `discipline`.
- Daily expiry sweep: `server/app/workers/tasks/discipline_expiry.py` gated by `scheduler_settings.task_key='discipline_expiry'`.

**Resources (Cap)**
- Signup: `client/src/pages/auth/ResourcesSignup.tsx` → `tier='resources_free'`. Sets `signup_source='resources_free'`, no enabled features.
- Sidebar: `ResourcesFreeSidebar` (with upgrade panel) selected by `isResourcesFreeTier()`.
- Frontend routes: `/resources/*` in `client/src/App.tsx`. Most are gated by `<RequireBusinessAccount>` so a non-business user is bounced to `/auth/resources-signup`.
- Backend: `server/app/core/routes/resources.py`. Public landing pages + business-gated tools (templates, state guides, calculators, audit, glossary, job descriptions).

**Current vs intended (gap callout)**:
Matcha Cap is described as a single Stripe-purchasable bundle of IR + Discipline + Resources.
- `ir_only_self_serve` signup now enables `incidents` + `employees` + `discipline` (the IR + Discipline half of the bundle), and `IrSidebar` exposes a Discipline nav entry gated by the flag.
- `resources_free` is still a distinct signup tier with its own `ResourcesFreeSidebar` and no overlap with `ir_only_self_serve` — the two halves of "Cap" don't share a tenant. Future work: pair Resources access into Cap signups so the bundle is a single tier rather than two.
- The `discipline` flag itself is still default `False` in `DEFAULT_COMPANY_FEATURES`; bespoke companies opt in via the admin Features page.

When a Cap user URL-hops to a feature they don't have (e.g. `/app/policies`, `/app/er-copilot`), `<FeatureGate>` (`client/src/components/FeatureGate.tsx`) renders `<UpgradeUpsellCard>` with an in-app "Talk to sales" inquiry form (`POST /api/resources/upgrade/inquiry`) instead of a 403 or empty page.

### Auxiliary surfaces (share codebase, not products)
- **Admin** — `AdminSidebar`, `/admin/*` routes; internal tooling (companies, jurisdiction data, payer data, broker mgmt).
- **Broker** — `BrokerSidebar`, `/broker/*` routes; for HR brokers managing multiple client companies.
- **Candidate / Employee portals** — public-token routes (`/candidate-interview/:token`, `/s/:token`); employee self-service through `employee_portal_router`.

## Stack

- **Framework**: FastAPI + uvicorn (async)
- **Database**: PostgreSQL via asyncpg (connection pool)
- **Background jobs**: Celery + Redis
- **AI**: Google Gemini (API key or Vertex AI)
- **Storage**: S3 + CloudFront
- **Auth**: JWT (separate chat JWT secret)

## Database

**⚠️ CRITICAL: The database is a PRODUCTION PostgreSQL on a remote EC2 instance (3.101.83.217), NOT a local container.** `DATABASE_URL` in `.env` connects to it (possibly via SSH tunnel). Treat every database operation as production.

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
│   ├── core/                       # Auth, admin, compliance, AI chat, policies
│   │   ├── models/
│   │   ├── routes/
│   │   └── services/
│   └── matcha/                     # Recruiting + HR domain
│       ├── models/
│       ├── routes/
│       ├── services/
│       └── workers/
├── tests/
└── alembic/

client/src/
├── api/                            # API client layer
│   ├── client.ts                   # Main fetch wrapper, auth, all API calls
│   ├── compliance.ts               # Compliance-specific API calls
│   ├── chatClient.ts               # Chat WebSocket/API client
│   ├── portal.ts                   # Portal API calls
│   └── leave.ts                    # Leave/PTO API calls
├── components/                     # Shared UI components
│   ├── chat/                       # Chat UI components
│   ├── er/                         # ER Copilot components
│   ├── ir/                         # IR incident components
│   ├── matcha-work/                # Recruiting-specific components
│   └── video/                      # Video interview components
├── context/
│   ├── AuthContext.tsx             # Auth state, user/role/feature access
│   └── ChatAuthContext.tsx         # Separate JWT context for chat
├── features/                       # Feature-based modules (preferred pattern)
│   ├── employee-intake/
│   ├── feature-guides/
│   └── handbook-wizard/
├── hooks/                          # Domain-specific custom hooks
│   ├── compliance/
│   ├── employees/
│   ├── er/
│   ├── ir/
│   └── offer-letters/
├── pages/                          # Route-level page components
│   ├── admin/
│   ├── broker/
│   ├── chat/
│   ├── landing/
│   └── portal/
├── types/                          # Shared TypeScript types
├── utils/                          # Pure utility functions
├── data/                           # Static/seed data
└── generated/                      # Auto-generated types (do not edit)
```

## Frontend ↔ Backend Connection

**API base URL**: `VITE_API_URL` env var, falls back to `/api` (proxied in dev via Vite).

**Auth flow**:
1. Login/register POSTs to `/api/auth/*` → returns `access_token` + `refresh_token`
2. Tokens stored in `localStorage` as `matcha_access_token` / `matcha_refresh_token`
3. All requests attach `Authorization: Bearer <access_token>` header
4. On 401, `client.ts` automatically refreshes via `/api/auth/refresh` and retries
5. `AuthContext.tsx` wraps the app — provides `user`, `hasRole()`, `hasFeature()`, `companyFeatures`

**Chat uses a separate JWT** (`ChatAuthContext.tsx`) — different secret, different token lifecycle.

**WebSocket**: Chat connects via WebSocket (not HTTP) — handled in `api/chatClient.ts`.

## User Roles

Four roles defined in `app/core/models/auth.py`:

| Role       | Description                                                               |
| ---------- | ------------------------------------------------------------------------- |
| `admin`    | Platform admin, full access                                               |
| `client`   | Business user (linked to a company) — this is what "business admin" means |
| `candidate`| Job seeker                                                                |
| `employee` | Company employee (HR portal)                                              |

**Auth dependencies** are split across two files:

- `app/core/dependencies.py` — `require_admin`, `require_candidate`
- `app/matcha/dependencies.py` — `require_client`, `require_employee`, `require_admin_or_client`

**Company approval flow**: Business registers → `status='pending'` → admin approves → features enabled. Note: `status IS NULL` is treated as approved for legacy rows.

## Feature Flags

Companies have `enabled_features` (JSONB) controlling access to: `offer_letters`, `policies`, `compliance`, `employees`, `vibe_checks`, `enps`, `performance_reviews`, `er_copilot`, `incidents`, `time_off`.

## Key Modules

- **Compliance** (`core/services/compliance_service.py`) — Jurisdiction-aware compliance checking with Gemini AI, preemption rules, tiered data (structured → repository → Gemini research)
- **AI Chat** (`core/services/ai_chat.py`) — WebSocket chat with local Qwen model or Gemini
- **IR Incidents** (`matcha/routes/ir_incidents.py`) — Safety/behavioral incident reporting with AI analysis
- **ER Copilot** (`matcha/routes/er_copilot.py`) — Employment relations case management
- **Interviews** (`matcha/services/`) — Voice interviews via Gemini Live API

## Running Tests

```bash
cd server
python3 -m pytest tests/ -v
```

## Running the Server

```bash
cd server
python3 run.py
# Starts on port 8001
```

## Running Both Apps

```bash
./scripts/dev.sh
# Matcha on :8001/:5174, Gummfit on :8003/:5175
```

## Code Modification Rules

- Before modifying any function, component, or class, you MUST identify and read all files that import or depend on it.
- If a task involves data fetching, database schemas, or global state, you are required to load the entire schema and all relevant model files into your context *before* proposing or executing changes.
