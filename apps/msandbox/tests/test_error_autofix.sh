#!/usr/bin/env bash
# Exercises apps/msandbox/error-autofix/* without touching prod, GitHub, or a real
# model. Stubs `ssh` and `gh` on PATH in the house style of
# test_collect_silent_error_evidence.sh / test_ci_guards.sh. Run:
#   ./apps/msandbox/tests/test_error_autofix.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
AUTOFIX_DIR="$REPO_ROOT/apps/msandbox/error-autofix"
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
      && grep -qF 'silent-error-autofix.yml' "$REPO_ROOT/apps/msandbox/harness/dispatch-if-idle.sh" \
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
      && grep -qF 'AUTOPR_CODEX_MODEL=gpt-5.6-luna' "$REPO_ROOT/apps/msandbox/harness/write-commit-subject.sh" \
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
[ "$1" != api ] || { echo "${NOTIFY_STUB_COMMENTS:-[]}"; exit 0; }
case "$1 $2" in
    "pr list")
        if [[ "$*" == *"--label autofix"* ]]; then
            echo '[{"number":42,"state":"OPEN","title":"🟡 [C70] fix: AttributeError","url":"https://github.test/pr/42","author":{"login":"'"${NOTIFY_STUB_AUTHOR:-app/github-actions}"'"},"body":"<!-- matcha-autofix-notify-review: abc123abc123 -->\n<!-- matcha-autopr-criticality: yellow -->\n<!-- matcha-autopr-confidence-score: 70 -->"}]'
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
# The marker in a HUMAN-authored body or comment is public input, not an
# instruction to exec into the production container and send mail.
rm -f "$TMP_DIR/notify.log"
PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" GH_TOKEN=x \
  GITHUB_REPOSITORY=x/x NOTIFY_STUB_LOG="$TMP_DIR/notify.log" NOTIFY_STUB_AUTHOR=some-human \
  NOTIFY_STUB_COMMENTS='[{"user":{"login":"some-human"},"body":"<!-- matcha-autofix-notify-review: abc123abc123 -->"}]' \
  "$AUTOFIX_DIR/notify-review-ready.sh" --reconcile >/dev/null 2>&1
check "reconciliation ignores notify markers written by humans" \
  $([ "$?" = 0 ] && [ ! -s "$TMP_DIR/notify.log" ] && echo 0 || echo 1)
check "the in-container mail snippet initializes settings first" \
  $(grep -qF 'from app.config import load_settings' "$AUTOFIX_DIR/notify-review-ready.sh" \
    && grep -qF 'load_settings()' "$AUTOFIX_DIR/notify-review-ready.sh" && echo 0 || echo 1)

################################################################################
# Correlated-log fetch — a client incident's request_id is attacker-controlled
# and is interpolated into a remote shell command. Anything outside the safe
# alphabet must never reach ssh.
################################################################################
cat > "$TMP_DIR/bin/ssh" <<'EOF'
#!/usr/bin/env bash
cat > "$SSH_STUB_CAPTURE"
exit 0
EOF
chmod +x "$TMP_DIR/bin/ssh"
printf '{"request_id":"x\"; touch /tmp/pwned; echo \"","stable_key":"abc123abc123"}\n' > "$TMP_DIR/hostile-incident.json"
: > "$TMP_DIR/ssh-capture"
PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" SSH_STUB_CAPTURE="$TMP_DIR/ssh-capture" \
  "$AUTOFIX_DIR/fetch-correlated-log.sh" "$TMP_DIR/hostile-incident.json" > "$TMP_DIR/hostile-out" 2>/dev/null
check "fetch-correlated-log.sh refuses a shell-hostile request_id before ssh" \
  $([ "$?" = 0 ] && [ ! -s "$TMP_DIR/ssh-capture" ] && [ ! -s "$TMP_DIR/hostile-out" ] && echo 0 || echo 1)
printf '{"request_id":"req-0123abcd","stable_key":"abc123abc123"}\n' > "$TMP_DIR/safe-incident.json"
PATH="$TMP_DIR/bin:$PATH" SSH_KEY="$TMP_DIR/fake.pem" SSH_STUB_CAPTURE="$TMP_DIR/ssh-capture" \
  "$AUTOFIX_DIR/fetch-correlated-log.sh" "$TMP_DIR/safe-incident.json" >/dev/null 2>&1
check "a well-formed request_id still reaches the remote grep" \
  $(grep -qF -- 'grep -F -- "[rid=req-0123abcd]"' "$TMP_DIR/ssh-capture" && echo 0 || echo 1)

