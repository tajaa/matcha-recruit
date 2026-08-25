#!/usr/bin/env bash
# Open/update one issue per exact marker; optionally close it on recovery.
set -euo pipefail

MARKER="${1:?usage: publish-issue.sh MARKER TITLE BODY_FILE LABEL [--recover]}"
TITLE="${2:?missing title}"
BODY_FILE="${3:?missing body file}"
LABEL="${4:?missing label}"
RECOVER="${5:-}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"

gh label create "$LABEL" --repo "$REPO" --color "B60205" \
    --description "Automated production monitoring" --force >/dev/null 2>&1 || true

issue_number="$(
    gh api --paginate --slurp "repos/$REPO/issues?state=open&per_page=100" \
        | jq -r --arg suffix "[$MARKER]" \
            '[.[][] | select(.pull_request == null) | select(.title | endswith($suffix))][0].number // empty'
)"

if [ "$RECOVER" = "--recover" ]; then
    if [ -n "$issue_number" ]; then
        gh issue comment "$issue_number" --repo "$REPO" --body-file "$BODY_FILE" >/dev/null
        gh issue close "$issue_number" --repo "$REPO" --reason completed >/dev/null
    fi
    exit 0
fi

if [ -n "$issue_number" ]; then
    gh issue comment "$issue_number" --repo "$REPO" --body-file "$BODY_FILE" >/dev/null
else
    gh issue create --repo "$REPO" --title "$TITLE [$MARKER]" --body-file "$BODY_FILE" \
        --label "$LABEL" >/dev/null
fi
