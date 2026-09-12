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
RUN_URL=""
if [ -n "${GITHUB_SERVER_URL:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ] && [ "$RUN_ID" != local ]; then
    RUN_URL="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$RUN_ID"
fi
NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
JOURNAL_NAME="autopr-run-$RUN_ID-$STAMP.md"
JOURNAL="$STAGE_DIR/$JOURNAL_NAME"

warn() { printf 'run-journal: warning: %s\n' "$1" >&2; }

# One line, operator words, per machine reason. Unknown reasons pass through.
reason_label() {
    case "$1" in
        "") printf 'completed' ;;
        investigate) printf 'the model pass failed or timed out before producing a valid report' ;;
        verify) printf 'the branch failed verification against the baseline' ;;
        publish|publish_artifact) printf 'publishing the result failed' ;;
        setup) printf 'the run died before the investigation started (claim, checkout, policy, or coverage step)' ;;
        cancelled) printf 'an operator cancelled the run' ;;
        runtime_approval) printf 'the investigation hit its time budget and is waiting for approval to continue' ;;
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
        verify) printf 'VERIFY FAILED' ;;
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
        listed="$(git diff --name-only "$BASE_SHA" -- . 2>/dev/null | sed 's/^/- `/; s/$/`/' || true)"
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
        met="$(jq -r 'if has("acceptance_criteria_met") then (.acceptance_criteria_met | tostring) else empty end' "$DECISION_FILE")"
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

resume_section() {
    local metadata="$CHECKPOINT_DIR/metadata.json"
    if [ -n "$CHECKPOINT_DIR" ] && [ -s "$metadata" ] \
        && [ "$(jq -r '.patch_saved // false' "$metadata")" = true ]; then
        printf 'A checkpoint with %s changed file(s) (%s-byte patch, saved %s) is stored on the runner at `%s`. The next run of this card resumes from it instead of starting over; it expires after the checkpoint retention window.\n' \
            "$(jq -r '.changed_file_count // 0' "$metadata")" \
            "$(jq -r '.patch_bytes // 0' "$metadata")" \
            "$(jq -r '.created_at // "?"' "$metadata")" "$CHECKPOINT_DIR"
    elif [ -n "$CHECKPOINT_DIR" ] && [ -s "$metadata" ]; then
        printf 'A checkpoint was saved at `%s` but holds no model patch (%s). The next run starts over.\n' \
            "$CHECKPOINT_DIR" "$(jq -r '[(if .report_saved then "report" else empty end), (if .decision_saved then "decision" else empty end), (if .transcript_saved then "transcript" else empty end)] | join(", ") // "nothing"' "$metadata")"
    else
        printf 'No resumable work was saved by this run.\n'
    fi
}

next_section() {
    case "$OUTCOME" in
        success) printf 'Nothing; review the PR or the attached report.\n' ;;
        paused) printf 'Approve more time from the ticket, or add context and press Run.\n' ;;
        *) printf 'Press Run on the ticket (or `msandbox autopr run-now %s`) to retry from the checkpoint; `msandbox autopr hold %s` parks it; `msandbox autopr log %s` shows this journal from a terminal.\n' "$ID8" "$ID8" "$ID8" ;;
    esac
}

{
    printf '# AutoPR run #%s · %s\n\n' "$RUN_ID" "$(printf '%s' "$OUTCOME" | tr '[:lower:]' '[:upper:]')"
    printf -- '- Card: %s (`%s`) · %s · mode %s\n' "$TITLE" "$ID8" "$PROJECT_TITLE" "$MODE"
    printf -- '- Recorded: %s\n' "$NOW_UTC"
    [ -z "$RUN_URL" ] || printf -- '- Run log: %s\n' "$RUN_URL"
    printf -- '- Result: %s — %s\n\n' "$OUTCOME" "$(reason_label "$REASON")"
    printf '## Done so far\n\n'; done_section; printf '\n'
    printf '## What is left\n\n'; left_section; printf '\n'
    printf '## Why it stopped\n\n%s.\n\n' "$(reason_label "$REASON")"
    printf '## Resume\n\n'; resume_section; printf '\n'
    printf '## Next step\n\n'; next_section
} > "$JOURNAL"

# lib.sh's helpers `die` on a non-2xx status; run them in subshells so a
# board failure is a warning here, never an exit before the header below or
# in the Cleanup step that called us.
if ( mw_api_upload "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files" "$JOURNAL" >/dev/null ); then
    printf 'journal attached: %s\n' "$JOURNAL_NAME"
else
    warn "could not attach $JOURNAL_NAME to task $TASK_ID"
fi

if label="$(stopped_header_label "$REASON")" && [ "$OUTCOME" != success ] && [ "$OUTCOME" != paused ]; then
    existing="$(jq -r '.progress_note // ""' "$CARD_FILE")"
    marker="🤖 AUTO SETUP · STOPPED: $label · run #$RUN_ID · note: see $JOURNAL_NAME"
    note="$(progress_note_with_origin "$marker" "$existing")"
    ( mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
        "$(jq -n --arg note "$note" '{progress_note: $note}')" >/dev/null ) \
        || warn "could not record the stop reason on task $TASK_ID"
fi
