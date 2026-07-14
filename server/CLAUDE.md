# Server (FastAPI Backend)

Python 3.12, FastAPI + asyncpg + Celery + Gemini. Production runs on EC2 with Postgres on a separate dedicated host (treated as RDS — see root CLAUDE.md for DB connection rules and the **production-safety guard list**).

## Layout

```
server/
├── run.py                       Entry point (uvicorn)
├── venv/                        Python 3.12 venv — local dev
├── requirements.txt             Pinned top-level deps
├── alembic/                     Migrations (use these, don't auto-mutate schema)
├── tests/                       pytest unit tests
├── scripts/                     One-off ops scripts (seed data, etc.)
└── app/
    ├── main.py                  App init, lifespan, CORS, mount /api
    ├── config.py                Pydantic settings from .env
    ├── database.py              asyncpg pool + init_db() bootstrap (5,649 lines — schema reference)
    ├── dependencies.py          Shared auth deps (require_admin etc.)
    ├── protocol.py              AI WebSocket / streaming shapes
    ├── core/                    Auth, admin, compliance, AI chat, policies, resources
    ├── matcha/                  Recruiting + HR domain (incl. matcha-work)
    │   ├── routes/              See routes/CLAUDE.md for the zoo
    │   ├── services/            Business logic — heavy AI calls, signature providers, etc.
    │   ├── models/              Pydantic request/response shapes
    │   └── workers/             (rare — most worker tasks live in app/workers/)
    ├── workers/                 Celery app + scheduled / heavy tasks
    ├── orm/                     SQLAlchemy helpers (legacy reports only — avoid for new code)
    └── uploads/                 Local-only upload temp dir (S3 in prod)
```

## Conventions

**Database**:
- asyncpg pool via `async with get_connection() as conn:`.
- All schema changes go through Alembic (`alembic/versions/`). `database.py:init_db()` bootstraps a fresh DB but should not be relied on for schema evolution.
- Use parameterized queries. Never f-string user input into SQL.
- Tenant isolation: filter by `company_id` (or `org_id` for employees-related tables) on every multi-tenant table.

**Imports**:
- Absolute imports for module-level (`from app.X import …`). This was the convention enforced during the IR refactor.
- Relative imports tolerated inside packages (e.g. `from ._shared import …` within `ir_incidents/`).
- Lazy imports inside function bodies are OK for circular-import avoidance.

**Auth**:
- JWT bearer token in `Authorization: Bearer …`. Roles: `admin`, `client`, `candidate`, `employee`, `broker`, `creator`, `agency`, `individual` (see root CLAUDE.md).
- Per-endpoint deps: `require_admin`, `require_client`, `require_candidate`, `require_employee`, `require_admin_or_client`, `require_broker_or_admin`.
- Feature-gated routers add `dependencies=[Depends(require_feature("flag"))]` at mount time (see `routes/__init__.py`).

**Models**:
- Pydantic v2 (`BaseModel`, `Field`, `model_validator`).
- Request and response models live in `app/<core|matcha>/models/<domain>.py`, not inline in route files.
- Enum-constrained fields use `Literal[...]` from `typing`.

**Background work**:
- FastAPI `BackgroundTasks.add_task(fn, ...)` for lightweight per-request work — plain `async def` functions, run in the same process after the response is sent.
- Celery for anything that survives the request lifecycle, runs scheduled, or needs separate concurrency limits. Tasks live in `app/workers/tasks/`. The worker container restarts every 15 min via systemd; `@worker_ready` re-dispatches periodic tasks (no celery-beat).

**Email**:
- Gmail API via OAuth2 (`app/core/services/email.py`) for transactional. MailerSend for broker invites + a few transactional flows. The send wrapper has a defense-in-depth guard that skips RFC 2606 reserved test domains — see root CLAUDE.md test-data rules.

**AI**:
- Gemini via `google.genai` SDK with `settings.gemini_api_key` (from the `LIVE_API` env var). Some services also honor a `GEMINI_API_KEY` env override. Native Google AI only — no Vertex.
- Per-feature analyzer singletons (e.g. `get_ir_analyzer`, `get_er_analyzer`) cache the model handle; don't instantiate per request.

