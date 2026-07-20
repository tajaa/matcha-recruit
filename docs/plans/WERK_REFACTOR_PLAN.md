# Werk + matcha-work Refactor — 4 Tracks, Phased

## Context

Daily-friction pains named by user, confirmed by code exploration:

1. **Commit→kanban check-off never fires.** Pipeline is GitHub-API server-pull only (needs server `GITHUB_TOKEN` + per-project connected repo; auto-scan only on board open; every failure silently swallowed at `ProjectDetailViewModel+Elements.swift:319`). No local-git scanning exists despite Props UI claiming globs "drive the commit-scan matcher". Element `repo_paths` globs are a no-op for matching (`_load_open_candidates` does no filtering). **User chose: local git scan as primary**, GitHub webhook as backstop.
2. **Thread LLM chats unsophisticated.** Single blocking Gemini call per turn, JSON-envelope straitjacket (`response_mime_type=application/json`), no token streaming (desktop shows spinner→blob, ignores `status` events), 15–20 message window, model sees project filenames only, no tool loop. Rich infra exists unused: operation dispatcher, mode context builders, RAG/embeddings. **User chose all four levers**: streaming, tool loop, drop JSON envelope, bigger memory.
3. **Tickets can't be "about" things.** Only rail is 1:1 `mw_tasks.element_id`. **User chose all target types**: project files/docs, elements/features, threads/chats, external (deal memos etc.).
4. **Structural debt**: `tasks.py` 1755 lines (5 unrelated areas), `send_message_stream` ~770-line function, round logic duplicated route+service.

Order: **A (cleanup) → B (commit scan) → C (aboutness) → D (thread AI)**. Each phase independently shippable.

Migrations: author → commit → `./scripts/migrate-dev.sh` (multi-head repo: set `down_revision` to current `alembic heads` tip at authoring time). Prod migrations left for user. Desktop: pbxproj has no auto-sync — **only 2 new Swift files total** (4 pbxproj entries each).

---

## Phase 0 — Unblock the test baseline (do FIRST, before Track A)

Measured baseline (`cd server && ./venv/bin/python -m pytest tests/matcha_work/ -q`), **not** the figure originally assumed:

- Without flags the suite **fails collection entirely**: `test_language_tutor.py` → `AttributeError: module 'google.genai.types' has no attribute 'HarmCategory'`.
- With `--ignore=tests/matcha_work/test_language_tutor.py`: **25 failed / 199 passed / 8 skipped**.

Two blockers to clear before refactoring anything:

**0a. Unpinned genai — latent production boot hazard.** `requirements.txt:6` pins `google-genai>=0.3.0`; the local venv resolved **2.0.0**, which removed `types.HarmCategory`. `services/ir_voice_parser.py:130` uses it at **module import time**, so `import app.matcha.routes` raises → the whole route tree (and therefore the app) fails to import on any genai 2.x install. Fix: pin genai to the working major in `requirements.txt` **and** make the safety-settings block version-tolerant (string category names, or `getattr` guard). Must land before Track D, which is genai-heavy — and it's what currently blocks running tests at all.

**0b. Triage the 5 `test_project_task_toggle.py` failures.** These sit in exactly the kanban round/toggle code Track A2 consolidates. Refactoring on top of already-red tests in the same area means no green signal to prove behavior preservation. Fix them or confirm-and-document why each is expected-red before A2. (`test_blog_pdf_export` + `test_journal_isolation` failures are known-pre-existing per prior session notes and are out of scope — leave them.)

After Phase 0, re-measure and freeze the number: every later phase must preserve it exactly.

---

## Track A — Structural cleanup

