# Split the 3 largest server files into packages

## Context

The 3 largest files in `server/` are monoliths that have outgrown single-file maintainability:

| File | Lines | Target |
|---|---|---|
| `app/database.py` | 6,551 | `app/database/` package (pool + handbook + bootstrap/ with 15 domain modules) |
| `app/core/routes/admin/jurisdictions.py` | 4,558 | `app/core/routes/admin/jurisdictions/` package (9 route files) |
| `app/core/services/compliance_service/_checks.py` | 3,364 | 4 sibling modules inside the existing package |

Behavior-preserving mechanical split only — no bug fixes, no dead-code removal. Mirrors the repo's established split idiom (`COMPLIANCE_REGISTRY_SPLIT_PLAN.md`, the 2026-07-25 core-routes split, the services split). All line numbers pinned to HEAD `c010ba5` and spot-verified this session. Scratchpad: `/private/tmp/claude-501/-Users-finch-Documents-github-matcha/10db4ce3-89c0-4528-8a9e-9a907eef64fe/scratchpad` (`<scratch>`).

**Verified constraints:**
- `database.py`: 399 import lines across 350 files, ALL `from … import <name>` form → package façade is fully transparent. Only 8 externally-imported symbols (`get_connection`, `init_pool`, `close_pool`, `get_pool`, `connection_or_direct`, `init_db`, `set_tenant_id`, `set_user_id`+`set_is_admin`). Exactly 2 relative imports, both lazy in-function: line 140 (`from .config import get_settings`) and line 5099 (`from .core.services.auth import hash_password`) — must be rewritten absolute (the ONLY allowed byte diffs). One test patch-target: `tests/paid_channels/test_paid_channels.py:1411` `patch("app.database.get_connection")` — survives via façade. `alembic/env.py` and `run.py` don't import it.
- `jurisdictions.py`: sole importer is `admin/__init__.py:4` (`… import router as _jurisdictions`). Zero module-level helpers/models — everything comes from `admin/_shared.py` + `app/core/models/admin.py` star-imports. 48 routes. Route-order hazard: `POST /jurisdictions/top-metros/check` (3445) must register before `POST /jurisdictions/{jurisdiction_id}/check` (3567, no `:uuid` converter).
- `_checks.py`: zero direct `._checks` importers or patch-targets repo-wide; all callers go through the package `__init__.py` (imports exactly 12 names from `._checks` at lines 191–204; 168-name `__all__`). Shadowing gotcha: nested `def _missing_required_categories` at 172 shadows the `._normalize` import for the entire `run_compliance_check_stream` body (121–1366); `run_compliance_check_background` (2312+) uses the imported one. Background does NOT call stream — independent twins.
- Branch `matcha/compliance-refactor` has **uncommitted compliance_registry work** (`M CLAUDE.md`, `M scripts/generate_compliance_ts.py`, `D compliance_registry.py`, untracked `compliance_registry/` + plan doc). Never touch/stage/commit it. **User commits everything; one commit per split.** Suggest user commits the registry work first (Part A also edits root `CLAUDE.md`).

## Shared machinery

**Extraction scripts** (one per split, in `<scratch>`): partition table as data; assert the first-line string of every range; assert ranges tile the file with no gap/overlap; emit files. **Never dedent** — extracted bodies keep original indentation (dedent would rewrite bytes inside triple-quoted SQL literals).

**Gate ladder** (run per split, abort + restore monolith on failure):
1. `server/venv/bin/python -m compileall -q <new files>` (post-edit hook also py_compiles)
2. Split-specific equivalence gate (below)
3. `cd server && venv/bin/python -c "import app.main"`
4. OpenAPI route-table diff vs baseline — `[(r.path, sorted(r.methods), r.name) for r in app.main.app.router.routes if hasattr(r, "methods")]`, **ordered** list equality; run for all 3 splits
5. Pytest failure-set diff: `venv/bin/python -m pytest -q` (with the known `--ignore` flags from `server/CLAUDE.md`) `| grep ^FAILED | sort`, diff vs baseline → empty. Pre-existing failures stay — do NOT fix.
6. Grep sweep + doc updates (per split)

**Baselines captured once, before any edit**: pytest FAILED set + OpenAPI route dump → `<scratch>`.

