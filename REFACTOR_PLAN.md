# Split three server/app/matcha monoliths into packages

> Working plan doc — mirrors `/Users/finch/.claude/plans/functional-finding-cat.md`. Update the Progress section as work lands.

## Progress

- [x] **Target 1: `routes/employee_portal.py`** — DONE, verified
  - All 10 submodules + `_shared.py` + `__init__.py` written
  - `_legacy.py` deleted (fully extracted; not renamed to `benefits.py` — deleted instead since nothing more to move)
  - Route-table snapshot: 33/33 routes, byte-identical to pre-split
  - Full app boot check: 1957 routes, imports clean
  - `py_compile` clean on all submodules
- [x] **Target 2: `routes/dashboard.py`** — DONE, verified
  - All 7 submodules + `__init__.py` written; `_legacy.py` deleted (fully extracted)
  - Route-table snapshot: 14/14 routes, byte-identical to pre-split
  - Workspace contract verified: `from app.matcha.routes.dashboard import _UPCOMING_SOURCES, _apply_company_filter, _severity_from_days, UpcomingItem` resolves; `_apply_company_filter` sanity-tested
  - Full app boot check: 1957 routes, imports clean
  - `py_compile` clean on all submodules
- [x] **Target 3: `services/matcha_work/matcha_work_document/__init__.py`** — DONE, verified
  - 11 new submodules written (_profile/context/threads/elements/modes/messages/versions/pdf/offer_letters/workbook/review_requests); `__init__.py` rewritten as pure facade (existing L6 leaf re-imports kept + new L7 block)
  - Attribute surface: all 39 externally-used attrs verified present via `hasattr`
  - Singleton identity verified: `doc_svc._company_profile_cache is _profile._company_profile_cache` and same for `invalidate_company_profile_cache`
  - Named imports verified (`add_message`/`apply_update` from offer_letters.py:736, `invalidate_company_profile_cache`, `build_matcha_work_thread_storage_prefix`)
  - All 17 consumer modules import-checked individually — clean
  - Full app boot: 1957 routes (unchanged), `py_compile` clean on all submodules
- [x] Smoke tests for all 3 splits — DONE
  - `tests/employee_portal/test_router_split_smoke.py` (3 tests), `tests/dashboard/test_router_split_smoke.py` (2 tests), `tests/matcha_work/test_doc_svc_facade.py` (2 tests) — all 7 pass
  - Broader regression check: `tests/matcha_work/ tests/employees/ tests/dashboard/ tests/employee_portal/` → 297 passed, 8 pre-existing failures (verified identical on unmodified `git stash` baseline — `test_blog_pdf_export.py` + `test_employees_google_workspace_onboarding.py`, unrelated to the split), 2 pre-broken collection errors per `server/CLAUDE.md`'s documented list

- [x] **Docs** — DONE (2026-07-26 review pass)
  - `routes/CLAUDE.md`: `employee_portal.py`/`dashboard.py` rows → package rows; split-router-package list + "Completed splits" line updated
  - New `employee_portal/CLAUDE.md` + `dashboard/CLAUDE.md` (mirroring `employees/CLAUDE.md`)
  - Root `CLAUDE.md`: directory-structure block + subtree-docs table
- [x] **Independent re-verification** (2026-07-26): per-route deep diff vs `HEAD` blobs — path/methods/endpoint-name/response-model/**dependency set**/params/status_code identical for all 47 routes, in the same registration order (only diff: response-model classes report their new module path). Per-function AST diff vs baseline: all 44 portal / 28 dashboard / 43 doc_svc defs present, no dupes, bodies byte-identical except relative→absolute lazy-import rewrites. Facade covers every externally-referenced attr (grep of `doc_svc.X` + named imports); dropped names are stdlib/private constants with no external reader.

## Summary — all 3 targets complete, verified, uncommitted

Nothing has been committed. `git status` shows: `employee_portal.py` and `dashboard.py` deleted (replaced by their packages), `matcha_work_document/__init__.py` modified, plus the new package directories and 3 new test files. Ready for review.

No commits made yet — all work is uncommitted on the current branch pending review.

