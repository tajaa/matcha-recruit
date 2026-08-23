#!/usr/bin/env bash
# Run the same checks against `main` (at $AUTOFIX_BASE_SHA) and the current
# branch, diff FAILING TEST NODE IDS (not counts), and emit a markdown table.
# A failure present in both trees is annotated pre-existing and never counted
# against the PR.
#
# Usage: (from repo root, on the fix branch, with the fix committed)
#   AUTOFIX_BASE_SHA=<sha captured before investigate.sh ran> \
#     ./scripts/error-autofix/verify.sh > verification.md
# Always exits 0. Sets AUTOFIX_NEW_FAILURES in $GITHUB_ENV when running in CI.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
CACHE_DIR="${AUTOFIX_CACHE_DIR:-$HOME/.cache/matcha-autofix}"
PY312="${PY312:-/opt/homebrew/bin/python3.12}"
mkdir -p "$CACHE_DIR"

# `AUTOFIX_BASE_SHA` must be captured by the workflow BEFORE investigate.sh
# runs (right after `git switch -C`), not re-derived here — by the time
# verify.sh runs, "main" may have moved if something merged mid-run, and a
# baseline that silently includes unrelated changes makes the table lie.
BASE_SHA="${AUTOFIX_BASE_SHA:-$(git -C "$REPO_ROOT" merge-base HEAD main 2>/dev/null || git -C "$REPO_ROOT" rev-parse main)}"

# ---- fake, harmless settings so app.config can load in a fresh checkout ---
# There is no .env in a fresh actions/checkout workspace, and load_settings()
# hard-raises without LIVE_API/DATABASE_URL. These must be identical in both
# trees and must never resemble prod.
export LIVE_API="${LIVE_API:-autofix-verify-not-a-real-key}"
export DATABASE_URL="${AUTOFIX_VERIFY_DATABASE_URL:-postgresql://verify:verify@127.0.0.1:5432/verify_never_connects}"
export DATABASE_SSL=disable
export ENV=test
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-autofix-verify-not-a-real-secret}"
case "$DATABASE_URL" in
    *rds.amazonaws.com*|*matcha-prod*) echo "refusing to run verify.sh against a prod-shaped DATABASE_URL" >&2; exit 1 ;;
esac
case "$ENV" in
    prod|production) echo "refusing to run verify.sh with ENV=$ENV" >&2; exit 1 ;;
esac

# ---- test-dir mapping -------------------------------------------------
# server/tests/<name>/ mirrors both routes/<name>/ and services/<name>/. For
# each changed file, try its parent directory name and its own stem, plus
# any test file that imports the changed module directly (catches the
# _shared.py case, where only sibling route modules import it and directory
# mirroring alone finds nothing).
WIDE_TRIGGERS='^server/app/(main|config|protocol)\.py$|^server/app/database/|^server/app/orm/|^server/app/core/(dependencies|request_context)\.py$'

