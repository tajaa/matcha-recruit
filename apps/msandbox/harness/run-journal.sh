#!/usr/bin/env bash
# Attach a per-run journal to the card so the ticket itself says what the run
# did, what is left, and why it stopped. The checkpoint keeps the work; this
# keeps the story next to the card, where the operator looks first. Runs from
# the workflow's always() Cleanup step on every outcome and is never fatal:
# a lost journal must not skip the checkout hand-back that follows it.
#
# Usage: run-journal.sh card.json --outcome success|failure|cancelled|paused
#          [--reason R] [--report FILE] [--decision FILE]
#          [--checkpoint DIR] [--pr N] [--base-sha SHA]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "$SCRIPT_DIR/lib.sh"

CARD_FILE="${1:?usage: run-journal.sh card.json --outcome OUTCOME [options]}"
shift
OUTCOME="" REASON="" REPORT_FILE="" DECISION_FILE="" CHECKPOINT_DIR="" PR_NUMBER="" BASE_SHA=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --outcome) OUTCOME="${2:?}"; shift 2 ;;
        --reason) REASON="${2:-}"; shift 2 ;;
        --report) REPORT_FILE="${2:-}"; shift 2 ;;
        --decision) DECISION_FILE="${2:-}"; shift 2 ;;
        --checkpoint) CHECKPOINT_DIR="${2:-}"; shift 2 ;;
        --pr) PR_NUMBER="${2:-}"; shift 2 ;;
        --base-sha) BASE_SHA="${2:-}"; shift 2 ;;
        *) echo "run-journal: unknown option $1" >&2; exit 2 ;;
    esac
done
case "$OUTCOME" in
    success|failure|cancelled|paused) ;;
    *) echo "run-journal: --outcome must be success|failure|cancelled|paused" >&2; exit 2 ;;
esac

PROJECT_ID="$(jq -r '.project_id' "$CARD_FILE")"
TASK_ID="$(jq -r '.task_id' "$CARD_FILE")"
ID8="$(jq -r '.id8 // (.task_id | .[0:8])' "$CARD_FILE")"
TITLE="$(jq -r '.title // "Untitled"' "$CARD_FILE")"
PROJECT_TITLE="$(jq -r '.project_title // "?"' "$CARD_FILE")"
MODE="$(jq -r '.mode // "todo"' "$CARD_FILE")"
RUN_ID="${GITHUB_RUN_ID:-local}"
# Where the hand-back move's server timestamp is left for the Cleanup step.
HANDBACK_AT_FILE="${AUTOPR_HANDBACK_AT_FILE:-${RUNNER_TEMP:+$RUNNER_TEMP/autopr-handback-at}}"
[ -z "$HANDBACK_AT_FILE" ] || rm -f "$HANDBACK_AT_FILE"
RUN_URL=""
if [ -n "${GITHUB_SERVER_URL:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ] && [ "$RUN_ID" != local ]; then
    RUN_URL="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$RUN_ID"
fi
# Everything an operator reads is Pacific. STAMP below stays UTC because it
# names the file, and those names are sorted and prefix-matched elsewhere.
NOW_LOCAL="$(TZ=America/Los_Angeles date +'%Y-%m-%d %H:%M %Z')"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

# UTC stamp → Pacific display: autopr_to_pacific in lib.sh.
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
JOURNAL_NAME="autopr-run-$RUN_ID-$STAMP.md"
JOURNAL="$STAGE_DIR/$JOURNAL_NAME"

warn() { printf 'run-journal: warning: %s\n' "$1" >&2; }

# The Cleanup step can only hand us the checkpoint its save-on-failure step
# wrote, and that step runs only when Investigate itself failed. A run whose
# model pass SUCCEEDED and then died in verify or publish still has one: the
# in-flight snapshot timer saves under the same `<run id>-<epoch>-inflight`
# key. Reporting "nothing was saved" for that run is how a valid patch gets
# abandoned — it happened to run 34670939778, whose 19-file patch survived a
# `docs/PRODUCTS.md` publish refusal with nothing on the card to say so.
if [ -z "$CHECKPOINT_DIR" ] && [ "$RUN_ID" != local ]; then
    checkpoint_root="${AUTOPR_CHECKPOINT_ROOT:-}"
    if [ -z "$checkpoint_root" ]; then
        journal_git_dir="$(git -C "${AUTOPR_WORKSPACE_ROOT:-.}" rev-parse --absolute-git-dir 2>/dev/null || true)"
        [ -z "$journal_git_dir" ] || checkpoint_root="$journal_git_dir/matcha-kanban-autopr-checkpoints"
    fi
    if [ -n "$checkpoint_root" ] && [ -d "$checkpoint_root/$TASK_ID" ]; then
        # Newest first, and only this run's own snapshots: an earlier round's
        # leftovers are not what this journal is reporting on.
        found="$(cd "$checkpoint_root/$TASK_ID" \
            && ls -1td -- "$RUN_ID"-*/ 2>/dev/null | sed 's|/$||' | head -1 || true)"
        [ -z "$found" ] || CHECKPOINT_DIR="$checkpoint_root/$TASK_ID/$found"
    fi
fi

# Cleanup runs on every outcome, which makes it the only place a SUCCESSFUL
# run's last checklist ticks can land: the snapshot timer fires every few
# minutes, so whatever the model finished in its final stretch is still only in
# its progress log. Never fatal — a lost tick must not skip the journal.
if [ "${AUTOPR_JOURNAL_SKIP_FINAL_TICK:-0}" != 1 ]; then
    ticked_now="$( ( "$SCRIPT_DIR/checkpoint.sh" tick "$CARD_FILE" ) 2>/dev/null || echo 0 )"
    case "$ticked_now" in
        ''|0) ;;
        *) printf 'run-journal: checked off %s subtask(s) from the final progress log\n' \
            "$ticked_now" >&2 ;;
    esac
