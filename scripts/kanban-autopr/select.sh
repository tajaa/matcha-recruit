#!/usr/bin/env bash
# Pick the first card from cards.json that isn't already handled by an open
# PR, isn't durably marked unscopable, isn't waiting for a human answer, and
# isn't mid-cooldown from a just-crashed attempt. GitHub is the durable dedup
# ledger for PRs; the card's own
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
[ "${AUTOPR_SELECT_READ_ONLY:-false}" = true ] || mkdir -p "$ATTEMPTS_DIR"

NOTHING_TO_DO=3
# The AutoPR review queue is deliberately bounded, but ten open implementation
# drafts lets the four supported projects make progress without a three-PR
# bottleneck. The workflow sets this explicitly; this default also keeps local
# dashboard/selector probes consistent when they run outside Actions.
MAX_OPEN_IMPLEMENTATION_PRS="${MAX_OPEN_IMPLEMENTATION_PRS:-10}"
ATTEMPT_COOLDOWN_MINUTES="${AUTOPR_ATTEMPT_COOLDOWN_MINUTES:-15}"

count="$(jq 'length' "$CARDS_FILE")"
[ "$count" -gt 0 ] || exit "$NOTHING_TO_DO"

# Backstop: never let a bad batch of cards produce an unbounded number of
# NEW open bot PRs. Checked per-decision below, not here — rework pushes a
# commit to a PR that's already open (it doesn't add to this count), so the
# cap must never block rework just because 3 unrelated PRs are already open.
# Question drafts are intentionally excluded from this cap: unanswered work
# should not prevent a well-specified card from being investigated. A fresh
# implementation is still bounded to keep human review manageable.
open_implementation_prs="$(gh pr list --repo "$REPO" --state open --label autopr --limit 100 --json labels --jq '[.[] | select(([.labels[].name] | index("autopr-awaiting-input")) | not)] | length')"

