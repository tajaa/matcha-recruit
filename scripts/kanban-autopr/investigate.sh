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

ATTACH_ARGS=()

# Fetch the same evidence the task detail UI uses. In particular, the history
# endpoint carries discussion notes, review boundaries, rejected-checklist
# reasons/severities, and attachment ids. This is required in BOTH modes: a
# card manually moved to changes_requested may have no existing PR, while a
# rework must know what earlier rounds already fixed.
subtasks="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/subtasks" 2>/dev/null || echo '[]')"
history="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/history" 2>/dev/null || echo '[]')"
files="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files" 2>/dev/null || echo '[]')"
printf '%s' "$subtasks" > "$WORK_DIR/subtasks.json"
printf '%s' "$history" > "$WORK_DIR/history.json"
printf '%s' "$files" > "$WORK_DIR/files.json"

# Attach a bounded, current-round-first set of the actual files. The JSON
# context still lists every file even when a large/old attachment is not
# downloaded, so the model can explain what evidence was unavailable rather
# than pretending the ticket had none.
ATTACHMENT_DIR="$WORK_DIR/attachments"
mkdir -p "$ATTACHMENT_DIR"
MAX_ATTACHMENT_COUNT="${AUTOPR_MAX_ATTACHMENT_COUNT:-12}"
MAX_ATTACHMENT_BYTES="${AUTOPR_MAX_ATTACHMENT_BYTES:-26214400}"
MAX_SINGLE_ATTACHMENT_BYTES="${AUTOPR_MAX_SINGLE_ATTACHMENT_BYTES:-10485760}"
current_round="$(jq -n \
    --slurpfile subtasks "$WORK_DIR/subtasks.json" \
    --slurpfile history "$WORK_DIR/history.json" '
    [
      ([$subtasks[0][]? | (.round_index // 1)] | max // 1),
      (([$history[0][]? | select(.event_type == "round_started")] | length) + 1)
    ] | max
')"
downloaded_bytes=0
downloaded_count=0
downloaded="[]"

while IFS= read -r file; do
    [ -n "$file" ] || continue
    [ "$downloaded_count" -lt "$MAX_ATTACHMENT_COUNT" ] || break

    url="$(printf '%s' "$file" | jq -r '.storage_url // empty')"
    filename="$(printf '%s' "$file" | jq -r '.filename // "attachment"')"
    declared_size="$(printf '%s' "$file" | jq -r '.file_size // 0')"
    [[ "$url" =~ ^https?:// ]] || continue
    [ "$declared_size" -le "$MAX_SINGLE_ATTACHMENT_BYTES" ] 2>/dev/null || continue
    [ $((downloaded_bytes + declared_size)) -le "$MAX_ATTACHMENT_BYTES" ] 2>/dev/null || continue

    safe_name="$(printf '%s' "$filename" | tr -cs '[:alnum:]._- ' '_' | cut -c1-120)"
    [ -n "$safe_name" ] || safe_name="attachment"
    local_path="$ATTACHMENT_DIR/$(printf '%02d' $((downloaded_count + 1)))-$safe_name"

    if ! curl -fLsS --max-time 30 --max-filesize "$MAX_SINGLE_ATTACHMENT_BYTES" \
        -o "$local_path" "$url"; then
        rm -f "$local_path"
        continue
    fi
    actual_size="$(wc -c < "$local_path" | tr -d '[:space:]')"
    if [ "$actual_size" -gt "$MAX_SINGLE_ATTACHMENT_BYTES" ] \
        || [ $((downloaded_bytes + actual_size)) -gt "$MAX_ATTACHMENT_BYTES" ]; then
        rm -f "$local_path"
        continue
    fi

    downloaded_bytes=$((downloaded_bytes + actual_size))
    downloaded_count=$((downloaded_count + 1))
    downloaded="$(jq -c -n --argjson rows "$downloaded" --argjson file "$file" \
        --arg path "$local_path" '$rows + [(($file | del(.storage_url)) + {local_path: $path})]')"
    ATTACH_ARGS+=(-f "$local_path")
done < <(printf '%s' "$files" | jq -c --argjson round "$current_round" \
    '((map(select((.round_index // 1) == $round)) | sort_by(.created_at // "") | reverse)
      + (map(select((.round_index // 1) != $round)) | sort_by(.created_at // "") | reverse))[]')

CONTEXT_FILE="$WORK_DIR/context.json"
jq -n \
    --slurpfile card "$CARD_FILE" \
    --slurpfile subtasks "$WORK_DIR/subtasks.json" \
    --slurpfile history "$WORK_DIR/history.json" \
    --slurpfile files "$WORK_DIR/files.json" \
    --argjson downloaded "$downloaded" \
    '{card: $card[0], subtasks: $subtasks[0], history: $history[0], files: ($files[0] | map(del(.storage_url))), downloaded_attachments: $downloaded}' \
    > "$CONTEXT_FILE"

# Put the structured brief first, then the locally downloaded evidence.
ATTACH_ARGS=(-f "$CONTEXT_FILE" "${ATTACH_ARGS[@]}")

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
