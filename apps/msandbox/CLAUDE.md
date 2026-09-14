# apps/msandbox — agent sandbox, session manager, AutoPR harness

Operator tooling that lives beside the product, not inside it. Nothing under
`server/`, `client/`, or `deploy/` imports from here; the only edges into the
product are the `/matcha-work/**/autopr/*` HTTP endpoints the harness calls
and the `mw_tasks.autopr_*` columns they read.

## Layout

| Path | What | Entry |
|---|---|---|
| `bin/agent-sandbox.sh` | Legacy control plane + the one-command system entrypoint (`msandbox` → this) | `./apps/msandbox/bin/agent-sandbox.sh <cmd>` |
| `cli/` | Python package `apps.msandbox.cli`: sessions, dashboard, install, AutoPR queue/control | `python3 -m apps.msandbox.cli` |
| `harness/` | kanban-autopr: collect → select → investigate → checkpoint → publish, per card | GitHub Actions `kanban-autopr.yml` |
| `error-autofix/` | Silent-production-error lane, same shape | `silent-error-autofix.yml` |
| `self-audit/` | The harness auditing its own scripts | `autopr-self-audit.yml` |
| `scope/` | Open-PR scope guard | called from the lanes |
| `sandbox/` | `Dockerfile*`, `entrypoint.sh`, the five compose files | via `bin/` and `cli/` only |
| `tests/` | 28 suites; python ones import `apps.msandbox.cli` | see ci.yml |
| `docs/` | AGENT_SANDBOX, MSANDBOX_SESSIONS, KANBAN_AUTOPR, SILENT_ERROR_AUTOFIX | — |

## Invariants that are easy to break from inside this tree

- **Repo root is derived by fixed depth, not `git rev-parse`.** `cli/*.py` use
  `parents[3]`; `bin/` and every `harness/`, `error-autofix/`, `self-audit/`,
  `tests/` script use `../../..`. The workflow runs the harness from a
  `git archive` extract that is not a git repo, and the relative walk lands on
  that extract root exactly as it lands on the checkout. Moving a script one
  level changes what "the repo" is.
- **`harness/lib.sh` reaches `scripts/alembic_graph_snapshot.py` relative to
  itself, never via `$repo_root`.** Inside `autopr_migration_draft_errors` that
  variable is the model-touched workspace; the helper has to run from the
  trusted copy. `kanban-autopr.yml` documents the outage this prevents.
- **Compose is always invoked with an explicit `--project-directory`.** The
  compose files sit under `sandbox/`, but their `context: .`, workspace default
  and `.env` lookup all mean the tree they were written against — the repo root
  for `bin/agent-sandbox.sh` (`COMPOSE_PROJECT_DIR`), `cli/autopr_control.py`
  and `self-audit/audit.sh`, and `MSANDBOX_RUNTIME_ROOT` (the installed release,
  which is a copy of that layout) for `cli/docker_runtime.py`. A call site that
  forgets the flag silently builds from `sandbox/` instead.
  `tests/test_agent_sandbox_networking.sh` asserts both the resolved context and
  that all four call sites still pass it.
- **`apps/` is in all three model-patch denylists**
  (`harness/run-codex-sandboxed.sh` `PATH_DENY_RE`, `harness/publish.sh`,
  `error-autofix/publish.sh`). This directory is the control plane; a patch
  that edits it must be refused, not reviewed. `cli/validation.py` is *not* a
  fourth: its `apps/` only decides whether a TestPlan gets the
  automation-contracts check appended. Consequence of the move, deliberate:
  the kanban lane could publish the four operator docs while they lived at
  `docs/ops/`; under `apps/msandbox/docs/` it no longer can. Product docs
  under the top-level `docs/` are unaffected.
- **The self-audit lane's allowed-edit set** is the regex in
  `self-audit/publish.sh` — extend it when adding a subdirectory here, except
  `self-audit/` itself. The auditor is a sealed capsule: it must never be able
  to rewrite its own prompt, verifier or publisher, and
  `tests/test_autopr_self_audit.sh` fails if the regex lets it.
