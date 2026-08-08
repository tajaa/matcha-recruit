# Runbook: migrate oceanlab into matcha monorepo

## Context

oceanlab (music catalog, FastAPI+psycopg3 sync SQLAlchemy backend, React/Vite client, Phase 1 built) moves from standalone repo `/Users/finch/Documents/github/oceanlab` into monorepo `/Users/finch/Documents/github/matcha`, Tell-Us pattern, history preserved. Decisions locked: subtree merge; `oceanlab_*` prefixed tables in matcha's shared DB; permission granted to checkout matcha `main`; prod URL path `/oceanlab/`; archive old repo after; no Claude attribution in commits; **no push of matcha until user says so**.

Commit sequence: C0 (oceanlab repo) then C1–C6 on matcha main. Run verification gate after each step before proceeding.

---

## STEP 0 — commit + push oceanlab loose ends (C0)

```bash
cd /Users/finch/Documents/github/oceanlab
git add client/vite.config.ts FIXPLAN.md dev-remote.sh
git commit -m "Parameterize client API proxy port; track FIXPLAN and dev-remote.sh"
git push origin main
```
**Gate:** `git status` clean (ignored files ok).

## STEP 1 — subtree merge into matcha (C1 + C2)

```bash
cd /Users/finch/Documents/github/matcha
git checkout main
git remote add oceanlab-src /Users/finch/Documents/github/oceanlab
git fetch oceanlab-src
git merge -s ours --no-commit --allow-unrelated-histories oceanlab-src/main
git read-tree --prefix=incoming/oceanlab/ -u oceanlab-src/main
git commit -m "Merge oceanlab history (subtree at incoming/oceanlab)"        # C1
```
Staging prefix required: both repos have top-level `server/` + `client/`.

Restructure (pure renames, C2):
```bash
git mv incoming/oceanlab/server/app server/app/oceanlab
git mv incoming/oceanlab/client client/oceanlab
mkdir -p server/app/oceanlab/scripts
git mv incoming/oceanlab/server/scripts/seed.py server/app/oceanlab/scripts/seed.py
git mv incoming/oceanlab/PROJECT.md incoming/oceanlab/FIXPLAN.md server/app/oceanlab/
# also git mv FIXNOTES.md / README.md if present at incoming/oceanlab root
git rm -r -f incoming/oceanlab   # pyproject, uv.lock, alembic/, alembic.ini, .github, dev-remote.sh — superseded; stays in history
git commit -m "oceanlab: move into monorepo layout (server/app/oceanlab, client/oceanlab)"   # C2
```
**Gate:** `git log --follow --oneline server/app/oceanlab/routers/artists.py` shows pre-merge oceanlab commits. `git status` clean.

## STEP 2 — backend integration (C3)

All paths below relative to `/Users/finch/Documents/github/matcha` unless noted.

### 2a. Import rewrite (140 lines)
```bash
cd server/app/oceanlab
grep -rl "from app\." --include="*.py" . | xargs sed -i '' 's/from app\./from app.oceanlab./g'
grep -rn "^import app\|from app import" --include="*.py" .   # catch stragglers, fix by hand
```
Note: conftest.py imports `from alembic...` — untouched (stdlib-style external pkg). conftest's `from app.main import app` becomes `from app.oceanlab.main import app` — fix in 2b (main.py deleted, see below).

