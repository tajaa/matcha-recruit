#!/usr/bin/env bash
# Stage the investigation's diff, guard it, and either open/update a draft PR
# or publish a question draft when the card needs a human answer. The board is
# where this user works, not GitHub Issues.
#
# Usage: ./publish.sh card.json decision.json report.md verification.md publication-copy.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AUTOPR_WORKSPACE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"
# shellcheck source=./decision.sh
source "$SCRIPT_DIR/decision.sh"

CARD_FILE="${1:?usage: publish.sh card.json decision.json report.md verification.md publication-copy.json}"
DECISION_FILE="${2:?usage: publish.sh card.json decision.json report.md verification.md publication-copy.json}"
REPORT_FILE="${3:?usage: publish.sh card.json decision.json report.md verification.md publication-copy.json}"
VERIFICATION_FILE="${4:?usage: publish.sh card.json decision.json report.md verification.md publication-copy.json}"
PUBLICATION_COPY_FILE="${5:?usage: publish.sh card.json decision.json report.md verification.md publication-copy.json}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"

TASK_ID="$(jq -r '.task_id' "$CARD_FILE")"
PROJECT_ID="$(jq -r '.project_id' "$CARD_FILE")"
ID8="$(jq -r '.id8' "$CARD_FILE")"
MODE="$(jq -r '.mode' "$CARD_FILE")"
TITLE="$(jq -r '.title' "$CARD_FILE")"
DESCRIPTION="$(jq -r '.description // ""' "$CARD_FILE")"
CATEGORY="$(jq -r '.category // "manual"' "$CARD_FILE")"
PROJECT_TITLE="$(jq -r '.project_title // ""' "$CARD_FILE")"
PROD_BUILD_NUMBER="$(jq -r '.production.build_number // empty' "$CARD_FILE")"
PROD_BACKEND_SHA="$(jq -r '.production.containers.backend.git_sha // empty' "$CARD_FILE")"
PROD_FRONTEND_SHA="$(jq -r '.production.containers.frontend.git_sha // empty' "$CARD_FILE")"
EXISTING_PROGRESS_NOTE="$(jq -r '.progress_note // ""' "$CARD_FILE")"
EXISTING_PR_NUMBER="$(jq -r '.pr_number // empty' "$CARD_FILE")"
RECONSIDERATION_EVENT_ID="$(jq -r '.autopr_reconsideration_event_id // empty' "$CARD_FILE")"
OUTCOME="$(jq -r '.outcome' "$DECISION_FILE")"
CONFIDENCE_SCORE="$(jq -r '.confidence_score' "$DECISION_FILE")"
CONFIDENCE_BAND="$(jq -r '.confidence_band' "$DECISION_FILE")"
CRITICALITY="$(jq -r '.criticality.level' "$DECISION_FILE")"
CRITICALITY_EMOJI="$(autopr_criticality_emoji "$CRITICALITY")"
AWAITING_HUMAN="$(jq -r '.awaiting_human' "$DECISION_FILE")"
NO_SAFE_ACTION_REASON="$(jq -r '.no_safe_action_reason // empty' "$DECISION_FILE")"
# A runtime extension is not standing product authority.
DIRECTIVE_CSV="$(jq -r '(.autopr_directives // []) | map(select(. == "draft_pr" or . == "trust_still_broken")) | join(",")' "$DECISION_FILE")"
DIRECTIVE_MARKER=""
[ -z "$DIRECTIVE_CSV" ] || DIRECTIVE_MARKER=" · [autopr:directives $DIRECTIVE_CSV]"
PRODUCTION_VERIFICATION_JSON="$(jq -c '.production_verification' "$DECISION_FILE")"
PRODUCTION_VERIFICATION_B64="$(printf '%s' "$PRODUCTION_VERIFICATION_JSON" | base64 | tr -d '\r\n')"
COMMIT_SUBJECT="$(jq -er '.commit_subject | select(type == "string")' "$PUBLICATION_COPY_FILE")" \
    || die "publication copy is missing a commit subject"
CARD_NOTE="$(jq -er '.card_note | select(type == "string")' "$PUBLICATION_COPY_FILE")" \
    || die "publication copy is missing a card note"
NEW_FAILURES="${AUTOFIX_NEW_FAILURES:-0}"
POSSIBLE_DUPLICATE="${AUTOPR_POSSIBLE_DUPLICATE:-0}"
NOTE_STATE="ready_for_review"
if [ "$AWAITING_HUMAN" = true ]; then
    NOTE_STATE="awaiting_answers"