- **`self-audit/audit.sh` runs its contract suites from `AUDIT_TESTS_DIR`
  (`apps/msandbox/tests/`), never a hardcoded path in the loop.** A suite the
  list names that is not there is an operator finding — check exit 78, which
  `run_check` reclassifies as `operator` regardless of the declared class —
  because the capsule cannot be repaired by the model and a "repo" failure
  would hand Codex a run it must refuse. `tests/test_autopr_self_audit.sh`
  asserts every `CONTRACT_SUITES` entry exists and that a missing one
  dispatches no repair. Moving the tests directory again means updating that
  default and nothing else.
- **Every publisher that runs `git reset --hard` calls
  `autopr_require_writable_root` immediately after assigning `REPO_ROOT`**
  (`harness/publish.sh`, `harness/investigate.sh`, `error-autofix/publish.sh`,
  `self-audit/publish.sh`). One definition, in `harness/workspace-guard.sh` —
  the one lane directory the workflow's `git archive` always carries, so the
  control root resolves it too. The resets carry no pathspec, so an unset
  `AUTOPR_WORKSPACE_ROOT` means "the checkout you are editing"; the workflows
  set it, a local run has to start clean. Call it *after* the assignment: a
  guard that reads `REPO_ROOT` first dies in its own subshell under `set -u`
  and silently passes.
- **A test that runs a lane script must point it at a throwaway repo** with
  `AUTOPR_WORKSPACE_ROOT`. `test_kanban_autopr.sh` and
  `test_kanban_autopr_publish.sh` used to run the real `investigate.sh` and
  `publish.sh` against the live checkout.
- **A `progress_note` write settles the run claim, so a STOPPED header must
  return the card's column in the same PATCH.** `claim_autopr_run` moves a
  picked card to In Progress; `collect.sh` admits In Progress only while that
  claim is live, and any later note or column event settles it
  (`project_task_service._AUTOPR_ACTIVE_CLAIM_QUERY`). `run-journal.sh`
  therefore hands a failed card back to its lane — Changes Requested with a
  PR, else Todo, the same rule as `card-control.sh unstick` — in the note
  write itself, exactly as `checkpoint.sh` does for a pause. A note-only
  write strands the card where nothing can select it (card `9a384f39`, run
  `34782997839`).
- **Cleanup books the failure ledger FIRST, then re-stamps it from the
  server's clock.** Everything after `record_outcome` is a best-effort network
  round-trip, so a journal that hangs — or a Cleanup cut short by the job
  timeout — must not cost the card its strike. But the journal's hand-back
  PATCH is itself a column move, and `select.sh` parks a repeat offender only
  while the ledger sits at or after the card's last move, so
  `autopr_touch_attempt_ledger` moves the marker back in front of it using the
  `updated_at` the server returned for that very move. Never compare a
  Postgres timestamp with a `date` reading on the runner: the park gate is one
  comparison and two clocks would decide it. `consume` keeps its place ahead
  of the journal — `checkpoint.sh`'s tick-ledger comment depends on it.
  `tests/test_kanban_autopr.sh` asserts the whole order.
- **The host Codex login is checked before anything is spent on it**:
  `cli/codex_auth.py` is the one implementation (`codex-backoff.sh auth-check`
  is its shell face), run by `dispatch-if-idle.sh` every tick, by the kanban
  workflow before Select, by `run-codex-sandboxed.sh` before it touches the
  sandbox, and printed by `msandbox doctor`. The sandbox copy of `auth.json`
  is bind-mounted read-only and the ChatGPT refresh token is single-use, so an
  expired access token never refreshes into working; only `codex login` on
  the runner Mac does.
