#!/usr/bin/env bash
# Mac-owned clock for the scheduled AutoPR lanes. Production errors get the
# first slot whenever their last completed pass is stale; otherwise the clock
# advances self-audit, then Kanban, with a five-minute routine cadence.
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
# The Kanban lane becomes eligible five minutes after its last completed pass.
# A human who wants a card now presses "Run AutoPR now" on it,
# which the one-minute watcher below turns into an immediate dispatch.
KANBAN_MAX_AGE_SECONDS="${AUTOPR_KANBAN_MAX_AGE_SECONDS:-300}"
# Floor between two request-driven dispatches, so a card that cannot actually
# be selected (capped queue, wrong lane, crashed run) cannot spin the runner.
FORCED_MIN_INTERVAL_SECONDS="${AUTOPR_FORCED_MIN_INTERVAL_SECONDS:-60}"
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
# The last snapshot run-snapshot.sh wrote, read here only to decide whether a
# scheduler tick can end without asking GitHub at all (same path expression
# as in run-snapshot.sh).
SNAPSHOT_CACHE_FILE="${AUTOPR_GITHUB_SNAPSHOT_CACHE_DIR:-${AUTOPR_DASHBOARD_CACHE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard}/github}/runs.json"
RUN_REQUEST_PROBE="${AUTOPR_RUN_REQUEST_PROBE:-$SCRIPT_DIR/has-run-request.sh}"
STATE_DIR="${AUTOPR_DISPATCH_STATE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard/dispatch}"
FORCED_MARKER="$STATE_DIR/last-forced-kanban"
# One button press costs at most one forced run: the set of pending requests
# the last forced dispatch was made for. While that set is unchanged and the
# request TTL has not passed, a run that died before claiming them (stale
# main gate, rate limit, master switch off) must not be re-fired every tick.
FORCED_REQUEST_SET="$STATE_DIR/last-forced-request-set"
FORCED_REQUEST_TTL_SECONDS="${AUTOPR_FORCED_REQUEST_TTL_SECONDS:-1800}"
CODEX_BACKOFF="${AUTOPR_CODEX_BACKOFF:-$SCRIPT_DIR/codex-backoff.sh}"
LOG_MAX_BYTES="${AUTOPR_DISPATCH_LOG_MAX_BYTES:-5242880}"
START_TASK=""
REQUESTED_TASK=""
NEXT_ELIGIBLE_AT=0
# Must match StartInterval in launchd/com.matcha.kanban-autopr-dispatch.plist.in.
# Only the dashboard's "next check" line reads it, but a stale value there is how
# an operator mistimes a manual start. One dispatch happens per tick and the
# cheaper lanes are checked first, so a coarse tick is what actually paces the
# Kanban lane: at 300 a card could wait three ticks (active run, then an errors
# pass, then its own) and take a quarter hour to leave Todo.
POLL_SECONDS="${AUTOPR_DISPATCH_POLL_SECONDS:-60}"
PREFERRED_TASK_FILE="$STATE_DIR/preferred-task"
# Notification Center banners are opt-in per operator (`msandbox notify on|off`
# writes the marker next to the master switch). The marker lives beside
# ENABLE_FILE so a test that relocates the switch also silences banners.
NOTIFY_FILE="${AUTOPR_NOTIFY_FILE:-$(dirname "$ENABLE_FILE")/autopr-notify}"
NOTIFY_BIN="${AUTOPR_NOTIFY_BIN:-/usr/bin/osascript}"
NOTIFIED_RUN_FILE="$STATE_DIR/last-notified-run"
NOTIFIED_OFF_FILE="$STATE_DIR/notified-off"
NOTIFIED_AUTH_FILE="$STATE_DIR/notified-codex-auth"
CODEX_AUTH_CACHE="$STATE_DIR/codex-auth-check"
CODEX_AUTH_CACHE_SECONDS="${AUTOPR_CODEX_AUTH_CACHE_SECONDS:-240}"
HOST_CODEX_AUTH_FILE="${AUTOPR_HOST_CODEX_AUTH_FILE:-$USER_HOME/.codex/auth.json}"

