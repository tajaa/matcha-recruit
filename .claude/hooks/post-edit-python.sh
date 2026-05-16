#!/usr/bin/env bash
# PostToolUse hook fired after Edit/Write tool calls.
# Reads tool data on stdin (JSON), extracts file_path, and runs a
# lightweight syntax check on Python files. Output is shown back to
# Claude so it sees the error before its next turn.
#
# Why py_compile and not pytest/mypy:
# - py_compile is instant (~10ms per file) — catches genuine syntax
#   errors without slowing iteration.
# - Heavier checks (ruff/mypy/pytest) belong to the dev's manual cycle,
#   not a per-edit hook.
#
# Why no TypeScript check here:
# - `npx tsc --noEmit` takes 10-30s on this project, too slow to gate
#   every .tsx edit. Run manually: `cd client && npx tsc --noEmit`.

set -u

# Read full stdin (jq prefers the whole payload).
payload=$(cat)

# Extract file_path; bail silently if jq is missing or payload malformed.
file_path=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null) || exit 0
[ -z "$file_path" ] && exit 0

# Only act on Python files inside server/.
case "$file_path" in
  *.py)
    [ -f "$file_path" ] || exit 0
    out=$(python3 -m py_compile "$file_path" 2>&1) || {
      printf 'py_compile failed for %s:\n%s\n' "$file_path" "$out"
      exit 0  # exit 0 — surface error to Claude but do not block tool result
    }
    # Optional ruff pass if installed (silent on clean code).
    if command -v ruff >/dev/null 2>&1; then
      ruff_out=$(ruff check --quiet --no-cache "$file_path" 2>&1) || true
      [ -n "$ruff_out" ] && printf 'ruff: %s\n' "$ruff_out"
    fi
    ;;
esac

exit 0
