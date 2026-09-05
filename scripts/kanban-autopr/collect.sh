#!/usr/bin/env bash
# Collect candidate kanban cards across every project in MATCHA_PROJECT_IDS
# (comma-separated) assigned to MATCHA_ASSIGNEE_EMAIL and sitting in `todo`
# or `changes_requested`, plus system-linked `in_progress` cards whose owner
# PR may need lifecycle reconciliation. A pending explicit reconsideration is
# also eligible in `todo` / `changes_requested` even if assignment changed:
# that user action is the durable one-run authorization. One bundle fetch per
# project (no company-wide list endpoint — the bot's access is per-project
# mw_project_collaborators rows, not a single company scope; see
# docs/ops/KANBAN_AUTOPR.md).
#
# Usage: ./collect.sh > cards.json
# Always exits 0; emits `[]` if nothing matches.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

_kanban_autopr_load_env
_kanban_autopr_validate_ci_scope

out="[]"
IFS=',' read -ra PROJECT_IDS <<< "$MATCHA_PROJECT_IDS"
for project_id in "${PROJECT_IDS[@]}"; do
    project_id="$(echo "$project_id" | xargs)"
    [ -n "$project_id" ] || continue

    bundle="$(mw_api GET "/matcha-work/projects/$project_id/bundle")" || die "bundle fetch failed for $project_id"
    project_title="$(printf '%s' "$bundle" | jq -r '.project.title // "untitled"')"

    elements="$(printf '%s' "$bundle" | jq -c '.elements // []')"

    candidates="$(printf '%s' "$bundle" | jq -c \
        --arg email "$MATCHA_ASSIGNEE_EMAIL" \
        --arg project_id "$project_id" \
        --arg project_title "$project_title" \
        --argjson elements "$elements" '
        .tasks // []
        | map(select(
            (
              (
                (.autopr_reconsideration_pending // false)
                and (.board_column == "todo" or .board_column == "changes_requested")
              )
              or (
                .assigned_email == $email
                and (
                  .board_column == "todo"
                  or .board_column == "changes_requested"
                  or (.board_column == "in_progress" and ((.progress_note // "") | startswith("🤖 AUTO SETUP · ALREADY SCOPED")))
                )
              )
              or (
                # "Run AutoPR now" on the card. An explicit human request is
                # work authorization on its own, exactly like a reconsideration,
                # so it does not depend on assignment.
                (.board_column == "todo" or .board_column == "changes_requested")
                and (.autopr_run_requested_at // null) != null
              )
              or (
                # A worker can consume an explicit additional-context directive
                # by repeating the very refusal that directive overrides.
                # Admit those cards as bounded recovery probes; only a matching
                # decision-bound history event survives the post-fetch filter
                # below.
                (.board_column == "todo" or .board_column == "changes_requested")
                and ((.progress_note // "")
                     | test("\\[autopr:no-spec [^]]+\\] already_fixed(?: |$)"; "i"))
              )
            )
            and .status != "cancelled"
          ))
        | map(
            . as $t
            | ($elements | map(select(.id == $t.element_id)) | .[0]) as $el
            | {
                task_id: $t.id,
                id8: ($t.id | gsub("-"; "") | .[0:8]),
                project_id: $project_id,
                project_title: $project_title,
                title: $t.title,
                description: $t.description,
                review_note: $t.review_note,
                board_column: $t.board_column,
                category: $t.category,
                priority: $t.priority,
                element_id: $t.element_id,
                element_name: $t.element_name,
                repo_paths: ($el.repo_paths // []),
                subtask_total: $t.subtask_total,
                subtask_done: $t.subtask_done,
                last_moved_at: $t.last_moved_at,
                created_at: $t.created_at,
                review_cycle_count: $t.review_cycle_count,
                pr_url: $t.pr_url,
                pr_number: $t.pr_number,
                progress_note: $t.progress_note,
                autopr_reconsideration_pending: ($t.autopr_reconsideration_pending // false),
                autopr_reconsideration_event_id: $t.autopr_reconsideration_event_id,
                autopr_reconsideration_at: $t.autopr_reconsideration_at,
                autopr_run_requested_at: $t.autopr_run_requested_at,
                assigned_to_autopr: ($t.assigned_email == $email),
                # Keep attachment metadata available for ranking/debugging,
                # but never put short-lived signed storage URLs in card.json.
                attachments: (($t.attachments // []) | map(del(.storage_url)))
              }
          )
    ')"

    out="$(jq -c -n --argjson a "$out" --argjson b "$candidates" '$a + $b')"
done

# Repair one consumed-directive edge case without weakening ordinary decision
# binding. The resolver accepts only an explicit directive whose old bound note
# and current note are both the already_fixed refusal draft_pr forbids. Old
# migration_required rows deliberately stay settled until fresh owner action.
recovery_dir="$(mktemp -d)"
trap 'rm -rf "$recovery_dir"' EXIT
card_count="$(printf '%s' "$out" | jq 'length')"
for ((i = 0; i < card_count; i++)); do
    card="$(printf '%s' "$out" | jq -c ".[$i]")"
    pending="$(printf '%s' "$card" | jq -r '.autopr_reconsideration_pending // false')"
    progress_note="$(printf '%s' "$card" | jq -r '.progress_note // ""')"
    [ "$pending" != true ] || continue
    case "$progress_note" in
        *"[autopr:no-spec "*" already_fixed"*) ;;
        *) continue ;;
    esac
    project_id="$(printf '%s' "$card" | jq -r '.project_id')"
    task_id="$(printf '%s' "$card" | jq -r '.task_id')"
    history="$(mw_api GET "/matcha-work/projects/$project_id/tasks/$task_id/history" 2>/dev/null || printf '[]')"
    printf '%s' "$card" > "$recovery_dir/card.json"
    printf '%s' "$history" > "$recovery_dir/history.json"
    python3 "$SCRIPT_DIR/resolve-directive-policy.py" \
        --recover-consumed \
        --card "$recovery_dir/card.json" \
        --history "$recovery_dir/history.json" \
        --output "$recovery_dir/policy.json"
    event_id="$(jq -r '.source_event_id // empty' "$recovery_dir/policy.json")"
    [ -n "$event_id" ] || continue
    event_at="$(jq -r '.source_event_at // empty' "$recovery_dir/policy.json")"
    out="$(printf '%s' "$out" | jq -c --argjson i "$i" --arg event "$event_id" --arg at "$event_at" '
      .[$i].autopr_reconsideration_pending = true
      | .[$i].autopr_reconsideration_event_id = $event
      | .[$i].autopr_reconsideration_at = (if $at == "" then null else $at end)
    ')"
done

# Unassigned cards were admitted only as recovery probes. Keep them only when
# the explicit context event above restored durable one-run authorization.
out="$(printf '%s' "$out" | jq -c '
  map(select(.assigned_to_autopr
             or (.autopr_reconsideration_pending // false)
             or ((.autopr_run_requested_at // null) != null)))
  | map(del(.assigned_to_autopr))
')"

printf '%s\n' "$out"