write_status() {
    local action="$1" reason="$2" now temporary
    now="$(date +%s)"
    mkdir -p "$STATE_DIR"
    temporary="$(mktemp "$STATE_DIR/.status.XXXXXX")" || return 1
    jq -cn --arg action "$action" --arg reason "$reason" --arg task "$REQUESTED_TASK" \
        --argjson checked "$now" --argjson poll "$POLL_SECONDS" \
        --argjson eligible "$NEXT_ELIGIBLE_AT" --argjson routine "$KANBAN_MAX_AGE_SECONDS" \
        '{action:$action,reason:$reason,requested_task_id:$task,checked_at:$checked,next_check_at:($checked+$poll),eligible_at:$eligible,routine_seconds:$routine}' > "$temporary"
    chmod 600 "$temporary"
    mv "$temporary" "$STATE_DIR/status.json"
    [ -z "$START_TASK" ] || cat "$STATE_DIR/status.json"
}

log_event() {
    local action="$1" reason="$2" runs="${3:-[]}" size
    mkdir -p "$(dirname "$LOG_FILE")"
    # Nothing rotated this file; it reached 7 MB after one week. Keep one
    # generation so the dashboard's tail still has history after a rotation.
    size="$(stat -f '%z' "$LOG_FILE" 2>/dev/null || stat -c '%s' "$LOG_FILE" 2>/dev/null || echo 0)"
    if [[ "$size" =~ ^[0-9]+$ ]] && [ "$size" -gt "$LOG_MAX_BYTES" ]; then
        mv -f "$LOG_FILE" "$LOG_FILE.1" 2>/dev/null || true
    fi
    jq -cn --arg ts "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg action "$action" \
        --arg reason "$reason" --argjson runs "$runs" \
        '{timestamp:$ts,action:$action,reason:$reason,runs:$runs}' >> "$LOG_FILE"
    write_status "$action" "$reason"
}

# Best-effort banner. Quotes and backslashes are dropped rather than escaped:
# AppleScript string quoting is not worth a scheduler bug, and every message
# here is composed from lane names, run ids, and conclusions.
notify() {
    local subtitle="$1" body="$2"
    [ -f "$NOTIFY_FILE" ] || return 0
    [ -x "$NOTIFY_BIN" ] || return 0
    subtitle="${subtitle//[\"\\]/}"
    body="${body//[\"\\]/}"
    "$NOTIFY_BIN" -e "display notification \"$body\" with title \"Matcha AutoPR\" subtitle \"$subtitle\"" \
        >/dev/null 2>&1 </dev/null || true
}

