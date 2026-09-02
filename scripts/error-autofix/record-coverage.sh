#!/usr/bin/env bash
# Attach a production incident to the older PR that already covers its fix.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

INCIDENT_FILE="${1:?usage: record-coverage.sh incident.json coverage.json decision.json}"
COVERAGE_FILE="${2:?usage: record-coverage.sh incident.json coverage.json decision.json}"
DECISION_FILE="${3:?usage: record-coverage.sh incident.json coverage.json decision.json}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
KEY="$(jq -r '.stable_key' "$INCIDENT_FILE")"
PR="$(jq -r '.covering_pr' "$COVERAGE_FILE")"
EXPECTED_SHA="$(jq -r '.covering_head_sha' "$COVERAGE_FILE")"
CRITICALITY="$(jq -r '.criticality.level' "$DECISION_FILE")"
CONFIDENCE_SCORE="$(jq -r '.confidence_score' "$DECISION_FILE")"
CONFIDENCE_BAND="$(jq -r '.confidence_band' "$DECISION_FILE")"
[[ "$KEY" =~ ^[0-9a-f]{12}$ ]] || die "stable_key has unexpected shape: $KEY"
[[ "$PR" =~ ^[0-9]+$ ]] || die "coverage is missing a covering PR"

live="$(gh pr view "$PR" --repo "$REPO" --json number,state,headRefOid,url)"
[ "$(printf '%s' "$live" | jq -r '.state')" = OPEN ] || die "covering PR #$PR is no longer open"
[ "$(printf '%s' "$live" | jq -r '.headRefOid')" = "$EXPECTED_SHA" ] || die "covering PR #$PR changed during comparison"

marker="<!-- matcha-autofix-coverage-error: $KEY -->"
comments="$(gh api "repos/$REPO/issues/$PR/comments?per_page=100")"
printf '%s' "$comments" | jq -e 'type == "array"' >/dev/null \
    || die "comments for covering PR #$PR returned invalid JSON"
if ! printf '%s' "$comments" | jq -e --arg marker "$marker" 'any(.[]; (.body // "") | contains($marker))' >/dev/null; then
    method="$(jq -r '.request_method // ""' "$INCIDENT_FILE")"
    path="$(jq -r '.request_path // "unknown endpoint"' "$INCIDENT_FILE")"
    occurrences="$(jq -r '.occurrences // 0' "$INCIDENT_FILE")"
    last_seen="$(jq -r '.last_seen // ""' "$INCIDENT_FILE")"
    error_id="$(jq -r '.error_id // ""' "$INCIDENT_FILE")"
    surface="$(jq -r '.surface // "server"' "$INCIDENT_FILE")"
    admin=""
    if [ -n "$error_id" ] && [ "$surface" = client ]; then
        admin="https://hey-matcha.com/admin/client-errors"
    elif [ -n "$error_id" ]; then
        admin="https://hey-matcha.com/admin/server-errors?search=$error_id"
    fi
    body_file="$(mktemp)"
    trap 'rm -f "$body_file"' EXIT
    {
        echo "$marker"
        echo "<!-- matcha-autofix-notify-review: $KEY -->"
        echo "<!-- matcha-autopr-criticality: $CRITICALITY -->"
        echo "<!-- matcha-autopr-confidence-score: $CONFIDENCE_SCORE -->"
        echo "Production error \`$KEY\` is already scoped by this PR."
        echo
        echo "- Endpoint: \`$method $path\`"
        echo "- Occurrences: $occurrences; last seen: $last_seen"
        [ -z "$admin" ] || echo "- Admin: $admin"
        echo
        echo "Merge and deploy this PR, then resolve the production error after the deployment is verified."
    } > "$body_file"
    gh pr comment "$PR" --repo "$REPO" --body-file "$body_file" >/dev/null
fi
gh pr edit "$PR" --repo "$REPO" --add-label covers-prod-error >/dev/null
gh pr edit "$PR" --repo "$REPO" --add-label "criticality:$CRITICALITY" >/dev/null 2>&1 || true
gh pr edit "$PR" --repo "$REPO" --add-label "confidence:$CONFIDENCE_BAND" >/dev/null 2>&1 || true
printf 'error-autofix: incident %s is already scoped in PR #%s\n' "$KEY" "$PR" >&2
