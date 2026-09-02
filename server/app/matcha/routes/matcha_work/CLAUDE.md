# Matcha Work Routes Package

Backend routes for Matcha Work (collaborative AI workspace — projects, threads, tasks, recruiting, AI turns). Package was split from an 11,572-line flat `matcha_work.py` into per-domain submodules on 2026-07-03. URL surface unchanged at the split; external import path `app.matcha.routes.matcha_work` stable.

## Schedule assistant routing invariant (2026-08-21)

`messaging.py` is also the scoped transport for `surface='schedule_assistant'`:
it admits the session owner through the schedule-session authorization path and
passes the resolved location/week context to Huume. The generic Work capability
resolver is intentionally not used for this surface; location authorization is
rechecked by `schedule_assistant_session._assert_manager_location` and schedule
writes recheck their domain relationships.

`matcha_work_document.get_thread()` hides schedule surfaces by default. The
streaming route opts in only to load the session thread, and still requires the
session owner; generic thread reads, lists, and recent activity must not expose
schedule state or staged actions. The old `/employee-schedule/chat` parser is no
longer mounted; voice transcription lives under `/employee-schedule/assistant`.

**Route count (recounted 2026-07-19, from source; +2 for `huume.py`'s plan approve/execute routes added since):** **204** gated routes on `router` + **4** on `public_router` = 208 endpoints. Reproduce with:

```bash
cd server && grep -c "^@router\."        app/matcha/routes/matcha_work/*.py   # per file
cd server && grep -h "^@router\." app/matcha/routes/matcha_work/*.py | wc -l  # 202
cd server && grep -h "^@public_router\." app/matcha/routes/matcha_work/*.py | wc -l  # 4
```

The "204 routes / 203 after the 2026-07-09 deletion of the dead non-streaming `POST /threads/{id}/messages`" figure this doc previously carried was **wrong, and was wrong before the 2026-07-19 `tasks.py` split** — the old `tasks.py | 37` row was an undercount of the same era, so the aggregate and the rows were never reconcilable. Nothing was removed to get from 203 to 202; the counts here are measured, not carried forward. The `messaging.py` deletion is real (see its module docstring) — only the arithmetic around it was bad. The **Routes** column below counts `@router.` decorators only; `public_router` routes are called out separately as "+ N public".

## Layout

| File | Concern | Routes |
|---|---|---|
| `__init__.py` | Routing assembly + 3-router re-exports (fresh aggregator, not crud-owned) | — |
| `_shared.py` | Cross-cutting helpers: project-access guards, file-url resolvers, upload constants. The pure shaping helpers (`_sse_data`, `_json_object`, `_row_to_message`, `THREAD_FILE_TEXT_CAP`) moved to `services/matcha_work/message_shapes.py` in the stage-5 audit — they carry no HTTP coupling, and keeping them here forced `turn_pipeline.py` into a module-level services→routes import. Re-exported here, so `from ._shared import _sse_data` is unchanged | — |
| `presence.py` | Heartbeat + online-users (**owns `presence_router`**) | 2 |
| ~~`ai_turn.py`~~ | **Moved to `services/matcha_work/ai_apply.py`** (refactor round 2, stage 5) — it always had zero routes. Field validation, phantom-claim scrubbing, offer-draft detection, onboarding provisioning, slide/blog/recruiting context injection, `_apply_ai_updates_and_operations` (the AI-response-to-DB-write step). Consumed by `messaging.py` and `threads.py` | — |
| `pdf_export.py` | Markdown→PDF rendering (WeasyPrint) + project/message/thread-project export endpoints | 3 |
| `thread_uploads.py` | Thread images/files/resume-batch/inventory uploads + batch interview send/sync | 7 |
| `projects.py` | Project CRUD/pin/archive/bundle, discipline lifecycle (**owns `public_router`** for the signature webhook), blog, project files/folders/links, project completion | 30 + 1 public |
| `sections.py` | Project sections (CRUD/reorder/revision/email/comments), AI diagram editing, legacy thread-scoped project endpoints. **Holds 2 order-sensitive route pairs** (see below) | 20 |
| `tasks.py` | Project kanban tasks + subtasks, pipeline-mode, done-count, task CRUD/reject/approve/ai-draft, review rounds, task summarize. **Ticket drafts, history/activity feeds, task attachments and research tasks all moved out on 2026-07-19** — see the four rows below | 15 |
| `project_agent_runs.py` | Espresso's durable board-launched repo-agent task drafts: idempotent enqueue + caller-owned status polling. Three invariants: `request_key` idempotency is scoped to `(project_id, requested_by)` (matching both the advisory lock and the unique index — a global lookup leaks another tenant's `run_id`); enqueue is `_can_edit_project`-gated because a run spends the company token budget; the status GET authorizes off its own `project_id`+`requested_by` filter rather than re-running `_verify_project_access` on a 2s poll. The agent/worker implementation lives in `services/matcha_work/project_agent/` + `workers/tasks/project_agent.py` | 2 |
| `ticket_drafts.py` | Ticket drafts — repo-grounded chat that promotes into a kanban task (split from `tasks.py` 2026-07-19) | 9 |
| `task_history.py` | Task history timeline, weekly board replay, project activity feed, and AutoPR additional-context reconsideration (+ `_serialize_history_row` / `_serialize_activity_row`) | 5 |
| `task_files.py` | Attachments scoped to one kanban task (ownership via `_shared._verify_task_belongs_to_project`) | 3 |
| `research_tasks.py` | Research tasks — HTTP shape + the 3 SSE streams. **Persistence lives in `services/research_task_service.py`**; storage is a list under the `research_tasks` key of the `mw_projects.project_data` JSONB blob (no table, no migration) — response shapes are consumed directly by `client/src/work/api/matchaWork/research.ts`, so they are byte-frozen | 9 |
| `workspace.py` | Cross-project home surface: open-tasks/recent-activity feeds, per-user Gmail email agent, entitlements/usage. The global (non-project) manual task board moved to `routes/dashboard/tasks.py` (2026-07-28) — see that package's CLAUDE.md — so this no longer holds an order-sensitive route pair | 11 |
| `elements.py` | Project elements (context-repo bindings) CRUD + repo-snapshot sync + files/folders/notes | 12 |
| `github.py` | Commit scan/suggestions, GitHub connection/sync/scan-commits (**owns `public_router`** for the push webhook) | 10 + 1 public |
| `collaboration.py` | Discussion channel, project collaborators, invites, admin-user search, thread collaborators | 13 |
| `recruiting.py` | Recruiting-client CRUD, project chats, job posting, candidate shortlist/dismiss/reject, resume upload/analyze, interviews | 19 |
| `tutor.py` | Language tutor voice sessions (Gemini Live) + EN/ES/FR utterance-check prompts | 3 |
| `tutor_sessions.py` | Standalone `/tutor/*` session create + admin metrics (list/detail/delete, aggregate, progress, comparison, vocabulary) — lifted out of `routes/interviews.py` 2026-07-27. **Exported but NOT included** by this package's `__init__.py`: `routes/__init__.py` mounts `tutor_sessions_router` itself, unprefixed and ungated, so the iOS MatchaTutor URL surface is unchanged. Do not `include_router` it here | 8 (mounted elsewhere) |
| `messaging.py` | Just the HTTP layer now (~220 ln): `send_message_stream` wires a `TurnContext` and calls into `services/matcha_work/turn_pipeline.py`'s stages. Its non-streaming twin was deleted 2026-07-09 — quota-bypass/wrong-tenant/crash-after-billing drift, zero callers. The pipeline itself (`TurnContext` + `_run_quota_gate` → `_prepare_attachments` → `_run_hard_stop_gates` → `_run_huume_dispatch` → `_inject_mode_contexts` → `_generate_turn` → `_audit_and_persist`, plus RAG-context/compliance-gap-detection/thread-file-attachment-meta helpers) moved to `services/matcha_work/turn_pipeline.py` (refactor round 2, stage 5 — it had zero routes of its own). Mode dispatch is registry-driven: a generic loop over `services/matcha_work_modes.THREAD_MODES` injects each active mode's context (node, benefits, legal, risk, training); compliance + payer are `custom_dispatch=True` and keep bespoke blocks (reasoning-chain statuses + conditional RAG; payer prompt-swap path) | 1 |
| `threads.py` | Remainder: create/logo/handbook-upload (a thin shell — the audit itself is `services/matcha_work/matcha_work_handbook_upload.run_handbook_upload`, moved out in refactor round 2 stage 5 along with ~450 lines of comments orphaned by the 2026-07-03 split), list/get, versions/revert/finalize/save-draft, PDF/proxy, archive/unarchive, review-requests + signatures + presentation, title/pin, mode toggles — the registry-driven `POST /threads/{id}/modes/{mode_key}` + 3 legacy aliases (`/node-mode`, `/compliance-mode`, `/payer-mode`) (**owns `public_router`** for public review routes) | 25 + 2 public |
| `huume.py` | Huume plan approve/execute — `POST /threads/{id}/huume/plan/approve` (flip named/all `proposed` steps to `approved`) + `.../plan/execute` (run every `approved` step, idempotent). Plans are keyed by `offer_id` (a thread may onboard several candidates at once); both routes take an optional `offer_id` in the body and fall back to "the sole active plan" via `actions.resolve_plan_offer_id`, 400ing with the candidate list when more than one is active and none was named. `/plan/execute` delegates to `services/huume/store.execute_plan_locked` — the same per-`(thread_id, offer_id)` advisory-locked path the chat tool's `execute_approved_steps` uses, so a UI-button execute and a chat-driven execute for the same candidate can't race. Also `GET .../huume/record` — the panel-facing fetch for the chat tool `show_record` (normalized incident/er_case/employee/credential view via `services/huume/record_view.py`, admin's own auth, re-checks the record type's own feature flag) — and `DELETE .../huume/record`, which drops one entry from the panel's open-record working set (`current_state.huume_records`, `store.update_huume_records`) via a record tab's `×`. `GET .../huume/offers` lists every offer letter ever drafted from the thread (`offer_letters.source_thread_id`, set once by `onboarding_skill`, never repointed) — `current_state.huume_offer` is a single slot that agent.py overwrites on each `draft_offer_letter` call, so this is what lets the panel keep a tab for an earlier candidate's offer after a second one is drafted in the same thread. `require_feature("huume")` on top of the package gate. See root CLAUDE.md's `huume` flag row for the full picture — the agent loop itself lives in `services/huume/`, not this package (only the REST counterpart to its chat-driven `execute_approved_steps`/`cancel_staged`/`show_record` tools does; `cancel_staged` has no REST twin, chat-only) | 5 |
| **Total** | | **200 routes** (+ 4 public) — was 199 before `huume.py`'s `DELETE .../huume/record` route (2026-07-29). Stale as of 2026-08-05 (`huume.py`'s new `GET .../huume/offers` route not reflected, and a fresh `grep -h "^@router\." app/matcha/routes/matcha_work/*.py \| wc -l` now returns 210, not 202) — this whole total needs a proper recount, not a one-line patch |

