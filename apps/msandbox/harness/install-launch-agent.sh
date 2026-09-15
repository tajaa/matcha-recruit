#!/usr/bin/env bash
# Install the local dispatcher without embedding credentials in launchd. Two
# agents share one script: the one-minute scheduler (which holds the Kanban
# lane to one pass per AUTOPR_KANBAN_MAX_AGE_SECONDS, default five minutes
# measured from the last run's completion) and a one-minute watcher that
# dispatches immediately when a card asks for a run. The workflow itself still
# owns Codex, board, and production use.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL="com.matcha.kanban-autopr-dispatch"
WATCH_LABEL="com.matcha.kanban-autopr-request-watch"
USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
INSTALL_ROOT="${AUTOPR_DISPATCH_INSTALL_ROOT:-$USER_HOME/.local/share/matcha-kanban-autopr}"
LAUNCH_AGENTS_DIR="${AUTOPR_LAUNCH_AGENTS_DIR:-$USER_HOME/Library/LaunchAgents}"
LAUNCHCTL_BIN="${AUTOPR_LAUNCHCTL_BIN:-/bin/launchctl}"
PLIST_TEMPLATE="$SCRIPT_DIR/launchd/$LABEL.plist.in"
WATCH_PLIST_TEMPLATE="$SCRIPT_DIR/launchd/$WATCH_LABEL.plist.in"
DISPATCHER_DESTINATION="$INSTALL_ROOT/dispatch-if-idle.sh"
PLIST_DESTINATION="$LAUNCH_AGENTS_DIR/$LABEL.plist"
WATCH_PLIST_DESTINATION="$LAUNCH_AGENTS_DIR/$WATCH_LABEL.plist"
TMUX_BIN="${AUTOPR_TMUX_BIN:-/opt/homebrew/bin/tmux}"
ENABLE_FILE="${AUTOPR_ENABLE_FILE:-$USER_HOME/.local/state/matcha-agent-sandbox/autopr-enabled}"

# --runtime-if-stale: refresh only the copied scripts, only when one differs
# from this checkout; never touches the plists, launchctl, or the dashboard.
# The kanban workflow runs it from its `main` checkout on every pass, so a
# merged harness fix reaches the LaunchAgents within one pass instead of
# waiting for someone to remember `msandbox install` (three times in the
# week of 2026-09-08 a merged fix sat uninstalled for days — a dead-login
# guard among them).
RUNTIME_ONLY=false
case "${1:-}" in
    --runtime-if-stale) RUNTIME_ONLY=true ;;
    '') ;;
    *) echo "usage: install-launch-agent.sh [--runtime-if-stale]" >&2; exit 2 ;;
esac

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
    for name in dispatch-if-idle.sh ensure-dashboard.sh dashboard.sh watch-work.sh watch-health.sh watch-pr.sh collect.sh collect-pr-context.sh select.sh run-snapshot.sh has-run-request.sh gh-cached.sh codex-backoff.sh status-segment.sh card-control.sh queue-handoff.sh; do
        install -m 755 "$SCRIPT_DIR/$name" "$INSTALL_ROOT/$name"
    done
    # Helpers the installed scripts shell out to by $SCRIPT_DIR path. Missing
    # ones fail quietly at runtime: dashboard.sh falls back to its last cached
    # bot-PR answer (so the PR pane freezes and the plan renders "unavailable"),
    # and collect.sh silently stops flagging reconsideration-pending cards.
    # apps/msandbox/tests/test_kanban_autopr_dispatch.sh enforces that every
    # $SCRIPT_DIR reference in an installed script is installed alongside it.
    for name in plan.py resolve-directive-policy.py; do
        install -m 644 "$SCRIPT_DIR/$name" "$INSTALL_ROOT/$name"
    done
    install -m 644 "$SCRIPT_DIR/lib.sh" "$INSTALL_ROOT/lib.sh"
    # cli/ helpers the installed scripts resolve relative to themselves. This
    # tree is FLAT, so each lands beside the scripts and they fall back to
    # $SCRIPT_DIR/<name> (select.sh, codex-backoff.sh). codex_auth.py missing
    # here made every dispatcher tick report a dead Codex login.
    local helper
    for helper in autopr_control.py codex_auth.py; do
        install -m 644 "$(dirname "$SCRIPT_DIR")/cli/$helper" "$INSTALL_ROOT/$helper"
    done
}

# Names install_runtime would write that are missing from, or differ from,
# the installed tree. Derived by running install_runtime into a staging
# directory, so this can never disagree with what the installer copies
# (cli/install.py and the dispatch suite parse install_runtime for the same
# reason; keep that function self-contained).
file_mode() {
    stat -f '%Lp' "$1" 2>/dev/null || stat -c '%a' "$1" 2>/dev/null || printf '?'
}