elif [ "$OUTCOME" = no_safe_action ]; then
    NOTE_STATE="no_safe_action"
fi

auto_setup_status() {
    if [ "$AWAITING_HUMAN" = true ]; then
        printf 'BLOCKED: AWAITING ANSWERS'
        return
    fi
    if [ "$OUTCOME" = no_safe_action ]; then
        case "$NO_SAFE_ACTION_REASON" in
            already_fixed) printf 'NO PR: ALREADY FIXED' ;;
            acceptance_criteria_met) printf 'NO PR: CARD ALREADY SATISFIED' ;;
            policy_blocked) printf 'NO PR: POLICY BLOCKED' ;;
            external_dependency) printf 'NO PR: EXTERNAL DEPENDENCY' ;;
            *) printf 'NO PR: HUMAN ACTION REQUIRED' ;;
        esac
        return
    fi
    printf 'READY FOR REVIEW'
}
AUTO_SETUP_STATUS="$(auto_setup_status)"

[ -n "$PROD_BUILD_NUMBER" ] || die "card context is missing the production build number"
[ -n "$PROD_BACKEND_SHA" ] || die "card context is missing the production backend SHA"
[ -n "$PROD_FRONTEND_SHA" ] || die "card context is missing the production frontend SHA"

if [ "$PROD_BACKEND_SHA" = "$PROD_FRONTEND_SHA" ]; then
    PROD_LABEL="prod $PROD_BACKEND_SHA"
else
    PROD_LABEL="prod backend $PROD_BACKEND_SHA / frontend $PROD_FRONTEND_SHA"
fi

progress_note_with_origin() {
    local marker="$1" existing="$2" header body preserved remainder
    # Replace this system's prior structured prefix on rework instead of
    # nesting it every round. Preserve any human-authored text after it.
    header="${existing%%$'\n'*}"
    if [ "$header" = "$existing" ]; then
        body=""
    else
        body="${existing#*$'\n'}"
    fi
    if [[ "$header" != "from auto setup"* ]] && [[ "$header" != "🤖 AUTO SETUP"* ]]; then
        # Entirely human-authored: nothing of it is this system's to rewrite.
        header="$existing"
        body=""
    fi
    # Drop only the machine-written blocks below the header: the pause report
    # and the question form (always written last). Everything else on those
    # lines is the operator's and survives the next cycle.
    preserved="$(printf '%s\n' "$body" | awk '
        /^Answers needed — reply below with the numbered choices:/ { exit }
        /^(Why more time|Done so far|Latest progress|Next step):/ { next }
        NF { seen = 1 }
        seen { lines[n++] = $0 }
        END {
            while (n > 0 && lines[n-1] ~ /^[[:space:]]*$/) n--
            for (i = 0; i < n; i++) print lines[i]
        }
    ')"
    remainder="$(printf '%s' "$header" | sed -E \
        's/^from auto setup( · build [^·]+)?( · prod( backend)? [^·]+( \/ frontend [^·]+)?)?( · PR #[0-9]+)?( · [^·]+ C[0-9]+ · (awaiting answers|ready for review|no safe action))?( · \[autopr:directives [^]]+\])?( · \[autopr:no-spec [^]]+\] (already_fixed|acceptance_criteria_met|migration_required|policy_blocked|external_dependency))?( · note: [^·]+)?( · )?//')"
    # New notes put the state first so the narrow card face shows the reason
    # for a stall before build provenance. Keep accepting the legacy lowercase
    # prefix above so an upgrade does not duplicate an existing human note.
    # PAUSED belongs in this alternation: checkpoint.sh writes it, so without
    # it every recovery run would re-append its own stale pause header here.
    remainder="$(printf '%s' "$remainder" | sed -E \
        's/^🤖 AUTO SETUP · (READY FOR REVIEW|BLOCKED: AWAITING ANSWERS|PAUSED: [A-Z0-9]+( [A-Z0-9]+)*|NO PR: [A-Z_ -]+)( · checkpoint [^·]+)?( · build [^·]+)?( · prod( backend)? [^·]+( \/ frontend [^·]+)?)?( · PR #[0-9]+)?( · [^·]+ C[0-9]+)?( · \[autopr:directives [^]]+\])?( · \[autopr:no-spec [^]]+\] (already_fixed|acceptance_criteria_met|migration_required|policy_blocked|external_dependency))?( · note: [^·]+)?( · )?//')"
    if [ -n "$remainder" ] && [ "$remainder" != "$header" ]; then
        printf '%s · %s' "$marker" "$remainder"
    elif [ -n "$header" ] \
        && [[ "$header" != "from auto setup"* ]] \
        && [[ "$header" != "🤖 AUTO SETUP"* ]]; then
        printf '%s · %s' "$marker" "$header"
    else
        printf '%s' "$marker"
    fi
    [ -z "$preserved" ] || printf '\n%s' "$preserved"
}

