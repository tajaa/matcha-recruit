#!/usr/bin/env bash
# Explicitly release one fresh AutoPR merge plan. This never bypasses branch
# protection, review requirements, checks, possible-duplicate holds, or a
# context dependency. PRs already ready for review are absent from the plan by
# design and are therefore never merged by this command.
set -euo pipefail

PLAN_FILE="${1:?usage: release-plan.sh plan.json expected-plan-id}"
EXPECTED_PLAN_ID="${2:?usage: release-plan.sh plan.json expected-plan-id}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
WAIT_SECONDS="${AUTOPR_MERGE_WAIT_SECONDS:-900}"
POLL_SECONDS="${AUTOPR_MERGE_POLL_SECONDS:-15}"

[ "${AUTOPR_RELEASE_EXECUTE:-false}" = true ] \
    || { echo "AUTOPR_RELEASE_EXECUTE=true is required" >&2; exit 1; }
jq -e '.schema_version == 1 and (.plan_id | type == "string")' "$PLAN_FILE" >/dev/null
actual_id="$(jq -r '.plan_id' "$PLAN_FILE")"
[ "$actual_id" = "$EXPECTED_PLAN_ID" ] \
    || { echo "stale merge plan: expected $EXPECTED_PLAN_ID, live plan is $actual_id" >&2; exit 1; }

blockers="$(jq '.release_blockers | length' "$PLAN_FILE")"
[ "$blockers" -eq 0 ] \
    || { echo "merge plan $actual_id still has context/check/review blockers" >&2; jq '.release_blockers' "$PLAN_FILE" >&2; exit 1; }

count="$(jq '.merge_order | length' "$PLAN_FILE")"
[ "$count" -gt 0 ] || { echo "merge plan $actual_id has no not-ready PRs to release"; exit 0; }

check_live_pr() {
    local number="$1"
    gh pr view "$number" --repo "$REPO" \
        --json number,state,isDraft,reviewDecision,mergeStateStatus,labels,statusCheckRollup,headRefOid
}

for ((index = 0; index < count; index++)); do
    number="$(jq -r ".merge_order[$index].pr_number" "$PLAN_FILE")"
    declared_dependencies="$(jq -r ".merge_order[$index].depends_on_prs[]?" "$PLAN_FILE")"
    while IFS= read -r dependency; do
        [ -n "$dependency" ] || continue
        state="$(gh pr view "$dependency" --repo "$REPO" --json state --jq '.state')"
        [ "$state" = MERGED ] \
            || { echo "PR #$number dependency #$dependency is $state, not merged" >&2; exit 1; }
    done <<< "$declared_dependencies"

    live="$(check_live_pr "$number")"
    jq -e '.state == "OPEN" and .isDraft == true' <<< "$live" >/dev/null \
        || { echo "PR #$number is no longer the not-ready draft in plan $actual_id" >&2; exit 1; }
    if jq -e '[.labels[].name] | any(. == "autopr-awaiting-input" or . == "needs-work" or . == "possible-duplicate" or . == "production-verification-failed")' <<< "$live" >/dev/null; then
        echo "PR #$number acquired a blocking label after plan generation" >&2
        exit 1
    fi

    gh pr ready "$number" --repo "$REPO" >/dev/null
    deadline=$(( $(date +%s) + WAIT_SECONDS ))
    while :; do
        live="$(check_live_pr "$number")"
        if jq -e '.reviewDecision == "CHANGES_REQUESTED"' <<< "$live" >/dev/null; then
            echo "PR #$number has changes requested" >&2
            exit 1
        fi
        if jq -e '[.statusCheckRollup[]? | (.conclusion // "")] | any(. == "FAILURE" or . == "CANCELLED" or . == "TIMED_OUT" or . == "ACTION_REQUIRED")' <<< "$live" >/dev/null; then
            echo "PR #$number has a failing required check" >&2
            exit 1
        fi
        checks_pending="$(jq '[.statusCheckRollup[]? | select((.status // "") != "COMPLETED")] | length' <<< "$live")"
        merge_state="$(jq -r '.mergeStateStatus // "UNKNOWN"' <<< "$live")"
        if [ "$checks_pending" -eq 0 ] && [ "$merge_state" = CLEAN ]; then
            break
        fi
        [ "$(date +%s)" -lt "$deadline" ] \
            || { echo "timed out waiting for PR #$number (merge=$merge_state pending_checks=$checks_pending)" >&2; exit 1; }
        sleep "$POLL_SECONDS"
    done

    # No --admin and no queued auto-merge: each predecessor is conclusively
    # merged before the next PR is evaluated against the new main.
    gh pr merge "$number" --repo "$REPO" --squash --delete-branch
    state="$(gh pr view "$number" --repo "$REPO" --json state --jq '.state')"
    [ "$state" = MERGED ] || { echo "PR #$number did not reach MERGED" >&2; exit 1; }
    echo "Merged plan $actual_id position $((index + 1))/$count: PR #$number"
done
