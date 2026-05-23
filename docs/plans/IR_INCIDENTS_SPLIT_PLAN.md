# Plan: Split `ir_incidents.py` into a Package

## Context

`server/app/matcha/routes/ir_incidents.py` is **5,061 lines** and owns **9 unrelated concerns** under one router. Every edit forces Claude (and humans) to load the entire file into context, even for a one-line change in a single endpoint. The file grew organically since the IR product launched and was never split.

Concrete cost: yesterday's IR Copilot close-out fix had to read ~500 lines of unrelated CRUD/analytics/OSHA code just to land a 3-method change in the copilot section. Multiply by every IR session.

## What's Actually In There

Counts derived from running `grep -nE "^(async def|def|@router\.)" ir_incidents.py`:

| Concern | Approx lines | Endpoint count |
|---|---|---|
| Helpers + pre-routes | 395 | (0 endpoints — `_sse`, `log_audit`, `_resolve_employee_refs`, `_auto_classify_incident_task`, `send_ir_notifications_task`, `_get_incident_with_company_check`, `parse_witnesses`, `row_to_response`) |
| Core CRUD | 766 | 5 (`create_incident`, `list_incidents`, `export_incidents`, `get_incident`, `update_incident`, `delete_incident`) |
| Anonymous reporting | 87 | 3 |
| OSHA logs + forms | 315 | 5 |
| Documents | 197 | 3 |
| Analytics + risk | 854 | 7 |
| Audit log API | 61 | 1 |
| AI analysis | 1053 | 8 |
| Investigation interviews | 631 | 6 |
| Copilot | 609 | 5 (+ helpers) |
| **TOTAL** | **~5061** | **~43 endpoints** |

## Target Layout

Convert the single file into a package, preserving the import path `app.matcha.routes.ir_incidents` so `routes/__init__.py`'s `from .ir_incidents import router as ir_incidents_router` keeps working with zero change.

**Important: Python cannot have `ir_incidents.py` and `ir_incidents/__init__.py` coexist at the same path.** The migration therefore renames the flat file to `_legacy.py` inside the new package on day one; subsequent steps drain endpoints out of `_legacy.py` into proper submodules; final step deletes `_legacy.py`.

```
server/app/matcha/routes/ir_incidents/
├── __init__.py                # Builds and re-exports the combined `router` + external symbols
├── _legacy.py                 # Renamed flat file. Shrinks each step. Deleted at the end.
├── _shared.py                 # Cross-module helpers + dependencies (created step 1; populated as helpers move out of _legacy)
├── crud.py                    # create / list / get / update / delete / export
├── anonymous_reporting.py     # public token status + generate + disable
├── documents.py               # upload / list / delete
├── osha.py                    # 300-log, 301, 300A + CSV exports + recordability + AI determine
├── analytics.py               # summary, trends, locations, WC metrics, risk-matrix, risk-insights, consistency
├── audit_log.py               # GET /{id}/audit-log
├── ai_analysis.py             # categorize, severity, root-cause, recommendations, similar, policy-mapping + clear-cache
├── investigation_interviews.py # create / batch / resend / generate-link / list / cancel
└── copilot.py                 # transcript / stream / accept / skip / close + copilot helpers
```

No `_types.py`. The current `ir_incidents.py` has **zero top-level `class` definitions** — every Pydantic model is already imported from `server/app/matcha/models/` (confirmed by `grep "^class\b" ir_incidents.py` returning empty). Models stay where they live today.

### `__init__.py` — Mounting Strategy

The parent mount in `server/app/matcha/routes/__init__.py:64` already adds the prefix and feature gate:

```python
matcha_router.include_router(ir_incidents_router, prefix="/ir/incidents", tags=["ir-incidents"],
                             dependencies=[Depends(require_feature("incidents"))])
```

Therefore the package's combined `router` must be a **bare** `APIRouter()` with no prefix or tags — otherwise paths double up to `/ir/incidents/ir/incidents/{id}`.

