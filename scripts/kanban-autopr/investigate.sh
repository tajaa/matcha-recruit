#!/usr/bin/env bash
# Ask Codex to implement (todo) or address feedback on (rework) one
# kanban card, and write a structured report. Leaves any fix unstaged in the
# working tree; never commits.
#
# Usage: ./investigate.sh card.json report.md raw-decision.json
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

CARD_FILE="${1:?usage: investigate.sh card.json report.md raw-decision.json}"
REPORT_FILE="${2:?usage: investigate.sh card.json report.md raw-decision.json}"
RAW_DECISION_FILE="${3:?usage: investigate.sh card.json report.md raw-decision.json}"
REPO_ROOT="${AUTOPR_WORKSPACE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
REPO="${GITHUB_REPOSITORY:-}"
WORK_DIR="$(mktemp -d)"
# checkpoint.sh reads this to tell a genuine step timeout from a crash: only a
# run that was killed may pause the card behind a human approval. A harness or
# model failure must fail loudly and stay selectable instead.
INVESTIGATION_EXIT_FILE="${AUTOPR_INVESTIGATION_EXIT_FILE:-${RUNNER_TEMP:+$RUNNER_TEMP/investigation-exit-code}}"
[ -z "$INVESTIGATION_EXIT_FILE" ] || rm -f "$INVESTIGATION_EXIT_FILE"
_investigate_cleanup() {
    local status=$?
    [ -z "$INVESTIGATION_EXIT_FILE" ] \
        || printf '%s\n' "$status" > "$INVESTIGATION_EXIT_FILE" 2>/dev/null \
        || true
    rm -rf "$WORK_DIR"
}
trap _investigate_cleanup EXIT