- **`auth-check` exit 4 means the credential is dead; any other non-zero means
  the check could not run.** Never conflate them. The dispatcher halts every
  lane on 4, so reporting a harness fault that way is a permanent silent stop
  behind a banner saying `codex login`, which cannot clear it. On anything
  else the dispatcher logs `codex-auth-check-unavailable` and proceeds — this
  is a spend guard, not a safety boundary, the same doctrine as
  `hot-redispatch-guard.sh`. The kanban workflow preflight and
  `run-codex-sandboxed.sh` follow the same rule: refuse on 4, warn and carry on
  otherwise. `cli/codex_auth.py` returns None for every shape it cannot read,
  including an `exp` that overflows `datetime` — raising there would make the
  shell face exit 1, which reads as "could not check" and fails OPEN on a
  credential just proved unverifiable.
- **The dispatcher caches the login verdict per `(auth file, mtime)` for
  `AUTOPR_CODEX_AUTH_CACHE_SECONDS`.** Both LaunchAgents tick every 60s and
  this guard sits above the watcher's idle short-circuit, so an uncached check
  would spawn bash + python3 ~1,440 times a day for a claim that changes about
  once every ten days. `codex login` rewrites `auth.json`, so a repaired login
  is picked up on the next tick rather than after the TTL.
- **The installed dispatcher tree is FLAT.** `install-launch-agent.sh` copies
  `harness/` into `~/.local/share/matcha-kanban-autopr` with no `cli/`
  sibling, so a `cli/` helper an installed script resolves must be (a) added
  to that installer and (b) resolved with a `$SCRIPT_DIR/<name>` fallback —
  see `select.sh` (`autopr_control.py`) and `codex-backoff.sh`
  (`codex_auth.py`). Missing the fallback made every installed tick report a
  dead Codex login. `tests/test_kanban_autopr_dispatch.sh` both checks the
  name list (comments stripped — a file merely mentioned in one used to
  satisfy it) and runs the real `install_runtime` into a throwaway root, then
  uses the result.
- **`run-journal.sh` never infers the board column from `$CARD_FILE`.** That
  snapshot is taken by `collect.sh` before `investigate.sh` claims the card,
  so its column is the lane the card came FROM and is never `in_progress`. An
  unreadable board is therefore treated as `in_progress` — this run's own
  claim put it there — and a card the run never claimed is unaffected, since
  the server writes no `column_change` when the value does not change.
  "Unreadable" means *the card was not extracted*, not "the body was empty": a
  200 carrying a proxy error page or a list the task is absent from has to
  count too, which is why one `jq` extracts the row and its success is the
  signal. And the journal body is composed before that PATCH is attempted, so
  it may not promise a retry — it names `msandbox autopr unstick` for the case
  where the write did not land.
- **`msandbox install` and `msandbox doctor` dispatch before the launcher's
  legacy-entrypoint probe.** Both run entirely inside the pinned release, and
  putting the probe first is what stranded operators across the `apps/` move:
  an error, and no way to install the launcher that would fix it.
- **`cli/install.py:RELEASE_PATHS`** is the single list of what an installed
  release carries; the copy step and the dirt probe both read it, and a path
  missing from the checkout is a hard error rather than a silently-clean id.
- **`harness/install-launch-agent.sh:install_runtime`** is parsed by
  `cli/install.py:dispatcher_installed_files` and by
  `tests/test_kanban_autopr_dispatch.sh`; keep it a flat list of names.

## Installed copies never auto-update

Two trees on the operator's Mac are copies: `~/.local/share/matcha-msandbox/releases/<sha>/`
(pinned by `~/.local/bin/msandbox`) and `~/.local/share/matcha-kanban-autopr/`
(run by the LaunchAgents). `msandbox doctor` reports drift; `msandbox install`
refreshes both. A launcher written before this directory existed cannot
upgrade itself — run `./apps/msandbox/bin/agent-sandbox.sh install` once.

Full mechanics: `docs/MSANDBOX_SESSIONS.md`, `docs/KANBAN_AUTOPR.md`,
`docs/AGENT_SANDBOX.md`.