```python
"""IR Incidents router package — composed from per-domain submodules.

External callers continue to do:
    from app.matcha.routes.ir_incidents import router as ir_incidents_router
"""
# The package's exported `router` IS `_legacy.router` directly. Wrapping
# `_legacy.router` inside a fresh `APIRouter()` and calling
# `wrapper.include_router(_legacy_router)` fails with
#   FastAPIError: Prefix and path cannot be both empty (path operation: create_incident)
# because `_legacy` registers root-collection routes via `@router.post("")`
# and FastAPI refuses to compose two empty-path segments. By exposing
# `_legacy.router` directly, the only prefix in play is the one applied at
# the parent mount in `server/app/matcha/routes/__init__.py:64`.
#
# As later submodules arrive, they import this same router and call
# `router.include_router(submodule_router)`. Submodules MUST NOT register
# their own routes with `@router.X("")` — empty paths only work because
# they originate from `_legacy.router` itself.
from ._legacy import router  # noqa: F401  (package public symbol)

# External re-exports. Hardcoded here so callers do not need to know which
# submodule a helper currently lives in. As helpers migrate out of _legacy
# into _shared / copilot / etc., flip the source on each line below.
from ._legacy import compute_wc_metrics              # noqa: F401  used by broker_portfolio.py
from ._legacy import (                                # noqa: F401  used by inbound_email.py
    _parse_occurred_at,
    generate_incident_number,
    send_ir_notifications_task,
)
from ._legacy import _close_incident_via_copilot     # noqa: F401  future cross-router use
```

Each submodule defines its own `router = APIRouter()` **without** any prefix. Each submodule's path strings (`"/"`, `"/{incident_id}"`, `"/copilot/stream"`, etc.) stay byte-identical to today's strings. URL surface unchanged.

As each step migrates endpoints, the corresponding `from ._legacy import …` lines flip to `from .copilot import …` / `from ._shared import …` / etc. The external import contract from `broker_portfolio.py` and `inbound_email.py` (`from .ir_incidents import compute_wc_metrics`, etc.) never changes — the package `__init__.py` is the stable seam.

### `_shared.py` — What Goes Here

Move everything cross-cutting that more than one submodule needs:

- `_sse(event: dict) -> str`
- `_company_filter(param_idx: int) -> str`
- `_to_naive_utc`, `_utc_now_naive`, `_parse_occurred_at`
- `_get_incident_with_company_check`
- `_safe_json_loads` (defined twice in current file at lines 412 and 1022 — dedupe to one definition)
- `_coerce_metadata_dict`
- `parse_witnesses`, `row_to_response`
- `generate_incident_number`
- `log_audit`
- `_resolve_employee_refs`
- `_auto_classify_incident_task`
- `_get_company_admin_contacts`
- `send_ir_notifications_task`
- `_FIELD_WHITELIST`, `_FIELD_LABELS`, `_VALID_INCIDENT_TYPES`, `_VALID_SEVERITIES`, `_VALID_STATUSES`, `_validate_field_value`

As helpers migrate from `_legacy.py` into `_shared.py`, the package `__init__.py` re-export lines for any externally consumed helper (`_parse_occurred_at`, `generate_incident_number`, `send_ir_notifications_task`) flip from `from ._legacy import …` to `from ._shared import …`. The external import contract stays stable.

## Critical Files to Modify

- `server/app/matcha/routes/ir_incidents.py` → delete and replace with a package
- `server/app/matcha/routes/__init__.py` → **no change**; the package's `__init__.py` re-exports `router` so `from .ir_incidents import router as ir_incidents_router` keeps working
- `server/app/matcha/routes/er_copilot.py` (and anywhere else) → check for any direct imports of helpers like `_close_incident_via_copilot`, `log_audit`, `_get_incident_with_company_check`, `_FIELD_WHITELIST` — these will need to import from `app.matcha.routes.ir_incidents._shared` (or from the package via the re-export in `__init__.py`)
- `server/tests/` → grep for `from app.matcha.routes.ir_incidents import` and update if any tests import internal helpers

## Reused / Existing Pieces

- Existing `APIRouter.include_router` composition pattern — already used in `server/app/main.py` and many sub-routers
- Existing `_close_incident_via_copilot` helper (just landed in commit `05fce70`) — moves cleanly into `copilot.py`
- Existing `_FIELD_WHITELIST`, `_FIELD_LABELS`, `_VALID_*` constants — move to `_shared.py` since both `copilot.py` and `crud.py` (update path) use them
- Existing `IR_ACTION_TYPES` already lives in `ir_ai_orchestrator.py` — no duplication
- Existing audit-log pattern in `log_audit()` — central to `_shared.py`, called from every submodule

## Execution Order (one PR per submodule, lowest-risk first)

Each step ships independently. After every step the app must still boot and `pytest` must still pass.

0. **Pre-step: convert relative imports to absolute.** The current `ir_incidents.py` uses dotted-relative imports (`from ...database import get_connection`, `from ..models.ir_incident import …`, `from ..dependencies import …`, etc.). When this file moves into a subdirectory, its package depth increases by one, so every `from ..X` must become `from ...X` to resolve to the same module. To avoid the brittle "rewrite every relative import" pass, instead **convert all relative imports in `ir_incidents.py` to absolute imports first** (`from app.database import …`, `from app.matcha.models.ir_incident import …`, `from app.matcha.dependencies import …`). Commit this on its own. Absolute imports are depth-invariant, so step 1's `git mv` becomes a true pure-rename with no content edits required. Use the same convention in every new submodule.

