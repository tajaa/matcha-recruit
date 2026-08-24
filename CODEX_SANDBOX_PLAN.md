# Codex Sandbox Plan

## Goal

Run Codex with broad command approval inside an isolated development container so it can work with the Matcha repository and `scripts/dev-remote.sh` without access to macOS browser profiles, Keychain data, or the host Docker daemon.

The current Codex Desktop app runs on the host. Full Access there is therefore not an acceptable isolation boundary. The sandboxed workflow will use Codex CLI inside the container. Desktop-app attachment can be considered later through a remote app-server, but should not be assumed for the first implementation.

## Security boundary

The container will:

- Mount only `/Users/finch/Documents/github/matcha` as the workspace.
- Use a dedicated non-root Linux user.
- Use a dedicated Codex home volume, not the host `~/.codex`.
- Not mount the host home directory, browser profiles, Keychain, SSH agent, or GitHub CLI configuration.
- Not mount `/var/run/docker.sock`; Docker-socket access would let Codex escape the sandbox by starting privileged containers or mounting host paths.
- Drop Linux capabilities and enable `no-new-privileges`.
- Publish development services only on `127.0.0.1`.

Codex will still be able to read anything inside the repository, including repository-local `.env` files and `secrets/` files. If those must also be hidden, they need to be masked and their required values injected separately.

## Proposed layout

```text
macOS host
├── repository bind-mounted read/write
├── localhost development ports
└── browser profiles, Keychain, home directory, Docker socket: not mounted

Codex Compose project
├── codex-workspace
│   ├── Codex CLI
│   ├── Git and GitHub CLI
│   ├── Python, Node, tmux, PostgreSQL tools
│   └── Matcha repository
├── postgres (dedicated sandbox volume)
└── redis (dedicated sandbox volume)
```

## Files to add

### `docker/codex-sandbox/Dockerfile`

Build a Linux development image containing:

- Codex CLI
- Git and GitHub CLI
- Python 3.12 and the server build dependencies
- Node 20 and npm
- tmux, `lsof`, PostgreSQL client tools, and Redis CLI tools
- Any system packages required by the existing server image
- Optional isolated Playwright/Chromium support for application tests; never mount a host browser profile

Run the workspace as a non-root user. Keep dependency directories in named volumes so macOS `node_modules` and virtual environments are not reused inside Linux.

### `docker-compose.codex.yml`

Define the workspace, PostgreSQL, and Redis services with:

- Dedicated named volumes for Codex state, Python dependencies, Node dependencies, Postgres, and Redis.
- No privileged mode and no Docker socket.
- Read-only root filesystem where practical, with tmpfs for `/tmp` and other runtime paths.
- Localhost-only port publishing for the backend, frontend, Tell-Us, Oceanlab, and optional chat endpoint.
- A dedicated sandbox Postgres volume rather than reusing a live or concurrently mounted Postgres data volume.

Provide an explicit database-import operation if the current local development data is needed. Never mount the same PostgreSQL data directory into two running containers.

### `scripts/codex-sandbox.sh`

Provide these commands:

```text
build       Build the sandbox image
login       Authenticate Codex inside the dedicated Codex-home volume
git-login   Authenticate GitHub inside the dedicated GitHub config volume
start       Start the sandbox services
dev         Run scripts/dev-remote.sh inside the workspace container
codex       Start Codex inside the workspace container
shell       Open a normal workspace shell
status      Show service and port status
stop        Stop the sandbox services
import-db   Explicitly import a copy of the local dev database
```

Codex authentication should use `codex login --device-auth` inside the container. GitHub pushes should use a repository-scoped token or an isolated `gh auth login` session, not the host Keychain or SSH agent.

Inside the externally sandboxed container, Codex may use its no-approval/full-access execution mode. That mode is intentionally limited by the container boundary, not by the host filesystem.

## `dev-remote.sh` integration

Add an explicit container mode, for example `CODEX_SANDBOX=1`, to `scripts/dev-remote.sh`.

In sandbox mode:

- Skip host Docker discovery, `docker run`, `docker start`, and `docker logs` calls.
- Use `postgres` and `redis` service names instead of `localhost` URLs.
- Preserve the existing tmux layout for backend, worker, frontend, Tell-Us, Oceanlab, and optional chat.
- Replace the Docker-log pane with a service readiness/status pane.
- Bind Vite to `0.0.0.0` so Docker-published ports are reachable from macOS.
- Enable file-watcher polling for bind-mounted source trees.
- Keep the existing port override variables and `stop` behavior.

The normal host workflow must remain unchanged when `CODEX_SANDBOX` is unset.

## Chat model

The default development stack should work without `--chat`. The existing chat path depends on a host model directory and a macOS/GPU-backed `llama-server`, neither of which should be mounted into the sandbox.

For optional chat support, use one of these later:

- Run a separately controlled host llama server and expose only its port to the container.
- Run a Linux-compatible model server inside the sandbox with its own model volume.

Do not mount the host model directory into the Codex workspace.

## Validation checklist

Before treating the setup as complete, verify:

- `/var/run/docker.sock` is absent inside the workspace container.
- Host browser-profile paths and Keychain paths are absent.
- The container cannot read unrelated paths under `/Users/finch`.
- Codex can inspect, edit, stage, commit, and optionally push repository changes.
- `scripts/dev-remote.sh` starts the backend, worker, frontend, Postgres, and Redis in sandbox mode.
- Backend, frontend, Tell-Us, and Oceanlab are reachable only through localhost ports.
- Hot reload works through the repository bind mount.
- A database import, when requested, populates only the sandbox Postgres volume.
- Stopping the sandbox leaves host browser data and host Docker state untouched.

## Implementation order

1. Add the Docker image and Compose services.
2. Add the workspace bootstrap and isolated authentication commands.
3. Add `CODEX_SANDBOX` handling to `dev-remote.sh`.
4. Start the stack and validate isolation before enabling full Codex execution.
5. Validate the complete dev workflow and document the optional chat path.
6. Consider Desktop-app remote attachment only after the containerized CLI workflow is stable.
