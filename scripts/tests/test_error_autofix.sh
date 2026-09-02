#!/usr/bin/env bash
# Exercises scripts/error-autofix/* without touching prod, GitHub, or a real
# model. Stubs `ssh` and `gh` on PATH in the house style of
# test_collect_silent_error_evidence.sh / test_ci_guards.sh. Run:
#   ./scripts/tests/test_error_autofix.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOFIX_DIR="$REPO_ROOT/scripts/error-autofix"
TMP_DIR="$(mktemp -d)"
MODEL_OUTPUT_DIR="$(mktemp -d /tmp/matcha-error-autofix-output-XXXXXX)"
trap 'rm -rf "$TMP_DIR" "$MODEL_OUTPUT_DIR"' EXIT

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

################################################################################
# 1-3: stable_key — date-free, matches app logic shape, distinct bugs distinct
################################################################################
STABLE_KEY_PY="
import sys
sys.path.insert(0, '$AUTOFIX_DIR')
from _query import stable_key
print(stable_key(sys.argv[1], sys.argv[2] or None, sys.argv[3], sys.argv[4]))
"
key_a1="$(python3 -c "$STABLE_KEY_PY" http_error DataError "invalid input for query argument \$4: 'bad'" "File \"/app/app/matcha/routes/employees/credentials.py\", line 456, in approve")"
key_a2="$(python3 -c "$STABLE_KEY_PY" http_error DataError "invalid input for query argument \$4: '13/45/2026'" "File \"/app/app/matcha/routes/employees/credentials.py\", line 456, in approve")"
check "stable_key ignores interpolated values (same bug, different bound value)" $([ "$key_a1" = "$key_a2" ] && echo 0 || echo 1)

key_b="$(python3 -c "$STABLE_KEY_PY" http_error DataError "invalid input for query argument \$3" "File \"/app/app/matcha/routes/employee_portal/schedule.py\", line 149, in create_my_schedule_request")"
check "stable_key: distinct bugs get distinct keys" $([ "$key_a1" != "$key_b" ] && echo 0 || echo 1)

check "stable_key is a 12-char hex string" $([[ "$key_a1" =~ ^[0-9a-f]{12}$ ]] && echo 0 || echo 1)

################################################################################
# 4-5: redaction — covers DB free text, spares structural fields
################################################################################
source "$AUTOFIX_DIR/lib.sh"
redacted="$(printf 'user@example.com 203.0.113.10 Bearer sekret 123e4567-e89b-12d3-a456-426614174000' | redact_stream)"
ok=0
for secret in 'user@example.com' '203.0.113.10' 'sekret' '123e4567-e89b-12d3-a456-426614174000'; do
    grep -qF "$secret" <<< "$redacted" && ok=1
done
check "redact_stream removes email/ip/bearer/uuid" "$ok"

structural="9df05930da86"
redacted_key="$(printf '%s' "$structural" | redact_stream)"
check "redact_stream spares a bare stable_key (no digit run \\u2265 7)" $([ "$redacted_key" = "$structural" ] && echo 0 || echo 1)

################################################################################
# collect.sh — SSH failure is fatal (not silently "no errors"), no-container
# shape matches _query.py's real shape, --hours/--limit are guarded
################################################################################
mkdir -p "$TMP_DIR/bin"
cat > "$TMP_DIR/bin/ssh" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null   # drain the heredoc collect.sh sends us; we don't execute it
case "${SSH_STUB_MODE:-ok}" in
    fail)
        exit 255
        ;;
    no_container)
        echo '{"incidents":[],"skipped_infra":0}'
        ;;
    *)
        echo '{"incidents":[{"stable_key":"deadbeef0001","error_id":"1","kind":"http_error","level":"ERROR","exception_type":"DataError","message":"boom for user@example.com","traceback":"File \"/app/x.py\", line 1","source":"api","request_method":"POST","request_path":"/api/x?token=secret","request_status":500,"occurrences":3,"days_seen":1,"first_seen":"2026-08-19T00:00:00Z","last_seen":"2026-08-22T00:00:00Z","request_id":"abc123","company_id":null}],"skipped_infra":1}'
        ;;
