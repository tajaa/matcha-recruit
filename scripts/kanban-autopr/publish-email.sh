#!/usr/bin/env bash
# Copy of publish-research.sh for the email artifact kind; keep the two in step.
#
# Publish an email-review run: attach the triage report to the card, post a
# summary note carrying it, and move the card to Review — or, when the card
# cannot be reviewed as asked (no snapshot attached, a decision only its owner
# can make), park it in Changes Requested with the numbered question form the
# operator answers from the ticket. `update_project_task` on the server then
# notifies every collaborator ("Ready for review") exactly as it does for a
# research report, so nothing here talks to email or chat directly.
#
# Never touches git, gh, labels, or Gmail: an email card owns no branch and no
# PR, and the emails it reviewed are the snapshots Espresso attached to it.
# Reply drafts are staged for a person to approve one send at a time; nothing
# here sends mail. Every board write goes through the bot's REST identity
# (lib.sh:mw_api).
#
# What differs from publish-research.sh, and nothing else should: the kind
# guard, the `email-report-` file names, the provenance line (emails reviewed
# rather than sources), no screenshots, and the wording of the notes. A fix to
# staging, orphan reuse, the summary note, or the card move belongs in both.
#
# Usage: ./publish-email.sh card.json report.md decision.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"
# shellcheck source=./decision.sh
source "$SCRIPT_DIR/decision.sh"

CARD_FILE="${1:?usage: publish-email.sh card.json report.md decision.json}"
REPORT_FILE="${2:?usage: publish-email.sh card.json report.md decision.json}"
DECISION_FILE="${3:?usage: publish-email.sh card.json report.md decision.json}"

TASK_ID="$(jq -r '.task_id' "$CARD_FILE")"
PROJECT_ID="$(jq -r '.project_id' "$CARD_FILE")"
ID8="$(jq -r '.id8' "$CARD_FILE")"
MODE="$(jq -r '.mode' "$CARD_FILE")"
PROD_BUILD_NUMBER="$(jq -r '.production.build_number // empty' "$CARD_FILE")"
PROD_BACKEND_SHA="$(jq -r '.production.containers.backend.git_sha // empty' "$CARD_FILE")"
PROD_FRONTEND_SHA="$(jq -r '.production.containers.frontend.git_sha // empty' "$CARD_FILE")"
EXISTING_PROGRESS_NOTE="$(jq -r '.progress_note // ""' "$CARD_FILE")"
RECONSIDERATION_EVENT_ID="$(jq -r '.autopr_reconsideration_event_id // empty' "$CARD_FILE")"

# Only a decision that went through decision.sh normalize-email may drive a
# board write; the raw model JSON never reaches this script, and neither does
# a research decision (a different schema with no per_email to count).
[ "$(jq -r '.kind // empty' "$DECISION_FILE")" = email ] \
    || die "decision is not a validated email decision"
OUTCOME="$(jq -r '.outcome' "$DECISION_FILE")"
CARD_NOTE="$(jq -r '.card_note' "$DECISION_FILE")"
SUMMARY="$(jq -r '.summary' "$DECISION_FILE")"
CONFIDENCE_SCORE="$(jq -r '.confidence_score' "$DECISION_FILE")"
# The band normalize-email already computed, shown on the card face.
case "$(jq -r '.confidence_band // "medium"' "$DECISION_FILE")" in
    high)   CONFIDENCE_BADGE="🟢" ;;
    low)    CONFIDENCE_BADGE="🔴" ;;
    *)      CONFIDENCE_BADGE="🟡" ;;
esac
EMAIL_COUNT="$(jq -r '.per_email | length' "$DECISION_FILE")"
STAGED_COUNT="$(jq -r '.staged_actions | length' "$DECISION_FILE")"
MODEL_NAME="$(autopr_kind_field email model)"

# Same defense in depth as publish.sh: the validator already checked these,
# but the card note is the one string that lands on the card face unescaped.
[[ "$CARD_NOTE" != *$'\n'* && "$CARD_NOTE" != *$'\r'* && "$CARD_NOTE" != *'·'* ]] \
    || die "email card note contains a forbidden separator or newline"
[ -n "$CARD_NOTE" ] && [ "${#CARD_NOTE}" -le 240 ] \
    || die "email card note must be 1-240 characters"