## Context

User asked for the most obvious refactor targets in `server/app/matcha`. Survey found four monoliths; `routes/interviews.py` excluded (product not in use). Remaining three get split into packages following the proven repo precedent (`routes/ir_incidents/`, `routes/employees/`, `routes/er_copilot/` — flat file → package whose `__init__.py` exposes `router`). Goal: identical URL surface and attribute surface, zero call-site changes, history preserved via `git mv` rename detection.

**Verified**: `routes/__init__.py` needs **zero changes** — it imports `router` from `.employee_portal` (line 8, mounted `/v1/portal` line 103) and `.dashboard` (line 40, mounted `/dashboard` line 143); package `__init__.py` re-exports satisfy both. Target 2 is a service, never mounted.

**Router pattern**: neither routes file has an empty-path route, so use the fresh-aggregator variant (`router = APIRouter()` in `__init__.py` + `include_router` per submodule — the matcha_work variant per `routes/CLAUDE.md`), not the ir_incidents `crud.router`-is-the-package-router trick.

**Landing order** (increasing blast radius): employee_portal → dashboard → matcha_work_document.

**Note on commits**: per repo convention, commits are only made when the user explicitly asks. This split is being done as a series of file edits on the current branch; nothing is committed automatically.

---

## Target 1 — `routes/employee_portal.py` (1727 lines, 33 routes) → `routes/employee_portal/`

### File tree
```
routes/employee_portal/
├── __init__.py             aggregator + compat re-exports
├── _shared.py              5 Depends lists + CompleteTaskRequest + 2 orphan helpers
├── profile.py              3 routes (GET /me, PATCH /me, GET /me/tasks)          [lines 87-311]
├── pto.py                  3 routes                                              [314-524]
├── leave.py                5 routes + LEAVE_TYPES                                [527-648]
├── schedule.py              4 routes                                             [651-781]
├── documents.py            4 routes                                              [784-992]
├── policies.py             2 routes                                              [995-1074]
├── onboarding.py           2 routes + OnboardingTaskResponse/OnboardingProgress  [1077-1208]
├── priorities.py           2 routes                                              [1211-1353]
├── credential_documents.py 2 routes + upload constants + _cred_doc_response      [1356-1464]
└── benefits.py             6 routes + _serialize_my_election/_my_active_window   [1467-1727] ← final git mv of _legacy.py
```

### `_shared.py` (exact contents)
```python
from typing import Any, Optional
import json
from fastapi import Depends
from pydantic import BaseModel
from app.matcha.dependencies import require_feature

_pto_dep = [Depends(require_feature("time_off"))]
_policies_dep = [Depends(require_feature("policies"))]
_compliance_plus_dep = [Depends(require_feature("compliance"))]
_schedule_dep = [Depends(require_feature("employee_schedule"))]
_benefits_dep = [Depends(require_feature("benefits_admin"))]

class CompleteTaskRequest(BaseModel):   # used by BOTH onboarding.py and priorities.py
    notes: Optional[str] = None

def _parse_json_array(value: Any) -> list[str]: ...        # verbatim from 47-64
def _normalize_string_list(values: Optional[list[str]]) -> list[str]: ...  # verbatim from 67-83
```
- **Why dep lists live here once**: `require_feature(...)` (dependencies.py:421) is a factory returning a fresh closure per call; `dependency_overrides` keys on function-object identity. One closure per feature, defined once, imported everywhere.
- `_parse_json_array` / `_normalize_string_list` have **zero callers repo-wide** (leftovers of removed internal-mobility routes). Keep with `# NOTE: no callers as of 2026-07 — deletion candidate in follow-up`. Do not delete now.