**Sequencing**: C (`_checks`, smallest blast radius — rehearses the machinery) → B (`jurisdictions`) → A (`database`, 350 importer files, done last with gates battle-tested). User commits after each.

---

## Part C — `_checks.py` → 4 sibling modules (first)

Each new module: line-1 docstring (own) + **lines 2–120 verbatim header clone** + verbatim ranges. ~19 dead header imports per file accepted (mechanical mandate, `# noqa` inherited from idiom).

| Module | Ranges (concatenated in order) | ~Lines | Owns |
|---|---|---|---|
| `_run.py` | 121–1365 + 2312–3071 | ~2,125 | `run_compliance_check_stream`, `run_compliance_check_background` — twins stay together; exceeds 800-line target unavoidably (atomic 1,245- and 760-line functions), note in docstring |
| `_reads.py` | 1366–1742 + 3147–3364 | ~715 | `_conn_or_new` (cut at **1366**, the `@asynccontextmanager` decorator line), `get_employee_impact_for_location`, `get_location_requirements`, `get_hierarchical_requirements`, `search_company_requirements` — all 3 intra-file call edges become intra-module |
| `_dashboards.py` | 1743–2216 | ~594 | `get_compliance_summary`, `get_compliance_dashboard` (+3 nested helpers) |
| `_settings.py` | 2217–2311 + 3072–3146 | ~290 | `update_auto_check_settings`, `get_check_log`, `set_requirement_pinned`, `get_pinned_requirements` |

First-line asserts: 121 `async def run_compliance_check_stream(`; 1366 `@asynccontextmanager`; 1367 `async def _conn_or_new(conn):`; 1743 `async def get_compliance_summary(`; 2217 `async def update_auto_check_settings(`; 2312 `async def run_compliance_check_background(`; 3072 `async def set_requirement_pinned(`; 3147 `async def get_hierarchical_requirements(`; 3323 `async def search_company_requirements(`. Ranges tile 121–3364.

Steps:
1. `cp _checks.py <scratch>/checks_orig.py`; `cp __init__.py <scratch>/cs_init_orig.py`
2. Run extraction script → 4 modules
3. Edit `compliance_service/__init__.py`: replace ONLY the `._checks` import block (lines 191–204) with 4 blocks (same 12 names, split by new home, keep `# noqa: F401`). **`__all__` byte-identical.**
4. `git rm _checks.py` (no shim — zero direct importers)
5. Equivalence gate: (a) diff new `__init__.py` vs pristine — only the 191–204 region changed; (b) load `<scratch>/checks_orig.py` via `spec_from_file_location`, assert `inspect.signature` equal for all 12 names old vs new package; (c) assert `_run.py` source contains BOTH the module-level `._normalize` import of `_missing_required_categories` AND the nested `def _missing_required_categories` (shadow pair must coexist)
6. Sweep: `grep -rn "_checks" server/app server/tests` → zero hits

Failure modes: cutting at 1367 orphans the decorator; "deduping" the nested shadow helper silently changes which categories Tier-3 research fetches — forbidden; `__all__` drift.

---

## Part B — `jurisdictions.py` → `admin/jurisdictions/` package (second)

**Header approach: J5 verbatim clone** (the existing admin-package idiom): each submodule = own docstring + lines 2–80 verbatim (imports, both star-imports, `logger`, `router = APIRouter()` at 78). Don't trim dead imports — every existing admin submodule carries the same clone; star-imports make lint-guided trimming unsafe.

9 contiguous files; **include order = file order = original line order** — concatenated route sequence reproduces original registration order exactly. Every cut lands on a `@router.` decorator line; ranges tile 81–4558.

| # | File | Route lines | Routes |
|---|---|---|---|
| 1 | `crud_listing.py` | 81–515 | create, list, tree |
| 2 | `cleanup.py` | 516–1008 | cleanup-duplicates, cleanup-duplicate-requirements, DELETE `{jurisdiction_id}` |
| 3 | `overviews.py` | 1009–1553 | data-/policy-/penalty-overview, api-sources |
| 4 | `quality.py` | 1554–2093 | quality-audit, coverage-matrix, integrity-check |
| 5 | `staleness.py` | 2094–2449 | run-staleness-check, key-coverage |
| 6 | `detail_evals.py` | 2450–3060 | category detail, policy detail, 9 evals routes |
| 7 | `requirements.py` | 3061–3444 | jurisdiction detail GET (here purely to preserve registration order — comment saying so), requirement PATCH/resolve-review/bookmark/bookmarked/reorder |
| 8 | `checks.py` | 3445–4070 | **top-metros/check first**, `{jurisdiction_id}/check`, check-specialty/-medical-compliance/-life-sciences/-federal-sources, apply-federal-sources |
| 9 | `requests_coverage.py` | 4071–4558 | jurisdiction-requests ×3, `/requirements/{id}/codify|history|as-of` tail (4279–4418, stays in line order), general-coverage, vertical-coverage |

