# Gummfit Agency

## What This Is

Creator economy platform. Connects creators/influencers with agencies for brand deals, campaigns, and affiliate partnerships.

## Stack

- **Framework**: FastAPI + uvicorn (async)
- **Database**: PostgreSQL via asyncpg (shared with matcha-recruit)
- **Storage**: S3 + CloudFront (shared with matcha-recruit)
- **Auth**: JWT (shared secret with matcha-recruit)

## Database

**Same database as matcha-recruit.** Both apps read `DATABASE_URL` from `.env`. Tables are bootstrapped in `server/app/database.py:init_db()` using `CREATE TABLE IF NOT EXISTS`.

## Directory Structure

```
gummfit-agency/
├── server/
│   ├── run.py                       # Entry point (uvicorn, port 8003)
│   ├── app/
│   │   ├── main.py                  # FastAPI app, lifespan, CORS, router mounting
│   │   ├── config.py                # Settings (db, jwt, s3, redis)
│   │   ├── database.py              # asyncpg pool + init_db() for gummfit tables
│   │   ├── dependencies.py          # get_current_user, require_roles (JWT validation)
│   │   ├── models/
│   │   │   └── auth.py              # UserRole, CurrentUser, registration models
│   │   ├── services/
│   │   │   ├── auth.py              # JWT token management, password hashing
│   │   │   └── storage.py           # S3 upload/delete
│   │   ├── routes/
│   │   │   └── auth.py              # login, register, /me, refresh, change-password
│   │   └── gummfit/                 # Domain code
│   │       ├── dependencies.py      # Creator/agency role checks
│   │       ├── models/              # Pydantic models per domain
│   │       ├── routes/              # API endpoints per domain
│   │       └── services/
│   ├── requirements.txt
│   └── Dockerfile
├── client/                          # Standalone React app (Vite + Tailwind)
│   ├── src/
│   │   ├── App.tsx                  # Gummfit-only routes
│   │   ├── api/client.ts            # API client
│   │   ├── pages/                   # Creator, agency, admin pages
│   │   ├── components/              # Layout, shared components
│   │   └── types/                   # TypeScript types
│   ├── package.json
│   └── Dockerfile
└── CLAUDE.md                        # This file
```

## User Roles

| Role           | Description                                    |
| -------------- | ---------------------------------------------- |
| `creator`      | Content creator / influencer                   |
| `agency`       | Talent or brand agency (linked via membership) |
| `gumfit_admin` | Platform admin for gummfit                     |

## Key Modules

- **Creators** — Profile management, revenue tracking, expenses, platform connections
- **Agencies** — Agency profiles, team members, creator discovery
- **Deals** — Brand deal marketplace, applications, contracts, payments
- **Campaigns** — Limit-order deal system, offers, escrow payments, affiliate links
- **GumFit Admin** — Platform management (creators, agencies, users, invites, assets)

## Running the Server

```bash
cd gummfit-agency/server
python run.py
# Starts on port 8003
```

## Running the Client

```bash
cd gummfit-agency/client
npm run dev
# Starts on port 5175
```

## Running Tests

```bash
cd gummfit-agency/server
python3 -m pytest tests/ -v
```
