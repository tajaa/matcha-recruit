#!/usr/bin/env bash
# Proves an AutoPR attempt leaves its submitted branch without erasing dirty
# files from the persistent Mac runner workspace.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CLEANUP="$REPO_ROOT/scripts/kanban-autopr/leave-task-checkout.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

git -C "$TMP_DIR" init -q
git -C "$TMP_DIR" config user.name test
git -C "$TMP_DIR" config user.email test@example.com
printf 'tracked\n' > "$TMP_DIR/tracked.txt"
git -C "$TMP_DIR" add tracked.txt
git -C "$TMP_DIR" commit -qm initial
git -C "$TMP_DIR" branch -M main
git -C "$TMP_DIR" switch -qc bot/task-aaaa0000

(cd "$TMP_DIR" && "$CLEANUP")
[ "$(git -C "$TMP_DIR" branch --show-current)" = main ]

git -C "$TMP_DIR" switch -q bot/task-aaaa0000
printf 'preserve me\n' > "$TMP_DIR/untracked.txt"
set +e
(cd "$TMP_DIR" && "$CLEANUP") >/dev/null 2>&1
dirty_rc=$?
set -e
[ "$dirty_rc" -ne 0 ]
[ "$(git -C "$TMP_DIR" branch --show-current)" = bot/task-aaaa0000 ]
[ "$(cat "$TMP_DIR/untracked.txt")" = "preserve me" ]

printf 'PASS: clean AutoPR checkout returns to main; dirty files are preserved\n'
