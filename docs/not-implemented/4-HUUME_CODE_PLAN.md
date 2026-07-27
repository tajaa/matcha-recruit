# Huume Code — `@huume` writes a PR from collab chat

> **Status (verified 2026-07-26): NOT IMPLEMENTED.** No `huume_code` flag anywhere in
> `feature_flags.py` or the codebase; no draft-PR tooling. Build order: **must follow
> `1-REFACTOR_PLAN_ROUND2.md`** — this adds `services/huume_code/` and
> `services/matcha_work/github_write.py` and edits `project_task_service.py`, all inside
> that refactor's Stage 3/6 blast radius, so building first means paying the migration
> twice. Also the highest-risk item here (model-driven GitHub **write** surface,
> process-wide PAT scope escalation on the app EC2, 2 new tables, auth-adjacent service
> user rows) and internal-only in v1 by its own admission — last on both axes.

## Context

Huume today is an HR agent: a bounded Gemini tool-calling loop (`server/app/matcha/services/huume/`) that runs inside a single `mw_threads` turn and stages HR actions for confirmation.

Separately, a matcha-work **collab** project already has every piece needed for engineering work — a GitHub repo bound to the project, an Elements repo snapshot, a kanban board, and a chat channel — but nothing joins them. A developer can look at a ticket, and look at the repo; nobody can ask for the change.

This adds that. In an Espresso collab's chat, `@huume work on the login-timeout ticket` makes Huume read the board, read the bound repo, write code, and open a **draft PR**. The draft PR is the review gate: Huume never merges, never pushes to a default branch, and never runs repo code.

Three decisions are fixed:
- **No confirm turn.** The mention *is* the request. Huume acks in chat and starts. Unlike an HR record, the artifact is a reviewable draft PR.
- **New company flag `huume_code`**, business collabs only. Personal Espresso projects deferred (the bot identity needs a `company_id`).
- **No clone, no code execution on the server.** Everything through the GitHub REST API.

## What already exists — reuse, don't rebuild

| Piece | Where |
|---|---|
| GitHub **read** (validate repo, tree, blobs, commits, webhook verify/install) | `services/matcha_work/github_service.py` |
| Repo bound per project | `mw_projects.github_repo` / `.github_branch` / `.github_last_scanned_sha`; routes in `routes/matcha_work/github.py` |
| Repo context for a model | `element_repo_service.build_grounding_context()`, `.fetch_convention_docs()`, `.assemble_context()`; snapshot in `mw_element_repo_files` |
| `@handle` parsing (handle = email local-part) | `services/matcha_work/mentions.py:parse_mentions` |
| Server → collab-chat posting | `project_task_service.py:~648-681` — INSERT `channel_messages` then `channels_ws.manager.broadcast_message(...)` |
| Fire-and-forget off the WS hot path, own connection, same channel→project reverse lookup | `channels_ws.py:49 _spawn_bg` + `:55 _bg_sync_channel_attachments` |
| Bounded agent loop shape (step recorder, never-raises, force-finish, tool registry, `huume_runs`/`huume_steps` audit) | `services/huume/agent.py`, `tools.py`, `prompt.py`, `store.py` |
| Repo-grounded self-contained Gemini calls | `services/matcha_work/ticket_draft_service.py` (the Props flow) |

Verified facts the design leans on: the WS send block (`channels_ws.py:770-885`) is `async with get_connection()` with **no** open transaction, and by line 868 it has the channel uuid, `ChannelUser` (id/name/email/**role**/company_id), the persisted message row, and `is_new_message`. Every people-picker query already filters `users.is_active = true`, and `routes/auth/login.py:133` 403s on inactive — so an inactive bot user is excluded from pickers and login **for free**, with no new column. `users.role` permits `'client'` (widened by migration `zw1x2y3z4a5b`). Celery has one default queue, `task_time_limit=600` / `task_soft_time_limit=540`, and `task_acks_late=True` **without** `task_reject_on_worker_lost` — so a killed worker loses the task rather than redelivering it (no duplicate-PR risk; stale `running` rows instead).

