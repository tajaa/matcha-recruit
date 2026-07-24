# Seed packs — test/demo data for prod (and dev)

Runner: `./scripts/seed-prod.sh <file> [--dry-run|--undo|--dev|--allow-ddl|--allow-real-emails]`

The runner opens the RDS tunnel itself, blocks DDL and non-reserved email
domains, wraps everything in one transaction, and requires typing `seed prod`
before a real prod write. `--dry-run` executes every statement against the real
DB inside `BEGIN…ROLLBACK` — always do that first.

## Workflow

```bash
./scripts/seed-prod.sh scripts/seed/mypack.sql --dev        # develop against local dev
./scripts/seed-prod.sh scripts/seed/mypack.sql --dry-run    # rehearse against prod
./scripts/seed-prod.sh scripts/seed/mypack.sql              # apply to prod
./scripts/seed-prod.sh scripts/seed/mypack.sql --undo       # revert
```

## Writing a seed pack

Two formats:

- **`pack.sql` + `pack.undo.sql`** — plain SQL pair. The undo file is
  mandatory; the runner refuses `--undo` without it.
- **`pack.py`** — prints SQL to stdout; invoked with `--undo` it must print the
  reversing SQL. Use when IDs/dates need computing (see
  `scripts/seed_regina_demo.py` for the shape).

Rules (the runner enforces 1–2, you enforce the rest):

1. **Data only, never DDL.** Schema goes through `migrate-prod.sh`.
2. **Reserved email domains only** — `@example.com`, `@*.test`, `@*.invalid`.
   Realistic fake domains bounce-storm the sender mailbox (medcenter.com,
   2026-05-15). A deliberate real address (your own gmail alias) needs
   `--allow-real-emails`.
3. **Additive only.** No `DELETE`/`UPDATE` of rows the pack didn't create,
   except filling columns that are currently NULL (and never overwriting).
4. **Tag everything you insert** so undo is a one-liner: put
   `DEMO-<PACK>-` in a natural key (`incident_number`, `name`, email
   local-part). Undo is then
   `DELETE FROM x WHERE col LIKE 'DEMO-<PACK>-%'`.
   For tables with no taggable text natural key (most tenant-scoped rows —
   they key on a UUID PK), pin every `id` under a shared UUID prefix instead
   (e.g. `b09e11e5-0001-...`) and undo with
   `DELETE FROM x WHERE id::text LIKE '<prefix>-%'`. See
   `benefits_sunset_dental.sql` for the pattern.
5. **Idempotent where cheap** — `ON CONFLICT DO NOTHING` on tagged natural
   keys, so a re-run after a partial failure is safe.

## Packs

- `benefits_sunset_dental.sql` — Sunset Smile Dental Group demo benefits
  (plan catalog, a closed + an open enrollment period, elections in every
  status, roster + eligibility exceptions, renewal-risk radar). Undo:
  `benefits_sunset_dental.undo.sql`. Linted by
  `server/tests/seed_packs/test_benefits_sunset_dental_pack.py`.
