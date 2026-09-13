#!/usr/bin/env bash
# Is any card asking for an immediate AutoPR pass?
#
# The scheduled Kanban lane is slow on purpose. This probe is what makes the
# card's "Run AutoPR now" button feel immediate without paying for a board
# bundle — or a GitHub API call — every tick. It answers with an exit status:
#
#   0  at least one pending request (dispatch now)
#   3  nothing queued
#   1  the board could not be asked (caller must not force a run)
#
# Pending means requested and not yet claimed by the harness; investigate.sh
# posts that claim when it picks the card up.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

NOTHING_QUEUED=3

_kanban_autopr_load_env

project_ids="$(printf '%s' "$MATCHA_PROJECT_IDS" | tr -d '[:space:]')"
[ -n "$project_ids" ] || die "MATCHA_PROJECT_IDS is empty"

if ! response="$(mw_api GET "/matcha-work/autopr/run-requests?project_ids=$project_ids" 2>/dev/null)"; then
    exit 1
fi

count="$(printf '%s' "$response" | jq '(.requests // []) | length' 2>/dev/null)" || exit 1
[[ "$count" =~ ^[0-9]+$ ]] || exit 1
[ "$count" -gt 0 ] || exit "$NOTHING_QUEUED"

printf '%s' "$response" | jq -c '.requests'
