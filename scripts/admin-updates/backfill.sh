#!/usr/bin/env bash
# One-time direct production backfill. This is intentionally separate from the
# GitHub Action: run it on the trusted host with a local gh login and the
# production SSH key when historical updates need to be filled immediately.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SINCE_DATE="${1:?usage: backfill.sh LAST_COVERED_UTC_DATE [--dry-run|--publish]}"
MODE="${2:---dry-run}"
SSH_KEY="${SSH_KEY:?SSH_KEY must point to the production SSH key}"
WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/admin-updates-backfill.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

[[ "$SINCE_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] \
    || { echo "admin-updates: LAST_COVERED_UTC_DATE must be YYYY-MM-DD" >&2; exit 2; }
case "$MODE" in
    --dry-run|--publish) ;;
    *) echo "admin-updates: expected --dry-run or --publish" >&2; exit 2 ;;
esac

production_context="$WORK_DIR/production-context.json"
production_state="$WORK_DIR/production-state.json"
deployment="$WORK_DIR/deployment.json"
plan="$WORK_DIR/plan.json"
draft="$WORK_DIR/draft.json"
report="$WORK_DIR/report.md"
receipt="$WORK_DIR/publish.json"

SSH_KEY="$SSH_KEY" "$REPO_ROOT/scripts/kanban-autopr/resolve-production-context.sh" \
    > "$production_context"
SSH_KEY="$SSH_KEY" "$SCRIPT_DIR/collect-prod-state.sh" > "$production_state"
jq -n \
    --arg deploy_id "direct-backfill-$(date -u +%Y%m%dT%H%M%SZ)" \
    --arg deployed_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg sha "$(git -C "$REPO_ROOT" rev-parse HEAD)" \
    '{deploy_id:$deploy_id,deployed_at:$deployed_at,target:"backfill",sha:$sha,source:"direct"}' \
    > "$deployment"
"$SCRIPT_DIR/collect.sh" "$production_context" "$production_state" "$deployment" "$plan" "" "$SINCE_DATE"
jq '{manualSinceDate,sourceWatermark,targetWatermark,candidates:(.candidates|length),units:(.units|length),deferred}' "$plan"

if [ "$(jq -r '.hasWork' "$plan")" != "true" ]; then
    echo "admin-updates: no production-ready updates in this date range"
    exit 0
fi
if [ "$MODE" = --dry-run ]; then
    echo "admin-updates: dry run complete; rerun with --publish to draft and write updates"
    exit 0
fi

"$SCRIPT_DIR/write-content.sh" "$plan" "$production_context" "$draft" "$report"
SSH_KEY="$SSH_KEY" "$SCRIPT_DIR/publish.sh" "$plan" "$draft" "$receipt"
SSH_KEY="$SSH_KEY" "$SCRIPT_DIR/collect-prod-state.sh" > "$WORK_DIR/state-after.json"
jq -e --slurpfile draft "$draft" '
  .last_pr_number >= $draft[0].processedThroughPr and
  (([$draft[0].entries[] | select(.product == "matcha") | .id] - .existing.matcha) | length == 0) and
  (([$draft[0].entries[] | select(.product == "tellus") | .id] - .existing.tellus) | length == 0)
' "$WORK_DIR/state-after.json" >/dev/null
printf 'admin-updates: direct backfill published and verified\n'
