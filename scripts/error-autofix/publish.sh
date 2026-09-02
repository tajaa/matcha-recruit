#!/usr/bin/env bash
# Stage the investigation's diff, guard it, and either open a draft PR (with
# a body assembled from the incident + report + verification table) or, if
# there is no diff, open/update a tracking issue instead.
#
# Usage: ./publish.sh incident.json decision.json report.md verification.md [commit-subject.json]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"
# shellcheck source=./decision.sh
source "$SCRIPT_DIR/decision.sh"

INCIDENT_FILE="${1:?usage: publish.sh incident.json decision.json report.md verification.md}"
DECISION_FILE="${2:?usage: publish.sh incident.json decision.json report.md verification.md}"
REPORT_FILE="${3:?usage: publish.sh incident.json decision.json report.md verification.md}"
VERIFICATION_FILE="${4:?usage: publish.sh incident.json decision.json report.md verification.md}"
COMMIT_SUBJECT_FILE="${5:-}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"

KEY="$(jq -r '.stable_key' "$INCIDENT_FILE")"
EXC="$(jq -r '.exception_type // "Error"' "$INCIDENT_FILE")"
PATH_="$(jq -r '.request_path // "unknown endpoint"' "$INCIDENT_FILE")"
METHOD="$(jq -r '.request_method // ""' "$INCIDENT_FILE")"
OCC="$(jq -r '.occurrences // 0' "$INCIDENT_FILE")"
LEVEL="$(jq -r '.level // "ERROR"' "$INCIDENT_FILE")"
SOURCE="$(jq -r '.source // "api"' "$INCIDENT_FILE")"
SURFACE="$(jq -r '.surface // "server"' "$INCIDENT_FILE")"
FIRST_SEEN="$(jq -r '.first_seen // ""' "$INCIDENT_FILE")"
LAST_SEEN="$(jq -r '.last_seen // ""' "$INCIDENT_FILE")"
ERROR_ID="$(jq -r '.error_id // ""' "$INCIDENT_FILE")"
REQUEST_ID="$(jq -r '.request_id // ""' "$INCIDENT_FILE")"
TRACEBACK="$(jq -r '.traceback // ""' "$INCIDENT_FILE")"
SAFE_CHANGES="$(jq -r '.safe_changes_present' "$DECISION_FILE")"
CRITICALITY="$(jq -r '.criticality.level' "$DECISION_FILE")"
CONFIDENCE_SCORE="$(jq -r '.confidence_score' "$DECISION_FILE")"
CONFIDENCE_BAND="$(jq -r '.confidence_band' "$DECISION_FILE")"
CRITICALITY_EMOJI="$(error_criticality_emoji "$CRITICALITY")"

BRANCH="bot/err-$KEY"

cd "$REPO_ROOT"
git add --all

# Path guard: denylist stays exactly as it was in the original workflow —
# this is what stops the bot rewriting its own harness. The allowlist is new
# and strictly stronger: it closes every path the denylist didn't think to
# name (CLAUDE.md, docs/, client/, opencode.jsonc, .claude/, ...).
unsafe_paths="$(git diff --cached --no-renames --name-only | grep -E '(^\.github/|^deploy/|^scripts/|^server/alembic/|^client/src/generated/|^client/src/api/errorReporter\.ts$|^client/src/components/shared/ErrorBoundary\.tsx$|^server/app/core/routes/telemetry/|^server/app/core/services/error_reporter\.py$|^server/app/core/services/error_notifier\.py$|(^|/)\.env|(^|/)(package(-lock)?\.json|npm-shrinkwrap\.json|pnpm-lock\.yaml|yarn\.lock|requirements[^/]*\.txt|pyproject\.toml|poetry\.lock|Pipfile(\.lock)?|Dockerfile[^/]*|docker-compose[^/]*\.ya?ml)$)' || true)"
if [ -n "$unsafe_paths" ]; then
    echo "Refusing unsafe automated change:" >&2
    printf '%s\n' "$unsafe_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

disallowed_paths="$(git diff --cached --no-renames --name-only | grep -vE '^(server/(app|tests)/.*\.py|client/src/.*\.(ts|tsx))$' || true)"
if [ -n "$disallowed_paths" ]; then
    echo "Refusing change outside server/app, server/tests, or client/src:" >&2
    printf '%s\n' "$disallowed_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

# `client.ts` is generally safe to fix, but the report-status policy inside it
# is a telemetry suppression boundary and must not be changed by this bot.
# Scoped to: touching the `_EXPECTED_STATUSES` set or the `_shouldReportStatus`
# definition (its one-line body also references `_EXPECTED_STATUSES`, so that
# half of the pattern already covers it), or deleting an existing
# `reportApiError(` call site. Deliberately NOT matched: a call to
# `_shouldReportStatus(...)` or a newly added `reportApiError(...)` call —
# those are legitimate fix shapes (e.g. editing the retry block) and used to
# trip this guard on any mention of the identifiers, discarding real work.
unsafe_reporting_change="$(git diff --cached -U0 -- client/src/api/client.ts | grep -E '^[+-].*(_EXPECTED_STATUSES|function _shouldReportStatus)|^-.*reportApiError\(' || true)"
if [ -n "$unsafe_reporting_change" ]; then
    echo "Refusing automated change to browser error-reporting policy:" >&2
    printf '%s\n' "$unsafe_reporting_change" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

# The model's decision and its patch must agree. Treat disagreement as an
# incomplete investigation, not as a no-fix issue or a reviewable PR.
if git diff --cached --quiet; then
    [ "$SAFE_CHANGES" = false ] \
        || die "triage claimed a safe fix but produced no code diff"
