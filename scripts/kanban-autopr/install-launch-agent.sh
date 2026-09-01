#!/usr/bin/env bash
# Install the local one-minute dispatcher without embedding credentials in
# launchd. The workflow itself still owns Codex, board, and production use.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.matcha.kanban-autopr-dispatch"
USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
INSTALL_ROOT="${AUTOPR_DISPATCH_INSTALL_ROOT:-$USER_HOME/.local/share/matcha-kanban-autopr}"
LAUNCH_AGENTS_DIR="${AUTOPR_LAUNCH_AGENTS_DIR:-$USER_HOME/Library/LaunchAgents}"
LAUNCHCTL_BIN="${AUTOPR_LAUNCHCTL_BIN:-/bin/launchctl}"
PLIST_TEMPLATE="$SCRIPT_DIR/launchd/$LABEL.plist.in"
DISPATCHER_DESTINATION="$INSTALL_ROOT/dispatch-if-idle.sh"
PLIST_DESTINATION="$LAUNCH_AGENTS_DIR/$LABEL.plist"
TMUX_BIN="${AUTOPR_TMUX_BIN:-/opt/homebrew/bin/tmux}"
ENABLE_FILE="${AUTOPR_ENABLE_FILE:-$USER_HOME/.local/state/matcha-agent-sandbox/autopr-enabled}"

validate_dependencies() {
    [ -x /opt/homebrew/bin/gh ] || { echo "missing /opt/homebrew/bin/gh" >&2; exit 1; }
    command -v jq >/dev/null || { echo "missing jq" >&2; exit 1; }
    [ -x "$TMUX_BIN" ] || { echo "missing tmux: $TMUX_BIN" >&2; exit 1; }
    [ -x "$LAUNCHCTL_BIN" ] || { echo "missing launchctl: $LAUNCHCTL_BIN" >&2; exit 1; }
    [ -x "$USER_HOME/.local/bin/msandbox" ] \
        || { echo "missing $USER_HOME/.local/bin/msandbox" >&2; exit 1; }
    /opt/homebrew/bin/gh auth status >/dev/null
}

install_runtime() {
    mkdir -p "$INSTALL_ROOT"
    local name
    for name in dispatch-if-idle.sh ensure-dashboard.sh dashboard.sh watch-work.sh watch-health.sh watch-pr.sh collect.sh select.sh; do
        install -m 755 "$SCRIPT_DIR/$name" "$INSTALL_ROOT/$name"
    done
    install -m 644 "$SCRIPT_DIR/lib.sh" "$INSTALL_ROOT/lib.sh"
}

render_launch_agent() {
    mkdir -p "$LAUNCH_AGENTS_DIR" "$USER_HOME/Library/Logs"
    sed \
        -e "s|__DISPATCHER_PATH__|$DISPATCHER_DESTINATION|g" \
        -e "s|__USER_HOME__|$USER_HOME|g" \
        "$PLIST_TEMPLATE" > "$PLIST_DESTINATION"
    plutil -lint "$PLIST_DESTINATION" >/dev/null
}

stop_launch_agent() {
    local domain="gui/$(id -u)"
    # Stop the old timer before replacing its dashboard. Bootstrap happens
    # only after the new session is ready; RunAtLoad can otherwise race the
    # installer's own `--restart` and both processes call tmux new-session.
    "$LAUNCHCTL_BIN" bootout "$domain/$LABEL" >/dev/null 2>&1 || true
}

start_launch_agent() {
    local domain="gui/$(id -u)"
    "$LAUNCHCTL_BIN" bootstrap "$domain" "$PLIST_DESTINATION"
    "$LAUNCHCTL_BIN" kickstart -k "$domain/$LABEL"
    "$LAUNCHCTL_BIN" print "$domain/$LABEL"
}

main() {
    validate_dependencies
    install_runtime
    render_launch_agent
    stop_launch_agent
    # stop_launch_agent intentionally makes the *complete* health check false.
    # Preserve authorization based on the master switch alone, then recreate
    # the dashboard and timer below. Checking autopr-ready here created a
    # circular dependency that turned every enabled reinstall into OFF state.
    if [ -f "$ENABLE_FILE" ] \
        && "$USER_HOME/.local/bin/msandbox" autopr-master-ready >/dev/null 2>&1; then
        # Preserve an already-on master switch across an idempotent reinstall
        # while ensuring the tmux panes use the freshly copied scripts.
        "$INSTALL_ROOT/ensure-dashboard.sh" --restart
        start_launch_agent
        echo "Installed and enabled $LABEL; logs: $USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log"
        echo "Open dashboard: tmux attach -t matcha-autopr"
    else
        # Installation is not authorization to start autonomous work. The
        # primary `msandbox start` command owns that transition.
        if "$TMUX_BIN" has-session -t matcha-autopr 2>/dev/null; then
            "$TMUX_BIN" kill-session -t matcha-autopr
        fi
        echo "Installed $LABEL in the OFF state. Run: msandbox start"
    fi
}

main "$@"
