#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AUDIT_FILE="${1:?usage: publish.sh AUDIT DECISION REPORT VERIFICATION}"
DECISION_FILE="${2:?usage: publish.sh AUDIT DECISION REPORT VERIFICATION}"
REPORT_FILE="${3:?usage: publish.sh AUDIT DECISION REPORT VERIFICATION}"
VERIFICATION_FILE="${4:?usage: publish.sh AUDIT DECISION REPORT VERIFICATION}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
FINGERPRINT="$(jq -r '.fingerprint' "$AUDIT_FILE")"
BRANCH="bot/autopr-audit-$FINGERPRINT"
OUTCOME="$(jq -r '.outcome' "$DECISION_FILE")"

cd "$REPO_ROOT"
git add --all
changed_paths="$(git diff --cached --name-only --no-renames)"
disallowed_paths="$(printf '%s\n' "$changed_paths" | grep -vE \
    '^(scripts/agent-sandbox\.sh|scripts/msandbox/.*|scripts/(kanban-autopr|error-autofix|autopr-scope)/[^/]+|scripts/tests/(test_msandbox_v2\.py|test_(agent_sandbox|msandbox_|kanban_autopr|error_autofix|autopr_)[^/]*\.(sh|py))|docker/agent-sandbox/[^/]+|docker-compose\.(sandbox|sandbox-session|sandbox-dev|sandbox-test|autopr-sandbox)\.yml|docs/ops/(AGENT_SANDBOX|MSANDBOX_SESSIONS|KANBAN_AUTOPR|SILENT_ERROR_AUTOFIX)\.md)$' || true)"
if printf '%s\n' "$changed_paths" | grep -qx 'scripts/tests/test_autopr_self_audit.sh'; then
    disallowed_paths="${disallowed_paths}${disallowed_paths:+$'\n'}scripts/tests/test_autopr_self_audit.sh"
fi
if [ -n "$disallowed_paths" ]; then
    echo "Self-audit repair touched a forbidden path:" >&2
    printf '%s\n' "$disallowed_paths" >&2
    git reset --hard >/dev/null 2>&1
    exit 1
fi

has_diff=false
git diff --cached --quiet || has_diff=true
if [ "$OUTCOME" = fix ]; then
    [ "$has_diff" = true ] || { echo "decision claimed a fix but produced no diff" >&2; exit 1; }
else
    [ "$has_diff" = false ] || {
        git reset --hard >/dev/null 2>&1
        echo "operator-action decision unexpectedly changed the repository" >&2
        exit 1
    }
    echo "No draft PR: the audit requires operator action or had no reproducible repository fix."
    exit 0
fi

git -c core.hooksPath=/dev/null \
    -c user.name=matcha-autopr-auditor \
    -c user.email=matcha-autopr-auditor@users.noreply.github.com \
    commit -m "fix: repair AutoPR audit $FINGERPRINT" >/dev/null
# Keep the repair checkout detached: the PR branch exists only on the remote,
# so neither this runner nor a developer worktree can retain branch ownership.
git -c core.hooksPath=/dev/null push --force-with-lease origin "HEAD:refs/heads/$BRANCH"

BODY_FILE="$(mktemp "${TMPDIR:-/tmp}/matcha-autopr-body.XXXXXX")"
trap 'rm -f "$BODY_FILE"' EXIT
{
    echo "<!-- matcha-autopr-self-audit: $FINGERPRINT -->"
    echo
    echo "## AutoPR self-audit repair"
    echo
    echo "Fingerprint: \`$FINGERPRINT\`"
    echo
    cat "$REPORT_FILE"
    echo
    cat "$VERIFICATION_FILE"
    echo
    echo "_Drafted inside the tracked-files-only msandbox repair lane._"
} > "$BODY_FILE"

existing="$(gh pr list --repo "$REPO" --head "$BRANCH" --state open --limit 1 --json number --jq '.[0].number // empty')"
if [ -n "$existing" ]; then
    gh pr edit "$existing" --repo "$REPO" --title "fix: repair AutoPR audit $FINGERPRINT" --body-file "$BODY_FILE"
else
    gh pr create --repo "$REPO" --draft --head "$BRANCH" \
        --title "fix: repair AutoPR audit $FINGERPRINT" --body-file "$BODY_FILE"
fi
gh pr edit "$BRANCH" --repo "$REPO" --add-label autopr-self-audit >/dev/null 2>&1 || true
