#!/usr/bin/env bash
# Preserve and recover interrupted Kanban AutoPR model work in the real
# repository's protected .git metadata. Nothing is uploaded to GitHub: partial
# model output can contain ticket evidence and remains mode-600 on the trusted
# Mac. A later attempt restores the patch only inside the disposable msandbox.
#
# Usage:
#   checkpoint.sh save CARD REPORT DECISION STARTED_AT_EPOCH TIMEOUT_MINUTES
#   checkpoint.sh latest CARD
#   checkpoint.sh consume CARD
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AUTOPR_WORKSPACE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

GIT_DIR="$(git -C "$REPO_ROOT" rev-parse --absolute-git-dir)"
CHECKPOINT_ROOT="${AUTOPR_CHECKPOINT_ROOT:-$GIT_DIR/matcha-kanban-autopr-checkpoints}"
RUNTIME_ROOT="${AUTOPR_SANDBOX_RUNTIME_ROOT:-$GIT_DIR/matcha-kanban-autopr-sandbox}"
SANDBOX_WORKSPACE="$RUNTIME_ROOT/workspace"
LIVE_LOG="${AUTOPR_LIVE_LOG:-$HOME/Library/Logs/matcha-kanban-autopr-live.log}"
MAX_PATCH_BYTES="${AUTOPR_SANDBOX_MAX_PATCH_BYTES:-5242880}"
MAX_REPORT_BYTES="${AUTOPR_SANDBOX_MAX_REPORT_BYTES:-1048576}"
MAX_DECISION_BYTES="${AUTOPR_SANDBOX_MAX_DECISION_BYTES:-262144}"
MAX_TRANSCRIPT_BYTES="${AUTOPR_CHECKPOINT_MAX_TRANSCRIPT_BYTES:-2097152}"

card_identity() {
    local card_file="$1" task_id
    task_id="$(jq -r '.task_id // empty' "$card_file")"
    [[ "$task_id" =~ ^[0-9a-fA-F-]{36}$ ]] || die "invalid checkpoint task id"
    printf '%s' "$task_id" | tr '[:upper:]' '[:lower:]'
}

task_root() {
    printf '%s/%s' "$CHECKPOINT_ROOT" "$(card_identity "$1")"
}

latest_checkpoint() {
    local card_file="$1" root active checkpoint
    root="$(task_root "$card_file")"
    active="$root/active"
    [ -f "$active" ] || return 0
    checkpoint="$(tr -d '\r\n' < "$active")"
    [[ "$checkpoint" =~ ^[A-Za-z0-9._-]+$ ]] || return 0
    [ -d "$root/$checkpoint" ] || return 0
    printf '%s\n' "$root/$checkpoint"
}

bounded_copy() {
    local source_file="$1" destination="$2" max_bytes="$3" size
    [ -s "$source_file" ] || return 0
    size="$(wc -c < "$source_file" | tr -d '[:space:]')"
    if [ "$size" -le "$max_bytes" ]; then
        cp "$source_file" "$destination"
    else
        head -c "$max_bytes" "$source_file" > "$destination"
    fi
    chmod 600 "$destination"
}

