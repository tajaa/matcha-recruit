#!/usr/bin/env bash
# Collect merged PR metadata with GitHub credentials on the trusted host, then
# reduce it to a production-bounded, credential-free model input.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PRODUCTION_CONTEXT="${1:?usage: collect.sh PRODUCTION_CONTEXT PRODUCTION_STATE DEPLOYMENT OUTPUT [SINCE_PR]}"
PRODUCTION_STATE="${2:?missing production state}"
DEPLOYMENT="${3:?missing deployment metadata}"
OUTPUT="${4:?missing output path}"
SINCE_PR="${5:-}"
LIMIT="${ADMIN_UPDATES_PR_LIMIT:-500}"
MERGED_PRS="$(mktemp "${RUNNER_TEMP:-/tmp}/admin-updates-prs.XXXXXX.json")"
trap 'rm -f "$MERGED_PRS"' EXIT

gh pr list --state merged --base main --limit "$LIMIT" \
    --json number,title,body,mergedAt,mergeCommit,files,url > "$MERGED_PRS"

count="$(jq 'length' "$MERGED_PRS")"
if [ "$count" -ge "$LIMIT" ]; then
    echo "admin-updates: merged PR query reached limit=$LIMIT; refusing a possibly incomplete watermark" >&2
    exit 1
fi
if jq -e 'any(.[]; ((.files // []) | length) >= 100)' "$MERGED_PRS" >/dev/null; then
    echo "admin-updates: a PR hit GitHub's 100-file metadata cap; refusing unsafe product classification" >&2
    exit 1
fi

args=(
    --production-context "$PRODUCTION_CONTEXT"
    --production-state "$PRODUCTION_STATE"
    --merged-prs "$MERGED_PRS"
    --deployment "$DEPLOYMENT"
    --repo-root "$REPO_ROOT"
    --output "$OUTPUT"
)
if [ -n "$SINCE_PR" ]; then
    [[ "$SINCE_PR" =~ ^[0-9]+$ ]] || { echo "admin-updates: since_pr must be numeric" >&2; exit 2; }
    args+=(--since-pr "$SINCE_PR")
fi
python3 "$SCRIPT_DIR/collect.py" "${args[@]}"
