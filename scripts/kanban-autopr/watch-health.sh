#!/usr/bin/env bash
# Local timer and self-hosted-runner health pane. It shows only process names
# and structured dispatcher events, never command arguments or secrets.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
LOG_FILE="${AUTOPR_DISPATCH_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log}"
LABEL="com.matcha.kanban-autopr-dispatch"
REFRESH_SECONDS="${AUTOPR_HEALTH_REFRESH_SECONDS:-15}"
MSANDBOX_BIN="${AUTOPR_MSANDBOX_BIN:-$USER_HOME/.local/bin/msandbox}"
SANDBOX_PROJECT="${AUTOPR_SANDBOX_PROJECT_NAME:-matcha-kanban-autopr-sandbox}"

render_health() {
    local launch_state runner_pids sandbox_status
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf 'LOCAL TIMER + RUNNER HEALTH · %s\n\n' "$(date '+%H:%M:%S %Z')"

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

    printf '\nAUTOPR MSANDBOX · '
    if [ ! -x "$MSANDBOX_BIN" ]; then
        printf 'missing (%s)\n' "$MSANDBOX_BIN"
    elif sandbox_status="$(env AGENT_SANDBOX_PROJECT_NAME="$SANDBOX_PROJECT" \
        "$MSANDBOX_BIN" status 2>&1)"; then
        if printf '%s\n' "$sandbox_status" | grep -q 'workspace'; then
            printf 'running · %s\n' "$SANDBOX_PROJECT"
        else
            printf 'ready, idle · %s\n' "$SANDBOX_PROJECT"
        fi
    else
        printf 'unavailable · %s\n' \
            "$(printf '%s' "$sandbox_status" | head -n 1)"
    fi

    printf '\nRECENT TIMER EVENTS\n'
    if [ -s "$LOG_FILE" ]; then
        # Active-workflow snapshots can contain dozens of prior runs. The
        # health pane needs the timer decision, not a wrapped dump of that
        # snapshot; the 24-hour dashboard owns workflow history.
        tail -n 8 "$LOG_FILE" | jq -r '
          "  " + (.timestamp // "?") + "  " + (.action // "?") + "  " + (.reason // "?")
        ' 2>/dev/null || tail -n 8 "$LOG_FILE"
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
