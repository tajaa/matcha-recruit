#!/usr/bin/env bash
# Follow the current or most recently worked Kanban AutoPR. Before publish,
# the runner's bot/task-* checkout is the only honest representation of the
# future PR, so show its live diff. After publish, add GitHub's PR metadata and
# checks while continuing to show the exact files from the runner worktree.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
WORKFLOW="${AUTOPR_WORKFLOW:-kanban-autopr.yml}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
GIT_BIN="${AUTOPR_GIT_BIN:-/usr/bin/git}"
RUNNER_WORKTREE="${AUTOPR_RUNNER_WORKTREE:-$USER_HOME/.local/share/matcha-actions-runner/_work/matcha-recruit/matcha-recruit}"
# PR/check metadata is observer-only and shares the dispatcher's API token.
REFRESH_SECONDS="${AUTOPR_PR_REFRESH_SECONDS:-60}"
PACIFIC_TZ="${AUTOPR_DASHBOARD_TZ:-America/Los_Angeles}"
MAX_DIFF_LINES="${AUTOPR_PR_DIFF_LINES:-80}"
MAX_FILE_LINES="${AUTOPR_PR_FILE_LINES:-3}"
CARD_SNAPSHOT="${AUTOPR_CARD_SNAPSHOT:-$USER_HOME/Library/Caches/matcha-kanban-autopr/cards.json}"

workflow_is_active() {
    "$GH_BIN" run list --repo "$REPO" --workflow "$WORKFLOW" --limit 10 --json status 2>/dev/null \
        | jq -e 'any(.[]; .status | IN("queued", "in_progress", "requested", "waiting", "pending"))' >/dev/null 2>&1
}

runner_task_branch() {
    local branch=""
    if "$GIT_BIN" -C "$RUNNER_WORKTREE" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        branch="$($GIT_BIN -C "$RUNNER_WORKTREE" branch --show-current 2>/dev/null || true)"
        if [[ "$branch" == bot/task-* ]]; then
            printf '%s\n' "$branch"
            return 0
        fi
    fi
    return 1
}

current_task_branch() {
    local workflow_active="$1" branch="" latest_open=""
    branch="$(runner_task_branch || true)"
    if [ "$workflow_active" = true ] && [ -n "$branch" ]; then
        printf '%s\n' "$branch"
        return 0
    fi

    # When the runner is between jobs, fall back to the most recently updated
    # open Kanban PR. Restrict both the label and branch prefix so a bot/err-*
    # production-error PR can never appear in this pane.
    latest_open="$($GH_BIN pr list --repo "$REPO" --state open --label autopr --limit 20 \
        --json headRefName,updatedAt 2>/dev/null \
        | jq -r '[.[] | select(.headRefName | startswith("bot/task-"))] | sort_by(.updatedAt) | reverse | .[0].headRefName // empty' 2>/dev/null)"
    if [ -n "$latest_open" ]; then
        printf '%s\n' "$latest_open"
    elif [ -n "$branch" ]; then
        # No open PR exists, but retaining the last attempted task is more
        # useful than an empty pane. The renderer labels it as historical.
        printf '%s\n' "$branch"
    fi
}

pr_for_branch() {
    local branch="$1" number
    number="$($GH_BIN pr list --repo "$REPO" --head "$branch" --state all --limit 1 \
        --json number --jq '.[0].number // empty' 2>/dev/null || true)"
    [ -n "$number" ] || return 1
    "$GH_BIN" pr view "$number" --repo "$REPO" \
        --json number,title,isDraft,state,url,labels,headRefName,updatedAt,reviewDecision,statusCheckRollup,files,additions,deletions \
        2>/dev/null
}

