#!/usr/bin/env bash
# Mac-owned clock for the scheduled AutoPR lanes. Production errors get the
# first slot whenever their last completed pass is stale; otherwise the clock
# advances self-audit, then Kanban — and the Kanban lane is held to one pass
# every twenty minutes so routine board sweeps stop dominating the runner.
# `--if-requested` is the human's way past that clock: the one-minute watcher
# LaunchAgent asks the board whether a card pressed "Run AutoPR now" and
# dispatches Kanban immediately when one has, without touching the GitHub API
# on an idle tick. The externally dispatched admin-update lane participates in
# the active-run interlock but is never scheduled here.
set -euo pipefail

REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
KANBAN_WORKFLOW="${AUTOPR_KANBAN_WORKFLOW:-${AUTOPR_WORKFLOW:-kanban-autopr.yml}}"
ERROR_WORKFLOW="${AUTOPR_ERROR_WORKFLOW:-silent-error-autofix.yml}"
AUDIT_WORKFLOW="${AUTOPR_AUDIT_WORKFLOW:-autopr-self-audit.yml}"
ADMIN_UPDATES_WORKFLOW="${AUTOPR_ADMIN_UPDATES_WORKFLOW:-admin-updates-autopublish.yml}"
ERROR_MAX_AGE_SECONDS="${AUTOPR_ERROR_MAX_AGE_SECONDS:-600}"
AUDIT_MAX_AGE_SECONDS="${AUTOPR_AUDIT_MAX_AGE_SECONDS:-21600}"
# The Kanban lane is the slow one: a scheduled pass every twenty minutes, not
# every tick. A human who wants a card now presses "Run AutoPR now" on it,
# which the one-minute watcher below turns into an immediate dispatch.
KANBAN_MAX_AGE_SECONDS="${AUTOPR_KANBAN_MAX_AGE_SECONDS:-1200}"
# Floor between two request-driven dispatches, so a card that cannot actually
# be selected (capped queue, wrong lane, crashed run) cannot spin the runner.
FORCED_MIN_INTERVAL_SECONDS="${AUTOPR_FORCED_MIN_INTERVAL_SECONDS:-300}"
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
RUN_SNAPSHOT="${AUTOPR_RUN_SNAPSHOT:-$SCRIPT_DIR/run-snapshot.sh}"
RUN_REQUEST_PROBE="${AUTOPR_RUN_REQUEST_PROBE:-$SCRIPT_DIR/has-run-request.sh}"
STATE_DIR="${AUTOPR_DISPATCH_STATE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard/dispatch}"
FORCED_MARKER="$STATE_DIR/last-forced-kanban"

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

has_active_workflow_run() {
    local runs="$1"
    printf '%s' "$runs" | jq -e 'any(.[]; .status | IN("queued", "in_progress", "requested", "waiting", "pending"))' >/dev/null
}

dispatch_workflow() {
    "$GH_BIN" api --method POST \
        "repos/$REPO/actions/workflows/$1/dispatches" -f "ref=$REF"
}

iso_to_epoch() {
    local iso="$1"
    date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%s 2>/dev/null \
        || date -u -d "$iso" +%s
}

workflow_pass_due() {
    local runs="$1" max_age="$2" last_completed completed_epoch now
    last_completed="$(printf '%s' "$runs" | jq -r \
        '[.[] | select(.status == "completed")] | sort_by(.updatedAt // .createdAt) | last | (.updatedAt // .createdAt) // empty')"
    [ -n "$last_completed" ] || return 0
    completed_epoch="$(iso_to_epoch "$last_completed")" || return 0
    now="$(date +%s)"
    [ $((now - completed_epoch)) -ge "$max_age" ]
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

marker_age_seconds() {
    local marker="$1" modified now
    [ -f "$marker" ] || { printf '%s' 999999999; return; }
    modified="$(stat -f '%m' "$marker" 2>/dev/null || true)"
    [[ "$modified" =~ ^[0-9]+$ ]] || modified="$(stat -c '%Y' "$marker" 2>/dev/null || echo 0)"
    now="$(date +%s)"
    printf '%s' "$((now - modified))"
}

# Liveness for the one-minute watcher, kept out of the shared dispatch log so
# an idle minute leaves no scheduling signal behind. Best-effort by design.
touch_watch_heartbeat() {
    mkdir -p "$STATE_DIR" 2>/dev/null && : > "$STATE_DIR/last-watch-tick" 2>/dev/null || true
}

# Exit status only: 0 = a card is waiting, 1 = nothing to force (queue empty or
# the board could not be asked). A probe failure must never force a run.
run_request_pending() {
    [ -x "$RUN_REQUEST_PROBE" ] || return 1
    local rc
    "$RUN_REQUEST_PROBE" >/dev/null 2>&1
    rc=$?
    case "$rc" in
        0) return 0 ;;
        3) return 1 ;;
        *) log_event error run-request-probe-failed; return 1 ;;
    esac
}

