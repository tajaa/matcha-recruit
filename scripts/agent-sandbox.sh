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
AUTOPR_COMPOSE_FILE="$PROJECT_ROOT/docker-compose.autopr-sandbox.yml"
PRIMARY_SANDBOX_PROJECT_NAME="${AGENT_SANDBOX_PRIMARY_PROJECT_NAME:-matcha-agent-sandbox}"
AUTOPR_SANDBOX_PROJECT_NAME="${AUTOPR_SANDBOX_PROJECT_NAME:-matcha-kanban-autopr-sandbox}"
AUTOPR_STATE_DIR="${AUTOPR_STATE_DIR:-$HOME/.local/state/matcha-agent-sandbox}"
AUTOPR_ENABLE_FILE="${AUTOPR_ENABLE_FILE:-$AUTOPR_STATE_DIR/autopr-enabled}"
AUTOPR_INSTALL_ROOT="${AUTOPR_DISPATCH_INSTALL_ROOT:-$HOME/.local/share/matcha-kanban-autopr}"
AUTOPR_LAUNCH_AGENT_PLIST="${AUTOPR_LAUNCH_AGENT_PLIST:-$HOME/Library/LaunchAgents/com.matcha.kanban-autopr-dispatch.plist}"
AUTOPR_LAUNCHCTL_BIN="${AUTOPR_LAUNCHCTL_BIN:-/bin/launchctl}"
AUTOPR_TMUX_BIN="${AUTOPR_TMUX_BIN:-/opt/homebrew/bin/tmux}"
AUTOPR_TMUX_SESSION="${AUTOPR_TMUX_SESSION:-matcha-autopr}"
# The self-hosted GitHub Actions runner LaunchAgent is what actually executes
# the kanban-autopr workflow on this Mac. `msandbox off`/`stop` boots it out so
# a stray workflow_dispatch has nowhere to land (not just a gated no-op);
# `msandbox start` bootstraps it back. Set AUTOPR_MANAGE_RUNNER=0 if the runner
# is administered separately (e.g. as a launchd system service via svc.sh).
AUTOPR_MANAGE_RUNNER="${AUTOPR_MANAGE_RUNNER:-1}"
AUTOPR_RUNNER_LAUNCH_LABEL="${AUTOPR_RUNNER_LAUNCH_LABEL:-com.matcha.github-actions-runner}"
AUTOPR_RUNNER_LAUNCH_AGENT_PLIST="${AUTOPR_RUNNER_LAUNCH_AGENT_PLIST:-$HOME/Library/LaunchAgents/com.matcha.github-actions-runner.plist}"
AUTOPR_GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
AUTOPR_REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
AUTOPR_WORKFLOW="${AUTOPR_WORKFLOW:-kanban-autopr.yml}"
PRIMARY_COMPOSE=(docker compose --project-name "$PRIMARY_SANDBOX_PROJECT_NAME" --file "$COMPOSE_FILE")
# Callers that need a separate trust boundary (Kanban AutoPR, for example)
# get their own container and named volumes without duplicating this launcher.
# The workspace and AWS mounts are explicit inputs so a trusted host wrapper
# can mount a sanitized clone and an empty credentials directory.
SANDBOX_PROJECT_NAME="${AGENT_SANDBOX_PROJECT_NAME:-matcha-agent-sandbox}"
export SANDBOX_WORKSPACE_DIR="${SANDBOX_WORKSPACE_DIR:-$PROJECT_ROOT}"
export SANDBOX_AWS_DIR="${SANDBOX_AWS_DIR:-$HOME/.aws}"
COMPOSE=(docker compose --project-name "$SANDBOX_PROJECT_NAME" --file "$COMPOSE_FILE")

configure_autopr_lane() {
    local bootstrap_root="${AUTOPR_SANDBOX_BOOTSTRAP_ROOT:-$PROJECT_ROOT/.git/matcha-autopr-sandbox/bootstrap}"
    SANDBOX_PROJECT_NAME="${AUTOPR_SANDBOX_PROJECT_NAME:-matcha-kanban-autopr-sandbox}"
    export SANDBOX_WORKSPACE_DIR="${SANDBOX_WORKSPACE_DIR:-$bootstrap_root/workspace}"
    export SANDBOX_AWS_DIR="${SANDBOX_AWS_DIR:-$bootstrap_root/empty-aws}"
    mkdir -p "$SANDBOX_WORKSPACE_DIR" "$SANDBOX_AWS_DIR"
    # The trusted bridge stages exactly one mode-600 OpenCode auth.json before
    # setting this flag. Keep it out of ordinary interactive msandbox runs.
    [ -n "${SANDBOX_OPENCODE_AUTH_FILE:-}" ] || {
        echo "AutoPR sandbox requires SANDBOX_OPENCODE_AUTH_FILE from its trusted bridge." >&2
        exit 1
    }
    [ -r "$SANDBOX_OPENCODE_AUTH_FILE" ] || {
        echo "AutoPR OpenCode auth file is not readable: $SANDBOX_OPENCODE_AUTH_FILE" >&2
        exit 1
    }
    COMPOSE=(docker compose --project-name "$SANDBOX_PROJECT_NAME" --file "$COMPOSE_FILE" --file "$AUTOPR_COMPOSE_FILE")
}