1. **Create the package skeleton.** `git mv server/app/matcha/routes/ir_incidents.py server/app/matcha/routes/ir_incidents/_legacy.py`. Add `server/app/matcha/routes/ir_incidents/__init__.py` shown above — bare `APIRouter()`, mounts `_legacy.router`, re-exports `compute_wc_metrics` / `_parse_occurred_at` / `generate_incident_number` / `send_ir_notifications_task` / `_close_incident_via_copilot`. Add an empty `_shared.py`. Original endpoints still execute from `_legacy.py`; every external importer keeps working unchanged. Validate: `python3 -c "from app.main import app; print(len(app.routes))"` returns the same count as before. **(Lowest risk — git sees this as a pure rename plus a 30-line `__init__.py`.)**
2. **`audit_log.py`** — single endpoint, tiny surface, low blast radius. Validate the extraction pattern works end-to-end. After this step the `__init__.py` adds `from .audit_log import router as _audit_router; router.include_router(_audit_router)` and `_legacy.py` shrinks by 61 lines.
3. **`anonymous_reporting.py`** — 3 endpoints, isolated from rest of IR.
4. **`documents.py`** — 3 endpoints, only touches `ir_incident_documents` table.
5. **`osha.py`** — 5 endpoints, self-contained OSHA logic.
6. **`investigation_interviews.py`** — 6 endpoints, isolated.
7. **`ai_analysis.py`** — 8 endpoints. Bigger; touches Gemini calls. Keep prompt-building inline for now; future PR can push to `services/`.
8. **`analytics.py`** — 7 endpoints. Contains the heavy SQL; verify response shapes vs frontend after move. **Move `compute_wc_metrics` here at the same time** — flip its re-export in `__init__.py` from `_legacy` to `analytics`.
9. **`copilot.py`** — 5 endpoints + helpers. Move `_close_incident_via_copilot` here at the same time; flip its re-export.
10. **`crud.py`** — moves last because every other submodule may depend on `row_to_response` / `_get_incident_with_company_check` which finalize in `_shared.py`. Move the helper migrations to `_shared.py` at the same time and flip the `_parse_occurred_at` / `generate_incident_number` / `send_ir_notifications_task` re-exports.

   **Step-10-specific gotcha:** the empty-path routes `@router.post("")` and `@router.get("")` (collection root) move out of `_legacy.py` into `crud.py`. The pattern `router.include_router(crud_router)` will then raise the same FastAPI "Prefix and path cannot be both empty" error that we worked around in step 1. Mitigations:
   - **Recommended:** flip `__init__.py` to `from .crud import router` once CRUD lands. The package's exported `router` then becomes `crud.router`, and the remaining `_legacy` content (if any still exists at this point) gets included into `crud.router` via the inverse `crud_router.include_router(_legacy_router)`. The empty-path routes live on the "outermost" router, so no empty-on-empty composition ever happens.
   - Alternative: keep a single shared `APIRouter()` created in `__init__.py` and have submodules accept it as an argument (`def register_routes(router: APIRouter) -> None`) instead of owning their own — bigger refactor, not recommended.
11. **Delete `_legacy.py`** — once all endpoints and all four externally-imported helpers have migrated. The package `__init__.py` keeps the re-export lines (now pointing at the new homes), so `broker_portfolio.py` and `inbound_email.py` need no edits.

Each step is a separate commit. Each step's diff should be 95%+ pure motion — almost no logic edits. Reviewers can `git diff -M -B` and confirm move-with-rename detection.

## Risks + Mitigations

