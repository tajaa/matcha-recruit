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
HANDOFF_CONTROL="$(dirname "$SCRIPT_DIR")/msandbox/autopr_control.py"
export AUTOPR_INVOCATION_ID="${AUTOPR_INVOCATION_ID:-local-$$-$(date +%s)}"
export AUTOPR_CONTINUATION_PID=$$
REPO_ROOT="${AUTOPR_WORKSPACE_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
REPO="${GITHUB_REPOSITORY:-}"
WORK_DIR="$(mktemp -d)"
# checkpoint.sh reads this to tell a genuine step timeout from a crash: only a
# run that was killed may pause the card behind a human approval. A harness or
# model failure must fail loudly and stay selectable instead.
INVESTIGATION_EXIT_FILE="${AUTOPR_INVESTIGATION_EXIT_FILE:-${RUNNER_TEMP:+$RUNNER_TEMP/investigation-exit-code}}"
[ -z "$INVESTIGATION_EXIT_FILE" ] || rm -f "$INVESTIGATION_EXIT_FILE"
# checkpoint.sh refuses to harvest a sandbox clone older than this: on a rework
# the leftover workspace still carries the same task id, so only its age
# distinguishes the previous round's work from this run's. The workflow writes
# the file before this script starts; local runs get their own.
INVESTIGATION_STARTED_FILE="${AUTOPR_INVESTIGATION_STARTED_FILE:-${RUNNER_TEMP:+$RUNNER_TEMP/investigation-started-at}}"
[ -n "$INVESTIGATION_STARTED_FILE" ] \
    || INVESTIGATION_STARTED_FILE="$WORK_DIR/investigation-started-at"
[ -s "$INVESTIGATION_STARTED_FILE" ] \
    || date +%s > "$INVESTIGATION_STARTED_FILE" 2>/dev/null \
    || true
