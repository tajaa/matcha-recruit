#!/usr/bin/env bash
# Exercises the kanban-autopr harness without touching Matcha, GitHub, or a
# real model. All network/model commands are stubbed on PATH.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOPR_DIR="$REPO_ROOT/scripts/kanban-autopr"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PASS=0
FAIL=0
check() {
    local desc="$1" ok="$2"
    if [ "$ok" = "0" ]; then
        echo "PASS: $desc"; PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"; FAIL=$((FAIL + 1))
    fi
}

workflow="$REPO_ROOT/.github/workflows/kanban-autopr.yml"
check "local dispatcher is the workflow's only automatic clock" \
    $(! grep -qF 'schedule:' "$workflow" && grep -qF 'workflow_dispatch:' "$workflow" && echo 0 || echo 1)

check "workflow resolves the active production build before collecting cards" \
    $(grep -qF 'resolve-production-context.sh > "$RUNNER_TEMP/production-context.json"' "$workflow" && echo 0 || echo 1)

check "workflow gives ordinary investigations 20 minutes and approved continuations 10" \
    $(grep -qF 'runtime-policy.sh' "$workflow" \
      && grep -qF "timeout-minutes: \${{ fromJSON(steps.runtime.outputs.minutes || '20') }}" "$workflow" \
      && grep -qF 'AUTOPR_NORMAL_RUNTIME_MINUTES:-20' "$AUTOPR_DIR/runtime-policy.sh" \
      && grep -qF 'AUTOPR_EXTENDED_RUNTIME_MINUTES:-10' "$AUTOPR_DIR/runtime-policy.sh" \
      && echo 0 || echo 1)

check "failed investigations checkpoint before the trusted checkout is reset" \
    $(grep -qF 'name: Checkpoint interrupted investigation' "$workflow" \
      && grep -qF 'checkpoint.sh save' "$workflow" \
      && grep -qF 'AUTOPR_RESUME_PATCH' "$AUTOPR_DIR/run-codex-sandboxed.sh" \
      && grep -qF 'checkpoint.sh" consume' "$AUTOPR_DIR/investigate.sh" \
      && echo 0 || echo 1)

check "production resolver uses active container digests and read-only migration revisions" \
    $(grep -qF 'aws ecr describe-images' "$AUTOPR_DIR/resolve-production-context.sh" \
      && grep -qF 'schema-snapshot.sh" prod-revisions' "$AUTOPR_DIR/resolve-production-context.sh" \
      && echo 0 || echo 1)

graph_snapshot="$(python3 "$REPO_ROOT/scripts/alembic_graph_snapshot.py" \
    "$REPO_ROOT/server/alembic/versions" 2>/dev/null)"
check "migration graph snapshot works without the backend virtualenv" \
    $(printf '%s' "$graph_snapshot" | jq -e \
      '(.heads | length) > 0 and (.revisions | length) > 0 and (.pending | length) == (.revisions | length)' \
      >/dev/null 2>&1 && echo 0 || echo 1)

check "future frontend images expose a small stable build manifest" \
    $(grep -qF '> dist/version.json' "$REPO_ROOT/client/Dockerfile" \
      && grep -qF '.build_number // .build // empty' "$AUTOPR_DIR/resolve-production-context.sh" \
      && echo 0 || echo 1)

check "model process is stripped of production SSH credentials" \
    $(grep -qF 'env -u GH_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY' "$AUTOPR_DIR/investigate.sh" && echo 0 || echo 1)

check "workflow forces Codex through the dedicated AutoPR msandbox" \
    $(grep -qF 'AUTOPR_MSANDBOX_BIN: ${{ github.workspace }}/scripts/agent-sandbox.sh' "$workflow" \
      && grep -qF 'AUTOPR_SANDBOX_PROJECT_NAME: matcha-kanban-autopr-sandbox' "$workflow" \
      && grep -qF 'run-codex-sandboxed.sh' "$AUTOPR_DIR/investigate.sh" \
      && grep -qF 'AUTOPR_CODEX_MODEL=gpt-5.6-sol' "$AUTOPR_DIR/investigate.sh" \
      && grep -qF 'AUTOPR_CODEX_REASONING_EFFORT=medium' "$AUTOPR_DIR/investigate.sh" \
      && echo 0 || echo 1)

check "rework uses current main and an immutable control-plane snapshot" \
    $(grep -qF 'git merge --no-edit main' "$workflow" \
      && grep -qF 'git archive main scripts/kanban-autopr scripts/error-autofix' "$workflow" \
      && grep -qF '"$AUTOPR_CONTROL_ROOT/kanban-autopr/investigate.sh"' "$workflow" \
      && grep -qF '"$AUTOPR_CONTROL_ROOT/kanban-autopr/publish.sh"' "$workflow" \
      && echo 0 || echo 1)

check "idle runs do not invoke uninitialized task cleanup" \
    $(grep -qF "if: always() && steps.select.outputs.skip == 'false'" "$workflow" \
      && echo 0 || echo 1)

check "workflow and dispatcher require the msandbox master switch" \
    $(grep -qF './scripts/agent-sandbox.sh autopr-ready' "$workflow" \
      && grep -qF '[ -f "$ENABLE_FILE" ]' "$AUTOPR_DIR/dispatch-if-idle.sh" \
      && grep -qF 'label=com.docker.compose.project=$PRIMARY_SANDBOX_PROJECT' "$AUTOPR_DIR/dispatch-if-idle.sh" \
      && grep -qF 'log_event skip msandbox-off' "$AUTOPR_DIR/dispatch-if-idle.sh" \
      && echo 0 || echo 1)

check "LaunchAgent reinstall preserves an enabled master switch" \
    $(grep -qF 'msandbox" autopr-master-ready' "$AUTOPR_DIR/install-launch-agent.sh" \
      && ! grep -qF 'msandbox" autopr-ready' "$AUTOPR_DIR/install-launch-agent.sh" \
      && echo 0 || echo 1)

check "msandbox start and stop own the AutoPR lifecycle" \
    $(grep -qF 'enable_autopr_control_plane' "$REPO_ROOT/scripts/agent-sandbox.sh" \
      && grep -qF 'disable_autopr_control_plane' "$REPO_ROOT/scripts/agent-sandbox.sh" \
      && grep -qF 'stop_autopr_container' "$REPO_ROOT/scripts/agent-sandbox.sh" \
      && grep -qF 'MSANDBOX SHUTDOWN BLOCKED' "$REPO_ROOT/scripts/agent-sandbox.sh" \
      && grep -qF 'msandbox stop --force' "$REPO_ROOT/scripts/agent-sandbox.sh" \
      && echo 0 || echo 1)

check "msandbox mounts only a staged read-only AutoPR Codex auth file" \
    $(grep -qF 'SANDBOX_CODEX_AUTH_FILE' "$REPO_ROOT/scripts/agent-sandbox.sh" \
      && grep -qF 'docker-compose.autopr-sandbox.yml' "$REPO_ROOT/scripts/agent-sandbox.sh" \
      && grep -qF 'auth.json:ro' "$REPO_ROOT/docker-compose.autopr-sandbox.yml" \
      && grep -qF 'cp "$HOST_CODEX_AUTH_FILE" "$SANDBOX_CODEX_AUTH_FILE"' "$AUTOPR_DIR/run-codex-sandboxed.sh" \
      && echo 0 || echo 1)

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    autopr_ports="$(SANDBOX_WORKSPACE_DIR="$TMP_DIR" SANDBOX_AWS_DIR="$TMP_DIR" \
      SANDBOX_CODEX_AUTH_FILE="$TMP_DIR/auth.json" \
      docker compose --project-name matcha-kanban-autopr-sandbox \
        --file "$REPO_ROOT/docker-compose.sandbox.yml" \
        --file "$REPO_ROOT/docker-compose.autopr-sandbox.yml" \
        config --format json | jq -c '.services.workspace.ports // []')"
    check "dedicated AutoPR sandbox publishes no host ports" \
      $([ "$autopr_ports" = '[]' ] && echo 0 || echo 1)
else
    check "dedicated AutoPR sandbox publishes no host ports" \
      $(grep -qF 'ports: !reset []' "$REPO_ROOT/docker-compose.autopr-sandbox.yml" \
        && echo 0 || echo 1)
fi

check "sandbox bridge uses a clean clone, empty AWS mount, and explicit Codex config" \
    $(grep -qF 'git clone --quiet --no-hardlinks --no-checkout' "$AUTOPR_DIR/run-codex-sandboxed.sh" \
      && grep -qF 'SANDBOX_AWS_DIR="$EMPTY_AWS_DIR"' "$AUTOPR_DIR/run-codex-sandboxed.sh" \
      && grep -qF 'git -C "$REPO_ROOT" apply --check --binary' "$AUTOPR_DIR/run-codex-sandboxed.sh" \
      && grep -qF -- '--ignore-user-config --model "$CODEX_MODEL"' "$AUTOPR_DIR/run-codex-sandboxed.sh" \
      && echo 0 || echo 1)

check "workflow delegates bounded publication prose to Luna medium" \
    $(grep -qF 'write-publication-copy.sh' "$workflow" \
      && grep -qF 'AUTOPR_CODEX_MODEL=gpt-5.6-luna' "$AUTOPR_DIR/write-publication-copy.sh" \
      && grep -qF 'AUTOPR_CODEX_REASONING_EFFORT=medium' "$AUTOPR_DIR/write-publication-copy.sh" \
      && grep -qF 'AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1' "$AUTOPR_DIR/write-publication-copy.sh" \
      && echo 0 || echo 1)

check "published PR and card carry production build provenance" \
    $(grep -qF '<!-- matcha-production-build: $PROD_BUILD_NUMBER -->' "$AUTOPR_DIR/publish.sh" \
      && grep -qF '🤖 AUTO SETUP · $AUTO_SETUP_STATUS · build $PROD_BUILD_NUMBER' "$AUTOPR_DIR/publish.sh" \
      && echo 0 || echo 1)

check "publisher permits only Espresso Swift source outside web/backend paths" \
    $(grep -qF 'platforms/desktop/Espresso/Espresso/.*\.swift' "$AUTOPR_DIR/publish.sh" && echo 0 || echo 1)

################################################################################
# mw_api must load config in its own shell, not only mw_login's command
# substitution (the bug that opened a PR and then failed to patch its card).
################################################################################
env_file="$TMP_DIR/env"
printf '%s\n' \
    'MATCHA_API_URL=https://example.invalid/api' \
    'MATCHA_BOT_EMAIL=bot@example.com' \
    'MATCHA_BOT_PASSWORD=secret' \
    'MATCHA_PROJECT_IDS=one' \
    'MATCHA_ASSIGNEE_EMAIL=owner@example.com' > "$env_file"

source "$AUTOPR_DIR/lib.sh"
mw_login() {
    _kanban_autopr_load_env
    printf token
}
curl() {
    local output_file="" arg
    printf '%s\n' "$*" > "$TMP_DIR/curl_args"
    while [ "$#" -gt 0 ]; do
        arg="$1"; shift
        if [ "$arg" = "-o" ]; then output_file="$1"; shift; fi
    done
    [ -z "$output_file" ] || printf '{"ok":true}' > "$output_file"
    printf 200
}
unset MATCHA_API_URL MATCHA_BOT_EMAIL MATCHA_BOT_PASSWORD MATCHA_PROJECT_IDS MATCHA_ASSIGNEE_EMAIL
MATCHA_AUTOPR_ENV="$env_file" mw_api GET /probe > "$TMP_DIR/api_result" 2>/dev/null
api_rc=$?
check "mw_api keeps MATCHA_API_URL available after login" \
    $([ "$api_rc" = "0" ] && grep -qF 'https://example.invalid/api/probe' "$TMP_DIR/curl_args" && echo 0 || echo 1)

