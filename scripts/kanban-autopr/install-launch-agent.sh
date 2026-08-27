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
DISPATCHER_SOURCE="$SCRIPT_DIR/dispatch-if-idle.sh"
DISPATCHER_DESTINATION="$INSTALL_ROOT/dispatch-if-idle.sh"
PLIST_DESTINATION="$LAUNCH_AGENTS_DIR/$LABEL.plist"

validate_dependencies() {
    [ -x /opt/homebrew/bin/gh ] || { echo "missing /opt/homebrew/bin/gh" >&2; exit 1; }
    command -v jq >/dev/null || { echo "missing jq" >&2; exit 1; }
    [ -x "$LAUNCHCTL_BIN" ] || { echo "missing launchctl: $LAUNCHCTL_BIN" >&2; exit 1; }
    /opt/homebrew/bin/gh auth status >/dev/null
}

install_dispatcher() {
    mkdir -p "$INSTALL_ROOT"
    install -m 755 "$DISPATCHER_SOURCE" "$DISPATCHER_DESTINATION"
}

render_launch_agent() {
    mkdir -p "$LAUNCH_AGENTS_DIR" "$USER_HOME/Library/Logs"
    sed \
        -e "s|__DISPATCHER_PATH__|$DISPATCHER_DESTINATION|g" \
        -e "s|__USER_HOME__|$USER_HOME|g" \
        "$PLIST_TEMPLATE" > "$PLIST_DESTINATION"
    plutil -lint "$PLIST_DESTINATION" >/dev/null
}

bootstrap_launch_agent() {
    local uid domain="gui/$(id -u)"
    "$LAUNCHCTL_BIN" bootout "$domain/$LABEL" >/dev/null 2>&1 || true
    "$LAUNCHCTL_BIN" bootstrap "$domain" "$PLIST_DESTINATION"
    "$LAUNCHCTL_BIN" kickstart -k "$domain/$LABEL"
    "$LAUNCHCTL_BIN" print "$domain/$LABEL"
}

main() {
    validate_dependencies
    install_dispatcher
    render_launch_agent
    bootstrap_launch_agent
    echo "Installed $LABEL; logs: $USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log"
}

main "$@"
