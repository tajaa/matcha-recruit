#!/usr/bin/env bash
# Run Codex, Claude Code, or OpenCode in the repository's isolated Docker
# development sandbox. See docs/ops/AGENT_SANDBOX.md for the full writeup.
set -euo pipefail

# Resolve through symlinks (e.g. ~/.local/bin/msandbox -> this file) so
# PROJECT_ROOT is the matcha repo root regardless of how this was invoked.
SCRIPT_SOURCE="${BASH_SOURCE[0]}"
while [[ -L "$SCRIPT_SOURCE" ]]; do
    SCRIPT_DIR="$(cd -P "$(dirname "$SCRIPT_SOURCE")" && pwd)"
    SCRIPT_SOURCE="$(readlink "$SCRIPT_SOURCE")"
    [[ "$SCRIPT_SOURCE" != /* ]] && SCRIPT_SOURCE="$SCRIPT_DIR/$SCRIPT_SOURCE"
done
PROJECT_ROOT="$(cd "$(dirname "$SCRIPT_SOURCE")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.sandbox.yml"
COMPOSE=(docker compose --project-name matcha-agent-sandbox --file "$COMPOSE_FILE")

usage() {
    cat <<'EOF'
Usage: msandbox [command] [args]   (or ./scripts/agent-sandbox.sh [command] [args])

Bare `msandbox` (no command) builds if needed, starts services, and drops you
into a shell in the workspace — the one-command way in.

Commands:
  build [--playwright]        Build the isolated workspace image.
  start                       Start workspace, PostgreSQL, and Redis.
  stop                        Stop sandbox services without deleting their volumes.
  status                      Show sandbox service status and published localhost ports.
  shell [cmd...]               Open a workspace shell (or run one command).
  dev [args]                   Run scripts/dev-remote.sh inside the workspace container.
  doctor                       Check the isolation + capability checklist.
  import-db [--yes]            Replace sandbox PostgreSQL with a dump of local matcha-postgres.

  login <codex|claude|opencode|gh>   Authenticate one agent (or GitHub) in its own state volume.
  run <codex|claude|opencode> [args] Start that agent with full execution inside the container boundary.
  codex [args]                       Shorthand for `run codex`.
  claude [args]                      Shorthand for `run claude`.
  opencode [args]                    Shorthand for `run opencode`.
  git-login                          Alias for `login gh`.

Set INSTALL_PLAYWRIGHT_BROWSERS=true (or `build --playwright`) to include an
isolated Chromium binary for Playwright. `import-db --yes` skips its
confirmation prompt. Set SANDBOX_UID/SANDBOX_GID to change the in-container
user (defaults to your macOS uid/gid so file ownership matches on both sides).
EOF
}

require_docker() {
    command -v docker >/dev/null || {
        echo "docker is required for the agent sandbox." >&2
        exit 1
    }
    docker info >/dev/null 2>&1 || {
        echo "Docker is not running or is not accessible." >&2
        exit 1
    }
}

start_services() {
    "${COMPOSE[@]}" up --detach postgres redis workspace
}

exec_workspace() {
    # `docker compose exec` defaults to root regardless of the entrypoint's
    # gosu drop (exec sessions bypass ENTRYPOINT) — force the unprivileged
    # agent user explicitly so every interactive session actually gets the
    # uid-aligned, non-root posture the image is built for.
    "${COMPOSE[@]}" exec --user "${SANDBOX_UID:-501}:${SANDBOX_GID:-20}" workspace "$@"
}

exec_workspace_no_tty() {
    "${COMPOSE[@]}" exec --no-TTY --user "${SANDBOX_UID:-501}:${SANDBOX_GID:-20}" workspace "$@"
}

login_agent() {
    local agent="$1"
    case "$agent" in
        codex)
            exec_workspace codex login --device-auth
            ;;
        claude)
            echo "Starting Claude Code — run /login inside, then open the printed URL on this Mac." >&2
            exec_workspace claude
            ;;
        opencode)
            exec_workspace opencode auth login
            ;;
        gh)
            if [[ -n "${GH_TOKEN:-}" ]]; then
                printf '%s' "$GH_TOKEN" | exec_workspace_no_tty gh auth login --hostname github.com --with-token
            else
                exec_workspace gh auth login --hostname github.com --git-protocol https
            fi
            ;;
        *)
            echo "Unknown agent for login: $agent (expected codex, claude, opencode, or gh)" >&2
            exit 1
            ;;
    esac
}

run_agent() {
    local agent="$1"
    shift || true
    case "$agent" in
        codex)
            exec_workspace codex --dangerously-bypass-approvals-and-sandbox "$@"
            ;;
        claude)
            exec_workspace claude --dangerously-skip-permissions "$@"
            ;;
        opencode)
            exec_workspace opencode "$@"
            ;;
        *)
            echo "Unknown agent: $agent (expected codex, claude, or opencode)" >&2
            exit 1
            ;;
    esac
}

import_database() {
    local source_container="${SOURCE_DB_CONTAINER:-matcha-postgres}"
    local source_database="${SOURCE_DB_NAME:-matcha}"
    local source_user="${SOURCE_DB_USER:-matcha}"
    local confirmed="${1:-}"

    if [[ "$source_container" == *prod* ]]; then
        echo "Refusing to import from a production-shaped container name: $source_container" >&2
        exit 1
    fi
    if ! docker ps --format '{{.Names}}' | grep -Fxq "$source_container"; then
        echo "Source container '$source_container' is not running." >&2
        echo "Start the local development database first, or set SOURCE_DB_CONTAINER." >&2
        exit 1
    fi
    if [[ "$confirmed" != "--yes" ]]; then
        echo "This replaces only the sandbox Postgres volume with '$source_container:$source_database'."
        read -r -p "Type 'import-sandbox-db' to continue: " confirmed
        [[ "$confirmed" == "import-sandbox-db" ]] || { echo "Aborted."; return 0; }
    fi

    "${COMPOSE[@]}" up --detach postgres
    docker exec "$source_container" pg_dump -U "$source_user" --format=custom "$source_database" \
        | "${COMPOSE[@]}" exec --no-TTY postgres sh -ceu '
            dropdb -U "$POSTGRES_USER" --if-exists "$POSTGRES_DB"
            createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
            pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --exit-on-error
        '
    echo "Sandbox database import completed. Host PostgreSQL volumes were not mounted or modified."
}

check() {
    local label="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        printf '  [ok]   %s\n' "$label"
    else
        printf '  [FAIL] %s\n' "$label"
    fi
}

run_doctor() {
    echo "Isolation:"
    check "docker.sock absent" exec_workspace test '!' -e /var/run/docker.sock
    check "host home dirs absent (/Users)" exec_workspace test '!' -d /Users
    check "container runs as configured uid" bash -c "[ \"\$(${COMPOSE[*]} exec --user '${SANDBOX_UID:-501}:${SANDBOX_GID:-20}' -T workspace id -u)\" = \"${SANDBOX_UID:-501}\" ]"
    check "git repository accessible (no dubious-ownership warning)" exec_workspace git -C /workspace status --short

    echo "Prod access:"
    check "ssh to app EC2" exec_workspace ssh -i secrets/roonMT-arm.pem -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new ec2-user@54.177.107.107 true
    check "aws sts get-caller-identity" exec_workspace aws sts get-caller-identity

    echo "Local dev services:"
    check "postgres reachable" exec_workspace pg_isready -h postgres -U matcha -d matcha
    check "redis reachable" exec_workspace redis-cli -h redis ping

    echo "Agent CLIs on PATH:"
    for bin in codex claude opencode gh aws ssh git; do
        check "$bin" exec_workspace which "$bin"
    done
}

command_name="${1:-}"
shift || true

case "$command_name" in
    build)
        require_docker
        if [[ "${1:-}" == "--playwright" ]]; then
            INSTALL_PLAYWRIGHT_BROWSERS=true "${COMPOSE[@]}" build workspace
        else
            "${COMPOSE[@]}" build workspace
        fi
        ;;
    login)
        require_docker
        start_services
        login_agent "${1:?usage: login <codex|claude|opencode|gh>}"
        ;;
    git-login)
        require_docker
        start_services
        login_agent gh
        ;;
    run)
        require_docker
        start_services
        run_agent "$@"
        ;;
    codex|claude|opencode)
        require_docker
        start_services
        run_agent "$command_name" "$@"
        ;;
    start)
        require_docker
        start_services
        ;;
    dev)
        require_docker
        start_services
        exec_workspace env AGENT_SANDBOX=1 ./scripts/dev-remote.sh "$@"
        ;;
    shell)
        require_docker
        start_services
        if [[ $# -gt 0 ]]; then
            # Not a login shell: Debian's /etc/profile resets PATH for login
            # shells, dropping /opt/node/bin (where codex/claude/opencode
            # live) and /usr/local/aws-cli — a plain -c preserves the image's
            # PATH like every other exec_workspace call already does.
            exec_workspace bash -c "$*"
        else
            exec_workspace bash
        fi
        ;;
    status)
        require_docker
        "${COMPOSE[@]}" ps
        echo
        for container_port in "${BACKEND_PORT:-8001}" "${FRONTEND_PORT:-5174}" "${TELLUS_PORT:-5191}" "${OCEANLAB_PORT:-5201}" "${CHAT_PORT:-8080}"; do
            printf 'workspace container port %s -> ' "$container_port"
            "${COMPOSE[@]}" port workspace "$container_port" 2>/dev/null || echo "not published"
        done
        ;;
    doctor)
        require_docker
        start_services
        run_doctor
        ;;
    stop)
        require_docker
        "${COMPOSE[@]}" stop
        ;;
    import-db)
        require_docker
        import_database "${1:-}"
        ;;
    "")
        # Bare `msandbox` — the one-command path: build (no-op if cached),
        # start services, drop into a shell ready to run an agent.
        require_docker
        "${COMPOSE[@]}" build workspace
        start_services
        exec_workspace bash
        ;;
    -h|--help|help)
        usage
        ;;
    *)
        echo "Unknown command: $command_name" >&2
        usage >&2
        exit 1
        ;;
esac