### Key signatures per module (representative; full bodies move verbatim)
- profile: `@router.get("/me", response_model=PortalDashboard)` `async def get_portal_dashboard(employee: dict = Depends(require_employee_record))`; `@router.patch("/me", response_model=EmployeeResponse)` `async def update_my_profile(request: ProfileUpdateRequest, employee=...)`; `@router.get("/me/tasks", response_model=PortalTasks)`.
- pto: `get_pto_summary` / `submit_pto_request` / `cancel_pto_request(request_id: UUID, ...)`, all `dependencies=_pto_dep`.
- leave: 5 routes; `LEAVE_TYPES = {"fmla","state_pfml","parental","bereavement","jury_duty","medical","military","unpaid_loa"}` stays local. **ORDER-SENSITIVE**: `/me/leave/eligibility` (deps `_compliance_plus_dep`) must register before `/me/leave/{leave_id}` — preserve in-file function order.
- schedule: 4 routes, `dependencies=_schedule_dep`; `get_my_schedule(start: datetime = Query(...), end: datetime = Query(...), ...)`. In-body lazy imports `from .employee_schedule._shared import …` currently resolve against `routes` pkg — **must become** `from app.matcha.routes.employee_schedule._shared import …` (stay lazy).
- documents: 4 routes incl. `sign_document(document_id: UUID, request: SignDocumentRequest, http_request: Request, employee=...)`; imports `HandbookVersionContent` (app.core.models.handbook), `SignatureService` (app.core.services.policy_service).
- policies: 2 routes, `dependencies=_policies_dep`.
- onboarding: `get_my_onboarding_tasks` (response_model=OnboardingProgress), `complete_onboarding_task(task_id: UUID, request: CompleteTaskRequest, ...)` — `CompleteTaskRequest` from `._shared`.
- priorities: `get_my_priority_tasks`, `complete_priority_task(task_id: UUID, request: CompleteTaskRequest, background_tasks: BackgroundTasks, ...)`; lazy imports become absolute (`app.core.services.email.EmailService`, `app.core.services.notification_manager.get_notification_manager`).
- credential_documents: `portal_upload_credential_document(background_tasks: BackgroundTasks, file: UploadFile = File(...), document_type: str = Query(...), ...)`; keeps `_MAX_CRED_UPLOAD = 10*1024*1024`, `_ALLOWED_CRED_EXTS`, `_VALID_DOC_TYPES`, `_cred_doc_response(row) -> dict` local.
- benefits: 6 routes `dependencies=_benefits_dep`; keeps `_serialize_my_election(r) -> dict`, `async def _my_active_window(conn, org_id: UUID, employee_id: UUID) -> Optional[dict]`; imports `ElectionUpsert, LifeEventCreate` (app.matcha.models.benefits), `log_benefit_audit, resolve_active_window` (app.matcha.services.benefits.benefits_enrollment).

### `__init__.py` (exact)
```python
"""Employee Self-Service Portal router package.

Split from a 1,727-line flat employee_portal.py (33 routes; URL surface
unchanged). No submodule declares an empty-path route, so the package router
is a fresh aggregator (matcha_work variant — see routes/CLAUDE.md).
Prefix /v1/portal is applied at the parent mount in routes/__init__.py.
"""
from fastapi import APIRouter

# Back-compat attribute surface (tests reference employee_portal_routes.require_employee_record)
from app.matcha.dependencies import (  # noqa: F401
    require_employee, require_employee_record, require_feature,
)
from ._shared import (  # noqa: F401
    _pto_dep, _policies_dep, _compliance_plus_dep, _schedule_dep, _benefits_dep,
)

router = APIRouter()

# Include order mirrors original file order (keeps OpenAPI ordering identical).
from .profile import router as _profile_router; router.include_router(_profile_router)
from .pto import router as _pto_router; router.include_router(_pto_router)
from .leave import router as _leave_router; router.include_router(_leave_router)
from .schedule import router as _schedule_router; router.include_router(_schedule_router)
from .documents import router as _documents_router; router.include_router(_documents_router)
from .policies import router as _policies_router; router.include_router(_policies_router)
from .onboarding import router as _onboarding_router; router.include_router(_onboarding_router)
from .priorities import router as _priorities_router; router.include_router(_priorities_router)
from .credential_documents import router as _credential_documents_router; router.include_router(_credential_documents_router)
from .benefits import router as _benefits_router; router.include_router(_benefits_router)
```