# Announce runs that finished since the last tick. GitHub run ids grow
# monotonically, so "newer than the last id seen" is exact; the first
# observation only records a baseline, so enabling banners never replays
# history. Kanban outcomes always notify; other lanes only when they fail.
notify_run_outcomes() {
    local runs="$1" last_seen newest completed line lane conclusion id created updated mins
    newest="$(printf '%s' "$runs" | jq -r '[.[] | select(.status == "completed") | .databaseId] | max // empty')"
    [ -n "$newest" ] || return 0
    last_seen="$(cat "$NOTIFIED_RUN_FILE" 2>/dev/null || true)"
    [[ "$last_seen" =~ ^[0-9]+$ ]] || last_seen=""
    mkdir -p "$STATE_DIR"
    printf '%s' "$newest" > "$NOTIFIED_RUN_FILE"
    [ -n "$last_seen" ] || return 0
    [ "$newest" -gt "$last_seen" ] || return 0
    [ -f "$NOTIFY_FILE" ] || return 0
    completed="$(printf '%s' "$runs" | jq -r --argjson since "$last_seen" '
        [.[] | select(.status == "completed" and .databaseId > $since)]
        | sort_by(.databaseId) | .[-3:][]
        | [(.lane // "run"), (.conclusion // "completed"), (.databaseId | tostring), (.createdAt // ""), (.updatedAt // "")] | @tsv')"
    while IFS=$'\t' read -r lane conclusion id created updated; do
        [ -n "$id" ] || continue
        mins=""
        if [ -n "$created" ] && [ -n "$updated" ]; then
            mins=" · $(( ( $(iso_to_epoch "$updated") - $(iso_to_epoch "$created") ) / 60 ))m"
        fi
        case "$lane:$conclusion" in
            kanban:*) notify "Kanban run $conclusion" "run #$id$mins" ;;
            *:failure|*:cancelled|*:timed_out) notify "$lane run $conclusion" "run #$id$mins" ;;
        esac
    done <<< "$completed"
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
    if [ -n "$REQUESTED_TASK" ] && [ "$1" = "$KANBAN_WORKFLOW" ]; then
        "$GH_BIN" api --method POST "repos/$REPO/actions/workflows/$1/dispatches" \
            -f "ref=$REF" -f "inputs[requested_task_id]=$REQUESTED_TASK"
    else
        "$GH_BIN" api --method POST \
            "repos/$REPO/actions/workflows/$1/dispatches" -f "ref=$REF"
    fi
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

# A scheduler tick that cannot dispatch anything needs no GitHub call. The
# Kanban lane's own eligibility is in status.json (`eligible_at`, written from
# the last snapshot's last completed run), and whether the error or self-audit
# lane is due is a function of time over the LAST snapshot: a run that
# completed since only makes a lane look more due, never less, so the stale
# read is conservative — it can only cause a fetch, never suppress one. Before
# this, 125 of 268 ticks on 2026-09-13 fetched a fresh 100-run list to log
# `kanban-not-due`, and 65 ticks in six days failed closed on a transient
# network error doing so. Never on the watcher lane (it has its own probe and
# never reaches here idle) and never when a start was requested.
scheduler_idle_without_fetch() {
    [ -s "$SNAPSHOT_CACHE_FILE" ] || return 1
    [ -s "$STATE_DIR/status.json" ] || return 1
    # A run that was still in flight at the last fetch is about to finish, and
    # notify_run_outcomes — the operator's "run finished" banner — only runs
    # after a fetch. Skipping the fetch here would hold that banner for the
    # rest of the eligibility window. It costs nothing: before this
    # short-circuit existed these ticks fetched anyway and ended at
    # `skip active-autopr-workflow`.
    ! jq -e 'any(.[]; .status != "completed")' "$SNAPSHOT_CACHE_FILE" >/dev/null 2>&1 || return 1
    local now eligible cached
    now="$(date +%s)"
    eligible="$(jq -r '.eligible_at // 0' "$STATE_DIR/status.json" 2>/dev/null || true)"
    [[ "$eligible" =~ ^[0-9]+$ ]] || return 1
    [ "$eligible" -gt "$now" ] || return 1
    cached="$(jq -c '[.[] | select(.lane == "errors")]' "$SNAPSHOT_CACHE_FILE" 2>/dev/null)" || return 1
    ! workflow_pass_due "$cached" "$ERROR_MAX_AGE_SECONDS" || return 1
    cached="$(jq -c '[.[] | select(.lane == "self-audit")]' "$SNAPSHOT_CACHE_FILE" 2>/dev/null)" || return 1
    ! workflow_pass_due "$cached" "$AUDIT_MAX_AGE_SECONDS" || return 1
    NEXT_ELIGIBLE_AT="$eligible"
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

file_mtime() {
    local path="$1" modified
    modified="$(stat -f '%m' "$path" 2>/dev/null || true)"
    [[ "$modified" =~ ^[0-9]+$ ]] || modified="$(stat -c '%Y' "$path" 2>/dev/null || echo 0)"
    printf '%s' "$modified"
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
# the board could not be asked). A probe failure must never force a run. On
# success PENDING_REQUEST_SET holds a stable fingerprint of the queue.
PENDING_REQUEST_SET=""
run_request_pending() {
    [ -x "$RUN_REQUEST_PROBE" ] || return 1
    local rc requests
    requests="$("$RUN_REQUEST_PROBE" 2>/dev/null)"
    rc=$?
    case "$rc" in
        0)
            printf '%s' "$requests" | jq -e 'type == "array" and length > 0 and all(.[]; (.task_id | type == "string") and (.task_id | test("^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")))' >/dev/null \
                || { log_event error invalid-run-requests; return 1; }
            local preferred="$START_TASK"
            [ -n "$preferred" ] || preferred="$(cat "$PREFERRED_TASK_FILE" 2>/dev/null || true)"
            REQUESTED_TASK="$(printf '%s' "$requests" | jq -r --arg preferred "$preferred" 'sort_by((if .task_id == $preferred then 0 else 1 end), .requested_at // "") | .[0].task_id')"
            if [ -n "$START_TASK" ] && [ "$REQUESTED_TASK" != "$START_TASK" ]; then
                log_event skip requested-ticket-no-longer-pending
                return 1
            fi
            PENDING_REQUEST_SET="$(printf '%s' "$requests" \
                | jq -r '[.[] | "\(.task_id // "")@\(.requested_at // "")"] | sort | join(",")' 2>/dev/null \
                )"
            return 0 ;;
        3) return 1 ;;
        *) log_event error run-request-probe-failed; return 1 ;;
    esac
}

