#!/usr/bin/env bash
# Live Actions progress pane. GitHub does not expose in-progress step stdout,
# but `gh run view` gives the current job/step and this pane adds local runner
# process state without printing ticket prompts or credential-bearing args.
set -uo pipefail

REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
WORKFLOW="${AUTOPR_WORKFLOW:-kanban-autopr.yml}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
REFRESH_SECONDS="${AUTOPR_WORK_REFRESH_SECONDS:-10}"

render_work() {
    local runs run_id pids
    runs="$($GH_BIN run list --repo "$REPO" --workflow "$WORKFLOW" --limit 10 \
        --json databaseId,status,createdAt,displayTitle,url 2>/dev/null || printf '[]')"
    run_id="$(printf '%s' "$runs" | jq -r \
        '[.[] | select(.status | IN("queued", "in_progress", "requested", "waiting", "pending"))][0].databaseId // empty')"

    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf 'LIVE PR-CREATION WORK\nUpdated %s\n\n' "$(date '+%H:%M:%S %Z')"
    if [ -n "$run_id" ]; then
        "$GH_BIN" run view "$run_id" --repo "$REPO" 2>&1 || printf 'Run #%s is present but details are temporarily unavailable.\n' "$run_id"
    else
        printf 'No Kanban AutoPR workflow is currently queued or running.\n'
        run_id="$(printf '%s' "$runs" | jq -r '.[0].databaseId // empty')"
        if [ -n "$run_id" ]; then
            printf '\nMOST RECENT RUN\n'
            "$GH_BIN" run view "$run_id" --repo "$REPO" 2>&1 || true
        fi
    fi

    printf '\nLOCAL WORKER PROCESSES\n'
    pids="$(pgrep -f 'Runner.Worker|opencode' | paste -sd, - 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        ps -p "$pids" -o pid=,etime=,comm= 2>/dev/null || true
    else
        printf '  none\n'
    fi
}

while :; do
    render_work
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
