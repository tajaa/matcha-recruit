#!/usr/bin/env bash
# Operator control of one AutoPR card from a terminal: hold it, release the
# hold, ask for an immediate run, put a stranded In Progress card back in a
# lane, or cancel the run that is working it. The board already had every
# primitive (unqueue, run-defer, run-now, column moves); this is the missing
# command-line face, and `msandbox autopr …` is a thin wrapper over it.
#
#   card-control.sh resolve   <id8|uuid|title-substring> [--json]
#   card-control.sh hold      <target> [--reason R]
#   card-control.sh release   <target>
#   card-control.sh run-now   <target>
#   card-control.sh unstick   <target> [--hold] [--reason R]
#   card-control.sh cancel-run [target] [--hold] [--reason R]
#   card-control.sh log       <target>          what its runs did, why they stopped
#
# Exit 0 on success, 2 when the target is ambiguous/unknown/usage, 3 when
# cancel-run finds no active Kanban run, 1 for a failed board call (via die).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
RUN_SNAPSHOT="${AUTOPR_RUN_SNAPSHOT:-$SCRIPT_DIR/run-snapshot.sh}"
USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
RUNNER_WORKTREE="${AUTOPR_RUNNER_WORKTREE:-$USER_HOME/.local/share/matcha-actions-runner/_work/matcha-recruit/matcha-recruit}"
GIT_BIN="${AUTOPR_GIT_BIN:-git}"

usage() {
    sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
    exit 2
}

VERB="${1:-}"
[ -n "$VERB" ] || usage
shift
TARGET="" REASON="held by operator" HOLD=false JSON=false
while [ "$#" -gt 0 ]; do
    case "$1" in
        --reason) REASON="${2:?--reason needs a value}"; shift 2 ;;
        --reason=*) REASON="${1#--reason=}"; shift ;;
        --hold) HOLD=true; shift ;;
        --json) JSON=true; shift ;;
        -*) echo "unknown option: $1" >&2; usage ;;
        *) [ -z "$TARGET" ] || { echo "one target only" >&2; usage; }; TARGET="$1"; shift ;;
    esac
done

