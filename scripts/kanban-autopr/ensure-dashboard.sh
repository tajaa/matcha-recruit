#!/usr/bin/env bash
# Idempotently create the operator tmux session. The LaunchAgent calls this on
# every tick, so killing the session is temporary and never affects dispatch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMUX_BIN="${AUTOPR_TMUX_BIN:-/opt/homebrew/bin/tmux}"
SESSION="${AUTOPR_TMUX_SESSION:-matcha-autopr}"
LOCK_DIR="${AUTOPR_TMUX_LOCK_DIR:-${TMPDIR:-/tmp}/matcha-autopr-tmux.lock}"
TMUX_WIDTH="${AUTOPR_TMUX_WIDTH:-133}"
TMUX_HEIGHT="${AUTOPR_TMUX_HEIGHT:-45}"

acquire_session_lock() {
    local attempt=0 lock_mtime=0 now=0
    mkdir -p "$(dirname "$LOCK_DIR")"
    while ! mkdir "$LOCK_DIR" 2>/dev/null; do
        # Reclaim only an abandoned lock. Normal dashboard creation takes a
        # fraction of a second, while five seconds of bounded waiting covers a
        # simultaneous installer/LaunchAgent start without hiding a deadlock.
        lock_mtime="$(stat -c %Y "$LOCK_DIR" 2>/dev/null || stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0)"
        [[ "$lock_mtime" =~ ^[0-9]+$ ]] || lock_mtime=0
        now="$(date +%s)"
        if [ $((now - lock_mtime)) -gt 60 ] 2>/dev/null; then
            rmdir "$LOCK_DIR" 2>/dev/null || true
            continue
        fi
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 50 ]; then
            echo "timed out waiting for dashboard startup lock: $LOCK_DIR" >&2
            return 1
        fi
        sleep 0.1
    done
    trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
}

[ -x "$TMUX_BIN" ] || { echo "tmux is not executable: $TMUX_BIN" >&2; exit 1; }
[[ "$TMUX_WIDTH" =~ ^[0-9]+$ ]] && [ "$TMUX_WIDTH" -ge 80 ] \
    || { echo "invalid dashboard width: $TMUX_WIDTH" >&2; exit 1; }
[[ "$TMUX_HEIGHT" =~ ^[0-9]+$ ]] && [ "$TMUX_HEIGHT" -ge 24 ] \
    || { echo "invalid dashboard height: $TMUX_HEIGHT" >&2; exit 1; }
acquire_session_lock
session_healthy() {
    local pane_states pane_count
    pane_states="$("$TMUX_BIN" list-panes -t "$SESSION" -F '#{pane_dead}' 2>/dev/null)" \
        || return 1
    pane_count="$(printf '%s\n' "$pane_states" | awk 'NF {count++} END {print count+0}')"
    [ "$pane_count" = 4 ] || return 1
    ! printf '%s\n' "$pane_states" | grep -q '^1$'
}

if "$TMUX_BIN" has-session -t "$SESSION" 2>/dev/null; then
    if [ "${1:-}" = --restart ] || ! session_healthy; then
        # A detached session can still contain dead/missing panes. Rebuild the
        # observer session automatically instead of treating its name alone as
        # proof that the dashboard started successfully.
        "$TMUX_BIN" kill-session -t "$SESSION"
    else
        printf 'Dashboard already ready: tmux attach -t %s\n' "$SESSION"
        exit 0
    fi
fi

printf -v dashboard_cmd '%q' "$SCRIPT_DIR/dashboard.sh"
printf -v work_cmd '%q' "$SCRIPT_DIR/watch-work.sh"
printf -v health_cmd '%q' "$SCRIPT_DIR/watch-health.sh"
printf -v pr_cmd '%q' "$SCRIPT_DIR/watch-pr.sh"

"$TMUX_BIN" new-session -d -x "$TMUX_WIDTH" -y "$TMUX_HEIGHT" -s "$SESSION" -n autopr "$dashboard_cmd"
"$TMUX_BIN" set-option -t "$SESSION" history-limit 100000 >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" mouse on >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" status on >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" status-position bottom >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" status-style 'bg=#111827,fg=#94a3b8' >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" status-left-length 32 >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" status-left '#[fg=#a7f3d0,bold]  MATCHA#[fg=#2dd4bf] / AUTOPR  ' >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" status-right-length 48 >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" status-right '#[fg=#64748b]detach #[fg=#cbd5e1,bold]Ctrl-b d  #[fg=#334155]│  #[fg=#94a3b8]%a %b %d · %I:%M %p  ' >/dev/null
"$TMUX_BIN" set-window-option -t "$SESSION:autopr" window-style 'bg=#0b1017' >/dev/null
"$TMUX_BIN" set-window-option -t "$SESSION:autopr" window-active-style 'bg=#0b1017' >/dev/null
"$TMUX_BIN" set-window-option -t "$SESSION:autopr" pane-border-style 'fg=#334155' >/dev/null
"$TMUX_BIN" set-window-option -t "$SESSION:autopr" pane-active-border-style 'fg=#2dd4bf' >/dev/null
main_pane="$("$TMUX_BIN" display-message -p -t "$SESSION:autopr" '#{pane_id}')"
# The overview owns the full-height left side so it stays readable from across
# a room. Raw model output, PR details, and health remain available as a
# secondary right-hand stack instead of competing equally with the status
# board. The detail rail gives roughly 40% to live work, 28% to the active PR,
# and 32% to compact system health. At the common 133-column terminal size, a
# 38% detail rail leaves the overview 82 columns wide so its queue rows do not
# wrap.
work_pane="$("$TMUX_BIN" split-window -h -p 38 -P -F '#{pane_id}' -t "$main_pane" "$work_cmd")"
pr_pane="$("$TMUX_BIN" split-window -v -p 62 -P -F '#{pane_id}' -t "$work_pane" "$pr_cmd")"
health_pane="$("$TMUX_BIN" split-window -v -p 54 -P -F '#{pane_id}' -t "$pr_pane" "$health_cmd")"
"$TMUX_BIN" set-option -t "$SESSION" remain-on-exit on >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" pane-border-status top >/dev/null
"$TMUX_BIN" set-option -t "$SESSION" pane-border-format '#[fg=#475569]─ #{?pane_active,#[fg=#a7f3d0]●,#[fg=#64748b]○} #[fg=#cbd5e1,bold]#{pane_title} #[fg=#475569]'
"$TMUX_BIN" select-pane -t "$main_pane" -T 'CONTROL BOARD · PACIFIC'
"$TMUX_BIN" select-pane -t "$work_pane" -T 'LIVE AGENT'
"$TMUX_BIN" select-pane -t "$health_pane" -T 'SYSTEM HEALTH'
"$TMUX_BIN" select-pane -t "$pr_pane" -T 'ACTIVE PR'
"$TMUX_BIN" select-pane -t "$main_pane"

session_healthy || {
    echo "dashboard was created but its four panes are not healthy" >&2
    "$TMUX_BIN" kill-session -t "$SESSION" >/dev/null 2>&1 || true
    exit 1
}

printf 'Dashboard ready: tmux attach -t %s\n' "$SESSION"
