#!/usr/bin/env bash
# Symlinks hooks/post-checkout into .git/hooks/post-checkout in THIS clone.
# Refuses (with a message) if a non-symlink hook already exists there —
# never overwrites someone else's hook. Does NOT set core.hooksPath, which
# would silently disable every other hook in the repo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK_SRC="$SCRIPT_DIR/hooks/post-checkout"
HOOK_DST="$REPO_ROOT/.git/hooks/post-checkout"

[ -x "$HOOK_SRC" ] || chmod +x "$HOOK_SRC"

if [ -e "$HOOK_DST" ] || [ -L "$HOOK_DST" ]; then
    if [ -L "$HOOK_DST" ] && [ "$(readlink "$HOOK_DST")" = "$HOOK_SRC" ]; then
        echo "Already installed: $HOOK_DST -> $HOOK_SRC"
        exit 0
    fi
    echo "Refusing to overwrite existing hook: $HOOK_DST" >&2
    echo "Remove or back it up, then re-run this script." >&2
    exit 1
fi

ln -s "$HOOK_SRC" "$HOOK_DST"
echo "Installed: $HOOK_DST -> $HOOK_SRC"