### Sequence
1. Snapshot route table pre-split: `python -c "from app.matcha.routes.employee_portal import router; print(sorted((r.path, tuple(sorted(r.methods))) for r in router.routes))"` → scratchpad. **DONE** (33 routes, saved).
2. `git mv employee_portal.py employee_portal/_legacy.py` + `__init__.py` = `from ._legacy import router` + compat re-imports. **DONE**.
3. Create `_shared.py`; cut modules out of `_legacy.py` one at a time (absolute imports as we go). **IN PROGRESS**.
4. `git mv _legacy.py benefits.py` (last remaining section, rename detected); flip last include.
5. Snapshot-diff + full boot check.

### Edge cases
- `require_employee_record` is a plain function (not factory) — `dependency_overrides` identity preserved by import.
- No module-level side effects in this file.
- `tests/employees/test_internal_mobility_routes.py` is pre-broken (references nonexistent `_mobility_dep` + `routes/internal_mobility`); already fails at collection on main. Ignore, don't fix here.
- `update_my_profile` re-imports `json` in-body (line 184) — keep verbatim; `get_pending_tasks` uses `import json as _json` in-body.

---

## Target 2 — `services/matcha_work/matcha_work_document/__init__.py` (2057 lines, 39 fns) → full package split

Already a package; L6 pass extracted `_coerce.py`/`_storage.py`/`_email_html.py`/`_tokens.py` with `# noqa: F401` re-import blocks (lines 23-64). **Continue that precedent: new leaf files + facade re-imports, NO `_legacy.py`/git-mv step.** Per-function history stays reachable via `git log -L`.

### File tree (new modules)
```
matcha_work_document/
├── __init__.py          facade: pure re-imports, no logic
├── _coerce.py / _storage.py / _email_html.py / _tokens.py   (existing, untouched)
├── _profile.py          NEW  [69-250]   ← THE TTLCache singleton lives here
├── context.py           NEW  [253-283]
├── threads.py           NEW  [286-479]
├── elements.py          NEW  [482-611]
├── modes.py             NEW  [614-690]
├── messages.py          NEW  [693-748]
├── versions.py          NEW  [759-880]
├── pdf.py               NEW  [883-1233]
├── offer_letters.py     NEW  [1236-1567]
├── workbook.py          NEW  [1570-1711]
└── review_requests.py   NEW  [1714-2057]
```
Intra-package import DAG verified acyclic: `_profile ← threads`; `elements ← threads, modes, versions, offer_letters, workbook`; `messages ← offer_letters, review_requests`; `pdf ← offer_letters, workbook`; `versions ← review_requests`. Each module gets its own `logger = logging.getLogger(__name__)`.

### Signatures per module
**`_profile.py`** — singleton, exactly one instantiation ever:
```python
from cachetools import TTLCache
_PROFILE_CACHE_TTL = 300
_PROFILE_CACHE_MAX = 1000
_company_profile_cache: TTLCache = TTLCache(maxsize=_PROFILE_CACHE_MAX, ttl=_PROFILE_CACHE_TTL)

def invalidate_company_profile_cache(company_id: UUID) -> None
async def get_company_profile_for_ai(company_id: UUID) -> dict
```
The 6 external lazy importers of `invalidate_company_profile_cache` (core/routes/admin/invites.py:299, core/routes/admin/companies.py:597+612, matcha/routes/companies.py:260+333) bind the function object; it closes over `_profile`'s module globals, so facade re-export = same object, same cache. Also re-export `_company_profile_cache` from facade for attribute parity.

**`context.py`**: `get_thread_message_count(thread_id: UUID) -> int`, `get_context_summary(thread_id) -> tuple[Optional[str], Optional[int]]`, `save_context_summary(thread_id, summary: str, msg_count: int) -> None` (all async).

**`threads.py`**: `create_thread(company_id, user_id, title: str = "New Chat") -> dict`, `get_thread(thread_id, company_id, *, user_id: UUID | None = None) -> Optional[dict]`, `_thread_list_item_from_row(row: dict) -> dict`, `list_threads(company_id, status=None, limit=50, offset=0, *, user_id=None) -> list[dict]`. Imports `MODE_COLUMNS_SQL` from matcha_work_modes, `._coerce._parse_jsonb`, `._profile.get_company_profile_for_ai`, `.elements._upsert_element_from_thread_row`.