---

## Design

### 1. Feature flag

`huume_code` in `server/app/core/feature_flags.py:DEFAULT_COMPANY_FEATURES`, default **off**, admin-toggle, **not** in any tier overlay. Add the row to the root `CLAUDE.md` flag table. Use the `/add-feature-flag` command for the standard wiring.

### 2. Bot identity — one inactive user per company

`channel_messages.sender_id` is `NOT NULL REFERENCES users(id)`, and display names come from a `COALESCE(clients.name, employees…, admins.name, users.email)` that appears in ~35 queries. Rather than touch those, give Huume a real (unusable) user:

- `users` row: `email = 'huume@<company_id>.invalid'` (RFC-6761 reserved → `email.py:_is_reserved_test_domain` blocks any send; local-part `huume` so `@huume` parses under the existing mention regex), `role = 'client'`, **`is_active = false`**, `password_hash` = a non-verifiable sentinel.
- `clients` row: `name = 'Huume'`, `company_id`, `job_title = 'AI agent'` — this is what makes every existing query render **Huume**.
- Deliberately **not** a `channel_members` row: the trigger reads `parse_mentions` output directly, so the bot stays out of member lists, presence, and mention-email fan-out.

New helper `services/huume_code/identity.py:ensure_huume_bot_user(conn, company_id) -> UUID`, idempotent (`ON CONFLICT (email) DO NOTHING` + re-select).

> `is_active = false` is load-bearing in three places at once — login, people-pickers, invite lookup. Note it in the helper's docstring so nobody "fixes" it.

### 3. Trigger — `channels_ws.py`, right after mention parsing

Insert immediately after line 868 (`mentioned_user_ids = …`), gated on `is_new_message`, mirroring `_bg_sync_channel_attachments` exactly:

```python
if is_new_message and "huume" in mention_handles:
    _spawn_bg(_bg_maybe_dispatch_huume_code(str(ch_uuid), user, row["content"], row["id"]))
```

The bg function (own connection, never raises) resolves and gates in order, replying in chat on each refusal:

1. channel → project: `SELECT id, company_id, github_repo, github_branch FROM mw_projects WHERE project_type='collab' AND project_data->>'discussion_channel_id' = $1`
2. `merge_company_features(...)` → `huume_code` on, and `matcha_work` on
3. sender role ∈ {`client`, `admin`} **and** `_can_edit_project(role)` for this project
4. project has `github_repo` — else "Connect a GitHub repo in Elements first."
5. per-company rate limit `check_rate_limit(company_id, "huume_code_run", 10, 3600)`
6. no live run: no `huume_code_runs` row for this project in `queued`/`running` **started under 15 min ago** (older ⇒ treat as dead, see §7)
7. INSERT `huume_code_runs` (status `queued`) → `run_huume_code.delay(str(run_id))` → post the ack as the bot.

Add an expression index so the reverse lookup stops being a seq scan on every mention (it is already unindexed for the attachment mirror — this fixes both):

```sql
CREATE INDEX IF NOT EXISTS idx_mw_projects_discussion_channel
ON mw_projects ((project_data->>'discussion_channel_id'));
```

### 4. Chat output — `services/huume_code/chat.py`

`post_as_huume(company_id, channel_id, content) -> None`: `ensure_huume_bot_user` → INSERT `channel_messages` → `channels_ws.manager.broadcast_message(...)` with `sender_name="Huume"`. Copied from the kanban-move echo, and like it, deliberately skips mention parsing, activity bumps, and the in-app notification fan-out.

Must use `database.connection_or_direct()`, not `get_connection()` — this runs in the **pool-free** Celery worker. The Redis pub/sub fan-out (`_FANOUT_CHANNEL`) is what gets the message onto live sockets from the worker process; that already works across uvicorn workers, so it works from Celery too.

