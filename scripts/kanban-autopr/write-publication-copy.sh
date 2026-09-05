#!/usr/bin/env bash
# Use Luna for bounded publication prose, then validate it before trusted code
# may use the commit subject or append the note to a Matcha Work card.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AUTOPR_WORKSPACE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
CARD_FILE="${1:?usage: write-publication-copy.sh CARD DECISION REPORT VERIFICATION OUTPUT}"
DECISION_FILE="${2:?missing decision path}"
REPORT_FILE="${3:?missing report path}"
VERIFICATION_FILE="${4:?missing verification path}"
OUTPUT_FILE="${5:?missing publication-copy output path}"
SANDBOX_RUNNER="${AUTOPR_SANDBOX_RUNNER:-$SCRIPT_DIR/run-codex-sandboxed.sh}"
WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/autopr-publication-copy-XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

die() {
    printf 'kanban-autopr publication copy: %s\n' "$1" >&2
    exit 1
}

for input_file in "$CARD_FILE" "$DECISION_FILE" "$REPORT_FILE" "$VERIFICATION_FILE"; do
    [ -s "$input_file" ] || die "missing or empty input: $input_file"
done
[ -x "$SANDBOX_RUNNER" ] || die "sandbox runner is not executable: $SANDBOX_RUNNER"

case "$(jq -r '.category // "manual"' "$CARD_FILE")" in
    feat) EXPECTED_PREFIX=feat ;;
    fix|bug) EXPECTED_PREFIX=fix ;;
    *) EXPECTED_PREFIX=chore ;;
esac

fallback_card_note() {
    local outcome reason
    outcome="$(jq -r '.outcome // empty' "$DECISION_FILE")"
    reason="$(jq -r '.no_safe_action_reason // empty' "$DECISION_FILE")"
    case "$outcome:$reason" in
        implementation:*)
            printf 'AutoPR completed this request and drafted the change for review.' ;;
        partial_implementation:*)
            printf 'AutoPR drafted the safe part of this request and still needs human answers.' ;;
        questions_only:*)
            printf 'AutoPR reviewed this request and still needs human answers before it can continue safely.' ;;
        no_safe_action:already_fixed)
            printf 'After reviewing the additional context, AutoPR still found this request already fixed.' ;;
        no_safe_action:policy_blocked)
            printf 'After reviewing the additional context, AutoPR still found this request blocked by policy.' ;;
        no_safe_action:external_dependency)
            printf 'After reviewing the additional context, AutoPR still found an external dependency blocks this request.' ;;
        *)
            printf 'AutoPR reviewed this request and recorded the result.' ;;
    esac
}

RAW_OUTPUT="$WORK_DIR/publication-copy.raw.json"
RECEIPT="$WORK_DIR/publication-copy.md"
rm -f "$OUTPUT_FILE"
env -u GH_TOKEN -u GITHUB_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY \
    AUTOPR_CODEX_MODEL=gpt-5.6-luna \
    AUTOPR_CODEX_REASONING_EFFORT=medium \
    AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1 \
    "$SANDBOX_RUNNER" "$SCRIPT_DIR/_prompt_publication_copy.txt" "$RECEIPT" "$RAW_OUTPUT" \
    -f "$CARD_FILE" -f "$DECISION_FILE" -f "$REPORT_FILE" -f "$VERIFICATION_FILE"

raw_subject="$(jq -r 'if type == "object" and (.commit_subject | type == "string") then .commit_subject else "" end' \
    "$RAW_OUTPUT" 2>/dev/null || true)"
raw_note="$(jq -r 'if type == "object" and (.card_note | type == "string") then .card_note else "" end' \
    "$RAW_OUTPUT" 2>/dev/null || true)"

# The prose pass occasionally picks the semantic conventional-commit type
# (for example `fix:`) instead of the card's required category (`feat:`).
# That mismatch is mechanical, so repair it here rather than dropping a
# completed investigation before its result can be written back to the card.
subject_body="$(printf '%s' "$raw_subject" | sed -E 's/^[[:alnum:]_-]+:[[:space:]]*//')"
normalized_subject="$EXPECTED_PREFIX: $subject_body"
if ! jq -ne --arg value "$normalized_subject" --arg prefix "$EXPECTED_PREFIX: " '
  ($value | length > ($prefix | length) and length <= 72) and
  ($value | startswith($prefix)) and
  ($value | test("[\\r\\n[:cntrl:]]") | not)
' >/dev/null; then
    normalized_subject="$EXPECTED_PREFIX: address kanban task"
fi

normalized_note="$raw_note"
if ! jq -ne --arg value "$normalized_note" '
  ($value | length > 0 and length <= 240) and
  ($value | test("[\\r\\n[:cntrl:]·]") | not) and
  ($value | test("https?://|www\\.") | not)
' >/dev/null; then
    normalized_note="$(fallback_card_note)"
fi

jq -n --arg subject "$normalized_subject" --arg note "$normalized_note" \
    '{schema_version: 1, commit_subject: $subject, card_note: $note}' > "$OUTPUT_FILE"

jq -e --arg prefix "$EXPECTED_PREFIX: " '
  type == "object" and
  ((keys | sort) == ["card_note", "commit_subject", "schema_version"]) and
  .schema_version == 1 and
  (.commit_subject | type == "string" and length > ($prefix | length) and length <= 72) and
  (.commit_subject | startswith($prefix)) and
  (.commit_subject | test("[\\r\\n[:cntrl:]]") | not) and
  (.card_note | type == "string" and length > 0 and length <= 240) and
  (.card_note | test("[\\r\\n[:cntrl:]·]") | not) and
  (.card_note | test("https?://|www\\.") | not)
' "$OUTPUT_FILE" >/dev/null || die "could not produce valid publication copy"

jq -c '{schema_version, commit_subject, card_note}' "$OUTPUT_FILE" > "$OUTPUT_FILE.next"
mv "$OUTPUT_FILE.next" "$OUTPUT_FILE"
printf 'Validated publication copy for %s\n' "$EXPECTED_PREFIX"
