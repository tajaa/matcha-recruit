#!/usr/bin/env bash
# Ask OpenCode to investigate one incident and write a structured report.
# Leaves any fix unstaged in the working tree; never commits.
#
# Usage: ./investigate.sh incident.json report.md [correlated-log.txt]
# No network access of its own — by the time this runs, the workflow has
# already deleted the prod SSH key (see fetch-correlated-log.sh, which must
# run BEFORE that deletion if log enrichment is wanted).
# The model never reports test results — verify.sh owns that, run separately
# by the workflow after this step.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

INCIDENT_FILE="${1:?usage: investigate.sh incident.json report.md [correlated-log.txt]}"
REPORT_FILE="${2:?usage: investigate.sh incident.json report.md [correlated-log.txt]}"
CORRELATED_LOG="${3:-}"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# The report must live outside the git workspace: `git add --all` in
# publish.sh would otherwise stage a file the model wrote under its own
# control, and it would ship inside the PR diff rather than becoming the PR
# body.
case "$(cd "$(dirname "$REPORT_FILE")" 2>/dev/null && pwd)/$(basename "$REPORT_FILE")" in
    "$REPO_ROOT"/*) die "REPORT_FILE must be outside the repo (got $REPORT_FILE)" ;;
esac

PROMPT_FILE="$WORK_DIR/prompt.txt"
sed "s#REPORT_PATH#$REPORT_FILE#g" "$SCRIPT_DIR/_prompt.txt" > "$PROMPT_FILE"

rm -f "$REPORT_FILE"

# Trim what the model sees: cap the message, and keep only traceback frames
# under this app's own source tree. Smaller injection surface, and a better
# root-cause signal than 20+ frames of uvicorn/starlette plumbing.
MODEL_INCIDENT="$WORK_DIR/incident-for-model.json"
jq -c '
  .message |= .[0:2000]
  | .traceback |= (
      split("\n")
      | map(select(test("/app/") or (startswith("File ") | not)))
      | .[0:25]
      | join("\n")
    )
' "$INCIDENT_FILE" > "$MODEL_INCIDENT"

ATTACH_ARGS=(-f "$MODEL_INCIDENT")
[ -n "$CORRELATED_LOG" ] && [ -s "$CORRELATED_LOG" ] && ATTACH_ARGS+=(-f "$CORRELATED_LOG")

# Defense in depth: this step's workflow env should already omit these, but
# strip them here too in case a future edit adds them back.
env -u GH_TOKEN -u EC2_SSH_KEY -u SSH_KEY \
    opencode run --auto --model openai/gpt-5.6-luna \
    "${ATTACH_ARGS[@]}" \
    "$(cat "$PROMPT_FILE")"

if [ ! -s "$REPORT_FILE" ]; then
    die "investigation produced no report at $REPORT_FILE"
fi

for heading in '### Root cause' '### Fix' '### Blast radius' '### Confidence'; do
    if ! grep -qF "$heading" "$REPORT_FILE"; then
        die "report is missing required heading: $heading"
    fi
done
