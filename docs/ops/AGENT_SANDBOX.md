# Agent sandbox

An isolated Docker workspace for running a coding agent (Codex, Claude Code,
or OpenCode) against this repo with broad/no-approval execution, without
giving it the macOS home directory, browser profiles, Keychain, host SSH
agent, or the host Docker socket.

Quickstart, from anywhere. `msandbox install` creates a versioned controller
under `~/.local/share/matcha-msandbox/releases/`; the launcher no longer points
into whichever branch happens to be checked out:

```bash
msandbox install
msandbox session create payroll-fix --agent codex --dev
msandbox session create inventory-pr --agent opencode --pr 348
msandbox session create ios-review --agent claude
msandbox session list
```

Every session owns a detached Git worktree, Compose project, home directory,
tmux TUI, attachment inbox, and validation record. Multiple sessions of the
same agent can run simultaneously. See `docs/ops/MSANDBOX_SESSIONS.md` for the
complete session, attachment, testing, PR-submission, and recovery workflows.

```bash
msandbox build --playwright   # rebuild with Chromium, or after Dockerfile changes
msandbox doctor payroll-fix
msandbox test payroll-fix --pr --xcode affected
msandbox attach payroll-fix ./shot.png --send
msandbox paste payroll-fix --send
msandbox session submit payroll-fix --draft
msandbox audit                # read-only AutoPR repo + machine-state audit
```

The legacy single-workspace/AutoPR control-plane commands remain compatible:

```bash
msandbox system up
msandbox system status
msandbox system down
msandbox login codex
```

Bare `msandbox` lists active sessions instead of opening or blocking on a
global workspace. `scripts/agent-sandbox.sh` remains the repository
compatibility entrypoint used by existing automation.

## What's isolated, and what isn't

The boundary here is **host-machine isolation, not blast-radius isolation.**
Once inside, an agent running with full/no-approval execution can do a lot —
that's a design choice made in this plan, documented below rather than hidden.

**Always blocked**, regardless of config:
- macOS home directory, browser profiles, Keychain, host SSH agent
- host Docker daemon/socket (no `docker build`, no starting sibling containers)
- any filesystem path outside this repo
- root filesystem is read-only; all Linux capabilities dropped except
  `CHOWN`/`DAC_OVERRIDE`/`FOWNER`/`SETGID`/`SETUID` (needed only for the
  entrypoint's one-time volume setup before it drops to the unprivileged
  `agent` user); `no-new-privileges`
- published ports bind to `127.0.0.1` only

**Deliberately reachable** (by design — see `docker-compose.sandbox.yml`):
- the repo bind mount, including `secrets/roonMT-arm.pem` and `server/.env`
- the normal host `matcha-postgres` and `matcha-redis` development services,
  through Docker Desktop's `host.docker.internal` gateway. A permissionless
  agent can change that same local development data; it cannot inspect or
  control the host Docker daemon.
- SSH to the app EC2 (`54.177.107.107`) and DB EC2 (`13.56.253.173`) — prod
  scripts (`prod-psql.sh`, `logs.sh`, `migrate-prod.sh`, `backups.sh`,
  `sync-test-tenants.sh`) work from inside the sandbox
- `~/.aws` mounted read-only — static access keys from `[default]`, not SSO,
  so they're long-lived and account-wide. A dedicated least-privilege IAM
  profile for the sandbox is a reasonable follow-up, not yet done.
- a no-approval agent in this container can therefore read prod data over
  SSH/psql and call the AWS CLI. `update-ec2.sh` (live deploy) additionally
  requires `SANDBOX_ALLOW_DEPLOY=1` — see below.

## Three lanes

**In-sandbox** (the default): editing code, running the dev stack against the
normal local development Postgres/Redis, reading prod logs/DB, most of
`scripts/`.

**Host-only build/deploy**: `build-and-push.sh` refuses to run inside the
sandbox — it needs `docker buildx` against a real daemon, which the sandbox
intentionally has none of. `update-ec2.sh` (live prod deploy) runs inside the
sandbox only with `SANDBOX_ALLOW_DEPLOY=1` set; otherwise it also refuses.
Run both from the host normally:
```bash
./scripts/build-and-push.sh && ./scripts/update-ec2.sh --matcha
```