mw_login() {
    _kanban_autopr_load_env
    if [ "${1:-}" = "--refresh" ]; then
        printf 'refresh\n' >> "$TMP_DIR/login_calls"
        printf fresh-token
    else
        printf cached\n >> "$TMP_DIR/login_calls"
        printf stale-token
    fi
}
curl() {
    local output_file="" arg all_args="$*"
    while [ "$#" -gt 0 ]; do
        arg="$1"; shift
        if [ "$arg" = "-o" ]; then output_file="$1"; shift; fi
    done
    if [[ "$all_args" == *"Bearer stale-token"* ]]; then
        [ -z "$output_file" ] || printf '{"detail":"expired"}' > "$output_file"
        printf 401
    else
        [ -z "$output_file" ] || printf '{"ok":true}' > "$output_file"
        printf 200
    fi
}
MATCHA_AUTOPR_ENV="$env_file" mw_api GET /refresh > "$TMP_DIR/refresh_result" 2>/dev/null
refresh_rc=$?
check "mw_api refreshes one stale token after a 401" \
    $([ "$refresh_rc" = "0" ] \
      && grep -qF refresh "$TMP_DIR/login_calls" \
      && grep -qF '"ok":true' "$TMP_DIR/refresh_result" \
      && echo 0 || echo 1)

set -a
source "$env_file"
set +a
( GITHUB_ACTIONS=true _kanban_autopr_validate_ci_scope ) > /dev/null 2>&1
check "Actions runs reject a localhost/non-production board target" \
    $([ "$?" != "0" ] && echo 0 || echo 1)
unset GITHUB_ACTIONS
unset -f curl mw_login

################################################################################
# An explicit reconsideration is durable work authorization. The collector
# must keep it runnable after reassignment, but only in the two lanes where the
# API permits a reconsideration request.
################################################################################
mkdir -p "$TMP_DIR/collect-bin" "$TMP_DIR/collect-runner"
cat > "$TMP_DIR/collect-bundle.json" <<'EOF'
{
  "project": {"title": "Collector test"},
  "elements": [],
  "tasks": [
    {"id":"11111111-0000-4000-8000-000000000001","title":"Reassigned reconsideration","assigned_email":"human@example.com","board_column":"todo","status":"pending","autopr_reconsideration_pending":true},
    {"id":"22222222-0000-4000-8000-000000000002","title":"Ordinary reassigned work","assigned_email":"human@example.com","board_column":"todo","status":"pending"},
    {"id":"33333333-0000-4000-8000-000000000003","title":"Moved reconsideration","assigned_email":"human@example.com","board_column":"review","status":"pending","autopr_reconsideration_pending":true},
    {"id":"44444444-0000-4000-8000-000000000004","title":"Assigned scoped work","assigned_email":"owner@example.com","board_column":"in_progress","status":"pending","progress_note":"🤖 AUTO SETUP · ALREADY SCOPED · PR #444"},
    {"id":"55555555-0000-4000-8000-000000000005","title":"Consumed go-ahead directive","assigned_email":"human@example.com","board_column":"todo","status":"pending","progress_note":"🤖 AUTO SETUP · NO PR: ALREADY FIXED · [autopr:no-spec 2026-09-02T01:00:00Z] already_fixed"},
    {"id":"66666666-0000-4000-8000-000000000006","title":"Consumed directive answered with a migration stop","assigned_email":"human@example.com","board_column":"todo","status":"pending","progress_note":"🤖 AUTO SETUP · NO PR: MIGRATION REQUIRED · [autopr:no-spec 2026-09-02T01:00:00Z] migration_required"},
    {"id":"77777777-0000-4000-8000-000000000007","title":"Queued by hand from the card","assigned_email":"human@example.com","board_column":"todo","status":"pending","autopr_run_requested_at":"2026-09-02T03:00:00+00:00"},
    {"id":"aaaaaaaa-0000-4000-8000-00000000000a","title":"Queued but already in review","assigned_email":"human@example.com","board_column":"review","status":"pending","autopr_run_requested_at":"2026-09-02T03:00:00+00:00"}
  ]
}
EOF
cat > "$TMP_DIR/collect-history.json" <<'EOF'
[
  {"id":"consumed-collector-event","created_at":"2026-09-02T00:59:00Z","metadata":{"kind":"autopr_additional_context","body":"just go ahead and do it anyways","autopr_reconsideration_of":"🤖 AUTO SETUP · NO PR: ALREADY FIXED · [autopr:no-spec 2026-09-02T00:30:00Z] already_fixed"}}
]
EOF
cat > "$TMP_DIR/collect-bin/curl" <<'EOF'
#!/usr/bin/env bash
output_file=""
write_status=0
url=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o) output_file="$2"; shift 2 ;;
        -w) write_status=1; shift 2 ;;
        http://*|https://*) url="$1"; shift ;;
        *) shift ;;
    esac
done
if [[ "$url" == */auth/login ]]; then
    printf '{"access_token":"stub-token"}'
    exit 0
fi
if [[ "$url" == */history ]]; then
    cp "$AUTOPR_TEST_HISTORY_FILE" "$output_file"
else
    cp "$AUTOPR_TEST_BUNDLE_FILE" "$output_file"
fi
[ "$write_status" = "0" ] || printf 200
EOF
chmod +x "$TMP_DIR/collect-bin/curl"
collected="$(PATH="$TMP_DIR/collect-bin:$PATH" \
    RUNNER_TEMP="$TMP_DIR/collect-runner" \
    MATCHA_AUTOPR_ENV="$env_file" \
    AUTOPR_TEST_BUNDLE_FILE="$TMP_DIR/collect-bundle.json" \
    AUTOPR_TEST_HISTORY_FILE="$TMP_DIR/collect-history.json" \
    "$AUTOPR_DIR/collect.sh" 2>"$TMP_DIR/collect-error.log")"
collect_rc=$?
check "collector admits a hand-queued card and only in an eligible lane" \
    $([ "$collect_rc" = "0" ] \
      && [ "$(printf '%s' "$collected" | jq 'length')" = "5" ] \
      && printf '%s' "$collected" | jq -e \
        'map(.id8) == ["11111111", "44444444", "55555555", "66666666", "77777777"]
         and (.[4].autopr_run_requested_at == "2026-09-02T03:00:00+00:00")
         and .[2].autopr_reconsideration_pending
         and .[2].autopr_reconsideration_event_id == "consumed-collector-event"
         and .[3].autopr_reconsideration_pending
         and .[3].autopr_reconsideration_event_id == "consumed-collector-event"' >/dev/null \
      && echo 0 || echo 1)

################################################################################
# investigate.sh packages checklist, history/discussion, GitHub feedback, and
# downloaded card files into one context passed to the model.
################################################################################
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/runner"
cat > "$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
output_file=""
write_status=0
url=""
[ -z "${AUTOPR_TEST_CURL_ARGS:-}" ] || printf '%s\n' "$*" >> "$AUTOPR_TEST_CURL_ARGS"
while [ "$#" -gt 0 ]; do
    case "$1" in
        -o) output_file="$2"; shift 2 ;;
        -w) write_status=1; shift 2 ;;
        http://*|https://*) url="$1"; shift ;;
        *) shift ;;
    esac
done
printf '%s\n' "$url" >> "${AUTOPR_TEST_CURL_URLS:-/dev/null}"
if [[ "$url" == */auth/login ]]; then
    printf '{"access_token":"stub-token"}'
    exit 0
fi
case "$url" in
    */subtasks)
        printf '[{"id":"sub-1","title":"Fix current label","is_done":false,"position":0,"round_index":6}]' > "$output_file"
        ;;
    */history)
        printf '[{"id":"event-1","event_type":"activity","metadata":{"body":"The screenshot still says note","attachment_ids":["file-1"]},"created_at":"2026-08-27T00:00:00Z"},{"id":"event-2","event_type":"review_rejected","metadata":{},"created_at":"2026-08-27T00:01:00Z"}]' > "$output_file"
        ;;
    */files)
        if [ "${AUTOPR_TEST_NO_FILES:-0}" = 1 ]; then
            printf '[]' > "$output_file"
        else
            printf '[{"id":"file-1","filename":"screen.png","storage_url":"https://files.invalid/screen.png","content_type":"image/png","file_size":8,"round_index":6,"created_at":"2026-08-27T00:00:00Z"}]' > "$output_file"
        fi
        ;;
    https://files.invalid/screen.png)
        printf 'png-stub' > "$output_file"
        ;;
    *)
        printf '{}' > "$output_file"
        ;;
esac
[ "$write_status" = "0" ] || printf 200
EOF
chmod +x "$TMP_DIR/bin/curl"

cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
    "pr list") printf '44\n' ;;
    "pr view") printf '{"reviews":[{"id":"review-44","body":"Use Journal everywhere","author":{"login":"haley"}}],"comments":[]}' ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"

cat > "$TMP_DIR/bin/codex" <<'EOF'
#!/usr/bin/env bash
printf 'Codex: inspecting card context\n'
printf '%s\n' "$@" > "$CODEX_STUB_ARGS"
prompt="${!#}"
printf '%s\n' "$prompt" | sed -n \
    '/^AUTOPR_INPUTS_BEGIN$/,/^AUTOPR_INPUTS_END$/ { s/^- //p; }' > "$CODEX_STUB_FILES"
while IFS= read -r input_path; do
    case "$(basename "$input_path")" in
        *context.json) cp "$input_path" "$CODEX_STUB_CONTEXT" ;;
    esac
done < "$CODEX_STUB_FILES"
report_path="$(printf '%s\n' "$prompt" | grep -oE '/[^ ]+/\.git/autopr-io/output/report\.md' | head -1)"
decision_path="$(printf '%s\n' "$prompt" | grep -oE '/[^ ]+/\.git/autopr-io/output/decision\.json' | head -1)"
if [ "${CODEX_STUB_FAIL:-0}" = 1 ]; then
    printf 'Codex: simulated failure\n'
    exit 17
fi
mkdir -p "$(dirname "$report_path")" "$(dirname "$decision_path")"
cat > "$report_path" <<'REPORT'
### Summary
stub
### Changes
stub
### Blast radius
stub
### Confidence
high
REPORT
cat > "$decision_path" <<'DECISION'
{
  "schema_version": 1,
  "outcome": "implementation",
  "confidence": {
    "requirements_clarity": {"score": 30, "reason": "clear card"},
    "evidence_quality": {"score": 20, "reason": "evidence attached"},
    "code_localization": {"score": 20, "reason": "known files"},
    "verification_strength": {"score": 15, "reason": "existing checks"},
    "production_alignment": {"score": 15, "reason": "baseline known"}
  },
  "criticality": {"level": "yellow", "reasons": ["scoped terminology"]},
  "questions": [],
  "safe_changes_present": true,
  "no_safe_action_reason": null
}
DECISION
EOF
chmod +x "$TMP_DIR/bin/codex"

cat > "$TMP_DIR/card.json" <<'EOF'
{"task_id":"f296d090-0000-4000-8000-000000000001","id8":"f296d090","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Standardize terminology","category":"fix","mode":"rework","review_note":"No change, including screenshot"}
EOF

PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" RUNNER_TEMP="$TMP_DIR/runner" \
GITHUB_REPOSITORY="tajaa/matcha-recruit" CODEX_STUB_FILES="$TMP_DIR/codex-files" \
CODEX_STUB_CONTEXT="$TMP_DIR/context.json" CODEX_STUB_ARGS="$TMP_DIR/codex-args" \
AUTOPR_LIVE_LOG="$TMP_DIR/live-work.log" \
AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/investigate-runtime" \
AUTOPR_SANDBOX_TEST_DIRECT=1 \
    "$AUTOPR_DIR/investigate.sh" "$TMP_DIR/card.json" "$TMP_DIR/report.md" "$TMP_DIR/decision.json" > "$TMP_DIR/investigate-command.log" 2>&1
investigate_rc=$?
[ "$investigate_rc" = 0 ] || sed -n '1,120p' "$TMP_DIR/investigate-command.log"

context_ok=1
if [ "$investigate_rc" = "0" ] \
    && jq -e '.subtasks[0].round_index == 6 and .history[0].metadata.body == "The screenshot still says note" and .downloaded_attachments[0].id == "file-1" and (.files[0] | has("storage_url") | not)' "$TMP_DIR/context.json" > /dev/null \
    && grep -q '01-screen.png' "$TMP_DIR/codex-files" \
    && grep -q 'feedback.json' "$TMP_DIR/codex-files"; then
    context_ok=0
fi
[ "$context_ok" = 0 ] || {
    printf '%s\n' 'Captured Codex inputs:'
    sed -n '1,20p' "$TMP_DIR/codex-files"
    jq . "$TMP_DIR/context.json" 2>/dev/null || true
}
check "rework investigation receives discussion, checklist, PR feedback, and screenshot" "$context_ok"

check "investigation context reserves bounded production diagnostics" \
    $(jq -e '.production == null and .production_recent_errors == [] and .production_log_signals == "" and .changes_since_production == []' "$TMP_DIR/context.json" >/dev/null && echo 0 || echo 1)

check "investigation normalizes validated confidence and triage" \
    $(jq -e '.confidence_score == 100 and .confidence_band == "high" and .awaiting_human == false and .feedback_checkpoint.review_id == "review-44"' "$TMP_DIR/decision.json" >/dev/null && echo 0 || echo 1)
cp "$TMP_DIR/decision.json" "$TMP_DIR/publication-decision.json"

check "investigation invokes Sol medium and mirrors Codex output to the live-work log" \
    $(grep -q 'CODEX LIVE STREAM' "$TMP_DIR/live-work.log" \
      && grep -q 'Codex: inspecting card context' "$TMP_DIR/live-work.log" \
      && grep -qx 'gpt-5.6-sol' "$TMP_DIR/codex-args" \
      && grep -qx 'model_reasoning_effort="medium"' "$TMP_DIR/codex-args" \
      && grep -q '\[COMPLETE\]' "$TMP_DIR/live-work.log" && echo 0 || echo 1)

# The real failure that blocked the first LaunchAgent-dispatched run happened
# before Codex: Bash 3.2 + `set -u` rejected an empty attachment array.
jq '.mode = "investigate"' "$TMP_DIR/card.json" > "$TMP_DIR/card-no-files.json"
AUTOPR_TEST_NO_FILES=1 PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" \
GITHUB_REPOSITORY="tajaa/matcha-recruit" CODEX_STUB_FILES="$TMP_DIR/codex-no-files" \
CODEX_STUB_CONTEXT="$TMP_DIR/context-no-files.json" CODEX_STUB_ARGS="$TMP_DIR/codex-no-files-args" \
AUTOPR_LIVE_LOG="$TMP_DIR/live-no-files.log" \
AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/investigate-runtime" \
AUTOPR_SANDBOX_TEST_DIRECT=1 \
    "$AUTOPR_DIR/investigate.sh" "$TMP_DIR/card-no-files.json" "$TMP_DIR/report-no-files.md" \
    "$TMP_DIR/decision-no-files.json" > /dev/null 2>&1
no_files_rc=$?
[ "$no_files_rc" = 0 ] || sed -n '1,120p' "$TMP_DIR/live-no-files.log"
no_files_count="$(wc -l < "$TMP_DIR/codex-no-files" | tr -d '[:space:]')"
check "investigation accepts a card with no attachments on macOS Bash" \
    $([ "$no_files_rc" = 0 ] \
      && [ "$no_files_count" = 1 ] \
      && jq -e '.downloaded_attachments == []' "$TMP_DIR/context-no-files.json" >/dev/null \
      && echo 0 || echo 1)
[ "$no_files_rc" != 0 ] || [ "$no_files_count" = 1 ] \
    || printf 'Expected one Codex input without attachments, got %s\n' "$no_files_count"

CODEX_STUB_FAIL=1 AUTOPR_TEST_NO_FILES=1 PATH="$TMP_DIR/bin:$PATH" \
MATCHA_AUTOPR_ENV="$env_file" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
CODEX_STUB_FILES="$TMP_DIR/codex-failed-files" CODEX_STUB_CONTEXT="$TMP_DIR/context-failed.json" \
CODEX_STUB_ARGS="$TMP_DIR/codex-failed-args" \
AUTOPR_LIVE_LOG="$TMP_DIR/live-failed.log" \
AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/investigate-runtime" \
AUTOPR_SANDBOX_TEST_DIRECT=1 \
    "$AUTOPR_DIR/investigate.sh" "$TMP_DIR/card-no-files.json" "$TMP_DIR/report-failed.md" \
    "$TMP_DIR/decision-failed.json" > /dev/null 2>&1
failed_codex_rc=$?
check "live tee preserves a failing Codex exit status" \
    $([ "$failed_codex_rc" != 0 ] \
      && grep -q '\[FAILED\] Codex exited 17' "$TMP_DIR/live-failed.log" \
      && echo 0 || echo 1)

################################################################################
# The msandbox bridge operates on a tracked-only clone and returns one patch.
# The direct seam below substitutes only for Docker/Codex; clone/input/
# output/patch behavior is the same path production uses.
################################################################################
SANDBOX_TEST_REPO="$TMP_DIR/sandbox-source"
mkdir -p "$SANDBOX_TEST_REPO/client/src" "$SANDBOX_TEST_REPO/secrets" \
  "$SANDBOX_TEST_REPO/server/app/matcha/services/huume"
git -C "$SANDBOX_TEST_REPO" init --initial-branch=main --quiet
git -C "$SANDBOX_TEST_REPO" config user.name test
git -C "$SANDBOX_TEST_REPO" config user.email test@example.com
printf 'export const existing = true;\n' > "$SANDBOX_TEST_REPO/client/src/existing.ts"
printf 'operator instructions\n' > "$SANDBOX_TEST_REPO/server/app/matcha/services/huume/CLAUDE.md"
git -C "$SANDBOX_TEST_REPO" add client/src/existing.ts server/app/matcha/services/huume/CLAUDE.md
git -C "$SANDBOX_TEST_REPO" commit --quiet -m base
printf 'host-only-secret\n' > "$SANDBOX_TEST_REPO/secrets/private.pem"

# Simulate a model killed before the bridge copied its output into RUNNER_TEMP.
# The checkpoint must capture tracked + untracked edits directly from the
# disposable workspace and make them available to the next sandbox attempt.
CHECKPOINT_RUNTIME="$TMP_DIR/checkpoint-runtime"
mkdir -p "$CHECKPOINT_RUNTIME"
git clone --quiet "$SANDBOX_TEST_REPO" "$CHECKPOINT_RUNTIME/workspace"
checkpoint_base="$(git -C "$CHECKPOINT_RUNTIME/workspace" rev-parse HEAD)"
mkdir -p "$CHECKPOINT_RUNTIME/workspace/.git/autopr-io/output"
printf '%s\n' "$checkpoint_base" \
    > "$CHECKPOINT_RUNTIME/workspace/.git/autopr-io/model-base-sha"
printf 'cccccccc-0000-4000-8000-000000000003\n' \
    > "$CHECKPOINT_RUNTIME/workspace/.git/autopr-io/task-id"
printf 'export const existing = false;\n' \
    > "$CHECKPOINT_RUNTIME/workspace/client/src/existing.ts"
printf 'export const recovered = true;\n' \
    > "$CHECKPOINT_RUNTIME/workspace/client/src/recovered.ts"
printf '%s\n' '### Summary' partial \
    > "$CHECKPOINT_RUNTIME/workspace/.git/autopr-io/output/report.md"
printf '%s\n' '{"schema_version":1}' \
    > "$CHECKPOINT_RUNTIME/workspace/.git/autopr-io/output/decision.json"
printf 'partial transcript\n' > "$TMP_DIR/checkpoint-live.log"
cat > "$TMP_DIR/checkpoint-card.json" <<'EOF'
{"task_id":"cccccccc-0000-4000-8000-000000000003","id8":"cccccccc","project_id":"dddddddd-0000-4000-8000-000000000004"}
EOF
checkpoint_path="$(AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$CHECKPOINT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    AUTOPR_SANDBOX_TEST_DIRECT=1 \
    "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/checkpoint-card.json" \
    "$TMP_DIR/missing-report" "$TMP_DIR/missing-decision" "$(date +%s)" 20)"
latest_checkpoint="$(AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    "$AUTOPR_DIR/checkpoint.sh" latest "$TMP_DIR/checkpoint-card.json")"
check "interrupted model work is checkpointed outside the disposable workspace" \
    $([ "$latest_checkpoint" = "$checkpoint_path" ] \
      && grep -q 'recovered.ts' "$checkpoint_path/model.patch" \
      && grep -q 'partial transcript' "$checkpoint_path/transcript.log" \
      && jq -e '.patch_saved == true and .runtime_limited == false and .changed_file_count == 2' \
        "$checkpoint_path/metadata.json" >/dev/null \
      && echo 0 || echo 1)

timeout_started_at="$(( $(date +%s) - 1200 ))"
runtime_checkpoint_path="$(PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" \
    AUTOPR_TEST_CURL_ARGS="$TMP_DIR/checkpoint-curl-args" \
    AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$CHECKPOINT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    AUTOPR_SANDBOX_TEST_DIRECT=1 GITHUB_RUN_ID=timeout-test \
    "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/checkpoint-card.json" \
    "$TMP_DIR/missing-report" "$TMP_DIR/missing-decision" "$timeout_started_at" 20)"
