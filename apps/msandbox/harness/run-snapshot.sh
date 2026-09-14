#!/usr/bin/env bash
# Return one shared, lane-tagged snapshot of every AutoPR workflow run.
#
# All four tmux panes and both dispatcher lanes use this helper. The
# first caller refreshes one unfiltered GitHub run list; concurrent/subsequent
# callers reuse the private local cache instead of each resolving four
# workflow names through GitHub's API.
set -uo pipefail

REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
REF="${AUTOPR_REF:-main}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
CACHE_ROOT="${AUTOPR_GITHUB_SNAPSHOT_CACHE_DIR:-${AUTOPR_DASHBOARD_CACHE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard}/github}"
CACHE_FILE="$CACHE_ROOT/runs.json"
LOCK_DIR="$CACHE_ROOT/runs.lock"
TTL_SECONDS="${AUTOPR_GITHUB_SNAPSHOT_TTL_SECONDS:-60}"
ALLOW_STALE="${AUTOPR_GITHUB_SNAPSHOT_ALLOW_STALE:-true}"

cache_age() {
    local modified now
    modified="$(stat -f '%m' "$CACHE_FILE" 2>/dev/null || true)"
    [[ "$modified" =~ ^[0-9]+$ ]] \
        || modified="$(stat -c '%Y' "$CACHE_FILE" 2>/dev/null || echo 0)"
    now="$(date +%s)"
    printf '%s' "$((now - modified))"
}

cache_is_fresh() {
    [ -s "$CACHE_FILE" ] && [ "$(cache_age)" -lt "$TTL_SECONDS" ] 2>/dev/null
}

emit_cache() {
    jq -e 'type == "array"' "$CACHE_FILE" >/dev/null 2>&1 || return 1
    cat "$CACHE_FILE"
}

mkdir -p "$CACHE_ROOT"
chmod 700 "$CACHE_ROOT" 2>/dev/null || true
if cache_is_fresh; then
    emit_cache
    exit $?
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    # Another pane is already refreshing. A last-known snapshot is preferable
    # to a second API request; only a first-ever simultaneous read may fail.
    [ "$ALLOW_STALE" = true ] || exit 1
    emit_cache
    exit $?
fi
cleanup() {
    [ -z "${raw_file:-}" ] || rm -f "$raw_file"
    [ -z "${next_file:-}" ] || rm -f "$next_file"
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT

# Recheck after acquiring the lock because another process may have refreshed
# between the optimistic freshness check and mkdir.
if cache_is_fresh; then
    emit_cache
    exit $?
fi

raw_file="$CACHE_ROOT/runs.raw.$$"
next_file="$CACHE_ROOT/runs.next.$$"
if ! "$GH_BIN" run list --repo "$REPO" --branch "$REF" --limit 100 \
    --json databaseId,status,conclusion,event,createdAt,updatedAt,url,displayTitle,workflowName \
    > "$raw_file"; then
    [ "$ALLOW_STALE" = true ] || exit 1
    emit_cache
    exit $?
fi

jq '
  map(
    if .workflowName == "Kanban autopr" then . + {lane:"kanban"}
    elif .workflowName == "Silent error autofix" then . + {lane:"errors"}
    elif .workflowName == "AutoPR self audit" then . + {lane:"self-audit"}
    elif .workflowName == "Publish production admin updates" then . + {lane:"admin-updates"}
    else empty end
  )
  | sort_by(.createdAt // "") | reverse
' "$raw_file" > "$next_file" || exit 1
chmod 600 "$next_file" 2>/dev/null || true
mv "$next_file" "$CACHE_FILE"
emit_cache