**`elements.py`**: `VALID_ELEMENT_TYPES = {"offer_letter", "review", "workbook"}`; `list_elements(...)`, `_upsert_element_from_thread_row(conn, thread_row)`, `_sync_element_for_thread(conn, thread_id)`, `sync_element_record(thread_id)`.

**`modes.py`**: `set_thread_pinned(thread_id, company_id, is_pinned: bool)`, `set_thread_mode(thread_id, company_id, mode_key: str, enabled: bool)` + 3 legacy setters (`set_thread_node_mode` / `_compliance_mode` / `_payer_mode`). Imports `MODE_COLUMNS_SQL, MODES_BY_KEY`, `.threads._thread_list_item_from_row`, `.elements._sync_element_for_thread`.

**`messages.py`**: `get_thread_messages(thread_id, limit: int | None = None) -> list[dict]`, `add_message(thread_id, role: str, content: str, version_created: Optional[int] = None, metadata: Optional[dict] = None) -> dict`.

**`versions.py`**: `apply_update(thread_id, updates: dict, diff_summary: Optional[str] = None) -> dict`, `revert_to_version(thread_id, target_version: int) -> dict`, `list_versions(thread_id, include_state: bool = False) -> list[dict]`.

**`pdf.py`**: `_get_cached_pdf_url(thread_id, version, is_draft, expected_prefix=None) -> Optional[str]`, `_cache_pdf_url(...)`, `generate_pdf(state: dict, thread_id, version, company_id, is_draft=True, logo_src=None) -> Optional[str]`, `_render_presentation_html(state) -> str`, `generate_presentation_pdf(...)`, `generate_cover_image(presentation_title, subtitle=None, *, company_id, thread_id) -> Optional[str]`. **Keep lazy in-body imports lazy**: `_generate_offer_letter_html` from routes/employee_lifecycle/offer_letters.py (genuine 2-way lazy relationship — offer_letters.py:736 imports this package back), `render_pdf`, `weasyprint.CSS`, `get_genai_client`.

**`offer_letters.py`**: `save_offer_letter_draft(thread_id, company_id) -> dict`, `send_offer_letter_draft(thread_id, company_id, recipient_emails: list[str], custom_message=None) -> dict`. Uses `._email_html`, `.pdf.generate_pdf`, `.messages.add_message`, `.elements._sync_element_for_thread`.

**`workbook.py`**: `generate_workbook_presentation(thread_id, company_id) -> dict`, `finalize_thread(thread_id, company_id) -> dict`.

**`review_requests.py`**: `_list_review_requests_for_thread(thread_id)`, `list_review_requests(thread_id, company_id)`, `sync_review_request_state(thread_id) -> dict`, `send_review_requests(thread_id, company_id, recipient_emails, custom_message=None) -> dict`, `get_public_review_request(token: str) -> Optional[dict]`, `submit_public_review_request(token: str, feedback: str, rating: Optional[int] = None) -> dict`. Uses `.versions.apply_update`, `.messages.add_message`.

