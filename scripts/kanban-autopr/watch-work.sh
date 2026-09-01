#!/usr/bin/env bash
# Live Codex pane. investigate.sh tees the model's real terminal
# stream to a local file because GitHub does not expose in-progress step stdout.
# GitHub is polled less often than the local log so this stays visually live
# without turning the observer into an API-heavy execution path.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
REPO="${AUTOPR_REPO:-tajaa/matcha-recruit}"
WORKFLOW="${AUTOPR_WORKFLOW:-kanban-autopr.yml}"
ERROR_WORKFLOW="${AUTOPR_ERROR_WORKFLOW:-silent-error-autofix.yml}"
AUDIT_WORKFLOW="${AUTOPR_AUDIT_WORKFLOW:-autopr-self-audit.yml}"
ADMIN_UPDATES_WORKFLOW="${AUTOPR_ADMIN_UPDATES_WORKFLOW:-admin-updates-autopublish.yml}"
GH_BIN="${AUTOPR_GH_BIN:-/opt/homebrew/bin/gh}"
LIVE_LOG="${AUTOPR_LIVE_LOG:-$USER_HOME/Library/Logs/matcha-kanban-autopr-live.log}"
REFRESH_SECONDS="${AUTOPR_WORK_REFRESH_SECONDS:-2}"
STATUS_REFRESH_SECONDS="${AUTOPR_WORK_STATUS_REFRESH_SECONDS:-10}"
MAX_ITERATIONS="${AUTOPR_DASHBOARD_MAX_ITERATIONS:-0}"
PACIFIC_TZ="${AUTOPR_DASHBOARD_TZ:-America/Los_Angeles}"

RUN_ID=""
RUN_STATUS="idle"
RUN_LANE=""
STEP_LINE=""
LAST_STATUS_REFRESH=0

