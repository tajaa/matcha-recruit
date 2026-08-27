#!/usr/bin/env bash
# Mac-owned clock for kanban-autopr. GitHub cron remains a fallback, while the
# workflow's concurrency group remains the final guard against a race.
set -euo pipefail

REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
WORKFLOW="${AUTOPR_WORKFLOW:-kanban-autopr.yml}"
REF="${AUTOPR_REF:-main}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
LOG_FILE="${AUTOPR_DISPATCH_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log}"
LOCK_DIR="${AUTOPR_DISPATCH_LOCK_DIR:-${TMPDIR:-/tmp}/matcha-kanban-autopr-dispatch.lock}"

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
    lock_mtime="$(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0)"
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
    "$GH_BIN" run list --repo "$REPO" --workflow "$WORKFLOW" --branch "$REF" --limit 20 \
        --json databaseId,status,event,createdAt,url
}

has_active_workflow_run() {
    local runs="$1"
    printf '%s' "$runs" | jq -e 'any(.[]; .status | IN("queued", "in_progress", "requested", "waiting", "pending"))' >/dev/null
}

dispatch_workflow() {
    "$GH_BIN" workflow run "$WORKFLOW" --repo "$REPO" --ref "$REF"
}

main() {
    [ -x "$GH_BIN" ] || { log_event error "gh-not-executable"; exit 1; }
    if ! acquire_dispatch_lock; then
        log_event skip local-lock
        exit 0
    fi

    local runs
    if ! runs="$(get_workflow_runs_json)"; then
        # Fail closed: a blind dispatch could create a second queued coding job.
        log_event error run-list-failed
        exit 1
    fi
    if has_active_workflow_run "$runs"; then
        log_event skip active-workflow "$runs"
        exit 0
    fi

    if ! dispatch_workflow >/dev/null; then
        log_event error dispatch-failed
        exit 1
    fi
    log_event dispatch workflow-dispatched
}

main "$@"
