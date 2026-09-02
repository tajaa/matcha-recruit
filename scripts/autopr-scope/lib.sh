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

autopr_scope_capture_diff() {
    local repo_root="$1" output="$2" index_file
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