[ -s "$REPORT_FILE" ] || die "email review produced no report at $REPORT_FILE"

# Production provenance is context for a PR, not for a report. A missing build
# (an SSH or ECR hiccup on the runner) must not throw away a completed pass, so
# the segment is simply omitted from the card note.
PROVENANCE=""
if [ -n "$PROD_BUILD_NUMBER" ] && [ -n "$PROD_BACKEND_SHA" ] && [ -n "$PROD_FRONTEND_SHA" ]; then
    if [ "$PROD_BACKEND_SHA" = "$PROD_FRONTEND_SHA" ]; then
        PROVENANCE="build $PROD_BUILD_NUMBER · prod $PROD_BACKEND_SHA · "
    else
        PROVENANCE="build $PROD_BUILD_NUMBER · prod backend $PROD_BACKEND_SHA / frontend $PROD_FRONTEND_SHA · "
    fi
else
    printf 'kanban-autopr: warning: production context is incomplete; publishing the report without a build label\n' >&2
fi

STAGED_BLOCK="$(autopr_render_staged_actions "$DECISION_FILE")"
# Reply drafts become approvable rows only on a board granted `outreach`.
# Without the grant they stay what they already are — words in a report — and
# the publisher says so rather than silently dropping them.
BOARD_CAPABILITIES="$(jq -r '(.autopr_capabilities // [])[]' "$CARD_FILE" 2>/dev/null || true)"
OUTREACH_GRANTED=false
printf '%s\n' "$BOARD_CAPABILITIES" | grep -qxF outreach && OUTREACH_GRANTED=true

# stage_actions RUN_KEY — POST the proposals so a human can approve each one.
# Never fatal: the report is the deliverable, and losing the approve buttons
# must not discard a completed run. A 409 is the expected answer when the
# grant was revoked between selection and publication. RUN_KEY is the report
# file id: the server returns the existing rows for a key it has already seen,
# so a retried publication never puts a second set of Send rows on the card.
# Sets STAGING_RESULT to one line the summary note can quote.
STAGING_RESULT=""
stage_actions() {
    local run_key="$1" payload staging_error response already
    [ "$STAGED_COUNT" -gt 0 ] || return 0
    if [ "$OUTREACH_GRANTED" != true ]; then
        printf 'kanban-autopr: board lacks the outreach grant; %s proposed action(s) stay report-only\n' \
            "$STAGED_COUNT" >&2
        STAGING_RESULT="This board is not granted outreach, so the proposals above are notes only — there is nothing to approve."
        return 0
    fi
    payload="$(jq -c --arg key "$run_key" '{actions: .staged_actions, run_key: $key}' "$DECISION_FILE")"
    if ! response="$(mw_api POST \
        "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/autopr/staged-actions" \
        "$payload" 2>"$STAGE_DIR/staging.err")"; then
        staging_error="$(tr -d '\r' < "$STAGE_DIR/staging.err" | tail -1 | cut -c1-300)"
        printf 'kanban-autopr: warning: could not stage %s proposed action(s) for task %s: %s\n' \
            "$STAGED_COUNT" "$TASK_ID" "$staging_error" >&2
        STAGING_RESULT="The proposals above could not be staged for approval ($staging_error); they remain in the report only."
        return 0
    fi
    already="$(printf '%s' "$response" | jq -r '.already_staged // false' 2>/dev/null || printf false)"
    if [ "$already" = true ]; then
        printf 'Proposals for this report were already staged; not staging again\n'
    else
        printf 'Staged %s proposed action(s) for human approval\n' "$STAGED_COUNT"
    fi
    STAGING_RESULT="$STAGED_COUNT proposed action(s) are waiting for your approval under Proposed Outreach — none sent."
}

# Tell the person who supplied additional context what became of it. Same
# tolerant-404 shape as publish.sh: during a rolling deploy the workflow can
# reach production before the endpoint does, and that must not turn a
# completed publication into a false failure.
post_reconsideration_result() {
    local expected_note="$1" message="$2" notification_error
    [ -n "$RECONSIDERATION_EVENT_ID" ] || return 0
    if ! notification_error="$(mw_api POST \
        "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/autopr/result-notification" \
        "$(jq -n --arg event "$RECONSIDERATION_EVENT_ID" --arg note "$expected_note" \
            --arg message "$message" \
            '{reconsideration_event_id:$event,expected_progress_note:$note,message:$message}')" \
        2>&1 >/dev/null)"; then
        if [[ "$notification_error" == *"HTTP 404:"* ]]; then
            printf 'kanban-autopr: warning: result notification endpoint is not deployed; card publication for task %s remains complete\n' \
                "$TASK_ID" >&2
        else
            printf '%s\n' "$notification_error" >&2
            return 1
        fi
    fi
}