refresh_workflow_status() {
    local now runs kanban_runs error_runs audit_runs admin_updates_runs active details
    now="$(date +%s)"
    if [ "${AUTOPR_DASHBOARD_ONCE:-0}" != 1 ] \
        && [ $((now - LAST_STATUS_REFRESH)) -lt "$STATUS_REFRESH_SECONDS" ]; then
        return 0
    fi
    LAST_STATUS_REFRESH="$now"

    kanban_runs="$($GH_BIN run list --repo "$REPO" --workflow "$WORKFLOW" --limit 10 \
        --json databaseId,status,createdAt 2>/dev/null || printf '[]')"
    error_runs="$($GH_BIN run list --repo "$REPO" --workflow "$ERROR_WORKFLOW" --limit 10 \
        --json databaseId,status,createdAt 2>/dev/null || printf '[]')"
    audit_runs="$($GH_BIN run list --repo "$REPO" --workflow "$AUDIT_WORKFLOW" --limit 10 \
        --json databaseId,status,createdAt 2>/dev/null || printf '[]')"
    admin_updates_runs="$($GH_BIN run list --repo "$REPO" --workflow "$ADMIN_UPDATES_WORKFLOW" --limit 10 \
        --json databaseId,status,createdAt 2>/dev/null || printf '[]')"
    runs="$(jq -cn --argjson kanban "$kanban_runs" --argjson errors "$error_runs" --argjson audit "$audit_runs" \
      --argjson admin_updates "$admin_updates_runs" '
      (($kanban | map(. + {lane:"kanban"})) + ($errors | map(. + {lane:"errors"})) +
       ($audit | map(. + {lane:"self-audit"})) + ($admin_updates | map(. + {lane:"admin-updates"})))
      | sort_by(.createdAt // "") | reverse')"
    active="$(printf '%s' "$runs" | jq -c \
        '[.[] | select(.status | IN("queued", "in_progress", "requested", "waiting", "pending"))][0] // .[0] // {}' 2>/dev/null)"
    RUN_ID="$(printf '%s' "$active" | jq -r '.databaseId // empty' 2>/dev/null)"
    RUN_STATUS="$(printf '%s' "$active" | jq -r '.status // "idle"' 2>/dev/null)"
    RUN_LANE="$(printf '%s' "$active" | jq -r '.lane // ""' 2>/dev/null)"
    STEP_LINE=""
    if [ -n "$RUN_ID" ] && [ "$RUN_STATUS" != idle ]; then
        details="$($GH_BIN run view "$RUN_ID" --repo "$REPO" --json jobs 2>/dev/null || printf '{"jobs":[]}')"
        STEP_LINE="$(printf '%s' "$details" | jq -r '
          [.jobs[]? as $job | $job.steps[]? |
            select(.status == "in_progress") | ($job.name + " · " + .name)][0] // empty
        ' 2>/dev/null)"
    fi
}

sanitize_model_stream() {
    # The model process has GitHub, Matcha, SSH, and EC2 credentials removed.
    # These filters are extra local-display protection for common token forms
    # and any PEM block a tool might accidentally print from the checkout.
    awk '
      /-----BEGIN .*PRIVATE KEY-----/ {print "[REDACTED PRIVATE KEY]"; pem=1; next}
      /-----END .*PRIVATE KEY-----/ {pem=0; next}
      !pem {print}
    ' | sed -E \
      -e 's/(Bearer )[A-Za-z0-9._~+\/=:-]+/\1[REDACTED]/g' \
      -e 's/sk-[A-Za-z0-9_-]{12,}/[REDACTED_OPENAI_KEY]/g' \
      -e 's/gh[pousr]_[A-Za-z0-9]{12,}/[REDACTED_GITHUB_TOKEN]/g' \
      -e 's/github_pat_[A-Za-z0-9_]{12,}/[REDACTED_GITHUB_TOKEN]/g' \
      -e 's/AKIA[0-9A-Z]{16}/[REDACTED_AWS_KEY]/g'
}

render_work_snapshot() {
    local pane_rows log_lines pids sandbox_project
    refresh_workflow_status
    pane_rows="$(tput lines 2>/dev/null || printf '24')"
    log_lines=$((pane_rows - 8))
    [ "$log_lines" -ge 6 ] || log_lines=6

    printf 'LIVE CODEX WORK · %s\n' "$(TZ="$PACIFIC_TZ" date '+%I:%M:%S %p %Z' | sed 's/^0//')"
    case "$RUN_LANE" in
        errors) sandbox_project=matcha-error-autofix-sandbox ;;
        self-audit) sandbox_project=matcha-autopr-self-audit-sandbox ;;
        *) sandbox_project=matcha-kanban-autopr-sandbox ;;
    esac
    printf 'EXECUTION msandbox · %s\n' "${AUTOPR_SANDBOX_PROJECT_NAME:-$sandbox_project}"
    if [ -n "$RUN_ID" ]; then
        printf 'RUN %s #%s · %s\n' "$RUN_LANE" "$RUN_ID" "$RUN_STATUS"
        [ -z "$STEP_LINE" ] || printf 'STEP %s\n' "$STEP_LINE"
    else
        printf 'RUN idle\n'
    fi

    pids="$(pgrep -f 'codex exec' 2>/dev/null | paste -sd, - 2>/dev/null || true)"
    if [ -n "$pids" ]; then
        printf 'PROCESS '
        ps -p "$pids" -o pid=,etime=,comm= 2>/dev/null | paste -sd' ' - || true
    fi

    printf '\nMODEL STREAM · latest %s lines\n' "$log_lines"
    if [ -s "$LIVE_LOG" ]; then
        sanitize_model_stream < "$LIVE_LOG" | tail -n "$log_lines"
    else
        printf 'Waiting for investigate.sh to start Codex.\n'
        printf 'The stream will appear here without opening GitHub logs.\n'
    fi
}

if [ "${AUTOPR_DASHBOARD_ONCE:-0}" = 1 ]; then
    render_work_snapshot
    exit 0