check "timed-out work moves to Changes Requested with a readable approval card" \
    $(jq -e '.runtime_limited == true and .changed_file_count == 2
        and .progress_excerpt == "partial"' \
        "$runtime_checkpoint_path/metadata.json" >/dev/null \
      && grep -q 'changes_requested' "$TMP_DIR/checkpoint-curl-args" \
      && grep -q 'Why more time' "$TMP_DIR/checkpoint-curl-args" \
      && grep -q 'Done so far' "$TMP_DIR/checkpoint-curl-args" \
      && grep -q 'Approve 10 more minutes' "$TMP_DIR/checkpoint-curl-args" \
      && echo 0 || echo 1)

# The pause note replaces progress_note wholesale, so it has to carry forward
# every durable marker the rest of the system reads out of that field.
cat > "$TMP_DIR/checkpoint-card-with-note.json" <<'EOF'
{"task_id":"11112222-0000-4000-8000-000000000011","id8":"11112222","project_id":"dddddddd-0000-4000-8000-000000000004","progress_note":"🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build 550 · prod abc · PR #7 · 🟡 C42 · [autopr:directives draft_pr] · note: n\nAnswers needed — reply below with the numbered choices:\n1. Which term is canonical?"}
EOF
: > "$TMP_DIR/preserved-curl-args"
PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" \
    AUTOPR_TEST_CURL_ARGS="$TMP_DIR/preserved-curl-args" \
    AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$CHECKPOINT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    AUTOPR_SANDBOX_TEST_DIRECT=1 GITHUB_RUN_ID=preserve-test \
    "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/checkpoint-card-with-note.json" \
    "$TMP_DIR/missing-report" "$TMP_DIR/missing-decision" "$timeout_started_at" 20 >/dev/null
check "the pause note keeps the standing directive grant and the pending questions" \
    $(grep -q 'autopr:directives draft_pr' "$TMP_DIR/preserved-curl-args" \
      && grep -q 'Which term is canonical' "$TMP_DIR/preserved-curl-args" \
      && grep -q 'PAUSED: APPROVE 10 MORE MINUTES' "$TMP_DIR/preserved-curl-args" \
      && echo 0 || echo 1)

# A harness or model failure is not a legitimate conclusion: it must never
# write the marker that blocks the card behind a human approval.
cat > "$TMP_DIR/crash-card.json" <<'EOF'
{"task_id":"22223333-0000-4000-8000-000000000022","id8":"22223333","project_id":"dddddddd-0000-4000-8000-000000000004"}
EOF
cat > "$TMP_DIR/signal-card.json" <<'EOF'
{"task_id":"33334444-0000-4000-8000-000000000033","id8":"33334444","project_id":"dddddddd-0000-4000-8000-000000000004"}
EOF
: > "$TMP_DIR/crash-curl-args"
printf '1\n' > "$TMP_DIR/investigation-exit-code"
crash_checkpoint_path="$(PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" \
    AUTOPR_TEST_CURL_ARGS="$TMP_DIR/crash-curl-args" \
    AUTOPR_INVESTIGATION_EXIT_FILE="$TMP_DIR/investigation-exit-code" \
    AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$CHECKPOINT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    AUTOPR_SANDBOX_TEST_DIRECT=1 GITHUB_RUN_ID=crash-test \
    "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/crash-card.json" \
    "$TMP_DIR/missing-report" "$TMP_DIR/missing-decision" "$timeout_started_at" 20)"
check "a crash inside the time limit checkpoints without pausing the card" \
    $(jq -e '.runtime_limited == false' "$crash_checkpoint_path/metadata.json" >/dev/null \
      && [ ! -s "$TMP_DIR/crash-curl-args" ] \
      && echo 0 || echo 1)

# A killed run either leaves no status behind or reports a signal.
printf '143\n' > "$TMP_DIR/investigation-exit-code"
signal_checkpoint_path="$(PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" \
    AUTOPR_TEST_CURL_ARGS="$TMP_DIR/signal-curl-args" \
    AUTOPR_INVESTIGATION_EXIT_FILE="$TMP_DIR/investigation-exit-code" \
    AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$CHECKPOINT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    AUTOPR_SANDBOX_TEST_DIRECT=1 GITHUB_RUN_ID=signal-test \
    "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/signal-card.json" \
    "$TMP_DIR/missing-report" "$TMP_DIR/missing-decision" "$timeout_started_at" 20)"
check "a signal-killed investigation still pauses for approval" \
    $(jq -e '.runtime_limited == true' "$signal_checkpoint_path/metadata.json" >/dev/null \
      && echo 0 || echo 1)
rm -f "$TMP_DIR/investigation-exit-code"

# A workspace left behind by another card must never be harvested: its patch
# would reach the wrong PR.
cat > "$TMP_DIR/foreign-card.json" <<'EOF'
{"task_id":"eeeeeeee-0000-4000-8000-000000000005","id8":"eeeeeeee","project_id":"dddddddd-0000-4000-8000-000000000004"}
EOF
foreign_checkpoint_path="$(PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" \
    AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$CHECKPOINT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    AUTOPR_SANDBOX_TEST_DIRECT=1 GITHUB_RUN_ID=foreign-test \
    "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/foreign-card.json" \
    "$TMP_DIR/missing-report" "$TMP_DIR/missing-decision" "$(date +%s)" 20 2>/dev/null)"
check "a sandbox left over from another card is never checkpointed as this one" \
    $(jq -e '.patch_saved == false and .changed_file_count == 0' \
        "$foreign_checkpoint_path/metadata.json" >/dev/null \
      && [ ! -e "$foreign_checkpoint_path/model.patch" ] \
      && echo 0 || echo 1)

cat > "$TMP_DIR/prune-card.json" <<'EOF'
{"task_id":"44445555-0000-4000-8000-000000000044","id8":"44445555","project_id":"dddddddd-0000-4000-8000-000000000004"}
EOF
for prune_run in prune-1 prune-2 prune-3; do
    PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" \
        AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
        AUTOPR_SANDBOX_RUNTIME_ROOT="$CHECKPOINT_RUNTIME" \
        AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
        AUTOPR_CHECKPOINT_MAX_PER_TASK=2 \
        AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
        AUTOPR_SANDBOX_TEST_DIRECT=1 GITHUB_RUN_ID="$prune_run" \
        "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/prune-card.json" \
        "$TMP_DIR/missing-report" "$TMP_DIR/missing-decision" "$(date +%s)" 20 \
        >/dev/null 2>&1
    sleep 1
done
check "checkpoints are bounded instead of accumulating under .git forever" \
    $([ "$(find "$TMP_DIR/checkpoints/44445555-0000-4000-8000-000000000044" \
        -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d '[:space:]')" = 2 ] \
      && echo 0 || echo 1)

check "the resumed transcript stays small enough to leave the model room to work" \
    $(grep -qF 'AUTOPR_CHECKPOINT_MAX_TRANSCRIPT_BYTES:-131072' "$AUTOPR_DIR/checkpoint.sh" \
      && [ "$(wc -c < "$checkpoint_path/transcript.log" | tr -d '[:space:]')" -le 131072 ] \
      && echo 0 || echo 1)

# checkpoint.sh save only runs as its own workflow step. A hard kill (machine
# death, SIGKILL, Docker restart) skips it entirely and the next run wipes the
# sandbox, so the investigation snapshots itself on a timer while the model
# still holds the workspace.
SNAPSHOT_RUNTIME="$TMP_DIR/snapshot-runtime"
mkdir -p "$SNAPSHOT_RUNTIME"
git clone --quiet "$SANDBOX_TEST_REPO" "$SNAPSHOT_RUNTIME/workspace"
snapshot_base="$(git -C "$SNAPSHOT_RUNTIME/workspace" rev-parse HEAD)"
mkdir -p "$SNAPSHOT_RUNTIME/workspace/.git/autopr-io/output"
printf '%s\n' "$snapshot_base" \
    > "$SNAPSHOT_RUNTIME/workspace/.git/autopr-io/model-base-sha"
printf '55556666-0000-4000-8000-000000000055\n' \
    > "$SNAPSHOT_RUNTIME/workspace/.git/autopr-io/task-id"
printf 'export const inflight = true;\n' \
    > "$SNAPSHOT_RUNTIME/workspace/client/src/inflight.ts"
printf '%s\n' '### Summary' 'still working' \
    > "$SNAPSHOT_RUNTIME/workspace/.git/autopr-io/output/report.md"
cat > "$TMP_DIR/snapshot-card.json" <<'EOF'
{"task_id":"55556666-0000-4000-8000-000000000055","id8":"55556666","project_id":"dddddddd-0000-4000-8000-000000000004"}
EOF
snapshot_index_before="$(shasum "$SNAPSHOT_RUNTIME/workspace/.git/index" | cut -d' ' -f1)"
snapshot_dir="$(AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$SNAPSHOT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    GITHUB_RUN_ID=snapshot-test \
    "$AUTOPR_DIR/checkpoint.sh" snapshot "$TMP_DIR/snapshot-card.json")"
snapshot_latest="$(AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    "$AUTOPR_DIR/checkpoint.sh" latest "$TMP_DIR/snapshot-card.json")"
snapshot_index_after="$(shasum "$SNAPSHOT_RUNTIME/workspace/.git/index" | cut -d' ' -f1)"
check "an in-flight snapshot captures live model work and becomes resumable" \
    $([ -n "$snapshot_dir" ] && [ "$snapshot_dir" = "$snapshot_latest" ] \
      && grep -q 'inflight.ts' "$snapshot_dir/model.patch" \
      && git -C "$SANDBOX_TEST_REPO" apply --check --binary "$snapshot_dir/model.patch" \
      && jq -e '.inflight == true and .patch_saved == true and .report_saved == true' \
        "$snapshot_dir/metadata.json" >/dev/null \
      && echo 0 || echo 1)

check "snapshots never fight the live container for its git index" \
    $([ "$snapshot_index_before" = "$snapshot_index_after" ] \
      && [ -f "$SNAPSHOT_RUNTIME/snapshot.index" ] \
      && echo 0 || echo 1)

snapshot_foreign="$(AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$SNAPSHOT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    GITHUB_RUN_ID=snapshot-test \
    "$AUTOPR_DIR/checkpoint.sh" snapshot "$TMP_DIR/foreign-card.json")"
check "an in-flight snapshot refuses a sandbox belonging to another card" \
    $([ -z "$snapshot_foreign" ] && echo 0 || echo 1)

# The pointer is the whole value of a snapshot: an empty later save must not
# take it away.
empty_save_path="$(PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" \
    AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$CHECKPOINT_RUNTIME" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    AUTOPR_LIVE_LOG="$TMP_DIR/checkpoint-live.log" \
    AUTOPR_SANDBOX_TEST_DIRECT=1 GITHUB_RUN_ID=empty-save-test \
    "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/snapshot-card.json" \
    "$TMP_DIR/missing-report" "$TMP_DIR/missing-decision" "$(date +%s)" 20 2>/dev/null)"
still_resumable="$(AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    "$AUTOPR_DIR/checkpoint.sh" latest "$TMP_DIR/snapshot-card.json")"
check "an empty save never steals the resume pointer from real saved work" \
    $([ -n "$empty_save_path" ] && [ "$still_resumable" = "$snapshot_dir" ] \
      && echo 0 || echo 1)

check "the investigation snapshots itself on a bounded, self-terminating timer" \
    $(grep -qF 'checkpoint.sh" snapshot' "$AUTOPR_DIR/investigate.sh" \
      && grep -qF 'AUTOPR_SNAPSHOT_INTERVAL_SECONDS:-240' "$AUTOPR_DIR/investigate.sh" \
      && grep -qF 'kill -0 "$parent"' "$AUTOPR_DIR/investigate.sh" \
      && grep -qF 'kill "$SNAPSHOT_PID"' "$AUTOPR_DIR/investigate.sh" \
      && echo 0 || echo 1)

cat > "$TMP_DIR/bin/codex" <<'EOF'
#!/usr/bin/env bash
prompt="${!#}"
report_path="$(printf '%s\n' "$prompt" | sed -n 's/^REPORT=//p')"
decision_path="$(printf '%s\n' "$prompt" | sed -n 's/^DECISION=//p')"
first_input="$(printf '%s\n' "$prompt" | sed -n \
    '/^AUTOPR_INPUTS_BEGIN$/,/^AUTOPR_INPUTS_END$/ { s/^- //p; }' | head -1)"