### A1: Split `server/app/matcha/routes/matcha_work/tasks.py` (behavior-preserving)
New route modules (follow `matcha_work/CLAUDE.md` split conventions — bare `APIRouter()`, absolute imports, wire in `__init__.py`):
- `ticket_drafts.py` — 14 ticket-draft endpoints (tasks.py:573–708)
- `task_history.py` — history, `/history/replay`, activity log/feed (tasks.py:710–885, 1029–1171)
- `task_files.py` — task file up/download + `_verify_task_belongs_to_project` (tasks.py:1173–1254)
- `research_tasks.py` — research-tasks endpoints (tasks.py:1256–1755); extract inline logic to new `services/research_task_service.py`. **Keep JSONB storage in `mw_projects.project_data` + response shapes byte-identical** (web consumes via `client/src/work/api/matchaWork/research.ts`). No migration.
- `tasks.py` keeps: pipeline-mode, task CRUD/reject/approve/ai-draft, subtasks, rounds, summarize.

Risk: tests importing `matcha_work.tasks` module-level names — grep `server/tests/matcha_work/` and repoint.
Verify: pytest baseline unchanged; route count unchanged; manual: draft promote, replay, task file upload, research run (web).

### A2: Round-logic consolidation
Extract duplicated round-start block (`project_task_service.py:975–1000` reject flow, `tasks.py:960–1000` start-round endpoint) into one helper in `project_subtask_service.py` (owns `_current_round:43`): `start_new_round(conn, *, task_id, project_id, actor_user_id, title) -> int` — logs `round_started`, carries `is_done=false` subtasks forward. Both call sites use it inside existing transactions. Keep the attachment `created_at` re-stamp in the route. History metadata stays string-only (desktop `[String: String]` decode trap).
Verify: `pytest tests/matcha_work/test_project_task_toggle_realdb.py`; manual reject→new round + carry-over.

### A3: Decompose `send_message_stream` (`messaging.py:468`, ~770 lines) — prereq for D
Stage functions in same file, SSE-emitting stages as async generators over a mutable `TurnContext` dataclass: `_run_quota_gate`, `_prepare_attachments`, `_run_hard_stop_gates`, `_inject_mode_contexts` (registry loop :829–852 + bespoke compliance/payer :854–935), `_generate_turn` (D1/D2 slot in here), `_audit_and_persist` (citation audit :1049 → `_apply_ai_updates_and_operations` → broadcast). `_finalize_cancelled_turn` (:131) untouched.
Verify: pytest baseline; manual matrix on **web + Werk**: plain send, compliance mode, payer mode, hr_pilot hard-stop, attachment, cancel mid-turn.

### A4: Desktop splits — **SKIPPED** (deliberate)
Don't restructure 130-field `MWProjectTask` or split TaskViewerSheet+Sections/KanbanBoardView: decode-shape risk + pbxproj churn, zero behavior. Deferred follow-up.

---

## Track B — Commit→check-off via local git scan

### B1: Server — glob scoping, scan ledger, revive client-push endpoint
**Migration `scanledger0001_commit_scan_ledger.py`:**
```sql
mw_commit_scan_ledger(
  id UUID PK DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
  commit_sha VARCHAR(64) NOT NULL,
  source VARCHAR(16) NOT NULL,          -- 'github' | 'local'
  scanned_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE (project_id, commit_sha)
)
```
Real downgrade. Cross-source dedupe: a commit scanned by either source never re-sent to Gemini. `github_last_scanned_sha` semantics untouched; local pushes never move it.

`services/commit_scan_service.py`:
- `scan_commits` (:318): claim commits via `INSERT ... ON CONFLICT DO NOTHING RETURNING`; skip unclaimed; new `source:` kwarg.
- **Fix design drift** in candidate selection: per commit, tasks bound to element **matching** changed files (existing `element_matches_commit:109` / `match_changed_files_to_elements:125`) → in; bound non-matching → out; **unbound → in** (hybrid — strict bound-only would kill scan for projects that never bound elements). Update `_load_open_candidates:258` docstring; Props UI claim (`ProjectElementsView.swift:368`) becomes true.
- Errors surface: `match_commit_to_subtasks:203` raises on Gemini failure instead of `return []`; `scan_commits` counts per-commit → response gains additive `ai_errors` field.