### 2b. Router aggregation
- Delete `server/app/oceanlab/main.py`.
- Rewrite `server/app/oceanlab/routers/__init__.py` (template: `server/app/tellus/routes/__init__.py`):
```python
from fastapi import APIRouter

from . import artists, codes, contributors, health, recordings, releases, tracks, works

oceanlab_router = APIRouter(tags=["oceanlab"])
for m in (health, artists, contributors, works, recordings, releases, tracks, codes):
    oceanlab_router.include_router(m.router)
```
(Old per-router `prefix="/api"` came from main.py's include calls — dropped; monolith mount supplies `/api/oceanlab`.)
- Mount in `server/app/main.py`: import next to line 602 (`from .tellus.routes import tellus_router`):
  `from .oceanlab.routers import oceanlab_router`
  include next to line 615: `app.include_router(oceanlab_router, prefix="/api/oceanlab")`.
- oceanlab's old lifespan did `settings.storage_root.mkdir(...)` — drop entirely (no upload endpoints exist; re-add in audio phase).

### 2c. IntegrityError scoping (replaces app-level handler)
Old app-level `@app.exception_handler(IntegrityError)` (oceanlab main.py:24–28) must NOT go on the monolith. In `server/app/oceanlab/routers/_errors.py` add:
```python
import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

logger = logging.getLogger(__name__)


class OceanlabRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except IntegrityError as exc:
                logger.exception("IntegrityError on %s %s", request.method, request.url.path, exc_info=exc)
                http = integrity_error_to_http(exc)
                return JSONResponse(status_code=http.status_code, content={"detail": http.detail})

        return handler
```
In each of the 8 router files (`artists.py, codes.py, contributors.py, health.py, recordings.py, releases.py, tracks.py, works.py`): `APIRouter(...)` → `APIRouter(route_class=OceanlabRoute, ...)` + import. (`include_router` preserves child route_class.)

### 2d. Table prefix + constraint map
- 20 `__tablename__` renames in `server/app/oceanlab/models/*.py` — prepend `oceanlab_`:
  `artists, isrc_config, upc_codes, contributors, deliveries, delivery_items, files, registration_tasks, recordings, credits, master_splits, jobs, releases, release_artists, tracks, royalty_statements, royalty_lines, works, recording_works, work_writers`
- Naming convention (`models/base.py:6–12`) derives constraint names from table name → they all shift automatically (`uq_releases_upc` → `uq_oceanlab_releases_upc`). Also grep models for explicitly named constraints (`sa.UniqueConstraint(..., name=` / `CheckConstraint(..., name=`) — e.g. `uq_tracks_release_disc_position` is multi-column so must be explicit — rename those strings to `oceanlab_`-prefixed form too.
- `_errors.py` `_UNIQUE_CONSTRAINT_MESSAGES`: rekey all 6 entries with `uq_oceanlab_` prefix.
- `tests/test_schema_constraints.py`: update any constraint-name string assertions.
- Grep whole oceanlab package for raw SQL table refs: `grep -rn "isrc_config\|upc_codes\|FROM \|JOIN " server/app/oceanlab --include="*.py"` — fix `services/isrc.py`/`upc.py` raw SQL and seed.py if they name tables.

### 2e. db.py — derive URL from monolith env
Replace `server/app/oceanlab/db.py` engine construction:
```python
import os

from app.oceanlab.config import settings


def _database_url() -> str:
    url = settings.database_url or os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


engine = create_engine(_database_url(), pool_pre_ping=True, future=True)
```
Sync engine coexists with matcha's asyncpg pool (sync endpoints run in threadpool). Local dev DB = `matcha` database now, not `oceanlab`.

### 2f. config.py — env-prefixed, boot-safe
Rewrite `server/app/oceanlab/config.py`:
```python
model_config = SettingsConfigDict(env_prefix="OCEANLAB_", env_file=".env", extra="ignore")

token: str = ""                      # env OCEANLAB_TOKEN; empty ⇒ auth disabled-closed (503)
database_url: str | None = None      # env OCEANLAB_DATABASE_URL override; default derive from DATABASE_URL
storage_root: Path = Path("var/oceanlab-storage")
label_name: str = "Oceanlab"
# keep youtube/soundcloud/ffmpeg fields as-is (get OCEANLAB_ prefix automatically)
```
Old field `oceanlab_token: str = Field(min_length=8)` dies (with env_prefix it would read `OCEANLAB_OCEANLAB_TOKEN`, and required-at-import would crash monolith boot). Update `deps.py:12` → `settings.token`; add guard at top of `require_auth`:
```python
if not settings.token:
    raise HTTPException(status_code=503, detail="Oceanlab auth not configured")
```
Update `tests/conftest.py:82,125` `settings.oceanlab_token` → `settings.token` and any health-router references. Add `OCEANLAB_TOKEN=<dev value>` to `server/.env` and `server/.env.example`.

### 2g. Alembic rebaseline
- New file `server/alembic/versions/oceanlab_app_01_standalone.py`, template `tellus_app_01_standalone.py`. `revision = "oceanlab_app_01"`, `down_revision` = matcha-line head (pick the matcha root-line head the tellus file used as its anchor pattern — check `tellus_app_01_standalone.py`'s down_revision choice and current `venv/bin/alembic heads`; matcha chain is intentionally multi-head, applied with `upgrade heads`).
- Content: hand-written `op.execute` DDL for all 20 `oceanlab_*` tables + indexes + `INSERT INTO oceanlab_isrc_config (id, registrant_prefix, year_digits, next_designation) VALUES (1, '', '', 1)` seed. Generate mechanically: after 2d rename, run one-off script compiling `CreateTable(t).compile(dialect=postgresql.dialect())` for `Base.metadata.sorted_tables`; cross-check against old `294504605e28_initial_schema.py` (visible via `git show C1:incoming/oceanlab/server/alembic/versions/...`).
- `downgrade()`: drop the 20 tables in reverse dependency order.
- Matcha `server/alembic/env.py` `include_name` scopes autogenerate to matcha's Base — oceanlab tables invisible there; oceanlab future migrations are hand-SQL `oceanlab_app_NN_*` files.

### 2h. requirements
Append to `server/requirements.txt`: `psycopg[binary]>=3.1`, `pydantic-settings>=2.4` (verify absent first: `grep -i "psycopg\|pydantic-settings" server/requirements.txt`). Then `server/venv/bin/pip install "psycopg[binary]>=3.1" "pydantic-settings>=2.4"`.

**Gate (C3):**
```bash
cd /Users/finch/Documents/github/matcha
python -m compileall -q server/app server/alembic          # CI check
./scripts/migrate-dev.sh                                    # applies oceanlab_app_01 to local matcha DB
docker exec matcha-postgres psql -U matcha -d matcha -c '\dt oceanlab_*'   # 20 tables
server/venv/bin/uvicorn app.main:app --port 8001 &          # from server/
curl -s 127.0.0.1:8001/api/oceanlab/health                  # ok
curl -s 127.0.0.1:8001/api/oceanlab/artists                 # 401
curl -s -H "Authorization: Bearer $OCEANLAB_TOKEN" 127.0.0.1:8001/api/oceanlab/artists   # 200
curl -s 127.0.0.1:8001/api/health                           # matcha unaffected
```
Commit C3: "oceanlab backend: mount at /api/oceanlab, prefixed tables, scoped errors, rebaselined migration".

## STEP 3 — tests (C4, may fold into C3)

`server/app/oceanlab/tests/conftest.py`:
- `TEST_DATABASE_URL` stays `postgresql+psycopg://matcha:matcha_dev@127.0.0.1:5432/oceanlab_test`.
- Replace `engine` fixture's alembic bootstrap (lines 19–44: `Config("alembic.ini")` + settings monkeypatch — both dead) with direct execution of the shipped migration:
```python
from alembic.migration import MigrationContext
from alembic.operations import Operations

import server_alembic_oceanlab  # actually: importlib load of server/alembic/versions/oceanlab_app_01_standalone.py

Base.metadata.drop_all(eng)
with eng.begin() as conn:
    conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        oceanlab_app_01_standalone.upgrade()
```
(load module via `importlib.util.spec_from_file_location` with path relative to conftest: `../../../..​/alembic/versions/oceanlab_app_01_standalone.py`). Preserves "shipped migration builds schema" drift check.
- `_TRUNCATE_TABLES` (lines 90–94): prefix all 20 names `oceanlab_`.
- isrc re-seed SQL (line 109): `INSERT INTO oceanlab_isrc_config ...`.
- Token headers already fixed in 2f.

One-time: `docker exec matcha-postgres psql -U matcha -c 'CREATE DATABASE oceanlab_test'` (skip if exists).

**Gate:** `cd server && venv/bin/pytest app/oceanlab/tests -q` — all pass (integrity tests prove OceanlabRoute). Then `venv/bin/pytest tests/ -q` if matcha suite is runnable locally, else compileall stands.
Commit C4.

## STEP 4 — frontend integration (C5)

### 4a. client/oceanlab/vite.config.ts (template `client/tellus/vite.config.ts`)
```ts
const backendTarget = process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8001'
export default defineConfig({
  base: '/oceanlab/',
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5201,               // clear of main 5175–5190 range and tellus 5191
    proxy: { '/api': { target: backendTarget, changeOrigin: true } },
  },
})
```
### 4b. client source
- `client/oceanlab/src/api/client.ts:18`: `baseURL: '/api'` → `'/api/oceanlab'`.
- `client/oceanlab/src/main.tsx`: `<BrowserRouter basename="/oceanlab">`.
- `client/oceanlab/package.json`: if `gen:api` script exists, point at `http://127.0.0.1:8001/openapi.json`.

### 4c. client/Dockerfile
Duplicate tellus stage block (lines 14–24) for oceanlab, placed after it:
```dockerfile
COPY oceanlab/package*.json ./oceanlab/
RUN cd oceanlab && npm ci
COPY oceanlab ./oceanlab
RUN cd oceanlab && npx vite build
```
(add `--legacy-peer-deps` only if `npm ci` fails without it) and next to line 46:
```dockerfile
COPY --from=builder /app/oceanlab/dist /usr/share/nginx/html/oceanlab
```

### 4d. client/nginx.conf
Mirror the three tellus stanzas (lines ~211–258) as `/oceanlab/assets/`, `= /oceanlab/index.html`, `/oceanlab/` — but CSP = the file's default/main-app CSP (copy from the main `= /index.html` stanza; no Google/S3 allowances). Remember: re-declare ALL headers in each location (add_header suppresses inherited).

### 4e. main client/vite.config.ts
Next to `/tellus` proxy (line ~35):
```ts
'/oceanlab': {
  target: process.env.VITE_OCEANLAB_TARGET || 'http://127.0.0.1:5201',
  changeOrigin: true,
  ws: true,
},
```

### 4f. deploy/nginx/matcha.conf (host nginx — manual scp later)
Next to `location /tellus/` (~line 87), same shape:
```nginx
location /oceanlab/ {
    proxy_pass http://matcha_frontend;
    # copy standard proxy_set_header block from /tellus/ location
}
```
`/api/oceanlab/*` needs nothing — existing `location /api/` (~:303) already proxies to backend upstream.

### 4g. dev-remote.sh (optional parity)
Add oceanlab window to `scripts/dev-remote.sh` mirroring tellus block (~257–325), port 5201.

**Gate:**
```bash
cd client/oceanlab && npm ci && npm run build     # dist/ emits under /oceanlab/ base
npm run dev &                                     # :5201
# main client dev: http://localhost:5174/oceanlab/ loads, CatalogPage/SettingsPage work against /api/oceanlab
cd /Users/finch/Documents/github/matcha && docker build -f client/Dockerfile client/   # both SPAs build
```
Commit C5: "oceanlab client: separate Vite app at /oceanlab/, Dockerfile stage, nginx stanzas".

## STEP 5 — docs + cleanup (C6)

- Root `CLAUDE.md`: add products-map row — Oceanlab | `client/oceanlab/` (separate Vite app, `/oceanlab/`) | `server/app/oceanlab/` (`/api/oceanlab`) | static bearer `OCEANLAB_TOKEN`, `oceanlab_*` tables | music catalog/label. Extend import-boundary rule to `oceanlab → app/core only`.
- New `server/app/oceanlab/CLAUDE.md`: boundary rule, sync-SQLAlchemy-in-threadpool note, migration convention (`oceanlab_app_NN` hand-SQL in matcha chain), pointer to PROJECT.md/FIXPLAN.md, dev port 5201, token env.
- `git remote remove oceanlab-src`.
- Commit C6.

**Full-image gate:** `./scripts/build-and-push.sh --no-push` (or its build-only mode) — both images build.

## STEP 6 — old repo archive (after user verifies merge)

```bash
cd /Users/finch/Documents/github/oceanlab
# prepend README note: "Superseded — code lives in matcha monorepo at server/app/oceanlab + client/oceanlab"
git add README.md && git commit -m "Point to matcha monorepo" && git push
gh repo archive tajaa/oceanlab --yes
```

## STEP 7 — prod rollout (manual, user-driven, NOT part of this session unless asked)

1. Add `OCEANLAB_TOKEN` to EC2 backend env.
2. `./scripts/migrate-prod.sh` (applies `oceanlab_app_01` to prod matcha DB).
3. `./scripts/build-and-push.sh && ./scripts/update-ec2.sh` (blue-green).
4. scp `deploy/nginx/matcha.conf` to EC2, `nginx -t`, reload.

## Critical files

matcha: `server/app/main.py` (:601–615), `server/alembic/versions/tellus_app_01_standalone.py`, `server/requirements.txt`, `client/Dockerfile` (:14–24, :46), `client/nginx.conf` (:211–258), `client/vite.config.ts` (:35), `deploy/nginx/matcha.conf` (:87, :303), `scripts/{migrate-dev.sh,dev-remote.sh}`, root `CLAUDE.md`.
oceanlab (post-move): `server/app/oceanlab/{config.py, db.py, deps.py, routers/__init__.py, routers/_errors.py, models/*.py, tests/conftest.py, tests/test_schema_constraints.py}`, `client/oceanlab/{vite.config.ts, src/api/client.ts, src/main.tsx}`.
