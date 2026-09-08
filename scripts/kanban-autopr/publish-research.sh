#!/usr/bin/env bash
# Publish a research run: attach the report to the card, post a summary note
# carrying it, and move the card to Review — or, when the subject was too
# vague, park it in Changes Requested with the numbered question form the
# operator answers from the ticket. `update_project_task` on the server then
# notifies every collaborator ("Ready for review") the same way it does for a
# merged PR card, so nothing here talks to email or chat directly.
#
# Never touches git, gh, or labels: a research card owns no branch and no PR.
# Every board write goes through the bot's REST identity (lib.sh:mw_api).
#
# Usage: ./publish-research.sh card.json report.md decision.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"
# shellcheck source=./decision.sh
source "$SCRIPT_DIR/decision.sh"

CARD_FILE="${1:?usage: publish-research.sh card.json report.md decision.json}"
REPORT_FILE="${2:?usage: publish-research.sh card.json report.md decision.json}"
DECISION_FILE="${3:?usage: publish-research.sh card.json report.md decision.json}"

TASK_ID="$(jq -r '.task_id' "$CARD_FILE")"
PROJECT_ID="$(jq -r '.project_id' "$CARD_FILE")"
ID8="$(jq -r '.id8' "$CARD_FILE")"
MODE="$(jq -r '.mode' "$CARD_FILE")"
PROD_BUILD_NUMBER="$(jq -r '.production.build_number // empty' "$CARD_FILE")"
PROD_BACKEND_SHA="$(jq -r '.production.containers.backend.git_sha // empty' "$CARD_FILE")"
PROD_FRONTEND_SHA="$(jq -r '.production.containers.frontend.git_sha // empty' "$CARD_FILE")"
EXISTING_PROGRESS_NOTE="$(jq -r '.progress_note // ""' "$CARD_FILE")"
RECONSIDERATION_EVENT_ID="$(jq -r '.autopr_reconsideration_event_id // empty' "$CARD_FILE")"

# Only a decision that went through decision.sh normalize-research may drive
# a board write; the raw model JSON never reaches this script.
[ "$(jq -r '.kind // empty' "$DECISION_FILE")" = research ] \
    || die "decision is not a validated research decision"
OUTCOME="$(jq -r '.outcome' "$DECISION_FILE")"
CARD_NOTE="$(jq -r '.card_note' "$DECISION_FILE")"
SUMMARY="$(jq -r '.summary' "$DECISION_FILE")"
CONFIDENCE_SCORE="$(jq -r '.confidence_score' "$DECISION_FILE")"
SOURCE_COUNT="$(jq -r '.sources | length' "$DECISION_FILE")"
STAGED_COUNT="$(jq -r '.staged_actions | length' "$DECISION_FILE")"
MODEL_NAME="$(autopr_kind_field research model)"

# Same defense in depth as publish.sh: the validator already checked these,
# but the card note is the one string that lands on the card face unescaped.
[[ "$CARD_NOTE" != *$'\n'* && "$CARD_NOTE" != *$'\r'* && "$CARD_NOTE" != *'·'* ]] \
    || die "research card note contains a forbidden separator or newline"
[ -n "$CARD_NOTE" ] && [ "${#CARD_NOTE}" -le 240 ] \
    || die "research card note must be 1-240 characters"
[ -s "$REPORT_FILE" ] || die "research produced no report at $REPORT_FILE"

[ -n "$PROD_BUILD_NUMBER" ] || die "card context is missing the production build number"
[ -n "$PROD_BACKEND_SHA" ] || die "card context is missing the production backend SHA"
[ -n "$PROD_FRONTEND_SHA" ] || die "card context is missing the production frontend SHA"
if [ "$PROD_BACKEND_SHA" = "$PROD_FRONTEND_SHA" ]; then
    PROD_LABEL="prod $PROD_BACKEND_SHA"
else
    PROD_LABEL="prod backend $PROD_BACKEND_SHA / frontend $PROD_FRONTEND_SHA"
fi

STAGED_BLOCK="$(autopr_render_staged_actions "$DECISION_FILE")"

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

