# Employee Portal Routes Package

Employee-facing self-service portal. Split from a 1,727-line flat `employee_portal.py` into per-domain submodules on 2026-07-26. URL surface unchanged (33 routes, byte-identical route table); external import path `app.matcha.routes.employee_portal` stable. Prefix `/v1/portal` is applied at the parent mount in `routes/__init__.py`.

## Layout

| File | Concern | Endpoints |
|---|---|---|
| `__init__.py` | Fresh-aggregator `router` + back-compat re-exports | — |
| `_shared.py` | 5 feature-dep lists + `CompleteTaskRequest` | — |
| `profile.py` | `GET/PATCH /me`, `GET /me/tasks` | 3 |
| `pto.py` | `/me/pto*` — balance summary, request, cancel (`time_off`) | 3 |
| `leave.py` | `/me/leave*` + `LEAVE_TYPES` | 5 |
| `schedule.py` | `/me/schedule*` — published shifts + swap/drop/unavailability (`employee_schedule`) | 4 |
| `documents.py` | `/me/documents*` incl. handbook content + e-sign | 4 |
| `policies.py` | `/policies*` (`policies`) | 2 |
| `onboarding.py` | `/onboarding*` + `OnboardingTaskResponse` / `OnboardingProgress` | 2 |
| `priorities.py` | `/priorities*` — priority task list + completion | 2 |
| `credential_documents.py` | `/me/credential-documents` upload + list | 2 |
| `benefits.py` | `/me/benefits*` — elections + life events (`benefits_admin`) | 6 |
| **Total** | | **33 routes** |

## Package router pattern

Fresh-aggregator variant (the `matcha_work/` style, see `routes/CLAUDE.md`): `__init__.py` creates its own `router = APIRouter()` and `include_router`s each submodule. No submodule declares an empty-path route, so the `crud.router`-is-the-package-router trick used by `ir_incidents/` / `employees/` is not needed here.

**Include order mirrors the original flat-file order** — it keeps OpenAPI ordering and route-resolution order identical to pre-split. Don't reorder.

## Feature-dependency lists live in `_shared.py` — exactly once

`require_feature(...)` (`matcha/dependencies.py`) is a **factory** returning a fresh closure per call, and `app.dependency_overrides` keys on function-object identity. Re-creating `[Depends(require_feature("time_off"))]` in a second module would create a distinct closure for the same flag, so a test override would silently miss one of them.

Therefore: import `_pto_dep` / `_policies_dep` / `_compliance_plus_dep` / `_schedule_dep` / `_benefits_dep` from `._shared`; never build a `Depends(require_feature(...))` list inside a submodule.

## Route order sensitivity

`leave.py` registers `GET /me/leave/eligibility` **before** `GET /me/leave/{leave_id}`. Reversing them makes the literal `eligibility` land on the `{leave_id}` UUID path and 422. Preserve in-file function order; note `/eligibility` also carries the extra `_compliance_plus_dep` gate.

## Cross-package lazy imports

`schedule.py` reuses the scheduling package's helpers (`INACTIVE_EMPLOYMENT_STATUSES`, `REQUEST_SELECT`, `fetch_shifts`, `log_audit`, `serialize_request`). These stay **lazy, in-body**, and are now **absolute**:

```python
from app.matcha.routes.employee_schedule._shared import fetch_shifts
```

They were relative (`from .employee_schedule._shared import …`) in the flat file, where `.` was the `routes` package; inside this package that would resolve to a nonexistent `employee_portal.employee_schedule`. Same rewrite applied to every other in-body import (`app.core.services.email`, `app.core.services.notification_manager`, `app.core.services.storage`, `app.core.services.credential_extraction`, `app.core.services.handbook_service`, `app.matcha.services.leave.*`).

## Orphan helpers (do not delete yet)

`_parse_json_array` and `_normalize_string_list` in `_shared.py` had **zero callers repo-wide** — leftovers of removed internal-mobility routes. Kept verbatim through the split so it stayed a pure move; **deleted 2026-07-27** (refactor round 2, stage 5).

## Back-compat attribute surface

`__init__.py` re-exports `require_employee`, `require_employee_record`, `require_feature`, and the five dep lists because tests do `employee_portal_routes.require_employee_record` / `employee_portal_routes._pto_dep[0].dependency`. `require_employee_record` is a plain function (not a factory), so importing it preserves `dependency_overrides` identity.

## Tests

`tests/employee_portal/test_router_split_smoke.py` (3 tests, no DB):
- 33-entry route-table snapshot (`(path, methods)` sorted) — catches lost routes, path typos, method drift, `""`-vs-`"/"`.
- Dep identity: `employee_portal._pto_dep is employee_portal._shared._pto_dep`.
- Compat attrs present.

```bash
cd server && ./venv/bin/python -m pytest tests/employee_portal/ -q
```

`tests/employees/test_internal_mobility_routes.py` imports this module but is **pre-broken on `main`** (references a nonexistent `_mobility_dep` and a removed `routes/internal_mobility`); it also monkeypatches a package-level `get_connection`, which the split makes per-submodule. Skip via `--ignore`, don't repair as part of unrelated work.

## Adding an endpoint

1. Pick the submodule by domain; each already has `router = APIRouter()`.
2. Feature gate: add `dependencies=_<flag>_dep` from `._shared` (or add a new list there if the flag is new).
3. Tenant isolation: derive the employee from `Depends(require_employee_record)`; scope every query by `employee["org_id"]` — never trust a client-supplied id.
4. New submodule ⇒ add `from .<name> import router as _<n>_router; router.include_router(_<n>_router)` in `__init__.py`, and extend the smoke-test snapshot.
