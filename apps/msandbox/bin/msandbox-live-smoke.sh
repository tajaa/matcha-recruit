#!/usr/bin/env bash
# Exercise the current PR through both the local test suites and a real,
# disposable msandbox session. This is an operator-run smoke test, not a CI
# test: it installs the controller from the current checkout and uses Docker.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PR_NUMBER="${MSANDBOX_LIVE_PR:-}"
KEEP_SESSION="${MSANDBOX_LIVE_KEEP_SESSION:-0}"
SKIP_INSTALL="${MSANDBOX_LIVE_SKIP_INSTALL:-0}"
SESSION_NAME=""
MSANDBOX_BIN="${MSANDBOX_BIN:-}"
SESSION_CREATED=0
FAILURES=0

say() {
    printf '\n==> %s\n' "$*"
}

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "required command is unavailable: $1"
}

run_check() {
    local title="$1"
    shift
    say "$title"
    if "$@"; then
        printf 'PASS: %s\n' "$title"
    else
        local status=$?
        printf 'FAIL: %s (exit %s)\n' "$title" "$status" >&2
        FAILURES=$((FAILURES + 1))
    fi
}

validate_session_schema() {
    python3 -m json.tool scripts/msandbox/schemas/session-v1.json >/dev/null
}

cleanup() {
    local status=$?
    trap - EXIT
    if [ "$SESSION_CREATED" -eq 1 ]; then
        "$MSANDBOX_BIN" session stop "$SESSION_NAME" >/dev/null 2>&1 || true
        if [ "$status" -eq 0 ] && [ "$KEEP_SESSION" != "1" ]; then
            say "Releasing disposable session $SESSION_NAME"
            if ! "$MSANDBOX_BIN" session release "$SESSION_NAME"; then
                printf 'WARNING: automatic release failed; session retained as %s\n' \
                    "$SESSION_NAME" >&2
                status=1
            fi
        else
            printf '\nSession %s was stopped and retained for inspection.\n' "$SESSION_NAME"
            printf 'Inspect: %s capabilities %s\n' "$MSANDBOX_BIN" "$SESSION_NAME"
            printf 'Release: %s session release %s\n' "$MSANDBOX_BIN" "$SESSION_NAME"
        fi
    fi
    exit "$status"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

cd "$REPO_ROOT"

require_command docker
require_command git
require_command gh
require_command python3

docker info >/dev/null 2>&1 || fail "Docker Desktop is not running or is inaccessible"
gh auth status --hostname github.com >/dev/null 2>&1 \
    || fail "GitHub CLI is not authenticated; run: gh auth login --hostname github.com"

if [ -z "$PR_NUMBER" ]; then
    PR_NUMBER="$(gh pr view --json number --jq .number 2>/dev/null)" \
        || fail "the current branch has no resolvable pull request; set MSANDBOX_LIVE_PR"
fi
case "$PR_NUMBER" in
    ''|*[!0-9]*) fail "MSANDBOX_LIVE_PR must be a numeric pull-request number" ;;
esac

SESSION_NAME="pr${PR_NUMBER}-live-$$"
printf 'PR: #%s\nSession: %s\nRepository: %s\n' \
    "$PR_NUMBER" "$SESSION_NAME" "$REPO_ROOT"

if [ -n "$(git status --porcelain)" ]; then
    printf 'NOTE: local changes are covered by the local checks; the disposable session uses the published PR head.\n'
fi

run_check "Python capability/session suite" \
    python3 -m pytest scripts/tests/test_msandbox_v2.py -q
run_check "Sandbox networking and mount contract" \
    bash scripts/tests/test_agent_sandbox_networking.sh
run_check "Attachment import boundary" \
    bash scripts/tests/test_msandbox_attachments.sh
run_check "Changed Python modules compile" \
    python3 -m py_compile \
        scripts/msandbox/agent_adapters.py \
        scripts/msandbox/capabilities.py \
        scripts/msandbox/cli.py \
        scripts/msandbox/docker_runtime.py \
        scripts/msandbox/install.py \
        scripts/msandbox/models.py \
        scripts/msandbox/sessions.py \
        scripts/msandbox/wizard.py
run_check "Session schema parses" \
    validate_session_schema
run_check "Shell entrypoints parse" \
    bash -n \
        scripts/agent-sandbox.sh \
        scripts/msandbox-live-smoke.sh \
        scripts/tests/test_agent_sandbox_networking.sh \
        scripts/tests/test_msandbox_attachments.sh \
        scripts/tests/test_msandbox_sessions.sh \
        scripts/tests/test_msandbox_worktrees.sh

if [ "$FAILURES" -ne 0 ]; then
    fail "$FAILURES local check(s) failed; live session was not created"
fi

if [ "$SKIP_INSTALL" != "1" ]; then
    say "Installing controller from the current checkout"
    "$REPO_ROOT/scripts/agent-sandbox.sh" install \
        || fail "controller installation failed"
fi

if [ -z "$MSANDBOX_BIN" ]; then
    MSANDBOX_BIN="$(command -v msandbox 2>/dev/null || true)"
fi
if [ -z "$MSANDBOX_BIN" ] && [ -n "${HOME:-}" ] && [ -x "${HOME}/.local/bin/msandbox" ]; then
    MSANDBOX_BIN="${HOME}/.local/bin/msandbox"
fi
[ -x "$MSANDBOX_BIN" ] || fail "installed msandbox launcher was not found"

say "Creating disposable no-agent session from PR #$PR_NUMBER"
"$MSANDBOX_BIN" session create "$SESSION_NAME" \
    --agent codex \
    --pr "$PR_NUMBER" \
    --no-start \
    --no-attach \
    || fail "session creation failed"
SESSION_CREATED=1

run_check "Measured doctor probe registry" \
    "$MSANDBOX_BIN" doctor "$SESSION_NAME"
run_check "Public capabilities command and refresh path" \
    "$MSANDBOX_BIN" capabilities "$SESSION_NAME" --refresh
run_check "Capability reports are private, valid, and nonempty" \
    "$MSANDBOX_BIN" session exec "$SESSION_NAME" -- sh -lc '
        set -eu
        json=/home/agent/.msandbox/capabilities.json
        markdown=/home/agent/.msandbox/capabilities.md
        test -s "$json"
        test -s "$markdown"
        test "$(stat -c %a "$json")" = 600
        test "$(stat -c %a "$markdown")" = 600
        python3 -m json.tool "$json" >/dev/null
    '
run_check "Container isolation boundary" \
    "$MSANDBOX_BIN" session exec "$SESSION_NAME" -- sh -lc '
        set -eu
        test ! -e /var/run/docker.sock
        test ! -e /workspace/secrets
        test ! -d /Users
        test -z "$(git -C /workspace status --porcelain)"
        echo isolation-ok
    '
run_check "Reproducible PR validation plan" \
    "$MSANDBOX_BIN" test "$SESSION_NAME" --pr

if [ "$FAILURES" -ne 0 ]; then
    fail "$FAILURES live check(s) failed"
fi

say "All local and live msandbox checks passed"
