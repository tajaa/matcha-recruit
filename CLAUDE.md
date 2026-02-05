# Matcha Recruit

## What This Is

AI-powered recruiting and HR platform. Two domains:

- **Matcha** — Recruiting (candidates, interviews, matching, offer letters) and HR ops (employees, onboarding, PTO, experience analytics)
- **Core** — Auth, admin, compliance monitoring, AI chat, policies, leads agent

This is the matcha app (`server/` + `client/`). A second app, Gummfit Agency (creator economy platform), lives in `gummfit-agency/` with its own server and client. See `ARCHITECTURE.md` for how the dual-app system works, and `gummfit-agency/CLAUDE.md` for gummfit-specific docs.

## Stack

- **Framework**: FastAPI + uvicorn (async)
- **Database**: PostgreSQL via asyncpg (connection pool)
- **Background jobs**: Celery + Redis
- **AI**: Google Gemini (API key or Vertex AI)
- **Storage**: S3 + CloudFront
- **Auth**: JWT (separate chat JWT secret)

## Database

**Do NOT start, check, or create any local Postgres containers.** The app reads `DATABASE_URL` from `.env` and that's it. The database is already running — just use it.

```
# .env already has this configured:
DATABASE_URL=postgresql://...
```

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
```

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