**Host-only Xcode**: `platforms/desktop/Espresso/` (macOS) and the iOS
projects under `platforms/ios/` need Xcode/`xcodebuild`, which cannot run in
a Linux container. An agent in the sandbox can still edit Swift and
`project.pbxproj` through the bind mount; build/test/open on the host:
```bash
./scripts/xcode-build.sh espresso build
./scripts/xcode-build.sh matchatutor test
```
See `scripts/xcode-build.sh` for the full target list and the existing
`release.sh` / `release-appstore.sh` / `run-prod.sh` for signing/notarization
and prod-tunneled runs — this wrapper doesn't reimplement those.

## Legacy/control-plane command reference (`scripts/agent-sandbox.sh`)

The session-oriented command reference is in `MSANDBOX_SESSIONS.md`.

| Command | What it does |
|---|---|
| `build [--playwright]` | Build the workspace image |
| `start` / `stop` / `off` / `status` | Master lifecycle with a required health summary; stop refuses active/unknown agent work unless `--force` is explicit; `off` is the explicit immediate shutdown. `start` bootstraps the self-hosted `com.matcha.github-actions-runner` LaunchAgent; `stop`/`off` boot it out so a stray `workflow_dispatch` has nowhere to run. Set `AUTOPR_MANAGE_RUNNER=0` if the runner is administered separately. |
| `autopr-ready` | Silent readiness probe used by the dispatcher/workflow |
| `shell [cmd...]` | Plain shell, or run one command, in the workspace |
| `exec <cmd> [args...]` | Non-interactive exact-argv command; used by trusted automation wrappers |
| `dev [args]` | `AGENT_SANDBOX=1 ./scripts/dev-remote.sh` inside the container |
| `doctor` | Runs the isolation/capability checklist below |
| `audit [--draft]` | Runs deterministic AutoPR/msandbox checks. Repository failures can dispatch the sealed draft-repair workflow with `--draft`; pending migrations and other machine state remain explicit operator actions. |
| `attach <file...>` | Copies only explicitly selected files (50 MiB each by default) to the gitignored `.msandbox/attachments/` inbox and prints `/workspace/...` paths understood by Codex, Claude Code, and OpenCode. Content hashes make repeats idempotent. |
| `paste` | macOS bridge for a copied Finder file/PDF or PNG clipboard image; imports it through the same bounded inbox. Run it in a host terminal, then paste the printed path into an existing agent prompt. |
| `login <codex\|claude\|opencode\|gh>` | Authenticate one agent (own state volume) |
| `run <codex\|claude\|opencode> [args]` | Start that agent with full execution |
| `codex` / `claude` / `opencode` | Shorthand for `run <agent>` |

Env vars: `AGENT_SANDBOX=1` (compose sets this automatically; `CODEX_SANDBOX=1`
still works as an alias in `dev-remote.sh` and the two dev-DB scripts).
`SANDBOX_UID`/`SANDBOX_GID` override the in-container user (default: your
macOS uid/gid, so files the agent writes land owned by you, not root).
Every sandbox shell also receives `DATABASE_URL` and `REDIS_URL` pointing at
the normal local dev services through `host.docker.internal`; these override
the repo `.env` files' host-only `localhost` addresses. `HOST_DEV_BACKEND_URL`,
`HOST_DEV_FRONTEND_URL`, `HOST_DEV_TELLUS_URL`, and `HOST_DEV_OCEANLAB_URL`
point at the host-run application stack for browser and integration tests.
`INSTALL_PLAYWRIGHT_BROWSERS=true` bakes in a Chromium for isolated Playwright
runs. `SANDBOX_ALLOW_DEPLOY=1` permits `update-ec2.sh` from inside the sandbox.
`MSANDBOX_ATTACHMENT_MAX_BYTES` changes the per-file import limit, and
`MSANDBOX_ATTACHMENTS_DIR` exists as a test/administration override. The
default inbox stays inside the repository bind mount but is ignored by Git, so
no new host directory is exposed and no attachment can enter an AutoPR clone.

Examples (run these from a host terminal; dragging after `attach` pastes the
selected Finder path into that command):