Key asserts: 81 `@router.post("/jurisdictions"`, 516, 965 (DELETE), 1009, 1554, 2094, 2450, 2641 (evals/run), 3061 `{jurisdiction_id:uuid}`, 3204 (PATCH), 3445 top-metros, 3567 `{jurisdiction_id}/check`, 4071, 4279 (codify), 4419 (general-coverage).

`jurisdictions/__init__.py` (hand-written): docstring stating include order is load-bearing + the top-metros constraint; import the 9 routers; `router = APIRouter()`; `include_router` each in table order; `__all__ = ["router"]`. One comment noting the Redis cache-key cross-file contract (writers in crud_listing/requirements, invalidators in cleanup/checks — key builders in `app.core.services.redis_cache`; no code moves). `admin/__init__.py:4` works byte-unchanged; `_resolve_jurisdiction_chain` re-export untouched.

Steps:
1. `cp jurisdictions.py <scratch>/jurisdictions_orig.py`
2. Extraction script (header 2–80 as shared prelude constant) → 9 files + `__init__.py`
3. `git rm` the monolith **before** import gates (routes/CLAUDE.md rule: `jurisdictions.py` must not survive alongside `jurisdictions/`)
4. Equivalence gate: ordered OpenAPI route-table diff vs baseline + assert package router has exactly 48 routes
5. Sweep: `grep -rn "admin.jurisdictions\|admin/jurisdictions" server/app server/tests` → only package files + `admin/__init__.py`. Add one-line note in `server/app/core/routes/CLAUDE.md` admin row that jurisdictions is now a package.

Failure modes: route-order regression (top-metros swallow — both in `checks.py` in original order, safe by construction; ordered OpenAPI gate catches everything else); severed nested closures (decorator-line cuts prevent); the 23 lazy in-function imports move automatically with route bodies (all absolute — verified).

---

## Part A — `database.py` → `app/database/` package (last)

### Layout

```
app/database/
├── __init__.py          façade — re-exports 13 pool names + _make_ssl_context + _ensure_handbook_tables + init_db (# noqa: F401; no __all__ — original had none)
├── pool.py       ~200   lines 1–200 verbatim: _pool global + contextvars + init_pool/get_pool/close_pool/has_pool/connection_or_direct/get_connection/_make_ssl_context. ONE edit: line 140 → `from app.config import get_settings`
├── handbook.py   ~465   lines 201–660 verbatim: _ensure_handbook_tables
└── bootstrap/
    ├── __init__.py      init_db orchestrator (below)
    └── 15 domain modules (each: docstring + `async def create_<domain>(conn):` wrapper + verbatim 8-space-indented body — NO dedent)
```

`_pool` + the 3 contextvars deliberately NOT re-exported (mutable `global` rebinding; zero external refs — gate re-proves).

### Bootstrap partition (all cuts on `# ===` banner seams; ranges tile 661–6551)