# The forced lane already dispatched for exactly these requests and none of
# them has been claimed or expired since: the button was honored once.
forced_request_set_already_dispatched() {
    [ -n "$PENDING_REQUEST_SET" ] || return 1
    [ -f "$FORCED_REQUEST_SET" ] || return 1
    [ "$(marker_age_seconds "$FORCED_REQUEST_SET")" -lt "$FORCED_REQUEST_TTL_SECONDS" ] || return 1
    [ "$(cat "$FORCED_REQUEST_SET" 2>/dev/null)" = "$PENDING_REQUEST_SET" ]
}

# Every lane shares one Codex login. After a usage-limit exit, a dispatched
# run pays its whole prelude and then dies in seconds; hold all lanes instead.
codex_backoff_active() {
    [ -x "$CODEX_BACKOFF" ] || return 1
    AUTOPR_DISPATCH_STATE_DIR="$STATE_DIR" "$CODEX_BACKOFF" active >/dev/null 2>&1
}

# A dead login is the same lane-wide condition with no resume time: the
# sandbox copy of auth.json is read-only and the refresh token is single-use,
# so only `codex login` on this Mac brings the lanes back. One local file read
# per tick, and nothing is launched to find out.
codex_auth_message=""
codex_auth_rc=0
codex_auth_required() {
    codex_auth_rc=0
    # Not 0: an absent or non-executable helper is the same install-drift class
    # this guard exists for, and returning "no expiry" with rc 0 made the
    # caller's "could not check" branch silent — a dispatcher that looks like
    # it verifies the login every tick and never does.
    [ -x "$CODEX_BACKOFF" ] || { codex_auth_rc=2; codex_auth_message="codex login: CANNOT CHECK: $CODEX_BACKOFF is missing or not executable"; return 1; }
    # Both LaunchAgents fire every 60s, and this sits above the watcher's
    # "nothing queued, exit" short-circuit — whose whole point is that an idle
    # tick costs one bounded query and nothing else. A JWT `exp` changes about
    # once every ten days, so spawning bash + python3 1,440 times a day to
    # re-read it is pure waste. Reuse the last verdict while it is fresh AND
    # the auth file has not been rewritten; `codex login` rewrites it, so a
    # repaired login is picked up on the very next tick rather than after the
    # TTL.
    local source_mtime cached_rc="" cached_path="" cached_mtime="" cached_message=""
    source_mtime="$(file_mtime "$HOST_CODEX_AUTH_FILE")"
    # Keyed on the exact file AND its mtime, not just the cache's own age:
    # `codex login` rewrites auth.json, so a repaired login invalidates this on
    # the very next tick instead of after the TTL.
    if [ -s "$CODEX_AUTH_CACHE" ] \
        && [ "$(marker_age_seconds "$CODEX_AUTH_CACHE")" -lt "$CODEX_AUTH_CACHE_SECONDS" ]; then
        IFS=$'\t' read -r cached_rc cached_path cached_mtime cached_message < "$CODEX_AUTH_CACHE" || true
        if [[ "$cached_rc" =~ ^[0-9]+$ ]] \
            && [ "$cached_path" = "$HOST_CODEX_AUTH_FILE" ] \
            && [ "$cached_mtime" = "$source_mtime" ]; then
            codex_auth_rc="$cached_rc"
            codex_auth_message="$cached_message"
            [ "$codex_auth_rc" -eq 4 ]
            return
        fi
    fi
    codex_auth_message="$("$CODEX_BACKOFF" auth-check 2>&1)" || codex_auth_rc=$?
    mkdir -p "$STATE_DIR" \
        && printf '%s\t%s\t%s\t%s\n' "$codex_auth_rc" "$HOST_CODEX_AUTH_FILE" "$source_mtime" \
            "${codex_auth_message//$'\t'/ }" > "$CODEX_AUTH_CACHE" \
        || true
    # ONLY 4 is "the credential is dead". A missing checker or a broken
    # interpreter is a harness fault, and holding every lane on one would be a
    # permanent silent stop whose banner tells the operator to run `codex
    # login` — which cannot clear it. Fail open there, exactly like
    # hot-redispatch-guard.sh: this is a spend guard, not a safety boundary.
    [ "$codex_auth_rc" -eq 4 ]
}

