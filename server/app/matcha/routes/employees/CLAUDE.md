# Employees Routes Package

Backend routes for employee management. Package was split from a 5,425-line flat `employees.py` into per-domain submodules on 2026-05-16. URL surface unchanged; external import path `app.matcha.routes.employees` stable.

## Layout

| File | Concern | Endpoints |
|---|---|---|
| `__init__.py` | Routing assembly + 3-router re-exports | — |
| `_shared.py` | Cross-cutting helpers + invitation service + background tasks | — |
| `crud.py` | Collection root + per-employee CRUD + onboarding-progress (**owns `router`**) | 10 |
| `onboarding.py` | Employee onboarding tasks + onboarding-draft endpoints | 9 |
| `offboarding.py` | Offboarding case lifecycle + RTW helpers (`assign_rtw_tasks`) | 4 |
| `invitations.py` | Per-employee invite + bulk-invite + invitations/status | 5 |
| `bulk_upload.py` | Bulk CSV upload (employees + credentials-only) + templates | 4 |
| `leave.py` | Per-employee leave eligibility + place-on-leave | 2 |
| `incidents.py` | Per-employee incidents endpoints | 2 |
| `credentials.py` | Healthcare credentials + credential-document upload/review (**ungated on purpose** — see below) | 8 |
| `oig.py` | OIG LEIE exclusion screening | 4 |
| `pto_admin.py` | **Sibling router `pto_admin_router`** — PTO admin endpoints | 3 |
| `leave_admin.py` | **Sibling router `leave_admin_router`** — leave admin endpoints | 9 |
| **Total** | | **60 routes** |

## Three routers

The package exposes **three** routers from `__init__.py`:

1. `router` — the main employees router. **`router` IS `crud.router`** (re-exported directly). All other domain submodules append into it via `router.include_router(...)` in `__init__.py`.
2. `pto_admin_router` — sibling, NOT included into `router`. Mounted at `/employees/pto` in `routes/__init__.py`.
3. `leave_admin_router` — sibling, NOT included into `router`. Mounted at `/employees/leave` in `routes/__init__.py`.

The two sibling routers share the `require_feature("time_off")` mount-time gate. The leave admin's `/eligibility`, `/deadlines`, `/notices` sub-endpoints add a per-route `require_feature("compliance")` dependency on top.

## Credentials are not gated on `credential_templates`

`credentials.py` is included with no `require_feature` dependency, and that is
deliberate. Two ungated surfaces call these endpoints for tenants that have
`employees` but not `credential_templates` (default-off, Matcha-X/Pro only):

- the employee **Onboarding** tab (`client/src/components/employees/OnboardingTaskList.tsx` → `useCredentialDocuments().upload`), and
- the **employee portal** (`routes/employee_portal/credential_documents.py`, itself ungated) — gating only the admin side would let an employee upload a document no admin could list, approve or download.

`credential_templates` gates the *template/requirement* surface, not credential
documents themselves. Reverted 2026-09-03 after PR #420 added a subrouter-wide
gate; the front-end `credentials` tab in `EmployeeDetail.tsx` stays unconditional
for the same reason.

## Package router pattern

Same as IR: `router` in `__init__.py` is `crud.router` directly — not a wrapping `APIRouter()`. CRUD owns the empty-path collection routes (`@router.post("")`, `@router.get("")`); wrapping it in a bare parent would trip FastAPI's "Prefix and path cannot be both empty" check.

**Consequence**: when adding a new submodule, **never use `@router.X("")` (empty path)**. The empty-path routes only work on the outermost router (crud).

## Adding a new endpoint

1. Find the right submodule by domain. If genuinely new, create a new submodule.
2. In that submodule, `router = APIRouter()` already exists. Add `@router.<method>("/<path>", ...)`.
3. Helpers come from `from ._shared import ...`. Don't define them locally if `_shared.py` already has them.
4. Tenant isolation: every endpoint that takes an employee/leave/document id must filter by `company_id = await get_client_company_id(current_user)` and verify ownership before reading/writing.
5. If adding a new submodule: add `from .<name> import router as _<n>_router; router.include_router(_<n>_router)` to `__init__.py`.

## Route shadowing (preserved from pre-split behavior)

CRUD declares `/{employee_id}` for GET/PUT/DELETE. Several submodules declare 1-segment static GETs/PUTs/DELETEs that get shadowed today:

- `GET /incident-counts` (incidents.py) — shadowed by `GET /{employee_id}`
- `GET /oig-summary` (oig.py) — shadowed by `GET /{employee_id}`
- `GET /onboarding-draft` (onboarding.py) — shadowed by `GET /{employee_id}`
- `PUT /onboarding-draft` (onboarding.py) — shadowed by `PUT /{employee_id}`
- `DELETE /onboarding-draft` (onboarding.py) — shadowed by `DELETE /{employee_id}`

