# Dashboard Routes Package

Cross-feature dashboard aggregation. Split from a 2,096-line flat `dashboard.py` into per-domain submodules on 2026-07-26 (14 routes at that point, byte-identical route table). External import path `app.matcha.routes.dashboard` stable. Prefix `/dashboard` is applied at the parent mount in `routes/__init__.py` — **ungated**, no `require_feature` dependency, deliberately: this is where cross-tenant, non-add-on HR-ops data belongs.

**2026-07-28: gained `tasks.py`** (6 routes, 14 → 20) — the global manual-task board + auto-populated deadline feed, moved here from `routes/matcha_work/workspace.py`. It used to be gated behind `matcha_work` (an admin-granted add-on most tenants don't have) even though its content — overdue credentials, incidents, training, compliance deadlines — has nothing to do with the matcha-work AI chat product. See `tasks.py`'s module docstring.

Pydantic models already lived in `app/matcha/models/dashboard.py` before the split — keep them there, not in the route submodules (the one exception is noted below).

## Layout

| File | Concern | Endpoints |
|---|---|---|
| `__init__.py` | Fresh-aggregator `router` + 4 workspace re-exports | — |
| `stats.py` | `GET /stats` (Redis-cached roll-up) + `_format_action` | 1 |
| `risk_flags.py` | `/flags`, `/flags/analyze`, `/wage-gap/details`, `/wage-gap/export.csv` + all flag machinery | 4 |
| `notifications.py` | `GET /notifications` — client notification feed | 1 |
| `credentials.py` | `GET /credential-expirations` + `_classify_severity` | 1 |
| `upcoming.py` | `GET /upcoming` + `_UPCOMING_SOURCES` (13 source dicts) | 1 |
| `escalated_queries.py` | `/escalated-queries*` — list/get/resolve/dismiss/status + `EscalatedQueryDetail` | 5 |
| `sidebar_badges.py` | `GET /sidebar-badges` | 1 |
| `tasks.py` | Global (non-project) manual task board: `GET/POST /tasks`, `PATCH/DELETE /tasks/{task_id}`, `POST/DELETE /tasks/dismiss`. `/tasks/dismiss` registered before `/tasks/{task_id}` — the reverse order (as it was in `matcha_work/workspace.py`) shadows `DELETE /tasks/dismiss` behind the non-UUID-converter `{task_id}` param | 6 |
| **Total** | | **20 routes** |

No `_shared.py`: the only cross-group helper was `_format_action`, whose sole caller is `get_dashboard_stats`, so it moved into `stats.py`. Don't add a `_shared.py` for a single-caller helper.

## Package router pattern

Fresh-aggregator variant (the `matcha_work/` style, see `routes/CLAUDE.md`): `__init__.py` owns a bare `router = APIRouter()` and `include_router`s each submodule in original flat-file order, which keeps OpenAPI ordering and route resolution identical to pre-split. No submodule declares an empty-path route.

## External contract — the module-level re-exports

`__init__.py` re-exports `_UPCOMING_SOURCES` / `_apply_company_filter` / `_severity_from_days` (from `.upcoming`) and `UpcomingItem` (from `app.matcha.models.dashboard`) with `# noqa: F401` — lint autofix would otherwise delete them. This used to back a lazy cross-package import from `routes/matcha_work/workspace.py`; that import was removed 2026-07-28 when `tasks.py` (which needs the same four symbols) moved into this package and could import `.upcoming` directly. The re-exports stayed in case anything else imports them by package name. The smoke test asserts the import still resolves and that `_apply_company_filter("x {company_filter}", None) == "x TRUE"`.

## Route order sensitivity

`escalated_queries.py` registers the static `GET /escalated-queries` **before** `GET /escalated-queries/{query_id}`. Preserve in-file function order or the collection path gets swallowed by the UUID path.

## `risk_flags.py` — nothing in it is dead

An earlier read of the flat file called `_classify_location` / `_write_flags_to_db` / `rebuild_flags_deterministic` unused. They're alive **internally**: `get_dashboard_flags` → `rebuild_flags_deterministic` → `_write_flags_to_db` → `_classify_location`, and `analyze_risk_flags` → `_write_flags_to_db`. They are module-private to this submodule — moved, not deleted, and deliberately **not** re-exported from `__init__.py`.

## Lazy imports

All in-body imports stayed lazy and became **absolute** (they were relative to the `routes` package in the flat file):

- `stats.py` — `app.core.services.compliance_service.get_employee_impact_for_location`, `app.matcha.services.workforce.wage_benchmark_service.compute_company_wage_gap`, `…flight_risk_service.compute_company_summary`
- `risk_flags.py` — `app.config.get_settings`, `…wage_benchmark_service.compute_employee_wage_gaps`, `app.core.services.compliance_service.get_employee_impact_for_location`
- `escalated_queries.py` — `matcha_work_document as _doc_svc`, `_row_to_message`, `thread_manager`

The `dashboard ↔ matcha_work_document` edge is **bidirectional** (`resolve_escalated_query` calls `_doc_svc.add_message`; that package's PDF path imports back into routes). Both directions must stay lazy.

## Route-layer model

`EscalatedQueryDetail(EscalatedQueryItem)` stays in `escalated_queries.py`, not in `models/dashboard.py` — it's a route-layer subclass of a shared model. Everything else comes from `app.matcha.models.dashboard`.

## Caching

`stats.py` uses the `redis_cache` helpers (`get_redis_cache`, `cache_get`, `cache_set`, `dashboard_stats_key`), keyed on `company_id`. Split-invariant — no invalidation change was needed.

## Tests

`tests/dashboard/test_router_split_smoke.py` (2 tests, no DB):
- 14-entry route-table snapshot (`(path, methods)` sorted).
- The workspace-contract import + `_apply_company_filter` sanity check.

```bash
cd server && ./venv/bin/python -m pytest tests/dashboard/ -q
```

## Adding an endpoint

1. Pick the submodule by domain; each already has `router = APIRouter()`.
2. Auth: `Depends(require_admin_or_client)`, then `await get_client_company_id(current_user)` — scope every query by that, never a path-supplied company id.
3. Response models go in `app/matcha/models/dashboard.py`.
4. New submodule ⇒ `from .<name> import router as _<n>_router; router.include_router(_<n>_router)` in `__init__.py`, and extend the smoke-test snapshot.
