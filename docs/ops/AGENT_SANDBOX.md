# Agent sandbox

An isolated Docker workspace for running a coding agent (Codex, Claude Code,
or OpenCode) against this repo with broad/no-approval execution, without
giving it the macOS home directory, browser profiles, Keychain, host SSH
agent, or the host Docker socket.

Quickstart, from anywhere (`~/.local/bin/sandbox` is a symlink to
`scripts/agent-sandbox.sh`):

```bash
sandbox build          # first time, or after Dockerfile/dependency changes
sandbox login codex    # or: login claude / login opencode / login gh
sandbox dev             # backend/worker/frontend/Tell-Us/Oceanlab in tmux
sandbox codex           # in another terminal — or `claude` / `opencode`
sandbox doctor          # isolation + capability self-check
```

`sandbox` is just `./scripts/agent-sandbox.sh` under a short name; both work
identically. Run `sandbox` with no args for the full command list.

## What's isolated, and what isn't

The boundary here is **host-machine isolation, not blast-radius isolation.**
Once inside, an agent running with full/no-approval execution can do a lot —
that's a design choice made in this plan, documented below rather than hidden.

**Always blocked**, regardless of config:
- macOS home directory, browser profiles, Keychain, host SSH agent
- host Docker daemon/socket (no `docker build`, no starting sibling containers)
- any filesystem path outside this repo
- root filesystem is read-only; all Linux capabilities dropped except
  `CHOWN`/`SETGID`/`SETUID` (needed only for the entrypoint's one-time volume
  setup before it drops to the unprivileged `agent` user); `no-new-privileges`
- published ports bind to `127.0.0.1` only

**Deliberately reachable** (by design — see `docker-compose.sandbox.yml`):
- the repo bind mount, including `secrets/roonMT-arm.pem` and `server/.env`
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

**In-sandbox** (the default): editing code, running the dev stack, hitting
local sandbox Postgres/Redis, reading prod logs/DB, most of `scripts/`.

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
| `start` / `stop` / `status` | Compose lifecycle (`stop` preserves volumes) |
| `shell [cmd...]` | Plain shell, or run one command, in the workspace |
| `dev [args]` | `AGENT_SANDBOX=1 ./scripts/dev-remote.sh` inside the container |
| `doctor` | Runs the isolation/capability checklist below |
| `import-db [--yes]` | Sandbox-only Postgres replaced with a dump of local `matcha-postgres` |
| `login <codex\|claude\|opencode\|gh>` | Authenticate one agent (own state volume) |
| `run <codex\|claude\|opencode> [args]` | Start that agent with full execution |
| `codex` / `claude` / `opencode` | Shorthand for `run <agent>` |

Env vars: `AGENT_SANDBOX=1` (compose sets this automatically; `CODEX_SANDBOX=1`
still works as an alias in `dev-remote.sh` and the two dev-DB scripts).
`SANDBOX_UID`/`SANDBOX_GID` override the in-container user (default: your
macOS uid/gid, so files the agent writes land owned by you, not root).
`INSTALL_PLAYWRIGHT_BROWSERS=true` bakes in a Chromium for isolated Playwright
runs. `SOURCE_DB_CONTAINER`/`SOURCE_DB_NAME`/`SOURCE_DB_USER` retarget
`import-db`. `SANDBOX_ALLOW_DEPLOY=1` permits `update-ec2.sh` from inside the
sandbox.

## Validation checklist

`sandbox doctor` runs all of this automatically. What it checks:

- `/var/run/docker.sock` absent inside the container
- no `/Users` (host home) visible inside the container
- container runs as your host uid (files land with correct ownership)
- `git status` inside `/workspace` is clean — no "dubious ownership" warning
- SSH to the app EC2 succeeds
- `aws sts get-caller-identity` succeeds
- sandbox Postgres/Redis are reachable
- `codex`, `claude`, `opencode`, `gh`, `aws`, `ssh`, `git` are all on `PATH`

Manual checks worth doing once after a fresh build:
- `sandbox dev` starts backend/worker/frontend/Tell-Us/Oceanlab; edit a
  `client/src` file on the host and confirm HMR fires (the sandbox uses
  polling watchers since bind-mounted macOS trees don't emit native Linux
  filesystem events)
- `sandbox import-db` only ever changes the `sandbox_postgres_data` volume —
  `docker ps -a | grep matcha-postgres` after should still show your normal
  local dev DB container untouched
- `sandbox stop` leaves the host's browser data, Docker state, and
  `matcha-postgres`/`matcha-redis` containers alone

## Chat model

No chat model ships in the sandbox by default (`--chat` is refused there — see
`dev-remote.sh`). The macOS/GPU-backed `llama-server` this repo uses for local
chat can't run in the Linux container, and its model directory is
deliberately not mounted in. If chat is needed later: run a separately
controlled host model server and expose only its port to the container, or
build a Linux-compatible model service with its own named volume — do not
mount the host model directory.