report_summary() {
    awk '
      /^### Summary[[:space:]]*$/ { capture=1; next }
      /^### / && capture { exit }
      capture { print }
    ' "$REPORT_FILE" | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//' \
        | jq -Rsr '.[0:1200]'
}

post_reconsideration_reply() {
    local pr_number="${1:-}" expected_note="${2:-}" summary message fixed_pr notification_error
    [ -n "$RECONSIDERATION_EVENT_ID" ] || return 0
    [ -n "$expected_note" ] || die "reconsideration result is missing its decision note"
    summary="$(report_summary)"
    case "$OUTCOME" in
        implementation)
            message="AutoPR accepted this additional context and drafted PR #$pr_number."
            ;;
        partial_implementation|questions_only)
            message="AutoPR reviewed this additional context but still needs human answers in PR #$pr_number."
            ;;
        no_safe_action)
            if [ "$NO_SAFE_ACTION_REASON" = already_fixed ]; then
                fixed_pr="${pr_number:-$EXISTING_PR_NUMBER}"
                if [[ "$fixed_pr" =~ ^[0-9]+$ ]]; then
                    message="After reviewing your additional context, AutoPR still found this request already fixed in PR #$fixed_pr."
                else
                    message="After reviewing your additional context, AutoPR still found this request already fixed."
                fi
            else
                message="After reviewing your additional context, AutoPR found that the no-PR decision still applies ($NO_SAFE_ACTION_REASON)."
            fi
            ;;
        *) return 0 ;;
    esac
    [ -z "$summary" ] || message="$message $summary"
    if ! (mw_api POST "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/activity" \
        "$(jq -n --arg body "$message" --arg reply "$RECONSIDERATION_EVENT_ID" \
            '{kind:"note",body:$body,reply_to:$reply}')" >/dev/null); then
        printf 'kanban-autopr: warning: could not post reconsideration result for task %s\n' "$TASK_ID" >&2
    fi
    # The activity thread is durable history, but the AutoPR account can be
    # the same identity as the reporter and ordinary comment notifications
    # deliberately suppress self-notification. This decision-bound endpoint
    # targets the original context author. During a rolling deployment the
    # workflow can reach production before the endpoint does; do not turn an
    # already-published PR/card update into a false failure for that one known
    # compatibility case. Authentication and all other API errors remain fatal.
    if ! notification_error="$(mw_api POST \
        "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/autopr/result-notification" \
        "$(jq -n --arg event "$RECONSIDERATION_EVENT_ID" --arg note "$expected_note" \
            --arg message "$message" \
            '{reconsideration_event_id:$event,expected_progress_note:$note,message:$message}')" \
        2>&1 >/dev/null)"; then
        if [[ "$notification_error" == *"HTTP 404:"* ]]; then
            printf 'kanban-autopr: warning: result notification endpoint is not deployed; PR/card publication for task %s remains complete\n' \
                "$TASK_ID" >&2
        else
            printf '%s\n' "$notification_error" >&2
            return 1
        fi
    fi
}

post_context_request() {
    local reason="$1" expected_note="$2"
    # Newlines survive: the acceptance-evidence block is the payload here, and
    # flattening it to one line at 600 characters cut the proof off after about
    # four criteria. The server sanitizes and bounds it again.
    reason="$(printf '%s' "$reason" | tr -d '\r' | jq -Rsr '.[0:4000]')"
    if ! (mw_api POST "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/autopr/context-request" \
        "$(jq -n --arg reason "$reason" --arg note "$expected_note" \
            '{reason:$reason,expected_progress_note:$note}')" >/dev/null); then
        # The card/PR state remains authoritative; surface chat delivery loss
        # without rolling back an otherwise complete publication.
        printf 'kanban-autopr: warning: could not post Espresso context request for task %s\n' \
            "$TASK_ID" >&2
    fi
}

BRANCH="bot/task-$ID8"