################################################################################
# 6-9: select.sh dedup decisions, via a stubbed `gh` on PATH
################################################################################
GH_STUB_RESPONSE_FILE="$TMP_DIR/gh_response.json"
echo '[{"state":"OPEN","mergedAt":null,"closedAt":null}]' > "$GH_STUB_RESPONSE_FILE"
cat > "$TMP_DIR/bin/gh" <<EOF
#!/usr/bin/env bash
case "\$1 \$2" in
    "issue list")
        # Emulate gh's own --jq so select.sh's real filter is exercised: the
        # cooldown clock comes from a marker in the issue BODY, and a stub that
        # echoed a pre-computed timestamp would never test that.
        jq_expr=""; want_jq=false
        for a in "\$@"; do
            if [ "\$want_jq" = true ]; then jq_expr="\$a"; want_jq=false; fi
            [ "\$a" != --jq ] || want_jq=true
        done
        printf '%s' "\${GH_STUB_ISSUES:-[]}" | jq -r "\$jq_expr"
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
nofix_issue() {
    # $1 = the confirmation marker publish.sh stamps into the body, $2 = createdAt
    jq -cn --arg confirmed "$1" --arg created "$2" \
        '[{title: "error: Boom in /x [ddd444444444]",
           body: ("no safe fix\n<!-- matcha-autofix-nofix-confirmed: " + $confirmed + " -->"),
           createdAt: $created}]'
}
now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
GH_STUB_ISSUES="$(nofix_issue "$now_iso" "$now_iso")" run_select "$incident_file" > /dev/null 2>&1
check "select.sh skips (exit 3) when an open no-fix issue already tracks this key" $([ "$?" = "3" ] && echo 0 || echo 1)

# …but not forever: once the bot's own last no-fix confirmation is a week old
# the incident is re-investigated (publish.sh then restamps the body).
out="$(GH_STUB_ISSUES="$(nofix_issue "2026-01-01T00:00:00Z" "2026-01-01T00:00:00Z")" run_select "$incident_file")"
check "select.sh re-investigates a no-fix issue after its cooldown" $([ -n "$out" ] && echo 0 || echo 1)

# A human commenting "still broken" bumps the issue's updatedAt. Keying the
# cooldown off that would extend the suppression another full week — the exact
# opposite of what the comment means.
out="$(GH_STUB_ISSUES="$(nofix_issue "2026-01-01T00:00:00Z" "$now_iso")" run_select "$incident_file")"
check "a human touching the no-fix issue does not extend its cooldown" $([ -n "$out" ] && echo 0 || echo 1)

# An issue predating the marker falls back to createdAt rather than never expiring.
out="$(jq -cn '[{title:"error: Boom in /x [ddd444444444]",body:"legacy body",createdAt:"2026-01-01T00:00:00Z"}]' > "$TMP_DIR/legacy-issue.json"; \
    GH_STUB_ISSUES="$(cat "$TMP_DIR/legacy-issue.json")" run_select "$incident_file")"
check "a pre-marker no-fix issue falls back to createdAt" $([ -n "$out" ] && echo 0 || echo 1)

unset GH_STUB_ISSUES
out="$(run_select "$incident_file")"
check "select.sh still investigates once the no-fix issue is gone" $([ -n "$out" ] && echo 0 || echo 1)

################################################################################
# Merged is not deployed. With the deployed build known, a merged fix whose
# commit is not in it yet is skipped instead of re-investigated every two
# hours until the next manual deploy (which produced a duplicate PR).
################################################################################
head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)"
parent_sha="$(git -C "$REPO_ROOT" rev-parse HEAD~1)"
make_incident "eee555555555" "2026-08-19T00:00:00Z" "2026-08-22T00:00:00Z" > "$incident_file"
printf '[{"state":"MERGED","mergedAt":"2026-08-20T00:00:00Z","closedAt":"2026-08-20T00:00:00Z","mergeCommit":{"oid":"%s"}}]\n' "$head_sha" > "$GH_STUB_RESPONSE_FILE"
AUTOFIX_DEPLOYED_SHA="$parent_sha" run_select "$incident_file" > /dev/null 2>&1
check "select.sh skips a merged fix whose commit is not in the deployed build" $([ "$?" = "3" ] && echo 0 || echo 1)
out="$(AUTOFIX_DEPLOYED_SHA="$head_sha" run_select "$incident_file")"
check "select.sh re-opens a merged fix once it is deployed and still recurring" $([ -n "$out" ] && echo 0 || echo 1)
out="$(AUTOFIX_DEPLOYED_SHA="not-a-commit" run_select "$incident_file")"
check "an unresolvable deployed SHA falls back to the grace-window rule" $([ -n "$out" ] && echo 0 || echo 1)

