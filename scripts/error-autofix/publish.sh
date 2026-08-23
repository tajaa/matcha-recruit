#!/usr/bin/env bash
# Stage the investigation's diff, guard it, and either open a draft PR (with
# a body assembled from the incident + report + verification table) or, if
# there is no diff, open/update a tracking issue instead.
#
# Usage: ./publish.sh incident.json report.md verification.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

INCIDENT_FILE="${1:?usage: publish.sh incident.json report.md verification.md}"
REPORT_FILE="${2:?usage: publish.sh incident.json report.md verification.md}"
VERIFICATION_FILE="${3:?usage: publish.sh incident.json report.md verification.md}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"

KEY="$(jq -r '.stable_key' "$INCIDENT_FILE")"
EXC="$(jq -r '.exception_type // "Error"' "$INCIDENT_FILE")"
PATH_="$(jq -r '.request_path // "unknown endpoint"' "$INCIDENT_FILE")"
METHOD="$(jq -r '.request_method // ""' "$INCIDENT_FILE")"
OCC="$(jq -r '.occurrences // 0' "$INCIDENT_FILE")"
LEVEL="$(jq -r '.level // "ERROR"' "$INCIDENT_FILE")"
SOURCE="$(jq -r '.source // "api"' "$INCIDENT_FILE")"
FIRST_SEEN="$(jq -r '.first_seen // ""' "$INCIDENT_FILE")"
LAST_SEEN="$(jq -r '.last_seen // ""' "$INCIDENT_FILE")"
ERROR_ID="$(jq -r '.error_id // ""' "$INCIDENT_FILE")"
REQUEST_ID="$(jq -r '.request_id // ""' "$INCIDENT_FILE")"
TRACEBACK="$(jq -r '.traceback // ""' "$INCIDENT_FILE")"

BRANCH="bot/err-$KEY"

cd "$REPO_ROOT"
git add --all

# Path guard: denylist stays exactly as it was in the original workflow —
# this is what stops the bot rewriting its own harness. The allowlist is new
# and strictly stronger: it closes every path the denylist didn't think to
# name (CLAUDE.md, docs/, client/, opencode.jsonc, .claude/, ...).
unsafe_paths="$(git diff --cached --no-renames --name-only | grep -E '(^\.github/|^deploy/|^scripts/|^server/alembic/|(^|/)\.env|(^|/)(package(-lock)?\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|Pipfile(\.lock)?|Dockerfile[^/]*|docker-compose[^/]*\.ya?ml)$)' || true)"
if [ -n "$unsafe_paths" ]; then
    echo "Refusing unsafe automated change:" >&2
    printf '%s\n' "$unsafe_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

disallowed_paths="$(git diff --cached --no-renames --name-only | grep -vE '^server/(app|tests)/.*\.py$' || true)"
if [ -n "$disallowed_paths" ]; then
    echo "Refusing change outside server/app or server/tests:" >&2
    printf '%s\n' "$disallowed_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

sev_for() {
    if [ "$LEVEL" = "CRITICAL" ] || [ "$OCC" -gt 50 ]; then
        echo high
    elif [ "$OCC" -ge 10 ]; then
        echo med
    else
        echo low
    fi
}
SEV="$(sev_for)"

ADMIN_LINK=""
[ -n "$ERROR_ID" ] && ADMIN_LINK="https://hey-matcha.com/admin/server-errors?search=$ERROR_ID"

# ---- no diff: track the incident as an issue instead of a silent no-op ----
if git diff --cached --quiet; then
    git reset --hard >/dev/null 2>&1
    # The key lives in the TITLE, not just an HTML comment in the body:
    # GitHub's issue search does not reliably full-text-match a body
    # comment (it's a code-search index, not a database LIKE), so a
    # marker-in-body search silently misses and opens a fresh issue every
    # run. A title substring match, checked client-side against the label's
    # issue list (never via `gh issue list --search`), is exact and
    # reliable. select.sh does the matching check before ever calling this
    # script, using the same "[$KEY]" convention.
    title="error: $EXC in $PATH_ [$KEY]"
    body="Investigated, but the model could not produce a safe fix from the
