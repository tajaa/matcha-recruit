#!/usr/bin/env bash
# Stage the investigation's diff, guard it, and either open/update a draft PR
# or publish a question draft when the card needs a human answer. The board is
# where this user works, not GitHub Issues.
#
# Usage: ./publish.sh card.json decision.json report.md verification.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"
# shellcheck source=./decision.sh
source "$SCRIPT_DIR/decision.sh"

CARD_FILE="${1:?usage: publish.sh card.json decision.json report.md verification.md}"
DECISION_FILE="${2:?usage: publish.sh card.json decision.json report.md verification.md}"
REPORT_FILE="${3:?usage: publish.sh card.json decision.json report.md verification.md}"
VERIFICATION_FILE="${4:?usage: publish.sh card.json decision.json report.md verification.md}"
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
OUTCOME="$(jq -r '.outcome' "$DECISION_FILE")"
CONFIDENCE_SCORE="$(jq -r '.confidence_score' "$DECISION_FILE")"
CONFIDENCE_BAND="$(jq -r '.confidence_band' "$DECISION_FILE")"
CRITICALITY="$(jq -r '.criticality.level' "$DECISION_FILE")"
CRITICALITY_EMOJI="$(autopr_criticality_emoji "$CRITICALITY")"
AWAITING_HUMAN="$(jq -r '.awaiting_human' "$DECISION_FILE")"

[ -n "$PROD_BUILD_NUMBER" ] || die "card context is missing the production build number"
[ -n "$PROD_BACKEND_SHA" ] || die "card context is missing the production backend SHA"
[ -n "$PROD_FRONTEND_SHA" ] || die "card context is missing the production frontend SHA"

if [ "$PROD_BACKEND_SHA" = "$PROD_FRONTEND_SHA" ]; then
    PROD_LABEL="prod $PROD_BACKEND_SHA"
else
    PROD_LABEL="prod backend $PROD_BACKEND_SHA / frontend $PROD_FRONTEND_SHA"
fi

progress_note_with_origin() {
    local marker="$1" existing="$2" remainder
    # Replace this system's prior structured prefix on rework instead of
    # nesting it every round. Preserve any human-authored text after it.
    remainder="$(printf '%s' "$existing" | sed -E \
        's/^from auto setup( · build [^·]+)?( · prod( backend)? [^·]+( \/ frontend [^·]+)?)?( · PR #[0-9]+)?( · [^·]+ C[0-9]+ · (awaiting answers|ready for review))?( · )?//')"
    if [ -n "$remainder" ] && [ "$remainder" != "$existing" ]; then
        printf '%s · %s' "$marker" "$remainder"
    elif [ -n "$existing" ] && [[ "$existing" != "from auto setup"* ]]; then
        printf '%s · %s' "$marker" "$existing"
    else
        printf '%s' "$marker"
    fi
}

BRANCH="bot/task-$ID8"

feedback_snapshot() {
    local pr_number="$1"
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
        echo "_Built by [this workflow run]($RUN_URL)._"
    } > "$output_file"
}

replace_triage_labels() {
    local branch="$1"
    local old
    for old in criticality:red criticality:orange criticality:yellow confidence:high confidence:medium confidence:low autopr-awaiting-input; do
        gh pr edit "$branch" --repo "$REPO" --remove-label "$old" >/dev/null 2>&1 || true
    done
    gh pr edit "$branch" --repo "$REPO" --add-label autopr >/dev/null 2>&1 || true
    [ "$MODE" != rework ] || gh pr edit "$branch" --repo "$REPO" --add-label autopr-rework >/dev/null 2>&1 || true
    gh pr edit "$branch" --repo "$REPO" --add-label "criticality:$CRITICALITY" --add-label "confidence:$CONFIDENCE_BAND" >/dev/null 2>&1 || true
    [ "$AWAITING_HUMAN" != true ] || gh pr edit "$branch" --repo "$REPO" --add-label autopr-awaiting-input >/dev/null 2>&1 || true
}

cd "$REPO_ROOT"
git add --all

# Path guard: denylist is what stops the bot rewriting its own harness or
# CI. The allowlist is strictly stronger — it closes every path the denylist
# didn't think to name. A card that genuinely needs a migration or infra
# change cannot be auto-PR'd; that is the correct conservative outcome, and
# the no-spec path below says so on the card.
unsafe_paths="$(git diff --cached --no-renames --name-only | grep -E '(^\.github/|^deploy/|^scripts/|^server/alembic/|^client/src/generated/|(^|/)\.env|(^|/)(package(-lock)?\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|Pipfile(\.lock)?|Dockerfile[^/]*|docker-compose[^/]*\.ya?ml)$)' || true)"
if [ -n "$unsafe_paths" ]; then
    echo "Refusing unsafe automated change:" >&2
    printf '%s\n' "$unsafe_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

disallowed_paths="$(git diff --cached --no-renames --name-only | grep -vE '^(server/(app|tests)/.*\.py|client/src/.*\.(ts|tsx)|platforms/desktop/Espresso/Espresso/.*\.swift)$' || true)"
if [ -n "$disallowed_paths" ]; then
    echo "Refusing change outside server/app, server/tests, client/src, or Espresso source:" >&2
    printf '%s\n' "$disallowed_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
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

