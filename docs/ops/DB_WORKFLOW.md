# Dev ↔ Prod Database Workflow

How the two Matcha Postgres databases relate, and the scripts that move schema and
data between them. Companion to [`DB_ENCRYPTION_RUNBOOK.md`](./DB_ENCRYPTION_RUNBOOK.md)
(which covers the encrypted-sidecar cutover).

## Topology

Two Postgres **containers on one DB EC2** (`3.101.83.217`):

| Container | Port | Role | Who connects |
|---|---|---|---|
| `matcha-postgres-prod` | 5433 | **PROD** (encrypted sidecar) | app EC2 `54.177.107.107`; hey-matcha.com |
| `matcha-postgres` | 5432 | **DEV** (+ 8 other apps' DBs) | your laptop via `dev-remote.sh` SSH tunnel |

App containers (backend/worker/frontend/redis/livekit) run on the separate app EC2
`54.177.107.107` and point at prod `:5433`.

> The root `CLAUDE.md` line "Postgres runs directly on the host, NOT in Docker" is
> stale — it's two containers, as above.

## The two flows

```
                 schema (alembic)                       data (anonymized)
   DEV  ──────────────────────────────▶  PROD     PROD ──────────────────────────▶ DEV
        migrate-dev.sh   migrate-prod.sh                 refresh-dev-from-prod.sh
```

- **Schema flows dev → prod.** You author an Alembic migration, apply it to dev, test,
  then apply the same revision to prod. Both directions are now scripted and symmetric.
- **Data flows prod → dev.** Periodically refresh dev with an anonymized clone of prod
  so local dev mirrors real (scrubbed) data. This is the backflow that was previously
  missing — dev and prod used to diverge with no way to reconcile.

## Scripts

| Script | Tunnels / acts on | What it does |
|---|---|---|
| `scripts/dev-remote.sh` | dev `:5432` | Start the local stack (tunnel + backend + worker + frontend). Does **not** run migrations. |
| `scripts/migrate-dev.sh` | dev `:5432` | `alembic upgrade head` against dev. Reuses an existing dev-remote tunnel if present. |
| `scripts/migrate-prod.sh` | prod `:5433` | `alembic upgrade head` against prod (reads `PROD_DATABASE_URL` from `server/.env`). |
| `scripts/refresh-dev-from-prod.sh` | both, host-side | Clone prod → dev and anonymize. See below. |
| `scripts/backups.sh` | DB host | Convenience CLI over the S3 backup bucket (list/latest/create/download/restore/size). |
| `scripts/sql/anonymize_dev.sql` | — | PII/secret scrub applied during a refresh. |

### Typical schema change

```bash
cd server && ./venv/bin/alembic revision -m "add foo"   # author
# ...edit the migration...
./scripts/migrate-dev.sh      # apply to dev, then test locally
./scripts/migrate-prod.sh     # apply the SAME revision to prod
```

Applying to **both** is mandatory — applying to only one is exactly the drift that
caused the `mw_tasks.pipeline_column` 500s. `alembic_version` should match on both DBs
afterward.

### Refresh dev from prod (close the backflow gap)

```bash
./scripts/refresh-dev-from-prod.sh --dry-run   # clone+anonymize into matcha_new, NO swap
# inspect matcha_new on the host, confirm scrub is clean, then:
./scripts/refresh-dev-from-prod.sh             # full run (rename-swap)
./scripts/dev-remote.sh                        # reconnect
```

What it does, all host-side (no customer data leaves the EC2 box):

1. **Snapshot** dev → `/home/ec2-user/dev-snapshots/dev_pre_refresh_<ts>.sql.gz` (keeps last 5).
2. **Stage** a fresh `matcha_new`.
3. **Clone** `pg_dump matcha-postgres-prod | pg_restore → matcha_new` (host-local pipe).
4. **Anonymize** `matcha_new` with `anonymize_dev.sql`.
5. **Swap** `matcha → matcha_old_<ts>`, `matcha_new → matcha` (keeps 1 old DB).
6. **Verify** counts + assert zero non-`@example.com` user emails.

Safety: it refuses if the target container name contains `prod`, requires typing
`refresh-dev`, and only ever rebuilds `matcha-postgres` (dev); prod is read-only as the
`pg_dump` source. A failed clone leaves the live dev DB untouched (the swap is last).

After a refresh, **all dev users share one password** (`devpass123`, override with
`DEV_LOGIN_PASSWORD=`). The script prints sample `admin`/`client`/`individual` emails to
log in with. Refresh also resets dev's `alembic_version` to prod's — re-run
`migrate-dev.sh` afterward if you have un-shipped local migrations.

### What anonymize_dev.sql scrubs

Emails → reserved domains; person + company names → synthetic; phones/addresses →
nulled; all `users.password_hash` → the dev hash; tokens/secrets (reset, invite, SSO
cert, OAuth, webhook, integration secrets, `gmail_token`) → nulled/randomized; Stripe
IDs → fake. **Kept for realism:** free-text narratives (incident descriptions,
offer-letter benefits, message bodies, company summaries). Extend the SQL if you need
those gone too. The column list is validated against the live schema; the run is wrapped
in a transaction with `ON_ERROR_STOP`, so an unknown column aborts safely.

## Backups (reference)

Canonical backup = host cron `/home/ec2-user/backup-to-s3.sh` on `3.101.83.217`, every
12h, gzipped per-DB → `s3://matcha-recruit-backups/postgres/` (SSE-AES256). Prod matcha
is `matcha_*` (~12 MB gz); dev/legacy matcha is `matcha_test_*`. Use `scripts/backups.sh
latest` to see the most recent of each. (The `postgres_*` ~400-byte objects are the
empty maintenance DB — harmless.)