fi

# The interactive pane is an append-only transcript. Redrawing it with
# `clear` erased tmux scrollback and made earlier model work impossible to
# inspect. Emit status only when it changes and append each sanitized model
# line once; tmux owns the bounded history.
LAST_STATUS=""
STREAM_SIGNATURE=""
STREAM_LINES=0
WAITING_SHOWN=0
ITERATION=0
SANITIZED_LOG="$(mktemp "${TMPDIR:-/tmp}/matcha-autopr-live.XXXXXX")" || {
    printf 'Could not create a private live-work display buffer.\n' >&2
    exit 1
}
trap 'rm -f -- "$SANITIZED_LOG"' EXIT

emit_status_change() {
    local current pids sandbox_project
    refresh_workflow_status
    current="$RUN_LANE|$RUN_ID|$RUN_STATUS|$STEP_LINE"
    [ "$current" != "$LAST_STATUS" ] || return 0
    LAST_STATUS="$current"
    case "$RUN_LANE" in
        errors) sandbox_project=matcha-error-autofix-sandbox ;;
        self-audit) sandbox_project=matcha-autopr-self-audit-sandbox ;;
        *) sandbox_project=matcha-kanban-autopr-sandbox ;;
    esac
    printf '\n[STATUS %s] msandbox · %s\n' "$(TZ="$PACIFIC_TZ" date '+%I:%M:%S %p %Z' | sed 's/^0//')" \
        "${AUTOPR_SANDBOX_PROJECT_NAME:-$sandbox_project}"
    if [ -n "$RUN_ID" ]; then
        printf 'RUN %s #%s · %s\n' "$RUN_LANE" "$RUN_ID" "$RUN_STATUS"
        [ -z "$STEP_LINE" ] || printf 'STEP %s\n' "$STEP_LINE"
    else
        printf 'RUN idle\n'
    fi
    pids="$(pgrep -f 'codex exec' 2>/dev/null | paste -sd, - 2>/dev/null || true)"
    [ -z "$pids" ] || printf 'PROCESS pid %s\n' "$pids"
}

append_model_stream() {
    local signature line_count
    if [ ! -s "$LIVE_LOG" ]; then
        if [ "$WAITING_SHOWN" = 0 ]; then
            printf '\nWaiting for investigate.sh to start Codex.\n'
            printf 'New model output will append here without replacing scrollback.\n'
            WAITING_SHOWN=1
        fi
        return 0
    fi

    sanitize_model_stream < "$LIVE_LOG" > "$SANITIZED_LOG"
    signature="$(sed -n '2p' "$SANITIZED_LOG")"
    line_count="$(wc -l < "$SANITIZED_LOG" | tr -d '[:space:]')"
    if [ "$signature" != "$STREAM_SIGNATURE" ] || [ "$line_count" -lt "$STREAM_LINES" ]; then
        [ -z "$STREAM_SIGNATURE" ] || printf '\n--- NEW CODEX RUN ---\n'
        STREAM_SIGNATURE="$signature"
        STREAM_LINES=0
        WAITING_SHOWN=0
    fi
    if [ "$line_count" -gt "$STREAM_LINES" ]; then
        [ "$STREAM_LINES" -ne 0 ] || printf '\nMODEL STREAM · current run\n'
        sed -n "$((STREAM_LINES + 1)),${line_count}p" "$SANITIZED_LOG"
        STREAM_LINES="$line_count"
    fi
}

printf 'LIVE CODEX WORK · append-only history\n'
printf 'Scroll with mouse/trackpad or Ctrl-b [ · detach with Ctrl-b d\n'
while :; do
    emit_status_change
    append_model_stream
    ITERATION=$((ITERATION + 1))
    if [ "$MAX_ITERATIONS" -gt 0 ] && [ "$ITERATION" -ge "$MAX_ITERATIONS" ]; then
        exit 0
    fi
    sleep "$REFRESH_SECONDS"
done
