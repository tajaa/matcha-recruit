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
#   AUTOFIX_HOURS/_LIMIT  the window collect.sh was given; every verdict is
#                         bounded by it, because that snapshot is the only
#                         evidence this script has
#   Exit 0 always; verdicts land as PR labels + one comment per PR.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

INCIDENTS_FILE="${1:?usage: verify-deployed-fixes.sh incidents.json}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
REPO_ROOT="${AUTOFIX_REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
CACHE_DIR="${AUTOFIX_CACHE_DIR:-$HOME/.cache/matcha-autofix}"
DEPLOY_LEDGER="${AUTOFIX_DEPLOY_LEDGER:-$CACHE_DIR/deployed-sha-first-seen.json}"
DEPLOY_GRACE_HOURS="${AUTOFIX_DEPLOY_GRACE_HOURS:-6}"
LOOKBACK_DAYS="${AUTOFIX_VERIFY_LOOKBACK_DAYS:-30}"
# The window collect.sh was given. The incident snapshot is the only evidence
# here, so a verdict may never claim more than this window actually shows.
OBSERVED_HOURS="${AUTOFIX_HOURS:-24}"
OBSERVED_LIMIT="${AUTOFIX_LIMIT:-25}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OBSERVED_SINCE="$(date -u -v"-${OBSERVED_HOURS}H" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -d "${OBSERVED_HOURS} hours ago" +%Y-%m-%dT%H:%M:%SZ)"

deployed_sha="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "${AUTOFIX_DEPLOYED_SHA:-}^{commit}" 2>/dev/null || true)"
if [ -z "$deployed_sha" ]; then
    echo "error-autofix: deployed SHA unknown; skipping fix verification" >&2
    exit 0
fi

# version.json names the deployed SHA but not when it shipped, and deploys here
# are manual: a fix can merge weeks before it goes live. Remember when this lane
# first observed each SHA live — it runs every couple of hours — and use that as
# the deploy time. Without it `merged_at` stands in for the deploy, and every
# occurrence from the pre-deploy weeks scores as a recurrence, permanently
# labelling a working fix production-verification-failed.
remember_deployed_sha() {
    local sha="$1" cutoff
    mkdir -p "$(dirname "$DEPLOY_LEDGER")"
    [ -s "$DEPLOY_LEDGER" ] || printf '{}\n' > "$DEPLOY_LEDGER"
    cutoff="$(date -u -v"-${LOOKBACK_DAYS}d" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -d "${LOOKBACK_DAYS} days ago" +%Y-%m-%dT%H:%M:%SZ)"
    jq -c --arg sha "$sha" --arg now "$NOW" --arg cutoff "$cutoff" \
        'with_entries(select(.value >= $cutoff)) | (.[$sha] //= $now)' \
        "$DEPLOY_LEDGER" > "$DEPLOY_LEDGER.tmp" 2>/dev/null \
        && mv "$DEPLOY_LEDGER.tmp" "$DEPLOY_LEDGER"
}

# The earliest observed deploy that already contained this merge. The currently
# live SHA is only an upper bound — the fix may have shipped several deploys
# ago — so scan the ledger instead of assuming the newest build carried it.
first_live_at() {
    local merge_sha="$1" sha seen resolved best=""
    while IFS=$'\t' read -r sha seen; do
        [ -n "$sha" ] && [ -n "$seen" ] || continue
        resolved="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "$sha^{commit}" 2>/dev/null || true)"
        [ -n "$resolved" ] || continue
        git -C "$REPO_ROOT" merge-base --is-ancestor "$merge_sha" "$resolved" 2>/dev/null || continue
        if [ -z "$best" ] || [[ "$seen" < "$best" ]]; then
            best="$seen"
        fi
    done < <(jq -r 'to_entries[] | "\(.key)\t\(.value)"' "$DEPLOY_LEDGER" 2>/dev/null)
    printf '%s' "$best"
}

remember_deployed_sha "$deployed_sha"

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
    # The window opens at the deploy that carried this merge, never at the
    # merge itself. Unknown go-live ⇒ treat it as live now, i.e. keep waiting.
    live_at="$(first_live_at "$merge_sha")"
    [ -n "$live_at" ] || live_at="$NOW"
    [[ "$live_at" > "$merged_at" ]] || live_at="$merged_at"
    grace_end="$(_iso_plus_hours "$live_at" "$DEPLOY_GRACE_HOURS")"
    [[ "$NOW" > "$grace_end" ]] || { waiting=$((waiting + 1)); continue; }
    # The snapshot only sees the last OBSERVED_HOURS hours, so nothing can be
    # asserted about anything older. Score over the later of the two bounds and
    # state which one the verdict rests on rather than implying full coverage.
    claim_since="$grace_end"
    [[ "$claim_since" > "$OBSERVED_SINCE" ]] || claim_since="$OBSERVED_SINCE"
    recurrence="$(jq -r --arg key "$key" --arg after "$claim_since" \
        '[.[] | select(.stable_key == $key and .last_seen > $after)] | map(.last_seen) | max // empty' "$INCIDENTS_FILE")"
    comment_file="$(mktemp)"
    if [ -n "$recurrence" ]; then
        printf '## Production verification\n\nDeployed build `%s` shipped this merge (first seen live %s), but fingerprint `%s` recurred at %s. The fix is **not** marked verified; the error lane will re-investigate it.\n' \
            "$deployed_sha" "$live_at" "$key" "$recurrence" > "$comment_file"
        label=production-verification-failed
        failed=$((failed + 1))
    else
        printf '## Production verification\n\nDeployed build `%s` shipped this merge (first seen live %s). Fingerprint `%s` is absent from the incident snapshot since %s — top %s actionable incidents over a rolling %s h window. Marked production verified.\n' \
            "$deployed_sha" "$live_at" "$key" "$claim_since" "$OBSERVED_LIMIT" "$OBSERVED_HOURS" > "$comment_file"
        label=production-verified
        verified=$((verified + 1))
    fi
    gh pr comment "$number" --repo "$REPO" --body-file "$comment_file" >/dev/null || true
    gh pr edit "$number" --repo "$REPO" --add-label "$label" >/dev/null 2>&1 || true
    rm -f "$comment_file"
done < <(printf '%s' "$prs" | jq -c '.[]')

printf 'error-autofix: deployed-fix verification — verified %s, failed %s, waiting %s\n' "$verified" "$failed" "$waiting" >&2
exit 0
