# Database workflow — full detail

Moved from root `CLAUDE.md`'s Database section. Read root `CLAUDE.md` first for the instance table, live-prod endpoint, and NEVER list — those stay there.

## Schema + data flow — keep dev and prod in sync (both directions)

Schema is managed via Alembic migrations in `server/alembic/versions/`; `server/app/database/bootstrap/__init__.py:init_db()` only bootstraps a fresh DB (it does **not** run migrations). The two DBs drift unless synced deliberately:

- **Schema, dev → prod:** author migration → `./scripts/migrate-dev.sh` (applies to dev `:5432`) → test → `./scripts/migrate-prod.sh` (applies the same revision to live `13.56.253.173:5433` through the app-EC2 tunnel; `--legacy` targets the retired original host). Applying to dev only is the drift that caused real `UndefinedColumnError` 500s. `alembic_version` must match afterward. Five gates guard prod: dirty-tree check, pending-revision preview, streamed S3 `pg_dump` with object verification, rehearsal against live rows followed by rollback, and typed confirmation. The flag is still named `--no-snapshot`, but it skips the logical S3 backup; there is no RDS snapshot gate anymore.
- **Data, prod → dev:** `./scripts/refresh-dev-from-prod.sh` — **anonymized** clone of the live EC2 Postgres into dev. `pg_dump` runs in a PG15 container on the app EC2 and streams to a local staging file. `--dry-run` restores into a staging DB without swapping. After a scrubbed run, **every dev user's password becomes `devpass123`**; PII is scrubbed by `scripts/sql/anonymize_dev.sql`.
- **One Matcha tenant, prod → local dev:** `./scripts/pull-tenant-from-prod.sh "Company Name" --dry-run`, then rerun without `--dry-run` to apply. The production connection is session-read-only. The tool walks the live FK graph from one `companies.id`, replaces only local tenant-owned descendant rows, includes Matcha Work / Matcha Ops data reached from that tenant, and maps shared catalog/identity UUIDs onto existing local natural-key rows instead of overwriting them. It excludes telemetry/infrastructure tables such as `usage_events`, rehearses the generated SQL inside a rolled-back local transaction, requires a typed tenant-name confirmation, and creates a full local PG15 recovery dump in `~/matcha-dev-snapshots` before committing. Cappe, TellUs, Oceanlab, other tenants, and unrelated shared catalogs are untouched. The selected tenant is copied verbatim, not anonymized; use this only for production data authorized to live on the development machine.
- **Anonymization gate — currently OFF (pre-customer).** `SKIP_ANONYMIZE=1` in `server/.env` makes the refresh clone prod → dev **verbatim** (real emails + passwords, every account logs in) — fine while there's no customer PII. **Turn it back ON the moment real customers exist:** delete/unset `SKIP_ANONYMIZE` in `server/.env` (default = on/scrubbed), then re-run `./scripts/refresh-dev-from-prod.sh` — dev re-anonymizes. To keep *your own* logins working after re-enabling, list them in `DEV_PRESERVE_EMAILS` (comma-sep, env or `server/.env`) — those keep real email + password while everyone else is scrubbed. Details in `docs/ops/DB_WORKFLOW.md`.
- **Seed/demo data → prod:** `./scripts/seed-prod.sh <pack> [--dry-run|--undo|--dev]` — the only sanctioned general-purpose way to write test/demo rows to prod. It manages the app-EC2 tunnel to the live DB EC2; guards = **DDL blocked**, **non-reserved email domains blocked**, **transaction-control statements blocked**, and a typed `seed prod` confirmation. **Always `--dry-run` first**. Pack conventions are in `scripts/seed/README.md`. The fixed post-deploy admin-update publisher is a deliberately narrower exception: model output is strict JSON, its trusted transaction can insert only the two changelog tables and advance `changelog_autogen_state`, and it verifies the committed ids afterward. See `ADMIN_UPDATES_AUTOPUBLISH.md`.
- **Backups:** `deploy/pg-backup.timer` runs at 06:00 and 18:00 UTC on the app EC2; normal backend deploys install the timer/service and enqueue one extra run. `deploy/backup-prod.sh` runs a PG15 `pg_dump`, streams custom format directly to `s3://matcha-recruit-backups/postgres-selfhosted/`, retains seven days, and uses `flock` to prevent timer/deploy overlap. Verify both `systemctl status pg-backup.service` and the newest S3 object's timestamp/size; a queued deploy is not proof of completion. The live DB has no RDS PITR. Its encrypted EBS data volume has one manual cutover snapshot from 2026-08-21, but AWS has no recurring DLM or Backup plan. `./scripts/backups.sh` and `deploy/backup-to-s3.sh` still target retired infrastructure and must not be used.

## Automated integrity checks

Two read-only workflows, split (2026-08-26) because they have unrelated
scheduling constraints and previously shared one file:

- **`.github/workflows/operational-integrity-checks.yml`** — **backup
  integrity** only. Runs at 09:17 and 21:17 UTC, three hours and seventeen
  minutes after each scheduled backup, from a hosted runner through the app
  EC2's existing AWS identity. It selects the newest S3 object by
  `LastModified`, requires it to be under 15 hours old and at least 1 MiB,
  downloads it to a restrictive temporary file on the app host, checks its
  byte count, and runs PG15 `pg_restore --list` plus a full extraction to
  `/dev/null` in a network-disabled container. The archive is deleted before
  the probe returns. This validates S3 availability and reads/decompresses
  every archive entry; it never connects to a database and is not a full
  restore rehearsal.
- **`.github/workflows/schema-drift-checks.yml`** — **schema drift**. Runs at
  17:17 UTC (10:17 PDT) on Finch's self-hosted Mac because dev is the shared
  local `matcha-postgres` container; that cron deliberately targets a time the
  Mac is normally awake — the old shared 09:17/21:17 cron sat the job queued
  for hours against a sleeping runner. It never starts the shared container. It
  compares the exact sorted multi-row `public.alembic_version` sets from dev
  and live `matcha-postgres-prod`. Equal heads and unexplained revision drift
  both trigger read-only, schema-only PG15 dumps so stamped-but-unrun DDL is
  detectable; an ancestry-explained `behind` state skips the expected schema
  difference. It does not import application startup, `init_db()`, or the
  partial ORM metadata.

An unexplained Alembic mismatch remains an alert even when normalized DDL is
equal. Equal Alembic heads with different normalized DDL are also an alert: a
migration may have been stamped without executing. The schema dump excludes
owners, ACLs, comments, security labels, tablespaces, publications, and
subscriptions; role and privilege drift are not covered. Raw dumps are never
uploaded or put into issues.

`schemasync01` is a historical reconciliation revision already applied before
PR merge. Do not edit its bytes. Although most statements are independently
`IF NOT EXISTS`/`ON CONFLICT` guarded, its account-type constraint repair is a
pairwise-rerunnable drop/add that takes an `ACCESS EXCLUSIVE` table lock; it is
not a literal no-op. Any correction after it must use a new revision.

Each check opens or updates a deduplicated `ops-health` GitHub issue, comments
and closes it after an authoritative recovery, and fails the workflow for an
unhealthy or unknown result. A collection failure opens its own monitor issue
and does not close an existing integrity/drift issue.
