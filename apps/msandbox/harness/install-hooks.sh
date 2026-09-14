#!/usr/bin/env bash
# Symlinks hooks/post-checkout and hooks/post-merge into .git/hooks/ in THIS
# clone. Refuses (with a message) if a non-symlink hook already exists there —
# never overwrites someone else's hook. Does NOT set core.hooksPath, which
# would silently disable every other hook in the repo.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
HOOKS_DIR="$(git -C "$REPO_ROOT" rev-parse --git-path hooks)"
case "$HOOKS_DIR" in
    /*) ;;
    *) HOOKS_DIR="$REPO_ROOT/$HOOKS_DIR" ;;
esac
mkdir -p "$HOOKS_DIR"

status=0
for hook in post-checkout post-merge; do
    src="$SCRIPT_DIR/hooks/$hook"
    dst="$HOOKS_DIR/$hook"
    [ -x "$src" ] || chmod +x "$src"
    if [ -e "$dst" ] || [ -L "$dst" ]; then
        if [ -L "$dst" ] && [ "$(readlink "$dst")" = "$src" ]; then
            echo "Already installed: $dst -> $src"
            continue
        fi
        echo "Refusing to overwrite existing hook: $dst" >&2
        echo "Remove or back it up, then re-run this script." >&2
        status=1
        continue
    fi
    ln -s "$src" "$dst"
    echo "Installed: $dst -> $src"
done
exit "$status"