fi

# A run killed at its time budget reaches Cleanup as a plain step failure:
# investigate.sh writes `paused=true` only for an acknowledged operator
# takeover (codex rc 75, which exits 0). The authority on "this was a timeout"
# is the checkpoint, which already parked the card with
# `PAUSED: APPROVE 10 MORE MINUTES` and moved it to Changes Requested. Believe
# it over the step outcome: otherwise this script overwrites that header with
# STOPPED, and both select.sh and Espresso's "approve 10 more minutes"
# affordance prefix-match the header that just disappeared. The workflow reads
# the same verdict before it records a ledger strike, so the two agree.
if [ -n "$CHECKPOINT_DIR" ] && [ -s "$CHECKPOINT_DIR/metadata.json" ] \
    && [ "$(jq -r '.runtime_limited // false' "$CHECKPOINT_DIR/metadata.json" 2>/dev/null)" = true ]; then
    OUTCOME=paused
    REASON=runtime_limited
fi

# One line, operator words, per machine reason. Unknown reasons pass through.
reason_label() {
    case "$1" in
        "") printf 'completed' ;;
        investigate) printf 'the model pass failed or timed out before producing a valid report' ;;
        auth) printf 'the host Codex login was dead, so the model never ran; nothing about this card failed (fix: `codex login` on the runner Mac, then Run)' ;;
        usage_limit) printf 'the shared ChatGPT quota was exhausted, so the model never finished; nothing about this card failed and the lanes back off until it returns' ;;
        infrastructure) printf 'the sandbox could not be started (Docker, disk, or network), so the model never ran; nothing about this card failed' ;;
        verify_timeout) printf 'the verification step ran out of its time budget and was killed; verify.sh reports a failing branch in its table, never as a status, so nothing about this card failed' ;;
        verify_broken) printf 'verification could not start at all — the harness is broken on this runner (check that error-autofix/verify.sh and toolchain.sh are in the control-plane archive and executable). Nothing about this card failed, and no card can be verified until it is fixed' ;;
        verify) printf 'the verification step did not complete (it was killed by its timeout, or refused to run here); verify.sh reports a failing branch in its table, never as a status, so nothing about this card failed' ;;
        publish|publish_artifact) printf 'publishing the result failed' ;;
        setup) printf 'the run died before the investigation started (claim, checkout, policy, or coverage step)' ;;
        cancelled) printf 'an operator cancelled the run' ;;
        runtime_limited) printf 'the investigation hit its time budget; the card is parked in Changes Requested until someone approves 10 more minutes' ;;
        operator_takeover) printf 'an operator took the checkout over; the manual session has no time limit and AutoPR is not working this card' ;;
        disallowed_paths) printf 'the change touched paths outside the approved product source paths and was refused' ;;
        cosmetic_only) printf 'the diff only rewrote string literals and was refused' ;;
        *) printf '%s' "$1" ;;
    esac
}