# Every card on every watched board that matches the target, one JSON object
# per line. A task id prefix wins over a title match so an id8 never collides
# with a title containing the same characters.
matching_cards() {
    local query="$1" project
    _kanban_autopr_load_env
    for project in ${MATCHA_PROJECT_IDS//,/ }; do
        project="${project//[[:space:]]/}"
        [ -n "$project" ] || continue
        mw_api GET "/matcha-work/projects/$project/bundle" | jq -c --arg q "$query" --arg p "$project" '
            [.tasks[]? | select(.status != "cancelled")
              | select(((.id // "") | ascii_downcase | startswith($q | ascii_downcase))
                       or ((.title // "") | ascii_downcase | contains($q | ascii_downcase)))]
            | .[] | {project_id: $p, task_id: .id, id8: (.id[0:8]), board_column: .board_column,
                     id_match: ((.id // "") | ascii_downcase | startswith($q | ascii_downcase)),
                     pr_number: (.pr_number // null), autopr_paused: (.autopr_paused // false),
                     autopr_hold_reason: (.autopr_hold_reason // null), title: (.title // "")}'
    done | jq -c -s 'if any(.[]; .id_match) then map(select(.id_match)) else . end | .[] | del(.id_match)'
}

resolve_card() {
    local query="$1" matches count
    [ -n "$query" ] || { echo "a card target is required (id8, uuid, or title text)" >&2; exit 2; }
    matches="$(matching_cards "$query")"
    count="$(printf '%s\n' "$matches" | grep -c . || true)"
    if [ "$count" -ne 1 ]; then
        if [ "$count" -eq 0 ]; then
            echo "no card matches '$query' on the watched boards" >&2
        else
            echo "'$query' matches $count cards; use an id8 or a longer title fragment:" >&2
            printf '%s\n' "$matches" | jq -r '"  " + .id8 + "  " + .board_column + "  " + .title' >&2
        fi
        exit 2
    fi
    printf '%s' "$matches"
}

card_line() {
    printf '%s' "$1" | jq -r '[.project_id, .task_id, .board_column, ((.pr_number // "-") | tostring),
        (.autopr_paused | tostring), .title] | @tsv'
}

card_field() { printf '%s' "$1" | jq -r "$2"; }

hold_card() {
    local card="$1" project task
    project="$(card_field "$card" .project_id)"; task="$(card_field "$card" .task_id)"
    mw_api POST "/matcha-work/projects/$project/tasks/$task/autopr/unqueue" \
        "$(jq -cn --arg reason "$REASON" '{reason: $reason}')" >/dev/null
    printf 'held %s · %s · %s\n' "$(card_field "$card" .id8)" "$(card_field "$card" .title)" "$REASON"
}

release_card() {
    local card="$1" project task
    project="$(card_field "$card" .project_id)"; task="$(card_field "$card" .task_id)"
    # run-defer settles the hold as the bot without queueing anything; the
    # routine sweep or an explicit run-now picks the card up from there.
    mw_api POST "/matcha-work/projects/$project/tasks/$task/autopr/run-defer" '{}' >/dev/null
    printf 'released %s · %s\n' "$(card_field "$card" .id8)" "$(card_field "$card" .title)"
}

run_now_card() {
    local card="$1" project task
    project="$(card_field "$card" .project_id)"; task="$(card_field "$card" .task_id)"
    # The hand-off helper records the durable board request first, then tries
    # an immediate dispatch; a failed kick still leaves the request queued.
    if "$SCRIPT_DIR/queue-handoff.sh" "$project" "$task" >/dev/null; then
        printf 'dispatched %s · %s\n' "$(card_field "$card" .id8)" "$(card_field "$card" .title)"
    else
        printf 'queued %s · %s (immediate dispatch declined; the watcher retries)\n' \
            "$(card_field "$card" .id8)" "$(card_field "$card" .title)"
    fi
}

unstick_card() {
    local card="$1" project task column
    project="$(card_field "$card" .project_id)"; task="$(card_field "$card" .task_id)"
    # Only a stranded claim is ours to move. A Review or Done card that
    # happens to match the target must not be dragged back into a lane the
    # selector picks from; the server gates holds this way but not raw moves.
    if [ "$(card_field "$card" .board_column)" != in_progress ]; then
        printf 'refusing to unstick %s · %s: it is in %s, not In Progress\n' \
            "$(card_field "$card" .id8)" "$(card_field "$card" .title)" \
            "$(card_field "$card" .board_column)" >&2
        exit 2
    fi
    column=todo
    [ "$(card_field "$card" '.pr_number // empty')" = "" ] || column=changes_requested
    # Move first: unqueue refuses a card that is not in Todo or Changes
    # Requested, so a hold on a stranded In Progress card must follow the move.
    mw_move_card "$project" "$task" "$column"
    printf 'moved %s · %s → %s\n' "$(card_field "$card" .id8)" "$(card_field "$card" .title)" "$column"
    [ "$HOLD" != true ] || hold_card "$card"
}

# Everything the system knows about a card's runs, newest first: the run
# journals Cleanup attaches to the ticket (the newest printed in full), the
# failure ledger select.sh consults, and the resumable checkpoints on the
# runner. Reads only.
log_card() {
    local card="$1" project task id8 files journals newest_url ledger checkpoints printed
    project="$(card_field "$card" .project_id)"; task="$(card_field "$card" .task_id)"
    id8="$(card_field "$card" .id8)"
    printf '%s · %s · %s\n' "$id8" "$(card_field "$card" .title)" "$(card_field "$card" .board_column)"
    files="$(mw_api GET "/matcha-work/projects/$project/tasks/$task/files")"
    journals="$(printf '%s' "$files" | jq -c '[.[] | select((.filename // "") | test("^autopr-run-.*\\.md$"))] | sort_by(.created_at) | reverse')"
    printf '\nRun journals: %s\n' "$(printf '%s' "$journals" | jq 'length')"
    printf '%s' "$journals" | jq -r '.[:10][] | "  " + (.created_at // "?")[0:19] + "  " + .filename'
    newest_url="$(printf '%s' "$journals" | jq -r '.[0] | (.url // .storage_url // empty)')"
    if [ -n "$newest_url" ]; then
        printf '\n--- newest journal ---\n'
        curl -sS "${MW_CURL_TIMEOUTS[@]}" "$newest_url" 2>/dev/null | head -n 120 \
            || printf '(could not download %s)\n' "$newest_url"
    fi
    ledger="${AUTOPR_CACHE_DIR:-$USER_HOME/.cache/matcha-autopr}/attempts/$id8"
    printf '\nFailure ledger: '
    if [ -s "$ledger" ]; then
        IFS=$'\t' read -r count reason ts < "$ledger" || true
        printf '%s consecutive × %s (last %s)\n' "${count:-?}" "${reason:-?}" "${ts:-?}"
    else
        printf 'none (last run succeeded, or the card was never run)\n'
    fi
    checkpoints="$RUNNER_WORKTREE/.git/matcha-kanban-autopr-checkpoints/$task"
    printf 'Checkpoints on the runner: '
    if [ -d "$checkpoints" ]; then
        # A card whose checkpoint dir holds no run directories is normal, but
        # the unmatched */ glob makes ls exit non-zero and set -e would treat
        # that as a failed lookup. prune_checkpoints guards the same glob.
        printed="$(cd "$checkpoints" && ls -1td -- */ 2>/dev/null | sed 's|/$||' | head -5 | tr '\n' ' ' || true)"
        printf '%s' "${printed:-none}"
        [ ! -f "$checkpoints/active" ] || printf ' (resumes from %s)' "$(tr -d '\r\n' < "$checkpoints/active")"
        printf '\n'
    else
        printf 'none\n'
    fi
}

active_kanban_run() {
    "$RUN_SNAPSHOT" | jq -r '[.[] | select(.lane == "kanban"
        and (.status | IN("queued", "in_progress", "requested", "waiting", "pending")))][0].databaseId // empty'
}

runner_task_id8() {
    local branch
    branch="$("$GIT_BIN" -C "$RUNNER_WORKTREE" branch --show-current 2>/dev/null || true)"
    [[ "$branch" == bot/task-* ]] || return 1
    printf '%s' "${branch#bot/task-}" | cut -c1-8
}

cancel_run() {
    local run_id query card
    run_id="$(active_kanban_run)"
    [ -n "$run_id" ] || { echo "no active Kanban run to cancel" >&2; exit 3; }
    # The card is whatever the runner checkout is on; an explicit target wins.
    # Resolve it BEFORE the cancel: an ambiguous target exits 2 here, with
    # the run untouched, instead of after a cancel that would leave the claim
    # live and the card stranded — the state this verb exists to prevent.
    query="$TARGET"
    [ -n "$query" ] || query="$(runner_task_id8 || true)"
    card=""
    [ -z "$query" ] || card="$(resolve_card "$query")"
    "$GH_BIN" run cancel "$run_id" --repo "$REPO" >/dev/null
    printf 'cancelled run #%s\n' "$run_id"
    "$GH_BIN" run watch "$run_id" --repo "$REPO" >/dev/null 2>&1 || true
    # The workflow's always() Cleanup step still runs on a cancelled job and
    # owns the local hand-back bookkeeping (autopr_control.py finish under the
    # workflow's identity). Nothing here should pretend to be that step. What
    # Cleanup never does is settle the board: the claim stays live and
    # collect.sh re-admits the card for thirty minutes, so move it now.
    if [ -z "$card" ]; then
        echo "runner checkout is not on a bot/task-* branch; pass the card to unstick it" >&2
        return 0
    fi
    unstick_card "$card"
}

case "$VERB" in
    resolve)
        card="$(resolve_card "$TARGET")"
        if [ "$JSON" = true ]; then printf '%s\n' "$card"; else card_line "$card"; fi
        ;;
    hold) hold_card "$(resolve_card "$TARGET")" ;;
    release) release_card "$(resolve_card "$TARGET")" ;;
    run-now) run_now_card "$(resolve_card "$TARGET")" ;;
    unstick) unstick_card "$(resolve_card "$TARGET")" ;;
    cancel-run) cancel_run ;;
    log) log_card "$(resolve_card "$TARGET")" ;;
    *) echo "unknown verb: $VERB" >&2; usage ;;
esac