**Streaming**:
- SSE for AI analysis runs (`StreamingResponse(event_stream(), media_type="text/event-stream")`).
- WebSocket for chat / channels / voice interviews. JWT in query param `?token=…`, validated on `accept`.

## Local dev

Use `./scripts/dev-remote.sh` from repo root. It SSH-tunnels Postgres from EC2 (treat as production — see root CLAUDE.md), starts Redis tunnel, backend on :8001, frontend on :5174, local chat model on :8080. Requires `secrets/roonMT-arm.pem`.

To run the backend alone (assumes tunnels are up):
```bash
cd server && ./venv/bin/python run.py     # :8001
```

## Tests

```bash
cd server && ./venv/bin/python -m pytest tests/<domain>/ -q
```

Some pre-existing tests use `importlib.util.spec_from_file_location(...)` with hard-coded relative paths and fail at collection time. Known set:
- `tests/employees/test_employee_invites_and_compliance.py`
- `tests/employees/test_internal_mobility_routes.py`
- `tests/er_copilot/test_er_copilot_risk_refresh.py`
- `tests/matcha_work/test_language_tutor.py`
- `tests/offers/test_offer_letters_plus_guidance.py`
- `tests/pre_termination/test_pre_termination.py`
- `tests/training/test_employee_create_supervisor.py`

These are pre-existing on `main`; don't try to fix them as part of unrelated work. The IR-incidents tests (132 passing) are the model to follow.

## Migration authoring rules

Prod is an RDS instance at the far end of an SSH tunnel (~100ms per round-trip),
and `migrate-prod.sh` gates every run: uncommitted migrations abort, pending
revisions are printed, an RDS snapshot is taken, the whole upgrade is **rehearsed
against live prod rows and rolled back**, and you type `migrate prod` to commit.
Write migrations that survive that:

- **Set-based SQL, never row-by-row Python loops.** A loop that is instant on the
  local dev container is ~20,000 sequential round-trips against prod and does not
  finish — it looks like a lock, but it is the DB idle, waiting on you.
  `jparent01` is the template: a TEMP table holds the plan, ~20 statements do the
  work, four seconds end to end.
- **Every `LIMIT 1` needs a deterministic `ORDER BY`.** Otherwise the pass and its
  own post-check can disagree, and the terminal `raise` rolls back the lot.
- **Repointing rows onto a UNIQUE column needs an explicit dedupe pass first**
  (ctid + `ROW_NUMBER()`, as in `jparent01`). Merging one row at a time hides the
  collision; merging a set does not.
- **Write a real `downgrade()`** where feasible. If it is genuinely irreversible,
  say so in the docstring — the RDS snapshot is then the only rollback.
- **Commit the migration before applying it to ANY database, dev included.** Dev
  and prod running different bytes of the same revision id is a silent drift with
  no alarm on it.
- **Rehearse:** `MIGRATE_REHEARSAL=1 DATABASE_URL=… alembic upgrade heads` runs
  the migration for real inside the upgrade transaction and raises at the end to
  force the rollback. `migrate-prod.sh` does this for you; run it by hand against
  dev while authoring. Its elapsed time is the signal — a slow rehearsal is a
  migration that will hang.

## Common pitfalls

- **Don't run Alembic upgrade automatically.** Schema changes require explicit user approval (see root CLAUDE.md production-safety list).
- **Don't introduce new SQLAlchemy code.** `app/orm/` exists for a few legacy reports; everything else is asyncpg.
- **Don't bypass `require_feature`.** Frontends will URL-hop to a feature page; the gate is what surfaces the upsell instead of 403.
- **Don't trust client-supplied `company_id`/`org_id`.** Always derive from `current_user` and verify ownership of the requested resource.
- **Don't define helpers in the route file when a service exists.** AI analyzers, signature providers, storage, email — all live under `services/` and are instantiated via getters.
