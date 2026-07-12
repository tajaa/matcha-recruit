# Matcha Work Routes Package

Backend routes for Matcha Work (collaborative AI workspace — projects, threads, tasks, recruiting, AI turns). Package was split from an 11,572-line flat `matcha_work.py` into per-domain submodules on 2026-07-03. URL surface unchanged at the split (204 routes; 203 since the 2026-07-09 deletion of the dead non-streaming `POST /threads/{id}/messages` — see `messaging.py`'s module docstring); external import path `app.matcha.routes.matcha_work` stable.

## Layout

| File | Concern | Routes |
|---|---|---|
| `__init__.py` | Routing assembly + 3-router re-exports (fresh aggregator, not crud-owned) | — |
| `_shared.py` | Cross-cutting helpers (`_sse_data`, project-access guards, file-url resolvers, thread-message serializer) + shared constants | — |
| `presence.py` | Heartbeat + online-users (**owns `presence_router`**) | 2 |
| `ai_turn.py` | **No routes.** Field validation, phantom-claim scrubbing, offer-draft detection, onboarding provisioning, slide/blog/recruiting context injection, `_apply_ai_updates_and_operations` (the AI-response-to-DB-write step) | — |
| `pdf_export.py` | Markdown→PDF rendering (WeasyPrint) + project/message/thread-project export endpoints | 3 |
| `thread_uploads.py` | Thread images/files/resume-batch/inventory uploads + batch interview send/sync | 7 |
| `projects.py` | Project CRUD/pin/archive/bundle, discipline lifecycle (**owns `public_router`** for the signature webhook), blog, project files/folders/links, project completion | 30 + 1 public |
| `sections.py` | Project sections (CRUD/reorder/revision/email/comments), AI diagram editing, legacy thread-scoped project endpoints. **Holds 2 order-sensitive route pairs** (see below) | 20 |
| `tasks.py` | Project kanban tasks + subtasks, pipeline-mode, ticket drafts, task history/rounds/activity/files, research tasks | 37 |
| `workspace.py` | Cross-project home surface: open-tasks/recent-activity feeds, per-user Gmail email agent, entitlements/usage, global (non-project) manual task board. **Holds 1 order-sensitive route pair** (see below) | 17 |
| `elements.py` | Project elements (context-repo bindings) CRUD + repo-snapshot sync + files/folders/notes | 12 |
| `github.py` | Commit scan/suggestions, GitHub connection/sync/scan-commits (**owns `public_router`** for the push webhook) | 10 + 1 public |
| `collaboration.py` | Discussion channel, project collaborators, invites, admin-user search, thread collaborators | 13 |
| `recruiting.py` | Recruiting-client CRUD, project chats, job posting, candidate shortlist/dismiss/reject, resume upload/analyze, interviews | 19 |
| `tutor.py` | Language tutor voice sessions (Gemini Live) + EN/ES/FR utterance-check prompts | 3 |
| `messaging.py` | The core AI-turn surface: `send_message_stream` (the biggest handler; its non-streaming twin was deleted 2026-07-09 — quota-bypass/wrong-tenant/crash-after-billing drift, zero callers) + RAG-context/compliance-gap-detection/thread-file-attachment-meta helpers. Mode dispatch is registry-driven: a generic loop over `services/matcha_work_modes.THREAD_MODES` injects each active mode's context (node, benefits, legal, risk, training); compliance + payer are `custom_dispatch=True` and keep bespoke blocks (reasoning-chain statuses + conditional RAG; payer prompt-swap path) | 1 |
| `threads.py` | Remainder: create/logo/handbook-upload, list/get, versions/revert/finalize/save-draft, PDF/proxy, archive/unarchive, review-requests + signatures + presentation, title/pin, mode toggles — the registry-driven `POST /threads/{id}/modes/{mode_key}` + 3 legacy aliases (`/node-mode`, `/compliance-mode`, `/payer-mode`) (**owns `public_router`** for public review routes) | 25 + 2 public |
| **Total** | | **204 routes** |

## Three routers

The package exposes **three** routers from `__init__.py`:

1. `router` — mounted at `/matcha-work`, feature-gated with `require_feature("matcha_work")` at construction (the constructor gate, not just the mount — see Gate note below).
2. `public_router` — mounted at `/matcha-work/public`, no gate. Aggregates public sub-routers from `projects.py` (signature webhook), `github.py` (push webhook), and `threads.py` (public review GET/POST).
3. `presence_router` — mounted at `/matcha-work/presence`, no gate. Owned entirely by `presence.py`.

**Unlike `ir_incidents/`/`employees/`, `router` is a fresh `APIRouter()`** in `__init__.py`, not a re-export of one submodule's router. Verified during the split: no submodule declares an empty-path route (`@router.get("")`), so there's no "prefix and path both empty" hazard to avoid — the crud-owns-router workaround those packages use isn't needed here.

### Gate note

`router`'s `require_feature("matcha_work")` dependency is declared in the `APIRouter(dependencies=[...])` constructor in `__init__.py` — this mirrors what the flat file did (the same gate was ALSO applied at the mount in `routes/__init__.py`, so it's effectively double-applied, same as before the split). Submodule routers themselves are all bare `APIRouter()` with no gate — the gate lives only on the package-level aggregator.

