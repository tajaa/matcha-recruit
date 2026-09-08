#!/usr/bin/env bash
# Self-heal cards whose AutoPR was merged but whose GitHub webhook did not move
# the card to Review. Emit only the still-eligible cards so this same workflow
# cannot create a duplicate PR while repairing the board.
#
# Usage: reconcile-merged-cards.sh cards.json > eligible-cards.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

CARDS_FILE="${1:?usage: reconcile-merged-cards.sh cards.json}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
GH_BIN="${AUTOPR_GH_BIN:-gh}"
# The run-scoped snapshot of open bot PRs (collect-pr-context.sh). A PR that is
# in it is OPEN, so it is neither merged nor closed and needs no `gh pr view`.
BOT_PRS_FILE="${AUTOPR_BOT_PRS_FILE:-}"
remaining='[]'

pr_known_open() {
    [ -n "$BOT_PRS_FILE" ] && [ -s "$BOT_PRS_FILE" ] || return 1
    jq -e --argjson n "$1" 'any(.[]; .number == $n and (.state // "OPEN") == "OPEN")' \
        "$BOT_PRS_FILE" >/dev/null 2>&1
}

while IFS= read -r card; do
    task_id="$(printf '%s' "$card" | jq -r '.task_id')"
    project_id="$(printf '%s' "$card" | jq -r '.project_id')"
    id8="$(printf '%s' "$card" | jq -r '.id8')"
    column="$(printf '%s' "$card" | jq -r '.board_column')"
    progress_note="$(printf '%s' "$card" | jq -r '.progress_note // ""')"
    pr_number="$(printf '%s' "$card" | jq -r '.pr_number // empty')"
    reconciled=false

    if { [ "$column" = changes_requested ] || [ "$column" = in_progress ]; } \
        && [[ "$pr_number" =~ ^[0-9]+$ ]] \
        && { [[ "$progress_note" == "from auto setup"* ]] \
            || [[ "$progress_note" == "🤖 AUTO SETUP"* ]]; } \
        && ! pr_known_open "$pr_number"; then
        # A GitHub read failure must fail closed. Treating an unknown PR as
        # fresh work could open a duplicate against the same ticket.
        pr="$($GH_BIN pr view "$pr_number" --repo "$REPO" --json state,headRefName)"
        state="$(printf '%s' "$pr" | jq -r '.state // empty')"
        head="$(printf '%s' "$pr" | jq -r '.headRefName // empty')"
        own_draft=false
        [ "$head" != "bot/task-$id8" ] || own_draft=true
        cross_lane=false
        [[ "$progress_note" != "🤖 AUTO SETUP · ALREADY SCOPED"* ]] || cross_lane=true
        if [ "$state" = MERGED ] \
            && { [ "$column" = changes_requested ] || [ "$cross_lane" = true ]; } \
            && { [ "$own_draft" = true ] || [ "$cross_lane" = true ]; }; then
            mw_move_card "$project_id" "$task_id" review
            printf 'Reconciled merged AutoPR #%s: card %s -> review\n' "$pr_number" "$task_id" >&2
            reconciled=true
        elif [ "$state" = CLOSED ] && [ "$own_draft" = true ]; then
            # A human closed this lane's own draft without merging: the card
            # was stuck in its column forever with nothing to say why. Hand it
            # back to Todo (the webhook does the same); it does not auto-rerun
            # — the branch's PR history still gates a fresh investigation
            # until the owner presses Run AutoPR or replies with context.
            # Cross-lane links (error-bot drafts closed as superseded or
            # duplicate) are not a rejection, so they are left alone.
            # Move AND rewrite the note through the server, which owns the
            # structured-note parser the webhook uses. A bare column PATCH left
            # the card in Todo still reading "READY FOR REVIEW". During a
            # rolling deploy the endpoint can lag this script: fall back to the
            # column move alone rather than leaving the card stuck.
            if ! closed_error="$(mw_api POST \
                "/matcha-work/projects/$project_id/tasks/$task_id/autopr/pr-closed" \
                "$(jq -n --argjson pr "$pr_number" '{pr_number: $pr}')" \
                2>&1 >/dev/null)"; then
                if [[ "$closed_error" == *"HTTP 404:"* ]]; then
                    mw_api PATCH "/matcha-work/projects/$project_id/tasks/$task_id" \
                        "$(jq -n '{board_column: "todo"}')" >/dev/null
                else
                    printf '%s\n' "$closed_error" >&2
                    exit 1
                fi
            fi
            printf 'Reconciled closed-unmerged AutoPR #%s: card %s -> todo\n' "$pr_number" "$task_id" >&2
            reconciled=true
        fi
    fi

    if [ "$reconciled" = false ]; then
        remaining="$(jq -cn --argjson rows "$remaining" --argjson card "$card" '$rows + [$card]')"
    fi
done < <(jq -c '.[]' "$CARDS_FILE")

printf '%s\n' "$remaining"
