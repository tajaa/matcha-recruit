# Where the runner-owned verification toolchain lives and how it is keyed.
# Sourced (never executed) by verify.sh, provision-verify-toolchain.sh and
# their tests, so every reader and the one writer agree on the paths.
#
# The toolchain is a venv with the server's requirements + dev requirements
# and a `client/node_modules` built with `npm ci`, both under
# $AUTOFIX_CACHE_DIR (default ~/.cache/matcha-autofix). Keyed on the
# dependency manifests so a branch that changes them reads as "toolchain
# stale" rather than being verified against the wrong dependency set.
#
# Nothing here may reach into ~/Documents, ~/Desktop or ~/Downloads: the
# lanes run under launchd (the Actions runner and the dispatcher), and macOS
# revokes a launchd job's Files-and-Folders grant whenever its binary changes
# — the runner's 2026-08-31 self-update did exactly that, and every bot PR
# for the next two weeks was labelled needs-work for "could not run".

autofix_toolchain_cache_dir() {
    printf '%s' "${AUTOFIX_CACHE_DIR:-$HOME/.cache/matcha-autofix}"
}

# autofix_ensure_cache_dir — create the cache root, owner-only. The lanes and
# the provisioner both reach it, and whichever runs first decides its mode;
# 0700 in one place keeps a lane from leaving it world-readable.
autofix_ensure_cache_dir() {
    local dir
    dir="$(autofix_toolchain_cache_dir)"
    mkdir -p "$dir" || return 1
    chmod 700 "$dir" 2>/dev/null || true
    printf '%s' "$dir"
}

# Keys are derived from the dependency manifests, so an absent manifest must
# be an error and never a key: `shasum` over no input returns the well-known
# empty digest, and every tree that lacks the manifests would then share one
# cache entry and be "verified" against a dependency set that matches none of
# them. Callers report the toolchain as unmeasurable instead.

# autofix_python_key REPO_ROOT — 12 hex chars over the server manifests.
autofix_python_key() {
    local root="$1" file found=false
    for file in "$root/server/requirements.txt" "$root/server/requirements-dev.txt"; do
        [ -f "$file" ] && found=true
    done
    [ "$found" = true ] || return 1
    # The `|| true` is load-bearing under `pipefail`: without it the loop's
    # status is the last `[ -f ]` test, so an absent requirements-dev.txt
    # fails the whole pipeline after the key has already been printed — and
    # every caller that checks the status reads a present toolchain as
    # unmeasurable.
    for file in "$root/server/requirements.txt" "$root/server/requirements-dev.txt"; do
        { [ -f "$file" ] && cat "$file"; } || true
    done | shasum -a 256 | cut -c1-12
}

# autofix_node_key REPO_ROOT — 12 hex chars over the client lockfile.
autofix_node_key() {
    local root="$1"
    [ -f "$root/client/package-lock.json" ] || return 1
    shasum -a 256 < "$root/client/package-lock.json" | cut -c1-12
}

# autofix_venv_dir REPO_ROOT — the venv verify.sh looks for. Non-zero (and
# silent) when the tree carries no server manifests to key on.
autofix_venv_dir() {
    local key
    key="$(autofix_python_key "$1")" && [ -n "$key" ] || return 1
    printf '%s/venv-py312-%s' "$(autofix_toolchain_cache_dir)" "$key"
}

# autofix_node_root REPO_ROOT — holds package.json, package-lock.json and the
# node_modules verify.sh symlinks into both trees. Non-zero (and silent) when
# the tree carries no client lockfile to key on.
autofix_node_root() {
    local key
    key="$(autofix_node_key "$1")" && [ -n "$key" ] || return 1
    printf '%s/client-%s' "$(autofix_toolchain_cache_dir)" "$key"
}

# autofix_python_usable PYTHON — the exact probe verify.sh runs.
autofix_python_usable() {
    [ -x "$1" ] && "$1" -c "import pytest, pytest_asyncio" >/dev/null 2>&1
}

# autofix_node_modules_usable NODE_MODULES_DIR
autofix_node_modules_usable() {
    [ -x "$1/.bin/tsc" ] && [ -x "$1/.bin/vitest" ]
}