## Order-sensitive routes (Starlette matches in registration order)

Three same-method overlapping route pairs exist. Each pair lives entirely within **one** submodule, in its original relative order — moving one half without the other would break matching:

1. `PUT /projects/{project_id}/sections/reorder` **before** `PUT /projects/{project_id}/sections/{section_id}` — both in `sections.py`.
2. `PUT /threads/{thread_id}/project/sections/reorder` **before** `PUT /threads/{thread_id}/project/sections/{section_id}` — both in `sections.py` (the legacy thread-scoped project group).
3. `DELETE /tasks/{task_id}` **before** `DELETE /tasks/dismiss` — both in `workspace.py`. **`task_id` uses a plain (non-UUID-converter) path param, so `DELETE /tasks/dismiss` is already shadowed today** — any `/tasks/dismiss` DELETE matches `/tasks/{task_id}` first and 422s on UUID coercion. This is pre-existing behavior from before the split; not fixed here.

**Don't reorder within a submodule** if it changes the relative position of either pair. Include order **between** submodules in `__init__.py` is free — no other route shares both method and an overlapping path pattern with anything in a different submodule (verified exhaustively against the full 204-route dump at every phase of the split).

## Adding a new endpoint

1. Find the right submodule by domain. If genuinely new, create a new submodule: `router = APIRouter()` at module scope, add `from .<name> import router as _<name>_router; router.include_router(_<name>_router)` to `__init__.py`.
2. Helpers come from `from ._shared import ...` or the owning submodule (e.g. `_render_project_pdf` from `pdf_export.py`, `_apply_ai_updates_and_operations` from `ai_turn.py`). Don't redefine them locally.
3. Tenant isolation: filter by `company_id = await get_client_company_id(current_user)` and verify ownership (`_verify_project_access` for project-scoped resources) before reading/writing.
4. `tags`/`prefix`/feature-gate live at the mount in `routes/__init__.py`, not on submodule decorators.

## Cross-submodule imports (intra-package dependency graph, acyclic)

- `_shared` ← everything.
- `ai_turn` ← `threads.py`, `messaging.py` (for `_apply_ai_updates_and_operations` + slide/blog/recruiting context helpers).
- `pdf_export._render_project_pdf` ← `projects.py` (discipline signature flow), `sections.py` (section email).
- `elements._list_project_elements` ← `projects.py` (bundle endpoint), `github.py` (repo-snapshot stats).
- `projects.{ALLOWED_PROJECT_FILE_EXTENSIONS,PROJECT_FILE_MAX_BYTES}` ← `threads.py` (thread-scoped project-image upload).