esac
EOF
chmod +x "$TMP_DIR/bin/ssh"

PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" SSH_STUB_MODE=fail \
    "$AUTOFIX_DIR/collect.sh" > /dev/null 2>"$TMP_DIR/collect_err.txt"
check "collect.sh exits nonzero on ssh failure (not silently '[]')" $([ "$?" != "0" ] && echo 0 || echo 1)

PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" SSH_STUB_MODE=no_container \
    "$AUTOFIX_DIR/collect.sh" > "$TMP_DIR/collect_out.json" 2>&1
rc=$?
check "collect.sh handles 'no container' cleanly (valid empty array, exit 0)" \
    $([ "$rc" = "0" ] && [ "$(jq -e 'type=="array" and length==0' "$TMP_DIR/collect_out.json" 2>/dev/null)" = "true" ] && echo 0 || echo 1)

PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" SSH_STUB_MODE=ok \
    "$AUTOFIX_DIR/collect.sh" > "$TMP_DIR/collect_out2.json" 2>"$TMP_DIR/collect_err2.txt"
rc=$?
redacted_message="$(jq -r '.[0].message' "$TMP_DIR/collect_out2.json" 2>/dev/null)"
ok=0
[ "$rc" = "0" ] || ok=1
grep -qF 'user@example.com' <<< "$redacted_message" && ok=1
[ "$(jq -r '.[0].stable_key' "$TMP_DIR/collect_out2.json" 2>/dev/null)" = "deadbeef0001" ] || ok=1
check "collect.sh redacts message but preserves stable_key end to end" "$ok"

PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" "$AUTOFIX_DIR/collect.sh" --hours > /dev/null 2>&1
check "collect.sh rejects --hours with no value instead of crashing on \$2" $([ "$?" != "0" ] && echo 0 || echo 1)

################################################################################
# investigate.sh — Codex receives isolated inputs plus one prompt
################################################################################
cat > "$TMP_DIR/bin/codex" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$CODEX_STUB_ARGS"
prompt="${!#}"
[[ "$prompt" == *'Investigate the attached production incident'* ]] || exit 8
[ "$(printf '%s\n' "$prompt" | sed -n \
    '/^AUTOPR_INPUTS_BEGIN$/,/^AUTOPR_INPUTS_END$/ { s/^- //p; }' \
    | wc -l | tr -d '[:space:]')" = 1 ] || exit 9
report_path="$(printf '%s\n' "$prompt" | grep -oE '/[^ ]+/\.git/autopr-io/output/report\.md' | head -1)"
decision_path="$(printf '%s\n' "$prompt" | grep -oE '/[^ ]+/\.git/autopr-io/output/decision\.json' | head -1)"
mkdir -p "$(dirname "$report_path")" "$(dirname "$decision_path")"
cat > "$report_path" <<'REPORT'
### Root cause
stub
### Fix
stub
### Blast radius
stub
### Confidence
high
REPORT
cat > "$decision_path" <<'DECISION'
{
  "schema_version": 1,
  "outcome": "no_safe_fix",
  "confidence": {
    "evidence_quality": {"score": 20, "reason": "stub"},
    "root_cause_clarity": {"score": 20, "reason": "stub"},
    "code_localization": {"score": 15, "reason": "stub"},
    "verification_readiness": {"score": 10, "reason": "stub"},
    "production_impact": {"score": 10, "reason": "stub"}
  },
  "criticality": {"level": "yellow", "reasons": ["stub"]},
  "safe_changes_present": false,
  "no_safe_fix_reason": "stub"
}
DECISION
EOF
chmod +x "$TMP_DIR/bin/codex"
cat > "$TMP_DIR/investigate-incident.json" <<'EOF'
{"message":"boom","traceback":"File \"/app/app/example.py\", line 1","stable_key":"abc123abc123"}
EOF
PATH="$TMP_DIR/bin:$PATH" CODEX_STUB_ARGS="$TMP_DIR/codex-args" \
    AUTOPR_SANDBOX_TEST_DIRECT=1 GITHUB_ACTIONS=false \
    "$AUTOFIX_DIR/investigate.sh" "$TMP_DIR/investigate-incident.json" \
    "$MODEL_OUTPUT_DIR/investigation.md" "$MODEL_OUTPUT_DIR/investigation.json" >/dev/null 2>&1
