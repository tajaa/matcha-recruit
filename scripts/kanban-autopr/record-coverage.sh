#!/usr/bin/env bash
# Link a card to an older open PR that already covers the proposed task patch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

CARD_FILE="${1:?usage: record-coverage.sh card.json coverage.json}"
COVERAGE_FILE="${2:?usage: record-coverage.sh card.json coverage.json}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
TASK_ID="$(jq -r '.task_id' "$CARD_FILE")"
PROJECT_ID="$(jq -r '.project_id' "$CARD_FILE")"
PR="$(jq -r '.covering_pr' "$COVERAGE_FILE")"
EXPECTED_SHA="$(jq -r '.covering_head_sha' "$COVERAGE_FILE")"
REASON="$(jq -r '.reason' "$COVERAGE_FILE")"
RECONSIDERATION_EVENT_ID="$(jq -r '.autopr_reconsideration_event_id // empty' "$CARD_FILE")"
[[ "$TASK_ID" =~ ^[0-9a-fA-F-]{36}$ ]] || die "task_id has unexpected shape"
[[ "$PR" =~ ^[0-9]+$ ]] || die "coverage is missing a covering PR"

live="$(gh pr view "$PR" --repo "$REPO" --json number,state,headRefName,headRefOid,url)"
[ "$(printf '%s' "$live" | jq -r '.state')" = OPEN ] || die "covering PR #$PR is no longer open"
[ "$(printf '%s' "$live" | jq -r '.headRefOid')" = "$EXPECTED_SHA" ] || die "covering PR #$PR changed during comparison"
url="$(printf '%s' "$live" | jq -r '.url')"

marker="<!-- matcha-autopr-coverage-task: $TASK_ID -->"
comments="$(gh api "repos/$REPO/issues/$PR/comments?per_page=100")"
printf '%s' "$comments" | jq -e 'type == "array"' >/dev/null \
    || die "comments for covering PR #$PR returned invalid JSON"
if ! printf '%s' "$comments" | jq -e --arg marker "$marker" 'any(.[]; (.body // "") | contains($marker))' >/dev/null; then
    gh pr comment "$PR" --repo "$REPO" --body "$marker

Matcha Work task \`$TASK_ID\` is already scoped by this PR. $REASON" >/dev/null
fi
gh pr edit "$PR" --repo "$REPO" --add-label covers-kanban-task >/dev/null

existing="$(jq -r '.progress_note // ""' "$CARD_FILE")"
source_label="existing PR"
[[ "$(printf '%s' "$live" | jq -r '.headRefName')" != bot/err-* ]] || source_label="production autofix"
note="🤖 AUTO SETUP · ALREADY SCOPED · PR #$PR · source $source_label"
[ -z "$existing" ] || [[ "$existing" == "🤖 AUTO SETUP"* ]] || note="$note · $existing"
mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
    "$(jq -n --arg url "$url" --argjson number "$PR" --arg note "$note" \
        '{pr_url:$url,pr_number:$number,board_column:"in_progress",progress_note:$note}')" >/dev/null
if [ -n "$RECONSIDERATION_EVENT_ID" ]; then
    reply="AutoPR reviewed this additional context. The requested change is already covered by PR #$PR. $REASON"
    if ! (mw_api POST "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/activity" \
        "$(jq -n --arg body "$reply" --arg reply_to "$RECONSIDERATION_EVENT_ID" \
            '{kind:"note",body:$body,reply_to:$reply_to}')" >/dev/null); then
        printf 'kanban-autopr: warning: could not post reconsideration coverage reply for task %s\n' "$TASK_ID" >&2
    fi
fi
printf 'kanban-autopr: task %s is already scoped in PR #%s\n' "$TASK_ID" "$PR" >&2
