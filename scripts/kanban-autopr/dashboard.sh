#!/usr/bin/env bash
# Read-only 24-hour operator dashboard for the Kanban AutoPR tmux session.
# It intentionally uses collect.sh + select.sh in read-only mode so the view
# answers "what is next?" with the same rules as the real workflow.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
WORKFLOW="${AUTOPR_WORKFLOW:-kanban-autopr.yml}"
ERROR_WORKFLOW="${AUTOPR_ERROR_WORKFLOW:-silent-error-autofix.yml}"
AUDIT_WORKFLOW="${AUTOPR_AUDIT_WORKFLOW:-autopr-self-audit.yml}"
ADMIN_UPDATES_WORKFLOW="${AUTOPR_ADMIN_UPDATES_WORKFLOW:-admin-updates-autopublish.yml}"
REF="${AUTOPR_REF:-main}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
REFRESH_SECONDS="${AUTOPR_DASHBOARD_REFRESH_SECONDS:-60}"
CARD_SNAPSHOT="${AUTOPR_CARD_SNAPSHOT:-$USER_HOME/Library/Caches/matcha-kanban-autopr/cards.json}"

utc_24_hours_ago() {
    date -u -v-24H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ
}

safe_gh() {
    "$GH_BIN" "$@" 2>/dev/null || printf '[]\n'
}

