# Matcha Recruit

## What This Is

AI-powered recruiting and HR platform. Two domains:

- **Matcha** — Recruiting (candidates, interviews, matching, offer letters) and HR ops (employees, onboarding, PTO, experience analytics)
- **Core** — Auth, admin, compliance monitoring, AI chat, policies, leads agent

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
