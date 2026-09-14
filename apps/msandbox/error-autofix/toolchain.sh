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

# autofix_python_key REPO_ROOT — 12 hex chars over the server manifests.
autofix_python_key() {
    local root="$1" file
    for file in "$root/server/requirements.txt" "$root/server/requirements-dev.txt"; do
        [ -f "$file" ] && cat "$file"
    done | shasum -a 256 | cut -c1-12
}

# autofix_node_key REPO_ROOT — 12 hex chars over the client lockfile.
autofix_node_key() {
    local root="$1"
    { [ -f "$root/client/package-lock.json" ] && cat "$root/client/package-lock.json"; } \
        | shasum -a 256 | cut -c1-12
}

# autofix_venv_dir REPO_ROOT — the venv verify.sh looks for.
autofix_venv_dir() {
    printf '%s/venv-py312-%s' "$(autofix_toolchain_cache_dir)" "$(autofix_python_key "$1")"
}

# autofix_node_root REPO_ROOT — holds package.json, package-lock.json and the
# node_modules verify.sh symlinks into both trees.
autofix_node_root() {
    printf '%s/client-%s' "$(autofix_toolchain_cache_dir)" "$(autofix_node_key "$1")"
}

# autofix_python_usable PYTHON — the exact probe verify.sh runs.
autofix_python_usable() {
    [ -x "$1" ] && "$1" -c "import pytest, pytest_asyncio" >/dev/null 2>&1
}

# autofix_node_modules_usable NODE_MODULES_DIR
autofix_node_modules_usable() {
    [ -x "$1/.bin/tsc" ] && [ -x "$1/.bin/vitest" ]
}