main() {
    local requested_mode=false
    [ "${1:-}" != "--if-requested" ] || requested_mode=true
    if [ "${1:-}" = --start ]; then
        START_TASK="${2:?task ID required}"
        [[ "$START_TASK" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]] || { echo 'invalid task ID' >&2; exit 2; }
        requested_mode=true
    fi
    if [ "$requested_mode" = true ]; then
        POLL_SECONDS=60
        touch_watch_heartbeat
    else
        mkdir -p "$STATE_DIR"
        : > "$STATE_DIR/last-scheduler-tick"
    fi
    [ -x "$GH_BIN" ] || { log_event error "gh-not-executable"; exit 1; }
    # `msandbox` remains the authoritative kill switch: it alone creates and
    # removes ENABLE_FILE. A persistent marker alone is insufficient after a
    # reboot/crash, so also require its primary workspace container to be live.
    if ! autopr_master_ready; then
        log_event skip msandbox-off
        # Once per off period: the container went down (sleep, crash, or a
        # deliberate stop) while the timer is still ticking.
        if [ ! -f "$NOTIFIED_OFF_FILE" ]; then
            mkdir -p "$STATE_DIR" && : > "$NOTIFIED_OFF_FILE"
            notify "AutoPR is off" "sandbox container down or master switch off · msandbox start"
        fi
        exit 0
    fi
    rm -f "$NOTIFIED_OFF_FILE"
    if codex_backoff_active; then
        log_event skip codex-usage-limit-backoff
        exit 0
    fi
    if codex_auth_required; then
        log_event skip codex-auth-required
        # Once per expiry: the token lapsed while the timer kept ticking.
        if [ ! -f "$NOTIFIED_AUTH_FILE" ]; then
            mkdir -p "$STATE_DIR" && : > "$NOTIFIED_AUTH_FILE"
            notify "Codex login expired" "${codex_auth_message:-run codex login on this Mac}"
        fi
        exit 0
    fi
    if [ "$codex_auth_rc" -ne 0 ]; then
        # Could not check. Say so in the log and keep going, rather than
        # silently grounding the lanes on a broken install.
        log_event error codex-auth-check-unavailable
    fi
    rm -f "$NOTIFIED_AUTH_FILE"
    # The watcher lane asks the board first and gives up before doing anything
    # else, so a minute-by-minute tick costs one bounded query against our own
    # API and nothing else. This runs BEFORE the dispatch lock and before the
    # dashboard-ensure pass on purpose: `mw_api` talks to a remote host, and a
    # stalled request must not hold the lock the five-minute scheduler needs,
    # nor re-prime the GitHub-reading observer panes sixty times an hour.
    if [ "$requested_mode" = true ]; then
        if [ -z "$START_TASK" ] && [ "$(marker_age_seconds "$FORCED_MARKER")" -lt "$FORCED_MIN_INTERVAL_SECONDS" ]; then
            exit 0
        fi
        if ! run_request_pending; then
            # Silent on the common path: an idle tick every minute would
            # otherwise bury the scheduler's own signal in the shared log the
            # dashboard reads, and grow the file five times as fast.
            touch_watch_heartbeat
            exit 0
        fi
        if [ -z "$START_TASK" ] && forced_request_set_already_dispatched; then
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
    # Recheck after acquiring ownership: a watcher may have dispatched while
    # this process was querying the board. Also bridge GitHub's visibility lag.
    if [ -n "$START_TASK" ]; then
        printf '%s' "$START_TASK" > "$PREFERRED_TASK_FILE"
    fi
    if [ "$requested_mode" = true ] && [ -z "$START_TASK" ] && forced_request_set_already_dispatched; then
        log_event skip request-already-dispatched
        exit 0
    fi
    if [ "$(marker_age_seconds "$STATE_DIR/last-dispatch")" -lt 60 ]; then
        log_event skip recent-dispatch-pending
        exit 0
    fi
    if [ "$requested_mode" != true ] && scheduler_idle_without_fetch; then
        log_event skip kanban-not-due
        exit 0
    fi

    local kanban_runs error_runs audit_runs all_runs workflow reason
    if [ ! -x "$RUN_SNAPSHOT" ] || ! all_runs="$(AUTOPR_REPO="$REPO" AUTOPR_REF="$REF" \
        AUTOPR_GH_BIN="$GH_BIN" AUTOPR_GITHUB_SNAPSHOT_ALLOW_STALE=false \
        AUTOPR_GITHUB_SNAPSHOT_TTL_SECONDS=0 "$RUN_SNAPSHOT")"; then
        # Fail closed: a blind dispatch could create a second queued coding job.
        log_event error run-snapshot-failed
        exit 1
    fi
    notify_run_outcomes "$all_runs"
    kanban_runs="$(printf '%s' "$all_runs" | jq -c '[.[] | select(.lane == "kanban")][0:20]')"
    error_runs="$(printf '%s' "$all_runs" | jq -c '[.[] | select(.lane == "errors")][0:20]')"
    audit_runs="$(printf '%s' "$all_runs" | jq -c '[.[] | select(.lane == "self-audit")][0:20]')"
    local last_completed
    last_completed="$(printf '%s' "$kanban_runs" | jq -r '[.[] | select(.status == "completed") | (.updatedAt // .createdAt)] | max // empty')"
    if [ -n "$last_completed" ]; then
        NEXT_ELIGIBLE_AT=$(( $(iso_to_epoch "$last_completed") + KANBAN_MAX_AGE_SECONDS ))
    fi
    if has_active_workflow_run "$all_runs"; then
        # Name the active run(s) only. Embedding the whole 20-run snapshot
        # made every such row up to 30 KB (1.3 MB/day, a rotation every four
        # days) and nothing reads more than the id and lane back out.
        log_event skip active-autopr-workflow \
            "$(printf '%s' "$all_runs" | jq -c '[.[] | select(.status != "completed") | {databaseId, lane, status}]')"
        exit 0
    fi

    if [ "$requested_mode" = true ]; then
        # A verified live request is passed as an exact workflow input. It
        # bypasses the routine-only spend floor, never the active-run lock.
        NEXT_ELIGIBLE_AT=0
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
    : > "$STATE_DIR/last-dispatch"
    notify "Run dispatched" "${workflow%.yml} · $reason"
    if [ "$requested_mode" = true ] \
        && ! { mkdir -p "$STATE_DIR" && : > "$FORCED_MARKER" \
               && printf '%s' "$PENDING_REQUEST_SET" > "$FORCED_REQUEST_SET"; }; then
        # Without the marker the floor between two forced dispatches is gone,
        # so this is worth a log line rather than an `set -e` exit that leaves
        # no trace of why the watcher stopped behaving.
        log_event error forced-marker-write-failed
    fi
    [ -z "$REQUESTED_TASK" ] || rm -f "$PREFERRED_TASK_FILE"
    log_event dispatch "$reason"
}

main "$@"
