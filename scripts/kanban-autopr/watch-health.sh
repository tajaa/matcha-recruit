#!/usr/bin/env bash
# Local timer and self-hosted-runner health pane. It shows only process names
# and structured dispatcher events, never command arguments or secrets.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
LOG_FILE="${AUTOPR_DISPATCH_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log}"
LABEL="com.matcha.kanban-autopr-dispatch"
REFRESH_SECONDS="${AUTOPR_HEALTH_REFRESH_SECONDS:-15}"

render_health() {
    local launch_state runner_pids
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf 'LOCAL TIMER + RUNNER HEALTH\nUpdated %s\n\n' "$(date '+%H:%M:%S %Z')"

    launch_state="$(launchctl print "gui/$(id -u)/$LABEL" 2>/dev/null \
        | sed -nE '/state =|runs =|last exit code =/p' | sed 's/^[[:space:]]*/  /')"
    if [ -n "$launch_state" ]; then
        printf 'LAUNCHAGENT\n%s\n' "$launch_state"
    else
        printf 'LAUNCHAGENT\n  not loaded\n'
    fi

    printf '\nSELF-HOSTED RUNNER\n'
    runner_pids="$(pgrep -f 'Runner.Listener' | paste -sd, - 2>/dev/null || true)"
    if [ -n "$runner_pids" ]; then
        ps -p "$runner_pids" -o pid=,etime=,comm= 2>/dev/null || true
    else
        printf '  Runner.Listener not found\n'
    fi

    printf '\nRECENT TIMER EVENTS\n'
    if [ -s "$LOG_FILE" ]; then
        tail -n 14 "$LOG_FILE" | jq -r '
          "  " + (.timestamp // "?") + "  " + (.action // "?") + "  " + (.reason // "?")
          + (if ((.runs // []) | length) > 0 then
               "  [" + ([.runs[] | "#" + (.databaseId | tostring) + ":" + .status] | join(", ")) + "]"
             else "" end)
        ' 2>/dev/null || tail -n 14 "$LOG_FILE"
    else
        printf '  no timer events yet\n'
    fi

    printf '\nSession is recreated by the five-minute dispatcher if closed.\n'
}

while :; do
    render_health
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