```bash
evidence="$(msandbox attach "/path/you/dragged/screenshot.png")"
msandbox codex -i "$evidence" "Diagnose what this screenshot shows"

evidence="$(msandbox paste)"       # copied screenshot or Finder file/PDF
msandbox claude "Read $evidence and help me fix the issue"
msandbox opencode --prompt "Read $evidence and help me fix the issue"
```

For an agent session that is already open, run `msandbox attach` or
`msandbox paste` in a second host terminal and paste the printed `/workspace/`
path into the existing prompt. Codex's `-i/--image` flag attaches initial
images directly; PDF and other document paths remain ordinary readable
workspace files. This bridge is deliberately explicit because mounting the
whole macOS temp tree or home directory would undo the sandbox boundary.

The host and sandbox development stacks use separate host port namespaces:

| Service | Host `dev-remote.sh` | Container port | Sandbox URL on the Mac |
|---|---:|---:|---:|
| Backend | 8001 | 8001 | `http://localhost:18001` |
| Main frontend | 5174 | 5174 | `http://localhost:15174` |
| Tell-Us | 5191 | 5191 | `http://localhost:15191` |
| Oceanlab | 5201 | 5201 | `http://localhost:15201` |
| Chat/utility | 8080 | 8080 | `http://localhost:18080` |

`SANDBOX_HOST_BACKEND_PORT`, `SANDBOX_HOST_FRONTEND_PORT`,
`SANDBOX_HOST_TELLUS_PORT`, `SANDBOX_HOST_OCEANLAB_PORT`, and
`SANDBOX_HOST_CHAT_PORT` override only the Mac-facing sandbox publications.
`BACKEND_PORT`, `FRONTEND_PORT`, `TELLUS_PORT`, `OCEANLAB_PORT`, and `CHAT_PORT`
remain the ports used by processes inside the container. If the host stack is
deliberately moved, the corresponding `HOST_DEV_*_PORT` variable updates the
gateway URL without changing either sandbox port.

`AGENT_SANDBOX_PROJECT_NAME`, `SANDBOX_WORKSPACE_DIR`, and `SANDBOX_AWS_DIR`
let a trusted wrapper create a separate container/volume namespace and narrow
the two host mounts. Kanban AutoPR uses all three: its project is
`matcha-kanban-autopr-sandbox`, its workspace is a clean disposable clone, and
its AWS mount is an empty directory. These are host-controlled containment
inputs, not options exposed to the model.

## Kanban AutoPR lane

The Kanban worker does not run OpenCode in the normal interactive workspace.
`scripts/kanban-autopr/run-opencode-sandboxed.sh` creates a tracked-files-only
clone of the selected task branch, removes its remote, and mounts that clone in
a dedicated msandbox project. Untracked `.env` files, PEM files, the Actions
checkout, host home, Docker socket, GitHub token, Matcha bot password,
production SSH key, and AWS credentials are absent. The model has broad
edit/bash/web access inside the clone and can reach the normal local dev
Postgres/Redis services through the Docker host gateway. The dedicated worker
publishes no host ports; the interactive sandbox uses its separate sandbox
port range, so the worker, interactive sandbox, and host dev stack can all run
together.
When it exits successfully, the trusted host copies
out the report/decision and applies one binary patch to the task branch; the
normal verifier and publisher remain outside the container. The bridge rejects
more than 25 changed files, patches larger than 5 MB, oversized reports or
decisions, and any symlink/submodule change before applying the patch.