else
    if [ "$SAFE_CHANGES" != true ]; then
        git reset --hard >/dev/null 2>&1
        die "triage claimed no safe fix but changed the working tree"
    fi
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
if [ -n "$ERROR_ID" ]; then
    if [ "$SURFACE" = "client" ]; then
        ADMIN_LINK="https://hey-matcha.com/admin/client-errors"
    else
        ADMIN_LINK="https://hey-matcha.com/admin/server-errors?search=$ERROR_ID"
    fi
fi

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
**Triage** $CRITICALITY_EMOJI $CRITICALITY · confidence $CONFIDENCE_SCORE/100 ($CONFIDENCE_BAND)
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
        body_file="$(mktemp)"
        printf '%s\n' "$body" > "$body_file"
        gh issue edit "$existing" --repo "$REPO" --body-file "$body_file" >/dev/null
        rm -f "$body_file"
    else
        gh issue create --repo "$REPO" --title "$title" --body "$body" --label autofix-nofix >/dev/null
    fi
    exit 0
fi

# ---- diff exists: open (or update) the PR ----
[ -n "$COMMIT_SUBJECT_FILE" ] && [ -s "$COMMIT_SUBJECT_FILE" ] \
    || die "safe fix is missing its Luna commit subject"
COMMIT_SUBJECT="$(jq -er '.commit_subject | select(type == "string")' "$COMMIT_SUBJECT_FILE")" \
    || die "commit subject output is invalid"
[[ "$COMMIT_SUBJECT" == fix:\ * && "$COMMIT_SUBJECT" != *$'\n'* && "$COMMIT_SUBJECT" != *$'\r'* ]] \
    || die "commit subject must be one line starting with fix:"
[ "${#COMMIT_SUBJECT}" -le 72 ] || die "commit subject exceeds 72 characters"
git config user.name "matcha-error-bot"
git config user.email "matcha-error-bot@users.noreply.github.com"
git commit -m "$COMMIT_SUBJECT" >/dev/null
git push --force-with-lease --set-upstream origin "$BRANCH"

NEW_FAILURES="${AUTOFIX_NEW_FAILURES:-0}"
RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/$REPO/actions/runs/${GITHUB_RUN_ID:-}"

BODY_FILE="$(mktemp)"
{
    echo "<!-- autofix-key: $KEY -->"
    echo "<!-- matcha-autofix-notify-review: $KEY -->"
    echo "<!-- matcha-autopr-criticality: $CRITICALITY -->"
    echo "<!-- matcha-autopr-confidence-score: $CONFIDENCE_SCORE -->"
    echo
    echo "## $EXC in $PATH_"
    echo
    echo "**Endpoint** \`$METHOD $PATH_\`"
    echo "**Occurrences** $OCC · first seen $FIRST_SEEN · last seen $LAST_SEEN"
    echo "**Source** $SOURCE · **Level** $LEVEL · **Fingerprint** \`$KEY\`"
    echo "**Triage** $CRITICALITY_EMOJI $CRITICALITY · confidence $CONFIDENCE_SCORE/100 ($CONFIDENCE_BAND)"
    [ -n "$ADMIN_LINK" ] && echo "**Admin** [$ERROR_ID]($ADMIN_LINK)"
    echo
    cat "$REPORT_FILE"
    context_excerpt="$(jq -r '.context_excerpt // empty' "$INCIDENT_FILE")"
    if [ -n "$context_excerpt" ]; then
        echo
        echo "<details><summary>Client context</summary>"
        echo
        echo '```'
        printf '%s\n' "$context_excerpt"
        echo '```'
        echo "</details>"
    fi
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

TITLE="$CRITICALITY_EMOJI [C$CONFIDENCE_SCORE] fix: $EXC in $PATH_"

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
    published_pr="$existing_open_pr"
else
    gh pr create --repo "$REPO" --draft --head "$BRANCH" --title "$TITLE" --body-file "$BODY_FILE"
    published_pr="$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --limit 1 --json number --jq '.[0].number // empty')"
fi

gh pr edit "$BRANCH" --repo "$REPO" --add-label autofix >/dev/null 2>&1 || true
gh pr edit "$BRANCH" --repo "$REPO" --add-label "sev:$SEV" >/dev/null 2>&1 || true
gh pr edit "$BRANCH" --repo "$REPO" --add-label "criticality:$CRITICALITY" >/dev/null 2>&1 || true
gh pr edit "$BRANCH" --repo "$REPO" --add-label "confidence:$CONFIDENCE_BAND" >/dev/null 2>&1 || true
if [ "${AUTOPR_POSSIBLE_DUPLICATE:-0}" = 1 ]; then
    gh pr edit "$BRANCH" --repo "$REPO" --add-label possible-duplicate >/dev/null 2>&1 || true
fi
if [ "$NEW_FAILURES" -gt 0 ] 2>/dev/null; then
    gh pr edit "$BRANCH" --repo "$REPO" --add-label needs-work >/dev/null 2>&1 || true
fi

# A prior no-fix issue can be provisional (for example when the model process
# crashed). Once a reviewable draft exists, the PR is the durable record.
existing_nofix="$(gh issue list --repo "$REPO" --state open --label autofix-nofix --limit 100 \
    --json number,title --jq "map(select(.title | contains(\"[$KEY]\"))) | .[0].number // empty")"
if [ -n "$existing_nofix" ]; then
    gh issue close "$existing_nofix" --repo "$REPO" \
        --comment "Superseded by draft PR #${published_pr:-unknown} for incident [$KEY]." >/dev/null
fi
