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
    printf '\nAUTOPR MSANDBOX · %s · ' "$label"
    if [ ! -x "$MSANDBOX_BIN" ]; then
        printf 'missing (%s)\n' "$MSANDBOX_BIN"
    elif sandbox_state="$(env AGENT_SANDBOX_PROJECT_NAME="$project" \
        "$MSANDBOX_BIN" workspace-state 2>&1)"; then
        case "$sandbox_state" in
            running) printf 'running · %s\n' "$project" ;;
            absent) printf 'ready, idle · %s\n' "$project" ;;
            *) printf 'blocked · container state %s · %s\n' "$sandbox_state" "$project" ;;
        esac
    else
        printf 'unavailable · %s\n' "$(printf '%s' "$sandbox_state" | head -n 1)"
    fi
}

render_health() {
    local launch_state runner_pids
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf 'LOCAL TIMER + RUNNER HEALTH · %s\n\n' "$(TZ="$PACIFIC_TZ" date '+%I:%M:%S %p %Z' | sed 's/^0//')"

    launch_state="$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null \
        | sed -nE '/state =|runs =|last exit code =/p' | sed 's/^[[:space:]]*/  /')"
    if [ -n "$launch_state" ]; then
        printf 'LAUNCHAGENT\n%s\n' "$launch_state"
    else
        printf 'LAUNCHAGENT\n  not loaded\n'
    fi

    printf '\nMSANDBOX MASTER SWITCH · '
    if [ ! -x "$MSANDBOX_BIN" ]; then
        printf 'unavailable\n'
    elif "$MSANDBOX_BIN" autopr-ready >/dev/null 2>&1; then
        printf 'ON · autonomous work permitted\n'
    else
        printf 'OFF · no AutoPR dispatch or model start permitted\n'
    fi

    printf '\nSELF-HOSTED RUNNER · '
    runner_pids="$(pgrep -f 'Runner.Listener' 2>/dev/null | paste -sd, - 2>/dev/null || true)"
    if [ -n "$runner_pids" ]; then
        ps -p "$runner_pids" -o pid=,etime=,comm= 2>/dev/null | sed 's/^[[:space:]]*//' || true
    else
        printf '  Runner.Listener not found\n'
    fi

    render_worker_state kanban "$KANBAN_SANDBOX_PROJECT"
    render_worker_state errors "$ERROR_SANDBOX_PROJECT"
    render_worker_state self-audit "$AUDIT_SANDBOX_PROJECT"

    printf '\nRECENT TIMER EVENTS\n'
    if [ -s "$LOG_FILE" ]; then
        # Active-workflow snapshots can contain dozens of prior runs. The
        # health pane needs the timer decision, not a wrapped dump of that
        # snapshot; the 24-hour dashboard owns workflow history.
        tail -n 8 "$LOG_FILE" | jq -r '[.timestamp // "", .action // "?", .reason // "?"] | @tsv' 2>/dev/null \
          | while IFS=$'\t' read -r event_time event_action event_reason; do
              printf '  %-15s %-8s %s\n' "$(dispatch_time_pacific "$event_time")" "$event_action" "$event_reason"
            done
    else
        printf '  no timer events yet\n'
    fi

    printf '\nSession exists only while the msandbox master switch is ON.\n'
}

while :; do
    render_health
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