feedback_snapshot() {
    local pr_number="$1"
    # `gh pr view` returns GraphQL ids for both comments and reviews. Store the
    # latest human id of each kind rather than a timestamp so an edited PR body
    # can never masquerade as human feedback.
    gh pr view "$pr_number" --repo "$REPO" --json comments,reviews 2>/dev/null | jq -c '
      def human:
        ((.author.login // "") | test("\\[bot\\]$"; "i") | not)
        and ((.author.login // "") != "matcha-kanban-autopr");
      {
        comment_id: ([.comments[]? | select(human and ((.body // "") | gsub("[[:space:]]"; "") | length > 0)) | .id] | last // ""),
        review_id: ([.reviews[]? | select(human and ((.body // "") | gsub("[[:space:]]"; "") | length > 0)) | .id] | last // "")
      }
    '
}

awaiting_input_has_new_feedback() {
    local body="$1" snapshot="$2" old_comment old_review new_comment new_review
    old_comment="$(printf '%s' "$body" | sed -nE 's/.*<!-- matcha-feedback-comment-id: ([^ ]+) -->.*/\1/p' | tail -1)"
    old_review="$(printf '%s' "$body" | sed -nE 's/.*<!-- matcha-feedback-review-id: ([^ ]+) -->.*/\1/p' | tail -1)"
    new_comment="$(printf '%s' "$snapshot" | jq -r '.comment_id // ""')"
    new_review="$(printf '%s' "$snapshot" | jq -r '.review_id // ""')"
    { [ -n "$new_comment" ] && [ "$new_comment" != "$old_comment" ]; } \
        || { [ -n "$new_review" ] && [ "$new_review" != "$old_review" ]; }
}

iso_to_epoch() {
    local iso="$1" prefix
    [ -n "$iso" ] || { printf 0; return; }
    prefix="$(printf '%s' "$iso" | cut -c1-19)"
    date -u -j -f "%Y-%m-%dT%H:%M:%S" "$prefix" +%s 2>/dev/null \
        || date -u -d "$iso" +%s 2>/dev/null \
        || printf 0
}

# A "run now" request is consumed by the pass that considers it, not only by
# the card that wins the pass. investigate.sh claims the card it picks up;
# this claims every run-requested card this pass declines or defers. Without
# it the one-minute watcher keeps forcing a Kanban dispatch for a card the
# selector can never choose — an ALREADY-SCOPED card whose linked PR is open,
# or a card blocked by the open-PR cap — and the forced lane then runs more
# often than the twenty-minute schedule it is supposed to bypass. The
# invariant this restores: one button press costs at most one forced run.
consume_run_request() {
    local card="$1" project_id task_id
    [ "${AUTOPR_SELECT_READ_ONLY:-false}" = true ] && return 0
    project_id="$(printf '%s' "$card" | jq -r '.project_id // empty')"
    task_id="$(printf '%s' "$card" | jq -r '.task_id // empty')"
    [ -n "$project_id" ] && [ -n "$task_id" ] || return 0
    # mw_api dies on a non-2xx response; a failed claim must never abort the
    # selection pass, so keep that exit inside a subshell.
    ( mw_api POST "/matcha-work/projects/$project_id/tasks/$task_id/autopr/run-claim" '{}' ) \
        >/dev/null 2>&1 \
        || printf 'kanban-autopr: warning: could not consume the run request for %s\n' \
            "$task_id" >&2
}

# already_handled ID8 BOARD_COLUMN LAST_MOVED_AT PROGRESS_NOTE PR_NUMBER
#                 RECONSIDERATION_PENDING RECONSIDERATION_AT RUN_REQUESTED_AT
# Echoes "skip", "investigate", or "rework" (rework = push to the existing
# open PR rather than opening a new one).
already_handled() {
    local id8="$1" column="$2" last_moved="$3" progress_note="$4" pr_number="${5:-}"
    local reconsideration_pending="${6:-false}" reconsideration_at="${7:-}"
    local run_requested_at="${8:-}" branch="bot/task-$id8"
    # An explicit "run now" from the card is the same class of authorization as
    # decision-bound context: it overrides the cooldown, the durable no-spec
    # ledger, and (in Todo) the historical PR ledger.
    local human_signal_epoch=0 reconsideration_epoch run_requested_epoch
    reconsideration_epoch="$(iso_to_epoch "$reconsideration_at")"
    run_requested_epoch="$(iso_to_epoch "$run_requested_at")"
    [ "$reconsideration_epoch" -le "$human_signal_epoch" ] || human_signal_epoch="$reconsideration_epoch"
    [ "$run_requested_epoch" -le "$human_signal_epoch" ] || human_signal_epoch="$run_requested_epoch"
    local run_requested=false
    [ -z "$run_requested_at" ] || run_requested=true

    local attempt_marker="$ATTEMPTS_DIR/$id8"
    if [ -f "$attempt_marker" ]; then
        local age_s attempt_epoch
        attempt_epoch="$(date -r "$attempt_marker" +%s 2>/dev/null || echo 0)"
        age_s=$(( $(date +%s) - attempt_epoch ))
        if [ "$age_s" -lt $((ATTEMPT_COOLDOWN_MINUTES * 60)) ] \
            && [ "$human_signal_epoch" -le "$attempt_epoch" ]; then
            echo skip
            return
        fi
    fi

    # A runtime-limited pass is intentionally not an automatic retry loop.
    # Its partial work is checkpointed, and the owner must either add bounded
    # context (including --extend-runtime for a 40-minute attempt) or press Run
    # AutoPR for another ordinary 20-minute attempt.
    if [[ "$progress_note" == "🤖 AUTO SETUP · PAUSED: RUNTIME APPROVAL REQUIRED"* ]] \
        && [ "$reconsideration_pending" != true ] \
        && [ "$run_requested" != true ]; then
        echo skip
        return
    fi

    # No-spec ledger lives on the card itself, not GitHub — this stops a
    # vague card being re-run every cron tick forever, and clears the moment
    # a human edits progress_note or moves the card (last_moved_at advances).
    if [[ "$progress_note" == *"[autopr:no-spec "* ]] \
        && [ "$reconsideration_pending" != true ] \
        && [ "$run_requested" != true ]; then
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

    # A card may be owned by a PR from the other automation lane, so its head
    # branch will not be bot/task-$id8. The explicit link written by
    # record-coverage.sh is the durable association.
    if [[ "$progress_note" == "🤖 AUTO SETUP · ALREADY SCOPED"* ]] && [[ "$pr_number" =~ ^[0-9]+$ ]]; then
        local linked_pr linked_state
        if ! linked_pr="$(gh pr view "$pr_number" --repo "$REPO" --json state)"; then
            echo skip
            return
        fi
        linked_state="$(printf '%s' "$linked_pr" | jq -r '.state // empty')"
        case "$linked_state" in
            OPEN|MERGED)
                echo skip
                return ;;
            CLOSED)
                echo investigate
                return ;;
            *)
                echo skip
                return ;;
        esac
    fi

    # A decision-bound human reply is fresh work authorization. In Todo that
    # must outrank the stable branch's historical PR ledger: the previous PR
    # may be closed or merged precisely because the operator reported that the
    # issue remains. Investigation starts again from current main and publish
    # will update an open PR or create a new draft for a closed/merged one.
    if [ "$column" = "todo" ] \
        && { [ "$reconsideration_pending" = true ] || [ "$run_requested" = true ]; }; then
        echo investigate
        return
    fi

    local prs n
    if ! prs="$(gh pr list --repo "$REPO" --head "$branch" --state all --limit 10 \
        --json state,createdAt,number,labels,body --jq 'sort_by(.createdAt) | reverse')"; then
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
        local state labels body pr_number snapshot
        state="$(printf '%s' "$prs" | jq -r '.[0].state // empty')"
        if [ "$state" = "OPEN" ]; then
            labels="$(printf '%s' "$prs" | jq -r '.[0].labels[]?.name')"
            if printf '%s\n' "$labels" | grep -qx 'autopr-awaiting-input'; then
                if [ "$reconsideration_pending" = true ] || [ "$run_requested" = true ]; then
                    # Context supplied on the card or by replying to Espresso
                    # is equivalent to new PR feedback. It is already bound to
                    # the exact live decision, so rework the existing draft
                    # immediately instead of waiting for a duplicate GitHub
                    # comment.
                    echo rework
                    return
                fi
                body="$(printf '%s' "$prs" | jq -r '.[0].body // ""')"
                pr_number="$(printf '%s' "$prs" | jq -r '.[0].number // empty')"
                if ! snapshot="$(feedback_snapshot "$pr_number")"; then
                    # If GitHub feedback cannot be read, do not treat the
                    # waiting card as eligible; a blind rework would spin.
                    echo skip
                elif awaiting_input_has_new_feedback "$body" "$snapshot"; then
                    echo rework
                else
                    echo skip
                fi
            else
                echo rework
            fi
        elif [ "$state" = "MERGED" ] \
            && { [[ "$progress_note" == "from auto setup"* ]] \
                || [[ "$progress_note" == "🤖 AUTO SETUP"* ]]; }; then
            # Defense in depth for a missed merge webhook. The workflow's
            # reconciliation step moves this card to Review; until that write
            # succeeds, never mistake the merged bot branch for fresh work.
            echo skip
        else
            echo investigate
        fi
        return
    fi

    # todo without fresh decision-bound context: any PR at all on this branch
    # means the bot already worked this card. The branch name is stable, so a
    # second automatic run would collide or duplicate work.
    [ "$n" -gt 0 ] && { echo skip; return; }
    echo investigate
}

# Rank from the cross-queue plan when present. The planner sees every Todo /
# Changes Requested card plus every open bot PR and keeps related work
# contiguous. The fallback preserves safe standalone use. A pending explicit
# reconsideration is first even without a plan: new human evidence is a direct
# rebuttal of the prior no-safe-action decision and must not sit behind routine
# rework.
ranked="$(jq -c '
    sort_by(
        (.autopr_plan.work_position //
          (if ((.autopr_run_requested_at // null) != null) then 0
           elif (.autopr_reconsideration_pending // false) then 1
           elif .board_column == "changes_requested" then 2
           else 3 end)),
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
    pr_number="$(printf '%s' "$card" | jq -r '.pr_number // empty')"
    reconsideration_pending="$(printf '%s' "$card" | jq -r '.autopr_reconsideration_pending // false')"
    reconsideration_at="$(printf '%s' "$card" | jq -r '.autopr_reconsideration_at // empty')"
    run_requested_at="$(printf '%s' "$card" | jq -r '.autopr_run_requested_at // empty')"

    decision="$(already_handled "$id8" "$column" "$last_moved" "$progress_note" "$pr_number" \
        "$reconsideration_pending" "$reconsideration_at" "$run_requested_at")"
    if [ "$decision" = investigate ] && [ "$open_implementation_prs" -ge "$MAX_OPEN_IMPLEMENTATION_PRS" ]; then
        # A NEW PR would push past the cap — this specific card can't go,
        # but a later, lower-ranked card might be `rework` (no new PR) and
        # still eligible, so skip this one and keep looking rather than
        # bailing the whole run.
        [ -z "$run_requested_at" ] || consume_run_request "$card"
        continue
    fi
    # A terminal skip is an answer to the request, not a reason to re-ask.
    # The card keeps whatever made it unselectable (an open linked PR, a
    # cooldown, unreadable GitHub feedback); the human sees the button return
    # and can press it again once that changes.
    if [ "$decision" = skip ] && [ -n "$run_requested_at" ]; then
        consume_run_request "$card"
    fi
    if [ "$decision" = investigate ] || [ "$decision" = rework ]; then
        # The tmux dashboard asks the same selector what would run next. Its
        # read-only probe must never create a cooldown marker or consume work.
        [ "${AUTOPR_SELECT_READ_ONLY:-false}" = true ] || touch "$ATTEMPTS_DIR/$id8"
        printf '%s' "$card" | jq -c --arg mode "$decision" '. + {mode: $mode}'
        exit 0
    fi
done

exit "$NOTHING_TO_DO"
