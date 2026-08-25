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
  start                       Start workspace and the normal local dev services.
  stop                        Stop sandbox services without deleting their volumes.
  status                      Show sandbox service status and published localhost ports.
  shell [cmd...]               Open a workspace shell (or run one command).
  dev [args]                   Run scripts/dev-remote.sh inside the workspace container.
  doctor                       Check the isolation + capability checklist.
  login <codex|claude|opencode|gh>   Authenticate one agent (or GitHub) in its own state volume.
  run <codex|claude|opencode> [args] Start that agent with full execution inside the container boundary.
  codex [args]                       Shorthand for `run codex`.
  claude [args]                      Shorthand for `run claude`.
  opencode [args]                    Shorthand for `run opencode`.
  git-login                          Alias for `login gh`.

Set INSTALL_PLAYWRIGHT_BROWSERS=true (or `build --playwright`) to include an
isolated Chromium binary for Playwright. Set SANDBOX_UID/SANDBOX_GID to change
the in-container user (defaults to your macOS uid/gid so file ownership matches
on both sides).
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

host_published_port() {
    local container_name=$1
    local container_port=$2
    local published_port

    published_port="$(docker port "$container_name" "$container_port" 2>/dev/null | head -n 1 | awk -F: '{print $NF}')"
    [[ -n "$published_port" ]] || {
        echo "Could not determine $container_name's published $container_port port." >&2
        return 1
    }
    printf '%s\n' "$published_port"
}

ensure_host_dev_services() {
    # The host-side launcher owns matcha-postgres/matcha-redis lifecycle. Run
    # only its service bootstrap mode here; agents still receive no Docker
    # socket and reach the services through Docker Desktop's host gateway.
    AGENT_SANDBOX= CODEX_SANDBOX= "$PROJECT_ROOT/scripts/dev-remote.sh" services
    HOST_DB_PORT="$(host_published_port matcha-postgres 5432/tcp)"
    HOST_REDIS_PORT="$(host_published_port matcha-redis 6379/tcp)"
    export HOST_DB_PORT HOST_REDIS_PORT
}

start_services() {
    ensure_host_dev_services
    "${COMPOSE[@]}" up --detach workspace
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

    echo "Host local dev services:"
    check "matcha-postgres reachable" exec_workspace pg_isready -h host.docker.internal -p "$HOST_DB_PORT" -U matcha -d matcha
    check "matcha-redis reachable" exec_workspace redis-cli -h host.docker.internal -p "$HOST_REDIS_PORT" ping

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
