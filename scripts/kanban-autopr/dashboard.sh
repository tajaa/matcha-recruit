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
PACIFIC_TZ="${AUTOPR_DASHBOARD_TZ:-America/Los_Angeles}"
RUNNER_WORKTREE="${AUTOPR_RUNNER_WORKTREE:-$USER_HOME/.local/share/matcha-actions-runner/_work/matcha-recruit/matcha-recruit}"
CACHE_DIR="${AUTOPR_DASHBOARD_CACHE_DIR:-$USER_HOME/Library/Caches/matcha-kanban-autopr/dashboard}"
CARD_SNAPSHOT="${AUTOPR_CARD_SNAPSHOT:-$USER_HOME/Library/Caches/matcha-kanban-autopr/cards.json}"
DISPATCH_LOG="${AUTOPR_DISPATCH_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-dispatch.log}"
PLAN_PY="${AUTOPR_PLAN_PY:-$SCRIPT_DIR/plan.py}"
RUN_SNAPSHOT="${AUTOPR_RUN_SNAPSHOT:-$SCRIPT_DIR/run-snapshot.sh}"

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

cache_age() {
    local path="$1" modified now age
    modified="$(stat -c %Y "$path" 2>/dev/null || stat -f %m "$path" 2>/dev/null || printf 0)"
    now="$(dashboard_now_epoch)"
    age=$((now - modified))
    [ "$age" -ge 0 ] 2>/dev/null || age=0
    format_duration_seconds "$age"
}