investigate_rc=$?
check "investigate.sh passes isolated evidence to Codex" "$investigate_rc"
check "investigate.sh normalizes validated confidence and triage" \
    $(jq -e '.confidence_score == 75 and .confidence_band == "high" and .criticality.level == "yellow"' \
      "$MODEL_OUTPUT_DIR/investigation.json" >/dev/null 2>&1 && echo 0 || echo 1)
check "investigate.sh uses Sol with medium reasoning for code fixes" \
    $(grep -qx 'gpt-5.6-sol' "$TMP_DIR/codex-args" \
      && grep -qx 'model_reasoning_effort="medium"' "$TMP_DIR/codex-args" \
      && echo 0 || echo 1)

################################################################################
# Fallback workflow evidence must remain actionable, rather than being replaced
# with an empty incident list before select.sh runs.
################################################################################
workflow="$REPO_ROOT/.github/workflows/silent-error-autofix.yml"
check "Mac dispatcher is the error workflow's only automatic clock" \
    $(! grep -qF 'schedule:' "$workflow" && grep -qF 'workflow_dispatch:' "$workflow" \
      && grep -qF 'silent-error-autofix.yml' "$REPO_ROOT/scripts/kanban-autopr/dispatch-if-idle.sh" \
      && echo 0 || echo 1)
fallback_block="$(sed -n '/Fallback log-grep evidence/,/Select one incident/p' "$workflow")"
check "fallback turns nonempty evidence into an incident" \
    $([[ "$fallback_block" == *'if [ ! -s "$RUNNER_TEMP/silent-error-evidence.txt" ]'* && "$fallback_block" == *'--rawfile evidence'* && "$fallback_block" == *'stable_key: $key'* ]] && echo 0 || echo 1)

failure_block="$(sed -n '/Fail incomplete investigation/,/Verify (baseline vs branch)/p' "$workflow")"
check "incomplete investigation fails without publishing a no-fix issue" \
    $([[ "$failure_block" == *'exit 1'* && "$failure_block" != *'publish.sh'* ]] && echo 0 || echo 1)

check "reconcile.sh uses sandboxed Sol with medium reasoning" \
    $(grep -qF 'AUTOFIX_RECONCILE_MODEL:-gpt-5.6-sol' "$AUTOFIX_DIR/reconcile.sh" \
      && grep -qF 'AUTOPR_CODEX_REASONING_EFFORT=medium' "$AUTOFIX_DIR/reconcile.sh" \
      && grep -qF 'run-codex-sandboxed.sh' "$AUTOFIX_DIR/reconcile.sh" \
      && echo 0 || echo 1)

check "workflow delegates error-fix commit subjects to Luna medium" \
    $(grep -qF 'write-commit-subject.sh fix' "$workflow" \
      && grep -qF 'AUTOPR_CODEX_MODEL=gpt-5.6-luna' "$REPO_ROOT/scripts/kanban-autopr/write-commit-subject.sh" \
      && ! grep -qF 'git commit -m "fix: $EXC in $PATH_"' "$AUTOFIX_DIR/publish.sh" \
      && echo 0 || echo 1)

check "publish.sh permits guarded TypeScript/TSX client fixes" \
    $(grep -qF 'client/src/.*\.(ts|tsx)' "$AUTOFIX_DIR/publish.sh" && echo 0 || echo 1)

check "publish.sh forbids changing browser error reporting" \
    $(grep -qF '^client/src/api/errorReporter\.ts$' "$AUTOFIX_DIR/publish.sh" && echo 0 || echo 1)