render_pr_metadata() {
    jq -r '
      "PR #\(.number)  " + (if .isDraft then "DRAFT" else .state end),
      "  " + .title[0:44],
      "  branch " + .headRefName + " · " + ((.files | length) | tostring) + " files · +" + (.additions | tostring) + " -" + (.deletions | tostring),
      "  labels " + ([.labels[].name | select(. != "autopr") | sub("criticality:"; "") | sub("confidence:"; "")] | join(", ")),
      (if (.statusCheckRollup | length) == 0 then "  checks none reported" else
         "  checks " +
         (([.statusCheckRollup[] | select((.status // "") != "COMPLETED")] | length) | tostring) + " running · " +
         (([.statusCheckRollup[] | select((.conclusion // .state // "") == "SUCCESS")] | length) | tostring) + " passed · " +
         (([.statusCheckRollup[] | select((.conclusion // .state // "") | IN("FAILURE", "ERROR", "TIMED_OUT", "CANCELLED"))] | length) | tostring) + " failed"
       end),
      "  " + (.url | sub("https://"; ""))
    '
}

render_card_title() {
    local branch="$1" id8="${branch#bot/task-}"
    [ -s "$CARD_SNAPSHOT" ] || return 0
    jq -r --arg id8 "$id8" '
      [.[] | select(.id8 == $id8)][0]
      | if . == null then empty else "  card " + (.project_title // "?") + " · " + (.title[0:34]) end
    ' "$CARD_SNAPSHOT" 2>/dev/null || true
}

render_local_diff() {
    local branch="$1" checked_out base short_stat pane_rows file_lines
    "$GIT_BIN" -C "$RUNNER_WORKTREE" rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 1
    checked_out="$($GIT_BIN -C "$RUNNER_WORKTREE" branch --show-current 2>/dev/null || true)"
    [ "$checked_out" = "$branch" ] || return 1

    base=main
    "$GIT_BIN" -C "$RUNNER_WORKTREE" rev-parse --verify "$base" >/dev/null 2>&1 || base=origin/main
    short_stat="$($GIT_BIN -C "$RUNNER_WORKTREE" diff --shortstat "$base" -- 2>/dev/null || true)"
    pane_rows="$(tput lines 2>/dev/null || printf '24')"
    file_lines=$((pane_rows - 13))
    [ "$file_lines" -ge 2 ] || file_lines=2
    [ "$file_lines" -le 8 ] || file_lines=8

    printf '\nCHANGED FILES · LIVE RUNNER WORKTREE\n'
    if [ -n "$short_stat" ]; then
        "$GIT_BIN" -C "$RUNNER_WORKTREE" diff --name-status "$base" -- 2>/dev/null \
            | sed -n "1,${file_lines}p"
        printf '  %s\n' "$(printf '%s' "$short_stat" | sed 's/^[[:space:]]*//')"
    else
        printf '  no diff from %s yet\n' "$base"
        return 0
    fi

    # The normal right-column pane is intentionally compact. Operators who
    # enlarge it can opt into a patch excerpt without pushing the PR identity
    # off-screen in the default layout.
    if [ "${AUTOPR_PR_SHOW_PATCH:-0}" = 1 ]; then
        printf '\nLIVE DIFF · first %s lines\n' "$MAX_DIFF_LINES"
        "$GIT_BIN" -C "$RUNNER_WORKTREE" diff --no-ext-diff --unified=1 "$base" -- 2>/dev/null \
            | sed -n "1,${MAX_DIFF_LINES}p"
    fi
}

render_remote_files() {
    local pr_json="$1"
    printf '\nCHANGED FILES\n'
    printf '%s' "$pr_json" | jq -r --argjson limit "$MAX_FILE_LINES" '
      if (.files | length) == 0 then "  none reported" else
        (.files[:$limit][] | "  " + .path + "  +" + (.additions | tostring) + " -" + (.deletions | tostring)),
        (if (.files | length) > $limit then "  +" + (((.files | length) - $limit) | tostring) + " more files" else empty end)
      end
    '
}

render_pr() {
    local branch pr_json="" workflow_active=false
    workflow_is_active && workflow_active=true
    branch="$(current_task_branch "$workflow_active")"

    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf 'ACTIVE / MOST RECENT KANBAN PR\nUpdated %s\n\n' "$(TZ="$PACIFIC_TZ" date '+%I:%M:%S %p %Z' | sed 's/^0//')"
    if [ -z "$branch" ]; then
        printf 'No bot/task-* worktree or open Kanban AutoPR was found.\n'
        printf 'This pane will populate after the workflow selects a card.\n'
        return 0
    fi

    if pr_json="$(pr_for_branch "$branch")" && [ -n "$pr_json" ]; then
        printf '%s' "$pr_json" | render_pr_metadata
    else
        if [ "$workflow_active" = true ]; then
            printf 'DRAFTING · PR NOT PUBLISHED YET\n'
        else
            printf 'LAST ATTEMPT · NO PR PUBLISHED\n'
        fi
        printf '  branch %s\n' "$branch"
        printf '  task %s\n' "${branch#bot/task-}"
        render_card_title "$branch"
        printf '  GitHub metadata appears after publish.\n'
    fi

    if ! render_local_diff "$branch"; then
        if [ -n "$pr_json" ]; then
            render_remote_files "$pr_json"
        else
            printf '\nRunner worktree is not available at:\n  %s\n' "$RUNNER_WORKTREE"
        fi
    fi
}

while :; do
    render_pr
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
