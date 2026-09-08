#!/usr/bin/env bash
# Local timer and self-hosted-runner health pane. It shows only process names
# and structured dispatcher events, never command arguments or secrets.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
LOG_FILE="${AUTOPR_DISPATCH_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log}"
LABEL="com.matcha.kanban-autopr-dispatch"
REFRESH_SECONDS="${AUTOPR_HEALTH_REFRESH_SECONDS:-15}"
PACIFIC_TZ="${AUTOPR_DASHBOARD_TZ:-America/Los_Angeles}"
MSANDBOX_BIN="${AUTOPR_MSANDBOX_BIN:-$USER_HOME/.local/bin/msandbox}"
KANBAN_SANDBOX_PROJECT="${AUTOPR_KANBAN_SANDBOX_PROJECT_NAME:-matcha-kanban-autopr-sandbox}"
ERROR_SANDBOX_PROJECT="${AUTOPR_ERROR_SANDBOX_PROJECT_NAME:-matcha-error-autofix-sandbox}"
AUDIT_SANDBOX_PROJECT="${AUTOPR_AUDIT_SANDBOX_PROJECT_NAME:-matcha-autopr-self-audit-sandbox}"

TUI_COLOR=false
case "${AUTOPR_DASHBOARD_COLOR:-auto}" in
    1|always|true) TUI_COLOR=true ;;
    0|never|false) TUI_COLOR=false ;;
    *) [ -t 1 ] && [ "${TERM:-dumb}" != dumb ] && TUI_COLOR=true ;;
esac
[ -z "${NO_COLOR:-}" ] || TUI_COLOR=false
if [ "$TUI_COLOR" = true ]; then
    C_RESET=$'\033[0m' C_BRAND=$'\033[38;5;157m' C_ACCENT=$'\033[38;5;80m'
    C_GOOD=$'\033[38;5;114m' C_WARN=$'\033[38;5;221m' C_BAD=$'\033[38;5;203m'
    C_MUTED=$'\033[38;5;245m' C_RAIL=$'\033[38;5;239m' C_BOLD=$'\033[1m'
else
    C_RESET='' C_BRAND='' C_ACCENT='' C_GOOD='' C_WARN='' C_BAD=''
    C_MUTED='' C_RAIL='' C_BOLD=''
fi

health_header() {
    printf '%b◆ LOCAL TIMER + RUNNER HEALTH%b · %s\n' \
        "$C_BRAND$C_BOLD" "$C_RESET" "$1"
}

health_section() {
    printf '%b◆ %s%b\n' "$C_BRAND$C_BOLD" "$1" "$C_RESET"
}

dispatch_time_pacific() {
    local timestamp="$1" epoch rendered
    epoch="$(date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$timestamp" +%s 2>/dev/null \
        || date -u -d "$timestamp" +%s 2>/dev/null)" || { printf '?'; return; }
    if date --version >/dev/null 2>&1; then
        rendered="$(TZ="$PACIFIC_TZ" date -d "@$epoch" '+%I:%M:%S %p %Z' 2>/dev/null)"
    else
        rendered="$(TZ="$PACIFIC_TZ" date -r "$epoch" '+%I:%M:%S %p %Z' 2>/dev/null)"
    fi
    printf '%s' "$rendered" | sed 's/^0//'
}

render_worker_state() {
    local label="$1" project="$2" sandbox_state
    printf '  %-16s ' "Worker $label"
    if [ ! -x "$MSANDBOX_BIN" ]; then
        printf '%b! missing%b\n' "$C_BAD$C_BOLD" "$C_RESET"
    elif sandbox_state="$(env AGENT_SANDBOX_PROJECT_NAME="$project" \
        "$MSANDBOX_BIN" workspace-state 2>&1)"; then
        case "$sandbox_state" in
            running) printf '%b● running%b\n' "$C_GOOD$C_BOLD" "$C_RESET" ;;
            absent) printf '%b○ ready, idle%b\n' "$C_MUTED$C_BOLD" "$C_RESET" ;;
            *) printf '%b! blocked (%s)%b\n' "$C_WARN$C_BOLD" "$sandbox_state" "$C_RESET" ;;
        esac
    else
        printf '%b! unavailable%b\n' "$C_BAD$C_BOLD" "$C_RESET"
    fi
}

