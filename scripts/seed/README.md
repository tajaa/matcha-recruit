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
5. **Idempotent where cheap** — `ON CONFLICT DO NOTHING` on tagged natural
   keys, so a re-run after a partial failure is safe.