# ---- cannot review as asked: park the card with the question form ----------
if [ "$OUTCOME" = needs_clarification ]; then
    no_spec="[autopr:no-spec $(date -u +%Y-%m-%dT%H:%M:%SZ)] needs_clarification"
    origin_note="$(progress_note_with_origin \
        "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · $PROVENANCE$CONFIDENCE_BADGE C$CONFIDENCE_SCORE · $no_spec · note: $CARD_NOTE" \
        "$EXISTING_PROGRESS_NOTE")"
    # Exactly the form Espresso's "Answer AutoPR questions" UI parses.
    card_questions="$(autopr_render_card_questions "$DECISION_FILE")"
    [ -z "$card_questions" ] || origin_note="$origin_note

$card_questions"
    mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
        "$(jq -n --arg note "$origin_note" \
            '{board_column: "changes_requested", progress_note: $note}')" >/dev/null
    context_questions="$(jq -r '[.questions[]?.question] | join(" ")' "$DECISION_FILE")"
    autopr_post_context_request "$PROJECT_ID" "$TASK_ID" \
        "$CARD_NOTE $context_questions If an email is missing from the card, attach it from Espresso's Email panel with Send to board." \
        "$origin_note"
    post_reconsideration_result "$origin_note" \
        "AutoPR reviewed this additional context but still needs answers before it can review these emails. $CARD_NOTE"
    echo "Email review needs clarification; marked card $TASK_ID no-spec: needs_clarification"
    exit 0
fi

[ "$OUTCOME" = email_report ] || die "unknown email outcome: $OUTCOME"

# ---- report: attach it, note it, move the card to Review -------------------
# Re-entrant on purpose, keyed on the card itself — publish-research.sh
# carries the full reasoning. In short: the move to Review is the LAST write,
# a retry is always a fresh workflow run, and the report's own summary note
# ("Report attached: <file>") is posted only after its upload succeeded. So
# the newest email report on the card with no such line in the discussion is
# an orphan of a pass that died before announcing it, and this run continues
# it; an announced report is a finished round in any column. Residual gap: a
# pass dying between its note and the card move still produces one extra
# round on the retry.
STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT

existing_files="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files")"
# Fatal rather than fail-open: without the discussion we cannot tell a crashed
# pass from a finished one, and guessing means a duplicate report or a lost
# round. The next pass re-reads and reuses the orphan.
history_json="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/history")" \
    || die "could not read the card's discussion; not publishing blind"
