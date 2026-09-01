#!/usr/bin/env bash
# Verify merged Kanban AutoPRs only after their merge commit is contained in
# the deployed source SHA. Automatic checks are a tiny allowlisted read-only
# HTTP schema; authenticated/stateful/visual plans become an explicit manual
# production gate instead of being falsely marked verified.
set -euo pipefail

DEPLOYED_SHA="${1:?usage: verify-production-fixes.sh deployed-sha deploy-target}"
DEPLOY_TARGET="${2:?usage: verify-production-fixes.sh deployed-sha deploy-target}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
SITE_URL="${AUTOPR_PRODUCTION_SITE_URL:-https://hey-matcha.com}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

full_sha="$(git rev-parse "$DEPLOYED_SHA^{commit}")" \
    || { echo "deployed SHA is not present in checkout: $DEPLOYED_SHA" >&2; exit 1; }

decode_spec() {
    local encoded="$1"
    if printf '%s' "$encoded" | base64 --decode 2>/dev/null; then
        return
    fi
    printf '%s' "$encoded" | base64 -D 2>/dev/null
}

target_is_live() {
    local required="$1"
    # A full Matcha rollout contains either component. A component-only rollout
    # may prove only that same component; a fix requiring both must wait for a
    # full rollout rather than passing after half of its code is live.
    [ "$DEPLOY_TARGET" = matcha ] || [ "$required" = "$DEPLOY_TARGET" ]
}

replace_verification_labels() {
    local number="$1" add="$2"
    local labels old
    labels="$(gh pr view "$number" --repo "$REPO" --json labels --jq '.labels[].name')"
    for old in production-verified production-verification-needed production-verification-failed; do
        if [ "$old" != "$add" ] && printf '%s\n' "$labels" | grep -qx "$old"; then
            gh pr edit "$number" --repo "$REPO" --remove-label "$old" >/dev/null
        fi
    done
    if ! printf '%s\n' "$labels" | grep -qx "$add"; then
        gh pr edit "$number" --repo "$REPO" --add-label "$add" >/dev/null
    fi
}

prs="$(gh pr list --repo "$REPO" --state merged --label autopr --limit 100 \
    --json number,title,mergeCommit,body,labels,mergedAt,url)"
processed=0
failed=0
manual=0
passed=0