# The cap read fails CLOSED: with no readable count, the selector dies
# instead of comparing an empty string and skipping the cap.
old_dir="$TMP_DIR/old-attempts"; mkdir -p "$old_dir/attempts"
touch -t 202601010000 "$old_dir/attempts/stalekey00001"
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" AUTOFIX_CACHE_DIR="$old_dir" \
    "$AUTOFIX_DIR/select.sh" "$incident_file" > /dev/null 2>&1 || true
check "select.sh prunes attempt markers older than the retention window" \
    $([ ! -e "$old_dir/attempts/stalekey00001" ] && echo 0 || echo 1)

################################################################################
# Deployed-fix verification: a merged autofix PR whose commit is live is
# marked verified when its fingerprint is silent, failed when it recurs.
################################################################################
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$GH_STUB_CALLS"
case "$1 $2" in
    "pr list") cat "$GH_STUB_MERGED_PRS" ;;
    *) exit 0 ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"
jq -n --arg sha "$parent_sha" '[{number:77,mergedAt:"2026-01-01T00:00:00Z",mergeCommit:{oid:$sha},labels:[{name:"autofix"}],url:"x",body:"<!-- autofix-key: aaa111111111 -->"}]' > "$TMP_DIR/merged-prs.json"
printf '[]\n' > "$TMP_DIR/quiet-incidents.json"
# Deploys are manual, so the verifier scores from when this lane FIRST saw the
# build live, not from mergedAt. Seed that observation an hour ago: on a real
# first sighting every PR is "waiting" until the grace window elapses.
deploy_ledger="$TMP_DIR/deploy-ledger.json"
seen_ago="$(date -u -v-1H +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"
jq -n --arg sha "$head_sha" --arg seen "$seen_ago" '{($sha): $seen}' > "$deploy_ledger"
: > "$TMP_DIR/verify-calls"
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x GH_STUB_CALLS="$TMP_DIR/verify-calls" \
  GH_STUB_MERGED_PRS="$TMP_DIR/merged-prs.json" AUTOFIX_DEPLOYED_SHA="$head_sha" \
  AUTOFIX_DEPLOY_LEDGER="$deploy_ledger" AUTOFIX_DEPLOY_GRACE_HOURS=0 \
  "$AUTOFIX_DIR/verify-deployed-fixes.sh" "$TMP_DIR/quiet-incidents.json" >/dev/null 2>&1
check "a deployed fix whose fingerprint went quiet is marked production-verified" \
  $(grep -q -- '--add-label production-verified' "$TMP_DIR/verify-calls" && grep -q '^pr comment 77 ' "$TMP_DIR/verify-calls" && echo 0 || echo 1)
make_incident "aaa111111111" "2026-08-19T00:00:00Z" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$TMP_DIR/loud-incidents.json"
: > "$TMP_DIR/verify-calls"
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x GH_STUB_CALLS="$TMP_DIR/verify-calls" \
  GH_STUB_MERGED_PRS="$TMP_DIR/merged-prs.json" AUTOFIX_DEPLOYED_SHA="$head_sha" \
  AUTOFIX_DEPLOY_LEDGER="$deploy_ledger" AUTOFIX_DEPLOY_GRACE_HOURS=0 \
  "$AUTOFIX_DIR/verify-deployed-fixes.sh" "$TMP_DIR/loud-incidents.json" >/dev/null 2>&1
check "a deployed fix whose fingerprint recurs is marked production-verification-failed" \
  $(grep -q -- '--add-label production-verification-failed' "$TMP_DIR/verify-calls" && echo 0 || echo 1)
# A merge that only just went live is not scored at all: every occurrence in the
# snapshot predates the deploy, so failing it would libel a working fix.
jq -n --arg sha "$head_sha" --arg seen "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '{($sha): $seen}' > "$TMP_DIR/fresh-ledger.json"
: > "$TMP_DIR/verify-calls"
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x GH_STUB_CALLS="$TMP_DIR/verify-calls" \
  GH_STUB_MERGED_PRS="$TMP_DIR/merged-prs.json" AUTOFIX_DEPLOYED_SHA="$head_sha" \
  AUTOFIX_DEPLOY_LEDGER="$TMP_DIR/fresh-ledger.json" \
  "$AUTOFIX_DIR/verify-deployed-fixes.sh" "$TMP_DIR/loud-incidents.json" >/dev/null 2>&1
check "a just-deployed merge is not failed by pre-deploy occurrences" \
  $([ ! -s "$TMP_DIR/verify-calls" ] || ! grep -q -- '--add-label' "$TMP_DIR/verify-calls" && echo 0 || echo 1)
