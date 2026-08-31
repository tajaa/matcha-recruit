#!/usr/bin/env bash
# Use Luna for bounded publication prose, then validate it before trusted code
# may use the commit subject or append the note to a Matcha Work card.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
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

RAW_OUTPUT="$WORK_DIR/publication-copy.raw.json"
RECEIPT="$WORK_DIR/publication-copy.md"
rm -f "$OUTPUT_FILE"
env -u GH_TOKEN -u GITHUB_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY \
    AUTOPR_CODEX_MODEL=gpt-5.6-luna \
    AUTOPR_CODEX_REASONING_EFFORT=medium \
    AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1 \
    "$SANDBOX_RUNNER" "$SCRIPT_DIR/_prompt_publication_copy.txt" "$RECEIPT" "$RAW_OUTPUT" \
    -f "$CARD_FILE" -f "$DECISION_FILE" -f "$REPORT_FILE" -f "$VERIFICATION_FILE"

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
' "$RAW_OUTPUT" >/dev/null || die "Luna returned invalid publication copy"

jq -c '{schema_version, commit_subject, card_note}' "$RAW_OUTPUT" > "$OUTPUT_FILE"
printf 'Validated Luna publication copy for %s\n' "$EXPECTED_PREFIX"
