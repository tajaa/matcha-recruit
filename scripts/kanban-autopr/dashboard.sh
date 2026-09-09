#!/usr/bin/env bash
# Read-only operator board for the Kanban AutoPR tmux session. The overview
# separates current work, exact next work, blocked queue entries, PR timing,
# and recent outcomes. Every external source is labelled live/stale/unavailable
# so an API failure can never masquerade as an empty queue.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
WORKFLOW="${AUTOPR_WORKFLOW:-kanban-autopr.yml}"
ERROR_WORKFLOW="${AUTOPR_ERROR_WORKFLOW:-silent-error-autofix.yml}"
AUDIT_WORKFLOW="${AUTOPR_AUDIT_WORKFLOW:-autopr-self-audit.yml}"
ADMIN_UPDATES_WORKFLOW="${AUTOPR_ADMIN_UPDATES_WORKFLOW:-admin-updates-autopublish.yml}"
REF="${AUTOPR_REF:-main}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
GIT_BIN="${AUTOPR_GIT_BIN:-/usr/bin/git}"
# Four live panes share one GitHub token. A 30-second overview plus the detail
# panes could exhaust the hourly core budget and prevent workflow dispatch.
REFRESH_SECONDS="${AUTOPR_DASHBOARD_REFRESH_SECONDS:-60}"
# GitHub is rate-limited per hour and these panes are read by a human a few
# times a day. Redraw on the same cadence, but only re-ask GitHub this often.
PR_LIST_TTL_SECONDS="${AUTOPR_DASHBOARD_PR_TTL_SECONDS:-300}"
BOARD_TTL_SECONDS="${AUTOPR_DASHBOARD_BOARD_TTL_SECONDS:-180}"
# The active run's step line is the one thing worth refreshing quickly, and
# only while a run is actually in flight.
RUN_DETAIL_TTL_SECONDS="${AUTOPR_DASHBOARD_RUN_DETAIL_TTL_SECONDS:-45}"
# The selector re-asks GitHub about every candidate card, so it is the most
# expensive probe on the board. Its answer changes on run boundaries, not
# between two redraws.
SELECT_TTL_SECONDS="${AUTOPR_DASHBOARD_SELECT_TTL_SECONDS:-300}"
PACIFIC_TZ="${AUTOPR_DASHBOARD_TZ:-America/Los_Angeles}"
RUNNER_WORKTREE="${AUTOPR_RUNNER_WORKTREE:-$USER_HOME/.local/share/matcha-actions-runner/_work/matcha-recruit/matcha-recruit}"
CACHE_DIR="${AUTOPR_DASHBOARD_CACHE_DIR:-$USER_HOME/Library/Caches/matcha-kanban-autopr/dashboard}"
CARD_SNAPSHOT="${AUTOPR_CARD_SNAPSHOT:-$USER_HOME/Library/Caches/matcha-kanban-autopr/cards.json}"
DISPATCH_LOG="${AUTOPR_DISPATCH_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log}"
PLAN_PY="${AUTOPR_PLAN_PY:-$SCRIPT_DIR/plan.py}"
RUN_SNAPSHOT="${AUTOPR_RUN_SNAPSHOT:-$SCRIPT_DIR/run-snapshot.sh}"

# Calm, high-contrast terminal palette. Color is enabled only for an interactive
# terminal (or explicitly with AUTOPR_DASHBOARD_COLOR=1), so redirected logs and
# tests remain clean plain text. NO_COLOR always wins.
TUI_COLOR=false
case "${AUTOPR_DASHBOARD_COLOR:-auto}" in
    1|always|true) TUI_COLOR=true ;;
    0|never|false) TUI_COLOR=false ;;
    *) [ -t 1 ] && [ "${TERM:-dumb}" != dumb ] && TUI_COLOR=true ;;
esac
[ -z "${NO_COLOR:-}" ] || TUI_COLOR=false

if [ "$TUI_COLOR" = true ]; then
    C_RESET=$'\033[0m'
    C_BOLD=$'\033[1m'
    C_BRAND=$'\033[38;5;157m'
    C_ACCENT=$'\033[38;5;80m'
    C_BLUE=$'\033[38;5;75m'
    C_GOOD=$'\033[38;5;114m'
    C_WARN=$'\033[38;5;221m'
    C_BAD=$'\033[38;5;203m'
    C_TEXT=$'\033[38;5;255m'
    C_MUTED=$'\033[38;5;245m'
    C_RAIL=$'\033[38;5;239m'
else
    C_RESET='' C_BOLD='' C_BRAND='' C_ACCENT='' C_BLUE=''
    C_GOOD='' C_WARN='' C_BAD='' C_TEXT='' C_MUTED='' C_RAIL=''
