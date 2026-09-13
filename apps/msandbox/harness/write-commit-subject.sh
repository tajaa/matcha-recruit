#!/usr/bin/env bash
# Delegate bounded commit-message wording to Luna without granting it a patch.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${1:?usage: write-commit-subject.sh PREFIX OUTPUT -f INPUT...}"
OUTPUT_FILE="${2:?missing output path}"
shift 2
SANDBOX_RUNNER="${AUTOPR_SANDBOX_RUNNER:-$SCRIPT_DIR/run-codex-sandboxed.sh}"
WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/autopr-commit-subject-XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

die() {
    printf 'autopr commit subject: %s\n' "$1" >&2
    exit 1
}

case "$PREFIX" in feat|fix|chore) ;; *) die "unsupported prefix: $PREFIX" ;; esac
[ "$#" -gt 0 ] || die "at least one input is required"
[ -x "$SANDBOX_RUNNER" ] || die "sandbox runner is not executable: $SANDBOX_RUNNER"

CONTEXT_FILE="$WORK_DIR/commit-context.json"
RECEIPT_FILE="$WORK_DIR/commit-subject.md"
RAW_OUTPUT="$WORK_DIR/commit-subject.raw.json"
jq -n --arg required_prefix "$PREFIX" '{required_prefix:$required_prefix}' > "$CONTEXT_FILE"
rm -f "$OUTPUT_FILE"
env -u GH_TOKEN -u GITHUB_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY \
    AUTOPR_CODEX_MODEL=gpt-5.6-luna \
    AUTOPR_CODEX_REASONING_EFFORT=medium \
    AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1 \
    "$SANDBOX_RUNNER" "$SCRIPT_DIR/_prompt_commit_subject.txt" "$RECEIPT_FILE" "$RAW_OUTPUT" \
    -f "$CONTEXT_FILE" "$@"

jq -e --arg prefix "$PREFIX: " '
  type == "object" and
  ((keys | sort) == ["commit_subject", "schema_version"]) and
  .schema_version == 1 and
  (.commit_subject | type == "string" and length > ($prefix | length) and length <= 72) and
  (.commit_subject | startswith($prefix)) and
  (.commit_subject | ((contains("\n") or contains("\r")) | not))
' "$RAW_OUTPUT" >/dev/null || die "Luna returned an invalid commit subject"

jq -c '{schema_version,commit_subject}' "$RAW_OUTPUT" > "$OUTPUT_FILE"
printf 'Validated Luna commit subject for %s\n' "$PREFIX"
