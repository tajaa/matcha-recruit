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
    $(grep -qF 'AUTOPR_MSANDBOX_BIN: ./scripts/agent-sandbox.sh' "$workflow" \
      && grep -qF 'AUTOPR_SANDBOX_PROJECT_NAME: matcha-kanban-autopr-sandbox' "$workflow" \
      && grep -qF 'run-codex-sandboxed.sh' "$AUTOPR_DIR/investigate.sh" \
      && grep -qF 'AUTOPR_CODEX_MODEL=gpt-5.6-sol' "$AUTOPR_DIR/investigate.sh" \
      && grep -qF 'AUTOPR_CODEX_REASONING_EFFORT=medium' "$AUTOPR_DIR/investigate.sh" \
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
    {"id":"44444444-0000-4000-8000-000000000004","title":"Assigned scoped work","assigned_email":"owner@example.com","board_column":"in_progress","status":"pending","progress_note":"🤖 AUTO SETUP · ALREADY SCOPED · PR #444"}
  ]
}
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
cp "$AUTOPR_TEST_BUNDLE_FILE" "$output_file"
[ "$write_status" = "0" ] || printf 200
EOF
chmod +x "$TMP_DIR/collect-bin/curl"
collected="$(PATH="$TMP_DIR/collect-bin:$PATH" \
    RUNNER_TEMP="$TMP_DIR/collect-runner" \
    MATCHA_AUTOPR_ENV="$env_file" \
    AUTOPR_TEST_BUNDLE_FILE="$TMP_DIR/collect-bundle.json" \
    "$AUTOPR_DIR/collect.sh" 2>"$TMP_DIR/collect-error.log")"
collect_rc=$?
check "collector honors reassigned reconsideration only in an eligible lane" \
    $([ "$collect_rc" = "0" ] \
      && [ "$(printf '%s' "$collected" | jq 'length')" = "2" ] \
      && printf '%s' "$collected" | jq -e \
        'map(.id8) == ["11111111", "44444444"]' >/dev/null \
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
      && [ "$(cat "$SANDBOX_TEST_REPO/server/app/matcha/services/huume/CLAUDE.md")" = "operator instructions" ] \
      && grep -q 'Ignored model edit to operator instruction file' "$TMP_DIR/sandbox-bridge.log" \
      && [ -s "$TMP_DIR/sandbox-report.md" ] \
      && [ ! -e "$SANDBOX_TEST_REPO/.autopr-io" ] \
      && echo 0 || echo 1)

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
  "$AUTOPR_DIR/write-publication-copy.sh" "$TMP_DIR/card.json" "$TMP_DIR/decision.json" \
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
  "$AUTOPR_DIR/write-publication-copy.sh" "$TMP_DIR/feat-card.json" "$TMP_DIR/decision.json" \
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
  -f "$TMP_DIR/card.json" -f "$TMP_DIR/decision.json" -f "$TMP_DIR/report.md" \
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
  "$AUTOPR_DIR/write-publication-copy.sh" "$TMP_DIR/card.json" "$TMP_DIR/decision.json" \
  "$TMP_DIR/report.md" "$TMP_DIR/publication-verification.md" "$TMP_DIR/publication-copy-edit.json" \
  >/dev/null 2>&1
publication_edit_rc=$?
check "publication writer rejects Luna repository edits before applying them" \
    $([ "$publication_edit_rc" != 0 ] \
      && [ ! -e "$REPO_ROOT/client/src/luna-edit.ts" ] \
      && echo 0 || echo 1)

cp "$TMP_DIR/decision.json" "$TMP_DIR/invalid-decision.json"
jq '.outcome = "questions_only" | .questions = [] | .safe_changes_present = false' \
    "$TMP_DIR/invalid-decision.json" > "$TMP_DIR/invalid-decision.next.json"
mv "$TMP_DIR/invalid-decision.next.json" "$TMP_DIR/invalid-decision.json"
"$AUTOPR_DIR/decision.sh" normalize "$TMP_DIR/invalid-decision.json" "$TMP_DIR/invalid-decision.normalized.json" >/dev/null 2>&1
invalid_decision_rc=$?
check "questions-only decisions require actionable questions" \
    $([ "$invalid_decision_rc" != 0 ] && echo 0 || echo 1)

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