usage() {
    cat <<'EOF'
Usage: msandbox [command] [args]   (or ./scripts/agent-sandbox.sh [command] [args])

Bare `msandbox` (no command) builds if needed, starts services, and drops you
into a shell in the workspace — the one-command way in.

Commands:
  build [--playwright]        Build the isolated workspace image.
  start                       Start workspace + dev services; load the AutoPR timer and self-hosted runner.
  stop [--force]              Stop everything (incl. the self-hosted runner); refuse active agent work unless forced.
  off                         Immediately stop everything (incl. the self-hosted runner and active agent work).
  status                      Show sandbox service, AutoPR master-switch, and runner status.
  workspace-state             Print this sandbox project's container runtime state.
  autopr-ready                Exit 0 only when the complete AutoPR system is healthy.
  shell [cmd...]               Open a workspace shell (or run one command).
  exec <cmd> [args...]         Run one non-interactive command with exact argv.
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
    # The dedicated AutoPR lane may start only while the primary msandbox is
    # explicitly enabled. Check both before and after `up` so `msandbox stop`
    # wins a concurrent start and no autonomous container survives the switch.
    if [ "${AGENT_SANDBOX_AUTOPR:-0}" = 1 ]; then
        require_autopr_system
    fi
    if [ "${AGENT_SANDBOX_SKIP_HOST_SERVICES:-0}" != 1 ]; then
        ensure_host_dev_services
    fi
    "${COMPOSE[@]}" up --detach workspace
    if [ "${AGENT_SANDBOX_AUTOPR:-0}" = 1 ] && ! autopr_system_ready; then
        "${COMPOSE[@]}" stop workspace >/dev/null 2>&1 || true
        echo "AutoPR refused to start because the primary msandbox was switched off." >&2
        return 1
    fi
}

primary_workspace_running() {
    local container_ids
    container_ids="$("${PRIMARY_COMPOSE[@]}" ps --status running --quiet workspace 2>/dev/null)" \
        || return 1
    [ -n "$container_ids" ]
}

autopr_master_ready() {
    [ -f "$AUTOPR_ENABLE_FILE" ] && primary_workspace_running
}

autopr_dashboard_healthy() {
    local pane_states pane_count
    [ -x "$AUTOPR_TMUX_BIN" ] || return 1
    "$AUTOPR_TMUX_BIN" has-session -t "$AUTOPR_TMUX_SESSION" 2>/dev/null || return 1
    pane_states="$("$AUTOPR_TMUX_BIN" list-panes -t "$AUTOPR_TMUX_SESSION" \
        -F '#{pane_dead}' 2>/dev/null)" || return 1
    pane_count="$(printf '%s\n' "$pane_states" | awk 'NF {count++} END {print count+0}')"
    [ "$pane_count" = 4 ] && ! printf '%s\n' "$pane_states" | grep -q '^1$'
}

autopr_timer_loaded() {
    local domain="gui/$(id -u)" label="com.matcha.kanban-autopr-dispatch"
    [ -x "$AUTOPR_LAUNCHCTL_BIN" ] \
        && "$AUTOPR_LAUNCHCTL_BIN" print "$domain/$label" >/dev/null 2>&1
}

autopr_runner_loaded() {
    local domain="gui/$(id -u)"
    [ -x "$AUTOPR_LAUNCHCTL_BIN" ] \
        && "$AUTOPR_LAUNCHCTL_BIN" print "$domain/$AUTOPR_RUNNER_LAUNCH_LABEL" >/dev/null 2>&1
}