The primary `msandbox` command is the authoritative AutoPR master switch.
`msandbox` or `msandbox start` starts the normal workspace container, writes a
private enable marker, loads/kicks the five-minute LaunchAgent, and creates the
host tmux dashboard. Startup prints primary-container, master-switch, timer,
dashboard, and agentic-activity state before opening a shell. A missing timer
or any dead/missing dashboard pane makes startup fail and rolls back anything
that invocation started. Re-entering bare `msandbox` refuses when another
Codex/OpenCode/Claude or AutoPR run is active, leaving that work untouched.
The activity summary identifies whether a coding agent belongs to the primary
sandbox, the AutoPR sandbox, or both, so a protected interactive session is not
mistaken for an unseen AutoPR run.
`msandbox stop` likewise refuses active work—or an unknown GitHub state—and
requires `msandbox stop --force` to interrupt deliberately. A successful stop
removes the marker first, unloads the timer, closes the dashboard, boots out the
self-hosted `com.matcha.github-actions-runner` LaunchAgent, and stops the
primary workspace plus every Kanban/error/self-audit worker container.
`msandbox off` is the equivalent immediate shutdown
command, so it also interrupts active work. Booting the runner out means a
`workflow_dispatch` (the only trigger `kanban-autopr.yml` has) queues with no
executor instead of running a gated no-op — it also idles the sibling
`schema-drift-checks.yml` and `silent-error-autofix.yml`, which share this
runner, plus `autopr-self-audit.yml`, until the next `msandbox start` (or
`AUTOPR_MANAGE_RUNNER=0` to opt out).
The dispatcher, GitHub workflow, and dedicated model launcher independently
require the marker, running primary workspace, loaded timer, and four live
dashboard panes.

No second OpenCode login is required for the Kanban worker. Before each run,
the trusted bridge copies the Mac's existing `~/.local/share/opencode/auth.json`
to a private mode-700 runtime directory and bind-mounts that **single file**
read-only into the dedicated container. OpenCode needs an auth credential to
call its provider; this keeps the rest of the host OpenCode home (history,
logs, database, and other state) out of the model's reach. Set
`AUTOPR_HOST_OPENCODE_AUTH_FILE` only if the working host auth file lives
elsewhere.

## AutoPR self-audit lane

The dispatcher gives `.github/workflows/autopr-self-audit.yml` one idle slot
when its last completed audit is six hours old. `msandbox audit` runs the same
checks on demand without changing state; `msandbox audit --draft` dispatches
the workflow only when a deterministic repository contract fails. The audit
also compares the running local dev database's `alembic_version` rows with the
repository graph and checks the control plane, but classifies those as operator
actions. It never applies DDL, starts a service, or creates a fake code fix for
machine drift.

For a repository failure, OpenCode runs in its own
`matcha-autopr-self-audit-sandbox` tracked-files-only clone. Its publisher
allows only the existing AutoPR/msandbox scripts, sandbox definitions, their
contract tests, and corresponding docs. The self-audit scripts and workflow
are a sealed capsule: the model cannot rewrite its own prompt, verifier,
publisher, or workflow. Verification must turn every original repairable
failure green without adding another one before the trusted host opens a draft
PR. It never merges or deploys.

## Validation checklist

`msandbox doctor` runs all of this automatically. What it checks:

- `/var/run/docker.sock` absent inside the container
- no `/Users` (host home) visible inside the container
- container runs as your host uid (files land with correct ownership)
- `git status` inside `/workspace` succeeds without a "dubious ownership"
  warning
- SSH to the app EC2 succeeds
- `aws sts get-caller-identity` succeeds
- the normal host `matcha-postgres`/`matcha-redis` services are reachable
  through the Docker Desktop gateway
- `codex`, `claude`, `opencode`, `gh`, `aws`, `ssh`, `git` are all on `PATH`

Manual checks worth doing once after a fresh build:
- `msandbox dev` starts backend/worker/frontend/Tell-Us/Oceanlab; edit a
  `client/src` file on the host and confirm HMR fires (the sandbox uses
  polling watchers since bind-mounted macOS trees don't emit native Linux
  filesystem events)
- with host `./scripts/dev-remote.sh` running, `curl "$HOST_DEV_FRONTEND_URL"`
  from `msandbox shell` reaches that host frontend while the Mac browser keeps
  using `http://localhost:5174`
- `msandbox stop` leaves the host's browser data, Docker state, and
  `matcha-postgres`/`matcha-redis` containers alone (the data persists because
  it is the normal local development stack)

## Chat model

No chat model ships in the sandbox by default (`--chat` is refused there — see
`dev-remote.sh`). The macOS/GPU-backed `llama-server` this repo uses for local
chat can't run in the Linux container, and its model directory is
deliberately not mounted in. If chat is needed later: run a separately
controlled host model server and expose only its port to the container, or
build a Linux-compatible model service with its own named volume — do not
mount the host model directory.
