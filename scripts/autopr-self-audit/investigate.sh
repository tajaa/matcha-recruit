#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
AUDIT_FILE="${1:?usage: investigate.sh AUDIT REPORT DECISION}"
REPORT_FILE="${2:?usage: investigate.sh AUDIT REPORT DECISION}"
DECISION_FILE="${3:?usage: investigate.sh AUDIT REPORT DECISION}"

for output_file in "$REPORT_FILE" "$DECISION_FILE"; do
    absolute_parent="$(cd "$(dirname "$output_file")" && pwd)"
    case "$absolute_parent/$(basename "$output_file")" in
        "$REPO_ROOT"/*) echo "model output must be outside the repository" >&2; exit 1 ;;
    esac
    rm -f "$output_file"
done

SANDBOX_RUNNER="${AUTOPR_SANDBOX_RUNNER:-$REPO_ROOT/scripts/kanban-autopr/run-codex-sandboxed.sh}"
[ -x "$SANDBOX_RUNNER" ] || { echo "sandbox runner is unavailable: $SANDBOX_RUNNER" >&2; exit 1; }
LIVE_LOG="${AUTOPR_LIVE_LOG:-$HOME/Library/Logs/matcha-kanban-autopr-live.log}"
live_log_ready=false
if mkdir -p "$(dirname "$LIVE_LOG")" 2>/dev/null; then
    if (umask 077; {
        printf 'MATCHA AUTOPR SELF AUDIT · CODEX LIVE STREAM\n'
        printf 'run %s · fingerprint %s · started %s\n\n' \
            "${GITHUB_RUN_ID:-local}" "$(jq -r '.fingerprint' "$AUDIT_FILE")" \
            "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    } > "$LIVE_LOG") 2>/dev/null; then
        live_log_ready=true
    fi
fi

run_model() {
    env -u GH_TOKEN -u GITHUB_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY \
        AUTOPR_CODEX_MODEL=gpt-5.6-sol \
        AUTOPR_CODEX_REASONING_EFFORT=medium \
        "$SANDBOX_RUNNER" "$SCRIPT_DIR/_prompt.txt" "$REPORT_FILE" "$DECISION_FILE.raw" \
        -f "$AUDIT_FILE"
}

if [ "$live_log_ready" = true ]; then
    set +e
    run_model 2>&1 | tee -a "$LIVE_LOG"
    model_rc="${PIPESTATUS[0]}"
    set -e
else
    set +e
    run_model
    model_rc=$?
    set -e
fi
[ "$model_rc" -eq 0 ] || { echo "audit model exited $model_rc" >&2; exit "$model_rc"; }

[ -s "$REPORT_FILE" ] || { echo "audit investigation produced no report" >&2; exit 1; }
for heading in '### Root cause' '### Fix' '### Safety boundary' '### Blast radius'; do
    grep -qF "$heading" "$REPORT_FILE" \
        || { echo "audit report is missing $heading" >&2; exit 1; }
done
"$SCRIPT_DIR/check-decision.sh" "$DECISION_FILE.raw" "$DECISION_FILE"
rm -f "$DECISION_FILE.raw"