`routes/matcha_work/github.py`:
- Revive `POST /projects/{id}/commit-scan` (:25, currently dead): Pydantic model `{source:"local", branch?, commits:[{sha, short_sha, message, branch?, changed_files:[str], diff?}]}`; caps: existing `MAX_COMMITS_PER_SCAN`, ~20KB diff truncation, changed_files cap. Response `{scanned, skipped_already_scanned, ai_errors, suggestions}`. Existing auth/edit gating.
- `github_scan_commits_endpoint` (:202) also writes ledger rows (`source='github'`). Webhook backstop unchanged.

Tests: extend `tests/matcha_work/test_commit_scan_glob.py` + new `test_commit_scan_ledger.py` — hybrid scoping (3 cases), cross-source dedupe, push validation/caps, ai_errors.

### B2: Desktop — local repo binding + scanner (**new file 1 of 2**)
**New** `Matcha/Services/Support/LocalGitScanner.swift` (+4 pbxproj entries):
- Security-scoped bookmark: NSOpenPanel folder pick → app-scoped bookmark in UserDefaults (`mw.localRepo.bookmark.<projectId>`), `startAccessingSecurityScopedResource` around scans. **Entitlements: add `com.apple.security.files.bookmarks.app-scope`** (sandbox + user-selected read-write already present).
- Git shell-out via `Process`: `git -C <path> log --pretty=format:%H%x1f%h%x1f%s%x1f%D%x1e --name-only -n 50 [<lastSha>..HEAD]` + `git rev-parse --abbrev-ref HEAD`; optional truncated `git show --stat`. CLT-missing probe → "Install Command Line Tools" message + GitHub-scan fallback. Client watermark (last-pushed HEAD) in UserDefaults; server ledger is authoritative dedupe.

Modified:
- `MatchaWorkService+Elements.swift`: `pushLocalCommits(projectId:commits:)` → the revived endpoint; decode additive fields.
- `Models/MatchaWork/ProjectElementModels.swift`: response model additions.
- `ProjectDetailViewModel+Elements.swift`: `localScanIfStale()` — prefer local when bookmark exists, else existing `autoScanCommitsIfStale` (:302); reuse 10-min cooldown. **Replace silent catch (:319)** with published `scanErrorMessage` (auto → dismissible board banner; manual → alert).
- `KanbanBoardView.swift` (:342 hook): call `localScanIfStale()` on board open; render banner; manual Scan button routes local when bound.
- `ProjectElementsView.swift` (Props): "Local repo" row — Connect Folder / bound path / Disconnect / Rescan.

Decisions baked in: trigger = board-open poll + manual button (FSEvents watcher deferred); one local repo root **per project** via bookmark (per-element paths rejected — element globs stay the server-side scoping mechanism).

Verify: xcodebuild; manual: connect folder → commit touching bound glob → open board → auto-check/chip; commit outside globs → bound tickets skipped, unbound matched; immediate re-scan → all `skipped_already_scanned`, zero Gemini calls; moved folder → visible error; GitHub backstop intact; no `GITHUB_TOKEN` needed for local path.

---

## Track C — Ticket aboutness: typed many-to-many refs

### C1: Backend
**Migration `taskref0001_task_refs.py`:**
```sql
mw_task_refs(
  id UUID PK DEFAULT gen_random_uuid(),
  task_id UUID NOT NULL REFERENCES mw_tasks(id) ON DELETE CASCADE,
  ref_type VARCHAR(24) NOT NULL,   -- 'file' | 'element' | 'thread' | 'external'
  ref_id UUID NULL,                -- NULL for external
  label VARCHAR(300) NULL,         -- required for external (service-enforced)
  url VARCHAR(1000) NULL, kind VARCHAR(40) NULL,   -- external: free-form sub-kind ('deal','doc',…)
  position INT NOT NULL DEFAULT 0, created_by UUID NULL, created_at TIMESTAMPTZ DEFAULT now()
)
-- partial unique (task_id, ref_type, ref_id) WHERE ref_id IS NOT NULL; idx (task_id); idx (ref_type, ref_id)
```
**`element_id` stays as-is** — board/scan-scoping concept (B1 uses it); refs = aboutness. No backfill/dual-write. Desktop may render element chip + ref chips in one visual row.

