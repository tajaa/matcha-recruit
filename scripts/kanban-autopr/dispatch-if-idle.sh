#!/usr/bin/env bash
# Mac-owned clock for both AutoPR lanes. Production errors get the first slot
# whenever their last completed pass is stale; otherwise the clock advances
# the Kanban queue. Neither workflow has a competing GitHub cron.
set -euo pipefail

REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
KANBAN_WORKFLOW="${AUTOPR_KANBAN_WORKFLOW:-${AUTOPR_WORKFLOW:-kanban-autopr.yml}}"
ERROR_WORKFLOW="${AUTOPR_ERROR_WORKFLOW:-silent-error-autofix.yml}"
ERROR_MAX_AGE_SECONDS="${AUTOPR_ERROR_MAX_AGE_SECONDS:-600}"
REF="${AUTOPR_REF:-main}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
DOCKER_BIN="${AUTOPR_DOCKER_BIN:-/usr/local/bin/docker}"
ENABLE_FILE="${AUTOPR_ENABLE_FILE:-$USER_HOME/.local/state/matcha-agent-sandbox/autopr-enabled}"
PRIMARY_SANDBOX_PROJECT="${AUTOPR_PRIMARY_SANDBOX_PROJECT:-matcha-agent-sandbox}"
LOG_FILE="${AUTOPR_DISPATCH_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log}"
LOCK_DIR="${AUTOPR_DISPATCH_LOCK_DIR:-${TMPDIR:-/tmp}/matcha-kanban-autopr-dispatch.lock}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_ENSURE="${AUTOPR_DASHBOARD_ENSURE:-$SCRIPT_DIR/ensure-dashboard.sh}"

log_event() {
    local action="$1" reason="$2" runs="${3:-[]}"
    mkdir -p "$(dirname "$LOG_FILE")"
    jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg action "$action" \
        --arg reason "$reason" --argjson runs "$runs" \
        '{timestamp:$ts,action:$action,reason:$reason,runs:$runs}' >> "$LOG_FILE"
}

acquire_dispatch_lock() {
    if mkdir "$LOCK_DIR" 2>/dev/null; then
        trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
        return 0
    fi
    # A killed launchd process can leave an empty directory behind. Reclaim
    # only a lock older than fifteen minutes; normal dispatches take seconds.
    local lock_mtime now
    lock_mtime="$(stat -f '%m' "$LOCK_DIR" 2>/dev/null || true)"
    [[ "$lock_mtime" =~ ^[0-9]+$ ]] \
        || lock_mtime="$(stat -c '%Y' "$LOCK_DIR" 2>/dev/null || echo 0)"
    now="$(date +%s)"
    if [ $((now - lock_mtime)) -gt 900 ] 2>/dev/null; then
        rmdir "$LOCK_DIR" 2>/dev/null || return 1
        mkdir "$LOCK_DIR" 2>/dev/null || return 1
        trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
        return 0
    fi
    return 1
}

get_workflow_runs_json() {
    local workflow="$1"
    "$GH_BIN" run list --repo "$REPO" --workflow "$workflow" --branch "$REF" --limit 20 \
        --json databaseId,status,event,createdAt,updatedAt,url
}

has_active_workflow_run() {
    local runs="$1"
    printf '%s' "$runs" | jq -e 'any(.[]; .status | IN("queued", "in_progress", "requested", "waiting", "pending"))' >/dev/null
}

dispatch_workflow() {
    "$GH_BIN" workflow run "$1" --repo "$REPO" --ref "$REF"
}

iso_to_epoch() {
    local iso="$1"
    date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null \
        || date -u -d "$iso" +%s
}

error_pass_due() {
    local runs="$1" last_completed completed_epoch now
    last_completed="$(printf '%s' "$runs" | jq -r \
        '[.[] | select(.status == "completed")] | sort_by(.updatedAt // .createdAt) | last | (.updatedAt // .createdAt) // empty')"
    [ -n "$last_completed" ] || return 0
    completed_epoch="$(iso_to_epoch "$last_completed")" || return 0
    now="$(date +%s)"
    [ $((now - completed_epoch)) -ge "$ERROR_MAX_AGE_SECONDS" ]
}

autopr_master_ready() {
    # This is the same two-part master predicate owned by `msandbox`: its
    # enable marker must exist and the primary sandbox workspace must still be
    # running. Evaluate it here with paths outside ~/Documents because macOS
    # TCC can deny background LaunchAgents access to the repo-backed msandbox
    # symlink even though the same command works in Terminal.
    [ -f "$ENABLE_FILE" ] || return 1
    [ -x "$DOCKER_BIN" ] || return 1
    [ -n "$("$DOCKER_BIN" ps --quiet \
        --filter "label=com.docker.compose.project=$PRIMARY_SANDBOX_PROJECT" \
        --filter 'label=com.docker.compose.service=workspace' \
        --filter 'status=running' 2>/dev/null)" ]
}

main() {
    [ -x "$GH_BIN" ] || { log_event error "gh-not-executable"; exit 1; }
    # `msandbox` remains the authoritative kill switch: it alone creates and
    # removes ENABLE_FILE. A persistent marker alone is insufficient after a
    # reboot/crash, so also require its primary workspace container to be live.
    if ! autopr_master_ready; then
        log_event skip msandbox-off
        exit 0
    fi
    if [ "${AUTOPR_TMUX_DASHBOARD:-1}" != 0 ] && [ -x "$DASHBOARD_ENSURE" ]; then
        # Observability must not become a scheduling dependency. Record a pane
        # startup failure, then continue the authoritative dispatch check.
        "$DASHBOARD_ENSURE" >/dev/null 2>&1 || log_event error dashboard-start-failed
    fi
    if ! acquire_dispatch_lock; then
        log_event skip local-lock
        exit 0
    fi

    local kanban_runs error_runs all_runs workflow reason
    if ! error_runs="$(get_workflow_runs_json "$ERROR_WORKFLOW")"; then
        # Fail closed: a blind dispatch could create a second queued coding job.
        log_event error error-run-list-failed
        exit 1
    fi
    if ! kanban_runs="$(get_workflow_runs_json "$KANBAN_WORKFLOW")"; then
        log_event error kanban-run-list-failed
        exit 1
    fi
    all_runs="$(jq -cn --argjson errors "$error_runs" --argjson kanban "$kanban_runs" \
        '$errors + $kanban')"
    if has_active_workflow_run "$all_runs"; then
        log_event skip active-autopr-workflow "$all_runs"
        exit 0
    fi

    if error_pass_due "$error_runs"; then
        workflow="$ERROR_WORKFLOW"
        reason="production-error-pass-due"
    else
        workflow="$KANBAN_WORKFLOW"
        reason="kanban-pass"
    fi
    if ! dispatch_workflow "$workflow" >/dev/null; then
        log_event error "${workflow}-dispatch-failed"
        exit 1
    fi
    log_event dispatch "$reason"
}

main "$@"