## Three routers

The package exposes **three** routers from `__init__.py`:

1. `router` — mounted at `/matcha-work`, feature-gated with `require_feature("matcha_work")` at construction (the constructor gate, not just the mount — see Gate note below).
2. `public_router` — mounted at `/matcha-work/public`, no gate. Aggregates public sub-routers from `projects.py` (signature webhook), `github.py` (push webhook), and `threads.py` (public review GET/POST).
3. `presence_router` — mounted at `/matcha-work/presence`, no gate. Owned entirely by `presence.py`.

**Unlike `ir_incidents/`/`employees/`, `router` is a fresh `APIRouter()`** in `__init__.py`, not a re-export of one submodule's router. Verified during the split: no submodule declares an empty-path route (`@router.get("")`), so there's no "prefix and path both empty" hazard to avoid — the crud-owns-router workaround those packages use isn't needed here.

### Gate note

`router`'s `require_feature("matcha_work")` dependency is declared in the `APIRouter(dependencies=[...])` constructor in `__init__.py` — this mirrors what the flat file did (the same gate was ALSO applied at the mount in `routes/__init__.py`, so it's effectively double-applied, same as before the split). Submodule routers themselves are all bare `APIRouter()` with no gate — the gate lives only on the package-level aggregator.

## Order-sensitive routes (Starlette matches in registration order)

