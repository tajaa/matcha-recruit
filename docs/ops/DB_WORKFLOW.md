# Dev ↔ Prod Database Workflow

How the two Matcha Postgres databases relate, and the scripts that move schema and
data between them. Companion to [`DB_ENCRYPTION_RUNBOOK.md`](./DB_ENCRYPTION_RUNBOOK.md)
(which covers the encrypted-sidecar cutover).

## Topology

**2026-06-15: dev moved off the DB EC2 to a local container.** The old DB EC2
(`3.101.83.217`, instance `matcha-postgres-db`) is now **stopped** with no public
IP — it's no longer reachable at all. `dev-remote.sh` now manages a local
pgvector/pg15 docker container (`matcha-postgres`) on your own laptop instead.

**Prod is on RDS.** `matcha-prod` (PG 15.18, encrypted, single-AZ, `db.t4g.small`)
lives in the app VPC.

| Instance | Where | Role | Reachable from |
|---|---|---|---|
| `matcha-prod` RDS | `matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com:5432` (app VPC) | **PROD** | app EC2 only (SG-locked); laptop via app-EC2 tunnel `localhost:5434`. `rds.force_ssl=1` → `sslmode=require` |
| `matcha-postgres` container | **local docker**, on your laptop | **DEV** | directly — no SSH/tunnel needed. Managed by `dev-remote.sh` (`docker exec` for everything else) |

Anything that talks to RDS goes through the app EC2 (`54.177.107.107`, tagged
`minty-backend-rds` in AWS) — that's the only box in the RDS's VPC.

App containers (backend/worker/frontend/redis/livekit) run on the app EC2 and point
at the RDS endpoint (`DATABASE_URL` + `DATABASE_SSL=require`).

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
| `scripts/dev-remote.sh` | local docker | Start the local stack (local Postgres container + backend + worker + frontend). Does **not** run migrations. |
| `scripts/migrate-dev.sh` | local docker | `alembic upgrade heads` against the local dev container. Starts it if not running. |
| `scripts/migrate-prod.sh` | RDS via app EC2 (`localhost:5434`) | `alembic upgrade heads` against RDS prod (reads `PROD_DATABASE_URL` from `server/.env`). `--legacy` targets the old `:5433` container (`PROD_LEGACY_DATABASE_URL`) — that container's host is stopped, so this path only works if you boot it back up. |
| `scripts/refresh-dev-from-prod.sh` | app EC2 (dump) + local docker (restore) | Clone RDS prod → local dev container and anonymize; dump streams app EC2 → laptop, restores via `docker exec`. See below. |
| `scripts/backups.sh` | DB host `3.101.83.217` | Convenience CLI over the S3 backup bucket — **stale**: the host cron it drives lives on the now-stopped DB EC2, so this currently can't reach it. RDS has its own automated snapshots separately; this script needs a rework if you want the old S3-cron flow back. |
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

What it does:

1. **Snapshot** dev → `~/matcha-dev-snapshots/dev_pre_refresh_<ts>.sql.gz` on your laptop (keeps last 5).
2. **Dump** RDS prod on the app EC2, streamed over SSH to a local temp file. Runs inside a
   disposable `postgres:15` container on the app EC2 rather than the box's bare-metal
   client — that's PG16, whose custom-format archives (`pg_dump -Fc`) use a newer
   version tag that a PG15 `pg_restore` refuses to read (`unsupported version (1.15) in
   file header`). Dumping from a matching-version container avoids the mismatch; first
   run pulls the ~80MB image, cached after.
3. **Stage** a fresh `matcha_new` in the local `matcha-postgres` container and `pg_restore` the dump into it (`docker exec`, no SSH — the container is local).
4. **Anonymize** `matcha_new` with `anonymize_dev.sql`.
5. **Swap** `matcha → matcha_old_<ts>`, `matcha_new → matcha` (keeps 1 old DB).
6. **Verify** counts + assert zero non-`@example.com` user emails.

Safety: it refuses if the target container name contains `prod`, requires typing
`refresh-dev`, and only ever rebuilds the local `matcha-postgres` container (dev); prod
(RDS) is read-only as the `pg_dump` source. A failed clone leaves the live dev DB
untouched (the swap is last).

After a refresh, **all dev users share one password** (`devpass123`, override with
`DEV_LOGIN_PASSWORD=`). The script prints sample `admin`/`client`/`individual` emails to
log in with. Refresh also resets dev's `alembic_version` to prod's — re-run
`migrate-dev.sh` afterward if you have un-shipped local migrations.

#### Logging into dev as yourself (`DEV_PRESERVE_EMAILS`)

By default anonymization rewrites **every** user email to `user_<uuid>@example.com`, so
your real prod accounts can't be used in dev — you're gated to the scrubbed test users.
To keep your own accounts usable, set an allowlist of emails that **skip the scrub** and
keep their **real email + real password**:

```bash
# in server/.env (set once; gitignored), or inline before the command:
DEV_PRESERVE_EMAILS="you@yourco.com,admin@yourco.com"
./scripts/refresh-dev-from-prod.sh
```

Those users come through with their real email and their actual (prod) password —
everyone else is still fully anonymized, and the PII-leak check excludes only the
allowlisted addresses. Empty/unset = the old behavior (every user scrubbed). This only
takes effect on the **next refresh** (the current dev DB is already scrubbed), so set it
and re-run the refresh to restore your logins.

#### Pre-customer escape hatch: `SKIP_ANONYMIZE`

Before there's any real customer data, the scrub is pure friction. Set
`SKIP_ANONYMIZE=1` (env or `server/.env`) and the refresh clones prod → dev **verbatim**
— no anonymization, every account usable with its real email + password, no allowlist to
maintain. The refresh prints a red warning, skips the anonymize step, and skips the
PII-leak assertion.

```bash
SKIP_ANONYMIZE=1 ./scripts/refresh-dev-from-prod.sh
```

**Turn it back on the moment you onboard real customers** — just unset `SKIP_ANONYMIZE`
(default is off / scrubbed). With it on, dev holds real PII and the dev backend can email
/ bill real people, so it's only safe while you're the only data in the system.

### What anonymize_dev.sql scrubs

Emails → reserved domains; person + company names → synthetic; phones/addresses →
nulled; all `users.password_hash` → the dev hash; tokens/secrets (reset, invite, SSO
cert, OAuth, webhook, integration secrets, `gmail_token`) → nulled/randomized; Stripe
IDs → fake. **Kept for realism:** free-text narratives (incident descriptions,
offer-letter benefits, message bodies, company summaries). Extend the SQL if you need
those gone too. The column list is validated against the live schema; the run is wrapped
in a transaction with `ON_ERROR_STOP`, so an unknown column aborts safely.

## Backups (reference — STALE, needs a rework)

The old canonical backup was a host cron `/home/ec2-user/backup-to-s3.sh` on
`3.101.83.217`, every 12h, gzipped per-DB → `s3://matcha-recruit-backups/postgres/`
(SSE-AES256), driven via `scripts/backups.sh`. That box is now **stopped** (dev moved
to a local container, prod moved to RDS), so this cron isn't running and
`scripts/backups.sh` can't reach it anymore.

RDS has its own automated snapshots (AWS-managed) covering prod in the meantime, but
there's no equivalent scripted backup for the local dev container, and the S3-cron
flow hasn't been rebuilt against the new topology. Treat this as an open gap, not a
working safety net — `refresh-dev-from-prod.sh`'s own pre-refresh snapshot
(`~/matcha-dev-snapshots/`) is the only current local backup of dev.
