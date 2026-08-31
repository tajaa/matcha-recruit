#!/usr/bin/env bash
# Ask Codex to investigate one incident and write a structured report.
# Leaves any fix unstaged in the working tree; never commits.
#
# Usage: ./investigate.sh incident.json report.md decision.json [correlated-log.txt]
# No network access of its own — by the time this runs, the workflow has
# already deleted the prod SSH key (see fetch-correlated-log.sh, which must
# run BEFORE that deletion if log enrichment is wanted).
# The model never reports test results — verify.sh owns that, run separately
# by the workflow after this step.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

INCIDENT_FILE="${1:?usage: investigate.sh incident.json report.md decision.json [correlated-log.txt]}"
REPORT_FILE="${2:?usage: investigate.sh incident.json report.md decision.json [correlated-log.txt]}"
DECISION_FILE="${3:?usage: investigate.sh incident.json report.md decision.json [correlated-log.txt]}"
CORRELATED_LOG="${4:-}"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

# The report must live outside the git workspace: `git add --all` in
# publish.sh would otherwise stage a file the model wrote under its own
# control, and it would ship inside the PR diff rather than becoming the PR
# body.
for output_file in "$REPORT_FILE" "$DECISION_FILE"; do
    case "$(cd "$(dirname "$output_file")" 2>/dev/null && pwd)/$(basename "$output_file")" in
        "$REPO_ROOT"/*) die "model output must be outside the repo (got $output_file)" ;;
    esac
    rm -f "$output_file"
done

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

# Match the Kanban lane's isolation: production runs use a disposable,
# tracked-files-only clone in the dedicated msandbox. Direct host execution is
# an explicit local test seam and is forbidden in GitHub Actions.
SANDBOX_RUNNER="${AUTOPR_SANDBOX_RUNNER:-$REPO_ROOT/scripts/kanban-autopr/run-codex-sandboxed.sh}"
TEST_DIRECT="${AUTOPR_SANDBOX_TEST_DIRECT:-0}"
[ "$TEST_DIRECT" != 1 ] || [ "${GITHUB_ACTIONS:-}" != true ] \
    || die "direct Codex execution is forbidden in GitHub Actions"
[ -x "$SANDBOX_RUNNER" ] || die "sandbox runner is not executable: $SANDBOX_RUNNER"
env -u GH_TOKEN -u EC2_SSH_KEY -u SSH_KEY \
    AUTOPR_CODEX_MODEL=gpt-5.6-sol \
    AUTOPR_CODEX_REASONING_EFFORT=medium \
    "$SANDBOX_RUNNER" "$SCRIPT_DIR/_prompt.txt" "$REPORT_FILE" "$DECISION_FILE" \
    "${ATTACH_ARGS[@]}"

if [ ! -s "$REPORT_FILE" ]; then
    die "investigation produced no report at $REPORT_FILE"
fi

for heading in '### Root cause' '### Fix' '### Blast radius' '### Confidence'; do
    if ! grep -qF "$heading" "$REPORT_FILE"; then
        die "report is missing required heading: $heading"
    fi
done

# Presentation metadata is model-produced data, never authority. Validate all
# fields and compute the bounded score/band in trusted shell before publish.
"$SCRIPT_DIR/decision.sh" normalize "$DECISION_FILE" "$DECISION_FILE.normalized"
mv "$DECISION_FILE.normalized" "$DECISION_FILE"
