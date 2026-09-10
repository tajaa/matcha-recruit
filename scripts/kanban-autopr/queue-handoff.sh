#!/usr/bin/env bash
# Explicit operator hand-back uses the existing, idempotent card run request.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
project="${1:?project required}"
task="${2:?task required}"
[[ "$project" =~ ^[0-9a-f-]{36}$ && "$task" =~ ^[0-9a-f-]{36}$ ]] || die "invalid card identity"
mw_api POST "/matcha-work/projects/$project/tasks/$task/autopr/run-now" '{}' >/dev/null
# The durable board request survives a busy runner or failed immediate kick.
if ! "$SCRIPT_DIR/dispatch-if-idle.sh" --start "$task"; then
    printf '\nTicket queued; immediate dispatch failed. The watcher will retry.\n' >&2
    exit 1
fi