# The card-face header. Only for a run that died in a way nothing else has
# already written to the card: publish.sh parks refusals, checkpoint.sh writes
# PAUSED, and a success is announced by the PR itself.
stopped_header_label() {
    case "$1" in
        investigate) printf 'MODEL PASS FAILED' ;;
        auth) printf 'CODEX LOGIN DEAD' ;;
        usage_limit) printf 'CODEX QUOTA' ;;
        infrastructure) printf 'SANDBOX FAULT' ;;
        verify_timeout) printf 'VERIFY TIMED OUT' ;;
        verify_broken) printf 'VERIFY IS BROKEN ON THE RUNNER' ;;
        verify) printf 'VERIFY DID NOT RUN' ;;
        publish|publish_artifact) printf 'PUBLISH FAILED' ;;
        setup) printf 'DIED IN SETUP' ;;
        cancelled) printf 'CANCELLED' ;;
        *) return 1 ;;
    esac
}

changed_files_section() {
    local metadata="$CHECKPOINT_DIR/metadata.json" listed=""
    if [ -n "$CHECKPOINT_DIR" ] && [ -s "$metadata" ]; then
        listed="$(jq -r '.changed_files[]? | "- `" + . + "`"' "$metadata" 2>/dev/null || true)"
        if [ -n "$listed" ]; then
            printf 'Files changed (%s, from the saved checkpoint):\n%s\n' \
                "$(jq -r '.changed_file_count // 0' "$metadata")" "$listed"
            return
        fi
    fi
    if [ -n "$BASE_SHA" ] && git rev-parse --verify -q "$BASE_SHA" >/dev/null 2>&1; then
        # run-codex-sandboxed.sh applies the model patch with plain `git apply`,
        # so everything the model CREATED is still untracked and invisible to
        # `git diff` alone. checkpoint.sh solves this by staging with
        # --intent-to-add; here the index belongs to the checkout hand-back
        # that runs next, so list the untracked paths instead of touching it.
        listed="$( { git diff --name-only "$BASE_SHA" -- . 2>/dev/null || true
                     git ls-files --others --exclude-standard -- . 2>/dev/null || true
                   } | sort -u | sed 's/^/- `/; s/$/`/' )"
        if [ -n "$listed" ]; then
            printf 'Files changed on the branch:\n%s\n' "$listed"
            return
        fi
    fi
    printf 'Files changed: none recorded.\n'
}

done_section() {
    local summary=""
    if [ -n "$REPORT_FILE" ] && [ -s "$REPORT_FILE" ]; then
        summary="$(autopr_report_summary "$REPORT_FILE" 2>/dev/null || true)"
    fi
    if [ -n "$summary" ]; then
        printf '%s\n\n' "$summary"
    else
        printf 'No report was produced by this run.\n\n'
    fi
    [ -z "$PR_NUMBER" ] || printf 'Draft PR #%s was published.\n\n' "$PR_NUMBER"
    changed_files_section
}

left_section() {
    local questions met summary
    if [ -n "$DECISION_FILE" ] && jq -e . "$DECISION_FILE" >/dev/null 2>&1; then
        # `false // empty` would drop a false verdict; test for the key instead.
        # `jq -e .` above accepts any truthy JSON, and a failed investigate
        # run hands us the raw model output — an array reaches `has(...)`,
        # which errors. Guard like the two calls below: this script exists to
        # explain the failure path, so it must survive malformed model JSON.
        met="$(jq -r 'if type == "object" and has("acceptance_criteria_met") then (.acceptance_criteria_met | tostring) else empty end' "$DECISION_FILE" 2>/dev/null || true)"
        [ -z "$met" ] || printf 'Acceptance criteria met: %s\n' "$met"
        summary="$(jq -r '.summary // empty' "$DECISION_FILE" | jq -Rsr '.[0:600]' 2>/dev/null || true)"
        [ -z "$summary" ] || printf 'Decision: %s\n' "$summary"
        questions="$(jq -r '.questions[]? | (if type == "object" then (.question // .text // tostring) else tostring end) | "- " + .' "$DECISION_FILE" 2>/dev/null || true)"
        if [ -n "$questions" ]; then
            printf 'Open questions for the owner:\n%s\n' "$questions"
        fi
        [ -n "$met$summary$questions" ] || printf 'The decision file carried nothing actionable.\n'
    else
        printf 'No decision was recorded; the next run starts from the saved checkpoint if there is one, otherwise from scratch.\n'
    fi
}

