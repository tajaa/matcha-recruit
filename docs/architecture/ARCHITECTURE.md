# Dual-App Architecture

This repo contains two independent applications that share a database, JWT secret, and S3 storage.

## Apps

| App | What it does | Server | Client |
|-----|-------------|--------|--------|
| **Matcha** | Recruiting, HR, compliance | `server/` | `client/` |
| **Gummfit** | Creator economy, brand deals | `gummfit-agency/server/` | `gummfit-agency/client/` |

Each app is fully self-contained with its own FastAPI backend, React frontend, Dockerfile, and dependencies. An LLM CLI scoped to either `server/` + `client/` or `gummfit-agency/` sees everything it needs.

## Repo Layout

```
matcha-recruit/
  server/                    # Matcha backend (FastAPI)
  client/                    # Matcha frontend (React + Vite)
  gummfit-agency/            # Self-contained gummfit app
    server/                  #   Own FastAPI backend
    client/                  #   Own React frontend
    CLAUDE.md                #   Gummfit-specific project docs
  docker-compose.yml         # All services + Redis
  scripts/dev.sh             # tmux launcher for both apps
  build-and-push.sh          # ECR build/push with per-service flags
  CLAUDE.md                  # Matcha-specific project docs
  ARCHITECTURE.md            # This file
```

## Shared Infrastructure

Both apps connect to the same Postgres database and use the same JWT secret, so a user authenticated in one app has valid tokens for the other. They share S3/CloudFront for file storage and Redis for caching.

**What's shared:**
- `DATABASE_URL` (same Postgres instance, same tables)
- `JWT_SECRET_KEY` / `JWT_ALGORITHM` (cross-app token validity)
- S3 bucket + CloudFront domain
- Redis instance

**What's NOT shared:**
- Application code (completely separate codebases)
- Ports (no overlap)
- npm dependencies (separate `node_modules`)
- Python venvs (separate `requirements.txt`)
- Docker images (separate ECR repos)

## Ports

| Service | Dev | Docker |
|---------|-----|--------|
| Matcha backend | 8001 | 8002 |
| Matcha frontend | 5174 | 8082 |
| Gummfit backend | 8003 | 8003 |
| Gummfit frontend | 5175 | 8083 |
| PostgreSQL | 5432 | -- |
| Redis | 6380 | 6379 |

Matcha owns port 8001 in dev (already deployed). Gummfit uses 8003 to avoid conflicts.

## User Roles

The `users` table has a single `role` column. Each app only handles its own roles:

| Role | App | Description |
|------|-----|-------------|
| `admin` | Matcha | Platform admin |
| `client` | Matcha | Business user (linked to company) |
| `candidate` | Matcha | Job seeker |
| `employee` | Matcha | Company employee |
| `creator` | Gummfit | Content creator / influencer |
| `agency` | Gummfit | Talent or brand agency |
| `gumfit_admin` | Gummfit | Gummfit platform admin |

Both apps share the `users` table. Matcha's login only redirects matcha roles; gummfit's login only redirects gummfit roles. The JWT tokens contain the role, so each app's auth middleware can enforce access.

## Token Namespacing

To prevent cross-app localStorage collisions when both frontends run on the same domain:

- Matcha: `access_token` / `refresh_token`
- Gummfit: `gummfit_access_token` / `gummfit_refresh_token`

## Database

Both apps use `CREATE TABLE IF NOT EXISTS` in their `init_db()` functions. Matcha's tables are bootstrapped in `server/app/database.py`, gummfit's in `gummfit-agency/server/app/database.py`. Since they share one Postgres instance, all tables coexist. Matcha also uses Alembic for migrations.

## Running Locally

### All at once (recommended)
```bash
./scripts/dev.sh
```
This starts a tmux session with two windows:
- **dev** window: Matcha backend + Celery worker + Matcha frontend
- **gumfit** window: Gummfit backend + Gummfit frontend

### Individually
```bash
# Matcha
cd server && python run.py          # :8001
cd client && npm run dev            # :5174

# Gummfit
cd gummfit-agency/server && python run.py    # :8003
cd gummfit-agency/client && npm run dev      # :5175
```

## Docker

```bash
# All services
docker compose up

# Just matcha
docker compose up matcha-backend matcha-frontend redis

# Just gummfit
docker compose up gummfit-backend gummfit-frontend redis
```

## Building & Deploying

```bash
# Matcha only (default)
./build-and-push.sh

# Gummfit only
./build-and-push.sh --gummfit

# Everything
./build-and-push.sh --all

# Individual services
./build-and-push.sh --gummfit-backend
./build-and-push.sh --gummfit-frontend
```

ECR repositories: `matcha-backend`, `matcha-frontend`, `gummfit-backend`, `gummfit-frontend`.

## Adding a New App

Follow the gummfit pattern:
1. Create `<app-name>/server/` with its own FastAPI app, config, database init, auth routes
2. Create `<app-name>/client/` with its own React app, API client, routing
3. Pick a unique port pair (e.g., 8005/8085)
4. Add services to `docker-compose.yml`
5. Add build targets to `build-and-push.sh`
6. Add tmux window to `scripts/dev.sh`
7. Namespace localStorage tokens to avoid collisions