workspace=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
    [ "${args[$i]}" != -C ] || workspace="${args[$((i + 1))]}"
done
cd "$workspace"
[ ! -e secrets/private.pem ] || exit 31
[ -z "$(git remote)" ] || exit 32
cp "$first_input" "$AUTOPR_SANDBOX_CAPTURE_CONTEXT"
mkdir -p "$(dirname "$report_path")" "$(dirname "$decision_path")" client/src
printf '%s\n' '### Summary' sandbox '### Changes' sandbox '### Blast radius' none '### Confidence' high > "$report_path"
printf '%s\n' '{"schema_version":1,"outcome":"implementation"}' > "$decision_path"
printf 'export const sandboxProbe = true;\n' > client/src/sandbox-probe.ts
printf 'model note\n' >> server/app/matcha/services/huume/CLAUDE.md
EOF
chmod +x "$TMP_DIR/bin/codex"

printf '%s\n' 'REPORT=REPORT_PATH' 'DECISION=DECISION_PATH' > "$TMP_DIR/sandbox-prompt.txt"
printf 'attachment\n' > "$TMP_DIR/sandbox-attachment.txt"
jq -n --arg path "$TMP_DIR/sandbox-attachment.txt" \
  '{downloaded_attachments:[{id:"attachment-1",local_path:$path}]}' > "$TMP_DIR/sandbox-context.json"

PATH="$TMP_DIR/bin:$PATH" AUTOPR_SANDBOX_TEST_DIRECT=1 \
AUTOPR_SANDBOX_REPO_ROOT="$SANDBOX_TEST_REPO" \
AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox-runtime" \
AUTOPR_RESUME_PATCH="$checkpoint_path/model.patch" \
AUTOPR_SANDBOX_CAPTURE_CONTEXT="$TMP_DIR/sandbox-captured-context.json" \
  "$AUTOPR_DIR/run-codex-sandboxed.sh" "$TMP_DIR/sandbox-prompt.txt" \
  "$TMP_DIR/sandbox-report.md" "$TMP_DIR/sandbox-decision.json" \
  -f "$TMP_DIR/sandbox-context.json" -f "$TMP_DIR/sandbox-attachment.txt" \
  >"$TMP_DIR/sandbox-bridge.log" 2>&1
sandbox_bridge_rc=$?
[ "$sandbox_bridge_rc" = 0 ] || sed -n '1,120p' "$TMP_DIR/sandbox-bridge.log"

check "msandbox bridge excludes secrets and instruction edits while applying the product patch" \
    $([ "$sandbox_bridge_rc" = 0 ] \
      && grep -q 'sandboxProbe' "$SANDBOX_TEST_REPO/client/src/sandbox-probe.ts" \
      && grep -q 'recovered' "$SANDBOX_TEST_REPO/client/src/recovered.ts" \
      && [ "$(cat "$SANDBOX_TEST_REPO/server/app/matcha/services/huume/CLAUDE.md")" = "operator instructions" ] \
      && grep -q 'Ignored model edit to operator instruction file' "$TMP_DIR/sandbox-bridge.log" \
      && [ -s "$TMP_DIR/sandbox-report.md" ] \
      && [ ! -e "$SANDBOX_TEST_REPO/.autopr-io" ] \
      && echo 0 || echo 1)

AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    "$AUTOPR_DIR/checkpoint.sh" consume "$TMP_DIR/checkpoint-card.json"
consumed_checkpoint="$(AUTOPR_WORKSPACE_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
    "$AUTOPR_DIR/checkpoint.sh" latest "$TMP_DIR/checkpoint-card.json")"
check "a completed retry deactivates but does not delete its saved checkpoint" \
    $([ -z "$consumed_checkpoint" ] && [ -d "$checkpoint_path" ] && echo 0 || echo 1)

mapped_attachment="$(jq -r '.downloaded_attachments[0].local_path' "$TMP_DIR/sandbox-captured-context.json" 2>/dev/null)"
check "msandbox bridge rewrites attachment paths into the isolated workspace" \
    $([ -n "$mapped_attachment" ] \
      && [ "$mapped_attachment" != "$TMP_DIR/sandbox-attachment.txt" ] \
      && [[ "$mapped_attachment" == "$TMP_DIR/sandbox-runtime/workspace/"* ]] \
      && echo 0 || echo 1)

rm -f "$SANDBOX_TEST_REPO/client/src/sandbox-probe.ts"
PATH="$TMP_DIR/bin:$PATH" AUTOPR_SANDBOX_TEST_DIRECT=1 \
AUTOPR_SANDBOX_MAX_CHANGED_FILES=0 \
AUTOPR_SANDBOX_REPO_ROOT="$SANDBOX_TEST_REPO" \
AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox-runtime" \
AUTOPR_SANDBOX_CAPTURE_CONTEXT="$TMP_DIR/sandbox-captured-context.json" \
  "$AUTOPR_DIR/run-codex-sandboxed.sh" "$TMP_DIR/sandbox-prompt.txt" \
  "$TMP_DIR/sandbox-report-capped.md" "$TMP_DIR/sandbox-decision-capped.json" \
  -f "$TMP_DIR/sandbox-context.json" -f "$TMP_DIR/sandbox-attachment.txt" \
  >/dev/null 2>&1
sandbox_cap_rc=$?
check "msandbox bridge enforces the mechanical changed-file cap before apply" \
    $([ "$sandbox_cap_rc" != 0 ] \
      && [ ! -e "$SANDBOX_TEST_REPO/client/src/sandbox-probe.ts" ] \
      && echo 0 || echo 1)

################################################################################
# Publication copy is a separate Luna-medium task. Its prose is validated and
# the sandbox bridge must reject any attempt by this writing-only pass to edit.
################################################################################
cat > "$TMP_DIR/bin/codex" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$CODEX_STUB_ARGS"
prompt="${!#}"
report_path="$(printf '%s\n' "$prompt" | grep -oE '/[^ ]+/\.git/autopr-io/output/report\.md' | head -1)"
decision_path="$(printf '%s\n' "$prompt" | grep -oE '/[^ ]+/\.git/autopr-io/output/decision\.json' | head -1)"
workspace=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
    [ "${args[$i]}" != -C ] || workspace="${args[$((i + 1))]}"
done
mkdir -p "$(dirname "$report_path")" "$(dirname "$decision_path")"
printf '%s\n' '### Publication copy' 'stub' > "$report_path"
if [[ "$prompt" == *'one commit subject for a completed Matcha AutoPR code change'* ]]; then
    printf '%s\n' '{"schema_version":1,"commit_subject":"fix: standardize terminology"}' > "$decision_path"
else
    printf '%s\n' '{"schema_version":1,"commit_subject":"fix: standardize terminology","card_note":"Needs the canonical term before the draft can be completed safely."}' > "$decision_path"
fi
[ "${CODEX_STUB_EDIT:-0}" != 1 ] || printf 'unexpected\n' > "$workspace/client/src/luna-edit.ts"
EOF
chmod +x "$TMP_DIR/bin/codex"
printf '%s\n' '## Verification' '' 'Focused checks passed.' > "$TMP_DIR/publication-verification.md"

PATH="$TMP_DIR/bin:$PATH" CODEX_STUB_ARGS="$TMP_DIR/luna-args" \
AUTOPR_SANDBOX_TEST_DIRECT=1 AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/publication-runtime" \
  "$AUTOPR_DIR/write-publication-copy.sh" "$TMP_DIR/card.json" "$TMP_DIR/publication-decision.json" \
  "$TMP_DIR/report.md" "$TMP_DIR/publication-verification.md" "$TMP_DIR/publication-copy.json" \
  >"$TMP_DIR/publication-command.log" 2>&1
publication_copy_rc=$?
[ "$publication_copy_rc" = 0 ] || sed -n '1,120p' "$TMP_DIR/publication-command.log"
check "publication writer uses Luna medium and validates its bounded output" \
    $([ "$publication_copy_rc" = 0 ] \
      && jq -e '.commit_subject == "fix: standardize terminology" and (.card_note | contains("canonical term"))' "$TMP_DIR/publication-copy.json" >/dev/null \
      && grep -qx 'gpt-5.6-luna' "$TMP_DIR/luna-args" \
      && grep -qx 'model_reasoning_effort="medium"' "$TMP_DIR/luna-args" \
      && echo 0 || echo 1)

jq '.category = "feat"' "$TMP_DIR/card.json" > "$TMP_DIR/feat-card.json"
PATH="$TMP_DIR/bin:$PATH" CODEX_STUB_ARGS="$TMP_DIR/feat-luna-args" \
AUTOPR_SANDBOX_TEST_DIRECT=1 AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/publication-runtime" \
  "$AUTOPR_DIR/write-publication-copy.sh" "$TMP_DIR/feat-card.json" "$TMP_DIR/publication-decision.json" \
  "$TMP_DIR/report.md" "$TMP_DIR/publication-verification.md" "$TMP_DIR/feat-publication-copy.json" \
  >/dev/null 2>&1
feat_publication_copy_rc=$?
check "publication writer repairs a model-selected commit prefix without dropping the card outcome" \
    $([ "$feat_publication_copy_rc" = 0 ] \
      && jq -e '.commit_subject == "feat: standardize terminology" and (.card_note | contains("canonical term"))' "$TMP_DIR/feat-publication-copy.json" >/dev/null \
      && echo 0 || echo 1)

PATH="$TMP_DIR/bin:$PATH" CODEX_STUB_ARGS="$TMP_DIR/commit-luna-args" \
AUTOPR_SANDBOX_TEST_DIRECT=1 AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/publication-runtime" \
  "$AUTOPR_DIR/write-commit-subject.sh" fix "$TMP_DIR/commit-subject.json" \
  -f "$TMP_DIR/card.json" -f "$TMP_DIR/publication-decision.json" -f "$TMP_DIR/report.md" \
  -f "$TMP_DIR/publication-verification.md" >/dev/null 2>&1
commit_subject_rc=$?
check "commit-subject writer uses Luna medium and validates its bounded output" \
    $([ "$commit_subject_rc" = 0 ] \
      && jq -e '.commit_subject == "fix: standardize terminology"' "$TMP_DIR/commit-subject.json" >/dev/null \
      && grep -qx 'gpt-5.6-luna' "$TMP_DIR/commit-luna-args" \
      && grep -qx 'model_reasoning_effort="medium"' "$TMP_DIR/commit-luna-args" \
      && echo 0 || echo 1)

CODEX_STUB_EDIT=1 PATH="$TMP_DIR/bin:$PATH" CODEX_STUB_ARGS="$TMP_DIR/luna-edit-args" \
AUTOPR_SANDBOX_TEST_DIRECT=1 AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/publication-runtime" \
  "$AUTOPR_DIR/write-publication-copy.sh" "$TMP_DIR/card.json" "$TMP_DIR/publication-decision.json" \
  "$TMP_DIR/report.md" "$TMP_DIR/publication-verification.md" "$TMP_DIR/publication-copy-edit.json" \
  >/dev/null 2>&1
publication_edit_rc=$?
check "publication writer rejects Luna repository edits before applying them" \
    $([ "$publication_edit_rc" != 0 ] \
      && [ ! -e "$REPO_ROOT/client/src/luna-edit.ts" ] \
      && echo 0 || echo 1)

