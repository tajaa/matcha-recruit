#!/usr/bin/env bash
# Run the Codex CLI in the repository's isolated Docker development sandbox.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/docker-compose.codex.yml"
COMPOSE=(docker compose --project-name matcha-codex-sandbox --file "$COMPOSE_FILE")

usage() {
    cat <<'EOF'
Usage: ./scripts/codex-sandbox.sh <command> [args]

Commands:
  build       Build the isolated workspace image.
  login       Authenticate Codex in the dedicated Codex-state volume.
  git-login   Authenticate GitHub in the dedicated GitHub-config volume.
  start       Start workspace, PostgreSQL, and Redis.
  dev         Run scripts/dev-remote.sh inside the workspace container.
  codex       Start Codex with full execution inside the container boundary.
  shell       Open a normal workspace shell.
  status      Show sandbox service status and published localhost ports.
  stop        Stop sandbox services without deleting their volumes.
  import-db   Replace sandbox PostgreSQL with a dump of local matcha-postgres.

Set INSTALL_PLAYWRIGHT_BROWSERS=true before `build` to include an isolated
Chromium binary for Playwright. `import-db --yes` skips its confirmation prompt.
EOF
}

require_docker() {
    command -v docker >/dev/null || {
        echo "docker is required for the Codex sandbox." >&2
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
    "${COMPOSE[@]}" exec workspace "$@"
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

command_name="${1:-}"
shift || true

case "$command_name" in
    build)
        require_docker
        "${COMPOSE[@]}" build workspace
        ;;
    login)
        require_docker
        start_services
        exec_workspace codex login --device-auth
        ;;
    git-login)
        require_docker
        start_services
        if [[ -n "${GH_TOKEN:-}" ]]; then
            printf '%s' "$GH_TOKEN" | "${COMPOSE[@]}" exec --no-TTY workspace gh auth login --hostname github.com --with-token
        else
            exec_workspace gh auth login --hostname github.com --git-protocol https
        fi
        ;;
    start)
        require_docker
        start_services
        ;;
    dev)
        require_docker
        start_services
        exec_workspace env CODEX_SANDBOX=1 ./scripts/dev-remote.sh "$@"
        ;;
    codex)
        require_docker
        start_services
        exec_workspace codex --dangerously-bypass-approvals-and-sandbox "$@"
        ;;
    shell)
        require_docker
        start_services
        exec_workspace bash
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
    stop)
        require_docker
        "${COMPOSE[@]}" stop
        ;;
    import-db)
        require_docker
        import_database "${1:-}"
        ;;
    -h|--help|help|"")
        usage
        ;;
    *)
        echo "Unknown command: $command_name" >&2
        usage >&2
        exit 1
        ;;
esac
