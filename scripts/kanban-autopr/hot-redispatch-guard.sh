#!/usr/bin/env bash
# GitHub-side floor between two Kanban runs, independent of the Mac dispatcher.
#
# The dispatcher is supposed to hold the scheduled Kanban lane to one pass per
# twenty minutes and forced runs to one per five. A stale installed copy of it
# re-fired a 35-second no-op run every 66 seconds for hours (2026-09-06); the
# workflow had no defense of its own. This runs first in the job and answers:
#
#   0  proceed
#   3  the previous completed run of this workflow ended less than
#      AUTOPR_HOT_REDISPATCH_FLOOR_SECONDS ago (default 300) — skip this pass
#
# A GitHub API failure proceeds (exit 0): this is a spend guard, not a safety
# boundary, and failing closed here would turn an API blip into a dead lane.
set -uo pipefail

REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
WORKFLOW="${AUTOPR_GUARD_WORKFLOW:-kanban-autopr.yml}"
FLOOR_SECONDS="${AUTOPR_HOT_REDISPATCH_FLOOR_SECONDS:-300}"
NOW="${AUTOPR_GUARD_NOW:-$(date +%s)}"
GH_BIN="${AUTOPR_GH_BIN:-gh}"
HOT=3

iso_to_epoch() {
    local iso="${1%%.*}"
    iso="${iso%Z}"
    date -u -j -f "%Y-%m-%dT%H:%M:%S" "$iso" +%s 2>/dev/null \
        || date -u -d "$1" +%s 2>/dev/null
}

if ! runs="$("$GH_BIN" run list --repo "$REPO" --workflow "$WORKFLOW" --status completed \
        --limit 5 --json databaseId,updatedAt,createdAt 2>/dev/null)"; then
    echo "hot-redispatch guard: could not list runs; proceeding" >&2
    exit 0
fi
last_completed="$(printf '%s' "$runs" | jq -r \
    '[.[] | select((.databaseId | tostring) != ($ENV.GITHUB_RUN_ID // "")) | (.updatedAt // .createdAt)] | max // empty' 2>/dev/null)"
[ -n "$last_completed" ] || exit 0
completed_epoch="$(iso_to_epoch "$last_completed")" || exit 0
[[ "$completed_epoch" =~ ^[0-9]+$ ]] || exit 0
age=$((NOW - completed_epoch))
if [ "$age" -lt "$FLOOR_SECONDS" ]; then
    printf 'hot-redispatch guard: previous %s run completed %ss ago (< %ss); skipping this pass\n' \
        "$WORKFLOW" "$age" "$FLOOR_SECONDS" >&2
    exit "$HOT"
fi
exit 0