fi

tui_width() {
    local width
    # COLUMNS is often the 80-column value inherited when launchd created the
    # detached session; tput reflects the pane after a real client attaches.
    width="$(tput cols 2>/dev/null || printf '%s' "${COLUMNS:-80}")"
    [[ "$width" =~ ^[0-9]+$ ]] || width=80
    [ "$width" -ge 40 ] 2>/dev/null || width=40
    [ "$width" -le 100 ] 2>/dev/null || width=100
    printf '%s' "$width"
}

tui_rule() {
    local width i
    width="$(tui_width)"
    printf '%b' "$C_RAIL"
    for ((i = 0; i < width; i++)); do printf '─'; done
    printf '%b\n' "$C_RESET"
}

section_heading() {
    printf '\n%b◆ %s%b\n' "$C_BRAND$C_BOLD" "$1" "$C_RESET"
}

badge_style() {
    case "$1" in
        NOW|ACTIVE|SUCCESS|READY|LIVE) printf '%s' "$C_GOOD$C_BOLD" ;;
        FEEDBACK|REWORK|RUNNING|IN_PROGRESS|VERIFYING|INVESTIGATING) printf '%s' "$C_BLUE$C_BOLD" ;;
        WAITING|HELD|CONTEXT|DRAFT|UNKNOWN|STALE) printf '%s' "$C_WARN$C_BOLD" ;;
        FAILURE|FAILED|ERROR|CANCELLED|DEGRADED) printf '%s' "$C_BAD$C_BOLD" ;;
        TODO|IDLE) printf '%s' "$C_MUTED$C_BOLD" ;;
        *) printf '%s' "$C_ACCENT$C_BOLD" ;;
    esac
}

dashboard_now_epoch() {
    printf '%s\n' "${AUTOPR_DASHBOARD_NOW_EPOCH:-$(date +%s)}"
}

utc_24_hours_ago() {
    date -u -v-24H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ
}

iso_to_epoch() {
    local value="$1"
    [ -n "$value" ] || return 1
    date -u -j -f '%Y-%m-%dT%H:%M:%SZ' "$value" +%s 2>/dev/null \
        || date -u -d "$value" +%s 2>/dev/null
}

epoch_to_pacific() {
    local epoch="$1" rendered
    if date --version >/dev/null 2>&1; then
        rendered="$(TZ="$PACIFIC_TZ" date -d "@$epoch" '+%I:%M %p %Z' 2>/dev/null)"
    else
        rendered="$(TZ="$PACIFIC_TZ" date -r "$epoch" '+%I:%M %p %Z' 2>/dev/null)"
    fi
    printf '%s\n' "$rendered" | sed 's/^0//'
}

iso_to_pacific() {
    local epoch
    epoch="$(iso_to_epoch "$1" 2>/dev/null)" || { printf '?'; return; }
    epoch_to_pacific "$epoch"
}

format_duration_seconds() {
    local total="$1" days hours minutes seconds
    [ "$total" -ge 0 ] 2>/dev/null || total=0
    days=$((total / 86400))
    hours=$(((total % 86400) / 3600))
    minutes=$(((total % 3600) / 60))
    seconds=$((total % 60))
    if [ "$days" -gt 0 ]; then
        printf '%sd %sh' "$days" "$hours"
    elif [ "$hours" -gt 0 ]; then
        printf '%sh %sm' "$hours" "$minutes"
    elif [ "$minutes" -gt 0 ]; then
        printf '%sm %ss' "$minutes" "$seconds"
    else
        printf '%ss' "$seconds"
    fi
}

duration_between() {
    local start end start_epoch end_epoch
    start="$1"
    end="$2"
    start_epoch="$(iso_to_epoch "$start" 2>/dev/null)" || { printf '?'; return; }
    if [ -n "$end" ]; then
        end_epoch="$(iso_to_epoch "$end" 2>/dev/null)" || { printf '?'; return; }
    else
        end_epoch="$(dashboard_now_epoch)"
    fi
    format_duration_seconds $((end_epoch - start_epoch))
}

cache_age_seconds() {
    local path="$1" modified now age
    modified="$(stat -c %Y "$path" 2>/dev/null || stat -f %m "$path" 2>/dev/null || printf 0)"
    now="$(dashboard_now_epoch)"
    age=$((now - modified))
    [ "$age" -ge 0 ] 2>/dev/null || age=0
    printf '%s' "$age"
}

cache_age() {
    format_duration_seconds "$(cache_age_seconds "$1")"
}