start_actions_runner() {
    [ "$AUTOPR_MANAGE_RUNNER" = 1 ] || return 0
    [ -x "$AUTOPR_LAUNCHCTL_BIN" ] || return 0
    local domain="gui/$(id -u)"
    if [ ! -f "$AUTOPR_RUNNER_LAUNCH_AGENT_PLIST" ]; then
        echo "AutoPR note: runner LaunchAgent plist not found at $AUTOPR_RUNNER_LAUNCH_AGENT_PLIST; leaving the self-hosted runner as-is." >&2
        return 0
    fi
    "$AUTOPR_LAUNCHCTL_BIN" print "$domain/$AUTOPR_RUNNER_LAUNCH_LABEL" >/dev/null 2>&1 \
        || "$AUTOPR_LAUNCHCTL_BIN" bootstrap "$domain" "$AUTOPR_RUNNER_LAUNCH_AGENT_PLIST" >/dev/null 2>&1 || true
    "$AUTOPR_LAUNCHCTL_BIN" kickstart "$domain/$AUTOPR_RUNNER_LAUNCH_LABEL" >/dev/null 2>&1 || true
    autopr_runner_loaded \
        || echo "AutoPR note: the self-hosted runner LaunchAgent did not load; the kanban-autopr workflow will queue until it is back." >&2
}

stop_actions_runner() {
    [ "$AUTOPR_MANAGE_RUNNER" = 1 ] || return 0
    [ -x "$AUTOPR_LAUNCHCTL_BIN" ] || return 0
    local domain="gui/$(id -u)"
    "$AUTOPR_LAUNCHCTL_BIN" bootout "$domain/$AUTOPR_RUNNER_LAUNCH_LABEL" >/dev/null 2>&1 || true
}

autopr_system_ready() {
    autopr_master_ready && autopr_timer_loaded && autopr_dashboard_healthy
}

container_has_agent_process() {
    local project="$1" container_id process_rows
    container_id="$(docker compose --project-name "$project" --file "$COMPOSE_FILE" \
        ps --quiet workspace 2>/dev/null)" || return 1
    [ -n "$container_id" ] || return 1
    process_rows="$(docker exec "$container_id" ps -eo comm=,args= 2>/dev/null)" || return 1
    printf '%s\n' "$process_rows" | awk '
      $1 ~ /^(codex|opencode|claude)$/ {found=1}
      $0 ~ /\/(codex|opencode|claude)([[:space:]]|$)/ {found=1}
      END {exit !found}
    '
}

workspace_state() {
    local container_id state
    container_id="$("${COMPOSE[@]}" ps --all --quiet workspace 2>/dev/null)" \
        || return 1
    if [ -z "$container_id" ]; then
        printf 'absent\n'
        return 0
    fi
    state="$(docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null)" \
        || return 1
    printf '%s\n' "$state"
}

detect_agentic_activity() {
    AGENTIC_ACTIVITY_STATE=idle
    AGENTIC_ACTIVITY_DETAIL="no Codex, OpenCode, Claude, or queued/running AutoPR work"
    if [ "${AGENT_SANDBOX_SKIP_ACTIVITY_CHECK:-0}" = 1 ]; then
        return 0
    fi

    local primary_agent=0 autopr_agent=0 found_local=0 runs=""
    container_has_agent_process "$PRIMARY_SANDBOX_PROJECT_NAME" && primary_agent=1
    container_has_agent_process "$AUTOPR_SANDBOX_PROJECT_NAME" && autopr_agent=1
    if [ "$primary_agent" = 1 ] || [ "$autopr_agent" = 1 ]; then found_local=1; fi

    if [ -x "$AUTOPR_GH_BIN" ] && command -v jq >/dev/null \
        && runs="$("$AUTOPR_GH_BIN" run list --repo "$AUTOPR_REPO" \
            --workflow "$AUTOPR_WORKFLOW" --branch main --limit 20 \
            --json databaseId,status,url 2>/dev/null)"; then
        if printf '%s' "$runs" | jq -e \
            'any(.[]; .status | IN("queued", "in_progress", "requested", "waiting", "pending"))' \
            >/dev/null; then
            AGENTIC_ACTIVITY_STATE=active
            AGENTIC_ACTIVITY_DETAIL="an AutoPR workflow is queued or running"
            return 0
        fi
    else
        if [ "$found_local" = 1 ]; then
            AGENTIC_ACTIVITY_STATE=active
            if [ "$primary_agent" = 1 ] && [ "$autopr_agent" = 1 ]; then
                AGENTIC_ACTIVITY_DETAIL="coding agents are running in both sandboxes"
            elif [ "$autopr_agent" = 1 ]; then
                AGENTIC_ACTIVITY_DETAIL="an AutoPR coding agent is running"
            else
                AGENTIC_ACTIVITY_DETAIL="a coding agent is running in the primary sandbox"
            fi
        else
            AGENTIC_ACTIVITY_STATE=unknown
            AGENTIC_ACTIVITY_DETAIL="GitHub activity could not be verified"
        fi
        return 0
    fi

    if [ "$found_local" = 1 ]; then
        AGENTIC_ACTIVITY_STATE=active
        if [ "$primary_agent" = 1 ] && [ "$autopr_agent" = 1 ]; then
            AGENTIC_ACTIVITY_DETAIL="coding agents are running in both sandboxes"
        elif [ "$autopr_agent" = 1 ]; then
            AGENTIC_ACTIVITY_DETAIL="an AutoPR coding agent is running"
        else
            AGENTIC_ACTIVITY_DETAIL="a coding agent is running in the primary sandbox"
        fi
    fi
}