### Facade `__init__.py`
Keep lines 1-64 (existing 4 leaf re-import blocks), delete all bodies, append:
```python
# Domain submodules (L7 split). External callers use doc_svc.X attribute
# access or named imports — every name below is load-bearing; do not prune.
from ._profile import (  # noqa: F401
    _company_profile_cache,   # singleton — lives in _profile; re-bound here for attr parity
    invalidate_company_profile_cache, get_company_profile_for_ai,
)
from .context import get_thread_message_count, get_context_summary, save_context_summary  # noqa: F401
from .threads import create_thread, get_thread, _thread_list_item_from_row, list_threads  # noqa: F401
from .elements import (  # noqa: F401
    VALID_ELEMENT_TYPES, list_elements, _upsert_element_from_thread_row,
    _sync_element_for_thread, sync_element_record,
)
from .modes import (  # noqa: F401
    set_thread_pinned, set_thread_mode, set_thread_node_mode,
    set_thread_compliance_mode, set_thread_payer_mode,
)
from .messages import get_thread_messages, add_message  # noqa: F401
from .versions import apply_update, revert_to_version, list_versions  # noqa: F401
from .pdf import (  # noqa: F401
    _get_cached_pdf_url, _cache_pdf_url, generate_pdf,
    _render_presentation_html, generate_presentation_pdf, generate_cover_image,
)
from .offer_letters import save_offer_letter_draft, send_offer_letter_draft  # noqa: F401
from .workbook import generate_workbook_presentation, finalize_thread  # noqa: F401
from .review_requests import (  # noqa: F401
    _list_review_requests_for_thread, list_review_requests, sync_review_request_state,
    send_review_requests, get_public_review_request, submit_public_review_request,
)
```
Then drop now-unused top-of-file imports from `__init__` (base64, asyncio, html, json, re, secrets, time, defaultdict, datetime, EmailService, get_storage, get_settings, MODE_COLUMNS_SQL, MODES_BY_KEY, TTLCache).

Attribute surface verified by repo-wide `doc_svc\.` grep — 36 distinct attributes, all covered by facade (list preserved in test below).

### Sequence
1. `_profile.py`, `context.py`, `messages.py`, `elements.py` (leaf-most) + facade block. Import-check.
2. `threads.py`, `modes.py`, `versions.py`.
3. `pdf.py`, `offer_letters.py`, `workbook.py`, `review_requests.py`; facade now pure imports; prune unused imports.

### Edge cases
- Singleton: never a second `TTLCache`; cache + its two functions never separated.
- `pdf.py` ↔ routes/offer_letters.py: both directions must stay lazy.
- Every facade import needs `# noqa: F401` or lint autofix deletes load-bearing re-exports.
- No route registration — zero URL-surface risk.

---

## Target 3 — `routes/dashboard.py` (2096 lines, 14 routes) → `routes/dashboard/`

Models already extracted to `models/dashboard.py` (flat file lines 27-57 = pure re-import block). **No `_shared.py` needed** — only cross-group helper is `_format_action`, whose sole caller is `get_dashboard_stats` (line 213) despite living at 1131; it moves into `stats.py`.

### File tree
```
routes/dashboard/
├── __init__.py            aggregator + workspace.py re-exports
├── stats.py               GET /stats + _format_action                     [86-406 + 1131-1146]
├── risk_flags.py          4 routes + all flag machinery                   [409-1128] ← final git mv of _legacy.py
├── notifications.py       GET /notifications                              [1149-1313]
├── credentials.py         GET /credential-expirations + _classify_severity [1316-1421]
├── upcoming.py            GET /upcoming + _UPCOMING_SOURCES machinery     [1424-1784]
├── escalated_queries.py   5 routes + EscalatedQueryDetail                 [1787-2021]
└── sidebar_badges.py      GET /sidebar-badges                             [2024-2096]
```