# The report must live outside the git workspace: `git add --all` in
# publish.sh would otherwise stage a file the model wrote under its own
# control, and it would ship inside the PR diff rather than becoming the PR
# body.
for output_file in "$REPORT_FILE" "$RAW_DECISION_FILE"; do
    case "$(cd "$(dirname "$output_file")" 2>/dev/null && pwd)/$(basename "$output_file")" in
        "$REPO_ROOT"/*) die "model output must be outside the repo (got $output_file)" ;;
    esac
    rm -f "$output_file"
done

MODE="$(jq -r '.mode' "$CARD_FILE")"
PROJECT_ID="$(jq -r '.project_id' "$CARD_FILE")"
TASK_ID="$(jq -r '.task_id' "$CARD_FILE")"
ID8="$(jq -r '.id8' "$CARD_FILE")"

ATTACH_ARGS=()
FEEDBACK_CHECKPOINT='{"comment_id":"","review_id":""}'
RESUME_PATCH=""
PRIOR_CHECKPOINT_FILE="$WORK_DIR/prior-checkpoint.json"
printf 'null\n' > "$PRIOR_CHECKPOINT_FILE"

# Resume a prior checkpoint only inside the disposable sandbox.
prior_checkpoint="$($SCRIPT_DIR/checkpoint.sh latest "$CARD_FILE")"
if [ -n "$prior_checkpoint" ]; then
    if [ -s "$prior_checkpoint/metadata.json" ]; then
        cp "$prior_checkpoint/metadata.json" "$PRIOR_CHECKPOINT_FILE"
    fi
    [ ! -s "$prior_checkpoint/model.patch" ] || RESUME_PATCH="$prior_checkpoint/model.patch"
    for checkpoint_input in report.md decision.json transcript.log; do
        [ ! -s "$prior_checkpoint/$checkpoint_input" ] \
            || ATTACH_ARGS+=(-f "$prior_checkpoint/$checkpoint_input")
    done
fi

# Consume any "run now" request as soon as this card is actually picked up.
# The claim is what stops the one-minute watcher re-dispatching for a card
# whose run then crashes, is capped, or produces no PR. Non-fatal: losing the
# claim must never abandon an investigation that is otherwise ready to go.
if [ "$(jq -r '.autopr_run_requested_at // empty' "$CARD_FILE")" != "" ]; then
    mw_api POST "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/autopr/run-claim" '{}' \
        >/dev/null 2>&1 \
        || printf 'kanban-autopr: warning: could not claim the run request for %s\n' \
            "$TASK_ID" >&2
fi

# Fetch the same evidence the task detail UI uses. In particular, the history
# endpoint carries discussion notes, review boundaries, rejected-checklist
# reasons/severities, and attachment ids. This is required in BOTH modes: a
# card manually moved to changes_requested may have no existing PR, while a
# rework must know what earlier rounds already fixed.
subtasks="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/subtasks" 2>/dev/null || echo '[]')"
history="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/history" 2>/dev/null || echo '[]')"
files="$(mw_api GET "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/files" 2>/dev/null || echo '[]')"
printf '%s' "$subtasks" > "$WORK_DIR/subtasks.json"
printf '%s' "$history" > "$WORK_DIR/history.json"
printf '%s' "$files" > "$WORK_DIR/files.json"

# Only the exact decision-bound reconsideration event may grant operator
# directives. Card prose, comments, PR bodies, and unrelated history remain
# untrusted evidence. Resolve structured metadata plus the same event's body
# so context submitted before a parser upgrade remains actionable.
# Reuse the policy the runtime step already resolved when it hands one over.
# Resolving twice against two different reads of the board history lets the
# budgeted runtime and the authority stated in the model's prompt disagree
# about the same run.
DIRECTIVE_FILE="$WORK_DIR/directive-policy.json"
if [ -n "${AUTOPR_DIRECTIVE_POLICY_FILE:-}" ] && [ -s "${AUTOPR_DIRECTIVE_POLICY_FILE}" ]; then
    jq '{directives:(.directives // []),
         test_route:(.test_route // null),
         source_event_id:(.source_event_id // null)}' \
        "$AUTOPR_DIRECTIVE_POLICY_FILE" > "$DIRECTIVE_FILE"
else
    python3 "$SCRIPT_DIR/resolve-directive-policy.py" \
        --card "$CARD_FILE" --history "$WORK_DIR/history.json" \
        --output "$DIRECTIVE_FILE"
fi

# An approved test tenant may be exercised by the trusted browser harness.
# Credentials never enter context.json or msandbox; only a screenshot and
# bounded same-origin console/network status reach the coding model.
TEST_TENANT_EVIDENCE_FILE="$WORK_DIR/test-tenant-evidence.json"
TEST_TENANT_SCREENSHOT="$WORK_DIR/test-tenant-reproduction.png"
EVIDENCE_PYTHON="${AUTOPR_EVIDENCE_PYTHON:-$REPO_ROOT/server/venv/bin/python}"
[ -x "$EVIDENCE_PYTHON" ] || EVIDENCE_PYTHON=python3
"$EVIDENCE_PYTHON" "$SCRIPT_DIR/collect-test-tenant-evidence.py" \
    --policy "$DIRECTIVE_FILE" \
    --output "$TEST_TENANT_EVIDENCE_FILE" \
    --screenshot "$TEST_TENANT_SCREENSHOT"

# Production access stays in this trusted shell. Give the coding model bounded,
# redacted diagnostics only: recent error reports, recent error-level container
# signals, live migration state, and the commits between the live image and the
# checked-out branch. A card about a missing column can therefore be recognized
# as schema drift; a card reporting behavior from an older build can be checked
# against changes already merged after that build.
printf '[]' > "$WORK_DIR/production-errors.json"
: > "$WORK_DIR/production-log-signals.txt"
printf '[]' > "$WORK_DIR/changes-since-production.json"
if jq -e '.production' "$CARD_FILE" >/dev/null 2>&1; then
    if [ -n "${SSH_KEY:-}" ]; then
        if ! "$REPO_ROOT/scripts/error-autofix/collect.sh" \
            --hours "${AUTOPR_PROD_ERROR_HOURS:-24}" \
            --limit "${AUTOPR_PROD_ERROR_LIMIT:-25}" \
            > "$WORK_DIR/production-errors.json" 2> "$WORK_DIR/production-errors.stderr"; then
            jq -n --rawfile detail "$WORK_DIR/production-errors.stderr" \
                '[{kind:"collection_unavailable",message:($detail | .[0:1000])}]' \
                > "$WORK_DIR/production-errors.json"
        else
            jq '.[0:10] | map(
                .message = ((.message // "")[0:2000])
                | .traceback = ((.traceback // "")[0:6000])
                | .context_excerpt = ((.context_excerpt // "")[0:1000])
              )' "$WORK_DIR/production-errors.json" \
                > "$WORK_DIR/production-errors.bounded.json"
            mv "$WORK_DIR/production-errors.bounded.json" "$WORK_DIR/production-errors.json"
        fi

        WINDOW_MINUTES="${AUTOPR_PROD_LOG_WINDOW_MINUTES:-120}" \
            EVIDENCE_FILE="$WORK_DIR/production-log-signals.txt" \
            "$REPO_ROOT/scripts/collect-silent-error-evidence.sh" \
            >/dev/null 2> "$WORK_DIR/production-logs.stderr" || true
    fi

    # Both components normally share one SHA. If a backend-only or
    # frontend-only deploy split them, keep both comparisons explicit.
    for component in backend frontend; do
        prod_sha="$(jq -r ".production.containers.${component}.git_sha // empty" "$CARD_FILE")"
        [ -n "$prod_sha" ] || continue
        path_scope="server"
        [ "$component" != frontend ] || path_scope="client"
        changes="$(git -C "$REPO_ROOT" log --max-count=100 --pretty=format:'%h %s' "$prod_sha..HEAD" -- \
            "$path_scope" 2>/dev/null || true)"
        row="$(jq -n --arg component "$component" --arg production_sha "$prod_sha" \
            --arg head_sha "$(git -C "$REPO_ROOT" rev-parse --short HEAD)" \
            --arg changes "$changes" \
            '{component:$component,production_sha:$production_sha,head_sha:$head_sha,commits:($changes | split("\n") | map(select(length > 0)))}')"
        jq --argjson row "$row" '. + [$row]' "$WORK_DIR/changes-since-production.json" \
            > "$WORK_DIR/changes-since-production.next"
        mv "$WORK_DIR/changes-since-production.next" "$WORK_DIR/changes-since-production.json"
    done
fi

# Attach a bounded, current-round-first set of the actual files. The JSON
# context still lists every file even when a large/old attachment is not
# downloaded, so the model can explain what evidence was unavailable rather
# than pretending the ticket had none.
ATTACHMENT_DIR="$WORK_DIR/attachments"
mkdir -p "$ATTACHMENT_DIR"
MAX_ATTACHMENT_COUNT="${AUTOPR_MAX_ATTACHMENT_COUNT:-12}"
MAX_ATTACHMENT_BYTES="${AUTOPR_MAX_ATTACHMENT_BYTES:-26214400}"
MAX_SINGLE_ATTACHMENT_BYTES="${AUTOPR_MAX_SINGLE_ATTACHMENT_BYTES:-10485760}"
current_round="$(jq -n \
    --slurpfile subtasks "$WORK_DIR/subtasks.json" \
    --slurpfile history "$WORK_DIR/history.json" '
    [
      ([$subtasks[0][]? | (.round_index // 1)] | max // 1),
      (([$history[0][]? | select(.event_type == "round_started")] | length) + 1)
    ] | max
')"
downloaded_bytes=0
downloaded_count=0
downloaded="[]"

while IFS= read -r file; do
    [ -n "$file" ] || continue
    [ "$downloaded_count" -lt "$MAX_ATTACHMENT_COUNT" ] || break

    url="$(printf '%s' "$file" | jq -r '.storage_url // empty')"
    filename="$(printf '%s' "$file" | jq -r '.filename // "attachment"')"
    declared_size="$(printf '%s' "$file" | jq -r '.file_size // 0')"
    [[ "$url" =~ ^https?:// ]] || continue
    [ "$declared_size" -le "$MAX_SINGLE_ATTACHMENT_BYTES" ] 2>/dev/null || continue
    [ $((downloaded_bytes + declared_size)) -le "$MAX_ATTACHMENT_BYTES" ] 2>/dev/null || continue

    safe_name="$(printf '%s' "$filename" | tr -cs '[:alnum:]_. -' '_' | cut -c1-120)"
    [ -n "$safe_name" ] || safe_name="attachment"
    local_path="$ATTACHMENT_DIR/$(printf '%02d' $((downloaded_count + 1)))-$safe_name"

    if ! curl -fLsS --max-time 30 --max-filesize "$MAX_SINGLE_ATTACHMENT_BYTES" \
        -o "$local_path" "$url"; then
        rm -f "$local_path"
        continue
    fi
    actual_size="$(wc -c < "$local_path" | tr -d '[:space:]')"
    if [ "$actual_size" -gt "$MAX_SINGLE_ATTACHMENT_BYTES" ] \
        || [ $((downloaded_bytes + actual_size)) -gt "$MAX_ATTACHMENT_BYTES" ]; then
        rm -f "$local_path"
        continue
    fi

    downloaded_bytes=$((downloaded_bytes + actual_size))
    downloaded_count=$((downloaded_count + 1))
    downloaded="$(jq -c -n --argjson rows "$downloaded" --argjson file "$file" \
        --arg path "$local_path" '$rows + [(($file | del(.storage_url)) + {local_path: $path})]')"
    ATTACH_ARGS+=(-f "$local_path")
done < <(printf '%s' "$files" | jq -c --argjson round "$current_round" \
    '((map(select((.round_index // 1) == $round)) | sort_by(.created_at // "") | reverse)
      + (map(select((.round_index // 1) != $round)) | sort_by(.created_at // "") | reverse))[]')

CONTEXT_FILE="$WORK_DIR/context.json"
jq -n \
    --slurpfile card "$CARD_FILE" \
    --slurpfile subtasks "$WORK_DIR/subtasks.json" \
    --slurpfile history "$WORK_DIR/history.json" \
    --slurpfile files "$WORK_DIR/files.json" \
    --slurpfile directive_policy "$DIRECTIVE_FILE" \
    --slurpfile test_tenant_evidence "$TEST_TENANT_EVIDENCE_FILE" \
    --slurpfile production_errors "$WORK_DIR/production-errors.json" \
    --slurpfile changes_since_production "$WORK_DIR/changes-since-production.json" \
    --slurpfile prior_checkpoint "$PRIOR_CHECKPOINT_FILE" \
    --rawfile production_log_signals "$WORK_DIR/production-log-signals.txt" \
    --argjson downloaded "$downloaded" \
    '{card: $card[0], directive_policy: $directive_policy[0], prior_checkpoint: $prior_checkpoint[0], test_tenant_evidence: $test_tenant_evidence[0], production: ($card[0].production // null), changes_since_production: $changes_since_production[0], production_recent_errors: $production_errors[0], production_log_signals: $production_log_signals, subtasks: $subtasks[0], history: $history[0], files: ($files[0] | map(del(.storage_url))), downloaded_attachments: $downloaded}' \
    > "$CONTEXT_FILE"

if [ -s "$TEST_TENANT_SCREENSHOT" ]; then
    ATTACH_ARGS+=( -f "$TEST_TENANT_SCREENSHOT" )
fi

# Put the structured brief first, then the locally downloaded evidence. macOS
# still ships Bash 3.2, where expanding an empty array under `set -u` raises an
# "unbound variable" error. Branch explicitly so cards without attachments
# reach Codex instead of failing before the investigation starts.
if [ "${#ATTACH_ARGS[@]}" -gt 0 ]; then
    ATTACH_ARGS=(-f "$CONTEXT_FILE" "${ATTACH_ARGS[@]}")
else
    ATTACH_ARGS=(-f "$CONTEXT_FILE")
fi

if [ "$MODE" = rework ]; then
    PROMPT_FILE="$SCRIPT_DIR/_prompt_rework.txt"
    branch="bot/task-$ID8"
    pr_number="$(gh pr list --repo "$REPO" --head "$branch" --state open --limit 1 --json number --jq '.[0].number // empty')"
    if [ -n "$pr_number" ]; then
        if gh pr view "$pr_number" --repo "$REPO" --json reviews,comments > "$WORK_DIR/feedback.json" 2>/dev/null; then
            FEEDBACK_CHECKPOINT="$("$SCRIPT_DIR/decision.sh" feedback-snapshot "$WORK_DIR/feedback.json")"
        else
            echo '{}' > "$WORK_DIR/feedback.json"
            # Preserve the prior PR-body checkpoint when GitHub feedback could
            # not be read. Writing empty ids would make every old answer appear
            # new and spin this draft on each cooldown.
            FEEDBACK_CHECKPOINT=null
        fi
    else
        echo '{}' > "$WORK_DIR/feedback.json"
        FEEDBACK_CHECKPOINT='{"comment_id":"","review_id":""}'
    fi
    ATTACH_ARGS+=(-f "$WORK_DIR/feedback.json")
else
    PROMPT_FILE="$SCRIPT_DIR/_prompt_todo.txt"
fi

# Defense in depth: this step's workflow env should already omit these, but
# strip them here too in case a future edit adds them back. The production path
# invokes a dedicated msandbox bridge; direct host execution exists only as an
# explicit local test seam and is rejected inside GitHub Actions. Mirror the
# sandboxed model's terminal output to one local, mode-600 observer log: GitHub
# does not expose an in-progress step's stdout, while the operator explicitly
# needs to see Codex investigate and edit the task live in tmux.
LIVE_LOG="${AUTOPR_LIVE_LOG:-$HOME/Library/Logs/matcha-kanban-autopr-live.log}"
SANDBOX_RUNNER="${AUTOPR_SANDBOX_RUNNER:-$SCRIPT_DIR/run-codex-sandboxed.sh}"
TEST_DIRECT="${AUTOPR_SANDBOX_TEST_DIRECT:-0}"
[ "$TEST_DIRECT" != 1 ] || [ "${GITHUB_ACTIONS:-}" != true ] \
    || die "direct Codex execution is forbidden in GitHub Actions"
live_log_ready=false
if mkdir -p "$(dirname "$LIVE_LOG")" 2>/dev/null; then
    if (umask 077; {
        printf 'MATCHA KANBAN AUTOPR · CODEX LIVE STREAM\n'
        printf 'run %s · task %s · mode %s · execution %s · started %s\n\n' \
            "${GITHUB_RUN_ID:-local}" "$ID8" "$MODE" \
            "$([ "$TEST_DIRECT" = 1 ] && printf test-direct || printf msandbox)" \
            "$(date '+%Y-%m-%d %H:%M:%S %Z')"
    } > "$LIVE_LOG") 2>/dev/null; then
        live_log_ready=true
    fi
fi

run_codex() {
    [ -x "$SANDBOX_RUNNER" ] || die "sandbox runner is not executable: $SANDBOX_RUNNER"
    runner_env=(
        env -u GH_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY
        -u AUTOPR_TEST_TENANT_EMAIL -u AUTOPR_TEST_TENANT_PASSWORD
        AUTOPR_CODEX_MODEL=gpt-5.6-sol
        AUTOPR_CODEX_REASONING_EFFORT=medium
        AUTOPR_TASK_ID="$TASK_ID"
    )
    [ -z "$RESUME_PATCH" ] || runner_env+=(AUTOPR_RESUME_PATCH="$RESUME_PATCH")
    "${runner_env[@]}" "$SANDBOX_RUNNER" "$PROMPT_FILE" "$REPORT_FILE" "$RAW_DECISION_FILE" \
        "${ATTACH_ARGS[@]}"
}

codex_pass() {
    if [ "$live_log_ready" = true ]; then
        run_codex 2>&1 | tee -a "$LIVE_LOG"
        codex_rc="${PIPESTATUS[0]}"
    else
        run_codex
        codex_rc=$?
    fi
    if [ "$codex_rc" -ne 0 ]; then
        [ "$live_log_ready" != true ] || printf '\n[FAILED] Codex exited %s at %s\n' \
            "$codex_rc" "$(date '+%H:%M:%S %Z')" >> "$LIVE_LOG"
        die "Codex investigation exited $codex_rc"
    fi
    [ "$live_log_ready" != true ] || printf '\n[COMPLETE] Codex finished at %s\n' \
        "$(date '+%H:%M:%S %Z')" >> "$LIVE_LOG"

    if [ ! -s "$REPORT_FILE" ]; then
        die "investigation produced no report at $REPORT_FILE"
    fi

    for heading in '### Summary' '### Changes' '### Blast radius' '### Confidence'; do
        if ! grep -qF "$heading" "$REPORT_FILE"; then
            die "report is missing required heading: $heading"
        fi
    done
}

codex_pass

# One corrective retry when the returned outcome contradicts the card owner's
# own directive. The owner already authorized this work, so a refusal the
# directive forbids is a model error, not a safety stop — and dying here would
# leave the card showing the stale refusal with no sign the authorization was
# ever read. The retry re-states the directive as a rejection of the exact
# decision just produced; the trusted validation below still has the last word.
if [ -s "$DIRECTIVE_FILE" ] \
    && ! "$SCRIPT_DIR/decision.sh" directive-ok "$RAW_DECISION_FILE" "$DIRECTIVE_FILE" 2>/dev/null; then
    echo "kanban-autopr: decision violated the operator directive; retrying once" >&2
    # The rejected pass concluded "no safe action", so it must not leave edits
    # behind for the retry to inherit.
    git -C "$REPO_ROOT" reset --hard HEAD >/dev/null 2>&1 || true
    git -C "$REPO_ROOT" clean -fd >/dev/null 2>&1 || true
    CORRECTION_FILE="$WORK_DIR/directive-correction.json"
    jq -n --slurpfile policy "$DIRECTIVE_FILE" --slurpfile rejected "$RAW_DECISION_FILE" \
        '{kind: "directive_violation",
          directive_policy: $policy[0],
          rejected_decision: {outcome: $rejected[0].outcome,
                              no_safe_action_reason: $rejected[0].no_safe_action_reason},
          instruction: "The authorized card owner issued the directives above and the trusted harness REJECTED the decision you just returned. Investigate again and return a decision that honors them. Under draft_pr you may not return already_fixed or migration_required: implement the repo-local change, and when it needs a schema change, author a new server/alembic/versions/*.py version file for human review and never run it against any database. questions_only is allowed only when a specific missing product decision blocks even a partial implementation. policy_blocked and external_dependency remain available only for a genuine safety or third-party blocker."}' \
        > "$CORRECTION_FILE"
    ATTACH_ARGS+=(-f "$CORRECTION_FILE")
    : > "$REPORT_FILE"
    : > "$RAW_DECISION_FILE"
    codex_pass
fi

# Codex's JSON is data, not authority. Keep the normalized result outside
# the repository too: publish.sh is the only script permitted to decide what
# reaches GitHub or the board.
"$SCRIPT_DIR/decision.sh" normalize "$RAW_DECISION_FILE" "$RAW_DECISION_FILE.normalized" "$DIRECTIVE_FILE"
jq --argjson checkpoint "$FEEDBACK_CHECKPOINT" \
    '. + {feedback_checkpoint: $checkpoint}' \
    "$RAW_DECISION_FILE.normalized" > "$RAW_DECISION_FILE.with-feedback"
mv "$RAW_DECISION_FILE.with-feedback" "$RAW_DECISION_FILE.normalized"
mv "$RAW_DECISION_FILE.normalized" "$RAW_DECISION_FILE"
"$SCRIPT_DIR/checkpoint.sh" consume "$CARD_FILE"