cp "$TMP_DIR/publication-decision.json" "$TMP_DIR/invalid-decision.json"
jq '.outcome = "questions_only" | .questions = [] | .safe_changes_present = false' \
    "$TMP_DIR/invalid-decision.json" > "$TMP_DIR/invalid-decision.next.json"
mv "$TMP_DIR/invalid-decision.next.json" "$TMP_DIR/invalid-decision.json"
"$AUTOPR_DIR/decision.sh" normalize "$TMP_DIR/invalid-decision.json" "$TMP_DIR/invalid-decision.normalized.json" >/dev/null 2>&1
invalid_decision_rc=$?
check "questions-only decisions require actionable questions" \
    $([ "$invalid_decision_rc" != 0 ] && echo 0 || echo 1)

jq '.questions = [
      {id:"q1",question:"First choice?",why_blocking:"Needed",default_assumption:"Choose A",options:[{key:"a",label:"A",impact:"First"},{key:"b",label:"B",impact:"Second"}]},
      {id:"q2",question:"Second choice?",why_blocking:"Needed",default_assumption:"Choose B",options:[{key:"a",label:"A",impact:"First"},{key:"b",label:"B",impact:"Second"}]}
    ]' "$TMP_DIR/publication-decision.json" > "$TMP_DIR/question-render-decision.json"
question_pr_copy="$(/bin/bash -c 'source "$1"; autopr_render_questions "$2"' _ \
    "$AUTOPR_DIR/decision.sh" "$TMP_DIR/question-render-decision.json")"
question_card_copy="$(/bin/bash -c 'source "$1"; autopr_render_card_questions "$2"' _ \
    "$AUTOPR_DIR/decision.sh" "$TMP_DIR/question-render-decision.json")"
check "question drafts are numbered and expose an in-ticket answer path" \
    $(printf '%s\n%s' "$question_pr_copy" "$question_card_copy" \
      | grep -qF '2. Second choice?' \
      && printf '%s' "$question_pr_copy" | grep -qF 'Add additional context' \
      && printf '%s' "$question_card_copy" | grep -qF 'reply below with the numbered choices' \
      && echo 0 || echo 1)

jq '.production_verification = {
      target:"frontend",
      mode:"automatic_http",
      reason:"Query strings are outside the verifier allowlist.",
      checks:[{path:"/app/jobs?tab=creds",expected_status:200}],
      steps:[]
    }' "$TMP_DIR/publication-decision.json" > "$TMP_DIR/invalid-production-check.json"
"$AUTOPR_DIR/decision.sh" normalize "$TMP_DIR/invalid-production-check.json" \
    "$TMP_DIR/invalid-production-check.normalized.json" >/dev/null 2>&1
invalid_production_check_rc=$?
check "decision and deploy verifier share the production HTTP allowlist" \
    $([ "$invalid_production_check_rc" != 0 ] \
      && grep -q 'include "production-check"' "$AUTOPR_DIR/decision.sh" \
      && grep -q 'include "production-check"' "$AUTOPR_DIR/verify-production-fixes.sh" \
      && echo 0 || echo 1)

jq '.outcome = "no_safe_action"
    | .safe_changes_present = false
    | .questions = []
    | .no_safe_action_reason = "already_fixed"' \
    "$TMP_DIR/publication-decision.json" > "$TMP_DIR/already-fixed-decision.json"
jq -n '{directives:["draft_pr","trust_still_broken"],test_route:"/app/jobs"}' \
    > "$TMP_DIR/forced-policy.json"
"$AUTOPR_DIR/decision.sh" normalize "$TMP_DIR/already-fixed-decision.json" \
    "$TMP_DIR/forced-decision.json" "$TMP_DIR/forced-policy.json" >/dev/null 2>&1
forced_already_fixed_rc=$?
check "decision-bound force directives reject another already-fixed exit" \
    $([ "$forced_already_fixed_rc" != 0 ] && echo 0 || echo 1)

jq '.no_safe_action_reason = "migration_required"' \
    "$TMP_DIR/already-fixed-decision.json" > "$TMP_DIR/migration-required-decision.json"
"$AUTOPR_DIR/decision.sh" normalize "$TMP_DIR/migration-required-decision.json" \
    "$TMP_DIR/forced-migration-decision.json" "$TMP_DIR/forced-policy.json" >/dev/null 2>&1
forced_migration_rc=$?
check "decision-bound draft directive requires authoring a needed migration" \
    $([ "$forced_migration_rc" != 0 ] && echo 0 || echo 1)

cat > "$TMP_DIR/pending-directive-card.json" <<'EOF'
{"autopr_reconsideration_pending":true,"autopr_reconsideration_event_id":"old-event"}
EOF
cat > "$TMP_DIR/pending-directive-history.json" <<'EOF'
[
  {"id":"unrelated","metadata":{"kind":"autopr_additional_context","body":"draft this PR"}},
  {"id":"old-event","metadata":{"kind":"autopr_additional_context","body":"just go ahead and do it anyways"}}
]
EOF
python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
    --card "$TMP_DIR/pending-directive-card.json" \
    --history "$TMP_DIR/pending-directive-history.json" \
    --output "$TMP_DIR/resolved-old-directive.json"
check "pre-upgrade decision-bound context still grants the requested draft" \
    $(jq -e '.directives == ["draft_pr"] and .source_event_id == "old-event"' \
      "$TMP_DIR/resolved-old-directive.json" >/dev/null && echo 0 || echo 1)

cat > "$TMP_DIR/runtime-card.json" <<'EOF'
{"task_id":"aaaaaaaa-0000-4000-8000-000000000001","id8":"aaaaaaaa","project_id":"bbbbbbbb-0000-4000-8000-000000000002","board_column":"changes_requested","progress_note":"🤖 AUTO SETUP · PAUSED: RUNTIME APPROVAL REQUIRED","autopr_reconsideration_pending":true,"autopr_reconsideration_event_id":"runtime-event"}
EOF
cat > "$TMP_DIR/runtime-history.json" <<'EOF'
[{"id":"runtime-event","metadata":{"kind":"autopr_additional_context","body":"--extend-runtime"}}]
EOF
# The 10 minutes continue saved work, so the approval only shortens a run that
# actually has a checkpoint to resume.
RUNTIME_CHECKPOINTS="$TMP_DIR/runtime-checkpoints"
runtime_task_root="$RUNTIME_CHECKPOINTS/aaaaaaaa-0000-4000-8000-000000000001"
mkdir -p "$runtime_task_root/run-1"
jq -n --arg created_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    '{schema_version:1,created_at:$created_at,patch_saved:true}' \
    > "$runtime_task_root/run-1/metadata.json"
printf 'run-1\n' > "$runtime_task_root/active"

AUTOPR_RUNTIME_HISTORY_FILE="$TMP_DIR/runtime-history.json" \
    AUTOPR_CHECKPOINT_ROOT="$RUNTIME_CHECKPOINTS" \
    "$AUTOPR_DIR/runtime-policy.sh" "$TMP_DIR/runtime-card.json" \
    "$TMP_DIR/extended-runtime-policy.json"
check "a decision-bound runtime approval grants a 10-minute continuation" \
    $(jq -e '.minutes == 10 and .extended == true and .directives == ["extend_runtime"]' \
      "$TMP_DIR/extended-runtime-policy.json" >/dev/null && echo 0 || echo 1)

AUTOPR_RUNTIME_HISTORY_FILE="$TMP_DIR/runtime-history.json" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/empty-checkpoints" \
    "$AUTOPR_DIR/runtime-policy.sh" "$TMP_DIR/runtime-card.json" \
    "$TMP_DIR/unresumable-runtime-policy.json"
check "a runtime approval never halves a from-scratch investigation" \
    $(jq -e '.minutes == 20 and .extended == false and .checkpoint == null' \
      "$TMP_DIR/unresumable-runtime-policy.json" >/dev/null && echo 0 || echo 1)

runtime_stale_root="$TMP_DIR/stale-checkpoints/aaaaaaaa-0000-4000-8000-000000000001"
mkdir -p "$runtime_stale_root/run-old"
jq -n '{schema_version:1,created_at:"2026-01-01T00:00:00Z",patch_saved:true}' \
    > "$runtime_stale_root/run-old/metadata.json"
printf 'run-old\n' > "$runtime_stale_root/active"
AUTOPR_RUNTIME_HISTORY_FILE="$TMP_DIR/runtime-history.json" \
    AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/stale-checkpoints" \
    "$AUTOPR_DIR/runtime-policy.sh" "$TMP_DIR/runtime-card.json" \
    "$TMP_DIR/stale-runtime-policy.json"
check "an expired checkpoint is neither resumed nor treated as a continuation" \
    $(jq -e '.minutes == 20 and .extended == false and .checkpoint == null' \
      "$TMP_DIR/stale-runtime-policy.json" >/dev/null && echo 0 || echo 1)

jq '.[0].metadata.body = "Here is more evidence, but no time approval."' \
    "$TMP_DIR/runtime-history.json" > "$TMP_DIR/normal-runtime-history.json"
AUTOPR_RUNTIME_HISTORY_FILE="$TMP_DIR/normal-runtime-history.json" \
    AUTOPR_CHECKPOINT_ROOT="$RUNTIME_CHECKPOINTS" \
    "$AUTOPR_DIR/runtime-policy.sh" "$TMP_DIR/runtime-card.json" \
    "$TMP_DIR/normal-runtime-policy.json"
check "ordinary additional context remains capped at 20 minutes" \
    $(jq -e '.minutes == 20 and .extended == false and .directives == []' \
      "$TMP_DIR/normal-runtime-policy.json" >/dev/null && echo 0 || echo 1)

cat > "$TMP_DIR/consumed-directive-card.json" <<'EOF'
{"board_column":"todo","progress_note":"🤖 AUTO SETUP · NO PR: ALREADY FIXED · [autopr:no-spec 2026-09-02T01:00:00Z] already_fixed","autopr_reconsideration_pending":false}
EOF
cat > "$TMP_DIR/consumed-directive-history.json" <<'EOF'
[
  {"id":"consumed-event","created_at":"2026-09-02T00:59:00Z","metadata":{"kind":"autopr_additional_context","body":"just go ahead and do it anyways","autopr_reconsideration_of":"🤖 AUTO SETUP · NO PR: ALREADY FIXED · [autopr:no-spec 2026-09-02T00:30:00Z] already_fixed"}}
]
EOF
python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
    --recover-consumed \
    --card "$TMP_DIR/consumed-directive-card.json" \
    --history "$TMP_DIR/consumed-directive-history.json" \
    --output "$TMP_DIR/recovered-consumed-directive.json"
check "legacy go-ahead context survives one obsolete repeated already-fixed result" \
    $(jq -e '.directives == ["draft_pr"] and .source_event_id == "consumed-event"' \
      "$TMP_DIR/recovered-consumed-directive.json" >/dev/null && echo 0 || echo 1)

jq '.progress_note = "🤖 AUTO SETUP · NO PR: POLICY BLOCKED · [autopr:no-spec 2026-09-02T01:00:00Z] policy_blocked"' \
    "$TMP_DIR/consumed-directive-card.json" > "$TMP_DIR/nonrecoverable-card.json"
python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
    --recover-consumed \
    --card "$TMP_DIR/nonrecoverable-card.json" \
    --history "$TMP_DIR/consumed-directive-history.json" \
    --output "$TMP_DIR/nonrecovered-directive.json"