### Signatures per module
- **stats.py**: `@router.get("/stats", response_model=DashboardStats)` `async def get_dashboard_stats(current_user: CurrentUser = Depends(require_admin_or_client))`; `def _format_action(action: str, details: dict | None) -> str`. Redis helpers (`get_redis_cache, cache_get, cache_set, dashboard_stats_key`). Lazy in-body stay lazy, made absolute: `get_employee_impact_for_location`, `compute_company_wage_gap`, `compute_company_summary`.
- **risk_flags.py**: module constants `_SEVERITY_ORDER`, `_RISK_ANALYSIS_PROMPT`, `_LOC_PATTERN`; fns `_detect_risk_patterns(company_id) -> dict`, `_analyze_with_ai(patterns) -> list[dict] | None`, `_deterministic_flags_from_patterns`, `_wage_rollup_flag`, `_apply_wage_rollup`, `_classify_location(name, dept_names=None) -> str`, `_write_flags_to_db(company_id, raw_flags, is_ai, dept_names=None) -> int`, `rebuild_flags_deterministic(company_id) -> int`; routes `GET /wage-gap/details`, `GET /wage-gap/export.csv`, `GET /flags`, `POST /flags/analyze`. **Correction from earlier assessment**: `_classify_location`/`_write_flags_to_db`/`rebuild_flags_deterministic` are NOT dead — alive internally (`get_dashboard_flags:1033` → `rebuild_flags_deterministic` → `_write_flags_to_db` → `_classify_location`; `analyze_risk_flags:1127` → `_write_flags_to_db`). Move, don't delete, don't re-export.
- **notifications.py**: `_CLIENT_NOTIFICATION_LINK_MAP`, `_CLIENT_NOTIFICATION_SUBQUERIES`; `async def get_client_notifications(limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), current_user=...)`. asyncpg UndefinedTable/Column probes.
- **credentials.py**: `_CREDENTIAL_LABELS`; `def _classify_severity(expiry_date: date, today: date) -> str`; `GET /credential-expirations`.
- **upcoming.py**: `_UPCOMING_SOURCES: list[dict]` (13 source dicts verbatim); `def _severity_from_days(days: int, *, critical_threshold: int = 14) -> str`; `def _apply_company_filter(sql: str, company_id: UUID | None) -> str`; `async def get_upcoming_deadlines(days: int = Query(90, ge=1, le=365), ...)`. Imports `codified_gate_sql`.
- **escalated_queries.py**: `class EscalatedQueryDetail(EscalatedQueryItem)` stays here (route-layer subclass); 5 routes (`list`/`get`/`resolve`/`dismiss`/`status`). **ORDER-SENSITIVE**: static `/escalated-queries` before `/escalated-queries/{query_id}` — file order. Three lazy imports in `resolve_escalated_query` stay lazy (`matcha_work_document as _doc_svc`, `_row_to_message`, `thread_manager`).
- **sidebar_badges.py**: `async def get_sidebar_badges(since_ir: Optional[str] = Query(None), since_er: Optional[str] = Query(None), since_escalations: Optional[str] = Query(None), ...)`.

### `__init__.py` (exact)
```python
"""Dashboard router package — split from flat dashboard.py (14 routes, URL
surface unchanged). Fresh-aggregator variant: no submodule declares an
empty-path route. Prefix /dashboard applied at the parent mount."""
from fastapi import APIRouter

router = APIRouter()

from .stats import router as _stats_router; router.include_router(_stats_router)
from .risk_flags import router as _risk_flags_router; router.include_router(_risk_flags_router)
from .notifications import router as _notifications_router; router.include_router(_notifications_router)
from .credentials import router as _credentials_router; router.include_router(_credentials_router)
from .upcoming import router as _upcoming_router; router.include_router(_upcoming_router)
from .escalated_queries import router as _escalated_queries_router; router.include_router(_escalated_queries_router)
from .sidebar_badges import router as _sidebar_badges_router; router.include_router(_sidebar_badges_router)

# External re-exports — routes/matcha_work/workspace.py:468 lazily does
#   from app.matcha.routes.dashboard import _UPCOMING_SOURCES, _apply_company_filter,
#       _severity_from_days, UpcomingItem
from .upcoming import _UPCOMING_SOURCES, _apply_company_filter, _severity_from_days  # noqa: F401
from app.matcha.models.dashboard import UpcomingItem  # noqa: F401
```

### Sequence
1. Snapshot route table (same one-liner, module `app.matcha.routes.dashboard`).
2. Relative→absolute imports in flat file.
3. `git mv dashboard.py dashboard/_legacy.py` + `__init__.py` = `from ._legacy import router` + the 4-symbol workspace re-export block (pointing at `._legacy`). Boot-check proves workspace.py contract immediately.
4. Extract stats/notifications/credentials/upcoming/escalated_queries/sidebar_badges; flip re-exports to `.upcoming`; `_legacy` keeps only risk-flags block, included second.
5. `git mv _legacy.py risk_flags.py` (~700 lines, rename detected); update `__init__`. Snapshot-diff + boot.