main() {
    local requested_mode=false
    [ "${1:-}" != "--if-requested" ] || requested_mode=true
    [ -x "$GH_BIN" ] || { log_event error "gh-not-executable"; exit 1; }
    # `msandbox` remains the authoritative kill switch: it alone creates and
    # removes ENABLE_FILE. A persistent marker alone is insufficient after a
    # reboot/crash, so also require its primary workspace container to be live.
    if ! autopr_master_ready; then
        log_event skip msandbox-off
        exit 0
    fi
    # The watcher lane asks the board first and gives up before doing anything
    # else, so a minute-by-minute tick costs one bounded query against our own
    # API and nothing else. This runs BEFORE the dispatch lock and before the
    # dashboard-ensure pass on purpose: `mw_api` talks to a remote host, and a
    # stalled request must not hold the lock the five-minute scheduler needs,
    # nor re-prime the GitHub-reading observer panes sixty times an hour.
    if [ "$requested_mode" = true ]; then
        if [ "$(marker_age_seconds "$FORCED_MARKER")" -lt "$FORCED_MIN_INTERVAL_SECONDS" ]; then
            exit 0
        fi
        if ! run_request_pending; then
            # Silent on the common path: an idle tick every minute would
            # otherwise bury the scheduler's own signal in the shared log the
            # dashboard reads, and grow the file five times as fast.
            touch_watch_heartbeat
            exit 0
        fi
    else
        if [ "${AUTOPR_TMUX_DASHBOARD:-1}" != 0 ] && [ -x "$DASHBOARD_ENSURE" ]; then
            # Observability must not become a scheduling dependency. Record a
            # pane startup failure, then continue the authoritative dispatch
            # check. Scheduler-only: the panes are themselves GitHub readers.
            "$DASHBOARD_ENSURE" >/dev/null 2>&1 || log_event error dashboard-start-failed
        fi
    fi
    if ! acquire_dispatch_lock; then
        log_event skip local-lock
        exit 0
    fi

    local kanban_runs error_runs audit_runs all_runs workflow reason
    if [ ! -x "$RUN_SNAPSHOT" ] || ! all_runs="$(AUTOPR_REPO="$REPO" AUTOPR_REF="$REF" \
        AUTOPR_GH_BIN="$GH_BIN" AUTOPR_GITHUB_SNAPSHOT_ALLOW_STALE=false "$RUN_SNAPSHOT")"; then
        # Fail closed: a blind dispatch could create a second queued coding job.
        log_event error run-snapshot-failed
        exit 1
    fi
    kanban_runs="$(printf '%s' "$all_runs" | jq -c '[.[] | select(.lane == "kanban")][0:20]')"
    error_runs="$(printf '%s' "$all_runs" | jq -c '[.[] | select(.lane == "errors")][0:20]')"
    audit_runs="$(printf '%s' "$all_runs" | jq -c '[.[] | select(.lane == "self-audit")][0:20]')"
    if has_active_workflow_run "$all_runs"; then
        log_event skip active-autopr-workflow "$all_runs"
        exit 0
    fi

    if [ "$requested_mode" = true ]; then
        # An explicit card request outranks the other lanes' schedules: the
        # human is waiting on this specific ticket. The cooldown marker is
        # burned after the dispatch actually lands, not here — a failed
        # dispatch must not make the next queued card wait five more minutes.
        workflow="$KANBAN_WORKFLOW"
        reason="kanban-run-request"
    elif workflow_pass_due "$error_runs" "$ERROR_MAX_AGE_SECONDS"; then
        workflow="$ERROR_WORKFLOW"
        reason="production-error-pass-due"
    elif workflow_pass_due "$audit_runs" "$AUDIT_MAX_AGE_SECONDS"; then
        workflow="$AUDIT_WORKFLOW"
        reason="autopr-self-audit-due"
    elif workflow_pass_due "$kanban_runs" "$KANBAN_MAX_AGE_SECONDS"; then
        workflow="$KANBAN_WORKFLOW"
        reason="kanban-pass"
    else
        log_event skip kanban-not-due
        exit 0
    fi
    if ! dispatch_workflow "$workflow" >/dev/null; then
        log_event error "${workflow}-dispatch-failed"
        exit 1
    fi
    if [ "$requested_mode" = true ] \
        && ! { mkdir -p "$STATE_DIR" && : > "$FORCED_MARKER"; }; then
        # Without the marker the floor between two forced dispatches is gone,
        # so this is worth a log line rather than an `set -e` exit that leaves
        # no trace of why the watcher stopped behaving.
        log_event error forced-marker-write-failed
    fi
    log_event dispatch "$reason"
}

main "$@"
