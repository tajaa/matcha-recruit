#!/usr/bin/env bash
# Idempotently create the operator tmux session. The LaunchAgent calls this on
# every tick, so killing the session is temporary and never affects dispatch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMUX_BIN="${AUTOPR_TMUX_BIN:-/opt/homebrew/bin/tmux}"
SESSION="${AUTOPR_TMUX_SESSION:-matcha-autopr}"

[ -x "$TMUX_BIN" ] || { echo "tmux is not executable: $TMUX_BIN" >&2; exit 1; }
if [ "${1:-}" = --restart ] && "$TMUX_BIN" has-session -t "$SESSION" 2>/dev/null; then
    "$TMUX_BIN" kill-session -t "$SESSION"
fi
if "$TMUX_BIN" has-session -t "$SESSION" 2>/dev/null; then
    exit 0
fi

printf -v dashboard_cmd '%q' "$SCRIPT_DIR/dashboard.sh"
printf -v work_cmd '%q' "$SCRIPT_DIR/watch-work.sh"
printf -v health_cmd '%q' "$SCRIPT_DIR/watch-health.sh"

"$TMUX_BIN" new-session -d -s "$SESSION" -n autopr "$dashboard_cmd"
main_pane="$("$TMUX_BIN" display-message -p -t "$SESSION:autopr" '#{pane_id}')"
work_pane="$("$TMUX_BIN" split-window -h -P -F '#{pane_id}' -t "$main_pane" "$work_cmd")"
health_pane="$("$TMUX_BIN" split-window -v -P -F '#{pane_id}' -t "$work_pane" "$health_cmd")"
"$TMUX_BIN" select-layout -t "$SESSION:autopr" main-vertical >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" remain-on-exit on >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" pane-border-status top >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" pane-border-format '#{pane_title}' >/dev/null
"$TMUX_BIN" select-pane -t "$main_pane" -T '24h queue + PR dashboard'
"$TMUX_BIN" select-pane -t "$work_pane" -T 'live PR-creation work'
"$TMUX_BIN" select-pane -t "$health_pane" -T 'timer + runner health'
"$TMUX_BIN" select-pane -t "$main_pane"

printf 'Dashboard ready: tmux attach -t %s\n' "$SESSION"
