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
    sed -n '2,19p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2
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
    column=todo
    [ "$(card_field "$card" '.pr_number // empty')" = "" ] || column=changes_requested
    # Move first: unqueue refuses a card that is not in Todo or Changes
    # Requested, so a hold on a stranded In Progress card must follow the move.
    mw_move_card "$project" "$task" "$column"
    printf 'moved %s · %s → %s\n' "$(card_field "$card" .id8)" "$(card_field "$card" .title)" "$column"
    [ "$HOLD" != true ] || hold_card "$(printf '%s' "$card" | jq -c --arg c "$column" '.board_column = $c')"
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
    query="$TARGET"
    [ -n "$query" ] || query="$(runner_task_id8 || true)"
    "$GH_BIN" run cancel "$run_id" --repo "$REPO" >/dev/null
    printf 'cancelled run #%s\n' "$run_id"
    "$GH_BIN" run watch "$run_id" --repo "$REPO" >/dev/null 2>&1 || true
    # The workflow's always() Cleanup step still runs on a cancelled job and
    # owns the local hand-back bookkeeping (autopr_control.py finish under the
    # workflow's identity). Nothing here should pretend to be that step. What
    # Cleanup never does is settle the board: the claim stays live and
    # collect.sh re-admits the card for thirty minutes, so move it now.
    if [ -z "$query" ]; then
        echo "runner checkout is not on a bot/task-* branch; pass the card to unstick it" >&2
        return 0
    fi
    card="$(resolve_card "$query")"
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
    *) echo "unknown verb: $VERB" >&2; usage ;;
esac
