# Matcha

Multi-product monorepo: one FastAPI backend + shared Postgres serving several products, each isolated by package, API prefix, JWT scope, and table prefix.

## Products

| Product | What it is | Frontend | Backend | Live at |
|---|---|---|---|---|
| **Matcha** | HR compliance platform (tiers: Free, Lite, Essentials, X, Compliance, Pro) — IR/OSHA incidents, ER cases, employees, handbooks, compliance research, broker risk tooling | `client/` (React SPA) | `server/app/core/` + `server/app/matcha/` at `/api` | [hey-matcha.com](https://hey-matcha.com) |
| **Matcha-work** | Collaborative AI workspace — projects, threads, channels, inbox | `client/src/pages/work/` at `/work` (business), `/werk` (personal), `/werk-lite` (slack-style) | `server/app/matcha/routes/matcha_work.py` (`mw_*` tables) | hey-matcha.com/work |
| **Werk** | macOS desktop client for matcha-work | `platforms/desktop/Werk/` (SwiftUI) | same matcha-work backend | App Store bundle `com.ahnimal.matcha` |
| **Cappe** | Website builder (consumer brand **Gummfit**) — sites, templates, booking, custom domains | inside `client/` — host-routed (`client/src/pages/cappe/`) | `server/app/cappe/` at `/api/cappe` + tenant renderer on `*.gummfit.com` | [gummfit.com](https://gummfit.com) |
| **Tell-Us** | Rewards-for-feedback platform (consumer + brand sides) | `client/tellus/` — separate Vite app | `server/app/tellus/` at `/api/tellus` | hey-matcha.com/tellus |
| **MatchaTutor** | iOS language tutor (dormant) | `platforms/ios/` (SwiftUI) | matcha-work tutor endpoints | — |
| **Ops agent** | Internal leads/ops console | `agent-ui/` (Preact) | `server/agent/` standalone service :9100 | internal |

Matcha tiers are **config, not code forks** — differentiated by `companies.signup_source` + `enabled_features` flags (see `CLAUDE.md` for the full tier/flag matrix).

## Layout

```
client/     React SPA (Matcha all tiers + Cappe host-routed) + tellus/ sub-app
server/     FastAPI: app/{core, matcha, cappe, tellus} + agent/ + alembic migrations
platforms/  Native apps: desktop/ (Werk macOS), ios/ (MatchaTutor)
agent-ui/   Ops agent frontend (Preact)
scripts/    Dev + ops: dev-remote.sh, migrate-*, backups, blue-green deploy helpers
deploy/     Host nginx configs (source of truth), RDS/S3 provisioning, systemd
docs/       Plans, ops runbooks (docs/ops/DB_WORKFLOW.md), broker/hris/sales research
```

## Development

```bash
./scripts/dev-remote.sh     # backend :8001, frontend :5174, DB + Redis tunnels
```

Full conventions, DB safety rules, and product boundaries: `CLAUDE.md` (+ subtree CLAUDE.md files in `server/`, `client/`, `server/app/matcha/routes/`).

## Deploy

```bash
./scripts/build-and-push.sh --frontend-only   # build + push image(s) to ECR
./scripts/update-ec2.sh --matcha              # blue-green swap on the app EC2
```

Frontends alternate ports 8082↔8083, backend 8002↔8003 — host nginx proxies via `matcha_frontend`/`matcha_backend` upstream groups (never hardcode ports; see `deploy/nginx/README.md`). Database workflow (dev/prod sync, migrations, backups): `docs/ops/DB_WORKFLOW.md`.

## Stack

FastAPI + asyncpg + Celery/Redis · PostgreSQL (single shared instance, RDS) · React 18 + Vite + Tailwind · SwiftUI · Gemini (AI) · S3/CloudFront · Stripe · LiveKit · AWS EC2 + nginx blue-green
