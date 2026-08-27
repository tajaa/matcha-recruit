#!/usr/bin/env bash
# Pick the first card from cards.json that isn't already handled by an open
# PR, isn't durably marked unscopable, and isn't mid-cooldown from a just-
# crashed attempt. GitHub is the durable dedup ledger for PRs; the card's own
# progress_note is the durable ledger for "can't be scoped, don't retry
# forever" (unlike error-autofix, this lives on the card, visible to the
# human who owns it — not a GitHub issue nobody on the board sees).
#
# Usage: ./select.sh cards.json > card.json
# Exit 3 (not 1) means "nothing to do" — the workflow treats 3 as
# success-and-stop, not failure.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

CARDS_FILE="${1:?usage: select.sh cards.json}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
CACHE_DIR="${AUTOPR_CACHE_DIR:-$HOME/.cache/matcha-autopr}"
ATTEMPTS_DIR="$CACHE_DIR/attempts"
mkdir -p "$ATTEMPTS_DIR"

NOTHING_TO_DO=3
MAX_OPEN_AUTOPR_PRS=3
ATTEMPT_COOLDOWN_MINUTES="${AUTOPR_ATTEMPT_COOLDOWN_MINUTES:-15}"

count="$(jq 'length' "$CARDS_FILE")"
[ "$count" -gt 0 ] || exit "$NOTHING_TO_DO"

# Backstop: never let a bad batch of cards produce an unbounded number of
# NEW open bot PRs. Checked per-decision below, not here — rework pushes a
# commit to a PR that's already open (it doesn't add to this count), so the
# cap must never block rework just because 3 unrelated PRs are already open.
open_autopr_prs="$(gh pr list --repo "$REPO" --state open --label autopr --limit 100 --json number --jq 'length')"

# already_handled ID8 BOARD_COLUMN LAST_MOVED_AT PROGRESS_NOTE
# Echoes "skip", "investigate", or "rework" (rework = push to the existing
# open PR rather than opening a new one).
already_handled() {
    local id8="$1" column="$2" last_moved="$3" progress_note="$4" branch="bot/task-$id8"

    local attempt_marker="$ATTEMPTS_DIR/$id8"
    if [ -f "$attempt_marker" ]; then
        local age_s
        age_s=$(( $(date +%s) - $(date -r "$attempt_marker" +%s 2>/dev/null || echo 0) ))
        if [ "$age_s" -lt $((ATTEMPT_COOLDOWN_MINUTES * 60)) ]; then
            echo skip
            return
        fi
    fi

    # No-spec ledger lives on the card itself, not GitHub — this stops a
    # vague card being re-run every cron tick forever, and clears the moment
    # a human edits progress_note or moves the card (last_moved_at advances).
    if [[ "$progress_note" == *"[autopr:no-spec "* ]]; then
        # Full ISO timestamp, not just a date: BSD `date -j -f` fills any
        # field the format string doesn't specify from the CURRENT time, not
        # midnight — a date-only marker parsed on a later run would silently
        # pick up that run's wall-clock time, making "moved after the
        # marker" drift throughout the day instead of comparing two fixed
        # instants.
        local marker_ts marker_epoch
        marker_ts="$(printf '%s' "$progress_note" | sed -E 's/^.*\[autopr:no-spec ([0-9TZ:-]+)\].*/\1/')"
        marker_epoch="$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$marker_ts" +%s 2>/dev/null || date -u -d "$marker_ts" +%s 2>/dev/null || echo 0)"
        local moved_epoch
        moved_epoch="$(date -u -j -f "%Y-%m-%dT%H:%M:%S" "${last_moved:0:19}" +%s 2>/dev/null || date -u -d "$last_moved" +%s 2>/dev/null || echo 0)"
        if [ "$moved_epoch" -le "$marker_epoch" ]; then
            echo skip
            return
        fi
    fi

    local prs n
    if ! prs="$(gh pr list --repo "$REPO" --head "$branch" --state all --limit 10 \
        --json state,createdAt --jq 'sort_by(.createdAt) | reverse')"; then
        # A transient gh/API failure must fail CLOSED (skip this card) — the
        # unhardened version let a malformed/empty $prs fall through `jq` and
        # `[ -gt ]` as silent no-ops, which read as "no PR exists yet" and
        # proceeded to `investigate`, risking a duplicate PR the failed call
        # simply couldn't see.
        echo skip
        return
    fi
    n="$(printf '%s' "$prs" | jq 'length' 2>/dev/null)" || n=0
    n="${n:-0}"

    if [ "$column" = "changes_requested" ]; then
        # This is the one place the logic inverts vs error-autofix: for
        # rework, an OPEN PR on this branch is the TARGET to push to, not a
        # reason to skip. No open PR means the card was moved to
        # changes_requested by hand (never had a bot PR) — treat it like a
        # fresh todo card instead.
        local state
        state="$(printf '%s' "$prs" | jq -r '.[0].state // empty')"
        if [ "$state" = "OPEN" ]; then
            echo rework
        else
            echo investigate
        fi
        return
    fi

    # todo: any PR at all on this branch (open, closed, or merged) means a
    # bot already worked this card — the branch name is stable
    # (bot/task-<id8>), so a second run would collide. If the card is back
    # in todo after a merge/close, a human moved it there deliberately;
    # investigate.sh will see the fresh state.
    [ "$n" -gt 0 ] && { echo skip; return; }
    echo investigate
}

# Rank: changes_requested before todo (already-specified rework unblocks a
# PR in flight), then oldest last_moved_at (falling back to created_at) first
# within each group.
ranked="$(jq -c '
    sort_by(
        (if .board_column == "changes_requested" then 0 else 1 end),
        (.last_moved_at // .created_at)
    )
' "$CARDS_FILE")"

n="$(printf '%s' "$ranked" | jq 'length')"
for ((i = 0; i < n; i++)); do
    card="$(printf '%s' "$ranked" | jq -c ".[$i]")"
    id8="$(printf '%s' "$card" | jq -r '.id8')"
    column="$(printf '%s' "$card" | jq -r '.board_column')"
    last_moved="$(printf '%s' "$card" | jq -r '.last_moved_at // .created_at')"
    progress_note="$(printf '%s' "$card" | jq -r '.progress_note // ""')"

    decision="$(already_handled "$id8" "$column" "$last_moved" "$progress_note")"
    if [ "$decision" = investigate ] && [ "$open_autopr_prs" -ge "$MAX_OPEN_AUTOPR_PRS" ]; then
        # A NEW PR would push past the cap — this specific card can't go,
        # but a later, lower-ranked card might be `rework` (no new PR) and
        # still eligible, so skip this one and keep looking rather than
        # bailing the whole run.
        continue
    fi
    if [ "$decision" = investigate ] || [ "$decision" = rework ]; then
        touch "$ATTEMPTS_DIR/$id8"
        printf '%s' "$card" | jq -c --arg mode "$decision" '. + {mode: $mode}'
        exit 0
    fi
done

exit "$NOTHING_TO_DO"