runtime_stale_names() {
    local staging path name
    staging="$(mktemp -d "${TMPDIR:-/tmp}/matcha-autopr-runtime.XXXXXX")"
    ( INSTALL_ROOT="$staging"; install_runtime ) >/dev/null
    for path in "$staging"/*; do
        name="$(basename "$path")"
        # Content AND mode. install(1) sets 755 on the scripts and 644 on the
        # helpers; a copy whose mode drifted to 644 is byte-identical, so a
        # content-only comparison reports "current" while the LaunchAgents
        # keep an unexecutable dispatcher.
        if ! cmp -s "$path" "$INSTALL_ROOT/$name" 2>/dev/null \
            || [ "$(file_mode "$path")" != "$(file_mode "$INSTALL_ROOT/$name")" ]; then
            printf '%s\n' "$name"
        fi
    done
    rm -rf "$staging"
}

sync_runtime_if_stale() {
    local stale
    # Refresh an installed tree; never create one. A runtime-only tree has no
    # plists and no LaunchAgents, so nothing would run it — but its existence
    # is what `cli/install.py:dispatcher_install_root().is_dir()` reads as
    # `lanes_installed`, which would start failing `msandbox doctor` on a
    # developer's machine over a Codex login and a verification cache for
    # lanes that host does not run.
    if [ ! -d "$INSTALL_ROOT" ]; then
        echo "No AutoPR dispatcher installed at $INSTALL_ROOT; run \`msandbox install\` (it renders the plists too)."
        return 0
    fi
    stale="$(runtime_stale_names | tr '\n' ' ')"
    stale="${stale% }"
    if [ -z "$stale" ]; then
        echo "AutoPR dispatcher tree current: $INSTALL_ROOT"
        return 0
    fi
    # install(1) unlinks the destination before writing, so a dispatcher tick
    # already running keeps its old inode; nothing here needs a launchctl
    # restart. The plists are not re-rendered: a changed template is the
    # full installer's job, and `msandbox doctor` / the self-audit report it.
    install_runtime
    echo "AutoPR dispatcher tree refreshed from $SCRIPT_DIR: $stale"
}

render_launch_agent() {
    mkdir -p "$LAUNCH_AGENTS_DIR" "$USER_HOME/Library/Logs"
    sed \
        -e "s|__DISPATCHER_PATH__|$DISPATCHER_DESTINATION|g" \
        -e "s|__USER_HOME__|$USER_HOME|g" \
        "$PLIST_TEMPLATE" > "$PLIST_DESTINATION"
    plutil -lint "$PLIST_DESTINATION" >/dev/null
    sed \
        -e "s|__DISPATCHER_PATH__|$DISPATCHER_DESTINATION|g" \
        -e "s|__USER_HOME__|$USER_HOME|g" \
        "$WATCH_PLIST_TEMPLATE" > "$WATCH_PLIST_DESTINATION"
    plutil -lint "$WATCH_PLIST_DESTINATION" >/dev/null
}

stop_launch_agent() {
    local domain="gui/$(id -u)"
    # Stop the old timer before replacing its dashboard. Bootstrap happens
    # only after the new session is ready; RunAtLoad can otherwise race the
    # installer's own `--restart` and both processes call tmux new-session.
    "$LAUNCHCTL_BIN" bootout "$domain/$LABEL" >/dev/null 2>&1 || true
    "$LAUNCHCTL_BIN" bootout "$domain/$WATCH_LABEL" >/dev/null 2>&1 || true
}

start_launch_agent() {
    local domain="gui/$(id -u)"
    # `msandbox off` writes a persistent launchd disable override for this
    # label. Bootstrap fails outright while that override is set, so clear it
    # on the only path that is actually authorized to start the timer.
    "$LAUNCHCTL_BIN" enable "$domain/$LABEL" >/dev/null 2>&1 || true
    "$LAUNCHCTL_BIN" bootstrap "$domain" "$PLIST_DESTINATION"
    "$LAUNCHCTL_BIN" kickstart -k "$domain/$LABEL"
    "$LAUNCHCTL_BIN" print "$domain/$LABEL"
    # The request watcher is the same script under a faster, cheaper tick.
    # A failure here must not fail the scheduler install: the twenty-minute
    # lane still runs, only the immediate button gets slower.
    "$LAUNCHCTL_BIN" enable "$domain/$WATCH_LABEL" >/dev/null 2>&1 || true
    "$LAUNCHCTL_BIN" bootstrap "$domain" "$WATCH_PLIST_DESTINATION" \
        || echo "warning: could not load $WATCH_LABEL" >&2
    "$LAUNCHCTL_BIN" kickstart -k "$domain/$WATCH_LABEL" >/dev/null 2>&1 || true
}

main() {
    if [ "$RUNTIME_ONLY" = true ]; then
        sync_runtime_if_stale
        return
    fi
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