render_health() {
    local launch_state runner_pids runner_state pane_rows event_count
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    health_header "$(TZ="$PACIFIC_TZ" date '+%I:%M:%S %p %Z' | sed 's/^0//')"

    launch_state="$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null \
        | sed -nE '/state =|last exit code =/p' \
        | sed -E 's/^[[:space:]]*//;s/ = /=/' \
        | awk 'BEGIN { first=1 } { if (!first) printf " · "; printf "%s", $0; first=0 } END { if (!first) print "" }')"

    health_section 'SYSTEMS'
    printf '  %-16s ' 'LaunchAgent'
    if [ -n "$launch_state" ]; then
        printf '%b● %s%b\n' "$C_GOOD" "$launch_state" "$C_RESET"
    else
        printf '%b○ not loaded%b\n' "$C_MUTED" "$C_RESET"
    fi

    printf '  %-16s ' 'Master switch'
    if [ ! -x "$MSANDBOX_BIN" ]; then
        printf '%b! unavailable%b\n' "$C_BAD$C_BOLD" "$C_RESET"
    elif "$MSANDBOX_BIN" autopr-ready >/dev/null 2>&1; then
        printf '%b● ON%b · dispatch enabled\n' "$C_GOOD$C_BOLD" "$C_RESET"
    else
        printf '%b○ OFF%b · dispatch disabled\n' "$C_WARN$C_BOLD" "$C_RESET"
    fi

    runner_pids="$(pgrep -f 'Runner.Listener' 2>/dev/null | paste -sd, - 2>/dev/null || true)"
    printf '  %-16s ' 'Runner'
    if [ -n "$runner_pids" ]; then
        runner_state="$(ps -p "$runner_pids" -o pid=,etime= 2>/dev/null | head -n 1 | sed 's/^[[:space:]]*//' || true)"
        printf '%b● online%b · %s\n' "$C_GOOD$C_BOLD" "$C_RESET" "$runner_state"
    else
        printf '%b○ offline%b\n' "$C_WARN$C_BOLD" "$C_RESET"
    fi

    render_worker_state kanban "$KANBAN_SANDBOX_PROJECT"
    render_worker_state errors "$ERROR_SANDBOX_PROJECT"
    render_worker_state self-audit "$AUDIT_SANDBOX_PROJECT"

    health_section 'RECENT TIMER EVENTS'
    # stty asks the live pane PTY. LINES/tput can retain the larger height from
    # before tmux split the detail rail and would render too many event rows.
    pane_rows="$(stty size 2>/dev/null | awk '{print $1}')"
    [[ "$pane_rows" =~ ^[0-9]+$ ]] || pane_rows=15
    event_count=$((pane_rows - 10))
    [ "$event_count" -ge 2 ] || event_count=2
    [ "$event_count" -le 5 ] || event_count=5
    if [ -s "$LOG_FILE" ]; then
        # Active-workflow snapshots can contain dozens of prior runs. The
        # health pane needs the timer decision, not a wrapped dump of that
        # snapshot; the 24-hour dashboard owns workflow history.
        tail -n "$event_count" "$LOG_FILE" | jq -r '[.timestamp // "", .action // "?", .reason // "?"] | @tsv' 2>/dev/null \
          | while IFS=$'\t' read -r event_time event_action event_reason; do
              if [ "${#event_reason}" -gt 20 ]; then
                  event_reason="${event_reason:0:19}…"
              fi
              printf '  %-15s %-8s %s\n' "$(dispatch_time_pacific "$event_time")" "$event_action" "$event_reason"
            done
    else
        printf '  no timer events yet\n'
    fi
}

while :; do
    render_health
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