check "workflow reconciles drafts before collecting production incidents" \
    $([ "$(grep -n 'Reconcile superseded autofix drafts' "$workflow" | cut -d: -f1)" -lt "$(grep -n 'Collect actionable server and client errors' "$workflow" | cut -d: -f1)" ] && echo 0 || echo 1)

################################################################################
# Fix-ready email — uses prod mail transport through trusted SSH and writes an
# idempotency marker only after the send succeeds.
################################################################################
cat > "$TMP_DIR/bin/ssh" <<'EOF'
#!/usr/bin/env bash
cat >/dev/null
exit 0
EOF
chmod +x "$TMP_DIR/bin/ssh"
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
[ "$1" != api ] || { echo '[]'; exit 0; }
case "$1 $2" in
    "pr list")
        if [[ "$*" == *"--label autofix"* ]]; then
            echo '[{"number":42,"state":"OPEN","title":"🟡 [C70] fix: AttributeError","url":"https://github.test/pr/42","body":"<!-- matcha-autofix-notify-review: abc123abc123 -->\n<!-- matcha-autopr-criticality: yellow -->\n<!-- matcha-autopr-confidence-score: 70 -->"}]'
        else
            echo '[]'
        fi
        ;;
    "pr view")
        echo '{"number":42,"state":"OPEN","title":"🟡 [C70] fix: AttributeError","url":"https://github.test/pr/42","body":"<!-- matcha-autofix-notify-review: abc123abc123 -->\n<!-- matcha-autopr-criticality: yellow -->\n<!-- matcha-autopr-confidence-score: 70 -->"}'
        ;;
    "pr comment")
        while [ "$#" -gt 0 ]; do
            if [ "$1" = --body-file ]; then cat "$2" >> "$NOTIFY_STUB_LOG"; break; fi
            shift
        done
        ;;
    *) exit 1 ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"
cat > "$TMP_DIR/notify-incident.json" <<'EOF'
{"stable_key":"abc123abc123","exception_type":"AttributeError","message":"Gemini role classification failed","request_path":"/employees"}
EOF
cat > "$TMP_DIR/notify-decision.json" <<'EOF'
{"criticality":{"level":"yellow"},"confidence_score":70}
EOF
PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" GH_TOKEN=x \
  GITHUB_REPOSITORY=x/x NOTIFY_STUB_LOG="$TMP_DIR/notify.log" \
  "$AUTOFIX_DIR/notify-review-ready.sh" --pr 42 \
    --incident "$TMP_DIR/notify-incident.json" --decision "$TMP_DIR/notify-decision.json" \
  >/dev/null 2>&1
check "fix-ready email records its durable sent marker" \
  $([ "$?" = 0 ] && grep -qF '<!-- matcha-autofix-review-email: abc123abc123 -->' "$TMP_DIR/notify.log" && echo 0 || echo 1)
rm -f "$TMP_DIR/notify.log"
PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" GH_TOKEN=x \
  GITHUB_REPOSITORY=x/x NOTIFY_STUB_LOG="$TMP_DIR/notify.log" \
  "$AUTOFIX_DIR/notify-review-ready.sh" --reconcile >/dev/null 2>&1
check "fix-ready email reconciliation retries an opted-in open PR" \
  $([ "$?" = 0 ] && grep -qF '<!-- matcha-autofix-review-email: abc123abc123 -->' "$TMP_DIR/notify.log" && echo 0 || echo 1)

################################################################################
# 6-9: select.sh dedup decisions, via a stubbed `gh` on PATH
################################################################################
GH_STUB_RESPONSE_FILE="$TMP_DIR/gh_response.json"
echo '[{"state":"OPEN","mergedAt":null,"closedAt":null}]' > "$GH_STUB_RESPONSE_FILE"
cat > "$TMP_DIR/bin/gh" <<EOF
#!/usr/bin/env bash
case "\$1 \$2" in
    "issue list")
        # No open no-fix issue tracking this incident, unless a test overrides it.
        echo "\${GH_STUB_ISSUE_HITS:-0}"
        ;;
    "pr list")
        if [[ "\$*" == *"--label autofix"* ]]; then
            echo 0
        else
            cat "$GH_STUB_RESPONSE_FILE"
        fi
        ;;
    *)
        cat "$GH_STUB_RESPONSE_FILE"
        ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"