render_dashboard() {
    local runs kanban_runs error_runs audit_runs admin_updates_runs open_prs open_kanban open_errors open_audits merged_prs cards selected selected_rc cutoff snapshot_tmp
    cutoff="$(utc_24_hours_ago)"
    kanban_runs="$(safe_gh run list --repo "$REPO" --workflow "$WORKFLOW" --branch "$REF" --limit 100 \
        --json databaseId,status,conclusion,event,createdAt,updatedAt,url,displayTitle)"
    error_runs="$(safe_gh run list --repo "$REPO" --workflow "$ERROR_WORKFLOW" --branch "$REF" --limit 100 \
        --json databaseId,status,conclusion,event,createdAt,updatedAt,url,displayTitle)"
    audit_runs="$(safe_gh run list --repo "$REPO" --workflow "$AUDIT_WORKFLOW" --branch "$REF" --limit 100 \
        --json databaseId,status,conclusion,event,createdAt,updatedAt,url,displayTitle)"
    admin_updates_runs="$(safe_gh run list --repo "$REPO" --workflow "$ADMIN_UPDATES_WORKFLOW" --branch "$REF" --limit 100 \
        --json databaseId,status,conclusion,event,createdAt,updatedAt,url,displayTitle)"
    runs="$(jq -cn --argjson kanban "$kanban_runs" --argjson errors "$error_runs" --argjson audit "$audit_runs" \
      --argjson admin_updates "$admin_updates_runs" '
      (($kanban | map(. + {lane:"kanban"})) + ($errors | map(. + {lane:"errors"})) +
       ($audit | map(. + {lane:"self-audit"})) + ($admin_updates | map(. + {lane:"admin-updates"})))
      | sort_by(.createdAt // "") | reverse')"
    open_kanban="$(safe_gh pr list --repo "$REPO" --state open --label autopr --limit 100 \
        --json number,title,isDraft,headRefName,updatedAt,labels,url)"
    open_errors="$(safe_gh pr list --repo "$REPO" --state open --label autofix --limit 100 \
        --json number,title,isDraft,headRefName,updatedAt,labels,url)"
    open_audits="$(safe_gh pr list --repo "$REPO" --state open --label autopr-self-audit --limit 100 \
        --json number,title,isDraft,headRefName,updatedAt,labels,url)"
    open_prs="$(jq -cn --argjson kanban "$open_kanban" --argjson errors "$open_errors" --argjson audit "$open_audits" \
        '$kanban + $errors + $audit | unique_by(.number) | sort_by(.updatedAt // "") | reverse')"
    merged_prs="$(safe_gh pr list --repo "$REPO" --state merged --label autopr --limit 100 \
        --json number,title,mergedAt,url)"

    cards="[]"
    if ! cards="$($SCRIPT_DIR/collect.sh 2>/dev/null)"; then
        cards="[]"
    fi
    # Share the already-collected board snapshot with the PR pane. This avoids
    # four extra production API bundle reads every ten seconds merely to turn
    # bot/task-<id> into a human-readable card title.
    if mkdir -p "$(dirname "$CARD_SNAPSHOT")" 2>/dev/null; then
        snapshot_tmp="$CARD_SNAPSHOT.$$"
        if (umask 077; printf '%s' "$cards" > "$snapshot_tmp") 2>/dev/null; then
            mv "$snapshot_tmp" "$CARD_SNAPSHOT" 2>/dev/null || true
        fi
    fi
    selected="$(AUTOPR_SELECT_READ_ONLY=true GITHUB_REPOSITORY="$REPO" \
        "$SCRIPT_DIR/select.sh" <(printf '%s' "$cards") 2>/dev/null)"
    selected_rc=$?
    [ "$selected_rc" -eq 0 ] || selected=""

    [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ] || clear
    printf 'MATCHA KANBAN AUTOPR · 24 HOUR VIEW\n'
    printf 'Updated %s · refresh %ss\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$REFRESH_SECONDS"

    printf 'WORKFLOW NOW · '
    if ! printf '%s' "$runs" | jq -r '
      [.[] | select(.status | IN("queued", "in_progress", "requested", "waiting", "pending"))]
      | if length == 0 then "idle" else .[0] | "\(.lane) #\(.databaseId)  \(.status)" end
    '; then
        printf 'GitHub unavailable\n'
    fi

    printf 'UP NEXT · '
    if [ -n "$selected" ]; then
        printf '%s' "$selected" | jq -r '"[\(.board_column)] \(.project_title) · \(.title[0:45]) · \(.id8)"'
    else
        printf 'none immediately eligible\n'
    fi

    printf '\nBOARD QUEUE · '
    printf '%s' "$cards" | jq -r '
      if length == 0 then "empty or API unavailable" else
        (((map(select(.board_column == "changes_requested")) | length) | tostring) + " CR · "
          + ((map(select(.board_column == "todo")) | length) | tostring) + " TODO"),
        (sort_by((if .board_column == "changes_requested" then 0 else 1 end), (.last_moved_at // .created_at))[:4][] |
          "  " + (if .board_column == "changes_requested" then "CR  " else "TODO" end)
          + " " + (.project_title // "?") + " · " + (.title[0:50])
          + (if (.progress_note // "") | test("awaiting answers"; "i") then "  [WAITING]" else "" end))
      end
    '

    printf '\nOPEN AUTO PRS\n'
    printf '%s' "$open_prs" | jq -r '
      if length == 0 then "  none" else .[:10][] |
        "  #\(.number) " + (if .isDraft then "DRAFT" else "OPEN " end) + " " + (.title[0:50])
        + (if ([.labels[].name] | index("autopr-awaiting-input")) then "  [WAITING]" else "" end)
      end
    '

    printf 'MERGED AUTO PRS · LAST 24 HOURS · '
    printf '%s' "$merged_prs" | jq -r --arg cutoff "$cutoff" '
      [.[] | select((.mergedAt // "") >= $cutoff)]
      | if length == 0 then "none" else [.[0:4][] | "#" + (.number | tostring)] | join(", ") end
    '

    printf '\nWORKFLOW RUNS · LAST 24 HOURS\n'
    printf '%s' "$runs" | jq -r --arg cutoff "$cutoff" '
      [.[] | select((.createdAt // "") >= $cutoff)][:4]
      | if length == 0 then "  none" else .[] |
        "  #\(.databaseId)  \(.createdAt[11:16])Z  " + .lane + " · " +
        (if .status == "completed" then (.conclusion // "completed") else .status end) + "  " + .event
      end
    '
}

while :; do
    render_dashboard
    [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] || exit 0
    sleep "$REFRESH_SECONDS"
done