export AUTOPR_INVESTIGATION_STARTED_FILE="$INVESTIGATION_STARTED_FILE"
SNAPSHOT_PID=""
# Killing the timer only kills the sleeping subshell: a `checkpoint.sh snapshot`
# it already forked keeps running and would re-point `active` after this run
# consumed it. checkpoint.sh snapshot-halt waits that pass out.
stop_inflight_snapshots() {
    if [ -n "$SNAPSHOT_PID" ]; then
        kill "$SNAPSHOT_PID" 2>/dev/null || true
        SNAPSHOT_PID=""
        "$SCRIPT_DIR/checkpoint.sh" snapshot-halt \
            || printf 'kanban-autopr: could not halt in-flight snapshots\n' >&2
    fi
}
_investigate_cleanup() {
    local status=$?
    stop_inflight_snapshots
    [ -z "$INVESTIGATION_EXIT_FILE" ] \
        || printf '%s\n' "$status" > "$INVESTIGATION_EXIT_FILE" 2>/dev/null \
        || true
    rm -rf "$WORK_DIR"
    # A failed continuation releases its claim, never its saved operator edits.
    if [ "$status" -ne 0 ] && [ -n "${TASK_ID:-}" ]; then
        python3 "$HANDOFF_CONTROL" finish "$TASK_ID" || true
    fi
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
# Everything mode-specific — prompt, model, sandbox switches, required report
# headings, decision validator — comes from the kind registry in lib.sh.
KIND_OUTCOME="$(autopr_kind_field "$MODE" outcome)" || die "unknown investigation mode: $MODE"
KIND_PROMPT="$(autopr_kind_field "$MODE" prompt)"
KIND_MODEL="$(autopr_kind_field "$MODE" model)"
KIND_EFFORT="$(autopr_kind_field "$MODE" effort)"
KIND_SANDBOX_ENV="$(autopr_kind_field "$MODE" sandbox)"
KIND_HEADINGS="$(autopr_kind_field "$MODE" headings)"
KIND_DECISION="$(autopr_kind_field "$MODE" decision)"
# `browse` is an extra grant on top of the kind's own capability: a research
# run on a board without it still reads the web through search, it just cannot
# drive a browser or bring screenshots back.
#
# An artifact kind's own grant already authorized the run; whether that run
# reads the web at all is its registry row's call. Research's row sets
# AUTOPR_CODEX_WEB_SEARCH=1; email's does not — its corpus is the snapshots
# attached to the card — so an email run gets neither search nor a browser,
# whatever else its board is granted, and context.json says so truthfully.
BOARD_CAPABILITIES="$(jq -r '(.autopr_capabilities // [])[]' "$CARD_FILE" 2>/dev/null || true)"
BROWSE_GRANTED=false
SEARCH_GRANTED=false
if [ "$KIND_OUTCOME" = artifact ]; then
    if [[ " $KIND_SANDBOX_ENV " == *" AUTOPR_CODEX_WEB_SEARCH=1 "* ]]; then
        SEARCH_GRANTED=true
        printf '%s\n' "$BOARD_CAPABILITIES" | grep -qxF browse && BROWSE_GRANTED=true
    fi
elif printf '%s\n' "$BOARD_CAPABILITIES" | grep -qxF research; then
    # Code drafting itself needs no grant. Reading the live web still crosses
    # the repository boundary and uses the existing per-board research grant.
    SEARCH_GRANTED=true
fi
ARTIFACTS_DIR="$WORK_DIR/artifacts"
mkdir -p "$ARTIFACTS_DIR"
SCREENSHOTS_REQUIRED=false
if [ "$MODE" = research ] && autopr_research_screenshots_required "$(cat "$CARD_FILE")"; then
    SCREENSHOTS_REQUIRED=true
fi
if [ "$SCREENSHOTS_REQUIRED" = true ] && [ "$BROWSE_GRANTED" != true ]; then
    die "this research card requires screenshots but the board lacks the browse capability"
fi

ATTACH_ARGS=()
FEEDBACK_CHECKPOINT='{"comment_id":"","review_id":""}'
RESUME_PATCH=""
REQUIRE_RESUME_PATCH=0
PRIOR_CHECKPOINT_FILE="$WORK_DIR/prior-checkpoint.json"
printf 'null\n' > "$PRIOR_CHECKPOINT_FILE"

# Resume a prior checkpoint only inside the disposable sandbox.
prior_checkpoint="$($SCRIPT_DIR/checkpoint.sh latest "$CARD_FILE")"
if [ -n "$prior_checkpoint" ]; then
    if [ -s "$prior_checkpoint/metadata.json" ]; then
        cp "$prior_checkpoint/metadata.json" "$PRIOR_CHECKPOINT_FILE"
    fi
    # Trust the metadata over the file: a checkpoint that records no patch must
    # never replay one left behind by an earlier pass of the same run.
    # An artifact kind never has a patch to restore: its checkpointed report
    # rides along as an untrusted `-f` input below instead.
    if [ "$KIND_OUTCOME" = pull_request ] \
        && [ -s "$prior_checkpoint/model.patch" ] \
        && [ "$(jq -r '.patch_saved // true' "$PRIOR_CHECKPOINT_FILE" 2>/dev/null)" != false ]; then
        RESUME_PATCH="$prior_checkpoint/model.patch"
    fi
    for checkpoint_input in report.md decision.json transcript.log; do
        [ ! -s "$prior_checkpoint/$checkpoint_input" ] \
            || ATTACH_ARGS+=(-f "$prior_checkpoint/$checkpoint_input")
    done
fi

# Recheck every selected card against the live hold before starting work.
# A cached candidate or failed API request must never bypass an unqueue.
claim="$(mw_api POST "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/autopr/run-claim" '{}')" \
    || die "could not verify the AutoPR queue state for $TASK_ID"
[ "$(printf '%s' "$claim" | jq -r '.ok')" = true ] \
    || die "ticket $TASK_ID was unqueued or left the queue before investigation"

handoff="$(python3 "$HANDOFF_CONTROL" continue "$TASK_ID")" \
    || die "could not acquire this task's operator hand-back"
if [ "$(jq 'length' <<< "$handoff")" -gt 0 ]; then
    RESUME_PATCH="$(jq -r '.patch' <<< "$handoff")"
    ATTACH_ARGS+=(-f "$(jq -r '.note' <<< "$handoff")")
    KIND_MODEL="$(jq -r '.model' <<< "$handoff")"
    KIND_EFFORT="$(jq -r '.effort' <<< "$handoff")"
    REQUIRE_RESUME_PATCH=1
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
    --arg id8 "$ID8" --arg outcome "$KIND_OUTCOME" '
    # An artifact run must not spend its attachment budget re-reading its own
    # earlier output: after round 1 the card carries the report the bot wrote plus up
    # to a dozen of its screenshots, which would crowd out files people attached
    # and be re-fed as image inputs. Keep only the newest prior report (the
    # revision prompt treats it as version 1) and drop the rest of what the
    # publisher uploaded, recognised by its own naming (research-… or
    # email-…-rN). The snapshots on an email card, email-<gmail message id>.md, carry no
    # round suffix and are never mistaken for output of the bot.
    def mine: ((.filename // "") | test("^(research|email)-(report-)?" + $id8 + "-r[0-9]+"));
    def prior_report: ((.filename // "") | test("^(research|email)-report-" + $id8 + "-r[0-9]+\\.md$"));
    (if $outcome == "artifact" then
        ([.[] | select(prior_report)] | sort_by(.created_at // "") | last) as $keep
        | map(select((mine | not) or (. == $keep)))
     else . end)
    | ((map(select((.round_index // 1) == $round)) | sort_by(.created_at // "") | reverse)
      + (map(select((.round_index // 1) != $round)) | sort_by(.created_at // "") | reverse))[]')

# The publisher's own earlier output that the filter above deliberately did
# NOT re-attach. It matters that the model is told: the report it is revising
# names each screenshot by filename and treats those images as the evidence
# for its claims, so without this it reads round-1 prose citing pictures it
# cannot see and has no way to know they were withheld rather than missing.
withheld_attachments='[]'
if [ "$KIND_OUTCOME" = artifact ]; then
    withheld_attachments="$(printf '%s' "$files" | jq -c --arg id8 "$ID8" '
        def mine: ((.filename // "") | test("^(research|email)-(report-)?" + $id8 + "-r[0-9]+"));
        def prior_report: ((.filename // "") | test("^(research|email)-report-" + $id8 + "-r[0-9]+\\.md$"));
        ([.[] | select(prior_report)] | sort_by(.created_at // "") | last) as $keep
        | [.[] | select(mine and (. != $keep)) | (.filename // empty)]' 2>/dev/null || printf '[]')"
fi

CONTEXT_FILE="$WORK_DIR/context.json"
# The model's copy of the history omits the lane's bookkeeping rows; the raw
# file above keeps them for the directive resolver and the round derivation.
autopr_strip_bookkeeping_history "$history" > "$WORK_DIR/history-for-model.json"
jq -n \
    --slurpfile card "$CARD_FILE" \
    --slurpfile subtasks "$WORK_DIR/subtasks.json" \
    --slurpfile history "$WORK_DIR/history-for-model.json" \
    --slurpfile files "$WORK_DIR/files.json" \
    --slurpfile directive_policy "$DIRECTIVE_FILE" \
    --slurpfile test_tenant_evidence "$TEST_TENANT_EVIDENCE_FILE" \
    --slurpfile production_errors "$WORK_DIR/production-errors.json" \
    --slurpfile changes_since_production "$WORK_DIR/changes-since-production.json" \
    --slurpfile prior_checkpoint "$PRIOR_CHECKPOINT_FILE" \
    --rawfile production_log_signals "$WORK_DIR/production-log-signals.txt" \
    --argjson downloaded "$downloaded" \
    --argjson withheld "$withheld_attachments" \
    --argjson web_search_available "$SEARCH_GRANTED" \
    --argjson screenshots_required "$SCREENSHOTS_REQUIRED" \
    '{card: $card[0], directive_policy: $directive_policy[0], prior_checkpoint: $prior_checkpoint[0], test_tenant_evidence: $test_tenant_evidence[0], grounding: {web_search_available: $web_search_available}, required_deliverables: {screenshots: $screenshots_required}, production: ($card[0].production // null), changes_since_production: $changes_since_production[0], production_recent_errors: $production_errors[0], production_log_signals: $production_log_signals, subtasks: $subtasks[0], history: $history[0], files: ($files[0] | map(del(.storage_url))), downloaded_attachments: $downloaded, withheld_attachments: $withheld}' \
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

PROMPT_FILE="$SCRIPT_DIR/$KIND_PROMPT"
if [ "$MODE" = rework ]; then
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
        AUTOPR_CODEX_MODEL="$KIND_MODEL"
        AUTOPR_CODEX_REASONING_EFFORT="$KIND_EFFORT"
        AUTOPR_TASK_ID="$TASK_ID"
        AUTOPR_HANDOFF_CARD="$CARD_FILE"
    )
    # Kind-specific sandbox switches (empty-patch enforcement, web search,
    # image inputs): space-separated KEY=VALUE from the registry.
    local kind_switch
    for kind_switch in $KIND_SANDBOX_ENV; do
        runner_env+=("$kind_switch")
    done
    if [ "$SEARCH_GRANTED" = true ] && [[ "$KIND_SANDBOX_ENV" != *AUTOPR_CODEX_WEB_SEARCH=1* ]]; then
        runner_env+=(AUTOPR_CODEX_WEB_SEARCH=1)
    fi
    if [ "$BROWSE_GRANTED" = true ]; then
        # No INSTALL_PLAYWRIGHT_BROWSERS here: it is a Docker BUILD arg
        # (docker/agent-sandbox/Dockerfile), read by `msandbox build
        # --playwright`, and setting it at run time installs nothing. The image
        # either carries Chromium or it does not; browse-capture.py exits 3 and
        # says so, and the prompt tells the model to fall back to web search
        # rather than treat that as a research failure.
        runner_env+=(
            AUTOPR_CODEX_COLLECT_ARTIFACTS=1
            AUTOPR_SANDBOX_ARTIFACTS_DIR="$ARTIFACTS_DIR"
        )
    fi
    [ -z "$RESUME_PATCH" ] || runner_env+=(AUTOPR_RESUME_PATCH="$RESUME_PATCH")
    runner_env+=(AUTOPR_REQUIRE_RESUME_PATCH="$REQUIRE_RESUME_PATCH")
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
    if [ "$codex_rc" -eq 75 ]; then
        stop_inflight_snapshots
        [ -z "${GITHUB_OUTPUT:-}" ] || printf 'paused=true\n' >> "$GITHUB_OUTPUT"
        [ -z "${GITHUB_STEP_SUMMARY:-}" ] || printf '## Operator takeover\nThe checkout is preserved under manual control. No autonomous timeout applies to the manual session.\n' >> "$GITHUB_STEP_SUMMARY"
        printf 'AutoPR handed off to the operator; manual work has no time limit.\n'
        exit 0
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

    local heading
    while IFS= read -r heading; do
        [ -n "$heading" ] || continue
        if ! grep -qF "$heading" "$REPORT_FILE"; then
            die "report is missing required heading: $heading"
        fi
    done <<< "$KIND_HEADINGS"
}

# Snapshot the live sandbox on a timer. checkpoint.sh save runs as a separate
# workflow step, so it never runs at all if this process is killed outright
# (machine death, SIGKILL, a Docker restart) — and the next run wipes the
# sandbox clone. Without this, that class of failure loses the whole
# investigation rather than the last few minutes of it.
SNAPSHOT_INTERVAL_SECONDS="${AUTOPR_SNAPSHOT_INTERVAL_SECONDS:-240}"
SNAPSHOT_MAX_PASSES="${AUTOPR_SNAPSHOT_MAX_PASSES:-15}"
start_inflight_snapshots() {
    [ "$SNAPSHOT_INTERVAL_SECONDS" -gt 0 ] 2>/dev/null || return 0
    # Clear any stop flag a previous run left in the shared runtime root.
    "$SCRIPT_DIR/checkpoint.sh" snapshot-arm \
        || printf 'kanban-autopr: could not arm in-flight snapshots\n' >&2
    local parent=$$
    (
        # Bounded, and self-terminating once this shell is gone: an orphaned
        # loop must never outlive the investigation and repoint a checkpoint
        # the next run is already reading.
        for _ in $(seq 1 "$SNAPSHOT_MAX_PASSES"); do
            sleep "$SNAPSHOT_INTERVAL_SECONDS"
            kill -0 "$parent" 2>/dev/null || exit 0
            # Never silence this: a snapshot that has been failing every pass
            # looks exactly like one that is working until the run is lost.
            "$SCRIPT_DIR/checkpoint.sh" snapshot "$CARD_FILE" >/dev/null \
                || printf 'kanban-autopr: in-flight snapshot pass failed\n' >&2
        done
    ) &
    SNAPSHOT_PID=$!
}

start_inflight_snapshots
codex_pass

# One corrective retry when the pass just returned is one the trusted harness
# will refuse anyway. Dying (or letting publish.sh die) would leave the card
# showing a stale refusal, or nothing at all, with no sign the run happened.
# The retry re-states the rejection of the exact decision just produced; the
# trusted validation below still has the last word.
CORRECTION_KIND=""
CORRECTION_INSTRUCTION=""
append_correction() {
    local kind="$1" instruction="$2"
    if [ -z "$CORRECTION_KIND" ]; then
        CORRECTION_KIND="$kind"
        CORRECTION_INSTRUCTION="$instruction"
    else
        CORRECTION_KIND="$CORRECTION_KIND,$kind"
        CORRECTION_INSTRUCTION="$CORRECTION_INSTRUCTION

$instruction"
    fi
}
if [ "$KIND_OUTCOME" = artifact ]; then
    if screenshot_contract_error="$(autopr_research_screenshot_contract_error \
            "$SCREENSHOTS_REQUIRED" "$REPORT_FILE" "$RAW_DECISION_FILE" "$ARTIFACTS_DIR")"; then
        append_correction required_screenshots_missing "The trusted harness REJECTED the research report you just returned: $screenshot_contract_error. The card explicitly requires screenshots. Run browse-capture.py for at least one relevant source page, verify that it prints a saved filename, and name the captured filename beside the finding it supports. Return a complete report and decision again; do not merely promise that screenshots will be added later."
    fi
elif [ "$(jq -r '.no_safe_action_reason // ""' "$RAW_DECISION_FILE" 2>/dev/null)" = migration_required ]; then
    # The single most common refusal, and it never protected anything: the
    # operator applies every migration by hand, so authoring the version file
    # is ordinary drafting work. decision.sh no longer accepts the reason at
    # all; correct it here so an out-of-date model costs one retry instead of
    # a dead run.
    append_correction migration_is_not_a_blocker "The trusted harness REJECTED the decision you just returned: migration_required is not an outcome this harness accepts. Needing a database migration is ordinary drafting work, not a blocker. Investigate again and implement the change: author the application code, its tests, and a new server/alembic/versions/<revision>.py version file for human review — its name must use only letters, digits and underscores without a leading underscore, it must assign a string literal `revision`, its `down_revision` must be one of the current repository heads, and it must define both `upgrade()` and `downgrade()`. You must never run a migration against any database and you must not touch env.py, templates, alembic.ini, or any migration runner code — a human reviews and applies every migration. If something OTHER than the schema change genuinely blocks you, use questions_only with concrete options, or no_safe_action with already_fixed, acceptance_criteria_met, policy_blocked, or external_dependency."
    if [ -s "$DIRECTIVE_FILE" ] \
        && ! "$SCRIPT_DIR/decision.sh" directive-ok "$RAW_DECISION_FILE" "$DIRECTIVE_FILE" 2>/dev/null; then
        append_correction directive_violation "The authorized card owner issued the directives above. The replacement decision must honor them as well as implementing the needed migration."
    fi
    if ! "$SCRIPT_DIR/decision.sh" grounding-ok "$RAW_DECISION_FILE" 2>/dev/null; then
        append_correction unresolved_researchable_context "Any remaining question or blocker must also carry the grounded resolution evidence and rationale described in the shared prompt contract."
    fi
elif [ "$(jq -r '.no_safe_action_reason // ""' "$RAW_DECISION_FILE" 2>/dev/null)" = already_fixed ] \
    && ! "$SCRIPT_DIR/decision.sh" acceptance-ok "$RAW_DECISION_FILE" 2>/dev/null; then
    append_correction already_fixed_requires_evidence "The trusted harness REJECTED an unevidenced already_fixed verdict. Either implement the uncovered work or return already_fixed with acceptance_evidence containing at least one real repository citation: criterion, path, nonblank line, and a commit at HEAD or in its ancestry. The harness verifies every citation. Do not manufacture a cosmetic change or guess evidence."
    if [ -s "$DIRECTIVE_FILE" ] \
        && ! "$SCRIPT_DIR/decision.sh" directive-ok "$RAW_DECISION_FILE" "$DIRECTIVE_FILE" 2>/dev/null; then
        append_correction directive_violation "The authorized card owner also issued directives that this decision violates. Honor every directive in the replacement decision."
    fi
    if ! "$SCRIPT_DIR/decision.sh" grounding-ok "$RAW_DECISION_FILE" 2>/dev/null; then
        append_correction unresolved_researchable_context "Any remaining question or blocker must also carry the grounded resolution evidence and rationale described in the shared prompt contract."
    fi
elif ! "$SCRIPT_DIR/decision.sh" schema-ok "$RAW_DECISION_FILE" 2>/dev/null; then
    # Invalid JSON and unrelated schema failures are not grounding failures.
    # Let the normalizer below report the precise validation error without a
    # misleading retry or an unreadable correction attachment.
    :
else
    # Detect every independent defect in this decision before spending the one
    # retry. An elif chain made a directive failure hide missing grounding (or
    # vice versa), so the replacement pass could satisfy only the first error
    # and then fail publication on the second.
    if [ -s "$DIRECTIVE_FILE" ] \
        && ! "$SCRIPT_DIR/decision.sh" directive-ok "$RAW_DECISION_FILE" "$DIRECTIVE_FILE" 2>/dev/null; then
        append_correction directive_violation "The authorized card owner issued the directives above and the trusted harness REJECTED the decision you just returned. Investigate again and return a decision that honors them. Under draft_pr you may not return already_fixed: implement the repo-local change, and when it needs a schema change, author a new server/alembic/versions/*.py version file for human review and never run it against any database. A needed migration is never a reason to refuse. questions_only is allowed when a specific missing product decision blocks even a partial implementation, and when the card or send-back cites a page, label, control, or behavior that exists nowhere in the repository. no_safe_action with acceptance_criteria_met is allowed when every acceptance criterion on the card is already satisfied on this branch, and it must carry acceptance_evidence with the criterion text plus path, line, and commit for each one; the harness verifies every citation and requires the commit to be HEAD or an ancestor of it, the line to be non-blank there, and the path to still exist at HEAD. Do not satisfy this directive with a change you would not make if the card did not exist. policy_blocked and external_dependency remain available only for a genuine safety or third-party blocker."
    fi
    if ! "$SCRIPT_DIR/decision.sh" grounding-ok "$RAW_DECISION_FILE" 2>/dev/null; then
        append_correction unresolved_researchable_context "The trusted harness REJECTED an unexplained blocker. Read the latest additional context as plain-language answers or research guidance, not just numbered choices. When context.json says grounding.web_search_available is true, use live web search and primary sources for missing public facts. When it is false, record that the board has not granted search and do not claim a search. Draft safe repo-local work through the existing research, catalog, and consumer path. Do not invent a counsel-approval requirement. Preserve actual review/approval gates and never write production data or apply migrations. Every remaining question needs resolution.kind (product_decision, private_context, source_unavailable, or explicit_approval), 1-5 nonblank resolution.evidence entries of at most 300 characters, and resolution.why_user_needed of at most 600 characters. A policy_blocked/external_dependency refusal needs the same object as blocker_resolution. Record only work actually done; if research is unavailable or fails, say so accurately. Prefer partial_implementation when safe independent work is possible."
    fi
    # publish.sh refuses a string-literal-only diff on a card asking for
    # structure and discards the run. Catching it here instead gives the model
    # the one thing that failure never had: a correction path.
    case "$(jq -r '.outcome // ""' "$RAW_DECISION_FILE" 2>/dev/null)" in
        implementation|partial_implementation)
            WORKTREE_DIFF="$WORK_DIR/worktree.diff"
            git -C "$REPO_ROOT" diff HEAD > "$WORKTREE_DIFF" 2>/dev/null || : > "$WORKTREE_DIFF"
            if autopr_cosmetic_only_diff "$WORKTREE_DIFF" \
                "$(jq -r '.title // ""' "$CARD_FILE")" "$(jq -r '.description // ""' "$CARD_FILE")"; then
                append_correction cosmetic_only_diff "The trusted harness REJECTED the decision you just returned: this card asks for structure — a route, a sidebar row, a menu entry, an endpoint — and your diff only rewrites string literals, which changes nothing a reader of the card asked for. Investigate again. If every acceptance criterion is already satisfied on this branch, return no_safe_action with acceptance_criteria_met and one acceptance_evidence entry per criterion (criterion text plus path, line, commit); the harness verifies every citation and requires the commit to be HEAD or an ancestor of it, the line to be non-blank there, and the path to still exist at HEAD. If a specific missing product decision blocks the structural change, return questions_only and say what is missing. Only return an implementation if you make the structural change the card actually asks for."
            fi
            # The publisher's migration gate, run here instead of there. A
            # mistyped down_revision used to cost the whole investigation:
            # publish.sh's only answer is `git reset --hard` and exit. Now that
            # drafting a migration is the routine path rather than a rare
            # exception, that failure needed a correction path like every other.
            if ! MIGRATION_DRAFT_ERRORS="$(autopr_migration_draft_errors "$REPO_ROOT" \
                    "${AUTOPR_MIGRATION_BASE_REF:-main}")"; then
                append_correction migration_draft_invalid "The trusted harness REJECTED the decision you just returned: the migration you drafted cannot be published.
$MIGRATION_DRAFT_ERRORS
Investigate again and re-author the change. A drafted migration must be a NEW file server/alembic/versions/<revision>.py whose name uses only letters, digits and underscores and does not start with an underscore; it must assign a string literal \`revision\`; its \`down_revision\` must be one of the current repository heads (listed as repository_heads in the production context) or another migration you are adding in this same change, never None and never a mid-chain revision; and it must define both \`upgrade()\` and \`downgrade()\`. Never edit or delete a migration already on main, never touch env.py, templates, alembic.ini, or any migration runner code, and never run a migration against any database."
            fi
            ;;
    esac
fi

if [ -n "$CORRECTION_KIND" ]; then
    echo "kanban-autopr: decision rejected ($CORRECTION_KIND); retrying once" >&2
    case ",$CORRECTION_KIND," in
        *,unresolved_researchable_context,*)
            if [ "$(jq -r '.outcome // ""' "$RAW_DECISION_FILE" 2>/dev/null)" = partial_implementation ] \
                && [[ ",$CORRECTION_KIND," != *,cosmetic_only_diff,* ]] \
                && [[ ",$CORRECTION_KIND," != *,migration_draft_invalid,* ]]; then
                grounding_patch="$WORK_DIR/grounding-resume.patch"
                git -C "$REPO_ROOT" diff HEAD > "$grounding_patch" 2>/dev/null \
                    || : > "$grounding_patch"
                if [ -s "$grounding_patch" ]; then
                    RESUME_PATCH="$grounding_patch"
                    REQUIRE_RESUME_PATCH=0
                fi
            fi
            ;;
    esac
    # The rejected pass must not leave edits behind for the retry to inherit.
    git -C "$REPO_ROOT" reset --hard HEAD >/dev/null 2>&1 || true
    git -C "$REPO_ROOT" clean -fd >/dev/null 2>&1 || true
    CORRECTION_FILE="$WORK_DIR/directive-correction.json"
    # A cosmetic-diff rejection can happen with no directive at all.
    [ -s "$DIRECTIVE_FILE" ] || printf 'null\n' > "$DIRECTIVE_FILE"
    jq -n --slurpfile policy "$DIRECTIVE_FILE" --slurpfile rejected "$RAW_DECISION_FILE" \
        --arg kind "$CORRECTION_KIND" --arg instruction "$CORRECTION_INSTRUCTION" \
        '{kind: $kind,
          directive_policy: ($policy[0] // null),
          rejected_decision: {outcome: $rejected[0].outcome,
                              no_safe_action_reason: $rejected[0].no_safe_action_reason,
                              questions: $rejected[0].questions,
                              blocker_resolution: $rejected[0].blocker_resolution},
          instruction: $instruction}' \
        > "$CORRECTION_FILE"
    ATTACH_ARGS+=(-f "$CORRECTION_FILE")
    if [ "$KIND_OUTCOME" = artifact ]; then
        # Do not publish an uncited capture from the rejected attempt. The
        # retry runs in a fresh sandbox and cannot inspect that image; it must
        # capture and name its own final evidence set.
        rm -rf -- "$ARTIFACTS_DIR"
        mkdir -p "$ARTIFACTS_DIR"
    fi
    : > "$REPORT_FILE"
    : > "$RAW_DECISION_FILE"
    codex_pass
fi

park_rejected_after_correction() {
    local failure="$1" existing marker origin_note
    stop_inflight_snapshots
    existing="$(jq -r '.progress_note // ""' "$CARD_FILE")"
    marker="[autopr:no-spec $(date -u +%Y-%m-%dT%H:%M:%SZ)] needs_clarification"
    origin_note="$(progress_note_with_origin \
        "🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · $marker · note: AutoPR $failure after one correction." \
        "$existing")"
    mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
        "$(jq -n --arg note "$origin_note" \
            '{board_column:"changes_requested",progress_note:$note}')" >/dev/null \
        || die "could not park the rejected investigation on task $TASK_ID"
    autopr_post_context_request "$PROJECT_ID" "$TASK_ID" \
        "AutoPR $failure after one correction. Review the saved checkpoint, then add plain-language context, clarify what it should research, or press Run to resume the repair." \
        "$origin_note"
}

POST_CORRECTION_FAILURE=""
if [ "$KIND_OUTCOME" = artifact ] && [ -n "$CORRECTION_KIND" ]; then
    if screenshot_contract_error="$(autopr_research_screenshot_contract_error \
            "$SCREENSHOTS_REQUIRED" "$REPORT_FILE" "$RAW_DECISION_FILE" "$ARTIFACTS_DIR")"; then
        POST_CORRECTION_FAILURE="still did not satisfy the requested screenshot deliverable: $screenshot_contract_error"
    fi
elif [ "$KIND_OUTCOME" = pull_request ] && [ -n "$CORRECTION_KIND" ]; then
    if ! "$SCRIPT_DIR/decision.sh" schema-ok "$RAW_DECISION_FILE" 2>/dev/null; then
        POST_CORRECTION_FAILURE="returned an invalid decision"
    elif [ -s "$DIRECTIVE_FILE" ] \
        && ! "$SCRIPT_DIR/decision.sh" directive-ok "$RAW_DECISION_FILE" "$DIRECTIVE_FILE" 2>/dev/null; then
        POST_CORRECTION_FAILURE="still violated the owner's directive"
    elif ! "$SCRIPT_DIR/decision.sh" grounding-ok "$RAW_DECISION_FILE" 2>/dev/null; then
        POST_CORRECTION_FAILURE="could not justify its remaining questions"
    else
        case "$(jq -r '.outcome // ""' "$RAW_DECISION_FILE")" in
            implementation|partial_implementation)
                POST_RETRY_DIFF="$WORK_DIR/post-retry.diff"
                git -C "$REPO_ROOT" diff HEAD > "$POST_RETRY_DIFF" 2>/dev/null \
                    || : > "$POST_RETRY_DIFF"
                if autopr_cosmetic_only_diff "$POST_RETRY_DIFF" \
                    "$(jq -r '.title // ""' "$CARD_FILE")" \
                    "$(jq -r '.description // ""' "$CARD_FILE")"; then
                    POST_CORRECTION_FAILURE="still produced only a cosmetic diff"
                elif ! autopr_migration_draft_errors "$REPO_ROOT" \
                    "${AUTOPR_MIGRATION_BASE_REF:-main}" >/dev/null; then
                    POST_CORRECTION_FAILURE="still produced an invalid migration draft"
                fi
                ;;
        esac
    fi
fi
if [ -n "$POST_CORRECTION_FAILURE" ]; then
    if [ "$KIND_OUTCOME" = artifact ]; then
        marker="[autopr:no-spec $(date -u +%Y-%m-%dT%H:%M:%SZ)] source_unavailable"
        origin_note="$(progress_note_with_origin \
            "🤖 AUTO SETUP · BLOCKED: RESEARCH OUTPUT INCOMPLETE · $marker · note: Requested screenshots were not captured after one retry." \
            "$(jq -r '.progress_note // ""' "$CARD_FILE")")"
        mw_api PATCH "/matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID" \
            "$(jq -n --arg note "$origin_note" '{board_column:"changes_requested",progress_note:$note}')" >/dev/null \
            || die "could not park the incomplete research result on task $TASK_ID"
        autopr_post_context_request "$PROJECT_ID" "$TASK_ID" \
            "AutoPR completed the written research but $POST_CORRECTION_FAILURE. Verify the board's browser runtime, then press Run to retry; the incomplete report was not published." \
            "$origin_note"
    else
        park_rejected_after_correction "$POST_CORRECTION_FAILURE"
    fi
    die "corrected investigation still failed validation; card parked for context"
fi

# Nothing below needs another snapshot, and `consume` must not race one.
stop_inflight_snapshots

# Codex's JSON is data, not authority. Keep the normalized result outside
# the repository too: publish.sh is the only script permitted to decide what
# reaches GitHub or the board.
"$SCRIPT_DIR/decision.sh" "$KIND_DECISION" "$RAW_DECISION_FILE" "$RAW_DECISION_FILE.normalized" "$DIRECTIVE_FILE" \
    || die "investigation decision rejected; publication is blocked"
jq --argjson checkpoint "$FEEDBACK_CHECKPOINT" \
    '. + {feedback_checkpoint: $checkpoint}' \
    "$RAW_DECISION_FILE.normalized" > "$RAW_DECISION_FILE.with-feedback" \
    || die "could not attach the validated feedback checkpoint"
mv "$RAW_DECISION_FILE.with-feedback" "$RAW_DECISION_FILE.normalized" \
    && mv "$RAW_DECISION_FILE.normalized" "$RAW_DECISION_FILE" \
    || die "could not install the validated investigation decision"
# Screenshots ride to the publisher through a stable directory rather than the
# decision JSON: the model names them, but only files the trusted bridge
# actually admitted are here.
if [ "$BROWSE_GRANTED" = true ] && [ -n "${AUTOPR_ARTIFACTS_OUTPUT_DIR:-}" ]; then
    mkdir -p "$AUTOPR_ARTIFACTS_OUTPUT_DIR"
    find "$ARTIFACTS_DIR" -maxdepth 1 -type f -exec cp {} "$AUTOPR_ARTIFACTS_OUTPUT_DIR/" \; 2>/dev/null || true
    collected="$(find "$AUTOPR_ARTIFACTS_OUTPUT_DIR" -maxdepth 1 -type f | wc -l | tr -d '[:space:]')"
    printf 'kanban-autopr: %s screenshot(s) ready for publication\n' "$collected" >&2
fi

"$SCRIPT_DIR/checkpoint.sh" consume "$CARD_FILE"