: > "$TMP_DIR/verify-calls"
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x GH_STUB_CALLS="$TMP_DIR/verify-calls" \
  GH_STUB_MERGED_PRS="$TMP_DIR/merged-prs.json" AUTOFIX_DEPLOYED_SHA="$parent_sha~1" \
  AUTOFIX_DEPLOY_LEDGER="$deploy_ledger" \
  "$AUTOFIX_DIR/verify-deployed-fixes.sh" "$TMP_DIR/quiet-incidents.json" >/dev/null 2>&1
check "an undeployed merge is neither verified nor failed" \
  $(! grep -q -- '--add-label' "$TMP_DIR/verify-calls" && echo 0 || echo 1)

################################################################################
# verify.sh — a pytest that did not run (rc 2: internal error / interrupted)
# renders "unavailable" and counts as unverified, never as "0 failed".
################################################################################
VERIFY_REPO="$TMP_DIR/verify-repo"
mkdir -p "$VERIFY_REPO/server/app" "$VERIFY_REPO/server/tests/app"
(
    cd "$VERIFY_REPO" && git init -q && git config user.email t@example.com && git config user.name t \
    && printf 'x = 1\n' > server/app/x.py && printf 'def test_x():\n    pass\n' > server/tests/app/test_x.py \
    && printf 'a\n' > server/requirements.txt && git add -A && git commit -q -m base
)
printf 'x = 2\n' > "$VERIFY_REPO/server/app/x.py"
cat > "$TMP_DIR/fake-python" <<'EOF'
#!/usr/bin/env bash
case "$*" in
    *"import pytest, pytest_asyncio"*) exit 0 ;;
    *py_compile*) exit 0 ;;
    *pytest*) echo "INTERNALERROR> boom"; exit "${FAKE_PYTEST_RC:-2}" ;;
esac
exit 0
EOF
chmod +x "$TMP_DIR/fake-python"
verify_env="$TMP_DIR/verify-github-env"; : > "$verify_env"
verify_out="$(AUTOPR_WORKSPACE_ROOT="$VERIFY_REPO" AUTOFIX_BASE_SHA="$(git -C "$VERIFY_REPO" rev-parse HEAD)" \
    AUTOFIX_DEV_VENV_PY="$TMP_DIR/fake-python" AUTOFIX_CACHE_DIR="$TMP_DIR/verify-cache" \
    RUNNER_TEMP="$TMP_DIR" GITHUB_ENV="$verify_env" "$AUTOFIX_DIR/verify.sh" 2>/dev/null)"
check "verify.sh renders a crashed pytest as unavailable, not 0 failed" \
  $(grep -q 'unavailable' <<< "$verify_out" && ! grep -q '0 failed | 0 failed' <<< "$verify_out" \
    && grep -q '^AUTOFIX_NEW_FAILURES=1$' "$verify_env" && echo 0 || echo 1)
: > "$verify_env"
AUTOPR_WORKSPACE_ROOT="$VERIFY_REPO" AUTOFIX_BASE_SHA="$(git -C "$VERIFY_REPO" rev-parse HEAD)" \
    AUTOFIX_DEV_VENV_PY="$TMP_DIR/does-not-exist" AUTOFIX_CACHE_DIR="$TMP_DIR/verify-cache" \
    RUNNER_TEMP="$TMP_DIR" GITHUB_ENV="$verify_env" "$AUTOFIX_DIR/verify.sh" >/dev/null 2>&1
check "verify.sh with no interpreter reports unverified (AUTOFIX_NEW_FAILURES=1) on both paths" \
  $(grep -q '^AUTOFIX_NEW_FAILURES=1$' "$verify_env" && echo 0 || echo 1)

################################################################################
# verify.sh — the runner-owned toolchain. The runner is a launchd job, and
# macOS drops a launchd job's ~/Documents grant whenever its binary changes
# (the 2026-08-31 runner self-update): from then to 09-14 every bot PR said
# "no usable Python interpreter" while the dev venv worked from a terminal.
# So: no ~/Documents default, and a cache under ~/.cache that verify.sh
# reads and provision-verify-toolchain.sh writes, keyed by toolchain.sh.
################################################################################
check "verify.sh has no default that reaches into ~/Documents (code lines, comments may explain why)" \
  $(! grep -vE '^[[:space:]]*#' "$AUTOFIX_DIR/verify.sh" | grep -q 'Documents' && echo 0 || echo 1)
check "verify.sh and the provisioner share one key helper" \
  $(grep -q '\. "\$SCRIPT_DIR/toolchain.sh"' "$AUTOFIX_DIR/verify.sh" \
    && grep -q 'error-autofix/toolchain.sh' "$AUTOFIX_DIR/../harness/provision-verify-toolchain.sh" && echo 0 || echo 1)