### Edge cases
- Redis cache keys computed by `redis_cache` helpers keyed on company_id — split-invariant, no invalidation needed.
- `require_admin_or_client` / `get_client_company_id` plain functions — override identity preserved.
- workspace.py `/tasks` endpoint = only external consumer, lazy import so no cycle, but highest-blast-radius break if a re-export is missed (powers matcha-work task board).
- Bidirectional lazy edge dashboard↔matcha_work_document (dashboard.py:1951 `_doc_svc.add_message`) — stays lazy in escalated_queries.py.

---

## Test plan

Existing coverage: effectively none imports these modules (searched server/tests/). `test_internal_mobility_routes.py` pre-broken — ignore. `test_compliance_notifications.py` copies SQL inline, unaffected.

**New smoke tests** (fast, no DB):
1. `tests/employee_portal/test_router_split_smoke.py`
   - Route-table snapshot: `sorted((r.path, tuple(sorted(r.methods))) for r in router.routes)` == hardcoded 33-entry pre-split snapshot (catches path typos, lost routes, method drift, ""-vs-"/" in one assert).
   - Dep identity: `employee_portal._pto_dep is employee_portal._shared._pto_dep`; router has exactly 33 routes.
   - Compat attrs: `require_employee_record`, `require_employee` present.
2. `tests/dashboard/test_router_split_smoke.py`
   - 14-entry route-table snapshot.
   - Workspace contract: `from app.matcha.routes.dashboard import _UPCOMING_SOURCES, _apply_company_filter, _severity_from_days, UpcomingItem` succeeds; `_apply_company_filter("x {company_filter}", None) == "x TRUE"`.
3. `tests/matcha_work/test_doc_svc_facade.py`
   - `hasattr` for all 36 externally-used attributes: add_message, apply_update, build_matcha_work_thread_storage_prefix, check_token_quota, create_thread, ensure_matcha_work_thread_storage_scope, finalize_thread, generate_cover_image, generate_pdf, generate_presentation_pdf, generate_workbook_presentation, get_company_profile_for_ai, get_context_summary, get_public_review_request, get_thread, get_thread_message_count, get_thread_messages, get_token_usage_summary, list_elements, list_review_requests, list_threads, list_versions, log_token_usage_event, normalize_recipient_emails, revert_to_version, save_context_summary, save_offer_letter_draft, send_offer_letter_draft, send_review_requests, set_thread_compliance_mode, set_thread_mode, set_thread_node_mode, set_thread_payer_mode, set_thread_pinned, submit_public_review_request, sync_element_record — plus invalidate_company_profile_cache, _sync_element_for_thread, _company_profile_cache.
   - Singleton identity: `matcha_work_document._company_profile_cache is matcha_work_document._profile._company_profile_cache`; same for `invalidate_company_profile_cache`.

**Manual verification per commit**:
- Full boot import: `cd server && python -c "from app.main import app; print(len(app.routes))"`.
- OpenAPI diff before/after: `python -c "from app.main import app; import json; print(json.dumps(sorted(app.openapi()['paths'])))"` — byte-identical.
- `python -m pytest tests/matcha_work/ tests/employees/ -q` — same pass/fail counts as pre-recorded baseline (excluding the two pre-broken files).
- Dev-server spot checks: `GET /dashboard/stats`, `GET /dashboard/upcoming`, portal `GET /v1/portal/me`, matcha-work tasks endpoint (exercises workspace→dashboard re-export), admin company edit (exercises invalidate_company_profile_cache).

## Rollback

- No migrations/schema/data — rollback is deleting the new package dir + restoring the flat file (nothing is committed yet, so `git checkout` on the touched paths is enough while uncommitted).
- Missed re-export in prod = one-line forward fix in package `__init__.py`; smoke tests exist to make that class of miss impossible pre-merge.
- After each target lands: update `routes/CLAUDE.md` router-map rows; add per-package `CLAUDE.md` mirroring `employees/CLAUDE.md`.

## Critical files
- `server/app/matcha/routes/employee_portal.py` (split)
- `server/app/matcha/routes/dashboard.py` (split)
- `server/app/matcha/services/matcha_work/matcha_work_document/__init__.py` (split)
- `server/app/matcha/routes/__init__.py` (verify-only — zero edits)
- `server/app/matcha/routes/matcha_work/workspace.py` (external consumer contract, verify-only)
