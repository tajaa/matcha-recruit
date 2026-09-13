#!/usr/bin/env bash
# Return the persistent self-hosted runner checkout to main after an AutoPR
# attempt. The remote bot/task-* branch is the durable PR workspace after
# publish; leaving it checked out makes later human/sandbox work ambiguous.
#
# Fail closed if anything is dirty. Cleanup must never erase model output or
# unrelated files merely to make the checkout look tidy.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

current="$(git branch --show-current)"
if [[ "$current" == bot/task-* ]]; then
    if [ -n "$(git status --short)" ]; then
        echo "Refusing to leave dirty AutoPR checkout $current; files were preserved." >&2
        exit 1
    fi
    git switch main >/dev/null
fi

git worktree prune