All of the above are plain module-level imports (no cycles — verified by import order in `__init__.py`). If a future addition creates a cycle, use a **lazy in-function import** (the repo convention — see e.g. `projects.py`'s `from app.matcha.services import project_service as proj_svc` inside route bodies).

## External symbols re-exported by `__init__.py`

- `router`, `public_router`, `presence_router` — consumed by `routes/__init__.py:34` (the only external importer; mounts unchanged from before the split).

No other symbol needs package-level re-export — tests that previously imported module-level names directly from the package (`_render_inline_md`, `UTTERANCE_CHECK_PROMPT_EN/ES`) were repointed at the real owning submodule during the split (`pdf_export.py`, `tutor.py` respectively) rather than kept as package re-exports.

## Test patch-target gotcha

Two tests monkeypatch/mock functions the flat module exposed at its own top level. With the package split, `mw = import app.matcha.routes.matcha_work` no longer IS the module holding those functions — patching `mw.foo` only rebinds the package's own attribute, not the submodule's internal reference. Both were repointed at the real submodule during the split:

- `tests/matcha_work/test_blog_pdf_export.py` — imports/patches via `from app.matcha.routes.matcha_work import pdf_export as mw` (was `import ... matcha_work as mw`).
- `tests/matcha_work/test_journal_isolation.py` — imports via `from app.matcha.routes.matcha_work import workspace as matcha_work` (was `from app.matcha.routes import matcha_work`).

If you move a function to a different submodule, check whether any test patches it by package-level name and repoint the test's import, not just add a re-export.

## Imports convention

- Absolute `from app.X import …` for app-level imports (matches the rest of the router zoo — converted from relative in phase 1 of the split).
- Absolute `from app.matcha.routes.matcha_work.<submodule> import …` for intra-package imports (this package uses absolute intra-package imports throughout, not `from .<submodule> import`, to keep the "which submodule owns this" grep-able).
- Lazy imports inside function bodies are the norm for service-layer calls (`project_service`, `project_task_service`, etc.) — this pattern predates the split and was preserved verbatim during extraction.

## Split-history gotcha: single-dot relative imports

Two lazy in-function imports (`from .dashboard import ...` in `threads.py`'s global-tasks helper, `from .thread_ws import thread_manager` in two AI-turn call sites) were valid single-dot relative imports when the file was flat (`app/matcha/routes/matcha_work.py`, sibling of `dashboard.py`/`thread_ws.py` in `app.matcha.routes`). Moving the file into the `matcha_work/` subpackage silently changed what a single dot resolves to. Fixed to absolute (`app.matcha.routes.dashboard`, `app.matcha.routes.thread_ws`) during the split. **If you see a bare `from .X import` anywhere in this package reaching for a module outside `matcha_work/`, it's wrong** — this package's own submodules are the only valid single-dot targets, and this package uses absolute imports for those anyway (see above).

## Tests

Full suite: `cd server && ./venv/bin/python -m pytest tests/matcha_work/ -q` — expect 12 failed / 126 passed / 8 skipped. The 12 failures are pre-existing (unrelated to the split — `TestRenderProjectPdf` PDF-rendering assertions, `test_non_image_requests_normal_flow`, `test_project_task_toggle` response-shape checks). Verified identical failure set at every phase of the split.

`pytest tests/` (the whole server suite) hits unrelated pre-existing collection errors in other packages (documented in `employees/CLAUDE.md`) plus a GUSTO-OAuth-env-var collection-order fragility — `test_language_tutor.py`'s module-level prompt-constant import triggers `app.matcha.routes.provisioning`'s startup check, which only succeeds if an earlier-collected file (`test_journal_isolation.py`, alphabetically first) has already called `os.environ.setdefault("GUSTO_OAUTH_*", ...)`. Pre-existing, not introduced by this split — scope `pytest` to `tests/matcha_work/` (or set the GUSTO env vars / load `.env` first) to avoid it.
