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
remaining='[]'

while IFS= read -r card; do
    task_id="$(printf '%s' "$card" | jq -r '.task_id')"
    project_id="$(printf '%s' "$card" | jq -r '.project_id')"
    id8="$(printf '%s' "$card" | jq -r '.id8')"
    column="$(printf '%s' "$card" | jq -r '.board_column')"
    progress_note="$(printf '%s' "$card" | jq -r '.progress_note // ""')"
    pr_number="$(printf '%s' "$card" | jq -r '.pr_number // empty')"
    reconciled=false

    if { [ "$column" = changes_requested ] \
            || { [ "$column" = in_progress ] && [[ "$progress_note" == "🤖 AUTO SETUP · ALREADY SCOPED"* ]]; }; } \
        && [ -n "$pr_number" ] \
        && { [[ "$progress_note" == "from auto setup"* ]] \
            || [[ "$progress_note" == "🤖 AUTO SETUP"* ]]; }; then
        # A GitHub read failure must fail closed. Treating an unknown PR as
        # fresh work could open a duplicate against the same ticket.
        pr="$($GH_BIN pr view "$pr_number" --repo "$REPO" --json state,headRefName)"
        state="$(printf '%s' "$pr" | jq -r '.state // empty')"
        head="$(printf '%s' "$pr" | jq -r '.headRefName // empty')"
        if [ "$state" = MERGED ] \
            && { [ "$head" = "bot/task-$id8" ] \
                || [[ "$progress_note" == "🤖 AUTO SETUP · ALREADY SCOPED"* ]]; }; then
            mw_move_card "$project_id" "$task_id" review
            printf 'Reconciled merged AutoPR #%s: card %s -> review\n' "$pr_number" "$task_id" >&2
            reconciled=true
        fi
    fi

    if [ "$reconciled" = false ]; then
        remaining="$(jq -cn --argjson rows "$remaining" --argjson card "$card" '$rows + [$card]')"
    fi
done < <(jq -c '.[]' "$CARDS_FILE")

printf '%s\n' "$remaining"