# ---- too vague to research: park the card with the question form ----------
if [ "$OUTCOME" = needs_clarification ]; then
    no_spec="[autopr:no-spec $(date -u +%Y-%m-%dT%H:%M:%SZ)] needs_clarification"
    origin_note="$(progress_note_with_origin \
        "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build $PROD_BUILD_NUMBER · $PROD_LABEL · 🟡 C$CONFIDENCE_SCORE · $no_spec · note: $CARD_NOTE" \
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
        "$CARD_NOTE $context_questions You can attach a screenshot in your Espresso reply or on the ticket." \
        "$origin_note"
    post_reconsideration_result "$origin_note" \
        "AutoPR reviewed this additional context but still needs answers before it can research this card. $CARD_NOTE"
    echo "Research needs clarification; marked card $TASK_ID no-spec: needs_clarification"
    exit 0
fi

[ "$OUTCOME" = research_report ] || die "unknown research outcome: $OUTCOME"

# ---- report: attach it, note it, move the card to Review -------------------
# Round = how many reports this card already carries, plus one. The filename
# is what the next revision run finds among the attachments as "version 1".
existing_files="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files")"
prior_reports="$(printf '%s' "$existing_files" \
    | jq '[.[] | select((.filename // "") | test("^research-report-.*\\.md$"))] | length')"
[[ "$prior_reports" =~ ^[0-9]+$ ]] || die "could not count prior research reports"
ROUND=$((prior_reports + 1))
FILENAME="research-report-$ID8-r$ROUND.md"

STAGE_DIR="$(mktemp -d)"
trap 'rm -rf "$STAGE_DIR"' EXIT
FINAL_REPORT="$STAGE_DIR/$FILENAME"
{
    # Trusted provenance header, written here rather than by the model.
    printf '_AutoPR research · %s · model %s · round %s · %s source(s)_\n\n' \
        "$(date -u +'%Y-%m-%d %H:%M UTC')" "$MODEL_NAME" "$ROUND" "$SOURCE_COUNT"
    cat "$REPORT_FILE"
    if [ -n "$STAGED_BLOCK" ]; then
        printf '\n\n### Proposed actions (not sent)\n\n%s\n' "$STAGED_BLOCK"
    fi
} > "$FINAL_REPORT"

upload="$(mw_api_upload "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files" "$FINAL_REPORT")"
FILE_ID="$(printf '%s' "$upload" | jq -r '.id // empty')"
[ -n "$FILE_ID" ] || die "report upload returned no file id: $upload"

note_body="$SUMMARY

Report attached: $FILENAME"
[ -z "$STAGED_BLOCK" ] || note_body="$note_body

$STAGED_BLOCK"
activity_payload="$(jq -n --arg body "$note_body" --arg file "$FILE_ID" \
    --arg reply "$RECONSIDERATION_EVENT_ID" \
    '{kind:"note", body:$body, attachment_ids:[$file]}
     + (if $reply == "" then {} else {reply_to:$reply} end)')"
mw_api POST "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/activity" "$activity_payload" >/dev/null

origin_note="$(progress_note_with_origin \
    "🤖 AUTO SETUP · READY FOR REVIEW · build $PROD_BUILD_NUMBER · $PROD_LABEL · 🟡 C$CONFIDENCE_SCORE · note: $CARD_NOTE" \
    "$EXISTING_PROGRESS_NOTE")"
mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
    "$(jq -n --arg note "$origin_note" \
        '{board_column: "review", progress_note: $note}')" >/dev/null

post_reconsideration_result "$origin_note" \
    "AutoPR reviewed this additional context and attached research report round $ROUND. $CARD_NOTE"

if [ "$STAGED_COUNT" -gt 0 ]; then
    echo "Published $FILENAME for task $TASK_ID ($MODE, round $ROUND, $SOURCE_COUNT sources, $STAGED_COUNT proposed actions not sent)"
else
    echo "Published $FILENAME for task $TASK_ID ($MODE, round $ROUND, $SOURCE_COUNT sources)"
fi
