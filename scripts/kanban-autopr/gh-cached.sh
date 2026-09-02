#!/usr/bin/env bash
# Run one read-only command and reuse its output for TTL seconds.
#
#   gh-cached.sh TTL_SECONDS CACHE_KEY COMMAND [ARG...]
#
# The four observer panes each re-rendered on their own timer and each issued
# its own `gh pr list` / `gh run view` every cycle, which spent a real slice of
# the hourly REST budget on a dashboard nobody was reading between ticks. The
# panes are observers: showing PR metadata that is a couple of minutes old is
# fine, and the dispatcher — which must not act on stale state — deliberately
# does not use this helper (it calls run-snapshot.sh with its own short TTL and
# ALLOW_STALE=false).
#
# On a command failure the last cached value is served when there is one, so a
# rate-limited or offline pane degrades to stale instead of blank.
set -uo pipefail

TTL_SECONDS="${1:?usage: gh-cached.sh ttl key command...}"
CACHE_KEY="${2:?usage: gh-cached.sh ttl key command...}"
shift 2
[ "$#" -gt 0 ] || { echo "gh-cached.sh: missing command" >&2; exit 2; }

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
CACHE_ROOT="${AUTOPR_GH_CACHE_DIR:-${AUTOPR_DASHBOARD_CACHE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard}/gh}"
CACHE_FILE="$CACHE_ROOT/$(printf '%s' "$CACHE_KEY" | tr -c '[:alnum:]._-' '_').json"

cache_age() {
    local modified now
    modified="$(stat -f '%m' "$CACHE_FILE" 2>/dev/null || true)"
    [[ "$modified" =~ ^[0-9]+$ ]] || modified="$(stat -c '%Y' "$CACHE_FILE" 2>/dev/null || echo 0)"
    now="$(date +%s)"
    printf '%s' "$((now - modified))"
}

mkdir -p "$CACHE_ROOT" 2>/dev/null || true
chmod 700 "$CACHE_ROOT" 2>/dev/null || true

# Cache freshness is file EXISTENCE plus age, not file size: empty output is a
# real answer, and the most common one on this board. `gh pr list --head
# bot/task-xxxx --jq '.[0].number // empty'` prints nothing for the whole time
# a run is mid-investigation, so treating empty as a miss made exactly that
# branch cost one REST call per pane per minute — the spend this helper exists
# to remove. Writes are tmp+mv, so a zero-byte file is a cached answer rather
# than a torn write.
if [ -f "$CACHE_FILE" ] && [ "$(cache_age)" -lt "$TTL_SECONDS" ] 2>/dev/null; then
    cat "$CACHE_FILE"
    exit 0
fi

# Only the command's exit status decides success. Callers that need to
# distinguish "no PR" still see empty output; they just see it without paying
# GitHub for it again.
if output="$("$@" 2>/dev/null)"; then
    tmp="$CACHE_FILE.$$"
    if (umask 077; printf '%s' "$output" > "$tmp") 2>/dev/null; then
        mv "$tmp" "$CACHE_FILE" 2>/dev/null || rm -f "$tmp"
    fi
    printf '%s' "$output"
    exit 0
fi

if [ -f "$CACHE_FILE" ]; then
    cat "$CACHE_FILE"
    exit 0
fi
exit 1