check "consumed directive recovery cannot override a different current blocker" \
    $(jq -e '.directives == [] and .source_event_id == null' \
      "$TMP_DIR/nonrecovered-directive.json" >/dev/null && echo 0 || echo 1)

for phrasing in "you can work on this." "do it anyway" "draft the migration" \
    "it can absolutely draft a pr with migration scripts"; do
    jq --arg body "$phrasing" '.[1].metadata.body = $body' \
        "$TMP_DIR/pending-directive-history.json" > "$TMP_DIR/natural-directive-history.json"
    python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
        --card "$TMP_DIR/pending-directive-card.json" \
        --history "$TMP_DIR/natural-directive-history.json" \
        --output "$TMP_DIR/resolved-natural-directive.json"
    check "plain owner authorization grants a draft: $phrasing" \
        $(jq -e '.directives == ["draft_pr"]' "$TMP_DIR/resolved-natural-directive.json" \
          >/dev/null && echo 0 || echo 1)
done

jq '.progress_note = "🤖 AUTO SETUP · NO PR: MIGRATION REQUIRED · [autopr:no-spec 2026-09-02T01:00:00Z] migration_required"
    | .autopr_reconsideration_pending = false' \
    "$TMP_DIR/consumed-directive-card.json" > "$TMP_DIR/consumed-migration-card.json"
jq '.[0].metadata.autopr_reconsideration_of = "🤖 AUTO SETUP · NO PR: MIGRATION REQUIRED · [autopr:no-spec 2026-09-02T00:30:00Z] migration_required"
    | .[0].metadata.body = "you can work on this."' \
    "$TMP_DIR/consumed-directive-history.json" > "$TMP_DIR/consumed-migration-history.json"
python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
    --recover-consumed \
    --card "$TMP_DIR/consumed-migration-card.json" \
    --history "$TMP_DIR/consumed-migration-history.json" \
    --output "$TMP_DIR/recovered-migration-directive.json"
check "a migration-required repeat cannot consume the owner's draft authorization" \
    $(jq -e '.directives == ["draft_pr"] and .source_event_id == "consumed-event"' \
      "$TMP_DIR/recovered-migration-directive.json" >/dev/null && echo 0 || echo 1)

# Recovery exists for standing product authority. A one-shot runtime approval
# bound to a cycle that is already over must not ride along with it.
jq '.[0].metadata.autopr_directives = "draft_pr,extend_runtime"
    | .[0].metadata.body = "go ahead and do it\n--extend-runtime"' \
    "$TMP_DIR/consumed-directive-history.json" > "$TMP_DIR/consumed-runtime-history.json"
python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
    --recover-consumed \
    --card "$TMP_DIR/consumed-directive-card.json" \
    --history "$TMP_DIR/consumed-runtime-history.json" \
    --output "$TMP_DIR/recovered-runtime-directive.json"
check "recovery never resurrects a spent runtime approval" \
    $(jq -e '.directives == ["draft_pr"]' \
      "$TMP_DIR/recovered-runtime-directive.json" >/dev/null && echo 0 || echo 1)

cat > "$TMP_DIR/standing-directive-card.json" <<'EOF'
{"board_column":"todo","progress_note":"🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · 🟡 C60 · [autopr:directives draft_pr,extend_runtime]","autopr_reconsideration_pending":false}
EOF
python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
    --card "$TMP_DIR/standing-directive-card.json" \
    --history "$TMP_DIR/pending-directive-history.json" \
    --output "$TMP_DIR/standing-directive.json"
check "draft authority survives while runtime approval remains one-shot" \
    $(jq -e '.directives == ["draft_pr"]' "$TMP_DIR/standing-directive.json" >/dev/null \
      && echo 0 || echo 1)

jq '.board_column = "review"' "$TMP_DIR/standing-directive-card.json" \
    > "$TMP_DIR/standing-directive-review-card.json"
python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
    --card "$TMP_DIR/standing-directive-review-card.json" \
    --history "$TMP_DIR/pending-directive-history.json" \
    --output "$TMP_DIR/standing-directive-review.json"
check "a standing authorization does not follow the card off the AutoPR lanes" \
    $(jq -e '.directives == []' "$TMP_DIR/standing-directive-review.json" >/dev/null \
      && echo 0 || echo 1)

"$AUTOPR_DIR/decision.sh" directive-ok "$TMP_DIR/migration-required-decision.json" \
    "$TMP_DIR/forced-policy.json" >/dev/null 2>&1
directive_ok_rejects_rc=$?
"$AUTOPR_DIR/decision.sh" directive-ok "$TMP_DIR/publication-decision.json" \
    "$TMP_DIR/forced-policy.json" >/dev/null 2>&1
directive_ok_accepts_rc=$?
check "directive-ok isolates a retryable directive violation from a fatal decision" \
    $([ "$directive_ok_rejects_rc" != 0 ] && [ "$directive_ok_accepts_rc" = 0 ] \
      && grep -q 'decision.sh" directive-ok' "$AUTOPR_DIR/investigate.sh" \
      && echo 0 || echo 1)

jq '.[1].metadata.body = "do not go ahead and do it"' \
    "$TMP_DIR/pending-directive-history.json" > "$TMP_DIR/negated-directive-history.json"
python3 "$AUTOPR_DIR/resolve-directive-policy.py" \
    --card "$TMP_DIR/pending-directive-card.json" \
    --history "$TMP_DIR/negated-directive-history.json" \
    --output "$TMP_DIR/resolved-negated-directive.json"
check "negated historical context does not grant draft authority" \
    $(jq -e '.directives == []' "$TMP_DIR/resolved-negated-directive.json" >/dev/null \
      && echo 0 || echo 1)

env -u AUTOPR_TEST_TENANT_EMAIL -u AUTOPR_TEST_TENANT_PASSWORD \
    python3 "$AUTOPR_DIR/collect-test-tenant-evidence.py" \
    --policy "$TMP_DIR/forced-policy.json" \
    --output "$TMP_DIR/test-tenant-unconfigured.json" \
    --screenshot "$TMP_DIR/test-tenant.png"
check "test-tenant replay fails closed without exposing or requiring credentials" \
    $(jq -e '.status == "not_configured" and .route == "/app/jobs" and .screenshot_path == null' \
      "$TMP_DIR/test-tenant-unconfigured.json" >/dev/null && echo 0 || echo 1)

check "collector preserves task attachment metadata" \
    $(grep -qF 'attachments: (($t.attachments // []) | map(del(.storage_url)))' "$AUTOPR_DIR/collect.sh" && echo 0 || echo 1)

################################################################################
# Changes Requested wins over Todo, and a just-attempted card cools down while
# the next five-minute tick advances to another eligible card.
################################################################################
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *"--label autopr"* && "$*" == *"--json labels"* ]]; then
    printf '0\n'
elif [[ "$*" == *"--label autopr"* ]]; then
    printf '[]\n'
elif [[ "$*" == *"--head bot/task-77777777"* ]] && [ -n "${AUTOPR_TEST_PRIOR_TASK_PR:-}" ]; then
    printf '[{"state":"%s","createdAt":"2026-01-01T00:00:00Z","number":77,"labels":[{"name":"autopr"}],"body":""}]\n' \
        "$AUTOPR_TEST_PRIOR_TASK_PR"
elif [[ "$*" == *"--head bot/task-aaaaaaaa"* ]] && [ -n "${AUTOPR_TEST_PAUSED_PR:-}" ]; then
    printf '[{"state":"OPEN","createdAt":"2026-01-01T00:00:00Z","number":91,"labels":[{"name":"autopr"},{"name":"autopr-awaiting-input"}],"body":"<!-- matcha-feedback-comment-id: %s -->"}]\n' \
        "${AUTOPR_TEST_PAUSED_PR_SEEN_COMMENT:-old-comment}"
elif [[ "$*" == *"pr view"* && "$*" == *"--json comments,reviews"* ]]; then
    printf '{"comments":[{"id":"new-comment","body":"here is the answer","author":{"login":"haley"}}],"reviews":[]}\n'
else
    printf '[]\n'
fi
EOF
chmod +x "$TMP_DIR/bin/gh"

cat > "$TMP_DIR/cards.json" <<'EOF'
[
  {"task_id":"11111111-0000-4000-8000-000000000001","id8":"11111111","project_id":"p","title":"Older todo","board_column":"todo","created_at":"2026-01-01T00:00:00Z","last_moved_at":"2026-01-01T00:00:00Z"},
  {"task_id":"22222222-0000-4000-8000-000000000002","id8":"22222222","project_id":"p","title":"Review feedback","board_column":"changes_requested","created_at":"2026-02-01T00:00:00Z","last_moved_at":"2026-02-01T00:00:00Z"}
]
EOF

select_cache="$TMP_DIR/select-cache"
first_selected="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$select_cache" "$AUTOPR_DIR/select.sh" "$TMP_DIR/cards.json")"
check "selector prioritizes Changes Requested over Todo" \
    $([ "$(printf '%s' "$first_selected" | jq -r '.id8')" = "22222222" ] && echo 0 || echo 1)

second_selected="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$select_cache" "$AUTOPR_DIR/select.sh" "$TMP_DIR/cards.json")"
check "cooldown lets the next tick advance to another card" \
    $([ "$(printf '%s' "$second_selected" | jq -r '.id8')" = "11111111" ] && echo 0 || echo 1)

check "implementation PR cap defaults to ten and workflow pins it" \
    $(grep -qF 'MAX_OPEN_IMPLEMENTATION_PRS="${MAX_OPEN_IMPLEMENTATION_PRS:-10}"' "$AUTOPR_DIR/select.sh" \
      && grep -qF 'MAX_OPEN_IMPLEMENTATION_PRS: 10' "$REPO_ROOT/.github/workflows/kanban-autopr.yml" \
      && echo 0 || echo 1)

check "no-spec dedup recognizes the marker inside the visible origin note" \
    $(grep -qF '[[ "$progress_note" == *"[autopr:no-spec "* ]]' "$AUTOPR_DIR/select.sh" && echo 0 || echo 1)

cat > "$TMP_DIR/no-spec-card.json" <<'EOF'
[
  {"task_id":"33333333-0000-4000-8000-000000000003","id8":"33333333","project_id":"p","title":"Unscopable","board_column":"todo","created_at":"2026-01-01T00:00:00Z","last_moved_at":"2026-01-01T00:00:00Z","progress_note":"from auto setup · build 550 · prod c5d3a49 · [autopr:no-spec 2026-01-02T00:00:00Z] missing evidence"}
]
EOF
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$TMP_DIR/no-spec-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/no-spec-card.json" >/dev/null 2>&1
no_spec_rc=$?
check "visible origin note still durably suppresses an unchanged no-spec card" \
    $([ "$no_spec_rc" = "3" ] && echo 0 || echo 1)

cat > "$TMP_DIR/runtime-paused-card.json" <<'EOF'
[
  {"task_id":"aaaaaaaa-0000-4000-8000-000000000001","id8":"aaaaaaaa","project_id":"p","title":"Long investigation","board_column":"changes_requested","created_at":"2026-01-01T00:00:00Z","last_moved_at":"2026-01-01T00:00:00Z","progress_note":"🤖 AUTO SETUP · PAUSED: RUNTIME APPROVAL REQUIRED · checkpoint 123"}
]
EOF
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$TMP_DIR/runtime-paused-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/runtime-paused-card.json" >/dev/null 2>&1
runtime_paused_rc=$?
check "a runtime-limited card waits instead of retrying forever" \
    $([ "$runtime_paused_rc" = "3" ] && echo 0 || echo 1)