save_checkpoint() {
    local card_file="$1" report_file="$2" decision_file="$3"
    local started_at="$4" timeout_minutes="$5" task_id id8 project_id
    local root run_key checkpoint_dir base_sha patch_bytes=0 patch_saved=false
    local elapsed=0 runtime_limited=false note

    task_id="$(card_identity "$card_file")"
    id8="$(jq -r '.id8 // empty' "$card_file")"
    project_id="$(jq -r '.project_id // empty' "$card_file")"
    [[ "$id8" =~ ^[0-9a-fA-F]{8}$ ]] || die "invalid checkpoint id8"
    [[ "$project_id" =~ ^[0-9a-fA-F-]{36}$ ]] || die "invalid checkpoint project id"
    [[ "$started_at" =~ ^[0-9]+$ ]] || die "invalid investigation start time"
    [[ "$timeout_minutes" =~ ^(20|40)$ ]] || die "invalid investigation timeout"

    root="$(task_root "$card_file")"
    run_key="${GITHUB_RUN_ID:-local}-$(date -u +%Y%m%dT%H%M%SZ)"
    checkpoint_dir="$root/$run_key"
    umask 077
    mkdir -p "$checkpoint_dir"
    chmod 700 "$CHECKPOINT_ROOT" "$root" "$checkpoint_dir"

    # A killed docker-exec can leave Codex running after the Actions step has
    # ended. Quiesce only this lane's dedicated container before reading its
    # worktree; the global msandbox master switch remains untouched.
    if [ "${AUTOPR_SANDBOX_TEST_DIRECT:-0}" != 1 ] \
        && [ -x "${AUTOPR_MSANDBOX_BIN:-}" ]; then
        env AGENT_SANDBOX_PROJECT_NAME="${AUTOPR_SANDBOX_PROJECT_NAME:-matcha-kanban-autopr-sandbox}" \
            AGENT_SANDBOX_AUTOPR=1 \
            SANDBOX_WORKSPACE_DIR="$SANDBOX_WORKSPACE" \
            "${AUTOPR_MSANDBOX_BIN}" stop >/dev/null 2>&1 || true
    fi

    base_sha=""
    if [ -f "$SANDBOX_WORKSPACE/.git/autopr-io/model-base-sha" ]; then
        base_sha="$(tr -d '\r\n' < "$SANDBOX_WORKSPACE/.git/autopr-io/model-base-sha")"
    fi
    if [ -d "$SANDBOX_WORKSPACE/.git" ] \
        && [[ "$base_sha" =~ ^[0-9a-f]{40}$ ]] \
        && git -C "$SANDBOX_WORKSPACE" cat-file -e "$base_sha^{commit}" 2>/dev/null; then
        git -C "$SANDBOX_WORKSPACE" add --intent-to-add --all -- .
        git -C "$SANDBOX_WORKSPACE" diff --binary --full-index "$base_sha" -- . \
            > "$checkpoint_dir/model.patch"
        patch_bytes="$(wc -c < "$checkpoint_dir/model.patch" | tr -d '[:space:]')"
        if [ "$patch_bytes" -le "$MAX_PATCH_BYTES" ]; then
            chmod 600 "$checkpoint_dir/model.patch"
            patch_saved=true
        else
            rm -f "$checkpoint_dir/model.patch"
        fi
        bounded_copy "$SANDBOX_WORKSPACE/.git/autopr-io/output/report.md" \
            "$checkpoint_dir/report.md" "$MAX_REPORT_BYTES"
        bounded_copy "$SANDBOX_WORKSPACE/.git/autopr-io/output/decision.json" \
            "$checkpoint_dir/decision.json" "$MAX_DECISION_BYTES"
    fi
    bounded_copy "$report_file" "$checkpoint_dir/report.md" "$MAX_REPORT_BYTES"
    bounded_copy "$decision_file" "$checkpoint_dir/decision.json" "$MAX_DECISION_BYTES"
    if [ -s "$LIVE_LOG" ]; then
        tail -c "$MAX_TRANSCRIPT_BYTES" "$LIVE_LOG" > "$checkpoint_dir/transcript.log"
        chmod 600 "$checkpoint_dir/transcript.log"
    fi

    elapsed=$(( $(date +%s) - started_at ))
    if [ "$elapsed" -ge $((timeout_minutes * 60 - 45)) ]; then
        runtime_limited=true
    fi
    jq -n \
        --arg task_id "$task_id" --arg id8 "$id8" --arg run_id "${GITHUB_RUN_ID:-local}" \
        --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --arg base_sha "$base_sha" \
        --argjson elapsed_seconds "$elapsed" --argjson timeout_minutes "$timeout_minutes" \
        --argjson runtime_limited "$runtime_limited" --argjson patch_saved "$patch_saved" \
        --argjson patch_bytes "$patch_bytes" \
        '{schema_version:1,task_id:$task_id,id8:$id8,run_id:$run_id,
          created_at:$created_at,base_sha:$base_sha,elapsed_seconds:$elapsed_seconds,
          timeout_minutes:$timeout_minutes,runtime_limited:$runtime_limited,
          patch_saved:$patch_saved,patch_bytes:$patch_bytes}' \
        > "$checkpoint_dir/metadata.json"
    chmod 600 "$checkpoint_dir/metadata.json"
    printf '%s\n' "$run_key" > "$root/active"
    chmod 600 "$root/active"

    if [ "$runtime_limited" = true ]; then
        note="🤖 AUTO SETUP · PAUSED: RUNTIME APPROVAL REQUIRED · checkpoint ${GITHUB_RUN_ID:-local} · note: Partial work is preserved. Add additional context with --extend-runtime to approve one 40-minute retry."
        mw_api PATCH "/matcha-work/projects/$project_id/tasks/$task_id" \
            "$(jq -n --arg note "$note" '{progress_note:$note}')" >/dev/null \
            || printf 'kanban-autopr: warning: checkpoint saved but the card pause note could not be written\n' >&2
    fi

    printf '%s\n' "$checkpoint_dir"
}

consume_checkpoint() {
    local card_file="$1" root active consumed
    root="$(task_root "$card_file")"
    active="$root/active"
    [ -f "$active" ] || return 0
    consumed="$root/consumed-${GITHUB_RUN_ID:-local}-$(date -u +%Y%m%dT%H%M%SZ)"
    mv "$active" "$consumed"
    chmod 600 "$consumed"
}

case "${1:-}" in
    save)
        [ "$#" -eq 6 ] || die "usage: checkpoint.sh save CARD REPORT DECISION STARTED_AT_EPOCH TIMEOUT_MINUTES"
        save_checkpoint "$2" "$3" "$4" "$5" "$6"
        ;;
    latest)
        [ "$#" -eq 2 ] || die "usage: checkpoint.sh latest CARD"
        latest_checkpoint "$2"
        ;;
    consume)
        [ "$#" -eq 2 ] || die "usage: checkpoint.sh consume CARD"
        consume_checkpoint "$2"
        ;;
    *)
        die "usage: checkpoint.sh save|latest|consume ..."
        ;;
esac
