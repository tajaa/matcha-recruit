#!/usr/bin/env bash
# Install the local five-minute dispatcher without embedding credentials in
# launchd. The workflow itself still owns OpenCode, board, and production use.
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
    # Recreate this one named observer session so an idempotent reinstall also
    # picks up newer pane scripts copied above.
    "$INSTALL_ROOT/ensure-dashboard.sh" --restart
    start_launch_agent
    echo "Installed $LABEL; logs: $USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log"
    echo "Open dashboard: tmux attach -t matcha-autopr"
}

main "$@"
