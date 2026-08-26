#!/usr/bin/env bash
# Ask OpenCode to implement (todo) or address feedback on (rework) one
# kanban card, and write a structured report. Leaves any fix unstaged in the
# working tree; never commits.
#
# Usage: ./investigate.sh card.json report.md
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

CARD_FILE="${1:?usage: investigate.sh card.json report.md}"
REPORT_FILE="${2:?usage: investigate.sh card.json report.md}"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO="${GITHUB_REPOSITORY:-}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# The report must live outside the git workspace: `git add --all` in
# publish.sh would otherwise stage a file the model wrote under its own
# control, and it would ship inside the PR diff rather than becoming the PR
# body.
case "$(cd "$(dirname "$REPORT_FILE")" 2>/dev/null && pwd)/$(basename "$REPORT_FILE")" in
    "$REPO_ROOT"/*) die "REPORT_FILE must be outside the repo (got $REPORT_FILE)" ;;
esac
rm -f "$REPORT_FILE"

MODE="$(jq -r '.mode' "$CARD_FILE")"
PROJECT_ID="$(jq -r '.project_id' "$CARD_FILE")"
TASK_ID="$(jq -r '.task_id' "$CARD_FILE")"
ID8="$(jq -r '.id8' "$CARD_FILE")"

ATTACH_ARGS=(-f "$CARD_FILE")

if [ "$MODE" = rework ]; then
    PROMPT_FILE="$SCRIPT_DIR/_prompt_rework.txt"
    branch="bot/task-$ID8"
    pr_number="$(gh pr list --repo "$REPO" --head "$branch" --state open --limit 1 --json number --jq '.[0].number // empty')"
    if [ -n "$pr_number" ]; then
        gh pr view "$pr_number" --repo "$REPO" --json reviews,comments > "$WORK_DIR/feedback.json" 2>/dev/null \
            || echo '{}' > "$WORK_DIR/feedback.json"
    else
        echo '{}' > "$WORK_DIR/feedback.json"
    fi
    ATTACH_ARGS+=(-f "$WORK_DIR/feedback.json")
else
    PROMPT_FILE="$SCRIPT_DIR/_prompt_todo.txt"
    subtasks="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/subtasks" 2>/dev/null || echo '[]')"
    printf '%s' "$subtasks" > "$WORK_DIR/subtasks.json"
    ATTACH_ARGS+=(-f "$WORK_DIR/subtasks.json")
fi

PROMPT_TEXT="$(sed "s#REPORT_PATH#$REPORT_FILE#g" "$PROMPT_FILE")"

# Defense in depth: this step's workflow env should already omit these, but
# strip them here too in case a future edit adds them back.
env -u GH_TOKEN -u MATCHA_BOT_PASSWORD \
    opencode run --auto --model openai/gpt-5.6-terra --variant high \
    "${ATTACH_ARGS[@]}" \
    -- "$PROMPT_TEXT"

if [ ! -s "$REPORT_FILE" ]; then
    die "investigation produced no report at $REPORT_FILE"
fi

for heading in '### Summary' '### Changes' '### Blast radius' '### Confidence'; do
    if ! grep -qF "$heading" "$REPORT_FILE"; then
        die "report is missing required heading: $heading"
    fi
done