jq '.[0].autopr_reconsideration_pending = true
    | .[0].autopr_reconsideration_event_id = "runtime-event"
    | .[0].autopr_reconsideration_at = "2026-01-02T00:00:00Z"' \
    "$TMP_DIR/runtime-paused-card.json" > "$TMP_DIR/runtime-approved-card.json"
runtime_approved="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$TMP_DIR/runtime-approved-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/runtime-approved-card.json")"
check "new decision-bound context reopens a runtime-limited card" \
    $([ "$(printf '%s' "$runtime_approved" | jq -r '.id8')" = "aaaaaaaa" ] \
      && echo 0 || echo 1)

# Answering on the draft PR is a documented alternate path, so the pause must
# not hide a card whose open awaiting-input draft just received a reply.
runtime_pr_answer="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_PAUSED_PR=1 \
    AUTOPR_CACHE_DIR="$TMP_DIR/runtime-pr-answer-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/runtime-paused-card.json")"
check "a PR reply reopens a runtime-limited card that already has a draft" \
    $([ "$(printf '%s' "$runtime_pr_answer" | jq -r '.mode')" = "rework" ] \
      && echo 0 || echo 1)

PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_PAUSED_PR=1 AUTOPR_TEST_PAUSED_PR_SEEN_COMMENT=new-comment \
    AUTOPR_CACHE_DIR="$TMP_DIR/runtime-pr-stale-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/runtime-paused-card.json" >/dev/null 2>&1
runtime_pr_stale_rc=$?
check "an open draft with no new reply leaves a paused card waiting" \
    $([ "$runtime_pr_stale_rc" = "3" ] && echo 0 || echo 1)

cat > "$TMP_DIR/reconsideration-cards.json" <<'EOF'
[
  {"task_id":"77777777-0000-4000-8000-000000000007","id8":"77777777","project_id":"p","title":"Reconsider me","board_column":"todo","created_at":"2026-01-01T00:00:00Z","last_moved_at":"2026-01-01T00:00:00Z","progress_note":"🤖 AUTO SETUP · NO PR: ALREADY FIXED · [autopr:no-spec 2026-01-02T00:00:00Z] already_fixed","autopr_reconsideration_pending":true,"autopr_reconsideration_event_id":"eeeeeeee-0000-4000-8000-000000000001","autopr_reconsideration_at":"2026-01-03T00:00:00+00:00"},
  {"task_id":"88888888-0000-4000-8000-000000000008","id8":"88888888","project_id":"p","title":"Fresh work","board_column":"todo","created_at":"2026-02-01T00:00:00Z","last_moved_at":"2026-02-01T00:00:00Z"}
]
EOF
reconsideration_cache="$TMP_DIR/reconsideration-cache"
reconsidered="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$reconsideration_cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/reconsideration-cards.json")"
check "pending additional context reopens an unchanged no-spec decision" \
    $([ "$(printf '%s' "$reconsidered" | jq -r '.id8')" = "77777777" ] \
      && [ "$(printf '%s' "$reconsidered" | jq -r '.mode')" = "investigate" ] \
      && echo 0 || echo 1)

cat > "$TMP_DIR/run-request-cards.json" <<'EOF'
[
  {"task_id":"88888888-0000-4000-8000-000000000008","id8":"88888888","project_id":"p","title":"Ordinary changes-requested work","board_column":"changes_requested","created_at":"2026-02-01T00:00:00Z","last_moved_at":"2026-02-01T00:00:00Z"},
  {"task_id":"99999999-0000-4000-8000-000000000009","id8":"99999999","project_id":"p","title":"Run me now","board_column":"todo","created_at":"2026-01-01T00:00:00Z","last_moved_at":"2026-01-01T00:00:00Z","progress_note":"🤖 AUTO SETUP · NO PR: MIGRATION REQUIRED · [autopr:no-spec 2026-01-02T00:00:00Z] migration_required","autopr_run_requested_at":"2026-01-03T00:00:00+00:00"}
]
EOF
run_requested="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$TMP_DIR/run-request-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/run-request-cards.json")"
check "an explicit run request outranks routine work and its own no-spec marker" \
    $([ "$(printf '%s' "$run_requested" | jq -r '.id8')" = "99999999" ] \
      && [ "$(printf '%s' "$run_requested" | jq -r '.mode')" = "investigate" ] \
      && echo 0 || echo 1)

# The same cache now holds a fresh attempt marker for that card: a request
# newer than the attempt must still beat the cooldown, exactly like
# decision-bound context does.
run_requested_again="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$TMP_DIR/run-request-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/run-request-cards.json" 2>/dev/null)"
check "a stale run request does not beat its own cooldown" \
    $([ "$(printf '%s' "$run_requested_again" | jq -r '.id8 // empty')" != "99999999" ] \
      && echo 0 || echo 1)

# A pass that declines a run-requested card must consume the request. Without
# this the one-minute watcher keeps forcing a Kanban dispatch for a card the
# selector can never pick, which runs the lane MORE often than the twenty-minute
# schedule the request was meant to jump.
rm -f "$TMP_DIR/claim-urls"
AUTOPR_TEST_CURL_URLS="$TMP_DIR/claim-urls" MATCHA_AUTOPR_ENV="$env_file" \
    PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$TMP_DIR/run-request-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/run-request-cards.json" >/dev/null 2>&1
check "a declined run request is consumed instead of re-forcing every tick" \
    $(grep -q '/tasks/99999999-0000-4000-8000-000000000009/autopr/run-claim' \
        "$TMP_DIR/claim-urls" && echo 0 || echo 1)

# The dashboard asks the same selector what would run next. That probe must
# never consume a human's queued request.
rm -f "$TMP_DIR/claim-urls"
AUTOPR_SELECT_READ_ONLY=true AUTOPR_TEST_CURL_URLS="$TMP_DIR/claim-urls" \
    MATCHA_AUTOPR_ENV="$env_file" \
    PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$TMP_DIR/run-request-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/run-request-cards.json" >/dev/null 2>&1
check "the read-only dashboard probe never consumes a run request" \
    $([ ! -s "$TMP_DIR/claim-urls" ] && echo 0 || echo 1)

prior_pr_retry_ok=0
for prior_state in CLOSED MERGED; do
    prior_selected="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
        AUTOPR_TEST_PRIOR_TASK_PR="$prior_state" \
        AUTOPR_CACHE_DIR="$TMP_DIR/prior-$prior_state-cache" \
        "$AUTOPR_DIR/select.sh" "$TMP_DIR/reconsideration-cards.json")"
    if [ "$(printf '%s' "$prior_selected" | jq -r '.id8')" != "77777777" ] \
        || [ "$(printf '%s' "$prior_selected" | jq -r '.mode')" != "investigate" ]; then
        prior_pr_retry_ok=1
    fi
done
check "pending Todo context overrides a closed or merged historical bot PR" \
    "$prior_pr_retry_ok"

after_reconsideration="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$reconsideration_cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/reconsideration-cards.json")"
check "a failed reconsideration cools down instead of spinning every tick" \
    $([ "$(printf '%s' "$after_reconsideration" | jq -r '.id8')" = "88888888" ] && echo 0 || echo 1)

cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
if [ "$1 $2" = "pr list" ]; then
    if [[ "$*" == *"--label autopr"* ]]; then
        printf '0\n'
    elif [[ "$*" == *"--head bot/task-55555555"* ]]; then
        printf '%s\n' '[{"state":"MERGED","createdAt":"2026-08-27T00:00:00Z","number":55,"labels":[{"name":"autopr"}],"body":""}]'
    else
        printf '[]\n'
    fi
fi
EOF
chmod +x "$TMP_DIR/bin/gh"
cat > "$TMP_DIR/merged-card.json" <<'EOF'
[
  {"task_id":"55555555-0000-4000-8000-000000000005","id8":"55555555","project_id":"p","title":"Already merged","board_column":"changes_requested","created_at":"2026-01-01T00:00:00Z","last_moved_at":"2026-01-01T00:00:00Z","progress_note":"🤖 AUTO SETUP · READY FOR REVIEW · PR #55"},
  {"task_id":"66666666-0000-4000-8000-000000000006","id8":"66666666","project_id":"p","title":"Fresh todo","board_column":"todo","created_at":"2026-02-01T00:00:00Z","last_moved_at":"2026-02-01T00:00:00Z"}
]
EOF
merged_fallback_selected="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$TMP_DIR/merged-cache" "$AUTOPR_DIR/select.sh" "$TMP_DIR/merged-card.json")"
check "merged AutoPR in Changes Requested cannot block or duplicate ahead of Todo" \
    $([ "$(printf '%s' "$merged_fallback_selected" | jq -r '.id8')" = "66666666" ] && echo 0 || echo 1)

################################################################################
# A questions draft remains in Changes Requested but cannot spin every five
# minutes. Only a new human PR comment makes it eligible for rework.
################################################################################
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
if [ "$1 $2" = "pr list" ]; then
    if [[ "$*" == *"--label autopr"* ]]; then
        printf '0\n'
    elif [[ "$*" == *"--head bot/task-44444444"* ]]; then
        printf '%s\n' '[{"state":"OPEN","createdAt":"2026-08-27T00:00:00Z","number":44,"labels":[{"name":"autopr-awaiting-input"}],"body":"<!-- matcha-feedback-comment-id: comment-1 -->\n<!-- matcha-feedback-review-id: none -->"}]'
    else
        printf '[]\n'
    fi
elif [ "$1 $2" = "pr view" ]; then
    comment_id="comment-1"
    [ "${AUTOPR_TEST_NEW_FEEDBACK:-0}" = 0 ] || comment_id="comment-2"
    printf '{"comments":[{"id":"%s","body":"please use journal","author":{"login":"haley"}}],"reviews":[]}' "$comment_id"
fi
EOF
chmod +x "$TMP_DIR/bin/gh"

cat > "$TMP_DIR/questions-card.json" <<'EOF'
[{"task_id":"44444444-0000-4000-8000-000000000004","id8":"44444444","project_id":"p","title":"Needs answer","board_column":"changes_requested","created_at":"2026-01-01T00:00:00Z","last_moved_at":"2026-01-01T00:00:00Z"}]
EOF
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" AUTOPR_CACHE_DIR="$TMP_DIR/questions-cache" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/questions-card.json" >/dev/null 2>&1
waiting_rc=$?
check "unanswered question draft is skipped" \
    $([ "$waiting_rc" = "3" ] && echo 0 || echo 1)

answered_selected="$(PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" AUTOPR_CACHE_DIR="$TMP_DIR/questions-cache" AUTOPR_TEST_NEW_FEEDBACK=1 \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/questions-card.json")"
check "new human feedback reselects the same draft for rework" \
    $([ "$(printf '%s' "$answered_selected" | jq -r '.mode')" = "rework" ] && echo 0 || echo 1)

readonly_cache="$TMP_DIR/readonly-select-cache"
AUTOPR_SELECT_READ_ONLY=true PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_CACHE_DIR="$readonly_cache" AUTOPR_TEST_NEW_FEEDBACK=1 \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/questions-card.json" >/dev/null
check "dashboard selection probe creates no cooldown state" \
    $([ ! -e "$readonly_cache" ] && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