source "$AUTOFIX_DIR/toolchain.sh"
TOOLCHAIN_CACHE="$TMP_DIR/toolchain-cache"
provisioner="$AUTOFIX_DIR/../harness/provision-verify-toolchain.sh"
AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" "$provisioner" --check --repo "$VERIFY_REPO" > "$TMP_DIR/toolchain-check.out" 2>&1
check "provisioner --check reports a missing toolchain with exit 3" \
  $([ "$?" -eq 3 ] && grep -q 'python: MISSING' "$TMP_DIR/toolchain-check.out" \
    && grep -q 'client: MISSING' "$TMP_DIR/toolchain-check.out" && echo 0 || echo 1)

# A cached venv under the keyed path is found with no override set at all.
cached_venv="$(AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" autofix_venv_dir "$VERIFY_REPO")"
mkdir -p "$cached_venv/bin"
cp "$TMP_DIR/fake-python" "$cached_venv/bin/python"
: > "$verify_env"
verify_out="$(AUTOPR_WORKSPACE_ROOT="$VERIFY_REPO" AUTOFIX_BASE_SHA="$(git -C "$VERIFY_REPO" rev-parse HEAD)" \
    AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" FAKE_PYTEST_RC=0 \
    RUNNER_TEMP="$TMP_DIR" GITHUB_ENV="$verify_env" "$AUTOFIX_DIR/verify.sh" 2>/dev/null)"
check "verify.sh uses the cached toolchain venv and renders a real pytest row" \
  $(grep -q '| pytest server/tests/app | 0 failed | 0 failed |' <<< "$verify_out" \
    && ! grep -q 'unavailable' <<< "$verify_out" \
    && grep -q '^AUTOFIX_NEW_FAILURES=0$' "$verify_env" && echo 0 || echo 1)

# A client change with no node_modules in the tree: the cached client
# toolchain is symlinked into both trees and the TypeScript row renders.
(
    cd "$VERIFY_REPO" && mkdir -p client/src \
    && printf '{"name":"x","version":"0.0.0"}\n' > client/package.json \
    && printf '{"name":"x","lockfileVersion":3}\n' > client/package-lock.json \
    && printf 'export const a = 1;\n' > client/src/a.ts \
    && git add -A && git commit -q -m client-base
)
printf 'export const a = 2;\n' > "$VERIFY_REPO/client/src/a.ts"
cached_node="$(AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" autofix_node_root "$VERIFY_REPO")/node_modules"
mkdir -p "$cached_node/.bin"
printf '#!/usr/bin/env bash\nexit 0\n' > "$cached_node/.bin/tsc"
printf '#!/usr/bin/env bash\nexit 0\n' > "$cached_node/.bin/vitest"
chmod +x "$cached_node/.bin/tsc" "$cached_node/.bin/vitest"
: > "$verify_env"
verify_out="$(AUTOPR_WORKSPACE_ROOT="$VERIFY_REPO" AUTOFIX_BASE_SHA="$(git -C "$VERIFY_REPO" rev-parse HEAD)" \
    AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" FAKE_PYTEST_RC=0 \
    RUNNER_TEMP="$TMP_DIR" GITHUB_ENV="$verify_env" "$AUTOFIX_DIR/verify.sh" 2>/dev/null)"
# The cache is linked into the branch tree for the run and unlinked after it.
# `AUTOPR_WORKSPACE_ROOT` can name any checkout, and a link left pointing into
# the shared cache turns a later `npm ci` in that clone into an in-place
# rewrite of the runner-owned toolchain every lane reads.
check "verify.sh typechecks against the cached client toolchain and leaves the tree unchanged" \
  $(grep -q '| TypeScript | 0 diagnostics | 0 diagnostics |' <<< "$verify_out" \
    && ! grep -q 'no client toolchain' <<< "$verify_out" \
    && [ ! -e "$VERIFY_REPO/client/node_modules" ] && [ ! -L "$VERIFY_REPO/client/node_modules" ] \
    && grep -q '^AUTOFIX_NEW_FAILURES=0$' "$verify_env" && echo 0 || echo 1)
AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" "$provisioner" --check --repo "$VERIFY_REPO" >/dev/null 2>&1
check "provisioner --check is current once both keyed directories are usable" $([ "$?" -eq 0 ] && echo 0 || echo 1)
# A real directory in the tree is never replaced by the cache symlink.
rm -f "$VERIFY_REPO/client/node_modules"
mkdir -p "$VERIFY_REPO/client/node_modules/.bin"
printf '#!/usr/bin/env bash\necho "src/a.ts(1,1): error TS1: real tree" >&2\nexit 1\n' > "$VERIFY_REPO/client/node_modules/.bin/tsc"
printf '#!/usr/bin/env bash\nexit 0\n' > "$VERIFY_REPO/client/node_modules/.bin/vitest"
chmod +x "$VERIFY_REPO/client/node_modules/.bin/tsc" "$VERIFY_REPO/client/node_modules/.bin/vitest"
verify_out="$(AUTOPR_WORKSPACE_ROOT="$VERIFY_REPO" AUTOFIX_BASE_SHA="$(git -C "$VERIFY_REPO" rev-parse HEAD)" \
    AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" FAKE_PYTEST_RC=0 \
    RUNNER_TEMP="$TMP_DIR" GITHUB_ENV="$verify_env" "$AUTOFIX_DIR/verify.sh" 2>/dev/null)"
check "verify.sh prefers a real node_modules in the tree over the cache and never replaces it" \
  $([ ! -L "$VERIFY_REPO/client/node_modules" ] \
    && grep -q '| TypeScript | 1 diagnostics | 1 diagnostics |' <<< "$verify_out" && echo 0 || echo 1)
# A branch tree carrying a real-but-broken node_modules (an interrupted
# `npm install`: no .bin/tsc) must report unavailable. Linking only the
# baseline to the cache and leaving the branch broken is the worst outcome
# available: the branch's tsc exits 127, prints no `error TS` lines, and
# `comm -13` reports zero regressions — a PR that ADDS type errors would
# publish as verified-clean.
rm -rf "$VERIFY_REPO/client/node_modules"
mkdir -p "$VERIFY_REPO/client/node_modules/.bin"
: > "$verify_env"
verify_out="$(AUTOPR_WORKSPACE_ROOT="$VERIFY_REPO" AUTOFIX_BASE_SHA="$(git -C "$VERIFY_REPO" rev-parse HEAD)" \
    AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" FAKE_PYTEST_RC=0 \
    RUNNER_TEMP="$TMP_DIR" GITHUB_ENV="$verify_env" "$AUTOFIX_DIR/verify.sh" 2>/dev/null)"
check "a broken node_modules in the branch tree reports unavailable, never a false green" \
  $(grep -q 'no client toolchain usable from the branch tree' <<< "$verify_out" \
    && ! grep -q '| TypeScript | ' <<< "$verify_out" \
    && grep -q '^AUTOFIX_NEW_FAILURES=1$' "$verify_env" && echo 0 || echo 1)

# A link left behind by a hard-killed run dangles as soon as
# provision-verify-toolchain.sh prunes that key. Nothing else removes it, and
# while it sits there the `! -L` test keeps matching — so a real node_modules
# installed here later would never be preferred again.
rm -rf "$VERIFY_REPO/client/node_modules"
# Ours — it points inside the cache root verify.sh is told to use.
ln -s "$TMP_DIR/pruned-cache/client-prunedkey/node_modules" "$VERIFY_REPO/client/node_modules"
verify_out="$(AUTOPR_WORKSPACE_ROOT="$VERIFY_REPO" AUTOFIX_BASE_SHA="$(git -C "$VERIFY_REPO" rev-parse HEAD)" \
    AUTOFIX_CACHE_DIR="$TMP_DIR/pruned-cache" FAKE_PYTEST_RC=0 \
    RUNNER_TEMP="$TMP_DIR" GITHUB_ENV="$verify_env" "$AUTOFIX_DIR/verify.sh" 2>/dev/null)"
check "a node_modules link left dangling by a pruned key is removed, not kept" \
  $([ ! -L "$VERIFY_REPO/client/node_modules" ] && [ ! -e "$VERIFY_REPO/client/node_modules" ] \
    && grep -q 'no client toolchain' <<< "$verify_out" && echo 0 || echo 1)

# A symlink the tree already had, pointing at a usable tree OUTSIDE our cache
# (a shared or pnpm-style store), is not ours: it is the dependency source,
# and a read-only verification run must neither replace nor delete it.
rm -rf "$VERIFY_REPO/client/node_modules"
foreign_modules="$TMP_DIR/foreign-node-modules"
mkdir -p "$foreign_modules/.bin"
printf '#!/usr/bin/env bash\nexit 0\n' > "$foreign_modules/.bin/tsc"
printf '#!/usr/bin/env bash\nexit 0\n' > "$foreign_modules/.bin/vitest"
chmod +x "$foreign_modules/.bin/tsc" "$foreign_modules/.bin/vitest"
ln -s "$foreign_modules" "$VERIFY_REPO/client/node_modules"
: > "$verify_env"
verify_out="$(AUTOPR_WORKSPACE_ROOT="$VERIFY_REPO" AUTOFIX_BASE_SHA="$(git -C "$VERIFY_REPO" rev-parse HEAD)" \
    AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" FAKE_PYTEST_RC=0 \
    RUNNER_TEMP="$TMP_DIR" GITHUB_ENV="$verify_env" "$AUTOFIX_DIR/verify.sh" 2>/dev/null)"