Two same-method overlapping route pairs exist. Each pair lives entirely within **one** submodule, in its original relative order — moving one half without the other would break matching:

1. `PUT /projects/{project_id}/sections/reorder` **before** `PUT /projects/{project_id}/sections/{section_id}` — both in `sections.py`.
2. `PUT /threads/{thread_id}/project/sections/reorder` **before** `PUT /threads/{thread_id}/project/sections/{section_id}` — both in `sections.py` (the legacy thread-scoped project group).

A third pair (`DELETE /tasks/{task_id}` vs `DELETE /tasks/dismiss`) used to live in `workspace.py` and was shadowed the same way (`task_id` is a plain, non-UUID-converter path param). It moved with the rest of the task board to `routes/dashboard/tasks.py` (2026-07-28) and was fixed there — `/tasks/dismiss` is now registered first.

**Don't reorder within a submodule** if it changes the relative position of either pair. Include order **between** submodules in `__init__.py` is free — no other route shares both method and an overlapping path pattern with anything in a different submodule (verified exhaustively against the full route dump at every phase of the split).

## Adding a new endpoint

1. Find the right submodule by domain. If genuinely new, create a new submodule: `router = APIRouter()` at module scope, add `from .<name> import router as _<name>_router; router.include_router(_<name>_router)` to `__init__.py`.
2. Helpers come from `from ._shared import ...` or the owning submodule (e.g. `_render_project_pdf` from `pdf_export.py`, `_apply_ai_updates_and_operations` from `services/matcha_work/ai_apply.py`). Don't redefine them locally.
3. Tenant isolation: filter by `company_id = await get_client_company_id(current_user)` and verify ownership (`_verify_project_access` for project-scoped resources) before reading/writing.
4. `tags`/`prefix`/feature-gate live at the mount in `routes/__init__.py`, not on submodule decorators.

