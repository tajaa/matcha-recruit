#!/usr/bin/env bash
# Resolve the runtime for a normal investigation or an approved continuation.
#
# Usage: runtime-policy.sh CARD OUTPUT
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

CARD_FILE="${1:?usage: runtime-policy.sh CARD OUTPUT}"
OUTPUT_FILE="${2:?missing output path}"
NORMAL_MINUTES="${AUTOPR_NORMAL_RUNTIME_MINUTES:-20}"
EXTENDED_MINUTES="${AUTOPR_EXTENDED_RUNTIME_MINUTES:-10}"
PROJECT_ID="$(jq -r '.project_id // empty' "$CARD_FILE")"
TASK_ID="$(jq -r '.task_id // empty' "$CARD_FILE")"
WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/autopr-runtime-policy-XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

case "$NORMAL_MINUTES:$EXTENDED_MINUTES" in
    20:10) ;;
    *) die "runtime limits are fixed at 20 normal / 10 approved minutes" ;;
esac
[ -n "$PROJECT_ID" ] && [ -n "$TASK_ID" ] || die "selected card is missing its ids"

HISTORY_FILE="${AUTOPR_RUNTIME_HISTORY_FILE:-$WORK_DIR/history.json}"
if [ -z "${AUTOPR_RUNTIME_HISTORY_FILE:-}" ]; then
    mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/history" \
        > "$HISTORY_FILE"
fi

python3 "$SCRIPT_DIR/resolve-directive-policy.py" \
    --card "$CARD_FILE" --history "$HISTORY_FILE" \
    --output "$WORK_DIR/directive-policy.json"

# The 10 minutes are a continuation of saved work, not a replacement budget
# for a fresh investigation. Without a resumable checkpoint the directive would
# HALVE a from-scratch run and all but guarantee another pause, so it only
# applies when there is actually something to continue from.
checkpoint="$("$SCRIPT_DIR/checkpoint.sh" latest "$CARD_FILE" 2>/dev/null || true)"

extended=false
minutes="$NORMAL_MINUTES"
if jq -e '(.directives // []) | index("extend_runtime") != null' \
    "$WORK_DIR/directive-policy.json" >/dev/null \
    && [ -n "$checkpoint" ]; then
    extended=true
    minutes="$EXTENDED_MINUTES"
fi

jq --argjson minutes "$minutes" --argjson extended "$extended" \
    --arg checkpoint "$checkpoint" \
    '. + {minutes:$minutes,extended:$extended,
          checkpoint:(if $checkpoint == "" then null else $checkpoint end)}' \
    "$WORK_DIR/directive-policy.json" > "$OUTPUT_FILE"