check "a symlinked node_modules the tree already had is used, not clobbered or deleted" \
  $([ -L "$VERIFY_REPO/client/node_modules" ] \
    && [ "$(readlink "$VERIFY_REPO/client/node_modules")" = "$foreign_modules" ] \
    && grep -q '| TypeScript | 0 diagnostics | 0 diagnostics |' <<< "$verify_out" \
    && ! grep -q 'no client toolchain' <<< "$verify_out" && echo 0 || echo 1)
rm -f "$VERIFY_REPO/client/node_modules"

# The Verify step has a timeout; a bash killed by SIGTERM with the default
# disposition never runs its EXIT trap, so the planted link would survive in
# the persistent (`clean: false`) checkout.
check "verify.sh cleans up on a signal, not only on a normal exit" \
  $(grep -q "trap 'cleanup; exit 143' TERM" "$AUTOFIX_DIR/verify.sh" \
    && grep -q "trap 'cleanup; exit 130' INT" "$AUTOFIX_DIR/verify.sh" && echo 0 || echo 1)

# A concurrent lane's cache entry survives a provision from a tree whose
# manifests differ: without the holder refcount, `prune_stale` rm -rfs the
# venv and node_modules a running verify.sh is symlinked into — pytest dies
# mid-suite and both tsc calls 127 through dangling links.
held_venv="$(AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" autofix_venv_dir "$VERIFY_REPO")"
AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" autofix_hold_toolchain "$held_venv"
OTHER_REPO="$TMP_DIR/other-repo"
mkdir -p "$OTHER_REPO/server" "$OTHER_REPO/client"
printf 'b\n' > "$OTHER_REPO/server/requirements.txt"
printf '{"name":"y","lockfileVersion":3}\n' > "$OTHER_REPO/client/package-lock.json"
printf '{"name":"y","version":"0.0.0"}\n' > "$OTHER_REPO/client/package.json"
AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" PY312=/nonexistent AUTOFIX_NPM_BIN=/nonexistent \
    "$provisioner" --repo "$OTHER_REPO" > "$TMP_DIR/prune.out" 2>&1
check "prune_stale keeps a cache entry a running lane still holds" \
  $([ -d "$held_venv" ] && grep -q 'in use by a running lane' "$TMP_DIR/prune.out" && echo 0 || echo 1)
AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" autofix_release_toolchain "$held_venv"
AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" PY312=/nonexistent AUTOFIX_NPM_BIN=/nonexistent \
    "$provisioner" --repo "$OTHER_REPO" > "$TMP_DIR/prune2.out" 2>&1
check "prune_stale collects it once the holder is gone" \
  $([ ! -d "$held_venv" ] && echo 0 || echo 1)

# Nothing else ever reclaimed another run's staging directory: build_python
# and build_node only remove their OWN `$$` path, and prune_stale used to
# `continue` past every `*.tmp.*`. A venv is ~1 GB, so interrupted runs
# accumulated silently.
live_tmp="$TOOLCHAIN_CACHE/venv-py312-liveheld.tmp.$$"
dead_tmp="$TOOLCHAIN_CACHE/venv-py312-orphaned.tmp.999999"
mkdir -p "$live_tmp" "$dead_tmp"
AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" PY312=/nonexistent AUTOFIX_NPM_BIN=/nonexistent \
    "$provisioner" --repo "$OTHER_REPO" > "$TMP_DIR/prune-tmp.out" 2>&1
check "an abandoned staging directory is reclaimed, a live one is not" \
  $([ ! -d "$dead_tmp" ] && [ -d "$live_tmp" ] \
    && grep -q 'pruned abandoned staging directory' "$TMP_DIR/prune-tmp.out" \
    && grep -q 'kept (build in flight)' "$TMP_DIR/prune-tmp.out" && echo 0 || echo 1)
rm -rf "$live_tmp"

# The in-use refcount has to be re-read after the build, not only before it:
# a venv takes minutes to build and a lane that starts reading the old entry
# in the meantime would have it deleted from under a running pytest.
check "the build re-checks the refcount before it replaces a live entry" \
  $(awk '/^build_python\(\)/,/^}/' "$provisioner" \
      | grep -A 2 'autofix_python_usable "\$temporary/bin/python"' >/dev/null \
    && [ "$(awk '/^build_python\(\)/,/^}/' "$provisioner" | grep -c 'autofix_toolchain_in_use') " = "2 " ] \
    && [ "$(awk '/^build_node\(\)/,/^}/' "$provisioner" | grep -c 'autofix_toolchain_in_use') " = "2 " ] \
    && echo 0 || echo 1)