# Dying here used to fail the workflow step with the diff discarded, no card
# note, and nothing in chat: the next scheduled cycle re-selected the same card
# and reproduced the same cosmetic diff forever, with no signal to a human. The
# refusal stands, but it lands on the card and asks its owner for a decision.
reject_cosmetic_diff() {
    local reject_note origin_note
    reject_note="[autopr:rejected $(date -u +%Y-%m-%dT%H:%M:%SZ)] cosmetic_only"
    origin_note="$(progress_note_with_origin \
        "🤖 AUTO SETUP · BLOCKED: COSMETIC DIFF · build $PROD_BUILD_NUMBER · $PROD_LABEL · $CRITICALITY_EMOJI C$CONFIDENCE_SCORE$DIRECTIVE_MARKER · $reject_note · note: $CARD_NOTE" \
        "$EXISTING_PROGRESS_NOTE")"
    if mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
        "$(jq -n --arg note "$origin_note" '{progress_note: $note}')" >/dev/null; then
        post_context_request \
            "AutoPR produced a diff that only rewrites string literals for a card asking for structure, so it was discarded. Either the criteria are already met — reply and it will return acceptance_criteria_met with per-criterion evidence — or the card needs the missing structural detail." \
            "$origin_note"
    else
        printf 'kanban-autopr: warning: could not record the cosmetic-diff rejection on task %s\n' \
            "$TASK_ID" >&2
    fi
    die "implementation diff only rewrites string literals for a card asking for structure; return acceptance_criteria_met with evidence, or questions_only"
}

existing_feedback_checkpoint() {
    local body="$1" kind="$2"
    printf '%s' "$body" | sed -nE "s/.*<!-- matcha-feedback-${kind}-id: ([^ ]+) -->.*/\\1/p" | tail -1
}