# The run's own account of itself, newest last. Without this the journal can
# only report the END state — "no report was produced" — which is exactly the
# case where the operator most needs to know what happened before that.
progress_section() {
    local metadata="$CHECKPOINT_DIR/metadata.json"
    local log="$CHECKPOINT_DIR/progress.jsonl" steps count phase keep ticked
    keep="${AUTOPR_JOURNAL_PROGRESS_STEPS:-20}"
    if [ -z "$CHECKPOINT_DIR" ] || [ ! -s "$log" ]; then
        # Only the kinds whose prompt carries the PROGRESS_PATH contract can be
        # said to have ignored it. Saying so on a kind that was never given the
        # contract is just wrong, and it was the normal case for research and
        # email before their prompts got it.
        case "$MODE" in
            todo|rework|investigate|feat|fix)
                printf 'The run logged no progress steps. It stopped before finishing its first step, or ignored the progress-log contract.\n' ;;
            *)
                printf 'No progress log was captured for this run.\n' ;;
        esac
        return
    fi
    count="$(jq -s 'length' "$log" 2>/dev/null || echo 0)"
    [[ "$count" =~ ^[0-9]+$ ]] || count=0
    phase="$(jq -r '.progress_phase // ""' "$metadata" 2>/dev/null || true)"
    [ -z "$phase" ] || printf 'Last phase: **%s**\n\n' "$phase"
    # Bounded: a long run can log dozens of steps and the tail is what says
    # where it got to. The whole log stays in the checkpoint either way.
    steps="$(jq -rs --argjson keep "$keep" '
        (if length > $keep then .[-$keep:] else . end)
        | map("- `" + (.phase // "?") + "` " + ((.note // "") | .[0:240])
              + (if (.next // "") == "" then "" else "  \n  → next: " + ((.next) | .[0:200]) end))
        | join("\n")' "$log" 2>/dev/null || true)"
    if [ -n "$steps" ]; then
        [ "$count" -le "$keep" ] \
            || printf '_Showing the last %s of %s logged steps._\n\n' "$keep" "$count"
        printf '%s\n' "$steps"
    fi
    # From the ledger, not metadata: most ticking happens on the 4-minute timer
    # and on a successful run there is no `save` pass to record a total.
    ticked="$(journal_ticked_count)"
    [ "$ticked" = 0 ] || printf '\nChecked off %s checklist item(s) on the ticket during this run.\n' "$ticked"
}

# Items this run checked off, counted from the run-keyed tick ledger beside the
# checkpoint directories.
journal_ticked_count() {
    local ledger count=0
    [ -n "$CHECKPOINT_DIR" ] || { printf '0'; return 0; }
    ledger="$(dirname "$CHECKPOINT_DIR")/ticked-subtasks"
    [ ! -f "$ledger" ] || count="$(grep -c "^$RUN_ID " "$ledger" 2>/dev/null || printf 0)"
    printf '%s' "${count:-0}"
}

# What the next run will be configured with, and why. A card on its third pause
# needs to show that something is actually changing between attempts.
runtime_section() {
    local metadata="$CHECKPOINT_DIR/metadata.json" reason attempt model effort
    [ -n "$CHECKPOINT_DIR" ] && [ -s "$metadata" ] || return 0
    reason="$(jq -r '.stall_reason // ""' "$metadata" 2>/dev/null || true)"
    [ -n "$reason" ] || return 0
    attempt="$(jq -r '.stall_attempt // 0' "$metadata" 2>/dev/null || echo 0)"
    model="$(jq -r '.suggested_model // ""' "$metadata" 2>/dev/null || true)"
    effort="$(jq -r '.suggested_effort // ""' "$metadata" 2>/dev/null || true)"
    printf '\n## Runtime for the next attempt\n\n'
    printf -- '- Stall classified as `%s` (pause #%s for this card).\n' "$reason" "$attempt"
    if [ -n "$model" ] && [ -n "$effort" ]; then
        printf -- '- The continuation runs on **%s** at **%s** effort.\n' "$model" "$effort"
        printf -- '- Pin a different one in the ticket'"'"'s AutoPR runtime setting to override this.\n'
    else
        printf -- '- No runtime change; the continuation reruns on the default for this card kind.\n'
    fi
}

resume_section() {
    local metadata="$CHECKPOINT_DIR/metadata.json" held
    if [ "$REASON" = operator_takeover ]; then
        printf 'Nothing was checkpointed: the working tree is held by the operator outside this workflow. `msandbox` shows the takeover session.\n'
        return
    fi
    if [ -n "$CHECKPOINT_DIR" ] && [ -s "$metadata" ] \
        && [ "$(jq -r '.patch_saved // false' "$metadata")" = true ]; then
        printf 'A checkpoint with %s changed file(s) (%s-byte patch, saved %s) is stored on the runner at `%s`. The next run of this card resumes from it instead of starting over; it expires after the checkpoint retention window.\n' \
            "$(jq -r '.changed_file_count // 0' "$metadata")" \
            "$(jq -r '.patch_bytes // 0' "$metadata")" \
            "$(autopr_to_pacific "$(jq -r '.created_at // ""' "$metadata")")" "$CHECKPOINT_DIR"
    elif [ -n "$CHECKPOINT_DIR" ] && [ -s "$metadata" ]; then
        # No patch is not the same as no resume: checkpoint.sh still points
        # `active` at a checkpoint holding a report or decision, and
        # investigate.sh re-attaches those to the next run as model inputs.
        # Saying "starts over" here sends an operator who wants a clean restart
        # to press Run and get a resumed run instead.
        held="$(jq -r '[(if .report_saved then "report" else empty end), (if .decision_saved then "decision" else empty end), (if .transcript_saved then "transcript" else empty end)] | join(", ")' "$metadata" 2>/dev/null || true)"
        if [ -n "$held" ]; then
            printf 'A checkpoint at `%s` holds no model patch, only the %s. The next run of this card starts the code over but is given those as inputs.\n' \
                "$CHECKPOINT_DIR" "$held"
        else
            printf 'A checkpoint directory exists at `%s` but saved nothing. The next run starts over.\n' "$CHECKPOINT_DIR"
        fi
    else
        printf 'No resumable work was saved by this run.\n'
    fi
}

next_section() {
    case "$OUTCOME" in
        success) printf 'Nothing; review the PR or the attached report.\n' ;;
        paused)
            if [ "$REASON" = operator_takeover ]; then
                printf 'Finish or hand back the manual session (`msandbox`); AutoPR resumes this card only after the takeover ends.\n'
            else
                printf 'Approve 10 more minutes from the ticket to continue from the saved checkpoint, or add context and press Run.\n'
            fi
            ;;
        cancelled) printf 'Nothing runs on its own: a cancel leaves the card where the operator put it, and `--hold` also parks it. `msandbox autopr release %s` lifts a hold, then Press Run (or `msandbox autopr run-now %s`) to retry from the checkpoint.\n' "$ID8" "$ID8" ;;
        # Deliberately not "the scheduler will retry": this text is composed
        # and uploaded BEFORE the hand-back PATCH below is attempted, and that
        # PATCH can fail. Say what the run tried to do and give the operator
        # the command that fixes it if it did not land.
        *) printf 'Press Run on the ticket (or `msandbox autopr run-now %s`) to retry from the checkpoint. A failed run also hands the card back to its lane (Changes Requested when it has a PR, otherwise Todo) so the scheduler can reach it again — if it is still sitting in In Progress, that write did not land and `msandbox autopr unstick %s` returns it. `msandbox autopr hold %s` parks it; `msandbox autopr log %s` shows this journal from a terminal.\n' "$ID8" "$ID8" "$ID8" "$ID8" ;;
    esac
}