Budget: **≤4 messages per run** — ack, "picked ticket X, editing", PR link, and a failure line if it comes to that.

### 5. GitHub write — `services/matcha_work/github_write.py`

New sibling to `github_service.py` (keep read/write separate; reuse its `_headers()`, `GITHUB_API`, `GitHubError`, `_excluded`):

- `ensure_branch(repo, base_branch, new_branch)` — `GET /git/ref/heads/<base>` → `POST /git/refs`; returns the base commit sha. Existing branch is reused, never force-updated.
- `commit_files(repo, branch, base_sha, files, deletes, message)` — `POST /git/blobs` per file → `POST /git/trees` (with `base_tree`) → `POST /git/commits` → `PATCH /git/refs/heads/<branch>` (no `force`).
- `open_draft_pr(repo, head, base, title, body)` — `POST /pulls` with `draft: true`; returns `html_url`.

**Ops prerequisite:** the existing server-global `GITHUB_TOKEN` is read-only. It needs `contents: write` + `pull_requests: write`. Set it in `~/matcha/.env.backend` on the app EC2 (these four `GITHUB_*` vars are read via `os.getenv`, not declared in `config.py`). Fail with a legible chat message on 403.

#### The write allowlist — required, not optional

There is exactly **one** GitHub identity for all tenants: a process-wide PAT, no per-project or per-company token column anywhere, no GitHub App. Today `github_service.validate_repo` is the only thing between a tenant and *any repo that PAT can read* — a tenant admin types an `owner/name` into the Elements connect sheet and it is accepted if the token can see it. Read-only, that is a disclosure concern. **Adding write scope turns it into: any tenant admin can open a PR on any repo Matcha's token can write to.**

So `github_write.py` gates every write on a server-side allowlist:

```
GITHUB_WRITE_ALLOWED_REPOS = "tajaa/matcha-recruit,tajaa/scratch"   # exact owner/name, comma-separated
```

Empty or unset ⇒ **all writes refused** (fail closed). Every write helper checks the project's `github_repo` against it and raises `GitHubError` with a message the bot relays verbatim. This is a blunt instrument and it is the right one for v1: the blast radius becomes a list a human typed.

> **Known v1 limitation, state it in the flag's CLAUDE.md row:** Huume can only write to repos on that server-side list, because the PAT is global. Fine for internal use and dogfooding; **not shippable to customers with their own repos** — that needs a GitHub App with per-installation tokens (a new table plus a refactor of `_headers()`, not a config change).

### 6. The agent — `services/huume_code/`

New package structurally mirroring `services/huume/` (`agent.py` / `tools.py` / `prompt.py` / `store.py` / `chat.py` / `identity.py`), with three deliberate differences:

- **Bounds:** ~30 model calls, **wall clock 420s**. That fits inside Celery's existing `task_soft_time_limit=540` with room for the force-finish path — no Celery config change and no new queue.
- **No SSE.** Progress goes to chat via §4, throttled; the caller is a Celery task, not a request.
- **A working set.** `write_file`/`delete_file` stage into an in-memory dict; **one** commit is pushed at `open_pr` time. No partial-push state to reconcile.

Tools:

| Tool | Kind | Notes |
|---|---|---|
| `list_tickets` | read | Open `mw_tasks` for the project (`todo`/`in_progress`/`changes_requested`) + subtask counts |
| `read_ticket(task_id)` | read | Full description + `mw_subtasks` checklist + the ticket's `element_id` |
| `list_files(prefix?)` | read | Repo tree, fetched once per run and cached |
| `read_file(path)` | read | Working set first, else blob at base ref |
| `search_repo(query)` | read | Substring over the `mw_element_repo_files` snapshot + tree paths — no dependency on GitHub code search |
| `write_file(path, content)` | write | Stages. Enforces the denylist + caps (§8) |
| `delete_file(path)` | write | Stages |
| `open_pr(title, body)` | write | Branch + commit + draft PR + move ticket to `review` |
| `post_update(message)` | write | Throttled chat note |
| `finish(message)` | finish | Ends the turn |

