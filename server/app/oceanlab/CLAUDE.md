# Oceanlab

Music catalog / label ingestion pipeline. Migrated into this monorepo from a
standalone repo (`tajaa/oceanlab`) via subtree merge — full pre-merge commit
history is preserved and reachable, see `git log --all -- server/app/oceanlab`.
Currently Phase 1 of a 4-phase build (schema + CRUD + ISRC/UPC assignment;
audio/artwork upload, packaging, and delivery are not built yet — see
`PROJECT.md` and `FIXPLAN.md` in this directory).

## Boundary rule

Same isolation contract as Cappe/Tell-Us: only import from `app/core/*`
(shared db pool, email, storage, auth, redis) — never from `app/matcha/*`.
Oceanlab currently imports from neither; it's fully self-contained with its
own sync SQLAlchemy engine (`db.py`) and its own settings (`config.py`,
`env_prefix="OCEANLAB_"`). If a future phase needs matcha's file-storage
service for audio uploads, that's the one `app/core/*` import to add —
nothing else.

## Sync SQLAlchemy in an async monolith

Unlike the rest of the monolith (asyncpg pool), oceanlab's routers use sync
SQLAlchemy 2 + psycopg3 (`db.py`, `get_db()`). FastAPI runs sync path
operations in a threadpool, so this coexists fine with the async pool — just
don't `await` anything inside an oceanlab route, and don't try to share a
connection/session between oceanlab and matcha code.

`db.py` calls `load_dotenv()` itself inside `_database_url()`, because the
engine is built **lazily** (`get_engine()`, `lru_cache`d) on first use rather
than at module import — a missing `DATABASE_URL` now raises on the first
oceanlab request instead of crashing `app.main` import for the whole
monolith. Don't remove the `load_dotenv()` call or revert to a module-level
`create_engine(...)`.

## Tables

All 20 tables are `oceanlab_*` prefixed, living in the shared matcha DB (no
separate database) — same convention as `cappe_*`/`tellus_*`. Constraint/index
names follow `models/base.py`'s naming convention (`pk_`, `uq_`, `ck_`, `fk_`,
`ix_` + table name), except a handful of explicitly-named multi-column
constraints, which are also `oceanlab_`-prefixed by hand — keep new ones
consistent so `_errors.py`'s `_UNIQUE_CONSTRAINT_MESSAGES` lookup keeps working.

## Migrations

Oceanlab's own alembic setup (`alembic.ini`, standalone `alembic/`) did **not**
carry over — matcha has one alembic chain with hand-SQL per-guest-app
migrations (see `server/alembic/versions/tellus_app_01_standalone.py` for the
pattern). Future oceanlab schema changes are new hand-SQL `oceanlab_app_NN_*`
files chained off the previous one — run `./scripts/migrate-dev.sh` /
`migrate-prod.sh` like any other matcha migration, not a separate alembic
invocation.

Chain so far:

| Revision | File | What |
|---|---|---|
| `oceanlab_app_01` | `oceanlab_app_01_standalone.py` | the 20 `oceanlab_*` tables |
| `oceanlab_app_02` | `oceanlab_app_02_label_defaults.py` | `oceanlab_label_settings` singleton |

**`tests/conftest.py` builds the test schema by executing these migration
modules directly** (not `Base.metadata.create_all`), so model/migration drift
fails tests. Every new migration must be appended to `_MIGRATION_MODULES`
there, and any new seeded-singleton row re-inserted in the `db_real` teardown
next to the `oceanlab_isrc_config` / `oceanlab_label_settings` inserts —
`TRUNCATE` drops them.

## Label defaults (single-owner prefill)

`oceanlab_label_settings` (id=1 singleton) + `services/defaults.py` answer, once,
the questions every release and recording would otherwise repeat: c-line/p-line
templates, territories, genre, default artist, and the default contributor who
owns 100% of master and publishing.

They are applied **at create time as real rows, never as a read-time overlay** —
the packaging manifest, the registration exporters and the validator all read
the tables directly, so an overlay would have to be reimplemented in each of
them, and editing a split down from 100% when a collaborator appears would need
a special "un-default" path. An explicit value in the request always wins.

`isrc_source` / `upc_source` (`own | distributor`) additionally drive **validator
severity**: with distributor-issued codes a missing ISRC/UPC at packaging time
is a warning; with label-owned codes it is a hard error. That is what lets the
first release ship before the $95 usisrc.org prefix and $30 GS1 GTINs exist.

## Auth

Static bearer token (`OCEANLAB_TOKEN` env var), constant-time compare in
`deps.py`. Empty/unset token → `require_auth` returns 503 ("not configured")
rather than crashing the monolith at boot or silently accepting any token.

## Dev

- Backend: rides the monolith (`uvicorn app.main:app`, mounted at `/api/oceanlab`).
- Client: separate Vite app, `client/oceanlab/`, dev port 5201 (`npm run dev`
  from that directory, or the `oceanlab` tmux window from `scripts/dev-remote.sh`).
  Served in prod at `/oceanlab/` by the same nginx container as the main app.
- Tests: `cd server && venv/bin/pytest app/oceanlab/tests` — has its own
  `tests/conftest.py` that boots a standalone FastAPI app (`main.py`, mounted
  at unprefixed `/api`) against a scratch `oceanlab_test` database, building
  the schema by executing the shipped migration directly (not
  `Base.metadata.create_all`), so model/migration drift still fails tests.
