#!/usr/bin/env bash
# Build (or check) the runner-owned verification toolchain that
# error-autofix/verify.sh needs on the Mac: a Python venv with the server's
# requirements + dev requirements, and a `client/node_modules` from `npm ci`.
# Both live under ~/.cache/matcha-autofix, keyed on the dependency manifests
# (see error-autofix/toolchain.sh for the layout and the reason it is not the
# dev clone under ~/Documents).
#
#   provision-verify-toolchain.sh [--repo ROOT]            build what is missing
#   provision-verify-toolchain.sh --check [--repo ROOT]    report; exit 0 current,
#                                                          3 missing
#   provision-verify-toolchain.sh --force [--repo ROOT]    rebuild both
#
# Run by hand or via `msandbox install --verify-toolchain`; never from a lane
# job — a `pip install` that dies on a native extension would eat the job's
# timeout, so verify.sh only ever READS this cache and reports "unavailable"
# when it is missing. audit.sh runs `--check` and reports a missing toolchain
# as an operator action.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
PY312="${PY312:-/opt/homebrew/bin/python3.12}"
NPM_BIN="${AUTOFIX_NPM_BIN:-npm}"
MODE=provision
FORCE=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check) MODE=check; shift ;;
        --force) FORCE=true; shift ;;
        # Without -e an unreachable path would leave REPO_ROOT empty and
        # every key would then be computed from absolute /server/... paths:
        # a MISSING report for a toolchain that is present, and a prune that
        # deletes the real one because the current key is a bogus one.
        --repo)
            REPO_ROOT="$(cd "${2:?--repo requires a path}" 2>/dev/null && pwd)" \
                || { echo "--repo: no such directory: $2" >&2; exit 2; }
            shift 2 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "usage: provision-verify-toolchain.sh [--check] [--force] [--repo ROOT]" >&2; exit 2 ;;
    esac
done

# shellcheck source=../error-autofix/toolchain.sh
. "$SCRIPT_DIR/../error-autofix/toolchain.sh"

CACHE_DIR="$(autofix_toolchain_cache_dir)"
# Both are keyed on the dependency manifests in $REPO_ROOT. A tree without
# them has no key at all — guessing one (the digest of no input) would alias
# it onto every other manifest-less tree's cache entry — so the directory is
# left empty here and every consumer below treats that as MISSING.
VENV_DIR="$(autofix_venv_dir "$REPO_ROOT")" || VENV_DIR=""
NODE_ROOT="$(autofix_node_root "$REPO_ROOT")" || NODE_ROOT=""
PYTHON_WHERE="${VENV_DIR:-no server/requirements*.txt under $REPO_ROOT}"
NODE_WHERE="${NODE_ROOT:+$NODE_ROOT/node_modules}"
NODE_WHERE="${NODE_WHERE:-no client/package-lock.json under $REPO_ROOT}"

python_current() { [ -n "$VENV_DIR" ] && autofix_python_usable "$VENV_DIR/bin/python"; }
node_current() { [ -n "$NODE_ROOT" ] && autofix_node_modules_usable "$NODE_ROOT/node_modules"; }

report() {
    local rc=0
    if python_current; then
        echo "verification toolchain python: current ($VENV_DIR)"
    else
        echo "verification toolchain python: MISSING ($PYTHON_WHERE)"
        rc=3
    fi
    if node_current; then
        echo "verification toolchain client: current ($NODE_ROOT/node_modules)"
    else
        echo "verification toolchain client: MISSING ($NODE_WHERE)"
        rc=3
    fi
    [ "$rc" -eq 0 ] || echo "Provision with: ./apps/msandbox/harness/provision-verify-toolchain.sh (or msandbox install --verify-toolchain)"
    return "$rc"
}