{
    printf '# AutoPR run #%s · %s\n\n' "$RUN_ID" "$(printf '%s' "$OUTCOME" | tr '[:lower:]' '[:upper:]')"
    printf -- '- Card: %s (`%s`) · %s · mode %s\n' "$TITLE" "$ID8" "$PROJECT_TITLE" "$MODE"
    printf -- '- Recorded: %s\n' "$NOW_LOCAL"
    [ -z "$RUN_URL" ] || printf -- '- Run log: %s\n' "$RUN_URL"
    printf -- '- Result: %s — %s\n\n' "$OUTCOME" "$(reason_label "$REASON")"
    printf '## Done so far\n\n'; done_section; printf '\n'
    printf '## Progress log\n\n'; progress_section; printf '\n'
    printf '## What is left\n\n'; left_section; printf '\n'
    printf '## Why it stopped\n\n%s.\n\n' "$(reason_label "$REASON")"
    printf '## Resume\n\n'; resume_section; printf '\n'
    printf '## Next step\n\n'; next_section
    runtime_section
} > "$JOURNAL"

# lib.sh's helpers `die` on a non-2xx status; run them in subshells so a
# board failure is a warning here, never an exit before the header below or
# in the Cleanup step that called us.
if ( mw_api_upload "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files" "$JOURNAL" >/dev/null ); then
    printf 'journal attached: %s\n' "$JOURNAL_NAME"