print_system_status() {
    local heading="${1:-MSANDBOX SYSTEM STATUS}"
    detect_agentic_activity
    printf '\n%s\n' "$heading"
    if primary_workspace_running; then
        printf '  Primary sandbox: RUNNING\n'
    else
        printf '  Primary sandbox: STOPPED\n'
    fi
    if autopr_master_ready; then
        printf '  AutoPR master:   ON\n'
    else
        printf '  AutoPR master:   OFF\n'
    fi
    if autopr_timer_loaded; then
        printf '  AutoPR timer:    LOADED\n'
    else
        printf '  AutoPR timer:    STOPPED\n'
    fi
    if [ "$AUTOPR_MANAGE_RUNNER" = 1 ]; then
        if autopr_runner_loaded; then
            printf '  Actions runner:  LOADED\n'
        else
            printf '  Actions runner:  STOPPED\n'
        fi
    fi
    if autopr_dashboard_healthy; then
        printf '  Dashboard:       READY (4 live panes)\n'
    elif "$AUTOPR_TMUX_BIN" has-session -t "$AUTOPR_TMUX_SESSION" 2>/dev/null; then
        printf '  Dashboard:       BROKEN (dead or missing pane)\n'
    else
        printf '  Dashboard:       STOPPED\n'
    fi
    printf '  Agentic work:    %s — %s\n\n' \
        "$(printf '%s' "$AGENTIC_ACTIVITY_STATE" | tr '[:lower:]' '[:upper:]')" \
        "$AGENTIC_ACTIVITY_DETAIL"
}

guard_interactive_entry() {
    local operation="$1"
    print_system_status "MSANDBOX PREFLIGHT"
    if [ "$AGENTIC_ACTIVITY_STATE" = active ] \
        || [ "$AGENTIC_ACTIVITY_STATE" = unknown ]; then
        echo "Refusing to $operation: $AGENTIC_ACTIVITY_DETAIL." >&2
        echo "Existing work and system state were left untouched." >&2
        return 1
    fi
    return 0
}

require_autopr_master() {
    autopr_master_ready || {
        echo "AutoPR is off. Start the primary sandbox with: msandbox start" >&2
        return 1
    }
}

require_autopr_system() {
    autopr_system_ready || {
        echo "AutoPR is not fully healthy; refusing autonomous model startup." >&2
        return 1
    }
}