# Build into a sibling temp dir and rename, so a half-built toolchain is
# never mistaken for a current one by a lane that runs concurrently.
build_python() {
    local temporary="$VENV_DIR.tmp.$$"
    [ -x "$PY312" ] || { echo "missing $PY312 (brew install python@3.12)" >&2; return 1; }
    rm -rf "$temporary"
    "$PY312" -m venv "$temporary" || return 1
    local manifests=(-r "$REPO_ROOT/server/requirements.txt")
    [ ! -f "$REPO_ROOT/server/requirements-dev.txt" ] \
        || manifests+=(-r "$REPO_ROOT/server/requirements-dev.txt")
    "$temporary/bin/python" -m pip install --quiet --disable-pip-version-check "${manifests[@]}" || {
        rm -rf "$temporary"
        return 1
    }
    if ! autofix_python_usable "$temporary/bin/python"; then
        echo "built venv cannot import pytest + pytest_asyncio; is server/requirements-dev.txt present?" >&2
        rm -rf "$temporary"
        return 1
    fi
    rm -rf "$VENV_DIR"
    mv "$temporary" "$VENV_DIR"
}

build_node() {
    local temporary="$NODE_ROOT.tmp.$$"
    command -v "$NPM_BIN" >/dev/null 2>&1 || { echo "missing npm ($NPM_BIN)" >&2; return 1; }
    [ -f "$REPO_ROOT/client/package-lock.json" ] || { echo "missing client/package-lock.json" >&2; return 1; }
    rm -rf "$temporary"
    mkdir -p "$temporary"
    cp "$REPO_ROOT/client/package.json" "$REPO_ROOT/client/package-lock.json" "$temporary/"
    # --legacy-peer-deps mirrors client/Dockerfile and ci.yml: react 19 vs
    # react-simple-maps' react<=18 peer range is an ERESOLVE otherwise.
    (cd "$temporary" && "$NPM_BIN" ci --legacy-peer-deps --no-audit --no-fund --loglevel=error) || {
        rm -rf "$temporary"
        return 1
    }
    if ! autofix_node_modules_usable "$temporary/node_modules"; then
        echo "npm ci finished but tsc/vitest are not in node_modules/.bin" >&2
        rm -rf "$temporary"
        return 1
    fi
    rm -rf "$NODE_ROOT"
    mv "$temporary" "$NODE_ROOT"
}

# Old keys are dead weight (a venv is ~1 GB); keep only the current ones.
prune_stale() {
    local entry
    # Never prune against an unresolved key: the "keep" patterns would be
    # empty and every real cache entry would read as stale.
    [ -n "$VENV_DIR" ] && [ -n "$NODE_ROOT" ] || return 0
    for entry in "$CACHE_DIR"/venv-py312-* "$CACHE_DIR"/client-*; do
        [ -e "$entry" ] || continue
        case "$entry" in
            "$VENV_DIR"|"$NODE_ROOT") continue ;;
            # A build in flight, possibly another operator's: build_python and
            # build_node clean up their own staging directory on every exit
            # path, so anything left here belongs to a live run or to one that
            # was hard-killed. Deleting it pulls the tree out from under an
            # `npm ci`; leaving it costs one directory until the next --force.
            *.tmp.*) continue ;;
        esac
        rm -rf "$entry"
        echo "pruned stale toolchain: $entry"
    done
}

autofix_ensure_cache_dir >/dev/null || { echo "cannot create $CACHE_DIR" >&2; exit 1; }

if [ "$MODE" = check ]; then
    report
    exit $?
fi

rc=0
if [ -z "$VENV_DIR" ]; then
    echo "cannot build the python toolchain: $PYTHON_WHERE" >&2
    rc=1
elif [ "$FORCE" = true ] || ! python_current; then
    echo "building python toolchain: $VENV_DIR"
    build_python || rc=1
else
    echo "python toolchain current: $VENV_DIR"
fi
if [ -z "$NODE_ROOT" ]; then
    echo "cannot build the client toolchain: $NODE_WHERE" >&2
    rc=1
elif [ "$FORCE" = true ] || ! node_current; then
    echo "building client toolchain: $NODE_ROOT"
    build_node || rc=1
else
    echo "client toolchain current: $NODE_ROOT"
fi
prune_stale
report || rc=1
exit "$rc"