run_select() {
    local incidents_file="$1"
    PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOFIX_CACHE_DIR="$TMP_DIR/cache-$RANDOM" \
        "$AUTOFIX_DIR/select.sh" "$incidents_file"
}

make_incident() {
    jq -n --arg key "$1" --arg first "$2" --arg last "$3" \
        '[{stable_key: $key, first_seen: $first, last_seen: $last, occurrences: 5, kind: "http_error", exception_type: "DataError", request_path: "/api/x"}]'
}

incident_file="$TMP_DIR/incidents.json"
make_incident "aaa111111111" "2026-08-19T00:00:00Z" "2026-08-22T00:00:00Z" > "$incident_file"

echo '[{"state":"OPEN","mergedAt":null,"closedAt":null}]' > "$GH_STUB_RESPONSE_FILE"
run_select "$incident_file" > /dev/null 2>&1
check "select.sh skips (exit 3) when a PR is OPEN" $([ "$?" = "3" ] && echo 0 || echo 1)

recent_closed="$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"
printf '[{"state":"CLOSED","mergedAt":null,"closedAt":"%s"}]\n' "$recent_closed" \
    > "$GH_STUB_RESPONSE_FILE"
run_select "$incident_file" > /dev/null 2>&1
check "select.sh skips a just-closed-unmerged PR (within cooldown)" $([ "$?" = "3" ] && echo 0 || echo 1)

echo '[{"state":"CLOSED","mergedAt":null,"closedAt":"2026-01-01T00:00:00Z"}]' > "$GH_STUB_RESPONSE_FILE"
run_select "$incident_file" > /dev/null
check "select.sh re-investigates a closed-unmerged PR after the cooldown" $?

make_incident "bbb222222222" "2026-08-19T00:00:00Z" "2026-08-19T01:00:00Z" > "$incident_file"
echo '[{"state":"MERGED","mergedAt":"2026-08-20T00:00:00Z","closedAt":"2026-08-20T00:00:00Z"}]' > "$GH_STUB_RESPONSE_FILE"
run_select "$incident_file" > /dev/null 2>&1
check "select.sh skips MERGED when last_seen predates the merge" $([ "$?" = "3" ] && echo 0 || echo 1)

make_incident "ccc333333333" "2026-08-19T00:00:00Z" "2026-08-22T00:00:00Z" > "$incident_file"
echo '[{"state":"MERGED","mergedAt":"2026-08-20T00:00:00Z","closedAt":"2026-08-20T00:00:00Z"}]' > "$GH_STUB_RESPONSE_FILE"
out="$(run_select "$incident_file")"
check "select.sh re-opens for a genuine recurrence after merge+grace" $([ -n "$out" ] && echo 0 || echo 1)

make_incident "ddd444444444" "2026-08-19T00:00:00Z" "2026-08-20T01:00:00Z" > "$incident_file"
echo '[{"state":"CLOSED","mergedAt":null,"closedAt":"2026-08-20T02:00:00Z","body":"<!-- autofix-superseded-by: 999 merged-at: 2026-08-20T00:00:00Z -->"}]' > "$GH_STUB_RESPONSE_FILE"
run_select "$incident_file" > /dev/null 2>&1
check "select.sh treats superseded drafts as merged fixes during deploy grace" $([ "$?" = "3" ] && echo 0 || echo 1)

echo '[]' > "$GH_STUB_RESPONSE_FILE"
out="$(run_select "$incident_file")"
check "select.sh emits an incident with no prior PR at all" $([ -n "$out" ] && echo 0 || echo 1)

################################################################################
# open no-fix issue must not starve the queue: skip, don't re-investigate
################################################################################
GH_STUB_ISSUE_HITS=1 run_select "$incident_file" > /dev/null 2>&1
check "select.sh skips (exit 3) when an open no-fix issue already tracks this key" $([ "$?" = "3" ] && echo 0 || echo 1)