else
    warn "could not attach $JOURNAL_NAME to task $TASK_ID"
fi

# One journal per run, forever, would bury the spec PDFs and screenshots people
# actually attached — a card run twenty times would carry twenty of them ahead
# of the real evidence. checkpoint.sh bounds its own footprint for the same
# reason; the newest few are the only ones anyone reads.
JOURNAL_KEEP="${AUTOPR_JOURNAL_KEEP:-5}"
prune_journals() {
    local files stale id
    files="$( ( mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files" ) 2>/dev/null || true )"
    [ -n "$files" ] || return 0
    stale="$(printf '%s' "$files" | jq -r --argjson keep "$JOURNAL_KEEP" '
        [ .[]? | select((.filename // "") | test("^autopr-run-.*\\.md$")) ]
        | sort_by(.created_at // "") | reverse | .[$keep:] | .[].id // empty' 2>/dev/null || true)"
    while IFS= read -r id; do
        [ -n "$id" ] || continue
        ( mw_api DELETE "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files/$id" >/dev/null ) 2>/dev/null \
            || warn "could not prune old journal $id"
    done <<< "$stale"
}
prune_journals

# The card face. `$CARD_FILE` is the SELECTION-time snapshot, so it cannot be
# trusted here: investigate.sh's park_rejected_after_correction and
# publish-research.sh both PATCH a `BLOCKED: AWAITING ANSWERS ·
# [autopr:no-spec …]` header and then exit non-zero, which reaches Cleanup as
# a plain failure. Writing STOPPED over that erases the marker select.sh uses
# to keep the card settled and the question form Espresso renders. Read the
# live note, and stand down whenever this run already parked the card.
snapshot_note="$(jq -r '.progress_note // ""' "$CARD_FILE")"
live_note="$snapshot_note"
# The live column decides whether this run has to hand the card back to a lane
# (below). It deliberately does NOT fall back to $CARD_FILE: that snapshot is
# taken by collect.sh BEFORE investigate.sh claims the card, so its column is
# the lane the card came from and never `in_progress`. Defaulting to it would
# turn a transient board read failure into exactly the stranding this write
# exists to prevent, while the journal reported the card returned. Track
# whether the read succeeded instead and decide below.
live_column=""
live_read_ok=false
live_pr="$(jq -r '.pr_number // empty' "$CARD_FILE")"
live_tasks="$( ( mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks" ) 2>/dev/null || true )"
# Extract THIS card once, and let that single step answer "did the board tell
# me anything about it". A non-empty body is not the same as a readable one: a
# 200 carrying a proxy error page, an error object, or a list this task is
# simply absent from all left the per-field filters returning "" — which then
# read as "not In Progress" and silently skipped the hand-back below, the exact
# stranding this write exists to prevent. jq fails on all three (it cannot
# index null), so a successful extraction is the signal.
if live_row="$(printf '%s' "$live_tasks" \
    | jq -ce --arg id "$TASK_ID" 'first(.[]? | select(.id == $id))' 2>/dev/null)"; then
    live_read_ok=true
    live_note="$(printf '%s' "$live_row" | jq -r '.progress_note // ""')"
    live_column="$(printf '%s' "$live_row" | jq -r '.board_column // ""')"
    live_pr_now="$(printf '%s' "$live_row" | jq -r '.pr_number // empty')"
    [ -z "$live_pr_now" ] || live_pr="$live_pr_now"
fi
[ -n "$live_pr" ] || live_pr="$PR_NUMBER"
already_parked=false
if [ "$live_note" != "$snapshot_note" ] \
    && printf '%s' "$live_note" \
        | grep -qE '\[autopr:(no-spec|rejected|parked) |· (PAUSED|BLOCKED|ON HOLD):'; then
    already_parked=true
fi

if label="$(stopped_header_label "$REASON")" && [ "$OUTCOME" != success ] \
    && [ "$OUTCOME" != paused ] && [ "$already_parked" != true ]; then
    # lib.sh's header alternation matches `· run #<id>`; RUN_ID is "local"
    # off CI, so that group accepts word characters, not just digits.
    marker="🤖 AUTO SETUP · STOPPED: $label · run #$RUN_ID · note: see $JOURNAL_NAME"
    note="$(progress_note_with_origin "$marker" "$live_note")"
    # Say on the card that the work survived. Every other park writes the same
    # line; without it the card's only resume signal is the timeout header, and
    # an owner looking at a stopped card cannot tell a resumable checkpoint from
    # a clean restart.
    resume_line="$(autopr_checkpoint_resume_line "$TASK_ID")"
    [ -z "$resume_line" ] || note="$note"$'\n'"$resume_line"
    # Hand the card back to a lane in the SAME write as the note. The claim
    # that moved it to In Progress is settled by any later progress-note or
    # column event (project_task_service._AUTOPR_ACTIVE_CLAIM_QUERY), so a
    # STOPPED note alone leaves a card the selector can never see again:
    # collect.sh admits In Progress only while the claim is live, and the
    # resume line's "Press Run" needs Todo or Changes Requested to mean
    # anything. checkpoint.sh's pause already moves in its note write; this is
    # the failure path's half of that. Same lane rule as card-control.sh
    # unstick: Changes Requested when a PR exists, else Todo (artifact kinds
    # own no PR). A card that already left In Progress is someone else's.
    patch='{progress_note: $note}'
    return_column=""
    # An unreadable board is treated as In Progress: this run's own claim is
    # what put the card there. If the run died before claiming, the card is
    # still in its lane and the server writes no column_change when the value
    # does not change (project_task_service update_task), so the redundant
    # write costs nothing and cannot disturb the park clock.
    if [ "$live_read_ok" != true ] || [ "$live_column" = in_progress ]; then
        return_column=todo
        [ -z "$live_pr" ] || return_column=changes_requested
        patch='{progress_note: $note, board_column: $column}'
    fi
    if handback_response="$( mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
        "$(jq -n --arg note "$note" --arg column "$return_column" "$patch")" )"; then
        # select.sh parks a repeat offender only while the failure ledger's
        # mtime is at or after the card's last move, and this hand-back IS a
        # move. Those two stamps come from different machines (Postgres on the
        # DB host, `date` on this runner), so hand the caller the server's own
        # timestamp to stamp the ledger with instead of racing the clocks.
        if [ -n "$return_column" ] && [ -n "$HANDBACK_AT_FILE" ]; then
            printf '%s' "$handback_response" \
                | jq -r '.updated_at // empty' 2>/dev/null > "$HANDBACK_AT_FILE" || true
        fi
    else
        warn "could not record the stop reason on task $TASK_ID"
    fi
elif [ "$already_parked" = true ]; then
    # The parker owns the header AND already wrote the same resume line, and
    # its question form sits below the note; rewriting it here would drop that.
    printf 'run-journal: card already parked by this run; leaving its header alone\n' >&2
fi