**Ticket selection is a tool call, not a matcher.** Keeping the trigger dumb (it only asks "is this a Huume-capable project?") means no fuzzy-match code to maintain: the agent calls `list_tickets`, picks, and states its choice in the ack. If genuinely ambiguous it asks in chat and calls `finish` — one cheap turn, no repo work.

There is **no read-one-task endpoint or service helper** in the package (the client fetches the whole board plus a separate subtasks call), so `read_ticket` is a small new function in `services/huume_code/store.py` built on the existing ownership guard `project_subtask_service._task_in_project`. Don't add a route for it — nothing outside the agent needs one.

**Grounding is scoped by the ticket's element.** `mw_tasks.element_id` (TEXT, FK to `mw_project_elements`) already links a ticket to an element, and each element owns `repo_paths` globs over the project's single repo. So once the agent picks a ticket, prefer `build_grounding_context(project_id, element_id)` for that element over the whole-project snapshot — the same narrowing `commit_scan_service` already does in the other direction. Fall back to project-wide when the ticket has no element. Plus `fetch_convention_docs(project_id)`, which is what surfaces `CLAUDE.md`-style convention files. Watch the budgets: the snapshot itself caps at 40 KB/file, 600 files, 5 MB total, and `assemble_context`'s `DEFAULT_CONTEXT_BUDGET` is 300 K chars — pass a smaller budget here, since this context is re-sent on every one of ~30 model calls.

Model `gemini-3.6-flash`, matching `huume/agent.py`.

Force-finish on a bound hit: if the working set is non-empty, still open the draft PR marked partial; otherwise post that it couldn't finish and change nothing.

### 7. Persistence — migration `huumecode01`

```
huume_code_runs(
  id, company_id, project_id, channel_id, task_id NULL,
  requested_by, trigger_message_id,
  status  -- queued | running | done | failed
  branch NULL, pr_url NULL, error NULL,
  model_calls, files_changed, token_usage JSONB,
  created_at, started_at, completed_at
)
huume_code_steps(run_id, seq, tool, kind, label, args, result, status)  -- mirrors huume_steps
```

Plus the §3 expression index. **Concurrency is guarded at the trigger** (step 6) rather than by a partial unique index on `task_id`, because the ticket isn't known until the agent picks it. Because `task_acks_late` is on but `task_reject_on_worker_lost` is not, a worker killed by the hourly `docker restart matcha-worker` **loses** the task rather than redelivering it — so there is no duplicate-PR risk, only a stale `running` row. Two things clear it: the 15-minute staleness window in step 6, and a reconcile pass in `@worker_ready` (`celery_app.py`) that flips `running` rows older than 15 minutes to `failed` — the same idiom the compose file already documents for OOM-stranded rows.

> A 7-minute run has a real chance of straddling the hourly worker restart. v1 fails cleanly and says "interrupted — ask me again". The proper fix (a `huume_code` queue on a second worker container exempt from the restart cron: `task_routes` in `celery_app.py` + a service in `docker-compose.yml`) is a deliberate follow-up, not v1.

### 8. Guardrails

The ticket text and repo file contents both reach a model that can write files — treat them as untrusted input. Containment is the denylist plus the draft PR, and the denylist is the part that is actually load-bearing:

- **Path denylist, enforced in `write_file`/`delete_file`** (not in the prompt): `.github/**`, `secrets/**`, `deploy/**`, `*.pem`, `.env*`, anything in `github_service.EXCLUDED_DIRS`. `.github/**` is not hygiene — `ci.yml` runs `on: pull_request` using the **head** ref's workflow file, so a PR that edits it executes the edited version against the repo. A draft PR does not contain that.
- Caps: ≤25 files touched, ≤80 KB per file, ≤400 KB total staged.
- The **write allowlist** of §5 — the one guardrail that bounds which repos exist as targets at all.
- Never force-push; never target the default branch; PR is always `draft: true`; branch is always `huume/<short-task-id>-<slug>`.
- Every run and tool call lands in `huume_code_runs`/`_steps`.