| Range | Module | Content / hazards |
|---|---|---|
| 661–673 | orchestrator | `async def init_db():` + fast-path guard (users exists → `_ensure_handbook_tables` → return) |
| 674–1135 | `identity.py` | users, admins, companies, SSO, clients, interviews, candidates |
| 1136–1640 | `recruiting.py` | matching/ATS, offer_letters, projects, job_applications |
| 1641–2041 | `er_copilot.py` | ER tables; `CREATE EXTENSION vector` at 1646 stays verbatim AND is hoisted (below) |
| 2042–2355 | `incidents.py` | IR core/CAPA/OSHA/people + IR↔ER bridge ALTERs (order-sensitive, preserved by call order) |
| 2356–2749 | `leads_policies.py` | leads agent + policy mgmt; calls `_ensure_handbook_tables(conn)` at 2603 → module imports it from `app.database.handbook` |
| 2750–3147 | `compliance.py` | compliance tracking + backfill guard |
| 3148–3496 | `jurisdictions.py` | jurisdiction repo; late FK into compliance tables (3241–3259) — safe, runs after `compliance.py` |
| 3497–3836 | `portal_chat.py` | portal note, blog, chat, AI chat, scheduler_settings, RSS, pattern recognition |
| 3837–4185 | `data_sources.py` | structured sources + seeds, posters, rate limits, ai_usage, invitations |
| 4186–4782 | `broker.py` | broker channel incl. `EXECUTE format()` constraint churn — verbatim |
| 4783–5081 | `provisioning.py` | provisioning/HRIS, inbox, reset tokens, beta, hr-news |
| 5082–5184 | `seeds_platform.py` | chat-room + bootstrap-admin seeds, platform_settings, risk snapshots. Edits: line 5099 → `from app.core.services.auth import hash_password`; add `import json` (only json users live here) |
| 5185–5912 | `matcha_work.py` | 24 mw_* tables, journal-RLS for-loop 5837–5874, seeds |
| 5913–6194 | `training.py` | training, i9, cobra, benefits, separation |
| 6195–6549 | `misc_tail.py` | error_logs, channels (+backfill), stray mw_risk_flags/mw_notifications, newsletter |
| 6550–6551 | orchestrator tail | `print("[DB] Tables initialized")` |

`bootstrap/__init__.py`: imports `get_connection`, `_ensure_handbook_tables`, 15 `create_*`; `init_db()` = verbatim fast path, then hoisted `await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")` with comment (pgvector needed by compliance_embeddings/payer_policy_embeddings/er_evidence_chunks across later modules; original statement stays in er_copilot.py; both idempotent), then 15 `await create_X(conn)` calls **in table order** (order load-bearing: cross-module ALTER/FK deps), then the print.

Key asserts: 9 `_pool: Optional[asyncpg.Pool] = None`; 61/154 defs; 201 `_ensure_handbook_tables`; 661 `async def init_db():`; 1646 CREATE EXTENSION; 2603 `_ensure_handbook_tables(conn)` call; 5185 MW banner; 6551 print. Script also asserts every non-blank bootstrap body line has ≥8-space indent (catches mid-statement cuts), and greps each module body for `json.`/`_ssl.` tokens vs imports present.

Steps:
1. `cp app/database.py <scratch>/database_orig.py`; verify `grep -n "from \." app/database.py` → exactly lines 140 + 5099
2. Extraction script → package
3. Hand-write `bootstrap/__init__.py` + façade `__init__.py`
4. `git rm app/database.py`
5. Equivalence gate: **source reconstruction** — strip wrapper defs/docstrings from the 15 modules + pool + handbook, concatenate in orchestrator order, diff vs pristine copy; allowed diff = exactly the 2 rewritten import lines. Symbol gate: `import app.database`; all façade names resolve; `app.database.get_connection is app.database.pool.get_connection` (patch-target invariant). **Never execute `init_db()` as a gate** — even fast path mutates via `_ensure_handbook_tables`.
6. Doc updates: root `CLAUDE.md` — Symbol Map `server/app/database.py:get_connection` → `server/app/database/pool.py:get_connection`, `:init_db` → `server/app/database/bootstrap/__init__.py:init_db`, directory-tree entry, Database-section prose mentioning `database.py:init_db()`; `server/CLAUDE.md` layout entries. Sweep `grep -rn "app/database\.py" CLAUDE.md server/ docs/`.

Failure modes: dedent (forbidden); pool `global` split across modules (all accessors stay in `pool.py`); relative lazy imports (the 2 rewrites are the entire allowed diff); pgvector/FK ordering (hoist + call order + reconstruction gate); `import json` NameError (compile can't catch — token grep gate); doc drift.

## Verification (end-to-end)

Per split: full gate ladder above. After all 3: `cd server && venv/bin/python -c "import app.main"`, OpenAPI diff empty, pytest FAILED set == baseline, `cd client` untouched (no FE changes). Optionally boot backend via `dev-remote.sh` stack and hit `/api/auth/me` + an admin jurisdictions endpoint — user's call. All work stays uncommitted; user reviews and commits one commit per split.