| Risk | Mitigation |
|---|---|
| `ir_incidents.py` and `ir_incidents/` cannot coexist | Step 1 renames the flat file to `ir_incidents/_legacy.py` via `git mv`. There is never a moment where both exist |
| Relative imports break when the file moves into a subdirectory | The flat file uses `from ...database`, `from ..models.X`, etc. Moving into `ir_incidents/_legacy.py` increases the package depth by one; every relative would need an added dot. **Pre-step 0** converts them all to absolute imports before any rename, eliminating the issue entirely |
| Route trailing-slash semantics | Current handlers use `@router.post("")` (empty string) for the collection root. FastAPI does NOT normalize this — `POST /ir/incidents` and `POST /ir/incidents/` behave differently. Submodules **must** keep `""` and not switch to `"/"`. Verified by the OpenAPI-diff verification step |
| `send_ir_notifications_task` / `_auto_classify_incident_task` are not Celery tasks | They are plain `async def` consumed via FastAPI `BackgroundTasks.add_task(fn, ...)` (callsites at `ir_incidents.py:629, 644, 1576`). No Celery autodiscovery dependency on the file location. Workers reference the `ir_incidents` table in SQL strings (`workers/tasks/interview_analysis.py`) — table name, not Python module — also unaffected |
| Ruff F401 (unused import) flags package re-exports | Every `from ._legacy import X` in `__init__.py` needs `# noqa: F401` because the package re-exports without using the symbol locally. Apply consistently |
| Imports of private helpers elsewhere break | Confirmed external consumers: `broker_portfolio.py` (`compute_wc_metrics`), `inbound_email.py` (`_parse_occurred_at`, `generate_incident_number`, `send_ir_notifications_task`). The package `__init__.py` re-exports all four from `_legacy.py` initially and flips each re-export target as the symbol migrates. No other private-helper imports exist in the codebase (verified via `grep -rn "from .ir_incidents\|from app.matcha.routes.ir_incidents" server/`) |
| FastAPI route ordering changes (e.g. `/{incident_id}` shadowing `/analytics/...`) | Today the file orders specific paths before parameterized paths. Preserve that order at the `include_router` level by registering `analytics`, `osha`, `anonymous_reporting`, `copilot` (which have static prefixes) **before** `crud` (which has the catch-all `/{incident_id}`). The compose loop in `__init__.py` controls this order. While `_legacy.py` still owns `/{incident_id}`, mount it last |
| Feature-gate dependency is lost | `routes/__init__.py:64` attaches `dependencies=[Depends(require_feature("incidents"))]` to the mount. FastAPI stacks dependencies through `include_router`, so each submodule transparently inherits the gate. No submodule needs to re-declare it |
| Duplicate `_safe_json_loads` definitions | Already defined twice in `_legacy.py` (lines 412 and 1022). Single definition in `_shared.py` resolves the duplication during whichever step moves the second one (likely step 9 or 10) |
| Tests that import internals break silently | After every step, run `cd server && python3 -m pytest tests/ -x -q`. The `-x` flag stops on first failure so import errors surface immediately. `tests/ir_incidents/test_ir_incidents.py:680` uses `importlib.util.find_spec("app.matcha.routes.ir_incidents")` — `find_spec` resolves packages the same as modules, so no test edit needed |
| Production deploy hiccup if any module fails to import | Each PR is independently revertable. Step 1 has small blast radius because it is a pure rename + thin `__init__.py`; subsequent steps each touch only one domain |

## Out of Scope (Intentionally Not Doing Yet)

- Pushing Gemini prompt-building from `ai_analysis.py` into `services/` (worth doing later — separate refactor)
- Pushing heavy analytics SQL into `services/ir_analytics_service.py` (later — would shrink `analytics.py` further but not necessary for the context-cost win)
- Splitting `services/ir_ai_orchestrator.py` itself (it's only ~600 lines and cohesive — not a problem)
- Splitting `server/app/core/services/email.py` and `server/app/matcha/routes/employees.py` — those are items 7b and 7c in `CLAUDE_CODE_PLAN.md` and ship after this one lands

## Verification

**Take baseline snapshots before pre-step 0 begins:**

```bash
cd server && python3 -c "from app.main import app; print(len(app.routes))" > /tmp/ir-route-count.txt
cd server && python3 -c "import json; from app.main import app; print(json.dumps(sorted([(r.path, sorted(list(r.methods or []))) for r in app.routes if hasattr(r, 'methods')]), default=str))" > /tmp/ir-openapi-baseline.txt
```

After **each** step (not just at the end):

1. **App boots**: `cd server && python3 -c "from app.main import app; print(len(app.routes))"` — route count must match `/tmp/ir-route-count.txt` exactly.
2. **OpenAPI surface unchanged**: regenerate the same file as `/tmp/ir-openapi-after.txt`, then `diff /tmp/ir-openapi-baseline.txt /tmp/ir-openapi-after.txt` — must be empty. Catches trailing-slash drift, accidental prefix doubling, missing endpoints.
3. **Tests green**: `cd server && python3 -m pytest tests/ -x -q`.
4. **Frontend still talks**: hit `/ir/incidents`, `/ir/incidents/{id}/copilot/stream`, `/ir/incidents/analytics/risk-insights` from a logged-in session in the matcha-lite UI. No 404s.
5. **No stale imports**: `cd server && grep -rn "from app.matcha.routes.ir_incidents import" .` — every match should resolve at runtime (test by importing in a REPL).

After the **final** step:

6. `wc -l server/app/matcha/routes/ir_incidents/*.py` — no single file > ~700 lines.
7. End-to-end manual smoke: create an incident → run categorize analysis → upload a document → open copilot → close via copilot button → check audit log → export CSV.
