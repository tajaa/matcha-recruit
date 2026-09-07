#!/usr/bin/env bash
# Delete automation branches whose pull request is already closed.
#
# kanban-autopr (`bot/*`) and Codex (`codex/*`) leave a branch behind for every
# PR, and the repo does not auto-delete on merge; ~100 of them accumulate. Only
# branches matching those prefixes are ever considered, and only when EVERY PR
# ever opened from the branch is closed (merged or not) and the most recent one
# closed more than MIN_AGE_DAYS ago. Branches with no PR at all are left alone —
# that is in-progress work, not litter.
#
#   prune-merged-bot-branches.sh [--dry-run] [--prefix bot/ --prefix codex/]
#
# Needs: gh (authenticated), jq, GITHUB_REPOSITORY.
set -euo pipefail

REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
MIN_AGE_DAYS="${MIN_AGE_DAYS:-7}"
DRY_RUN=false
PREFIXES=()
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --prefix) PREFIXES+=("$2"); shift 2 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done
[ ${#PREFIXES[@]} -gt 0 ] || PREFIXES=(bot/ codex/)

cutoff="$(date -u -d "-${MIN_AGE_DAYS} days" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
       || date -u -v-"${MIN_AGE_DAYS}"d +%Y-%m-%dT%H:%M:%SZ)"

default_branch="$(gh api "repos/$REPO" --jq .default_branch)"

for prefix in "${PREFIXES[@]}"; do
    case "$prefix" in
        */) ;;
        *) echo "prefix must end with '/': $prefix" >&2; exit 2 ;;
    esac
    # Never let a prefix widen to the default branch or to human-owned trees.
    case "$prefix" in
        "$default_branch"/|main/|master/|claude/|matcha/|release/) echo "refusing prefix $prefix" >&2; exit 2 ;;
    esac
done

all_branches="$(gh api --paginate "repos/$REPO/branches?per_page=100" --jq '.[].name')"
candidates="$(for prefix in "${PREFIXES[@]}"; do
    grep -E "^$(printf '%s' "$prefix" | sed 's/[.[\*^$/]/\\&/g')" <<< "$all_branches" || true
done | sort -u)"

deleted=0; kept=0; skipped=0
while IFS= read -r branch; do
    [ -n "$branch" ] || continue
    prs="$(gh api --paginate "repos/$REPO/pulls?state=all&head=${REPO%%/*}:${branch}&per_page=100" \
        --jq '[.[] | {state, merged: (.merged_at != null), closed_at}]')"
    total="$(jq 'length' <<< "$prs")"
    if [ "$total" -eq 0 ]; then
        echo "keep   $branch (no PR yet)"
        skipped=$((skipped + 1))
        continue
    fi
    open="$(jq '[.[] | select(.state == "open")] | length' <<< "$prs")"
    if [ "$open" -gt 0 ]; then
        echo "keep   $branch ($open open PR)"
        kept=$((kept + 1))
        continue
    fi
    newest_closed="$(jq -r '[.[].closed_at] | max' <<< "$prs")"
    if [[ "$newest_closed" > "$cutoff" ]]; then
        echo "keep   $branch (closed $newest_closed, younger than ${MIN_AGE_DAYS}d)"
        kept=$((kept + 1))
        continue
    fi
    if [ "$DRY_RUN" = true ]; then
        echo "would-delete $branch (last PR closed $newest_closed)"
    else
        gh api -X DELETE "repos/$REPO/git/refs/heads/$branch" >/dev/null
        echo "delete $branch (last PR closed $newest_closed)"
    fi
    deleted=$((deleted + 1))
done <<< "$candidates"

echo "done: deleted=$deleted kept=$kept no_pr=$skipped dry_run=$DRY_RUN"
