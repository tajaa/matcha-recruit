#!/usr/bin/env bash
# Close the loop on merged error-bot fixes: once a fix's merge commit is in
# the deployed build, assert its fingerprint has stopped recurring.
#
# The post-deploy verifier (kanban-autopr/verify-production-fixes.sh) only
# ever looked at `autopr`-labeled PRs with an HTTP check trailer; error-bot
# PRs carry `autofix` and no trailer, so nothing ever confirmed a production
# error was actually gone. This runs in the error lane right after
# collection — the one place that already holds the fresh incident list.
#
# Usage: verify-deployed-fixes.sh incidents.json
#   AUTOFIX_DEPLOYED_SHA  the deployed build (frontend version.json git_sha)
#   Exit 0 always; verdicts land as PR labels + one comment per PR.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

INCIDENTS_FILE="${1:?usage: verify-deployed-fixes.sh incidents.json}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
REPO_ROOT="${AUTOFIX_REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
DEPLOY_GRACE_HOURS="${AUTOFIX_DEPLOY_GRACE_HOURS:-6}"
LOOKBACK_DAYS="${AUTOFIX_VERIFY_LOOKBACK_DAYS:-30}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

deployed_sha="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "${AUTOFIX_DEPLOYED_SHA:-}^{commit}" 2>/dev/null || true)"
if [ -z "$deployed_sha" ]; then
    echo "error-autofix: deployed SHA unknown; skipping fix verification" >&2
    exit 0
fi

_iso_plus_hours() {
    date -u -j -v"+${2}H" -f "%Y-%m-%dT%H:%M:%SZ" "$1" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -d "$1 + $2 hours" +%Y-%m-%dT%H:%M:%SZ
}

since="$(date -u -v"-${LOOKBACK_DAYS}d" +%Y-%m-%d 2>/dev/null || date -u -d "${LOOKBACK_DAYS} days ago" +%Y-%m-%d)"
if ! prs="$(gh pr list --repo "$REPO" --state merged --label autofix --search "merged:>=$since" --limit 100 \
        --json number,mergedAt,mergeCommit,body,labels,url)"; then
    echo "error-autofix: could not list merged autofix PRs" >&2
    exit 0
fi

verified=0; failed=0; waiting=0
while IFS= read -r pr; do
    [ -n "$pr" ] || continue
    number="$(printf '%s' "$pr" | jq -r '.number')"
    if printf '%s' "$pr" | jq -e '[.labels[].name] | any(. == "production-verified" or . == "production-verification-failed")' >/dev/null; then
        continue
    fi
    key="$(printf '%s' "$pr" | jq -r '.body // "" | try capture("<!-- autofix-key: (?<key>[0-9a-f]{12}) -->").key catch ""')"
    merge_sha="$(printf '%s' "$pr" | jq -r '.mergeCommit.oid // empty')"
    merged_at="$(printf '%s' "$pr" | jq -r '.mergedAt // empty')"
    [ -n "$key" ] && [ -n "$merge_sha" ] && [ -n "$merged_at" ] || continue
    git -C "$REPO_ROOT" merge-base --is-ancestor "$merge_sha" "$deployed_sha" 2>/dev/null || { waiting=$((waiting + 1)); continue; }
    # The deploy time is not known here; require the grace window after the
    # merge to have elapsed so a pre-deploy occurrence cannot fail the fix.
    grace_end="$(_iso_plus_hours "$merged_at" "$DEPLOY_GRACE_HOURS")"
    [[ "$NOW" > "$grace_end" ]] || { waiting=$((waiting + 1)); continue; }
    recurrence="$(jq -r --arg key "$key" --arg after "$grace_end" \
        '[.[] | select(.stable_key == $key and .last_seen > $after)] | map(.last_seen) | max // empty' "$INCIDENTS_FILE")"
    comment_file="$(mktemp)"
    if [ -n "$recurrence" ]; then
        printf '## Production verification\n\nDeployed build `%s` contains this merge, but fingerprint `%s` recurred at %s. The fix is **not** marked verified; the error lane will re-investigate it.\n' \
            "$deployed_sha" "$key" "$recurrence" > "$comment_file"
        label=production-verification-failed
        failed=$((failed + 1))
    else
        printf '## Production verification\n\nDeployed build `%s` contains this merge and fingerprint `%s` has not recurred since %s. Marked production verified.\n' \
            "$deployed_sha" "$key" "$grace_end" > "$comment_file"
        label=production-verified
        verified=$((verified + 1))
    fi
    gh pr comment "$number" --repo "$REPO" --body-file "$comment_file" >/dev/null || true
    gh pr edit "$number" --repo "$REPO" --add-label "$label" >/dev/null 2>&1 || true
    rm -f "$comment_file"
done < <(printf '%s' "$prs" | jq -c '.[]')

printf 'error-autofix: deployed-fix verification — verified %s, failed %s, waiting %s\n' "$verified" "$failed" "$waiting" >&2
exit 0