enable_autopr_control_plane() {
    [ "${AGENT_SANDBOX_AUTOPR:-0}" != 1 ] || return 0

    mkdir -p "$AUTOPR_STATE_DIR"
    chmod 700 "$AUTOPR_STATE_DIR"
    (umask 077; : > "$AUTOPR_ENABLE_FILE")

    local dashboard_ensure="$AUTOPR_INSTALL_ROOT/ensure-dashboard.sh"
    [ -x "$dashboard_ensure" ] || dashboard_ensure="$PROJECT_ROOT/scripts/kanban-autopr/ensure-dashboard.sh"
    if [ ! -x "$dashboard_ensure" ]; then
        echo "AutoPR startup failed: dashboard helper is not installed." >&2
        disable_autopr_control_plane
        return 1
    fi
    if ! "$dashboard_ensure" >/dev/null; then
        echo "AutoPR startup failed: dashboard creation failed." >&2
        disable_autopr_control_plane
        return 1
    fi
    if ! autopr_dashboard_healthy; then
        echo "AutoPR startup failed: dashboard does not have four live panes." >&2
        disable_autopr_control_plane
        return 1
    fi

    local domain="gui/$(id -u)" label="com.matcha.kanban-autopr-dispatch"
    if [ ! -x "$AUTOPR_LAUNCHCTL_BIN" ] || [ ! -f "$AUTOPR_LAUNCH_AGENT_PLIST" ]; then
        echo "AutoPR startup failed: timer is not installed; run scripts/kanban-autopr/install-launch-agent.sh." >&2
        disable_autopr_control_plane
        return 1
    fi
    if ! "$AUTOPR_LAUNCHCTL_BIN" print "$domain/$label" >/dev/null 2>&1 \
        && ! "$AUTOPR_LAUNCHCTL_BIN" bootstrap "$domain" "$AUTOPR_LAUNCH_AGENT_PLIST"; then
        echo "AutoPR startup failed: LaunchAgent could not be loaded." >&2
        disable_autopr_control_plane
        return 1
    fi
    if ! "$AUTOPR_LAUNCHCTL_BIN" kickstart -k "$domain/$label"; then
        echo "AutoPR startup failed: LaunchAgent could not be started." >&2
        disable_autopr_control_plane
        return 1
    fi
    if ! autopr_timer_loaded; then
        echo "AutoPR startup failed: LaunchAgent did not remain loaded." >&2
        disable_autopr_control_plane
        return 1
    fi

    # Best-effort: `msandbox off`/`stop` booted the self-hosted runner out, so
    # bring it back. A separately administered runner (AUTOPR_MANAGE_RUNNER=0)
    # or a missing plist only warns — it does not fail the master switch, which
    # the dispatcher/workflow/model launcher gate on independently.
    start_actions_runner

    echo "AutoPR enabled; dashboard: tmux attach -t $AUTOPR_TMUX_SESSION"
}

disable_autopr_control_plane() {
    # Remove the authoritative gate first. Even if launchctl or Docker fails,
    # the installed dispatcher and workflow/model entrypoints now fail closed.
    rm -f -- "$AUTOPR_ENABLE_FILE"

    local domain="gui/$(id -u)" label="com.matcha.kanban-autopr-dispatch"
    if [ -x "$AUTOPR_LAUNCHCTL_BIN" ]; then
        "$AUTOPR_LAUNCHCTL_BIN" bootout "$domain/$label" >/dev/null 2>&1 || true
    fi
    if [ -x "$AUTOPR_TMUX_BIN" ] \
        && "$AUTOPR_TMUX_BIN" has-session -t "$AUTOPR_TMUX_SESSION" 2>/dev/null; then
        "$AUTOPR_TMUX_BIN" kill-session -t "$AUTOPR_TMUX_SESSION" || true
    fi
}

stop_autopr_container() {
    docker compose --project-name "$AUTOPR_SANDBOX_PROJECT_NAME" \
        --file "$COMPOSE_FILE" stop workspace >/dev/null 2>&1 || true
}

shutdown_all_sandboxes() {
    disable_autopr_control_plane
    stop_actions_runner
    if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
        stop_autopr_container
        "${PRIMARY_COMPOSE[@]}" stop workspace
    fi
    print_system_status "MSANDBOX STOPPED"
}

start_primary_and_enable_autopr() {
    local primary_was_running=0
    primary_workspace_running && primary_was_running=1
    start_services
    if ! enable_autopr_control_plane; then
        if [ "$primary_was_running" = 0 ]; then
            "${PRIMARY_COMPOSE[@]}" stop workspace >/dev/null 2>&1 || true
            echo "MSANDBOX STARTUP FAILED — all newly started systems are shut down." >&2
        else
            echo "MSANDBOX STARTUP FAILED — the pre-existing primary sandbox was left untouched." >&2
        fi
        return 1
    fi
    print_system_status "MSANDBOX STARTED"
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
    check "DATABASE_URL targets host gateway" exec_workspace bash -c 'case "${DATABASE_URL:-}" in postgresql://matcha:*@host.docker.internal:*/matcha) exit 0;; *) exit 1;; esac'
    check "REDIS_URL targets host gateway" exec_workspace bash -c 'case "${REDIS_URL:-}" in redis://host.docker.internal:*/0) exit 0;; *) exit 1;; esac'
    check "matcha-postgres reachable" exec_workspace pg_isready -h host.docker.internal -p "$HOST_DB_PORT" -U matcha -d matcha
    check "matcha-redis reachable" exec_workspace redis-cli -h host.docker.internal -p "$HOST_REDIS_PORT" ping

    echo "Agent CLIs on PATH:"
    for bin in codex claude opencode gh aws ssh git; do
        check "$bin" exec_workspace which "$bin"
    done
}