Behavior: client request lands on `/{employee_id}` first, FastAPI tries to coerce the literal string to UUID, returns 422 with no fallthrough.

**Don't add a new 1-segment static GET/PUT/DELETE to any submodule** — it would be shadowed. Put those routes in `crud.py` BEFORE `/{employee_id}` registers if you want them reachable. POST 1-segment paths are fine (crud's POST is on the empty-path collection root, not on `/{employee_id}`).

## Cross-submodule call

`onboarding.py:assign_return_to_work_tasks` route calls `assign_rtw_tasks`, which lives in `offboarding.py`. To avoid an intra-package module-level cycle, the call uses a **lazy** `from app.matcha.routes.employees.offboarding import assign_rtw_tasks` inside the route body. Keep this pattern if any future submodule needs to call functions defined in another submodule.

## External symbols re-exported by `__init__.py`

Keep these working when moving things around:

- `router`, `pto_admin_router`, `leave_admin_router` — consumed by `routes/__init__.py:7`
- `_refresh_risk_assessment` — lazy-imported by `er_copilot.py:91` and `workers/tasks/er_analysis.py:132`. Now lives in `_shared.py`.
- `EmployeeCreateRequest` — imported by `tests/training/test_employee_create_supervisor.py:3`. Lives in `crud.py`.

## Mounting

```python
# routes/__init__.py
matcha_router.include_router(employees_router, prefix="/employees", tags=["employees"],
                             dependencies=[Depends(require_feature("employees"))])
matcha_router.include_router(pto_admin_router, prefix="/employees/pto", tags=["pto-admin"],
                             dependencies=[Depends(require_feature("time_off"))])
matcha_router.include_router(leave_admin_router, prefix="/employees/leave", tags=["leave-admin"],
                             dependencies=[Depends(require_feature("time_off"))])
```

`tags` apply at the mount, not per-route. **Do not** add `tags=...` to any submodule decorator.

## Imports convention

- Absolute `from app.X import …` for app-level imports.
- Relative `from ._shared import …` / `from .offboarding import …` for intra-package imports (matches IR convention).
- Lazy imports inside function bodies are OK for circular-import avoidance — used for `assign_rtw_tasks`, service singletons (`get_leave_agent`, `get_oig_screening_service`, etc.), and the `_refresh_risk_assessment` consumers.
- Employee creation treats `send_invitation=true` as explicit administrator intent.
  The legacy tenant `auto_send_invitation` preference applies only when neither an
  explicit send nor skip is requested. OIG screening is independent: a possible name
  match alerts administrators to verify identity but does not suppress portal access.

## Tests

Four tests used to load a route module via `importlib.util.spec_from_file_location` with a
hard-coded `employees.py` path (a pattern that breaks at collection time on any package
split, silently). Refactor round 2 stage 4 (`f84c537`) rewrote three of them to plain
imports against the split submodules; only one is still genuinely broken:

- `tests/employees/test_employee_invites_and_compliance.py` — **fixed**. 2 tests pass; a
  third, `test_create_employee_syncs_compliance_location`, is `xfail(strict=True)` — it
  does not model credential auto-tasks or new-hire training evaluation added after the
  test was written.
- `tests/employees/test_internal_mobility_routes.py` — **still broken**. Imports
  `app.matcha.routes.internal_mobility`, a module that does not exist (pre-existing on
  `main`, not something a package split could fix).
- `tests/er_copilot/test_er_copilot_risk_refresh.py` — **fixed**, both tests pass. Also
  surfaced a real patch-target bug in the test itself, not the app: `create_case_core`
  reaches `log_audit` via `routes.er_copilot._shared`'s own binding, so patching
  `crud.py`'s copy of the name never intercepted the call.
- `tests/training/test_employee_create_supervisor.py` — passes; was never actually broken
  by the spec-load pattern.

Run the full passing set (no `--ignore` needed anymore, except the one real collection
error):
```bash
cd server && ./venv/bin/python -m pytest tests/employees/ tests/er_copilot/ tests/training/ -q \
  --continue-on-collection-errors
```
Expect: only `tests/employees/test_internal_mobility_routes.py` errors at collection;
everything else passes (plus the 1 `xfail(strict)` above and the pre-existing
`google_workspace_onboarding` failures noted in `server/CLAUDE.md`). Re-measure rather
than trust this list — see `server/CLAUDE.md`'s own note on the same point.
