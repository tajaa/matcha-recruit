#!/usr/bin/env bash
# shellcheck shell=bash
# One definition of the dirty-worktree refusal, sourced by every lane that runs
# `git reset --hard`.
#
# Those resets carry no pathspec, so they discard tracked AND untracked work
# anywhere in $REPO_ROOT. Without AUTOPR_WORKSPACE_ROOT that root is the
# checkout the script runs from, which is how a local run once destroyed work
# in progress on the very harness being run. The workflows always set the
# variable; a local run that wants the fallback has to start from a clean tree.
#
# It lives in harness/ because that is the one lane directory the workflow's
# `git archive` snapshot always carries, so the control root resolves it too.
# It deliberately does not use any lane's `die`: each lane keeps its own
# stderr prefix by passing one, and this file stays free of lane dependencies.
#
# CALL IT IMMEDIATELY AFTER ASSIGNING REPO_ROOT. A guard placed above the
# assignment dies in its own subshell under `set -u`, the substitution comes
# back empty, and the reset it exists to prevent runs anyway.
autopr_require_writable_root() {
    local root="${1:?autopr_require_writable_root: repository root is required}"
    local label="${2:-msandbox}"
    [ -z "${AUTOPR_WORKSPACE_ROOT:-}" ] || return 0
    [ -n "$(git -C "$root" status --porcelain 2>/dev/null)" ] || return 0
    printf '%s: refusing to run against %s: the working tree is dirty and AUTOPR_WORKSPACE_ROOT is unset\n' \
        "$label" "$root" >&2
    exit 1
}