unset GH_STUB_ISSUE_HITS
out="$(run_select "$incident_file")"
check "select.sh still investigates once the no-fix issue is gone" $([ -n "$out" ] && echo 0 || echo 1)

################################################################################
# 10: publish.sh path guard — denylist and allowlist both fatal on bad paths
################################################################################
FAKE_REPO="$TMP_DIR/fake-repo"
mkdir -p "$FAKE_REPO/scripts/error-autofix" "$FAKE_REPO/server/app/matcha/routes"
cp "$AUTOFIX_DIR"/*.sh "$FAKE_REPO/scripts/error-autofix/"
(
    cd "$FAKE_REPO" && git init -q && git config user.email t@example.com && git config user.name t \
    && echo "x" > README.md && git add -A && git commit -q -m init
)
cat > "$TMP_DIR/publish-decision.json" <<'EOF'
{"schema_version":1,"outcome":"no_safe_fix","safe_changes_present":false,"no_safe_fix_reason":"stub","criticality":{"level":"yellow","reasons":["stub"]},"confidence_score":70,"confidence_band":"medium"}
EOF
cat > "$TMP_DIR/publish-incident.json" <<'EOF'
{"stable_key":"aaa111111111","surface":"server","error_id":"id","kind":"http_error","level":"ERROR","exception_type":"DataError","message":"boom","traceback":"trace","source":"api","request_method":"GET","request_path":"/x","occurrences":1,"first_seen":"2026-08-20T00:00:00Z","last_seen":"2026-08-20T00:00:00Z"}
EOF
echo "changed" >> "$FAKE_REPO/scripts/error-autofix/collect.sh"
(
    cd "$FAKE_REPO" && GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    "$FAKE_REPO/scripts/error-autofix/publish.sh" "$TMP_DIR/publish-incident.json" \
      "$TMP_DIR/publish-decision.json" /dev/null /dev/null
) > "$TMP_DIR/publish_out.txt" 2>&1
check "publish.sh refuses a diff touching scripts/" $([ "$?" != "0" ] && echo 0 || echo 1)

(cd "$FAKE_REPO" && git checkout -- scripts/error-autofix/collect.sh)
echo "docs change" >> "$FAKE_REPO/README.md"
(
    cd "$FAKE_REPO" && GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    "$FAKE_REPO/scripts/error-autofix/publish.sh" "$TMP_DIR/publish-incident.json" \
      "$TMP_DIR/publish-decision.json" /dev/null /dev/null
) > "$TMP_DIR/publish_out2.txt" 2>&1
check "publish.sh refuses a diff outside server/app or server/tests" $([ "$?" != "0" ] && echo 0 || echo 1)
(cd "$FAKE_REPO" && git checkout -- README.md)

################################################################################
# 11: a later valid no-fix report replaces the retry placeholder body.
################################################################################
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GH_STUB_CALLS"
case "$1 $2" in
    "issue list") echo 91 ;;
    *) exit 0 ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"
cat > "$TMP_DIR/report.md" <<'EOF'
### Root cause
known schema mismatch
### Fix
no safe application-only fix
### Blast radius
one route
### Confidence
high
EOF
(
    cd "$FAKE_REPO" && PATH="$TMP_DIR/bin:$PATH" GH_STUB_CALLS="$TMP_DIR/gh_calls.txt" \
    GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    "$FAKE_REPO/scripts/error-autofix/publish.sh" "$TMP_DIR/publish-incident.json" \
      "$TMP_DIR/publish-decision.json" "$TMP_DIR/report.md" /dev/null
) > "$TMP_DIR/publish_out3.txt" 2>&1
check "publish.sh replaces a placeholder no-fix issue body" \
    $([ "$?" = "0" ] && grep -q '^issue edit 91 ' "$TMP_DIR/gh_calls.txt" && echo 0 || echo 1)

################################################################################
# Summary
################################################################################
echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