New `services/task_ref_service.py` (patterns: `broker/pilot.py:346` per-kind LEFT JOINs; `ir_incidents/_shared.py:261` entity_type/entity_id):
- `list_refs_for_tasks(task_ids)` — one query, LEFT JOINs `mw_project_files` (filename) / `mw_project_elements` (name) / `mw_threads` (title) for display labels; no N+1.
- `add_ref` (same-project ownership validation; verify `mw_threads` project/company linkage at implementation), `remove_ref`, `reorder`.

Routes (in `tasks.py` next to CRUD): `GET/POST /projects/{pid}/tasks/{tid}/refs`, `DELETE .../refs/{id}`; task-list payload gains additive `refs: [...]` (batched); task-create accepts optional `refs`. Picker uses existing file/element/thread list endpoints.

Tests: new `tests/matcha_work/test_task_refs.py` — CRUD, external-requires-label, cross-project rejected, CASCADE, label resolution, batched list.

### C2: Desktop (**new file 2 of 2**)
**New** `Matcha/Views/MatchaWork/TaskViewer/TaskRefsSection.swift` (+4 pbxproj entries) — chips row, picker sheet (Files / Elements / Threads / External form), tap-to-navigate dispatch.

Modified: `ProjectTaskModels.swift` (`MWTaskRef` + optional `refs` on `MWProjectTask` — additive, decode-safe); `MatchaWorkService+Tasks.swift` (CRUD); `TaskViewerSheet+Sections.swift` (mount section); `KanbanCard.swift` (compact chips: icon + count). Navigation via existing `AuxWindowTarget` (AppStateModels.swift:33) / `handleNotificationLink` (AppState.swift:829): file → `.file`, thread → `.thread(id)`, element → Props pane, external → `NSWorkspace.open(url)`.

Verify: build; add/remove/navigate each type; card chips; web task list unaffected; `npx tsc -p tsconfig.app.json --noEmit` if web types touched.

---

## Track D — Thread AI (streaming → tool loop → memory)