# fetch_json DATA_VAR STATE_VAR CACHE_KEY TTL_SECONDS COMMAND...
# TTL 0 means "always ask" (the run snapshot already has its own TTL).
# STATE is "live", "stale <age>", or "unavailable". Last-known-good data is
# deliberately retained during transient GitHub/board failures.
fetch_json() {
    local data_var="$1" state_var="$2" key="$3" ttl="$4" output cache tmp state age
    shift 4
    cache="$CACHE_DIR/$key.json"
    # Observer freshness, not dispatch freshness: within TTL the pane redraws
    # from its own cache instead of spending another GitHub request. The
    # dispatcher never reads these files.
    if [ "$ttl" -gt 0 ] 2>/dev/null && [ -s "$cache" ]; then
        age="$(cache_age_seconds "$cache")"
        if [ "$age" -lt "$ttl" ] 2>/dev/null \
            && jq -e 'type == "array" or type == "object"' "$cache" >/dev/null 2>&1; then
            printf -v "$data_var" '%s' "$(<"$cache")"
            printf -v "$state_var" '%s' live
            return
        fi
    fi
    if output="$("$@" 2>/dev/null)" \
        && printf '%s' "$output" | jq -e 'type == "array" or type == "object"' >/dev/null 2>&1; then
        state=live
        if mkdir -p "$CACHE_DIR" 2>/dev/null; then
            tmp="$cache.$$"
            if (umask 077; printf '%s' "$output" > "$tmp") 2>/dev/null; then
                mv "$tmp" "$cache" 2>/dev/null || true
            fi
        fi
    elif [ -s "$cache" ] && jq -e 'type == "array" or type == "object"' "$cache" >/dev/null 2>&1; then
        output="$(<"$cache")"
        state="stale $(cache_age "$cache")"
    else
        output='[]'
        state=unavailable
    fi
    printf -v "$data_var" '%s' "$output"
    printf -v "$state_var" '%s' "$state"
}

write_card_snapshot() {
    local cards="$1" snapshot_tmp
    if mkdir -p "$(dirname "$CARD_SNAPSHOT")" 2>/dev/null; then
        snapshot_tmp="$CARD_SNAPSHOT.$$"
        if (umask 077; printf '%s' "$cards" > "$snapshot_tmp") 2>/dev/null; then
            mv "$snapshot_tmp" "$CARD_SNAPSHOT" 2>/dev/null || true
        fi
    fi
}

runner_task_branch() {
    local branch
    "$GIT_BIN" -C "$RUNNER_WORKTREE" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
    branch="$("$GIT_BIN" -C "$RUNNER_WORKTREE" branch --show-current 2>/dev/null || true)"
    [[ "$branch" == bot/task-* ]] || return 1
    printf '%s\n' "$branch"
}

phase_label() {
    case "$1" in
        *Collect*candidate*|*Select*card*) printf 'SELECTING' ;;
        *Create*branch*) printf 'STARTING' ;;
        *Investigate*) printf 'INVESTIGATING' ;;
        *cover*this*task*|*Link*covering*) printf 'DUPLICATE CHECK' ;;
        *Verify*) printf 'VERIFYING' ;;
        *commit*subject*|*card*note*) printf 'WRITING UPDATE' ;;
        *Publish*) printf 'PUBLISHING' ;;
        *Cleanup*) printf 'CLEANUP' ;;
        '') printf 'RUNNING' ;;
        *) printf '%s' "$1" ;;
    esac
}

