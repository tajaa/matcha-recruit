#!/usr/bin/env bash
# Resolve the bounded investigation timeout for one selected card. Twenty
# minutes is the ordinary ceiling. A decision-bound --extend-runtime reply
# from an authorized project member grants one 40-minute attempt; the grant is
# intentionally not a standing card directive and must be renewed after every
# extended attempt that also times out.
#
# Usage: runtime-policy.sh CARD OUTPUT
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

CARD_FILE="${1:?usage: runtime-policy.sh CARD OUTPUT}"
OUTPUT_FILE="${2:?missing output path}"
NORMAL_MINUTES="${AUTOPR_NORMAL_RUNTIME_MINUTES:-20}"
EXTENDED_MINUTES="${AUTOPR_EXTENDED_RUNTIME_MINUTES:-40}"
PROJECT_ID="$(jq -r '.project_id // empty' "$CARD_FILE")"
TASK_ID="$(jq -r '.task_id // empty' "$CARD_FILE")"
WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/autopr-runtime-policy-XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

case "$NORMAL_MINUTES:$EXTENDED_MINUTES" in
    20:40) ;;
    *) die "runtime limits are fixed at 20 normal / 40 approved minutes" ;;
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
