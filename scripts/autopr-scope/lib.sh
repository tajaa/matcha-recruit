#!/usr/bin/env bash
# Shared helpers for cross-lane AutoPR scope deduplication. Source, don't execute.
set -uo pipefail

autopr_scope_die() {
    printf 'autopr-scope: %s\n' "$1" >&2
    exit 1
}

autopr_scope_mode() {
    case "${AUTOPR_SCOPE_DEDUPE_MODE:-enforce}" in
        off|observe|enforce) printf '%s\n' "${AUTOPR_SCOPE_DEDUPE_MODE:-enforce}" ;;
        *) autopr_scope_die "AUTOPR_SCOPE_DEDUPE_MODE must be off, observe, or enforce" ;;
    esac
}

# autopr_scope_require_repo REPO_ROOT
# A misresolved root used to surface only as git's own `fatal: not a git
# repository` plus whatever generic failure came next, which costs a whole
# investigate run to trace back. Say the cause instead.
#
# `rev-parse --git-dir` alone is not enough: git walks up, so a root that is
# merely *inside* some repository would pass and then have that parent's tree
# read instead. Require the root to be the top level itself. Both sides are
# compared physically because $GITHUB_WORKSPACE and $TMPDIR can carry symlink
# components (macOS /tmp, /var/folders) that git resolves and the caller's
# string does not.
autopr_scope_require_repo() {
    local repo_root="$1" toplevel
    [ -d "$repo_root" ] \
        || autopr_scope_die "repo root is not a git repository: $repo_root does not exist (set AUTOPR_WORKSPACE_ROOT)"
    toplevel="$(git -C "$repo_root" rev-parse --show-toplevel 2>/dev/null)" \
        || autopr_scope_die "repo root is not a git repository: $repo_root (set AUTOPR_WORKSPACE_ROOT)"
    [ -n "$toplevel" ] \
        || autopr_scope_die "repo root is not a git repository: $repo_root has no work tree (set AUTOPR_WORKSPACE_ROOT)"
    [ "$(cd "$repo_root" && pwd -P)" = "$(cd "$toplevel" && pwd -P)" ] \
        || autopr_scope_die "repo root is not a git repository: $repo_root sits inside $toplevel (set AUTOPR_WORKSPACE_ROOT)"
}

autopr_scope_capture_diff() {
    local repo_root="$1" output="$2" index_file
    autopr_scope_require_repo "$repo_root"
    index_file="$(mktemp "${RUNNER_TEMP:-/tmp}/autopr-scope-index-XXXXXX")"
    rm -f "$index_file"
    if ! GIT_INDEX_FILE="$index_file" git -C "$repo_root" read-tree HEAD \
        || ! GIT_INDEX_FILE="$index_file" git -C "$repo_root" add --all \
        || ! GIT_INDEX_FILE="$index_file" git -C "$repo_root" diff --cached --binary --no-ext-diff --no-renames > "$output"; then
        rm -f "$index_file"
        autopr_scope_die "could not capture the proposed patch"
    fi
    rm -f "$index_file"
}

autopr_scope_patch_id() {
    # A concatenated diff stream can produce more than one patch-id. Compare
    # the complete sorted set: accepting only the first would let an exact
    # proposal plus an additional patch masquerade as full identity.
    git patch-id --stable < "$1" 2>/dev/null \
        | awk '{print $1}' | sort | paste -sd, -
}