render_dashboard() {
    local cutoff kanban_runs error_runs audit_runs admin_updates_runs runs
    local open_kanban open_errors open_audits open_prs merged_prs cards bot_prs plan selected selected_rc
    local kanban_state error_state audit_state admin_state open_kanban_state open_errors_state
    local open_audits_state merged_state board_state bot_pr_state plan_state all_states source_state source_style
    local selected_cache empty_marker
    local active run_id run_lane run_status run_created run_title run_elapsed run_started current_id8=""
    local run_details run_details_state step_line phase branch id8 active_card project card_title
    local dispatch_line dispatch_ts dispatch_action dispatch_reason dispatch_time
    local queue_counts row_badge row_project row_title row_time row_when row_iso row_symbol
    local pr_number pr_lane pr_state pr_title pr_created pr_flag
    local merged_number merged_lane merged_title merged_created merged_at merged_verification
    local recent_id recent_lane recent_result recent_created recent_updated
    local plan_input_dir plan_id plan_merge_count plan_release_blockers plan_position plan_number plan_title plan_blocked

    cutoff="$(utc_24_hours_ago)"
    fetch_json runs kanban_state runs-all 0 env AUTOPR_REPO="$REPO" AUTOPR_REF="$REF" \
        AUTOPR_GH_BIN="$GH_BIN" "$RUN_SNAPSHOT"
    error_state="$kanban_state"
    audit_state="$kanban_state"
    admin_state="$kanban_state"
    kanban_runs="$(printf '%s' "$runs" | jq -c '[.[] | select(.lane == "kanban")]')"
    error_runs="$(printf '%s' "$runs" | jq -c '[.[] | select(.lane == "errors")]')"
    audit_runs="$(printf '%s' "$runs" | jq -c '[.[] | select(.lane == "self-audit")]')"
    admin_updates_runs="$(printf '%s' "$runs" | jq -c '[.[] | select(.lane == "admin-updates")]')"

    fetch_json open_kanban open_kanban_state prs-open-kanban "$PR_LIST_TTL_SECONDS" "$GH_BIN" pr list --repo "$REPO" \
        --state open --label autopr --limit 100 \
        --json number,title,isDraft,headRefName,createdAt,updatedAt,labels,url
    fetch_json open_errors open_errors_state prs-open-errors "$PR_LIST_TTL_SECONDS" "$GH_BIN" pr list --repo "$REPO" \
        --state open --label autofix --limit 100 \
        --json number,title,isDraft,headRefName,createdAt,updatedAt,labels,url
    fetch_json open_audits open_audits_state prs-open-audits "$PR_LIST_TTL_SECONDS" "$GH_BIN" pr list --repo "$REPO" \
        --state open --label autopr-self-audit --limit 100 \
        --json number,title,isDraft,headRefName,createdAt,updatedAt,labels,url
    open_prs="$(jq -cn --argjson kanban "$open_kanban" --argjson errors "$open_errors" \
        --argjson audit "$open_audits" '$kanban + $errors + $audit | unique_by(.number) | sort_by(.updatedAt // "") | reverse')"
    fetch_json merged_prs merged_state prs-merged "$PR_LIST_TTL_SECONDS" "$GH_BIN" pr list --repo "$REPO" \
        --state merged --limit 100 \
        --json number,title,createdAt,mergedAt,headRefName,labels,url

    fetch_json cards board_state board-cards "$BOARD_TTL_SECONDS" "$SCRIPT_DIR/collect.sh"
    fetch_json bot_prs bot_pr_state bot-pr-context "$PR_LIST_TTL_SECONDS" env GITHUB_REPOSITORY="$REPO" \
        "$SCRIPT_DIR/collect-pr-context.sh"
    plan='{"schema_version":1,"plan_id":"unavailable","work_order":[],"merge_order":[],"release_blockers":[],"ready_prs_excluded":[]}'
    plan_state=unavailable
    plan_input_dir="$CACHE_DIR/plan-input"
    if [ "$board_state" = live ] && [ "$bot_pr_state" = live ] \
        && mkdir -p "$plan_input_dir" 2>/dev/null \
        && (umask 077; printf '%s' "$cards" > "$plan_input_dir/cards.json") 2>/dev/null \
        && (umask 077; printf '%s' "$bot_prs" > "$plan_input_dir/prs.json") 2>/dev/null \
        && python3 "$PLAN_PY" \
            --cards "$plan_input_dir/cards.json" \
            --prs "$plan_input_dir/prs.json" \
            --output "$plan_input_dir/plan.json" \
            --cards-output "$plan_input_dir/planned-cards.json" 2>/dev/null \
        && jq -e '.schema_version == 1' "$plan_input_dir/plan.json" >/dev/null 2>&1 \
        && jq -e 'type == "array"' "$plan_input_dir/planned-cards.json" >/dev/null 2>&1; then
        plan="$(<"$plan_input_dir/plan.json")"
        cards="$(<"$plan_input_dir/planned-cards.json")"
        plan_state=live
    fi
    write_card_snapshot "$cards"
    # The selector asks GitHub about every candidate card, so it is the most
    # expensive probe here. Cache its answer: what it would pick next changes
    # on run boundaries, not between two redraws. An empty answer ("nothing to
    # do") is cached as an explicit marker so it does not re-run every tick.
    selected=""
    # Default to "failed" so no path below can render a selector verdict it
    # never actually obtained.
    selected_rc=1
    selected_cache="$CACHE_DIR/next-selection.json"
    # The cached answer carries the selector's exit status with it. Rendering
    # reads that status (0 = a pick, 3 = nothing eligible, anything else =
    # failed), so a warm cache hit must restore it too — otherwise every
    # redraw inside the TTL reports a healthy selector as broken.
    empty_marker='if type == "object" and (has("autopr_dashboard_rc") or (.autopr_dashboard_empty // false)) then true else false end'
    if [ -s "$selected_cache" ] \
        && [ "$(cache_age_seconds "$selected_cache")" -lt "$SELECT_TTL_SECONDS" ] 2>/dev/null; then
        if [ "$(jq -r "$empty_marker" "$selected_cache" 2>/dev/null || printf false)" = true ]; then
            selected_rc="$(jq -r '.autopr_dashboard_rc // 3' "$selected_cache" 2>/dev/null || printf 3)"
            [[ "$selected_rc" =~ ^[0-9]+$ ]] || selected_rc=3
        else
            selected="$(jq -r 'tojson' "$selected_cache" 2>/dev/null || printf '')"
            [ -z "$selected" ] || selected_rc=0
        fi
    else
        selected="$(AUTOPR_SELECT_READ_ONLY=true GITHUB_REPOSITORY="$REPO" \
            "$SCRIPT_DIR/select.sh" <(printf '%s' "$cards") 2>/dev/null)"
        selected_rc=$?
        [ "$selected_rc" -eq 0 ] || selected=""
        # Only a definitive verdict is cacheable. A selector FAILURE (rate
        # limit, crash) stored as the empty marker would be served for the
        # next five minutes as "nothing to do" — the opposite of the
        # last-known-good policy every other source on this board follows.
        if { [ "$selected_rc" -eq 0 ] || [ "$selected_rc" -eq 3 ]; } \
            && mkdir -p "$CACHE_DIR" 2>/dev/null; then
            if [ -n "$selected" ]; then
                (umask 077; printf '%s' "$selected" > "$selected_cache") 2>/dev/null || true
            else
                (umask 077; printf '{"autopr_dashboard_rc":3}' > "$selected_cache") 2>/dev/null || true
            fi
        fi
    fi

    all_states="$kanban_state $error_state $audit_state $admin_state $open_kanban_state $open_errors_state $open_audits_state $merged_state $board_state $bot_pr_state $plan_state"
    if [[ "$all_states" == *unavailable* ]]; then
        source_state='DEGRADED · source unavailable'
    elif [[ "$all_states" == *stale* ]]; then
        source_state='STALE · showing last-known-good data'
    else
        source_state='LIVE'
    fi

    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf '%b╭─ %bMATCHA AUTOPR CONTROL BOARD%b\n' "$C_RAIL" "$C_BRAND$C_BOLD" "$C_RESET"
    case "$source_state" in
        LIVE) source_style="$C_GOOD$C_BOLD" ;;
        STALE*) source_style="$C_WARN$C_BOLD" ;;
        *) source_style="$C_BAD$C_BOLD" ;;
    esac
    printf '%b│%b %s  %b● %s%b  %b↻ %ss%b\n' \
        "$C_RAIL" "$C_RESET" \
        "$(TZ="$PACIFIC_TZ" date '+%a %b %-d · %-I:%M:%S %p %Z' 2>/dev/null \
          || TZ="$PACIFIC_TZ" date '+%a %b %d · %I:%M:%S %p %Z')" \
        "$source_style" "$source_state" "$C_RESET" "$C_MUTED" "$REFRESH_SECONDS" "$C_RESET"

    # The one-minute request watcher shares this log with the five-minute
    # scheduler. Its idle ticks are bookkeeping, not a scheduling signal, so
    # skip them here (and in older logs that still carry them) rather than
    # letting them mask the scheduler's real last action.
    dispatch_line="$(tail -n 400 "$DISPATCH_LOG" 2>/dev/null \
        | grep -v '"reason":"no-run-request"' | tail -n 1 || true)"
    dispatch_ts="$(printf '%s' "$dispatch_line" | jq -r '.timestamp // empty' 2>/dev/null)"
    dispatch_action="$(printf '%s' "$dispatch_line" | jq -r '.action // empty' 2>/dev/null)"
    dispatch_reason="$(printf '%s' "$dispatch_line" | jq -r '.reason // empty' 2>/dev/null)"
    dispatch_time="$(iso_to_pacific "$dispatch_ts")"
    if [ -n "$dispatch_action" ]; then
        printf '%b│%b %bSCHEDULER%b  %s · %b%s%b · %s\n' \
            "$C_RAIL" "$C_RESET" "$C_MUTED$C_BOLD" "$C_RESET" "$dispatch_time" \
            "$C_ACCENT" "$dispatch_action" "$C_RESET" "$dispatch_reason"
    else
        printf '%b│%b %bSCHEDULER%b  last signal unavailable\n' \
            "$C_RAIL" "$C_RESET" "$C_MUTED$C_BOLD" "$C_RESET"
    fi
    tui_rule

    active="$(printf '%s' "$runs" | jq -c \
        '[.[] | select(.status | IN("queued", "in_progress", "requested", "waiting", "pending"))][0] // {}')"
    run_id="$(printf '%s' "$active" | jq -r '.databaseId // empty')"
    if [ -n "$run_id" ]; then
        run_lane="$(printf '%s' "$active" | jq -r '.lane // "?"')"
        run_status="$(printf '%s' "$active" | jq -r '.status // "?"')"
        run_created="$(printf '%s' "$active" | jq -r '.createdAt // empty')"
        run_title="$(printf '%s' "$active" | jq -r '.displayTitle // empty')"
        run_elapsed="$(duration_between "$run_created" '')"
        run_started="$(iso_to_pacific "$run_created")"
        fetch_json run_details run_details_state "run-$run_id" "$RUN_DETAIL_TTL_SECONDS" "$GH_BIN" run view "$run_id" --repo "$REPO" --json jobs
        step_line="$(printf '%s' "$run_details" | jq -r '
          [.jobs[]? as $job | $job.steps[]? | select(.status == "in_progress") | ($job.name + " · " + .name)][0] // empty
        ' 2>/dev/null)"
        phase="$(phase_label "${step_line#* · }")"
        section_heading "NOW · $phase · $run_elapsed"
        printf '  %b●%b %b%s%b run %b#%s%b · %s · started %s\n' \
            "$C_GOOD" "$C_RESET" "$C_TEXT$C_BOLD" \
            "$(printf '%s' "$run_lane" | tr '[:lower:]' '[:upper:]')" "$C_RESET" \
            "$C_ACCENT" "$run_id" "$C_RESET" "$run_status" "$run_started"
        branch="$(runner_task_branch 2>/dev/null || true)"
        if [ "$run_lane" = kanban ] && [ -n "$branch" ]; then
            id8="${branch#bot/task-}"
            current_id8="$id8"
            active_card="$(printf '%s' "$cards" | jq -c --arg id8 "$id8" '[.[] | select(.id8 == $id8)][0] // {}')"
            project="$(printf '%s' "$active_card" | jq -r '.project_title // "MATCHA"')"
            card_title="$(printf '%s' "$active_card" | jq -r '.title // empty')"
            printf '  %b%s%b · %s\n' "$C_ACCENT$C_BOLD" "$project" "$C_RESET" "${card_title:-task $id8}"
            printf '  %bbranch%b %s\n' "$C_MUTED" "$C_RESET" "$branch"
        elif [ -n "$run_title" ]; then
            printf '  %s\n' "$run_title"
        fi
    else
        printf '\n%b◆ NOW · IDLE%b\n' "$C_MUTED$C_BOLD" "$C_RESET"
        printf '  %b○%b No workflow is currently queued or running.\n' "$C_MUTED" "$C_RESET"
    fi

    plan_id="$(printf '%s' "$plan" | jq -r '.plan_id // "unavailable"')"
    section_heading "PLAN · $plan_id · NOT-READY PRS ONLY"
    if [ "$plan_state" != live ]; then
        printf '  %b! unavailable%b · existing queue remains visible below\n' "$C_WARN$C_BOLD" "$C_RESET"
    else
        printf '  %bWORK ORDER%b\n' "$C_MUTED$C_BOLD" "$C_RESET"
        printf '%s' "$plan" | jq -r '.work_order[:5][] |
          [(.position | tostring), .cluster_id, (if .blocked then "CONTEXT" elif .board_column == "changes_requested" then "REWORK" else "TODO" end), (.title[0:52])] | @tsv
        ' | while IFS=$'\t' read -r plan_position row_project row_badge plan_title; do
            printf '    %b%-2s%b %-4s %b%-8s%b %s\n' \
                "$C_ACCENT$C_BOLD" "$plan_position" "$C_RESET" "$row_project" \
                "$(badge_style "$row_badge")" "$row_badge" "$C_RESET" "$plan_title"
        done
        plan_merge_count="$(printf '%s' "$plan" | jq '.merge_order | length')"
        printf '  %bMERGE ORDER%b · %s draft(s)\n' "$C_MUTED$C_BOLD" "$C_RESET" "$plan_merge_count"
        if [ "$plan_merge_count" -eq 0 ]; then
            printf '    none · PRs already ready for review are deliberately excluded\n'
        else
            printf '%s' "$plan" | jq -r '.merge_order[:6][] |
              [(.position | tostring), (.pr_number | tostring), (.title[0:48]),
               (((.blockers // []) + ([.context_dependencies[]?.state])) | join(", "))] | @tsv
            ' | while IFS=$'\t' read -r plan_position plan_number plan_title plan_blocked; do
                printf '    %-2s #%-4s %-48s%s\n' "$plan_position" "$plan_number" "$plan_title" "${plan_blocked:+ · BLOCKED: $plan_blocked}"
            done
        fi
        plan_release_blockers="$(printf '%s' "$plan" | jq '.release_blockers | length')"
        if [ "$plan_merge_count" -gt 0 ] && [ "$plan_release_blockers" -eq 0 ]; then
            printf '  %bREADY TO RELEASE%b · gh workflow run autopr-release-plan.yml -f plan_id=%s\n' \
                "$C_GOOD$C_BOLD" "$C_RESET" "$plan_id"
        elif [ "$plan_release_blockers" -gt 0 ]; then
            printf '  %bRELEASE BLOCKED%b · %s unresolved review/check/context condition(s)\n' \
                "$C_WARN$C_BOLD" "$C_RESET" "$plan_release_blockers"
        fi
    fi

    if [ "$selected_rc" -eq 0 ] && [ -n "$selected" ]; then
        section_heading 'NEXT · EXACT SELECTOR RESULT'
        printf '%s' "$selected" | jq -r '
          "  " + (.project_title // "?") + " · " + .title,
          "  " + (if .mode == "research" then
                    (if .board_column == "changes_requested" then "research revision" else "research report" end)
                  elif .board_column == "changes_requested" then "rework" else "new work" end)
               + " · task " + .id8
        '
    elif [ "$selected_rc" -eq 3 ]; then
        section_heading 'NEXT · NONE ELIGIBLE AFTER CURRENT WORK'
        printf '  %b○%b Queue entries below may be waiting, held, or cooling down.\n' "$C_MUTED" "$C_RESET"
    else
        section_heading 'NEXT · UNKNOWN'
        printf '  %b! Selector failed (exit %s)%b; this does not mean the queue is empty.\n' \
            "$C_BAD$C_BOLD" "$selected_rc" "$C_RESET"
    fi
    # Cards the selector passed over because their board lacks a grant. The
    # selector leaves this hint on every pass (read-only ones included); it is
    # the one "held" a person can fix, so name it rather than folding it into
    # "waiting, held, or cooling down".
    ungranted_hints="$(cat "${AUTOPR_CACHE_DIR:-$USER_HOME/.cache/matcha-autopr}/ungranted.json" 2>/dev/null || printf '[]')"
    printf '%s' "$ungranted_hints" | jq -r --arg cutoff "$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)" '
      if type == "array" then
        [.[] | select((.ts // "") >= $cutoff)][:4][]
        | "  held: task " + .id8 + " needs the `" + .capability + "` board grant (Admin → Settings → AutoPR board capabilities)"
      else empty end' 2>/dev/null || true

    queue_counts="$(printf '%s' "$cards" | jq -r --arg current_id8 "$current_id8" '
      def pending: (.autopr_reconsideration_pending // false);
      def waiting: ((.progress_note // "") | test("awaiting answers"; "i"));
      def held: ((.progress_note // "") | contains("[autopr:no-spec ")) and (pending | not);
      "\(length) tracked · \([.[] | select(.id8 == $current_id8)] | length) active · \([.[] | select(pending and .id8 != $current_id8)] | length) feedback · \([.[] | select(waiting and .id8 != $current_id8)] | length) waiting · \([.[] | select(held and .id8 != $current_id8)] | length) held"
    ')"
    section_heading "QUEUE · $queue_counts"
    printf '%s' "$cards" | jq -r --arg current_id8 "$current_id8" '
      def pending: (.autopr_reconsideration_pending // false);
      def waiting: ((.progress_note // "") | test("awaiting answers"; "i"));
      def held: ((.progress_note // "") | contains("[autopr:no-spec ")) and (pending | not);
      sort_by(
        (if .id8 == $current_id8 then 0 elif pending then 1 elif .board_column == "changes_requested" then 2 else 3 end),
        (.last_moved_at // .created_at)
      )[:6][] |
      [(if .id8 == $current_id8 then "NOW" elif pending then "FEEDBACK" elif waiting then "WAITING" elif held then "HELD" elif .board_column == "changes_requested" then "REWORK" else "TODO" end),
       (.project_title // "?"), (.title[0:42]), (.last_moved_at // .created_at // "")] | @tsv
    ' | while IFS=$'\t' read -r row_badge row_project row_title row_when; do
        row_iso="$row_when"
        case "$row_iso" in
            *.*) row_iso="${row_iso%%.*}Z" ;;
            *+00:00) row_iso="${row_iso%+00:00}Z" ;;
        esac
        row_time="$(iso_to_pacific "$row_iso")"
        case "$row_badge" in
            NOW) row_symbol='▶' ;;
            FEEDBACK) row_symbol='↺' ;;
            REWORK) row_symbol='↻' ;;
            WAITING) row_symbol='?' ;;
            HELD) row_symbol='!' ;;
            *) row_symbol='○' ;;
        esac
        printf '  %b%s %-8s%b %-9s %-42s %b%s%b\n' \
            "$(badge_style "$row_badge")" "$row_symbol" "$row_badge" "$C_RESET" \
            "$row_project" "$row_title" "$C_MUTED" "$row_time" "$C_RESET"
    done
    [ "$(printf '%s' "$cards" | jq 'length')" -gt 0 ] || printf '  No cards, or the board source is unavailable.\n'

    section_heading 'OPEN BOT PRS · AGE'
    if [ "$(printf '%s' "$open_prs" | jq 'length')" -eq 0 ]; then
        printf '  none\n'
    else
        printf '%s' "$open_prs" | jq -r '.[:6][] |
          [(.number | tostring),
           (if ([.labels[].name] | index("autopr")) then "KANBAN" elif ([.labels[].name] | index("autofix")) then "ERROR" else "AUDIT" end),
           (if .isDraft then "DRAFT" else "OPEN" end),
           (.title[0:35]), (.createdAt // ""),
           (if ([.labels[].name] | index("autopr-awaiting-input")) then "WAITING" elif ([.labels[].name] | index("needs-work")) then "NEEDS WORK" else "" end)] | @tsv
        ' | while IFS=$'\t' read -r pr_number pr_lane pr_state pr_title pr_created pr_flag; do
            printf '  %b#%-4s%b %-6s %b%-5s%b %-35s %b%8s%b%s\n' \
                "$C_ACCENT$C_BOLD" "$pr_number" "$C_RESET" "$pr_lane" \
                "$(badge_style "$pr_state")" "$pr_state" "$C_RESET" "$pr_title" \
                "$C_MUTED" "$(duration_between "$pr_created" '')" "$C_RESET" "${pr_flag:+ · $pr_flag}"
        done
    fi

    section_heading 'RECENT BOT PRS · OPEN → MERGE · PACIFIC'
    printf '%s' "$merged_prs" | jq -r --arg cutoff "$cutoff" '
      [.[] | select((.mergedAt // "") >= $cutoff) |
        select([.labels[].name] | any(. == "autopr" or . == "autofix" or . == "autopr-self-audit"))]
      | sort_by(.mergedAt) | reverse | .[:5][] |
      [(.number | tostring),
       (if ([.labels[].name] | index("autopr")) then "KANBAN" elif ([.labels[].name] | index("autofix")) then "ERROR" else "AUDIT" end),
       (.title[0:40]), (.createdAt // ""), (.mergedAt // ""),
       (if ([.labels[].name] | index("autopr") | not) then ""
        elif ([.labels[].name] | index("production-verified")) then "PROD VERIFIED"
        elif ([.labels[].name] | index("production-verification-failed")) then "PROD FAILED"
        elif ([.labels[].name] | index("production-verification-needed")) then "PROD CHECK NEEDED"
        else "AWAITING DEPLOY/CHECK" end)] | @tsv
    ' | while IFS=$'\t' read -r merged_number merged_lane merged_title merged_created merged_at merged_verification; do
        printf '  %b#%-4s%b %-6s %-40s %b%8s · %s%b%s\n' \
            "$C_ACCENT$C_BOLD" "$merged_number" "$C_RESET" "$merged_lane" "$merged_title" \
            "$C_MUTED" "$(duration_between "$merged_created" "$merged_at")" "$(iso_to_pacific "$merged_at")" "$C_RESET" \
            "${merged_verification:+ · $merged_verification}"
    done

    section_heading 'RECENT RUNS · DURATION · PACIFIC'
    printf '%s' "$runs" | jq -r --arg cutoff "$cutoff" '
      [.[] | select(.status == "completed" and (.createdAt // "") >= $cutoff)][:5][] |
      [(.databaseId | tostring), .lane, (.conclusion // "completed"), (.createdAt // ""), (.updatedAt // "")] | @tsv
    ' | while IFS=$'\t' read -r recent_id recent_lane recent_result recent_created recent_updated; do
        printf '  %b%-13s%b %-13s %b%-9s%b %b%8s · %s%b\n' \
            "$C_ACCENT$C_BOLD" "#$recent_id" "$C_RESET" "$recent_lane" \
            "$(badge_style "$(printf '%s' "$recent_result" | tr '[:lower:]' '[:upper:]')")" \
            "$recent_result" "$C_RESET" "$C_MUTED" \
            "$(duration_between "$recent_created" "$recent_updated")" "$(iso_to_pacific "$recent_updated")" "$C_RESET"
    done
}

while :; do
    render_dashboard
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
