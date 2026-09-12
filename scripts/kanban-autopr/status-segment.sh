#!/usr/bin/env bash
# One line of AutoPR state for a tmux status bar. Every msandbox agent session
# runs this on its status-interval, so it reads local files only — never
# GitHub, Docker, or the board. Emits tmux #[...] styles unless
# AUTOPR_SEGMENT_PLAIN=1. The sources are the same ones the dispatcher and the
# observer dashboard write: the master-switch marker, the per-tick scheduler
# status, the shared run snapshot, and the card snapshot.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
ENABLE_FILE="${AUTOPR_ENABLE_FILE:-$USER_HOME/.local/state/matcha-agent-sandbox/autopr-enabled}"
STATE_DIR="${AUTOPR_DISPATCH_STATE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard/dispatch}"
RUNS_FILE="${AUTOPR_GITHUB_SNAPSHOT_CACHE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard/github}/runs.json"
CARD_SNAPSHOT="${AUTOPR_CARD_SNAPSHOT:-$USER_HOME/Library/Caches/matcha-kanban-autopr/cards.json}"
RUNNER_WORKTREE="${AUTOPR_RUNNER_WORKTREE:-$USER_HOME/.local/share/matcha-actions-runner/_work/matcha-recruit/matcha-recruit}"
GIT_BIN="${AUTOPR_GIT_BIN:-git}"
NOW="${AUTOPR_NOW_EPOCH:-$(date +%s)}"
PLAIN="${AUTOPR_SEGMENT_PLAIN:-0}"
STALE_AFTER_SECONDS=360
TITLE_WIDTH=24

style() { [ "$PLAIN" = 1 ] || printf '#[%s]' "$1"; }
emit() {
    # $1 style, $2 text
    printf '%sAUTOPR %s%s\n' "$(style "$1")" "$2" "$(style default)"
}

iso_to_epoch() {
    date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$1" +%s 2>/dev/null \
        || date -u -d "$1" +%s 2>/dev/null || printf '%s' "$NOW"
}

minutes_since() {
    local epoch="$1"
    printf '%s' $(( (NOW - epoch) / 60 ))
}

[ -f "$ENABLE_FILE" ] || { emit 'fg=red,bold' 'OFF'; exit 0; }

reason='' checked_at=0 eligible_at=0 next_check_at=0
if [ -s "$STATE_DIR/status.json" ]; then
    IFS=$'\t' read -r reason checked_at eligible_at next_check_at < <(
        jq -r '[(.reason // ""), (.checked_at // 0), (.eligible_at // 0), (.next_check_at // 0)] | @tsv' \
            "$STATE_DIR/status.json" 2>/dev/null || printf '\t0\t0\t0\n')
fi
[[ "$checked_at" =~ ^[0-9]+$ ]] || checked_at=0
[[ "$eligible_at" =~ ^[0-9]+$ ]] || eligible_at=0
[[ "$next_check_at" =~ ^[0-9]+$ ]] || next_check_at=0

if [ "$checked_at" -eq 0 ]; then
    emit 'fg=yellow,bold' 'no scheduler signal'
    exit 0
fi
if [ $((NOW - checked_at)) -gt "$STALE_AFTER_SECONDS" ]; then
    emit 'fg=yellow,bold' "scheduler stale $(minutes_since "$checked_at")m"
    exit 0
fi
case "$reason" in
    msandbox-off) emit 'fg=red,bold' 'SANDBOX OFF'; exit 0 ;;
    codex-usage-limit-backoff) emit 'fg=yellow,bold' 'codex backoff'; exit 0 ;;
esac

active=''
if [ -s "$RUNS_FILE" ]; then
    active="$(jq -c '[.[] | select(.status | IN("queued", "in_progress", "requested", "waiting", "pending"))][0] // empty' \
        "$RUNS_FILE" 2>/dev/null || true)"
fi
if [ -n "$active" ]; then
    lane="$(printf '%s' "$active" | jq -r '.lane // "run"' | tr '[:lower:]' '[:upper:]')"
    created="$(printf '%s' "$active" | jq -r '.createdAt // empty')"
    elapsed=''
    [ -z "$created" ] || elapsed=" $(minutes_since "$(iso_to_epoch "$created")")m"
    card=''
    if [ "$lane" = KANBAN ] && [ -s "$CARD_SNAPSHOT" ] \
        && branch="$("$GIT_BIN" -C "$RUNNER_WORKTREE" branch --show-current 2>/dev/null)" \
        && [[ "$branch" == bot/task-* ]]; then
        id8="${branch#bot/task-}"
        card="$(jq -r --arg id8 "${id8:0:8}" --argjson w "$TITLE_WIDTH" \
            '[.[] | select(.id8 == $id8) | .title[0:$w]][0] // empty' "$CARD_SNAPSHOT" 2>/dev/null || true)"
    fi
    # tmux parses this output as a format string: a card title containing
    # `#[` or `#{` would restyle or truncate every session's status bar.
    [ "$PLAIN" = 1 ] || card="${card//#/##}"
    emit 'fg=green,bold' "▶ ${lane}${elapsed}${card:+ · $card}"
    exit 0
fi

if [ "$eligible_at" -gt "$NOW" ]; then
    wait_s=$((eligible_at - NOW))
    if [ "$wait_s" -ge 60 ]; then emit 'fg=cyan' "idle · next in $(( (wait_s + 59) / 60 ))m"
    else emit 'fg=cyan' "idle · next in ${wait_s}s"; fi
elif [ "$next_check_at" -gt "$NOW" ]; then
    emit 'fg=cyan' "idle · tick in $((next_check_at - NOW))s"
else
    emit 'fg=cyan' 'idle · tick due'
fi
