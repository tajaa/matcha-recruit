# Agent sandbox

An isolated Docker workspace for running a coding agent (Codex, Claude Code,
or OpenCode) against this repo with broad/no-approval execution, without
giving it the macOS home directory, browser profiles, Keychain, host SSH
agent, or the host Docker socket.

Quickstart, from anywhere (`~/.local/bin/msandbox` is a symlink to
`scripts/agent-sandbox.sh` — named `msandbox`, not `sandbox`, because
`~/Documents/github/claude-sandbox/sandbox` already owns that name as a
generic devcontainer launcher for other projects):

```bash
msandbox                # one command: build (if needed) + start + shell in
```
From that shell: `codex`, `claude`, or `opencode` are already on `PATH` and
already logged in once you've run `login` (below) — or drive the rest from
outside the container instead:
```bash
msandbox build --playwright   # rebuild with Chromium, or after Dockerfile changes
msandbox login codex          # or: login claude / login opencode / login gh
msandbox autopr-login         # isolated OpenCode login for the Kanban worker
msandbox dev                  # backend/worker/frontend/Tell-Us/Oceanlab in tmux
msandbox codex                # in another terminal — or `claude` / `opencode`
msandbox exec command args    # exact-argv, non-TTY automation path
msandbox doctor               # isolation + capability self-check
```

`msandbox` is just `./scripts/agent-sandbox.sh` under a short name; both work
identically. Run `msandbox help` for the full command list.

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

## Command reference (`scripts/agent-sandbox.sh`)

| Command | What it does |
|---|---|
| `build [--playwright]` | Build the workspace image |
| `start` / `stop` / `status` | Workspace lifecycle; `start` also ensures the normal local dev DB/Redis are running |
| `shell [cmd...]` | Plain shell, or run one command, in the workspace |
| `exec <cmd> [args...]` | Non-interactive exact-argv command; used by trusted automation wrappers |
| `dev [args]` | `AGENT_SANDBOX=1 ./scripts/dev-remote.sh` inside the container |
| `doctor` | Runs the isolation/capability checklist below |
| `login <codex\|claude\|opencode\|gh>` | Authenticate one agent (own state volume) |
| `autopr-login` | Authenticate OpenCode in the dedicated AutoPR project with empty workspace/AWS mounts |
| `run <codex\|claude\|opencode> [args]` | Start that agent with full execution |
| `codex` / `claude` / `opencode` | Shorthand for `run <agent>` |

Env vars: `AGENT_SANDBOX=1` (compose sets this automatically; `CODEX_SANDBOX=1`
still works as an alias in `dev-remote.sh` and the two dev-DB scripts).
`SANDBOX_UID`/`SANDBOX_GID` override the in-container user (default: your
macOS uid/gid, so files the agent writes land owned by you, not root).
Every sandbox shell also receives `DATABASE_URL` and `REDIS_URL` pointing at
the normal local dev services through `host.docker.internal`; these override
the repo `.env` files' host-only `localhost` addresses.
`INSTALL_PLAYWRIGHT_BROWSERS=true` bakes in a Chromium for isolated Playwright
runs. `SANDBOX_ALLOW_DEPLOY=1` permits `update-ec2.sh` from inside the sandbox.

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
Postgres/Redis services. When it exits successfully, the trusted host copies
out the report/decision and applies one binary patch to the task branch; the
normal verifier and publisher remain outside the container. The bridge rejects
more than 25 changed files, patches larger than 5 MB, oversized reports or
decisions, and any symlink/submodule change before applying the patch.

The dedicated project has its own persistent OpenCode account state. Log in
once before enabling the timer:

```bash
msandbox autopr-login
```

The next AutoPR investigation recreates that project's container with the
sanitized workspace and empty AWS mount while preserving its named auth volume.

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
