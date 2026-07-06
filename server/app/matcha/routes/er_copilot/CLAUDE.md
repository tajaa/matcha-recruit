# ER Copilot Routes Package

Backend routes for the Employee Relations (ER) investigation product. Package was split from a 4,132-line flat `er_copilot.py` into per-concern submodules. URL surface unchanged; external import path `app.matcha.routes.er_copilot` stable (`router` + `public_router` re-exported).

Mounted in `routes/__init__.py`: `router` at `/er/cases` (gated by `require_feature("er_copilot")`), `public_router` at `/shared/er-export` (no auth — token-gated share-link download).

## Layout

| File | Concern | Endpoints |
|---|---|---|
| `__init__.py` | Routing assembly + external re-exports | — |
| `_shared.py` | Cross-cutting helpers, constants (`MAX_UPLOAD_SIZE`, `ER_DOC_*_CHAR_CAP`), logger | — |
| `crud.py` | Case lifecycle: create, list, metrics, by-employee, get, update, delete | 7 |
| `export.py` | Case export + share links (authed) **and** public share-link info/download (`public_router`) | 6 |
| `notes.py` | Case notes: list + create | 2 |
| `documents.py` | Document upload, list, get, reprocess, reprocess-all, delete | 6 |
| `analysis.py` | AI analysis: timeline, discrepancies, policy-check, similar-cases (each post + get) | 8 |
| `guidance.py` | AI guidance: suggested guidance (get/post/stream) + outcome analysis (stream/post) | 5 |
| `search.py` | Evidence search (RAG over case documents) | 1 |
| `reports.py` | Report generation: summary, determination letter, report fetch | 3 |
| `case_views.py` | Read-only case views: audit log, retaliation risk, investigation interviews, linked incidents, claims-readiness PDF | 5 |
| **Total** | | **43 routes** (41 `router` + 2 `public_router`) |

## Package router pattern

The package's exported `router` is **`crud.router` directly** — not a wrapping `APIRouter()`. CRUD owns the empty-path collection routes (`@router.post("")`, `@router.get("")`); wrapping it in a bare parent would trip FastAPI's "Prefix and path cannot be both empty" check. All other submodules append into `crud.router` via `router.include_router(...)` in `__init__.py`.

**Consequence**: when adding a new submodule, **never use `@router.X("")` (empty path)**. The empty-path routes only work on the outermost router, reserved for CRUD.

`public_router` lives in `export.py` (share-link download is the only public surface) and is re-exported by `__init__.py` for the separate `/shared/er-export` mount.

## Relative imports

Submodules sit one directory deeper than the old flat file, so **all relative imports carry one extra dot**: app-level modules are `....database` / `....config` / `....core.*`, and matcha-level modules are `...dependencies` / `...services.*` / `...models.er_case`. Cross-submodule helpers come from `._shared`.

## Adding a new endpoint

1. Find the right submodule by concern (or create one if genuinely new).
2. In that submodule, `router = APIRouter()` already exists. Add `@router.<method>("/<path>", ...)`.
3. Helpers come from `from ._shared import ...`. Don't redefine them locally.
4. Tenant isolation: every endpoint that takes `case_id` must call `_verify_case_company(conn, case_id, company_id, is_admin)` from `_shared` — it raises 404 on cross-company access. Derive `company_id` from `get_client_company_id(current_user)`, never trust the path param alone.
5. Audit: write-side actions go through `await log_audit(conn, ...)` from `_shared`.
6. If new submodule: add `from .<name> import router as _<name>_router` and append it to the include loop in `__init__.py`.

## External symbols re-exported by `__init__.py`

Kept working for existing tests that import from the package directly:

- `_build_document_excerpts`, `ER_DOC_PER_DOC_CHAR_CAP`, `ER_DOC_TOTAL_CHAR_CAP` ← `_shared.py` (used by `tests/er_copilot/test_document_excerpts.py`)
- `_queue_risk_assessment_refresh` ← `_shared.py`

`tests/er_copilot/test_er_copilot_risk_refresh.py` loads `crud.py` by file path (create_case / update_case live there now) — it registers `app.matcha.routes.er_copilot` as a package stub so `from ._shared import ...` resolves. This test is part of the pre-existing brittle `spec_from_file_location` set noted in `server/CLAUDE.md`.
