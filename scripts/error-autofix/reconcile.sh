#!/usr/bin/env bash
# Close an open autofix draft only when a later human PR demonstrably contains
# the same fix. GitHub metadata is collected before Terra runs; Terra receives
# no credentials and writes a strict verdict to a temp file.
#
# Usage: GH_TOKEN=... ./scripts/error-autofix/reconcile.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
LOOKBACK_DAYS="${AUTOFIX_RECONCILE_LOOKBACK_DAYS:-7}"
MODEL="${AUTOFIX_RECONCILE_MODEL:-openai/gpt-5.6-terra}"
WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/autofix-reconcile-XXXXXX")"
TREE_DIR="$WORK_DIR/tree"
trap 'git -C "$REPO_ROOT" worktree remove --force "$TREE_DIR" >/dev/null 2>&1 || true; rm -rf "$WORK_DIR"' EXIT

since="$(date -u -v"-${LOOKBACK_DAYS}d" +%Y-%m-%d 2>/dev/null || date -u -d "${LOOKBACK_DAYS} days ago" +%Y-%m-%d)"
drafts="$WORK_DIR/drafts.json"
merged="$WORK_DIR/merged.json"

gh pr list --repo "$REPO" --state open --label autofix --limit 100 \
    --json number,title,state,isDraft,createdAt,headRefName,body,files,url > "$drafts"
[ "$(jq 'length' "$drafts")" -gt 0 ] || exit 0

gh pr list --repo "$REPO" --state merged --search "merged:>=$since" --limit 100 \
    --json number,title,mergedAt,headRefName,files,url > "$merged"
[ "$(jq 'length' "$merged")" -gt 0 ] || exit 0

git -C "$REPO_ROOT" worktree add --detach "$TREE_DIR" HEAD >/dev/null

while IFS= read -r draft_number; do
    draft="$WORK_DIR/draft-$draft_number.json"
    jq --argjson number "$draft_number" '.[] | select(.number == $number)' "$drafts" > "$draft"
    draft_created="$(jq -r '.createdAt' "$draft")"
    candidates="$WORK_DIR/candidates-$draft_number.json"
    jq --slurpfile draft "$draft" '
        ($draft[0].files | map(.path)) as $draft_files |
        map(select(.mergedAt > $draft[0].createdAt) | select(
            [.files[].path] as $candidate_files |
            any($draft_files[]; . as $path | $candidate_files | index($path))
        ))
    ' "$merged" > "$candidates"
    [ "$(jq 'length' "$candidates")" -gt 0 ] || continue

    draft_diff="$WORK_DIR/draft-$draft_number.diff"
    gh pr diff "$draft_number" --repo "$REPO" > "$draft_diff"
    candidate_diffs=()
    while IFS= read -r candidate_number; do
        candidate_diff="$WORK_DIR/candidate-$candidate_number.diff"
        gh pr diff "$candidate_number" --repo "$REPO" > "$candidate_diff"
        candidate_diffs+=(-f "$candidate_diff")
    done < <(jq -r '.[].number' "$candidates")

    result="$WORK_DIR/result-$draft_number.json"
    prompt="$WORK_DIR/prompt-$draft_number.txt"
    sed "s#RESULT_PATH#$result#g" "$SCRIPT_DIR/_reconcile_prompt.txt" > "$prompt"
    # Terra does not need GitHub or production access to compare the patches.
    env -u GH_TOKEN -u GITHUB_TOKEN -u EC2_SSH_KEY -u SSH_KEY \
        opencode run --auto --model "$MODEL" --variant high --dir "$TREE_DIR" \
        -f "$draft" -f "$candidates" -f "$draft_diff" "${candidate_diffs[@]}" \
        -- "$(<"$prompt")" || continue

    jq -e '
        (.decision == "superseded" or .decision == "no_match" or .decision == "uncertain") and
        (.confidence == "high" or .confidence == "medium" or .confidence == "low") and
        (.reason | type == "string" and length > 0)
    ' "$result" >/dev/null 2>&1 || continue
    [ "$(jq -r '.decision' "$result")" = "superseded" ] || continue
    [ "$(jq -r '.confidence' "$result")" = "high" ] || continue

    replacing_pr="$(jq -r '.replacing_pr' "$result")"
    jq -e --argjson number "$replacing_pr" 'any(.[]; .number == $number)' "$candidates" >/dev/null || continue

    # Re-fetch immediately before mutation. A human may have edited, marked
    # ready, or merged either PR while Terra was comparing their patches.
    live_draft="$(gh pr view "$draft_number" --repo "$REPO" --json number,state,isDraft,headRefName,body,labels)"
    live_replacing="$(gh pr view "$replacing_pr" --repo "$REPO" --json number,state,mergedAt)"
    [ "$(printf '%s' "$live_draft" | jq -r '.state')" = "OPEN" ] || continue
    [ "$(printf '%s' "$live_draft" | jq -r '.isDraft')" = "true" ] || continue
    [[ "$(printf '%s' "$live_draft" | jq -r '.headRefName')" == bot/err-* ]] || continue
    [ "$(printf '%s' "$live_replacing" | jq -r '.state')" = "MERGED" ] || continue
    merged_at="$(printf '%s' "$live_replacing" | jq -r '.mergedAt')"
    [ -n "$merged_at" ] && [ "$merged_at" != "null" ] || continue

    marker="<!-- autofix-superseded-by: $replacing_pr merged-at: $merged_at -->"
    body_file="$WORK_DIR/body-$draft_number.md"
    printf '%s\n\n%s\n' "$(printf '%s' "$live_draft" | jq -r '.body // ""')" "$marker" > "$body_file"
    gh pr edit "$draft_number" --repo "$REPO" --body-file "$body_file" --add-label autofix-superseded >/dev/null
    reason="$(jq -r '.reason' "$result")"
    gh pr close "$draft_number" --repo "$REPO" \
        --comment "Superseded by #$replacing_pr: $reason" >/dev/null

    key="$(printf '%s' "$live_draft" | jq -r 'try capture("<!-- autofix-key: (?<key>[0-9a-f]{12}) -->").key catch ""')"
    if [ -n "$key" ]; then
        nofix="$(gh issue list --repo "$REPO" --state open --label autofix-nofix --limit 100 \
            --json number,title --jq "map(select(.title | contains(\"[$key]\"))) | .[0].number // empty")"
        [ -z "$nofix" ] || gh issue close "$nofix" --repo "$REPO" \
            --comment "Superseded by merged PR #$replacing_pr." >/dev/null
    fi
    printf 'error-autofix: closed draft #%s as superseded by #%s\n' "$draft_number" "$replacing_pr" >&2
done < <(jq -r '.[] | select(.isDraft == true and (.headRefName | startswith("bot/err-"))) | .number' "$drafts")
