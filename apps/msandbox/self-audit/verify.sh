#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BEFORE="${1:?usage: verify.sh BEFORE AFTER SUMMARY}"
AFTER="${2:?usage: verify.sh BEFORE AFTER SUMMARY}"
SUMMARY="${3:?usage: verify.sh BEFORE AFTER SUMMARY}"
AFTER_AUDIT_SUMMARY="$(mktemp "${TMPDIR:-/tmp}/matcha-autopr-verify.XXXXXX")"
trap 'rm -f "$AFTER_AUDIT_SUMMARY"' EXIT

"$SCRIPT_DIR/audit.sh" --json "$AFTER" --summary "$AFTER_AUDIT_SUMMARY"
unresolved="$(jq -n --slurpfile before "$BEFORE" --slurpfile after "$AFTER" '
  [$before[0].checks[] | select(.status == "fail" and .repairability == "repo") | .id] as $failed
  | [$after[0].checks[] | select((.id as $id | $failed | index($id)) and .status != "pass") | .id]
')"
new_failures="$(jq -n --slurpfile before "$BEFORE" --slurpfile after "$AFTER" '
  [$before[0].checks[] | select(.status == "fail" and .repairability == "repo") | .id] as $old
  | [$after[0].checks[] | select(.status == "fail" and .repairability == "repo" and ((.id as $id | $old | index($id)) | not)) | .id]
')"

{
    echo "## Verification"
    echo
    if [ "$(jq length <<< "$unresolved")" -eq 0 ] && [ "$(jq length <<< "$new_failures")" -eq 0 ]; then
        echo "All previously failing repo-repairable checks now pass, with no new repairable failures."
    else
        echo "Verification failed."
        echo
        echo "- Unresolved: $(jq -c . <<< "$unresolved")"
        echo "- New failures: $(jq -c . <<< "$new_failures")"
    fi
    operator_count="$(jq -r '.operator_failures' "$AFTER")"
    [ "$operator_count" -eq 0 ] \
        || echo "- Operator-action findings remain: $operator_count (not changed by this PR)."
} > "$SUMMARY"

[ "$(jq length <<< "$unresolved")" -eq 0 ] && [ "$(jq length <<< "$new_failures")" -eq 0 ]
