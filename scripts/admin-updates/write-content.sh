#!/usr/bin/env bash
# Draft bounded changelog prose with Luna/high in the existing credential-free
# AutoPR sandbox, then validate every field before returning it to trusted code.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PLAN="${1:?usage: write-content.sh PLAN PRODUCTION_CONTEXT OUTPUT REPORT}"
PRODUCTION_CONTEXT="${2:?missing production context}"
OUTPUT="${3:?missing output path}"
REPORT="${4:?missing report path}"
SANDBOX_RUNNER="${AUTOPR_SANDBOX_RUNNER:-$REPO_ROOT/scripts/kanban-autopr/run-codex-sandboxed.sh}"
LIVE_LOG="${AUTOPR_LIVE_LOG:-$HOME/Library/Logs/matcha-kanban-autopr-live.log}"
WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/admin-updates-draft.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

[ -s "$PLAN" ] || { echo "admin-updates: missing plan" >&2; exit 1; }
[ -s "$PRODUCTION_CONTEXT" ] || { echo "admin-updates: missing production context" >&2; exit 1; }
[ -x "$SANDBOX_RUNNER" ] || { echo "admin-updates: sandbox runner is not executable" >&2; exit 1; }

RAW_DRAFT="$WORK_DIR/draft.json"
RAW_REPORT="$WORK_DIR/report.md"

# The prompt asks the model to "name the actual navigation" but never used to
# hand it any, so it invented plausible paths. Regenerated from the working tree
# on every run: the readable form grounds the prompt, the JSON form lets the
# trusted validator drop any step that still names a surface we do not have.
# Missing grounding must never be fatal: the deploy dispatch is non-fatal by
# design, so a partial checkout aborting the run would trade a wrong changelog
# for no changelog. Without an inventory the validator leaves steps alone.
NAV_INVENTORY="$WORK_DIR/nav-inventory.txt"
NAV_INVENTORY_JSON="$WORK_DIR/nav-inventory.json"
NAV_PROMPT_ARGS=()
NAV_VALIDATE_ARGS=()
if python3 "$SCRIPT_DIR/nav_inventory.py" "$NAV_INVENTORY" --repo-root "$REPO_ROOT" --format text \
    && python3 "$SCRIPT_DIR/nav_inventory.py" "$NAV_INVENTORY_JSON" --repo-root "$REPO_ROOT"; then
    NAV_PROMPT_ARGS=(-f "$NAV_INVENTORY")
    NAV_VALIDATE_ARGS=(--nav-inventory "$NAV_INVENTORY_JSON")
else
    echo "admin-updates: warning: nav inventory unavailable; navigation grounding disabled" >&2
fi
live_log_ready=false
if mkdir -p "$(dirname "$LIVE_LOG")" 2>/dev/null; then
    if (umask 077; {
        printf 'MATCHA ADMIN UPDATES · LUNA LIVE STREAM\n'
        printf 'run %s · started %s\n\n' "${GITHUB_RUN_ID:-local}" "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    } > "$LIVE_LOG") 2>/dev/null; then
        live_log_ready=true
    fi
fi

run_model() {
    env -u GH_TOKEN -u GITHUB_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY \
        AUTOPR_CODEX_MODEL=gpt-5.6-luna \
        AUTOPR_CODEX_REASONING_EFFORT=high \
        AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1 \
        "$SANDBOX_RUNNER" "$SCRIPT_DIR/_prompt.txt" "$RAW_REPORT" "$RAW_DRAFT" \
        -f "$PLAN" -f "$PRODUCTION_CONTEXT" ${NAV_PROMPT_ARGS[@]+"${NAV_PROMPT_ARGS[@]}"}
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
[ "$model_rc" -eq 0 ] || { echo "admin-updates: Luna exited $model_rc" >&2; exit "$model_rc"; }
[ "$live_log_ready" != true ] || printf '\n[COMPLETE] Luna finished at %s\n' \
    "$(date '+%H:%M:%S %Z')" >> "$LIVE_LOG"

python3 "$SCRIPT_DIR/validate.py" "$PLAN" "$RAW_DRAFT" "$OUTPUT" \
    ${NAV_VALIDATE_ARGS[@]+"${NAV_VALIDATE_ARGS[@]}"}
cp "$RAW_REPORT" "$REPORT"
printf 'Validated Luna/high admin update draft: %s entries, %s skips\n' \
    "$(jq '.entries | length' "$OUTPUT")" "$(jq '.skipped | length' "$OUTPUT")"
