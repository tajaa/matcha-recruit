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
  automation-contracts check appended.
- **The self-audit lane's allowed-edit set** is the regex in
  `self-audit/publish.sh` — extend it when adding a subdirectory here, except
  `self-audit/` itself. The auditor is a sealed capsule: it must never be able
  to rewrite its own prompt, verifier or publisher, and
  `tests/test_autopr_self_audit.sh` fails if the regex lets it.
- **Every publisher that runs `git reset --hard` refuses a dirty worktree when
  `AUTOPR_WORKSPACE_ROOT` is unset** (`harness/publish.sh`,
  `harness/investigate.sh`, `error-autofix/publish.sh`,
  `self-audit/publish.sh`). The resets carry no pathspec, so unset means "the
  checkout you are editing"; the workflows set the variable, a local run has to
  start clean. Assign `REPO_ROOT` *above* the guard — a guard that reads it
  first dies in a subshell under `set -u` and silently passes.
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