command_name="${1:-}"
shift || true

# This flag is set exclusively by run-opencode-sandboxed.sh.  Configure the
# dedicated compose overlay before any lifecycle command so stop/start/exec
# all refer to the same contained AutoPR lane.
if [ "${AGENT_SANDBOX_AUTOPR:-0}" = 1 ]; then
    configure_autopr_lane
fi

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
        start_primary_and_enable_autopr
        login_agent "${1:?usage: login <codex|claude|opencode|gh>}"
        ;;
    git-login)
        require_docker
        start_primary_and_enable_autopr
        login_agent gh
        ;;
    run)
        require_docker
        if [ "${AGENT_SANDBOX_AUTOPR:-0}" = 1 ]; then
            start_services
        else
            guard_interactive_entry "start another coding agent" || exit 3
            start_primary_and_enable_autopr
        fi
        run_agent "$@"
        ;;
    codex|claude|opencode)
        require_docker
        guard_interactive_entry "start another coding agent" || exit 3
        start_primary_and_enable_autopr
        run_agent "$command_name" "$@"
        ;;
    start)
        require_docker
        if [ "${AGENT_SANDBOX_AUTOPR:-0}" = 1 ]; then start_services; else start_primary_and_enable_autopr; fi
        ;;
    dev)
        require_docker
        start_primary_and_enable_autopr
        exec_workspace env AGENT_SANDBOX=1 ./scripts/dev-remote.sh "$@"
        ;;
    shell)
        require_docker
        guard_interactive_entry "open another sandbox shell" || exit 3
        start_primary_and_enable_autopr
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
    exec)
        require_docker
        [[ $# -gt 0 ]] || { echo "usage: msandbox exec <cmd> [args...]" >&2; exit 1; }
        if [ "${AGENT_SANDBOX_AUTOPR:-0}" = 1 ]; then start_services; else start_primary_and_enable_autopr; fi
        # This path is intended for automation. Keep argv boundaries intact
        # and disable TTY allocation so prompts/files never pass through a
        # shell string or fail on a headless GitHub Actions runner.
        exec_workspace_no_tty "$@"
        ;;
    status)
        require_docker
        "${COMPOSE[@]}" ps
        echo
        for container_port in "${BACKEND_PORT:-8001}" "${FRONTEND_PORT:-5174}" "${TELLUS_PORT:-5191}" "${OCEANLAB_PORT:-5201}" "${CHAT_PORT:-8080}"; do
            printf 'workspace container port %s -> ' "$container_port"
            "${COMPOSE[@]}" port workspace "$container_port" 2>/dev/null || echo "not published"
        done
        print_system_status "MSANDBOX CURRENT STATE"
        ;;
    workspace-state)
        require_docker
        workspace_state
        ;;
    autopr-ready)
        require_docker
        autopr_system_ready
        ;;
    autopr-master-ready)
        require_docker
        autopr_master_ready
        ;;
    doctor)
        require_docker
        start_primary_and_enable_autopr
        run_doctor
        ;;
    stop)
        if [ "${AGENT_SANDBOX_AUTOPR:-0}" = 1 ]; then
            require_docker
            "${COMPOSE[@]}" stop workspace
        else
            force_stop=0
            if [ "${1:-}" = --force ]; then
                force_stop=1
                shift
            fi
            [ "$#" = 0 ] || { echo "usage: msandbox stop [--force]" >&2; exit 2; }
            detect_agentic_activity
            if [ "$force_stop" = 0 ] \
                && { [ "$AGENTIC_ACTIVITY_STATE" = active ] \
                    || [ "$AGENTIC_ACTIVITY_STATE" = unknown ]; }; then
                print_system_status "MSANDBOX SHUTDOWN BLOCKED"
                echo "Refusing to stop: $AGENTIC_ACTIVITY_DETAIL." >&2
                echo "Wait for the work to finish, or explicitly override with: msandbox stop --force" >&2
                exit 3
            fi
            shutdown_all_sandboxes
        fi
        ;;
    off)
        [ "$#" = 0 ] || { echo "usage: msandbox off" >&2; exit 2; }
        shutdown_all_sandboxes
        ;;
    "")
        # Bare `msandbox` — the one-command path: build (no-op if cached),
        # start services, drop into a shell ready to run an agent.
        require_docker
        guard_interactive_entry "open another sandbox shell" || exit 3
        "${COMPOSE[@]}" build workspace
        start_primary_and_enable_autopr
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