### 9. Board integration

Move the ticket to `in_progress` at start and `review` at PR open, with the bot as actor.

Note the side effects before wiring it: `project_task_service`'s column-move path posts a chat echo **and** `_notify_task_column_transition` emails every collaborator. Two board moves per run means two emails per run to everyone. Recommendation: call the underlying update directly and **suppress the email notification** for bot-actor moves, keeping the chat echo (which is the useful signal and is already where the conversation is).

### 10. Client (Espresso) — effectively zero

Huume's messages are ordinary `channel_messages` arriving over the existing channel WebSocket, so they render in collab chat with **no Swift changes at all**. `MessageBubbleView.swift:13-21` already parses message content as Markdown into an `AttributedString`, so posting the PR as `[PR #123](https://github.com/…)` renders tappable for free — Huume should always emit markdown links rather than bare URLs.

One optional polish item: a "Huume can work here" line in the existing `githubBar` (`ProjectElementsView.swift:173-190`, right beside the connect/change-repo + Scan-commits controls), showing whether the flag is on and a repo is bound. Not required to ship.

---

## Files touched

**New** — `server/app/matcha/services/huume_code/{__init__,agent,tools,prompt,store,chat,identity}.py`, `server/app/matcha/services/matcha_work/github_write.py`, `server/app/workers/tasks/huume_code.py`, `server/alembic/versions/huumecode01_*.py`, `server/tests/huume_code/`.

**Edited** — `server/app/core/feature_flags.py` (flag), `server/app/werk/routes/channels_ws.py` (trigger + one bg function, ~40 lines), `server/app/workers/celery_app.py` (`@worker_ready` reconcile), `CLAUDE.md` (flag row + a line in the Symbol Map), and optionally `platforms/desktop/Espresso/…/ProjectElementsView.swift`.

## Verification

1. **Unit, no DB** — pure helpers: path denylist (assert `.github/workflows/ci.yml`, `secrets/x.pem`, `.env.backend` are all refused), the caps, branch-name slugification, and the working-set read-your-writes behaviour of `read_file`. Follow `tests/matcha_work/` conventions.
2. **Bot identity** — `ensure_huume_bot_user` twice in a row returns the same id; the created user cannot log in (`POST /api/auth/login` → 403) and does not appear in `GET /matcha-work/admin-users/search`.
3. **GitHub write, against a scratch repo** — a small script that calls `ensure_branch` → `commit_files` → `open_draft_pr` and asserts the PR is `draft: true` on a `huume/*` branch. Run manually; do **not** point it at `matcha`. Also assert the allowlist fails closed: with `GITHUB_WRITE_ALLOWED_REPOS` unset, every write helper raises.
4. **End-to-end on dev** (`./scripts/dev-remote.sh`, local `matcha-postgres`): enable `huume_code` on a dev company, bind a scratch repo to a collab project, create a kanban ticket, type `@huume work on <ticket>` in the collab chat, and watch for the ack → picked-ticket note → PR link. Verify `huume_code_runs`/`_steps` rows and that the ticket moved to `review`.
5. **Refusal paths** — repeat with the flag off, with no repo bound, as an `employee`-role member, and twice in quick succession; each should produce exactly one explanatory chat reply and no Gemini spend.
6. **Interrupt** — `docker restart matcha-worker` mid-run; confirm the stale `running` row is reconciled on worker start and no second PR appears.
7. `cd server && ./venv/bin/python -m pytest tests/huume_code tests/matcha_work -q` (matcha_work has 6 known pre-existing `test_blog_pdf_export.py` failures — ignore those).

**Do not run** `alembic upgrade` against prod, and do not deploy — migration application and rollout are the user's call.
