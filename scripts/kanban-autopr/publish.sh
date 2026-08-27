#!/usr/bin/env bash
# Stage the investigation's diff, guard it, and either open/update a draft PR
# or, if there is no diff, write a no-spec marker onto the card instead of
# opening a GitHub issue — the board is where this user works, not GitHub
# Issues.
#
# Usage: ./publish.sh card.json report.md verification.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

CARD_FILE="${1:?usage: publish.sh card.json report.md verification.md}"
REPORT_FILE="${2:?usage: publish.sh card.json report.md verification.md}"
VERIFICATION_FILE="${3:?usage: publish.sh card.json report.md verification.md}"
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
        's/^from auto setup( · build [^·]+)?( · prod( backend)? [^·]+( \/ frontend [^·]+)?)?( · PR #[0-9]+)?( · )?//')"
    if [ -n "$remainder" ] && [ "$remainder" != "$existing" ]; then
        printf '%s · %s' "$marker" "$remainder"
    elif [ -n "$existing" ] && [[ "$existing" != "from auto setup"* ]]; then
        printf '%s · %s' "$marker" "$existing"
    else
        printf '%s' "$marker"
    fi
}

BRANCH="bot/task-$ID8"

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

# ---- no diff: mark the card no-spec instead of opening a PR ----
if git diff --cached --quiet; then
    git reset --hard >/dev/null 2>&1
    reason="$(grep -A2 '### Confidence' "$REPORT_FILE" | tail -n +2 | head -1 | sed 's/^[[:space:]]*//' | cut -c1-200)"
    [ -n "$reason" ] || reason="no safe fix produced"
    note="from auto setup · build $PROD_BUILD_NUMBER · $PROD_LABEL · [autopr:no-spec $(date -u +%Y-%m-%dT%H:%M:%SZ)] $reason"
    mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
        "$(jq -n --arg note "$note" '{progress_note: $note}')" >/dev/null
    echo "No diff produced; marked card $TASK_ID no-spec: $reason"
    exit 0
fi

# ---- diff exists: open (or update) the PR ----
git config user.name "matcha-kanban-autopr"
git config user.email "matcha-kanban-autopr@users.noreply.github.com"
git commit -m "$PREFIX: $TITLE" >/dev/null
git push --force-with-lease --set-upstream origin "$BRANCH"

NEW_FAILURES="${AUTOFIX_NEW_FAILURES:-0}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/$REPO/actions/runs/${GITHUB_RUN_ID:-}"

BODY_FILE="$(mktemp)"
{
    echo "<!-- matcha-task: $TASK_ID -->"
    echo "<!-- matcha-project: $PROJECT_ID -->"
    echo "<!-- matcha-production-build: $PROD_BUILD_NUMBER -->"
    echo "<!-- matcha-production-backend-sha: $PROD_BACKEND_SHA -->"
    echo "<!-- matcha-production-frontend-sha: $PROD_FRONTEND_SHA -->"
    echo
    echo "## $TITLE"
    [ -n "$PROJECT_TITLE" ] && echo "**Board** $PROJECT_TITLE"
    echo "**Production baseline** build $PROD_BUILD_NUMBER · $PROD_LABEL"
    echo
    if [ -n "$DESCRIPTION" ]; then
        echo "$DESCRIPTION"
        echo
    fi
    cat "$REPORT_FILE"
    echo
    cat "$VERIFICATION_FILE"
    echo
    echo "_Built by [this workflow run]($RUN_URL)._"
} > "$BODY_FILE"

TITLE_LINE="$PREFIX: $TITLE"

existing_open_pr="$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --limit 1 --json number --jq '.[0].number // empty')"
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

gh pr edit "$BRANCH" --repo "$REPO" --add-label autopr >/dev/null 2>&1 || true
if [ "$MODE" = rework ]; then
    gh pr edit "$BRANCH" --repo "$REPO" --add-label autopr-rework >/dev/null 2>&1 || true
fi
if [ "$NEW_FAILURES" -gt 0 ] 2>/dev/null; then
    gh pr edit "$BRANCH" --repo "$REPO" --add-label needs-work >/dev/null 2>&1 || true
fi

pr_url="${GITHUB_SERVER_URL:-https://github.com}/$REPO/pull/$published_pr"
origin_note="$(progress_note_with_origin \
    "from auto setup · build $PROD_BUILD_NUMBER · $PROD_LABEL · PR #$published_pr" \
    "$EXISTING_PROGRESS_NOTE")"
mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
    "$(jq -n --arg url "$pr_url" --argjson num "${published_pr:-null}" --arg col "in_progress" \
        --arg note "$origin_note" \
        '{pr_url: $url, pr_number: $num, board_column: $col, progress_note: $note}')" >/dev/null

echo "Published PR #$published_pr for task $TASK_ID ($MODE)"
