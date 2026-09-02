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

extended=false
minutes="$NORMAL_MINUTES"
if jq -e '(.directives // []) | index("extend_runtime") != null' \
    "$WORK_DIR/directive-policy.json" >/dev/null; then
    extended=true
    minutes="$EXTENDED_MINUTES"
fi

jq --argjson minutes "$minutes" --argjson extended "$extended" \
    '. + {minutes:$minutes,extended:$extended}' \
    "$WORK_DIR/directive-policy.json" > "$OUTPUT_FILE"