# A tree with only requirements-dev.txt has no key: build_python passes
# requirements.txt to pip unconditionally, so a key there is a path that can
# never become present.
DEVONLY_REPO="$TMP_DIR/devonly-repo"
mkdir -p "$DEVONLY_REPO/server"
printf 'pytest\n' > "$DEVONLY_REPO/server/requirements-dev.txt"
devonly_key_rc=0
AUTOFIX_CACHE_DIR="$TOOLCHAIN_CACHE" autofix_venv_dir "$DEVONLY_REPO" >/dev/null 2>&1 || devonly_key_rc=$?
check "a dev-only manifest set yields no python key" $([ "$devonly_key_rc" != 0 ] && echo 0 || echo 1)

################################################################################
# 10: publish.sh path guard — denylist and allowlist both fatal on bad paths
################################################################################
FAKE_REPO="$TMP_DIR/fake-repo"
mkdir -p "$FAKE_REPO/apps/msandbox/error-autofix" "$FAKE_REPO/server/app/matcha/routes"
cp "$AUTOFIX_DIR"/*.sh "$FAKE_REPO/apps/msandbox/error-autofix/"
# publish.sh sources the shared dirty-worktree guard out of harness/.
mkdir -p "$FAKE_REPO/apps/msandbox/harness"
cp "$AUTOFIX_DIR/../harness/workspace-guard.sh" "$FAKE_REPO/apps/msandbox/harness/workspace-guard.sh"
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
echo "changed" >> "$FAKE_REPO/apps/msandbox/error-autofix/collect.sh"
(
    cd "$FAKE_REPO" && GH_TOKEN=x GITHUB_REPOSITORY=x/x AUTOPR_WORKSPACE_ROOT="$FAKE_REPO" \
    "$FAKE_REPO/apps/msandbox/error-autofix/publish.sh" "$TMP_DIR/publish-incident.json" \
      "$TMP_DIR/publish-decision.json" /dev/null /dev/null
) > "$TMP_DIR/publish_out.txt" 2>&1
check "publish.sh refuses a diff touching scripts/" $([ "$?" != "0" ] && echo 0 || echo 1)

(cd "$FAKE_REPO" && git checkout -- apps/msandbox/error-autofix/collect.sh)
echo "docs change" >> "$FAKE_REPO/README.md"
(
    cd "$FAKE_REPO" && GH_TOKEN=x GITHUB_REPOSITORY=x/x AUTOPR_WORKSPACE_ROOT="$FAKE_REPO" \
    "$FAKE_REPO/apps/msandbox/error-autofix/publish.sh" "$TMP_DIR/publish-incident.json" \
      "$TMP_DIR/publish-decision.json" /dev/null /dev/null
) > "$TMP_DIR/publish_out2.txt" 2>&1
check "publish.sh refuses a diff outside server/app or server/tests" $([ "$?" != "0" ] && echo 0 || echo 1)
(cd "$FAKE_REPO" && git checkout -- README.md)

# publish.sh's five `git reset --hard` calls carry no pathspec. Run without
# AUTOPR_WORKSPACE_ROOT against a dirty tree they discard a developer's work in
# progress, so the publisher must refuse before reaching them.
echo "local work in progress" > "$FAKE_REPO/uncommitted.txt"
dirty_guard_err="$(
    cd "$FAKE_REPO" && GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    "$FAKE_REPO/apps/msandbox/error-autofix/publish.sh" "$TMP_DIR/publish-incident.json" \
      "$TMP_DIR/publish-decision.json" /dev/null /dev/null 2>&1 >/dev/null
)"
dirty_guard_rc=$?
check "publish.sh refuses a dirty worktree when AUTOPR_WORKSPACE_ROOT is unset" \
    $([ "$dirty_guard_rc" != "0" ] \
        && printf '%s' "$dirty_guard_err" | grep -qF 'AUTOPR_WORKSPACE_ROOT is unset' \
        && [ -f "$FAKE_REPO/uncommitted.txt" ] && echo 0 || echo 1)
rm -f "$FAKE_REPO/uncommitted.txt"

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
    GH_TOKEN=x GITHUB_REPOSITORY=x/x AUTOPR_WORKSPACE_ROOT="$FAKE_REPO" \
    "$FAKE_REPO/apps/msandbox/error-autofix/publish.sh" "$TMP_DIR/publish-incident.json" \
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
