#!/usr/bin/env bash
# Collect merged PR metadata with GitHub credentials on the trusted host, then
# reduce it to a production-bounded, credential-free model input.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PRODUCTION_CONTEXT="${1:?usage: collect.sh PRODUCTION_CONTEXT PRODUCTION_STATE DEPLOYMENT OUTPUT [SINCE_PR [SINCE_DATE]]}"
PRODUCTION_STATE="${2:?missing production state}"
DEPLOYMENT="${3:?missing deployment metadata}"
OUTPUT="${4:?missing output path}"
SINCE_PR="${5:-}"
SINCE_DATE="${6:-}"
LIMIT="${ADMIN_UPDATES_PR_LIMIT:-500}"
REST_FILE_LIMIT="${ADMIN_UPDATES_REST_FILE_LIMIT:-3000}"
REPO="${GITHUB_REPOSITORY:-tajaa/matcha-recruit}"
MERGED_PRS="$(mktemp "${RUNNER_TEMP:-/tmp}/admin-updates-prs.XXXXXX.json")"
FULL_FILES=""
NEXT_PRS=""
trap 'rm -f "$MERGED_PRS" "${FULL_FILES:-}" "${NEXT_PRS:-}"' EXIT

gh pr list --state merged --base main --limit "$LIMIT" \
    --json number,title,body,mergedAt,mergeCommit,files,url > "$MERGED_PRS"

count="$(jq 'length' "$MERGED_PRS")"
if [ "$count" -ge "$LIMIT" ]; then
    echo "admin-updates: merged PR query reached limit=$LIMIT; refusing a possibly incomplete watermark" >&2
    exit 1
fi
# GraphQL's `files` connection stops at 100 records. Replace each possibly
# truncated result with the paginated REST list before classifying products;
# otherwise one invisible Tell-Us or frontend path could make us publish an
# incomplete update. GitHub's REST endpoint itself caps a PR at 3,000 files,
# so retain a fail-closed ceiling there.
capped_prs="$(jq -r '.[] | select(((.files // []) | length) >= 100) | .number' "$MERGED_PRS")"
if [ -n "$capped_prs" ]; then
    while IFS= read -r pr_number; do
        [ -n "$pr_number" ] || continue
        FULL_FILES="$(mktemp "${RUNNER_TEMP:-/tmp}/admin-updates-files.XXXXXX.json")"
        gh api --paginate "repos/$REPO/pulls/$pr_number/files?per_page=100" \
            | jq -s 'add | map({path: .filename})' > "$FULL_FILES"
        full_count="$(jq 'length' "$FULL_FILES")"
        if [ "$full_count" -ge "$REST_FILE_LIMIT" ]; then
            echo "admin-updates: PR #$pr_number reached the REST file limit=$REST_FILE_LIMIT; refusing unsafe product classification" >&2
            exit 1
        fi

        NEXT_PRS="$(mktemp "${RUNNER_TEMP:-/tmp}/admin-updates-prs-next.XXXXXX.json")"
        jq --argjson pr_number "$pr_number" --slurpfile files "$FULL_FILES" '
            map(if .number == $pr_number then .files = $files[0] else . end)
        ' "$MERGED_PRS" > "$NEXT_PRS"
        mv "$NEXT_PRS" "$MERGED_PRS"
        NEXT_PRS=""
        rm -f "$FULL_FILES"
        FULL_FILES=""
    done <<< "$capped_prs"
fi

args=(
    --production-context "$PRODUCTION_CONTEXT"
    --production-state "$PRODUCTION_STATE"
    --merged-prs "$MERGED_PRS"
    --deployment "$DEPLOYMENT"
    --repo-root "$REPO_ROOT"
    --output "$OUTPUT"
)
if [ -n "$SINCE_PR" ] && [ -n "$SINCE_DATE" ]; then
    echo "admin-updates: since_pr and since_date are mutually exclusive" >&2
    exit 2
fi
if [ -n "$SINCE_PR" ]; then
    [[ "$SINCE_PR" =~ ^[0-9]+$ ]] || { echo "admin-updates: since_pr must be numeric" >&2; exit 2; }
    args+=(--since-pr "$SINCE_PR")
fi
if [ -n "$SINCE_DATE" ]; then
    args+=(--since-date "$SINCE_DATE")
fi
python3 "$SCRIPT_DIR/collect.py" "${args[@]}"
