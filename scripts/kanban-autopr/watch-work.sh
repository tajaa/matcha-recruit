#!/usr/bin/env bash
# Live OpenCode/OpenAI pane. investigate.sh tees the model's real terminal
# stream to a local file because GitHub does not expose in-progress step stdout.
# GitHub is polled less often than the local log so this stays visually live
# without turning the observer into an API-heavy execution path.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
WORKFLOW="${AUTOPR_WORKFLOW:-kanban-autopr.yml}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
LIVE_LOG="${AUTOPR_LIVE_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-live.log}"
REFRESH_SECONDS="${AUTOPR_WORK_REFRESH_SECONDS:-2}"
STATUS_REFRESH_SECONDS="${AUTOPR_WORK_STATUS_REFRESH_SECONDS:-10}"

RUN_ID=""
RUN_STATUS="idle"
STEP_LINE=""
LAST_STATUS_REFRESH=0

refresh_workflow_status() {
    local now runs details
    now="$(date +%s)"
    if [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] \
        && [ $((now - LAST_STATUS_REFRESH)) -lt "$STATUS_REFRESH_SECONDS" ]; then
        return 0
    fi
    LAST_STATUS_REFRESH="$now"

    runs="$($GH_BIN run list --repo "$REPO" --workflow "$WORKFLOW" --limit 10 \
        --json databaseId,status,createdAt 2>/dev/null || printf '[]')"
    RUN_ID="$(printf '%s' "$runs" | jq -r \
        '[.[] | select(.status | IN("queued", "in_progress", "requested", "waiting", "pending"))][0].databaseId // .[0].databaseId // empty' \
        2>/dev/null)"
    RUN_STATUS="$(printf '%s' "$runs" | jq -r --argjson id "${RUN_ID:-0}" \
        '[.[] | select(.databaseId == $id)][0].status // "idle"' 2>/dev/null)"
    STEP_LINE=""
    if [ -n "$RUN_ID" ] && [ "$RUN_STATUS" != idle ]; then
        details="$($GH_BIN run view "$RUN_ID" --repo "$REPO" --json jobs 2>/dev/null || printf '{"jobs":[]}')"
        STEP_LINE="$(printf '%s' "$details" | jq -r '
          [.jobs[]? as $job | $job.steps[]? |
            select(.status == "in_progress") | ($job.name + " · " + .name)][0] // empty
        ' 2>/dev/null)"
    fi
}

sanitize_model_stream() {
    # The model process has GitHub, Matcha, SSH, and EC2 credentials removed.
    # These filters are extra local-display protection for common token forms
    # and any PEM block a tool might accidentally print from the checkout.
    awk '
      /-----BEGIN .*PRIVATE KEY-----/ {print "[REDACTED PRIVATE KEY]"; pem=1; next}
      /-----END .*PRIVATE KEY-----/ {pem=0; next}
      !pem {print}
    ' | sed -E \
      -e 's/(Bearer )[A-Za-z0-9._~+\/=:-]+/\1[REDACTED]/g' \
      -e 's/sk-[A-Za-z0-9_-]{12,}/[REDACTED_OPENAI_KEY]/g' \
      -e 's/gh[pousr]_[A-Za-z0-9]{12,}/[REDACTED_GITHUB_TOKEN]/g' \
      -e 's/github_pat_[A-Za-z0-9_]{12,}/[REDACTED_GITHUB_TOKEN]/g' \
      -e 's/AKIA[0-9A-Z]{16}/[REDACTED_AWS_KEY]/g'
}

render_work() {
    local pane_rows log_lines pids
    refresh_workflow_status
    pane_rows="$(tput lines 2>/dev/null || printf '24')"
    log_lines=$((pane_rows - 8))
    [ "$log_lines" -ge 6 ] || log_lines=6

    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf 'LIVE OPENCODE / OPENAI WORK · %s\n' "$(date '+%H:%M:%S %Z')"
    if [ -n "$RUN_ID" ]; then
        printf 'RUN #%s · %s\n' "$RUN_ID" "$RUN_STATUS"
        [ -z "$STEP_LINE" ] || printf 'STEP %s\n' "$STEP_LINE"
    else
        printf 'RUN idle\n'
    fi

    pids="$(pgrep -f 'opencode run' 2>/dev/null | paste -sd, - 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        printf 'PROCESS '
        ps -p "$pids" -o pid=,etime=,comm= 2>/dev/null | paste -sd' ' - || true
    fi

    printf '\nMODEL STREAM · latest %s lines\n' "$log_lines"
    if [ -s "$LIVE_LOG" ]; then
        sanitize_model_stream < "$LIVE_LOG" | tail -n "$log_lines"
    else
        printf 'Waiting for investigate.sh to start OpenCode.\n'
        printf 'The stream will appear here without opening GitHub logs.\n'
    fi
}

while :; do
    render_work
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