render_body() {
    local output_file="$1" comment_id="$2" review_id="$3"
    {
        echo "<!-- matcha-task: $TASK_ID -->"
        echo "<!-- matcha-project: $PROJECT_ID -->"
        echo "<!-- matcha-production-build: $PROD_BUILD_NUMBER -->"
        echo "<!-- matcha-production-backend-sha: $PROD_BACKEND_SHA -->"
        echo "<!-- matcha-production-frontend-sha: $PROD_FRONTEND_SHA -->"
        echo "<!-- matcha-autopr-outcome: $OUTCOME -->"
        echo "<!-- matcha-autopr-criticality: $CRITICALITY -->"
        echo "<!-- matcha-autopr-confidence-score: $CONFIDENCE_SCORE -->"
        echo "<!-- matcha-autopr-note-state: $NOTE_STATE -->"
        echo "<!-- matcha-production-verification: $PRODUCTION_VERIFICATION_B64 -->"
        [ -z "$NO_SAFE_ACTION_REASON" ] || echo "<!-- matcha-autopr-no-safe-action-reason: $NO_SAFE_ACTION_REASON -->"
        echo "<!-- matcha-feedback-comment-id: ${comment_id:-none} -->"
        echo "<!-- matcha-feedback-review-id: ${review_id:-none} -->"
        echo
        echo "## $TITLE"
        [ -n "$PROJECT_TITLE" ] && echo "**Board** $PROJECT_TITLE"
        echo "**Production baseline** build $PROD_BUILD_NUMBER · $PROD_LABEL"
        echo "**Triage** $CRITICALITY_EMOJI $CRITICALITY · confidence $CONFIDENCE_SCORE/100 ($CONFIDENCE_BAND)"
        echo
        if [ "$AWAITING_HUMAN" = true ]; then
            autopr_render_questions "$DECISION_FILE"
            echo
        fi
        if [ -n "$DESCRIPTION" ]; then
            echo "$DESCRIPTION"
            echo
        fi
        cat "$REPORT_FILE"
        echo
        cat "$VERIFICATION_FILE"
        echo
        echo "## Production verification"
        jq -r '
          .production_verification |
          "**Target** " + .target + " · **Mode** " + .mode + "\n\n" +
          .reason + "\n\n" +
          (if .mode == "automatic_http" then
             (.checks | map("- `GET " + .path + "` → " + (.expected_status | tostring) +
               (if (.body_contains // "") != "" then "; contains `" + .body_contains + "`" else "" end) +
               (if (.body_absent // "") != "" then "; excludes `" + .body_absent + "`" else "" end)) | join("\n"))
           else
             (.steps | to_entries | map(((.key + 1) | tostring) + ". " + .value) | join("\n"))
           end)
        ' "$DECISION_FILE"
        echo
        echo "_This check becomes eligible only after this merge is present in the deployed production SHA._"
        echo
        echo "_Built by [this workflow run]($RUN_URL)._"
    } > "$output_file"
}

replace_triage_labels() {
    local target="$1"
    local labels old desired_criticality="criticality:$CRITICALITY" desired_confidence="confidence:$CONFIDENCE_BAND"
    local -a args=(pr edit "$target" --repo "$REPO")
    labels="$(gh pr view "$target" --repo "$REPO" --json labels --jq '.labels[].name')"
    for old in criticality:red criticality:orange criticality:yellow confidence:high confidence:medium confidence:low autopr-awaiting-input; do
        if printf '%s\n' "$labels" | grep -qx "$old" \
            && [ "$old" != "$desired_criticality" ] \
            && [ "$old" != "$desired_confidence" ] \
            && { [ "$old" != autopr-awaiting-input ] || [ "$AWAITING_HUMAN" != true ]; }; then
            args+=(--remove-label "$old")
        fi
    done
    args+=(--add-label autopr --add-label "$desired_criticality" --add-label "$desired_confidence")
    [ "$MODE" != rework ] || args+=(--add-label autopr-rework)
    [ "$AWAITING_HUMAN" != true ] || args+=(--add-label autopr-awaiting-input)
    [ "$POSSIBLE_DUPLICATE" != 1 ] || args+=(--add-label possible-duplicate)
    if [ "$NEW_FAILURES" -gt 0 ] 2>/dev/null; then
        args+=(--add-label needs-work)
    elif printf '%s\n' "$labels" | grep -qx needs-work; then
        args+=(--remove-label needs-work)
    fi
    gh "${args[@]}" >/dev/null
}

cd "$REPO_ROOT"
git add --all

# Path guard: denylist is what stops the bot rewriting its own harness or CI.
# The allowlist is strictly stronger. Authoring a new migration version is
# ordinary drafting work: publication always opens a GitHub draft PR and this
# script never runs a migration. Existing mainline migrations and all migration
# runner/configuration files remain closed.
changed_paths="$(git diff --cached --no-renames --name-only)"
unsafe_paths="$(printf '%s\n' "$changed_paths" | grep -E '(^\.github/|^deploy/|^scripts/|^client/src/generated/|(^|/)\.env|(^|/)(package(-lock)?\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|Pipfile(\.lock)?|Dockerfile[^/]*|docker-compose[^/]*\.ya?ml)$)' || true)"
unsafe_migrations="$(printf '%s\n' "$changed_paths" \
    | grep -E '^server/alembic/' \
    | grep -vE '^server/alembic/versions/[A-Za-z0-9_]+\.py$' || true)"
if [ -n "$unsafe_migrations" ]; then
    unsafe_paths="${unsafe_paths}${unsafe_paths:+$'\n'}${unsafe_migrations}"
fi
if [ -n "$unsafe_paths" ]; then
    echo "Refusing unsafe automated change:" >&2
    printf '%s\n' "$unsafe_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

allowed_paths_re='^(server/(app|tests)/.*\.py|server/alembic/versions/[A-Za-z0-9_]+\.py|client/src/.*\.(ts|tsx)|platforms/desktop/Espresso/Espresso/.*\.swift)$'
disallowed_paths="$(printf '%s\n' "$changed_paths" | grep -vE "$allowed_paths_re" || true)"
if [ -n "$disallowed_paths" ]; then
    echo "Refusing change outside approved product source paths:" >&2
    printf '%s\n' "$disallowed_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

migration_paths="$(printf '%s\n' "$changed_paths" \
    | grep -E '^server/alembic/versions/[A-Za-z0-9_]+\.py$' || true)"
if [ -n "$migration_paths" ]; then
    migration_base_ref="${AUTOPR_MIGRATION_BASE_REF:-main}"
    git rev-parse --verify "$migration_base_ref^{commit}" >/dev/null 2>&1 \
        || die "migration safety base is unavailable: $migration_base_ref"

    deleted_migrations="$(git diff --cached --diff-filter=D --no-renames --name-only -- \
        server/alembic/versions || true)"
    if [ -n "$deleted_migrations" ]; then
        echo "Refusing deletion of migration version files:" >&2
        printf '%s\n' "$deleted_migrations" >&2
        git reset --hard >/dev/null 2>&1
        exit 1
    fi

    unsafe_migration_modes="$(git diff --cached --raw --no-renames -- \
        server/alembic/versions \
        | awk '$2 != "100644" {print $0}' || true)"
    if [ -n "$unsafe_migration_modes" ]; then
        echo "Refusing non-regular migration version files:" >&2
        printf '%s\n' "$unsafe_migration_modes" >&2
        git reset --hard >/dev/null 2>&1
        exit 1
    fi

    existing_migrations=""
    while IFS= read -r migration_path; do
        [ -n "$migration_path" ] || continue
        migration_status="$(git diff --cached --no-renames --name-status \
            "$migration_base_ref" -- "$migration_path" | awk 'NR == 1 {print $1}')"
        if [ "$migration_status" != A ]; then
            existing_migrations="${existing_migrations}${existing_migrations:+$'\n'}${migration_path}"
        fi
    done <<< "$migration_paths"
    if [ -n "$existing_migrations" ]; then
        echo "Refusing edits to migration files already present on $migration_base_ref:" >&2
        printf '%s\n' "$existing_migrations" >&2
        git reset --hard >/dev/null 2>&1
        exit 1
    fi

    if ! migration_graph_error="$(python3 "$REPO_ROOT/scripts/alembic_graph_snapshot.py" \
        "$REPO_ROOT/server/alembic/versions" 2>&1)"; then
        echo "Refusing an invalid migration graph or migration file:" >&2
        printf '%s\n' "$migration_graph_error" >&2
        git reset --hard >/dev/null 2>&1
        exit 1
    fi
fi

# Same telemetry-suppression boundary error-autofix guards — kanban cards
# can touch client.ts too (it's the one file every frontend PR eventually
# brushes against), and this bot must not be the one that quietly loosens
# what gets reported.
unsafe_reporting_change="$(git diff --cached -U0 -- client/src/api/client.ts | grep -E '^[+-].*(_EXPECTED_STATUSES|function _shouldReportStatus)|^-.*reportApiError\(' || true)"
if [ -n "$unsafe_reporting_change" ]; then
    echo "Refusing automated change to browser error-reporting policy:" >&2
    printf '%s\n' "$unsafe_reporting_change" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

case "$CATEGORY" in
    feat) PREFIX="feat" ;;
    fix|bug) PREFIX="fix" ;;
    *) PREFIX="chore" ;;
esac
[ "${COMMIT_SUBJECT#"$PREFIX: "}" != "$COMMIT_SUBJECT" ] \
    || die "publication commit subject must start with $PREFIX:"
[[ "$COMMIT_SUBJECT" != *$'\n'* && "$COMMIT_SUBJECT" != *$'\r'* ]] \
    || die "publication commit subject must be one line"
[ "${#COMMIT_SUBJECT}" -le 72 ] || die "publication commit subject exceeds 72 characters"
[[ "$CARD_NOTE" != *$'\n'* && "$CARD_NOTE" != *$'\r'* && "$CARD_NOTE" != *'·'* ]] \
    || die "publication card note contains a forbidden separator or newline"
[ -n "$CARD_NOTE" ] && [ "${#CARD_NOTE}" -le 240 ] \
    || die "publication card note must be 1-240 characters"

# The decision must agree with the actual working tree. Do not turn a model
# mismatch into a permanent no-spec marker, and never publish product changes
# beside a questions-only draft.
has_diff=false
git diff --cached --quiet || has_diff=true
case "$OUTCOME" in
    implementation|partial_implementation)
        [ "$has_diff" = true ] || die "decision says safe changes exist but the worktree is empty"
        # A partial_implementation carries the same shape for the same reason,
        # so the guard covers both outcomes rather than leaving the lower bar
        # as a way around it.
        STAGED_DIFF_FILE="$(mktemp)"
        git diff --cached > "$STAGED_DIFF_FILE"
        if autopr_cosmetic_only_diff "$STAGED_DIFF_FILE" "$TITLE" "$DESCRIPTION"; then
            rm -f "$STAGED_DIFF_FILE"
            git reset --hard >/dev/null 2>&1
            reject_cosmetic_diff
        fi
        rm -f "$STAGED_DIFF_FILE"
        ;;
    questions_only|no_safe_action)
        if [ "$has_diff" = true ]; then
            git reset --hard >/dev/null 2>&1
            die "decision forbids product changes but the worktree contains a diff"
        fi
        ;;
    *) die "unknown triage outcome: $OUTCOME" ;;
