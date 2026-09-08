#!/usr/bin/env bash
# Collect bounded planning context for every open bot PR. PR bodies, comments,
# and reviews are untrusted text: this script only serializes them for the
# planner/model and never evaluates their contents.
set -euo pipefail

REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
ROWS_FILE="$TMP_DIR/prs.jsonl"
: > "$ROWS_FILE"

# Filter by label SERVER-side, one call per label (gh's --label is AND across
# repeats, so an OR needs one list each). Listing 100 open PRs and filtering
# client-side silently drops every bot PR past the hundredth most recent, and
# select.sh derives its open-PR cap from this snapshot: the cap would read low
# exactly when the repo is busiest — which is when it has to fire.
open="$(
    {
        for label in autopr autofix autopr-self-audit; do
            gh pr list --repo "$REPO" --state open --label "$label" --limit 100 \
                --json number,title,isDraft,headRefName,headRefOid,createdAt,updatedAt,labels,url \
                || exit 1
        done
    } | jq -s 'add | unique_by(.number)'
)"

while IFS= read -r number; do
    [ -n "$number" ] || continue
    if ! detail="$(gh pr view "$number" --repo "$REPO" \
        --json number,title,isDraft,state,headRefName,headRefOid,createdAt,updatedAt,labels,url,body,reviewDecision,statusCheckRollup,comments,reviews,files 2>/dev/null)"; then
        # Fail closed at the aggregate level. A partial PR snapshot can invent
        # an ordering by making a dependency/comment disappear.
        echo "could not read planning context for PR #$number" >&2
        exit 1
    fi
    bounded="$(printf '%s' "$detail" | jq -c '
      .body = ((.body // "")[0:6000])
      | .comments = ((.comments // [])[-10:] | map({
          author: (.author.login // "unknown"),
          createdAt,
          body: ((.body // "")[0:2000])
        }))
      | .reviews = ((.reviews // [])[-10:] | map({
          author: (.author.login // "unknown"),
          submittedAt,
          state,
          body: ((.body // "")[0:2000])
        }))
      | .files = ((.files // []) | map(.path) | .[0:100])
      | .labels = ((.labels // []) | map(.name))
      | .checks = ((.statusCheckRollup // []) | map({
          name: (.name // .context // "check"),
          status: (.status // "UNKNOWN"),
          conclusion: (.conclusion // null)
        }))
      | del(.statusCheckRollup)
    ')"
    printf '%s\n' "$bounded" >> "$ROWS_FILE"
done < <(printf '%s' "$open" | jq -r '.[].number')

jq -s '.' "$ROWS_FILE"