available evidence.

**Endpoint** \`$METHOD $PATH_\`
**Occurrences** $OCC · first seen $FIRST_SEEN · last seen $LAST_SEEN
**Source** $SOURCE · **Level** $LEVEL
$( [ -n "$ADMIN_LINK" ] && echo "**Admin** [$ERROR_ID]($ADMIN_LINK)" )

$(cat "$REPORT_FILE" 2>/dev/null || echo '_(no report file)_')

<details><summary>Traceback</summary>

\`\`\`
$TRACEBACK
\`\`\`
</details>"

    existing="$(gh issue list --repo "$REPO" --state open --label autofix-nofix --limit 100 \
        --json number,title --jq "map(select(.title | contains(\"[$KEY]\"))) | .[0].number // empty")"
    if [ -n "$existing" ]; then
        gh issue comment "$existing" --repo "$REPO" --body "$body" >/dev/null
    else
        gh issue create --repo "$REPO" --title "$title" --body "$body" --label autofix-nofix >/dev/null
    fi
    exit 0
fi

# ---- diff exists: open (or update) the PR ----
git config user.name "matcha-error-bot"
git config user.email "matcha-error-bot@users.noreply.github.com"
git commit -m "fix: $EXC in $PATH_" >/dev/null
git push --force-with-lease --set-upstream origin "$BRANCH"

NEW_FAILURES="${AUTOFIX_NEW_FAILURES:-0}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/$REPO/actions/runs/${GITHUB_RUN_ID:-}"

BODY_FILE="$(mktemp)"
{
    echo "<!-- autofix-key: $KEY -->"
    echo
    echo "## $EXC in $PATH_"
    echo
    echo "**Endpoint** \`$METHOD $PATH_\`"
    echo "**Occurrences** $OCC · first seen $FIRST_SEEN · last seen $LAST_SEEN"
    echo "**Source** $SOURCE · **Level** $LEVEL · **Fingerprint** \`$KEY\`"
    [ -n "$ADMIN_LINK" ] && echo "**Admin** [$ERROR_ID]($ADMIN_LINK)"
    echo
    cat "$REPORT_FILE"
    echo
    cat "$VERIFICATION_FILE"
    echo
    echo "<details><summary>Traceback</summary>"
    echo
    echo '```'
    printf '%s\n' "$TRACEBACK"
    echo '```'
    echo "</details>"
    if [ -n "$REQUEST_ID" ]; then
        echo
        echo "<details><summary>Correlated request id</summary>"
        echo
        echo "\`rid=$REQUEST_ID\`"
        echo "</details>"
    fi
    echo
    echo "_Investigated by [this workflow run]($RUN_URL)._"
} > "$BODY_FILE"

TITLE="fix: $EXC in $PATH_"

# `gh pr view <branch>` matches a PR for that head branch REGARDLESS of
# state — including one already merged or closed. select.sh's re-open path
# (a genuine recurrence after a merged fix, or a retry after a
# closed-unmerged cooldown) pushes new commits to this same branch name, so
# without an explicit state check this would silently `gh pr edit` the old,
# already-closed PR instead of creating a new one — the recurrence would
# never surface anywhere a human looks.
existing_open_pr="$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --limit 1 --json number --jq '.[0].number // empty')"
if [ -n "$existing_open_pr" ]; then
    gh pr edit "$BRANCH" --repo "$REPO" --title "$TITLE" --body-file "$BODY_FILE"
else
    gh pr create --repo "$REPO" --draft --head "$BRANCH" --title "$TITLE" --body-file "$BODY_FILE"
fi

gh pr edit "$BRANCH" --repo "$REPO" --add-label autofix >/dev/null 2>&1 || true
gh pr edit "$BRANCH" --repo "$REPO" --add-label "sev:$SEV" >/dev/null 2>&1 || true
if [ "$NEW_FAILURES" -gt 0 ] 2>/dev/null; then
    gh pr edit "$BRANCH" --repo "$REPO" --add-label needs-work >/dev/null 2>&1 || true
fi