esac

existing_open_json='[]'
if [ "$OUTCOME" != no_safe_action ] || [ "$MODE" = rework ]; then
    git config user.name "matcha-kanban-autopr"
    git config user.email "matcha-kanban-autopr@users.noreply.github.com"
    existing_open_json="$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --limit 1 --json number,body)"
fi
existing_open_pr="$(printf '%s' "$existing_open_json" | jq -r '.[0].number // empty')"
existing_body="$(printf '%s' "$existing_open_json" | jq -r '.[0].body // ""')"
old_comment_id="$(existing_feedback_checkpoint "$existing_body" comment)"
old_review_id="$(existing_feedback_checkpoint "$existing_body" review)"
if jq -e '.feedback_checkpoint | type == "object"' "$DECISION_FILE" >/dev/null; then
    consumed_comment_id="$(jq -r '.feedback_checkpoint.comment_id // ""' "$DECISION_FILE")"
    consumed_review_id="$(jq -r '.feedback_checkpoint.review_id // ""' "$DECISION_FILE")"
else
    consumed_comment_id="$old_comment_id"
    consumed_review_id="$old_review_id"
fi

RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/$REPO/actions/runs/${GITHUB_RUN_ID:-}"
TITLE_LINE="$(autopr_title_marker "$DECISION_FILE") $PREFIX: $TITLE"