### D1: Real token streaming (backward-compatible SSE)
Server (`matcha_work_ai.py` + A3's `_generate_turn`):
- `client.aio.models.generate_content_stream(...)` replaces blocking thread-pool `_call_gemini` (:1149). Keep JSON envelope for now, Gemini cache (:868), model selection/entitlement clamps (:711).
- **Incremental reply extractor** (new pure function + unit tests): stateful scanner over accumulating raw text, finds `"reply":"` in envelope, emits unescaped contents as they grow → SSE `{type:"delta", text}`. Stream end → parse full JSON exactly as today → unchanged `complete` flow. Prompt nudge: emit `reply` first (temporary; D2 removes envelope).
- **hr_pilot threads: buffer-then-audit** — no deltas; citation audit (messaging.py:1049) on full text before persist/broadcast, identical to today.
- Disconnect mid-stream → cancel aiter → existing `_finalize_cancelled_turn` bills estimate. Keepalives stay for pre-generation stages.

Web-safe: `client/src/work/api/matchaWork/messaging.ts:59–83` passes unknown event types through (verified); optionally extend `MWStreamEvent` union (`client/src/work/types.ts:543`, additive).

Desktop (no new files): `ThreadDetailViewModel.swift` `handleSSEEvent:319` — add `case "delta": streamingContent += text`, `case "status":` → status line. UI already wired: `ChatPanelView.swift:311` renders `StreamingBubbleView(content: viewModel.streamingContent)`; `complete` already clears (:406). (Verified all three anchors.)

Verify: extractor unit tests (escapes, unicode, reply-last); pytest baseline; manual: Werk live tokens; web unchanged; hr_pilot no deltas + audit intact; cancel bills correctly.

### D2: Native tool loop + drop JSON envelope (biggest phase)
**Precedent (verified):** `services/research_browse_service.py:158–215` already implements a bounded multi-step function-call loop — `MAX_TURNS` iteration, append `candidate.content` to `contents`, collect `[pt for pt in parts if pt.function_call]`, execute, feed results back, break when no calls remain. **Copy this loop shape.** Caveat: it drives the *built-in* `computer_use` tool — grep confirms **zero custom `FunctionDeclaration` anywhere in the codebase**, so declaration generation + `function_response` round-tripping is genuinely new ground. Budget accordingly and cover it with the fake-genai test below.

- `ai_turn.py`: refactor `_apply_ai_updates_and_operations` internals into per-operation executor registry (1:1 with `SUPPORTED_AI_OPERATIONS`, matcha_work_ai.py:164 — 13 ops: create/update/save_draft/send_draft/finalize/send_requests/track/create_employees/generate_presentation/generate_handbook/generate_policy/execute_hr_action/none), individually callable.
- `matcha_work_ai.py`: generate Gemini `FunctionDeclaration`s from registry + doc/state-update writes + on-demand context tools from mode builders (`get_node_context` ← matcha_work_node.py:215, mode contexts ← matcha_work_mode_contexts.py, `search_project_files` / `read_project_file`). Bounded loop (max ~6 steps): stream deltas; `function_call` → execute → `function_response` → continue. Additive SSE `{type:"tool", name, status}`.
- Drop `response_mime_type=application/json`; plain-text replies stream natively (D1 extractor removed). Rewrite `MATCHA_WORK_STATIC_PROMPT_TEMPLATE` (:269–546) — most negative lines police the envelope; shrink hard; bump cache key. Defensive fallback: legacy-envelope parse path kept.
- `complete` event shape **unchanged** (content = accumulated text; effects applied via tools; `ai_reasoning_steps` metadata from tool trace so desktop metadata merge `ThreadDetailViewModel.swift:344–362` keeps working).
- **Payer mode excluded from loop initially** (Gemini constrains mixing `google_search` with function declarations) — stays on current single-shot search-grounded path.
- Escape hatch: `MW_TOOL_LOOP=off` env toggle → D1 path, one release.

Verify: declaration-parity unit tests (every op mapped), scripted fake-genai loop test; pytest baseline; manual matrix web+Werk: doc edit, slides, recruiting ops, node/compliance modes (statuses + citations), hr_pilot, cancel, Flash vs Pro tiers.

### D3: Bigger memory
- History window 20 → ~50 for Pro tier (matcha_work_ai.py:1412 / messaging.py:554), guarded by `estimate_usage` budget; rolling compaction (:1657) unchanged for older history.
- Semantic recall: embed thread messages on persist (reuse `embedding_service` / `_get_rag_context` infra); new `retrieve_thread_memory(query)` tool in D2 loop over full thread history + summaries. Migration `mwmem0001` **only if** no existing embedding store fits — check `embedding_service` tables first.
- Project files: filename-list injection (messaging.py:596–602) replaced by D2 `read_project_file` / `search_project_files` tools (reuse extraction :410).

Verify: recall tool unit test (stubbed embeddings); manual long-thread recall; token usage within entitlement clamps.

---

## Global risks
- Web client shares every endpoint — all payload/SSE changes additive; `[DONE]` terminator + `complete`/`error` semantics untouched.
- `mw_project_elements` (kanban buckets) vs `mw_elements` (offer-letter chat) name collision — never rename; new code says "project elements".
- Sandbox git shell-out: `Process` under active security scope; CLT probe + GitHub fallback.
- Migration rules (server/CLAUDE.md): real downgrades, commit before applying, `migrate-dev.sh` only (prod = user).
- Pre-existing pytest failures (12) must not grow.

## Deferred (noted, not in scope)
- A4 desktop God-file splits + `MWProjectTask` restructure.
- FSEvents live commit watcher.
- Payer mode in tool loop (SDK mixed-tools support).