## Cross-submodule imports (intra-package dependency graph, acyclic)

- `_shared` ← everything.
- `services/matcha_work/ai_apply.py` ← `threads.py`, `messaging.py` (for `_apply_ai_updates_and_operations` + slide/blog/recruiting context helpers).
- `services/matcha_work/matcha_work_handbook_upload.py` ← `threads.py` (`run_handbook_upload` + `_thread_accepts_handbook_upload`). That service lazily imports `_shared._build_thread_detail_response` back **inside** `run_handbook_upload` — a top-level import would cycle, since `threads.py` imports the service at module scope. (`_sse_data` no longer needs the lazy hop; it comes from `services/matcha_work/message_shapes.py` at module scope.)
- `services/matcha_work/turn_pipeline.py` ← `messaging.py` only (the pipeline `send_message_stream` orchestrates).
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

Two lazy in-function imports (`from .dashboard import ...` in `threads.py`'s global-tasks helper, `from .thread_ws import thread_manager` in two AI-turn call sites) were valid single-dot relative imports when the file was flat (`app/matcha/routes/matcha_work.py`, sibling of `dashboard.py`/`thread_ws.py` in `app.matcha.routes`). Moving the file into the `matcha_work/` subpackage silently changed what a single dot resolves to. Fixed to absolute (`app.matcha.routes.dashboard`, `app.matcha.routes.work.thread_ws`) during the split. **If you see a bare `from .X import` anywhere in this package reaching for a module outside `matcha_work/`, it's wrong** — this package's own submodules are the only valid single-dot targets, and this package uses absolute imports for those anyway (see above).

## Tests

Full suite: `cd server && ./venv/bin/python -m pytest tests/matcha_work/ -q` — expect **6 failed / 242 passed / 8 skipped** (measured 2026-07-19). The 6 failures are all `test_blog_pdf_export.py` (`TestRenderProjectPdf` PDF-rendering assertions) and are pre-existing — unrelated to either the 2026-07-03 package split or the 2026-07-19 `tasks.py` split. (The older "12 failed / 126 passed" figure this doc carried predates a good deal of test growth; re-measure rather than trusting a remembered number.)

`pytest tests/` (the whole server suite) hits unrelated pre-existing collection errors in other packages (documented in `employees/CLAUDE.md`) plus a GUSTO-OAuth-env-var collection-order fragility — `test_language_tutor.py`'s module-level prompt-constant import triggers `app.matcha.routes.integrations.provisioning`'s startup check, which only succeeds if an earlier-collected file (`test_journal_isolation.py`, alphabetically first) has already called `os.environ.setdefault("GUSTO_OAUTH_*", ...)`. Pre-existing, not introduced by this split — scope `pytest` to `tests/matcha_work/` (or set the GUSTO env vars / load `.env` first) to avoid it.

## Thread modes (moved from root Key Modules)

- **Matcha Work thread modes** (`matcha/services/matcha_work/matcha_work_modes.py` — THE registry) — per-thread grounding modes, one boolean column each on `mw_threads`: `node` (internal data), `compliance`, `payer`, `benefits`, `legal`, `risk`, `training`. Toggle via `POST /matcha-work/threads/{id}/modes/{key}` (3 legacy per-mode aliases remain). Context builders in `services/matcha_work/matcha_work_node.py` (node/compliance/payer-staff) + `services/matcha_work/matcha_work_mode_contexts.py` (benefits/legal/risk/training, all read-only SQL — legal deliberately does NOT call `legal_defense.gather_evidence` per turn). Adding a mode = migration + builder + one `ThreadMode` entry + one frontend `THREAD_MODE_TOGGLES` row (`client/src/work/components/panels/constants.ts`); everything else (setter, route, column lists, models, dispatch loop, toggle buttons, list badges) is registry-driven. Compliance + payer keep bespoke dispatch blocks in `messaging.py` (`custom_dispatch=True`). Modes that read a **paid** subsystem carry `required_feature` (benefits→`benefits_admin`, legal→`legal_defense`, risk→`risk_profile`, training→`training`): the toggle route 403s without the flag, the dispatch loop re-checks it each turn (so a revoked flag stops injecting), and the frontend hides the button. node/compliance/payer predate this and stay ungated.