map_test_dirs() {
    local f dirs=() mod
    for f in "$@"; do
        [[ "$f" == server/app/* ]] || continue
        if [[ "$f" =~ $WIDE_TRIGGERS ]]; then
            echo "server/tests"
            return
        fi
        local parent stem
        parent="$(basename "$(dirname "$f")")"
        stem="$(basename "$f" .py)"
        for name in "$parent" "$stem"; do
            [ -d "$REPO_ROOT/server/tests/$name" ] && dirs+=("server/tests/$name")
        done
        mod="$(echo "${f#server/}" | sed 's/\.py$//; s#/#.#g')"
        while IFS= read -r hit; do
            [ -n "$hit" ] && dirs+=("$(dirname "$hit")")
        done < <(grep -rlF "$mod" "$REPO_ROOT/server/tests" 2>/dev/null | sed "s#^$REPO_ROOT/##")
    done
    printf '%s\n' "${dirs[@]+"${dirs[@]}"}" | sort -u
}

# investigate.sh commits nothing and stages nothing (it edits the working
# tree only — see its own docstring), so at the point this runs (workflow
# order is investigate -> verify -> publish, publish does the commit) BOTH
# the committed-vs-base diff AND the staged diff are empty. Without the
# plain worktree-diff fallback, this always fell through to "no changed
# files" -> "no matching test directory" -> a green-looking table that
# tested nothing, on every single PR.
CHANGED_FILES=($(git -C "$REPO_ROOT" diff --name-only "$BASE_SHA"...HEAD 2>/dev/null || true))
if [ "${#CHANGED_FILES[@]}" -eq 0 ]; then
    CHANGED_FILES=($(git -C "$REPO_ROOT" diff --cached --name-only 2>/dev/null || true))
fi
if [ "${#CHANGED_FILES[@]}" -eq 0 ]; then
    CHANGED_FILES=($(git -C "$REPO_ROOT" diff --name-only 2>/dev/null || true))
fi

TEST_DIRS=($(map_test_dirs "${CHANGED_FILES[@]+"${CHANGED_FILES[@]}"}"))

CLIENT_CHANGED=false
for f in "${CHANGED_FILES[@]+"${CHANGED_FILES[@]}"}"; do
    [[ "$f" == client/* ]] && CLIENT_CHANGED=true && break
done

# ---- interpreter selection ---------------------------------------------
# Prefer the repo's own dev venv as an interpreter rather than building a
# fresh one: requirements.txt pins with `>=`, so hashing it doesn't actually
# pin anything, and neither pytest nor pytest-asyncio are in it at all. The
# venv resolves site-packages from its own prefix regardless of cwd, so
# pointing it at the workspace's server/ tree (rather than this dev clone)
# picks up the branch's code, not the dev clone's.
DEV_VENV_PY="${AUTOFIX_DEV_VENV_PY:-$HOME/Documents/github/matcha/server/venv/bin/python}"
VENV_PY=""
BOOTSTRAP_OK=false

if [ -x "$DEV_VENV_PY" ] && "$DEV_VENV_PY" -c "import pytest, pytest_asyncio" >/dev/null 2>&1; then
    VENV_PY="$DEV_VENV_PY"
    BOOTSTRAP_OK=true
else
    # Fallback: a cached, manually-provisioned venv. NOT built on the fly —
    # a `pip install` that then fails on a native extension (xmlsec,
    # pymupdf) can eat the whole job's timeout for nothing. If it's missing
    # or stale, verification reports UNAVAILABLE rather than guessing.
    REQ_HASH="$(shasum -a 256 "$REPO_ROOT/server/requirements.txt" | cut -c1-12)"
    CACHED_VENV="$CACHE_DIR/venv-py312-$REQ_HASH"
    if [ -x "$CACHED_VENV/bin/python" ] && "$CACHED_VENV/bin/python" -c "import pytest, pytest_asyncio" >/dev/null 2>&1; then
        VENV_PY="$CACHED_VENV/bin/python"
        BOOTSTRAP_OK=true
    fi
fi

if [ "$BOOTSTRAP_OK" != true ]; then
    cat <<EOF
### Verification

**Checks did not run** — no usable Python interpreter with pytest was found
(looked for the dev venv at \`$DEV_VENV_PY\` and a cached venv keyed on
\`server/requirements.txt\`). This PR has not been verified. Review the diff
manually before merging.

To provision the cached venv once by hand:
\`\`\`
/opt/homebrew/bin/python3.12 -m venv $CACHE_DIR/venv-py312-<hash>
$CACHE_DIR/venv-py312-<hash>/bin/pip install -r server/requirements.txt pytest pytest-asyncio
\`\`\`
EOF
    echo "AUTOFIX_NEW_FAILURES=0" >> "${GITHUB_ENV:-/dev/null}" 2>/dev/null || true
    exit 0
fi

# ---- run one suite in one tree, emit sorted failing node ids -----------
run_suite() {
    local tree="$1" outfile="$2"
    if [ "${#TEST_DIRS[@]}" -eq 0 ]; then
        : > "$outfile"
        return
    fi
    (
        cd "$tree" && "$VENV_PY" -m pytest "${TEST_DIRS[@]}" \
            -q --tb=no -rf -p no:cacheprovider --continue-on-collection-errors
    ) 2>/dev/null | grep '^FAILED ' | sed 's/^FAILED //' | cut -d' ' -f1 | sort > "$outfile"
}

compileall_check() {
    local tree="$1" changed_py=() f
    for f in "${CHANGED_FILES[@]+"${CHANGED_FILES[@]}"}"; do
        [[ "$f" == *.py ]] && [ -f "$tree/$f" ] && changed_py+=("$tree/$f")
    done
    [ "${#changed_py[@]}" -eq 0 ] && { echo pass; return; }
    "$VENV_PY" -m py_compile "${changed_py[@]}" >/dev/null 2>&1 && echo pass || echo fail
}

# ---- baseline worktree --------------------------------------------------
# --detach is required: `main` (or whatever branch checkout left HEAD on) may
# already be checked out in this workspace, and `git worktree add` refuses a
# branch ref that's checked out elsewhere unless detached.
BASE_TREE="$(mktemp -d "${RUNNER_TEMP:-/tmp}/autofix-baseline-XXXXXX")"
git -C "$REPO_ROOT" worktree prune >/dev/null 2>&1 || true
git -C "$REPO_ROOT" worktree add --detach "$BASE_TREE" "$BASE_SHA" >/dev/null 2>&1
cleanup() {
    git -C "$REPO_ROOT" worktree remove --force "$BASE_TREE" >/dev/null 2>&1 || true
    git -C "$REPO_ROOT" worktree prune >/dev/null 2>&1 || true
}
trap cleanup EXIT

BASE_FAILS="$(mktemp)"
BRANCH_FAILS="$(mktemp)"
run_suite "$BASE_TREE" "$BASE_FAILS"
run_suite "$REPO_ROOT" "$BRANCH_FAILS"

REGRESSIONS="$(comm -13 "$BASE_FAILS" "$BRANCH_FAILS")"
FIXED="$(comm -23 "$BASE_FAILS" "$BRANCH_FAILS")"
NEW_FAILURES="$(printf '%s' "$REGRESSIONS" | grep -c . || true)"

echo "### Verification"
echo
echo "| Check | Baseline (main) | This branch |"
echo "|---|---|---|"
echo "| compileall (changed files) | $(compileall_check "$BASE_TREE") | $(compileall_check "$REPO_ROOT") |"

if [ "${#TEST_DIRS[@]}" -eq 0 ]; then
    echo "| pytest | — | **no matching test directory found** |"
else
    base_n="$(grep -c . "$BASE_FAILS" || true)"
    branch_n="$(grep -c . "$BRANCH_FAILS" || true)"
    label="pytest ${TEST_DIRS[*]}"
    branch_note="$branch_n failed"
    if [ "$NEW_FAILURES" -eq 0 ] && [ "$branch_n" -gt 0 ]; then
        branch_note="$branch_note — pre-existing"
    elif [ "$NEW_FAILURES" -gt 0 ]; then
        branch_note="$branch_note — **$NEW_FAILURES new**"
    fi
    echo "| $label | $base_n failed | $branch_note |"
fi

if [ "$CLIENT_CHANGED" = true ]; then
    echo "| npm run build | *(client changes — not verified by this pass; review manually)* | *(same)* |"
else
    echo "| npm run build | *skipped, client/ unchanged* | *skipped* |"
fi

if [ -n "$REGRESSIONS" ]; then
    echo
    echo "**New failures introduced by this branch:**"
    echo '```'
    printf '%s\n' "$REGRESSIONS"
    echo '```'
fi

if [ -n "$FIXED" ]; then
    echo
    echo "Also fixed (was failing on main): $(printf '%s' "$FIXED" | tr '\n' ' ')"
fi

echo "AUTOFIX_NEW_FAILURES=$NEW_FAILURES" >> "${GITHUB_ENV:-/dev/null}" 2>/dev/null || true