announced_reports="$(printf '%s' "$history_json" | jq -c '
    [.[]? | select(.event_type == "activity") | (.metadata.body // "")
          | scan("Report attached: (email-report-\\S+\\.md)")]
    | flatten' 2>/dev/null || printf 'null')"
[ "$announced_reports" != null ] || die "could not read prior report announcements"

# Only the NEWEST report can be a crashed pass's orphan. The snapshots Espresso
# attached (email-<gmail id8>.md) never match: they carry no -report- infix.
orphan_report="$(printf '%s' "$existing_files" \
    | jq -c --arg id8 "$ID8" --argjson announced "$announced_reports" '
    ([.[] | select((.filename // "") | test("^email-report-" + $id8 + "-r[0-9]+\\.md$"))]
     | sort_by(.created_at) | last) as $newest
    | if $newest == null then empty
      elif ($newest.filename | IN($announced[])) then empty
      else $newest end')"

if [ -n "$orphan_report" ]; then
    FILE_ID="$(printf '%s' "$orphan_report" | jq -r '.id')"
    FILENAME="$(printf '%s' "$orphan_report" | jq -r '.filename')"
    ROUND="$(printf '%s' "$FILENAME" | sed -E 's/^.*-r([0-9]+)\.md$/\1/')"
    [[ "$ROUND" =~ ^[0-9]+$ ]] || die "could not read the round from $FILENAME"
    printf 'kanban-autopr: report %s was uploaded by an earlier pass that did not finish; reusing it\n' "$FILENAME" >&2
else
    # Round = how many email reports this card already carries, plus one. The
    # filename is what the next revision run finds among the attachments as
    # "version 1".
    prior_reports="$(printf '%s' "$existing_files" \
        | jq '[.[] | select((.filename // "") | test("^email-report-.*\\.md$"))] | length')"
    [[ "$prior_reports" =~ ^[0-9]+$ ]] || die "could not count prior email reports"
    ROUND=$((prior_reports + 1))
    FILENAME="email-report-$ID8-r$ROUND.md"
    FINAL_REPORT="$STAGE_DIR/$FILENAME"
    {
        # Trusted provenance header, written here rather than by the model.
        printf '_AutoPR email review · %s · model %s · round %s · %s email(s) reviewed_\n\n' \
            "$(date -u +'%Y-%m-%d %H:%M UTC')" "$MODEL_NAME" "$ROUND" "$EMAIL_COUNT"
        cat "$REPORT_FILE"
        if [ -n "$STAGED_BLOCK" ]; then
            printf '\n\n### Proposed actions (not sent)\n\n%s\n' "$STAGED_BLOCK"
            if [ "$OUTREACH_GRANTED" != true ]; then
                printf '\n_This board is not granted outreach, so these are notes only — there is nothing to approve._\n'
            fi
        fi
    } > "$FINAL_REPORT"
    upload="$(mw_api_upload "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files" "$FINAL_REPORT")"
    FILE_ID="$(printf '%s' "$upload" | jq -r '.id // empty')"
    [ -n "$FILE_ID" ] || die "report upload returned no file id: $upload"
fi
ATTACHMENT_IDS="[\"$FILE_ID\"]"

# Proposals become approvable rows BEFORE the note announces them, so a reader
# who opens the ticket the moment the notification lands never sees "needs
# your approval" above an empty Proposed Outreach section. Keyed on the report
# id so a retry finds the rows it already made.
stage_actions "$FILE_ID"

note_body="$SUMMARY

Report attached: $FILENAME"
[ -z "$STAGED_BLOCK" ] || note_body="$note_body

$STAGED_BLOCK"
[ -z "$STAGING_RESULT" ] || note_body="$note_body
$STAGING_RESULT"

# The note names its report file, which is what makes the report announced —
# so the announcement list read above is also this write's natural key.
note_already_posted=false
if printf '%s' "$announced_reports" | jq -e --arg f "$FILENAME" 'any(.[]?; . == $f)' >/dev/null; then
    note_already_posted=true
    printf 'kanban-autopr: summary note for %s is already on the card; not posting again\n' "$FILENAME" >&2
fi
if [ "$note_already_posted" != true ]; then
    activity_payload="$(jq -n --arg body "$note_body" --argjson files "$ATTACHMENT_IDS" \
        --arg reply "$RECONSIDERATION_EVENT_ID" \
        '{kind:"note", body:$body, attachment_ids:$files}
         + (if $reply == "" then {} else {reply_to:$reply} end)')"
    mw_api POST "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/activity" "$activity_payload" >/dev/null
fi

origin_note="$(progress_note_with_origin \
    "🤖 AUTO SETUP · READY FOR REVIEW · $PROVENANCE$CONFIDENCE_BADGE C$CONFIDENCE_SCORE · note: $CARD_NOTE" \
    "$EXISTING_PROGRESS_NOTE")"
mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
    "$(jq -n --arg note "$origin_note" \
        '{board_column: "review", progress_note: $note}')" >/dev/null

post_reconsideration_result "$origin_note" \
    "AutoPR reviewed this additional context and attached email report round $ROUND. $CARD_NOTE"

if [ "$STAGED_COUNT" -gt 0 ]; then
    echo "Published $FILENAME for task $TASK_ID ($MODE, round $ROUND, $EMAIL_COUNT email(s) reviewed, $STAGED_COUNT reply draft(s) awaiting human approval — none sent)"
else
    echo "Published $FILENAME for task $TASK_ID ($MODE, round $ROUND, $EMAIL_COUNT email(s) reviewed)"
fi