# ---- unautomatable: mark the card and reconcile an existing rework PR ----
if [ "$OUTCOME" = no_safe_action ]; then
    git reset --hard >/dev/null 2>&1
    # Both refusals a draft_pr directive can overturn must actively ask the
    # owner for that authorization. Without the prompt the card just reads as
    # a refusal, and the human has no visible way to say "do it anyway".
    NEEDS_CONTEXT_REQUEST=false
    case "$NO_SAFE_ACTION_REASON" in
        already_fixed|acceptance_criteria_met) NEEDS_CONTEXT_REQUEST=true ;;
    esac
    # A card whose criteria are already met is the one refusal a human must see
    # in full: the point is not "no PR", it is "here is where each thing you
    # asked for already lives" -- so the proof rides along with the ask.
    CONTEXT_REASON="$CARD_NOTE"
    if [ "$NO_SAFE_ACTION_REASON" = acceptance_criteria_met ]; then
        acceptance_evidence="$(autopr_render_acceptance_evidence "$DECISION_FILE")"
        [ -z "$acceptance_evidence" ] || CONTEXT_REASON="$CARD_NOTE"$'\n'"$acceptance_evidence"
    fi
    no_spec="[autopr:no-spec $(date -u +%Y-%m-%dT%H:%M:%SZ)] $NO_SAFE_ACTION_REASON"
    note_prefix="🤖 AUTO SETUP · $AUTO_SETUP_STATUS · build $PROD_BUILD_NUMBER · $PROD_LABEL"
    if [ "$MODE" = rework ]; then
        [ -n "$existing_open_pr" ] || die "rework no-safe-action has no open PR for $BRANCH"
        BODY_FILE="$(mktemp)"
        render_body "$BODY_FILE" "$consumed_comment_id" "$consumed_review_id"
        gh pr edit "$BRANCH" --repo "$REPO" --title "$TITLE_LINE" --body-file "$BODY_FILE"
        replace_triage_labels "$existing_open_pr"
        pr_url="${GITHUB_SERVER_URL:-https://github.com}/$REPO/pull/$existing_open_pr"
        origin_note="$(progress_note_with_origin \
            "$note_prefix · PR #$existing_open_pr · $CRITICALITY_EMOJI C$CONFIDENCE_SCORE$DIRECTIVE_MARKER · $no_spec · note: $CARD_NOTE" \
            "$EXISTING_PROGRESS_NOTE")"
        mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
            "$(jq -n --arg url "$pr_url" --argjson num "$existing_open_pr" --arg note "$origin_note" \
                '{pr_url: $url, pr_number: $num, board_column: "changes_requested", progress_note: $note}')" >/dev/null
        if [ "$NEEDS_CONTEXT_REQUEST" = true ]; then
            post_context_request "$CONTEXT_REASON" "$origin_note"
        fi
        post_reconsideration_reply "$existing_open_pr" "$origin_note"
        echo "Updated PR #$existing_open_pr and marked card $TASK_ID no-spec: $NO_SAFE_ACTION_REASON"
    else
        origin_note="$(progress_note_with_origin \
            "$note_prefix · $CRITICALITY_EMOJI C$CONFIDENCE_SCORE$DIRECTIVE_MARKER · $no_spec · note: $CARD_NOTE" \
            "$EXISTING_PROGRESS_NOTE")"
        mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
            "$(jq -n --arg note "$origin_note" '{progress_note: $note}')" >/dev/null
        if [ "$NEEDS_CONTEXT_REQUEST" = true ]; then
            post_context_request "$CONTEXT_REASON" "$origin_note"
        fi
        post_reconsideration_reply "" "$origin_note"
        echo "No diff produced; marked card $TASK_ID no-spec: $NO_SAFE_ACTION_REASON"
    fi
    exit 0
