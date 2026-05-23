# Plan: Split `server/app/matcha/routes/employees.py` into a Package

## Context

`employees.py` at 5,425 lines is the second-largest router in the codebase and the last open item from `CLAUDE_CODE_PLAN.md` (item 7c). It owns 7+ unrelated concerns (CRUD, bulk upload, invitations, onboarding tasks, offboarding cases, PTO admin, leave admin, per-employee leave, incidents, onboarding-draft, credentials + credential-documents, OIG screening) and edits routinely require reading hundreds of unrelated lines. It also declares **3 routers** (`router`, `pto_admin_router`, `leave_admin_router`), making it structurally more complex than the IR or email splits.

This is a pure mechanical extraction modeled on `server/app/matcha/routes/ir_incidents/` (132 tests, stable). No behavior change — every route's path/method/response_model/auth-dep stays identical. Verified by OpenAPI-spec diff at every phase.

## Decisions

- **Branch:** continue on `werk-refactor`.
- **Granularity:** one commit per phase (14 commits).
- **Shadow check:** OpenAPI-diff + route-order diff. No live HTTP capture (FastAPI's `app.routes` order capture catches shadow regressions without needing the SSH tunnel).

## Target layout

```
server/app/matcha/routes/employees/
├── __init__.py        — re-exports + sub-router include_router glue
├── _shared.py         — helpers + invitation service + background tasks
├── crud.py            — list/get/create/update/status/delete + collection root + onboarding-progress (owns `router`)
├── invitations.py     — invite, resend, bulk-invite, invite-all, invitations/status
├── bulk_upload.py     — bulk-upload + credentials-template + credentials-upload
├── onboarding.py      — /{employee_id}/onboarding/* + /onboarding-draft + onboarding task models
├── offboarding.py     — /{employee_id}/offboard/* + RTW helpers + offboarding task models
├── leave.py           — /{employee_id}/leave/eligibility + /place
├── incidents.py       — /incident-counts + /{employee_id}/incidents
├── credentials.py     — /{employee_id}/credentials + credential-documents (upload/approve/reject/download)
├── oig.py             — /oig-summary + /oig-batch-screen + /{id}/oig-status + /{id}/oig-screen
├── pto_admin.py       — owns `pto_admin_router` (sibling, NOT included into main router)
└── leave_admin.py     — owns `leave_admin_router` (sibling, NOT included into main router)
```

External consumers (must keep working):
- `routes/__init__.py:7` — `from .employees import router as employees_router, pto_admin_router, leave_admin_router`
- `er_copilot.py:91` (lazy) — `_refresh_risk_assessment`
- `workers/tasks/er_analysis.py:132` (lazy) — `_refresh_risk_assessment`
- `tests/training/test_employee_create_supervisor.py:3` — `EmployeeCreateRequest` (test is pre-broken; preserve symbol anyway)

## Package `__init__.py` (final shape)

```python
"""Employees router package. Split from a 5,425-line flat file 2026-05-16."""

# Main router lives in crud.py — it owns the collection-root @router.post("") / @router.get("")
# routes, so the package router IS crud.router (IR pattern).
from .crud import router  # noqa: F401

# Append sub-routers to the main router in source-order for shadowing parity.
from .invitations import router as _invitations_router; router.include_router(_invitations_router)
from .bulk_upload import router as _bulk_upload_router; router.include_router(_bulk_upload_router)
from .onboarding import router as _onboarding_router; router.include_router(_onboarding_router)
from .offboarding import router as _offboarding_router; router.include_router(_offboarding_router)
from .leave import router as _leave_router; router.include_router(_leave_router)
from .incidents import router as _incidents_router; router.include_router(_incidents_router)
from .credentials import router as _credentials_router; router.include_router(_credentials_router)
from .oig import router as _oig_router; router.include_router(_oig_router)

# Sibling routers — mounted at separate prefixes in routes/__init__.py:46,48.
from .pto_admin import router as pto_admin_router  # noqa: F401
from .leave_admin import router as leave_admin_router  # noqa: F401

# External re-exports.
from ._shared import _refresh_risk_assessment  # noqa: F401 (er_copilot, er_analysis worker)
from .crud import EmployeeCreateRequest  # noqa: F401 (test consumer)
```

## `_shared.py` contents

- Pure helpers (orig 46–104): `_json_object`, `_coerce_bool`, `_exception_message`, `_parse_csv_date`, `_column_exists`.
- Column-probe helpers (106–153): `_employee_compensation_fields_available`, `_employee_status_fields_available`, `_employee_org_fields_available`.
- Location sync (156–184): `_sync_employee_location_for_compliance`.
- Comp tuple builder (187–197): `_employee_compensation_values`.
- Invitation service (377–506): `send_single_invitation`, `_send_invitation_with_conn`, `_auto_send_invitation`.
- Background tasks (509–787): `_refresh_risk_assessment`, `_perform_oig_screening`, `_run_provisioning_and_notify`, `_send_provisioning_email`.
- Constants: `INVITATION_SEND_FAILED_DETAIL`.
- Existing lazy imports inside function bodies (`get_settings` line 547, `get_oig_screening_service` line 574) stay lazy.

## Pydantic model placement

| Model | Lives in | Re-exported? |
|---|---|---|
| `EmployeeCreateRequest`, `EmployeeUpdateRequest`, `EmployeeStatusUpdateRequest`, `EmployeeListResponse`, `EmployeeDetailResponse`, `OnboardingProgressItem` | `crud.py` | `EmployeeCreateRequest` only |
| `InvitationResponse`, `BulkInviteResponse`, `InvitationStatusItem`, `InvitationStatusSummary` | `invitations.py` | — |
| `BulkEmployeeCSVUpload`, `BulkCredentialsUploadResponse` | `bulk_upload.py` | — |
| `EmployeeOnboardingTaskResponse`, `AssignOnboardingTasksRequest`, `UpdateOnboardingTaskRequest` | `onboarding.py` | — |
| `OffboardingCase*`, `OffboardingTask*`, RTW/offboarding constants, `_to_offboarding_task_response`, `_to_offboarding_case_response`, `_ensure_rtw_templates`, `assign_rtw_tasks` | `offboarding.py` | — |
| `PlaceOnLeaveRequest` | `leave.py` | — |
| `EmployeeCredentialsRequest`, `EmployeeCredentialsResponse`, `CredentialDocumentResponse` | `credentials.py` | — |
| `PTORequestAdminResponse`, `PTORequestActionRequest`, `PTOSummaryStats` | `pto_admin.py` | — |
| `LeaveActionRequest`, `LeaveRequestAdminResponse`, `ReturnCheckinRequest`, `LeaveDeadlineResponse`, `LeaveDeadlineActionRequest`, `LeaveNoticeRequest` | `leave_admin.py` | — |

`assign_rtw_tasks` (defined line 2870) has exactly 1 caller at line 3157 inside `assign_return_to_work_tasks` route in the onboarding section (3136). After split, that route moves to `onboarding.py`; `assign_rtw_tasks` lives in `offboarding.py`. `onboarding.py` does a **lazy** `from .offboarding import assign_rtw_tasks` inside the function body to break the module-level cycle. Matches IR's `_auto_map_policy_violations` pattern.

## Phased rollout (one commit per phase, all on `werk-refactor`)

### Phase 0 — Baseline capture (no commit)
- Generate **full** OpenAPI baseline (catches response_model / auth-dep / tags drift, not just path/method add-remove):
  ```bash
  cd server && ./venv/bin/python -c "
  from app.main import app; import json
  print(json.dumps(app.openapi(), indent=2, sort_keys=True))
  " > /tmp/openapi_employees_baseline.json
  ```
- Generate **route-order baseline** (catches shadow-order regressions that the sorted-spec diff misses):
  ```bash
  ./venv/bin/python -c "
  from app.main import app
  for r in app.routes:
      methods = sorted(getattr(r, 'methods', []) or [])
      print(f\"{','.join(methods):10s} {r.path}\")
  " > /tmp/routes_employees_baseline.txt
  ```
- Run test subset baseline:
  ```bash
  ./venv/bin/python -m pytest tests/employees/ -q \
    --ignore=tests/employees/test_employee_invites_and_compliance.py \
    --ignore=tests/employees/test_internal_mobility_routes.py
  ```
  Record pass count.

### Phase 1 — Relative→absolute import sweep (commit 1)
- In current `employees.py`, convert all `from ...database`, `from ...core.*`, `from ..dependencies`, `from ..services.*` (lines 21–35) to absolute `from app.X`.
- Also convert all in-function lazy relative imports.
- Verify.

### Phase 2 — Create package + `_legacy.py` shim (commit 2)
- `mkdir server/app/matcha/routes/employees/` and `git mv server/app/matcha/routes/employees.py server/app/matcha/routes/employees/_legacy.py`.
- Add `employees/__init__.py`:
  ```python
  from ._legacy import (
      router, pto_admin_router, leave_admin_router,
      _refresh_risk_assessment, EmployeeCreateRequest,
  )
  __all__ = ["router", "pto_admin_router", "leave_admin_router",
             "_refresh_risk_assessment", "EmployeeCreateRequest"]
  ```
- Verify.

### Phase 3 — Extract `_shared.py` (commit 3)
- Create `_shared.py`. Move helpers + invitation service + background tasks out of `_legacy.py`.
- In `_legacy.py`, replace defs with `from ._shared import …`.
- Update `__init__.py` to re-export `_refresh_risk_assessment` from `._shared` (not `._legacy`).
- Verify.

### Phase 4 — Extract `pto_admin.py` (commit 4)
- Move lines 3768–3966 + PTO models to `pto_admin.py` with new `router = APIRouter()`.
- Delete moved block from `_legacy.py`.
- **Delete the `pto_admin_router = APIRouter()` declaration from `_legacy.py` (currently line 40).** The bare `APIRouter()` becomes orphan once the routes move; leaving it ships a dead empty router.
- Switch `__init__.py` re-export of `pto_admin_router` from `._legacy` to `.pto_admin`.
- Verify.

### Phase 5 — Extract `leave_admin.py` (commit 5)
- Move lines 3968–4544 + leave models to `leave_admin.py`.
- **Delete the `leave_admin_router = APIRouter()` declaration from `_legacy.py` (currently line 41).** Same orphan-cleanup as Phase 4.
- Switch `__init__.py` re-export of `leave_admin_router`.
- Verify.

### Phase 6 — Extract leaf submodules (commits 6–13)

Order chosen so each commit's dependencies live in `_shared.py` already, or are leaf-only:

6. **`oig.py`** (5309–end) — uses `_perform_oig_screening` from `_shared`.
7. **`incidents.py`** (4630–4693) — pure SQL, no shared helpers.
8. **`leave.py`** (4546–4628) — already uses lazy service imports.
9. **`credentials.py`** (4795–5304) — self-contained.
10. **`bulk_upload.py`** (1746–2426) — calls `send_single_invitation` + `_perform_oig_screening` from `_shared`.
11. **`invitations.py`** (1706–1745, 2428–2629) — calls `send_single_invitation` from `_shared`.
12. **`offboarding.py`** (2631–3766 less PTO/leave already moved). Define `assign_rtw_tasks` here; `_legacy.py`'s onboarding section still calls it via a local name. Update `_legacy.py` to `from .offboarding import assign_rtw_tasks` at module top (or lazy inside the route body — either works since both modules are already loaded).
13. **`onboarding.py`** (2935–3389, 4695–4792). Move `assign_return_to_work_tasks` route + onboarding-draft routes. Lazy `from .offboarding import assign_rtw_tasks` inside the route body to break module-level cycle.

Per step:
- Move section(s) + their Pydantic models.
- Create `router = APIRouter()` in the new file.
- Add `from .<name> import router as _<n>_router; router.include_router(_<n>_router)` to `__init__.py`. **Intermediate `__init__.py` state during phase 6:** top stays `from ._legacy import router` (and remaining re-exports); each phase appends a fresh `router.include_router(...)` line for the newly extracted submodule. `router` is mutated after `_legacy.py` finishes its own decorator registrations — load order is correct.
- Drop the moved block from `_legacy.py`.
- Verify.

### Phase 7 — `crud.py` + delete `_legacy.py` (commit 14)
- Rename what's left in `_legacy.py` to `crud.py` (or copy contents). Should be: imports + 6 Pydantic models + `router = APIRouter()` + `/onboarding-progress` + lines 831–1705 of original (main CRUD block).
- Switch `__init__.py` top imports from `._legacy` to `.crud`.
- Delete `_legacy.py`.
- Verify (final spec + route-order diff vs phase-0 baseline = empty).

## Verification harness (run between every phase)

```bash
cd server

# 1. Import surface
./venv/bin/python -c "
from app.matcha.routes.employees import (
    router, pto_admin_router, leave_admin_router,
    _refresh_risk_assessment, EmployeeCreateRequest,
)
print('import surface ok')
"

# 2. OpenAPI diff vs baseline (MUST be empty — catches response_model / auth-dep / tags drift)
./venv/bin/python -c "
from app.main import app; import json
print(json.dumps(app.openapi(), indent=2, sort_keys=True))
" > /tmp/openapi_employees_step.json
diff /tmp/openapi_employees_baseline.json /tmp/openapi_employees_step.json

# 2b. Route-order diff vs baseline (MUST be empty — catches shadow-order regressions)
./venv/bin/python -c "
from app.main import app
for r in app.routes:
    methods = sorted(getattr(r, 'methods', []) or [])
    print(f\"{','.join(methods):10s} {r.path}\")
" > /tmp/routes_employees_step.txt
diff /tmp/routes_employees_baseline.txt /tmp/routes_employees_step.txt

# 3. Lazy-import resolution (mimics er_copilot + worker call sites)
./venv/bin/python -c "
def f():
    from app.matcha.routes.employees import _refresh_risk_assessment
    return _refresh_risk_assessment
print('lazy ok:', f().__name__)
"

# 4. Test subset
./venv/bin/python -m pytest tests/employees/ -q \
  --ignore=tests/employees/test_employee_invites_and_compliance.py \
  --ignore=tests/employees/test_internal_mobility_routes.py
```

**Invocation step per phase** (email-refactor lesson: `dir()` misses runtime `NameError`). Each phase also runs a TestClient call against one endpoint per submodule it touched, with `get_connection`, `get_current_user`, `require_admin_or_client`, `get_client_company_id` stubbed:

| Commit | Endpoint(s) to exercise |
|---|---|
| 2 (shim) | `GET /api/matcha/employees` |
| 3 (_shared) | `POST /api/matcha/employees` (`_sync_employee_location_for_compliance` + `_auto_send_invitation`); `POST /api/matcha/employees/{id}/oig-screen` |
| 4 (pto) | `GET /api/matcha/employees/pto/requests` |
| 5 (leave_admin) | `GET /api/matcha/employees/leave/requests`, `POST /api/matcha/employees/leave/requests/{id}/return-checkin` |
| 6 (oig) | `GET /api/matcha/employees/oig-summary` |
| 7 (incidents) | `GET /api/matcha/employees/incident-counts` |
| 8 (leave) | `POST /api/matcha/employees/{id}/leave/place` |
| 9 (credentials) | `GET /api/matcha/employees/{id}/credentials` |
| 10 (bulk_upload) | `GET /api/matcha/employees/bulk-upload/template`, `POST /api/matcha/employees/bulk-upload` (small CSV w/ reserved-domain emails) |
| 11 (invitations) | `POST /api/matcha/employees/{id}/invite`, `POST /api/matcha/employees/bulk-invite` |
| 12 (offboarding) | `POST /api/matcha/employees/{id}/offboard`, `GET /api/matcha/employees/{id}/offboard`, `PATCH /api/matcha/employees/{id}/offboard/tasks/{task_id}` |
| 13 (onboarding) | `GET /api/matcha/employees/{id}/onboarding`, `POST /api/matcha/employees/{id}/onboarding/assign-rtw/{leave_request_id}` (exercises lazy `assign_rtw_tasks`), `PUT /api/matcha/employees/onboarding-draft` (exercises PUT-shadow preservation) |
| 14 (crud final) | `GET /api/matcha/employees/onboarding-progress`, `GET /api/matcha/employees/departments`, `GET /api/matcha/employees/by-uid/{uid}` |

A 4xx response from stubbed DB is fine — gate is "no `NameError`/`ImportError`/`AttributeError`/5xx". OpenAPI diff is the structural gatekeeper.

## Pre-commit gate (every phase)

Before `git commit` for any phase: BOTH conditions must hold.

1. **Structural**: full OpenAPI JSON diff empty + route-order diff empty + import-surface check passes.
2. **Runtime**: TestClient hit on each endpoint touched in the phase returns non-5xx (status 200/4xx fine; `NameError`/`ImportError` = stop).

Email-refactor lesson: `dir()`/import-resolution checks silently passed for 9 commits while `html.escape` was crashing at runtime. Don't merge a phase whose runtime check is "I assume it works."

## Post-split (final commit or part of commit 13)

- Add `server/app/matcha/routes/employees/CLAUDE.md` mirroring `ir_incidents/CLAUDE.md` (layout table, package-router note, "when adding a new endpoint" recipe, `assign_rtw_tasks` lazy-import gotcha, route-shadowing note, test command).
- Update root `CLAUDE.md` Directory Structure entry: `employees.py` (5,425 lines) → `employees/` (package, split 2026-05-16).
- Update `server/app/matcha/routes/CLAUDE.md` table row + "Current strong candidates" list — strike `employees.py`, only `er_copilot.py` remains.
- Update `CLAUDE_CODE_PLAN.md`: mark item 7c done.

## Risk list

1. **Route shadowing of 1-segment static routes.** FastAPI matches `/{employee_id}` first; UUID-coerce fails → 422 with no fallthrough. Affected today (because the source registers them AFTER `/{employee_id}` at 1317/1383/1686):
   - `GET /incident-counts` (shadowed by `GET /{employee_id}` at 1317)
   - `GET /oig-summary` (shadowed by `GET /{employee_id}` at 1317)
   - `GET /onboarding-draft` (shadowed by `GET /{employee_id}` at 1317)
   - `PUT /onboarding-draft` (shadowed by `PUT /{employee_id}` at 1383)
   - `DELETE /onboarding-draft` (shadowed by `DELETE /{employee_id}` at 1686)

   POST routes (`/bulk-invite`, `/invite-all`, `/oig-batch-screen`) are NOT shadowed — crud's POST is on `""` (collection root), not `/{employee_id}`.

   Layout preserves status quo by `include_router`-ing submodules AFTER crud's catch-all, matching original source order. Phase 0's route-order baseline + per-phase diff catches accidental reordering.

2. **`_refresh_risk_assessment` import chain.** Lives in `_shared.py` after split, re-exported from package `__init__.py`. Both consumers (`er_copilot.py:91`, `workers/tasks/er_analysis.py:132`) do lazy imports — they hit `__init__.py` once and grab the re-export. Phase-2 lazy-import test covers this.

3. **`EmployeeCreateRequest` test consumer.** `tests/training/test_employee_create_supervisor.py:3` is in the pre-broken list per `server/CLAUDE.md`, but the symbol must still be importable. Re-exported from `__init__.py`.

4. **`assign_rtw_tasks` cross-submodule call.** After split, defined in `offboarding.py`, called from a route in `onboarding.py`. Use lazy import inside the onboarding function body to avoid module-level circularity. Phase-12 invocation step exercises this exact path.

5. **`spec_from_file_location` brittle tests** at `tests/employees/test_employee_invites_and_compliance.py:60`, `tests/employees/test_internal_mobility_routes.py`, `tests/er_copilot/test_er_copilot_risk_refresh.py:33,39`. These break when `employees.py` becomes a package. Pre-broken on `main`; do NOT try to fix as part of this work. Skip via `--ignore`.

6. **Empty-path routes restricted to `crud.py`.** Per IR pattern, only the package-router-owner may declare `@router.X("")`. No submodule may use empty paths.

7. **Mount-time tags.** `routes/__init__.py:44,46,48` applies `tags=["employees"|"pto-admin"|"leave-admin"]` at the mount, not per-route. Preserve: do NOT add `tags=...` to any submodule decorator.

8. **Trailing-slash trap** (from IR CLAUDE.md). FastAPI does NOT normalize `""` vs `"/"`. Preserve exact path strings — copy lines, don't retype.

9. **Pre-existing test failures.** Per `server/CLAUDE.md`, ignored test files listed above. Goal is "same set of pre-broken tests, plus all previously-passing tests still pass."

## Critical files

- `server/app/matcha/routes/employees.py` (source → becomes `employees/_legacy.py` → split)
- `server/app/matcha/routes/__init__.py` (consumer, 3-router import unchanged)
- `server/app/matcha/routes/ir_incidents/__init__.py` (template)
- `server/app/matcha/routes/ir_incidents/_shared.py` (template)
- `server/app/matcha/routes/ir_incidents/CLAUDE.md` (template for new `employees/CLAUDE.md`)
- `server/app/matcha/routes/CLAUDE.md` (zoo table update)
- `CLAUDE_CODE_PLAN.md` (mark 7c done)
- `CLAUDE.md` root (Directory Structure entry)

## What this plan deliberately does NOT do

- No SQL changes, no schema migrations, no new endpoints.
- No `response_model` changes, no auth-dep changes, no path/method changes.
- No attempt to fix pre-broken `spec_from_file_location` tests.
- No simultaneous extraction of `er_copilot.py` — separate work item.
- No frontend changes.