# The decision must agree with the actual working tree. Do not turn a model
# mismatch into a permanent no-spec marker, and never publish product changes
# beside a questions-only draft.
has_diff=false
git diff --cached --quiet || has_diff=true
case "$OUTCOME" in
    implementation|partial_implementation)
        [ "$has_diff" = true ] || die "decision says safe changes exist but the worktree is empty"
        ;;
    questions_only|no_safe_action)
        if [ "$has_diff" = true ]; then
            git reset --hard >/dev/null 2>&1
            die "decision forbids product changes but the worktree contains a diff"
        fi
        ;;
    *) die "unknown triage outcome: $OUTCOME" ;;
esac

# ---- unautomatable: visible no-spec card marker, no PR ----
if [ "$OUTCOME" = no_safe_action ]; then
    git reset --hard >/dev/null 2>&1
    reason="$(jq -r '.no_safe_action_reason' "$DECISION_FILE")"
    note="from auto setup · build $PROD_BUILD_NUMBER · $PROD_LABEL · [autopr:no-spec $(date -u +%Y-%m-%dT%H:%M:%SZ)] $reason"
    mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
        "$(jq -n --arg note "$note" '{progress_note: $note}')" >/dev/null
    echo "No diff produced; marked card $TASK_ID no-spec: $reason"
    exit 0
fi

# ---- code diff or an explicit questions-only draft: open/update the PR ----
git config user.name "matcha-kanban-autopr"
git config user.email "matcha-kanban-autopr@users.noreply.github.com"

existing_open_json="$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --limit 1 --json number,body)"
existing_open_pr="$(printf '%s' "$existing_open_json" | jq -r '.[0].number // empty')"
existing_body="$(printf '%s' "$existing_open_json" | jq -r '.[0].body // ""')"

if [ "$AWAITING_HUMAN" = true ] && [ -z "$existing_open_pr" ]; then
    max_awaiting="${MAX_OPEN_AWAITING_INPUT_PRS:-10}"
    open_awaiting="$(gh pr list --repo "$REPO" --state open --label autopr-awaiting-input --limit 100 --json number --jq 'length')"
    [ "$open_awaiting" -lt "$max_awaiting" ] \
        || die "awaiting-input draft cap reached ($open_awaiting/$max_awaiting)"
fi

if [ "$has_diff" = true ]; then
    git commit -m "$PREFIX: $TITLE" >/dev/null
    git push --force-with-lease --set-upstream origin "$BRANCH"
elif [ -z "$existing_open_pr" ]; then
    # GitHub needs a head commit to host a draft with questions, but this empty
    # commit deliberately changes no product files.
    git commit --allow-empty -m "$PREFIX: $TITLE (questions)" >/dev/null
    git push --force-with-lease --set-upstream origin "$BRANCH"
fi

NEW_FAILURES="${AUTOFIX_NEW_FAILURES:-0}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/$REPO/actions/runs/${GITHUB_RUN_ID:-}"

BODY_FILE="$(mktemp)"
old_comment_id="$(existing_feedback_checkpoint "$existing_body" comment)"
old_review_id="$(existing_feedback_checkpoint "$existing_body" review)"
render_body "$BODY_FILE" "$old_comment_id" "$old_review_id"

TITLE_LINE="$(autopr_title_marker "$DECISION_FILE") $PREFIX: $TITLE"

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
note_state="ready for review"
[ "$AWAITING_HUMAN" != true ] || { card_column=changes_requested; note_state="awaiting answers"; }
origin_note="$(progress_note_with_origin \
    "from auto setup · build $PROD_BUILD_NUMBER · $PROD_LABEL · PR #$published_pr · $CRITICALITY_EMOJI C$CONFIDENCE_SCORE · $note_state" \
    "$EXISTING_PROGRESS_NOTE")"
mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
    "$(jq -n --arg url "$pr_url" --argjson num "${published_pr:-null}" --arg col "$card_column" \
        --arg note "$origin_note" \
        '{pr_url: $url, pr_number: $num, board_column: $col, progress_note: $note}')" >/dev/null

# Commit the feedback checkpoint only after the PR and card are both updated.
# If an earlier operation fails, select.sh sees the old checkpoint and retries
# the human answer instead of silently dropping it.
if [ "$AWAITING_HUMAN" = true ]; then
    snapshot="$(feedback_snapshot "$published_pr")"
    new_comment_id="$(printf '%s' "$snapshot" | jq -r '.comment_id // ""')"
    new_review_id="$(printf '%s' "$snapshot" | jq -r '.review_id // ""')"
    render_body "$BODY_FILE" "$new_comment_id" "$new_review_id"
    gh pr edit "$BRANCH" --repo "$REPO" --title "$TITLE_LINE" --body-file "$BODY_FILE"
fi

replace_triage_labels "$BRANCH"
if [ "$NEW_FAILURES" -gt 0 ] 2>/dev/null; then
    gh pr edit "$BRANCH" --repo "$REPO" --add-label needs-work >/dev/null 2>&1 || true
fi

echo "Published PR #$published_pr for task $TASK_ID ($MODE, $OUTCOME)"