while IFS= read -r pr; do
    number="$(printf '%s' "$pr" | jq -r '.number')"
    merge_sha="$(printf '%s' "$pr" | jq -r '.mergeCommit.oid // empty')"
    body="$(printf '%s' "$pr" | jq -r '.body // ""')"
    encoded="$(printf '%s' "$body" | sed -nE 's/.*<!-- matcha-production-verification: ([A-Za-z0-9+\/=]+) -->.*/\1/p' | tail -1)"
    [ -n "$merge_sha" ] && [ -n "$encoded" ] || continue
    git merge-base --is-ancestor "$merge_sha" "$full_sha" || continue
    if printf '%s' "$pr" | jq -e '[.labels[].name] | any(
        . == "production-verified"
        or . == "production-verification-needed"
        or . == "production-verification-failed"
    )' >/dev/null; then
        continue
    fi
    if ! spec="$(decode_spec "$encoded")" \
        || ! printf '%s' "$spec" | jq -e '
          type == "object"
          and (.target | IN("backend","frontend","both"))
          and (.mode | IN("automatic_http","manual"))
          and (.reason | type == "string" and length > 0)
          and (.checks | type == "array")
          and (.steps | type == "array")
        ' >/dev/null; then
        echo "PR #$number has an invalid production verification trailer" >&2
        failed=$((failed + 1))
        continue
    fi
    required_target="$(printf '%s' "$spec" | jq -r '.target')"
    target_is_live "$required_target" || continue
    processed=$((processed + 1))
    mode="$(printf '%s' "$spec" | jq -r '.mode')"
    comment_file="$TMP_DIR/pr-$number.md"

    if [ "$mode" = manual ]; then
        {
            echo "## Production verification required"
            echo
            echo "This merge is now present in deployed production \`$full_sha\`, but its reviewed check requires an authenticated, stateful, or visual production test. It has **not** been marked fixed."
            echo
            printf '%s' "$spec" | jq -r '.steps | to_entries[] | "\(.key + 1). \(.value)"'
        } > "$comment_file"
        gh pr comment "$number" --repo "$REPO" --body-file "$comment_file" >/dev/null
        replace_verification_labels "$number" production-verification-needed
        manual=$((manual + 1))
        continue
    fi

    if ! printf '%s' "$spec" | jq -L "$SCRIPT_DIR" -e '
      include "production-check";
      (.checks | length >= 1 and length <= 5)
      and all(.checks[]; valid_production_http_check)
    ' >/dev/null; then
        echo "PR #$number automatic production plan failed the HTTP allowlist" >&2
        replace_verification_labels "$number" production-verification-failed
        failed=$((failed + 1))
        continue
    fi

    check_failed=0
    : > "$comment_file"
    {
        echo "## Production verification"
        echo
        echo "Deployed SHA: \`$full_sha\`"
        echo
        echo "| Check | Expected | Observed | Result |"
        echo "|---|---:|---:|---|"
    } >> "$comment_file"
    check_count="$(printf '%s' "$spec" | jq '.checks | length')"
    for ((check_index = 0; check_index < check_count; check_index++)); do
        check="$(printf '%s' "$spec" | jq -c ".checks[$check_index]")"
        path="$(printf '%s' "$check" | jq -r '.path')"
        expected_status="$(printf '%s' "$check" | jq -r '.expected_status')"
        contains="$(printf '%s' "$check" | jq -r '.body_contains // ""')"
        absent="$(printf '%s' "$check" | jq -r '.body_absent // ""')"
        response_file="$TMP_DIR/pr-$number-check-$check_index.body"
        # Do not follow redirects: an otherwise safe same-origin path must not
        # make the trusted verifier fetch an arbitrary redirect destination.
        observed_status="$(curl -sS --max-time 20 --max-filesize 2097152 -o "$response_file" -w '%{http_code}' "$SITE_URL$path" || printf 000)"
        result=pass
        [ "$observed_status" = "$expected_status" ] || result=fail
        [ -z "$contains" ] || grep -Fq -- "$contains" "$response_file" || result=fail
        if [ -n "$absent" ] && grep -Fq -- "$absent" "$response_file"; then result=fail; fi
        [ "$result" = pass ] || check_failed=1
        printf '| `GET %s` | %s | %s | %s |\n' "$path" "$expected_status" "$observed_status" "$result" >> "$comment_file"
    done

    if [ "$check_failed" -eq 0 ]; then
        echo >> "$comment_file"
        echo "All reviewed read-only production assertions passed; the issue is marked production verified." >> "$comment_file"
        gh pr comment "$number" --repo "$REPO" --body-file "$comment_file" >/dev/null
        replace_verification_labels "$number" production-verified
        passed=$((passed + 1))
    else
        echo >> "$comment_file"
        echo "At least one reviewed production assertion failed; the issue is **not** marked fixed." >> "$comment_file"
        gh pr comment "$number" --repo "$REPO" --body-file "$comment_file" >/dev/null
        replace_verification_labels "$number" production-verification-failed
        failed=$((failed + 1))
    fi
done < <(printf '%s' "$prs" | jq -c 'sort_by(.mergedAt // "")[]')

jq -n --arg deployed_sha "$full_sha" --arg target "$DEPLOY_TARGET" \
    --argjson processed "$processed" --argjson passed "$passed" \
    --argjson manual "$manual" --argjson failed "$failed" \
    '{deployed_sha:$deployed_sha,target:$target,processed:$processed,passed:$passed,manual_required:$manual,failed:$failed}'

[ "$failed" -eq 0 ]