fi

# ---- code diff or an explicit questions-only draft: open/update the PR ----

if [ "$AWAITING_HUMAN" = true ] && [ -z "$existing_open_pr" ]; then
    max_awaiting="${MAX_OPEN_AWAITING_INPUT_PRS:-10}"
    open_awaiting="$(gh pr list --repo "$REPO" --state open --label autopr-awaiting-input --limit 100 --json number --jq 'length')"
    [ "$open_awaiting" -lt "$max_awaiting" ] \
        || die "awaiting-input draft cap reached ($open_awaiting/$max_awaiting)"
fi

if [ "$has_diff" = true ]; then
    git commit -m "$COMMIT_SUBJECT" >/dev/null
    git push --force-with-lease --set-upstream origin "$BRANCH"
elif [ -z "$existing_open_pr" ]; then
    # GitHub needs a head commit to host a draft with questions, but this empty
    # commit deliberately changes no product files.
    git commit --allow-empty -m "$COMMIT_SUBJECT" >/dev/null
    git push --force-with-lease --set-upstream origin "$BRANCH"
fi

BODY_FILE="$(mktemp)"
render_body "$BODY_FILE" "$consumed_comment_id" "$consumed_review_id"

if [ -n "$existing_open_pr" ]; then
    gh pr edit "$BRANCH" --repo "$REPO" --title "$TITLE_LINE" --body-file "$BODY_FILE"
    published_pr="$existing_open_pr"
else
    # Parse the number straight out of `gh pr create`'s own stdout URL
    # rather than a follow-up `gh pr list` — that second call can race the
    # first (list-consistency lag) and return empty, which previously
    # produced a pr_url ending in "/pull/" (still http(s)-shaped, so it
    # passed validation) and a null pr_number stored on the card.
    created_url="$(gh pr create --repo "$REPO" --draft --head "$BRANCH" --title "$TITLE_LINE" --body-file "$BODY_FILE")"
    published_pr="$(printf '%s' "$created_url" | grep -oE '[0-9]+$' || true)"
fi
[ -n "$published_pr" ] || die "could not determine the PR number for $BRANCH"

pr_url="${GITHUB_SERVER_URL:-https://github.com}/$REPO/pull/$published_pr"
card_column=in_progress
[ "$AWAITING_HUMAN" != true ] || card_column=changes_requested
origin_note="$(progress_note_with_origin \
    "🤖 AUTO SETUP · $AUTO_SETUP_STATUS · build $PROD_BUILD_NUMBER · $PROD_LABEL · PR #$published_pr · $CRITICALITY_EMOJI C$CONFIDENCE_SCORE$DIRECTIVE_MARKER · note: $CARD_NOTE" \
    "$EXISTING_PROGRESS_NOTE")"
if [ "$AWAITING_HUMAN" = true ]; then
    card_questions="$(autopr_render_card_questions "$DECISION_FILE")"
    [ -z "$card_questions" ] || origin_note="$origin_note

$card_questions"
fi
replace_triage_labels "$published_pr"
mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
    "$(jq -n --arg url "$pr_url" --argjson num "${published_pr:-null}" --arg col "$card_column" \
        --arg note "$origin_note" \
        '{pr_url: $url, pr_number: $num, board_column: $col, progress_note: $note}')" >/dev/null
if [ "$AWAITING_HUMAN" = true ]; then
    context_questions="$(jq -r '[.questions[]?.question] | join(" ")' "$DECISION_FILE")"
    post_context_request "$CARD_NOTE $context_questions You can attach a screenshot in your Espresso reply or on the ticket." "$origin_note"
fi
post_reconsideration_reply "$published_pr" "$origin_note"

echo "Published PR #$published_pr for task $TASK_ID ($MODE, $OUTCOME)"
