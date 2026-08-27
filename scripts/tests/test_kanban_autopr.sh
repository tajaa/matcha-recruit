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

check "published PR and card carry production build provenance" \
    $(grep -qF '<!-- matcha-production-build: $PROD_BUILD_NUMBER -->' "$AUTOPR_DIR/publish.sh" \
      && grep -qF 'from auto setup · build $PROD_BUILD_NUMBER' "$AUTOPR_DIR/publish.sh" \
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
        printf '[{"id":"file-1","filename":"screen.png","storage_url":"https://files.invalid/screen.png","content_type":"image/png","file_size":8,"round_index":6,"created_at":"2026-08-27T00:00:00Z"}]' > "$output_file"
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

cat > "$TMP_DIR/bin/opencode" <<'EOF'
#!/usr/bin/env bash
while [ "$#" -gt 0 ]; do
    if [ "$1" = "-f" ]; then
        printf '%s\n' "$2" >> "$OPENCODE_STUB_FILES"
        [ "$(basename "$2")" != "context.json" ] || cp "$2" "$OPENCODE_STUB_CONTEXT"
        shift 2
    else
        shift
    fi
done
cat > "$OPENCODE_STUB_REPORT" <<'REPORT'
### Summary
stub
### Changes
stub
### Blast radius
stub
### Confidence
high
REPORT
cat > "$OPENCODE_STUB_DECISION" <<'DECISION'
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
chmod +x "$TMP_DIR/bin/opencode"

cat > "$TMP_DIR/card.json" <<'EOF'
{"task_id":"f296d090-0000-4000-8000-000000000001","id8":"f296d090","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Standardize terminology","mode":"rework","review_note":"No change, including screenshot"}
EOF

PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$env_file" RUNNER_TEMP="$TMP_DIR/runner" \
GITHUB_REPOSITORY="tajaa/matcha-recruit" OPENCODE_STUB_FILES="$TMP_DIR/opencode_files" \
OPENCODE_STUB_CONTEXT="$TMP_DIR/context.json" OPENCODE_STUB_REPORT="$TMP_DIR/report.md" \
OPENCODE_STUB_DECISION="$TMP_DIR/decision.json" \
    "$AUTOPR_DIR/investigate.sh" "$TMP_DIR/card.json" "$TMP_DIR/report.md" "$TMP_DIR/decision.json" > /dev/null 2>&1
investigate_rc=$?

context_ok=1
if [ "$investigate_rc" = "0" ] \
    && jq -e '.subtasks[0].round_index == 6 and .history[0].metadata.body == "The screenshot still says note" and .downloaded_attachments[0].id == "file-1" and (.files[0] | has("storage_url") | not)' "$TMP_DIR/context.json" > /dev/null \
    && grep -q '/attachments/01-screen.png' "$TMP_DIR/opencode_files" \
    && grep -q '/feedback.json' "$TMP_DIR/opencode_files"; then
    context_ok=0
fi
check "rework investigation receives discussion, checklist, PR feedback, and screenshot" "$context_ok"

check "investigation context reserves bounded production diagnostics" \
    $(jq -e '.production == null and .production_recent_errors == [] and .production_log_signals == "" and .changes_since_production == []' "$TMP_DIR/context.json" >/dev/null && echo 0 || echo 1)

check "investigation normalizes validated confidence and triage" \
    $(jq -e '.confidence_score == 100 and .confidence_band == "high" and .awaiting_human == false and .feedback_checkpoint.review_id == "review-44"' "$TMP_DIR/decision.json" >/dev/null && echo 0 || echo 1)

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

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