# fetch_json DATA_VAR STATE_VAR CACHE_KEY COMMAND...
# STATE is "live", "stale <age>", or "unavailable". Last-known-good data is
# deliberately retained during transient GitHub/board failures.
fetch_json() {
    local data_var="$1" state_var="$2" key="$3" output cache tmp state
    shift 3
    cache="$CACHE_DIR/$key.json"
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
    local open_audits_state merged_state board_state bot_pr_state plan_state all_states source_state
    local active run_id run_lane run_status run_created run_title run_elapsed run_started current_id8=""
    local run_details run_details_state step_line phase branch id8 active_card project card_title
    local dispatch_line dispatch_ts dispatch_action dispatch_reason dispatch_time
    local queue_counts row_badge row_project row_title row_time row_when row_iso
    local pr_number pr_lane pr_state pr_title pr_created pr_flag
    local merged_number merged_lane merged_title merged_created merged_at merged_verification
    local recent_id recent_lane recent_result recent_created recent_updated
    local plan_input_dir plan_id plan_merge_count plan_release_blockers plan_position plan_number plan_title plan_blocked

    cutoff="$(utc_24_hours_ago)"
    fetch_json runs kanban_state runs-all env AUTOPR_REPO="$REPO" AUTOPR_REF="$REF" \
        AUTOPR_GH_BIN="$GH_BIN" "$RUN_SNAPSHOT"
    error_state="$kanban_state"
    audit_state="$kanban_state"
    admin_state="$kanban_state"
    kanban_runs="$(printf '%s' "$runs" | jq -c '[.[] | select(.lane == "kanban")]')"
    error_runs="$(printf '%s' "$runs" | jq -c '[.[] | select(.lane == "errors")]')"
    audit_runs="$(printf '%s' "$runs" | jq -c '[.[] | select(.lane == "self-audit")]')"
    admin_updates_runs="$(printf '%s' "$runs" | jq -c '[.[] | select(.lane == "admin-updates")]')"

    fetch_json open_kanban open_kanban_state prs-open-kanban "$GH_BIN" pr list --repo "$REPO" \
        --state open --label autopr --limit 100 \
        --json number,title,isDraft,headRefName,createdAt,updatedAt,labels,url
    fetch_json open_errors open_errors_state prs-open-errors "$GH_BIN" pr list --repo "$REPO" \
        --state open --label autofix --limit 100 \
        --json number,title,isDraft,headRefName,createdAt,updatedAt,labels,url
    fetch_json open_audits open_audits_state prs-open-audits "$GH_BIN" pr list --repo "$REPO" \
        --state open --label autopr-self-audit --limit 100 \
        --json number,title,isDraft,headRefName,createdAt,updatedAt,labels,url
    open_prs="$(jq -cn --argjson kanban "$open_kanban" --argjson errors "$open_errors" \
        --argjson audit "$open_audits" '$kanban + $errors + $audit | unique_by(.number) | sort_by(.updatedAt // "") | reverse')"
    fetch_json merged_prs merged_state prs-merged "$GH_BIN" pr list --repo "$REPO" \
        --state merged --limit 100 \
        --json number,title,createdAt,mergedAt,headRefName,labels,url

    fetch_json cards board_state board-cards "$SCRIPT_DIR/collect.sh"
    fetch_json bot_prs bot_pr_state bot-pr-context env GITHUB_REPOSITORY="$REPO" \
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
    selected="$(AUTOPR_SELECT_READ_ONLY=true GITHUB_REPOSITORY="$REPO" \
        "$SCRIPT_DIR/select.sh" <(printf '%s' "$cards") 2>/dev/null)"
    selected_rc=$?
    [ "$selected_rc" -eq 0 ] || selected=""

    all_states="$kanban_state $error_state $audit_state $admin_state $open_kanban_state $open_errors_state $open_audits_state $merged_state $board_state $bot_pr_state $plan_state"
    if [[ "$all_states" == *unavailable* ]]; then
        source_state='DEGRADED · source unavailable'
    elif [[ "$all_states" == *stale* ]]; then
        source_state='STALE · showing last-known-good data'
    else
        source_state='LIVE'
    fi

    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf 'MATCHA AUTOPR CONTROL BOARD\n'
    printf '%s · %s · refresh %ss\n' \
        "$(TZ="$PACIFIC_TZ" date '+%a %b %-d · %-I:%M:%S %p %Z' 2>/dev/null \
          || TZ="$PACIFIC_TZ" date '+%a %b %d · %I:%M:%S %p %Z')" \
        "$source_state" "$REFRESH_SECONDS"

    dispatch_line="$(tail -n 1 "$DISPATCH_LOG" 2>/dev/null || true)"
    dispatch_ts="$(printf '%s' "$dispatch_line" | jq -r '.timestamp // empty' 2>/dev/null)"
    dispatch_action="$(printf '%s' "$dispatch_line" | jq -r '.action // empty' 2>/dev/null)"
    dispatch_reason="$(printf '%s' "$dispatch_line" | jq -r '.reason // empty' 2>/dev/null)"
    dispatch_time="$(iso_to_pacific "$dispatch_ts")"
    if [ -n "$dispatch_action" ]; then
        printf 'Scheduler last signal %s · %s · %s\n' "$dispatch_time" "$dispatch_action" "$dispatch_reason"
    else
        printf 'Scheduler last signal unavailable\n'
    fi

    active="$(printf '%s' "$runs" | jq -c \
        '[.[] | select(.status | IN("queued", "in_progress", "requested", "waiting", "pending"))][0] // {}')"
    run_id="$(printf '%s' "$active" | jq -r '.databaseId // empty')"
    printf '\nNOW'
    if [ -n "$run_id" ]; then
        run_lane="$(printf '%s' "$active" | jq -r '.lane // "?"')"
        run_status="$(printf '%s' "$active" | jq -r '.status // "?"')"
        run_created="$(printf '%s' "$active" | jq -r '.createdAt // empty')"
        run_title="$(printf '%s' "$active" | jq -r '.displayTitle // empty')"
        run_elapsed="$(duration_between "$run_created" '')"
        run_started="$(iso_to_pacific "$run_created")"
        fetch_json run_details run_details_state "run-$run_id" "$GH_BIN" run view "$run_id" --repo "$REPO" --json jobs
        step_line="$(printf '%s' "$run_details" | jq -r '
          [.jobs[]? as $job | $job.steps[]? | select(.status == "in_progress") | ($job.name + " · " + .name)][0] // empty
        ' 2>/dev/null)"
        phase="$(phase_label "${step_line#* · }")"
        printf ' · %s · %s\n' "$phase" "$run_elapsed"
        printf '  %s run #%s · %s · started %s\n' "$(printf '%s' "$run_lane" | tr '[:lower:]' '[:upper:]')" \
            "$run_id" "$run_status" "$run_started"
        branch="$(runner_task_branch 2>/dev/null || true)"
        if [ "$run_lane" = kanban ] && [ -n "$branch" ]; then
            id8="${branch#bot/task-}"
            current_id8="$id8"
            active_card="$(printf '%s' "$cards" | jq -c --arg id8 "$id8" '[.[] | select(.id8 == $id8)][0] // {}')"
            project="$(printf '%s' "$active_card" | jq -r '.project_title // "MATCHA"')"
            card_title="$(printf '%s' "$active_card" | jq -r '.title // empty')"
            printf '  %s · %s\n' "$project" "${card_title:-task $id8}"
            printf '  branch %s\n' "$branch"
        elif [ -n "$run_title" ]; then
            printf '  %s\n' "$run_title"
        fi
    else
        printf ' · IDLE\n'
        printf '  No workflow is currently queued or running.\n'
    fi

    plan_id="$(printf '%s' "$plan" | jq -r '.plan_id // "unavailable"')"
    printf '\nPLAN · %s · NOT-READY PRS ONLY\n' "$plan_id"
    if [ "$plan_state" != live ]; then
        printf '  unavailable · existing queue remains visible below\n'
    else
        printf '  WORK ORDER\n'
        printf '%s' "$plan" | jq -r '.work_order[:5][] |
          [(.position | tostring), .cluster_id, (if .blocked then "CONTEXT" elif .board_column == "changes_requested" then "REWORK" else "TODO" end), (.title[0:52])] | @tsv
        ' | while IFS=$'\t' read -r plan_position row_project row_badge plan_title; do
            printf '    %-2s %-4s %-8s %s\n' "$plan_position" "$row_project" "$row_badge" "$plan_title"
        done
        plan_merge_count="$(printf '%s' "$plan" | jq '.merge_order | length')"
        printf '  MERGE ORDER · %s draft(s)\n' "$plan_merge_count"
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
            printf '  RELEASE gh workflow run autopr-release-plan.yml -f plan_id=%s\n' "$plan_id"
        elif [ "$plan_release_blockers" -gt 0 ]; then
            printf '  RELEASE BLOCKED · %s unresolved review/check/context condition(s)\n' "$plan_release_blockers"
        fi
    fi

    printf '\nNEXT'
    if [ "$selected_rc" -eq 0 ] && [ -n "$selected" ]; then
        printf ' · EXACT SELECTOR RESULT\n'
        printf '%s' "$selected" | jq -r '
          "  " + (.project_title // "?") + " · " + .title,
          "  " + (if .board_column == "changes_requested" then "rework" else "new work" end) + " · task " + .id8
        '
    elif [ "$selected_rc" -eq 3 ]; then
        printf ' · NONE ELIGIBLE AFTER CURRENT WORK\n'
        printf '  Queue entries below may be waiting, held, or cooling down.\n'
    else
        printf ' · UNKNOWN\n'
        printf '  Selector failed (exit %s); this does not mean the queue is empty.\n' "$selected_rc"
    fi

    queue_counts="$(printf '%s' "$cards" | jq -r --arg current_id8 "$current_id8" '
      def pending: (.autopr_reconsideration_pending // false);
      def waiting: ((.progress_note // "") | test("awaiting answers"; "i"));
      def held: ((.progress_note // "") | contains("[autopr:no-spec ")) and (pending | not);
      "\(length) tracked · \([.[] | select(.id8 == $current_id8)] | length) active · \([.[] | select(pending and .id8 != $current_id8)] | length) feedback · \([.[] | select(waiting and .id8 != $current_id8)] | length) waiting · \([.[] | select(held and .id8 != $current_id8)] | length) held"
    ')"
    printf '\nQUEUE · %s\n' "$queue_counts"
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
        printf '  %-8s %-9s %-42s %s\n' "$row_badge" "$row_project" "$row_title" "$row_time"
    done
    [ "$(printf '%s' "$cards" | jq 'length')" -gt 0 ] || printf '  No cards, or the board source is unavailable.\n'

    printf '\nOPEN BOT PRS · AGE\n'
    if [ "$(printf '%s' "$open_prs" | jq 'length')" -eq 0 ]; then
        printf '  none\n'
    else
        printf '%s' "$open_prs" | jq -r '.[:6][] |
          [(.number | tostring),
           (if ([.labels[].name] | index("autopr")) then "KANBAN" elif ([.labels[].name] | index("autofix")) then "ERROR" else "AUDIT" end),
           (if .isDraft then "DRAFT" else "OPEN" end),
           (.title[0:42]), (.createdAt // ""),
           (if ([.labels[].name] | index("autopr-awaiting-input")) then "WAITING" elif ([.labels[].name] | index("needs-work")) then "NEEDS WORK" else "" end)] | @tsv
        ' | while IFS=$'\t' read -r pr_number pr_lane pr_state pr_title pr_created pr_flag; do
            printf '  #%-4s %-6s %-5s %-42s %8s%s\n' "$pr_number" "$pr_lane" "$pr_state" "$pr_title" \
                "$(duration_between "$pr_created" '')" "${pr_flag:+ · $pr_flag}"
        done
    fi

    printf '\nRECENT BOT PRS · OPEN → MERGE · PACIFIC\n'
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
        printf '  #%-4s %-6s %-40s %8s · %s%s\n' "$merged_number" "$merged_lane" "$merged_title" \
            "$(duration_between "$merged_created" "$merged_at")" "$(iso_to_pacific "$merged_at")" \
            "${merged_verification:+ · $merged_verification}"
    done

    printf '\nRECENT RUNS · DURATION · PACIFIC\n'
    printf '%s' "$runs" | jq -r --arg cutoff "$cutoff" '
      [.[] | select(.status == "completed" and (.createdAt // "") >= $cutoff)][:5][] |
      [(.databaseId | tostring), .lane, (.conclusion // "completed"), (.createdAt // ""), (.updatedAt // "")] | @tsv
    ' | while IFS=$'\t' read -r recent_id recent_lane recent_result recent_created recent_updated; do
        printf '  %-13s %-13s %-9s %8s · %s\n' "#$recent_id" "$recent_lane" "$recent_result" \
            "$(duration_between "$recent_created" "$recent_updated")" "$(iso_to_pacific "$recent_updated")"
    done
}

while :; do
    render_dashboard
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
