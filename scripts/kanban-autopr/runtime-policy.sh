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

# Which model and effort this run gets, and why. A card that pins a runtime
# keeps it until someone clears it; otherwise the last stall's classification
# decides, and an unclassified first run falls through to the kind registry
# (empty here, resolved by investigate.sh).
#
# Resolving it HERE rather than in investigate.sh keeps one answer per run: the
# workflow step that budgets the minutes and the step that spends them agree,
# the same way the directive policy is resolved once and handed over.
model="" effort="" runtime_source=auto
card_model="$(jq -r '.autopr_model // empty' "$CARD_FILE")"
card_effort="$(jq -r '.autopr_effort // empty' "$CARD_FILE")"
if [ -n "$card_model" ] || [ -n "$card_effort" ]; then
    runtime_source=manual
    model="$card_model"
    effort="$card_effort"
elif [ -n "$checkpoint" ] && [ -s "$checkpoint/metadata.json" ]; then
    model="$(jq -r '.suggested_model // empty' "$checkpoint/metadata.json")"
    effort="$(jq -r '.suggested_effort // empty' "$checkpoint/metadata.json")"
fi
# A pinned or suggested value that no endpoint knows is a dead run. Drop it and
# let the registry default stand rather than failing the card here.
[ -z "$model" ] || autopr_runtime_model_valid "$model" || model=""
[ -z "$effort" ] || autopr_runtime_effort_valid "$effort" || effort=""
[ -n "$model$effort" ] || runtime_source=default

stall_reason=""
stall_attempt=0
if [ -n "$checkpoint" ] && [ -s "$checkpoint/metadata.json" ]; then
    stall_reason="$(jq -r '.stall_reason // empty' "$checkpoint/metadata.json")"
    stall_attempt="$(jq -r '.stall_attempt // 0' "$checkpoint/metadata.json")"
    [[ "$stall_attempt" =~ ^[0-9]+$ ]] || stall_attempt=0
fi

jq --argjson minutes "$minutes" --argjson extended "$extended" \
    --arg checkpoint "$checkpoint" --arg model "$model" --arg effort "$effort" \
    --arg runtime_source "$runtime_source" --arg stall_reason "$stall_reason" \
    --argjson stall_attempt "$stall_attempt" \
    '. + {minutes:$minutes,extended:$extended,
          checkpoint:(if $checkpoint == "" then null else $checkpoint end),
          model:(if $model == "" then null else $model end),
          effort:(if $effort == "" then null else $effort end),
          runtime_source:$runtime_source,
          stall_reason:(if $stall_reason == "" then null else $stall_reason end),
          stall_attempt:$stall_attempt}' \
    "$WORK_DIR/directive-policy.json" > "$OUTPUT_FILE"
