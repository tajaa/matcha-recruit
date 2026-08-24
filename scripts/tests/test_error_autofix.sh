#!/usr/bin/env bash
# Exercises scripts/error-autofix/* without touching prod, GitHub, or a real
# model. Stubs `ssh` and `gh` on PATH in the house style of
# test_collect_silent_error_evidence.sh / test_ci_guards.sh. Run:
#   ./scripts/tests/test_error_autofix.sh
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOFIX_DIR="$REPO_ROOT/scripts/error-autofix"
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
# Fallback workflow evidence must remain actionable, rather than being replaced
# with an empty incident list before select.sh runs.
################################################################################
workflow="$REPO_ROOT/.github/workflows/silent-error-autofix.yml"
fallback_block="$(sed -n '/Fallback log-grep evidence/,/Select one incident/p' "$workflow")"
check "fallback turns nonempty evidence into an incident" \
    $([[ "$fallback_block" == *'if [ ! -s "$RUNNER_TEMP/silent-error-evidence.txt" ]'* && "$fallback_block" == *'--rawfile evidence'* && "$fallback_block" == *'stable_key: $key'* ]] && echo 0 || echo 1)

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

echo '[{"state":"CLOSED","mergedAt":null,"closedAt":"2026-08-22T00:00:00Z"}]' > "$GH_STUB_RESPONSE_FILE"
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
echo "changed" >> "$FAKE_REPO/scripts/error-autofix/collect.sh"
(
    cd "$FAKE_REPO" && GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    "$FAKE_REPO/scripts/error-autofix/publish.sh" /dev/null /dev/null /dev/null
) > "$TMP_DIR/publish_out.txt" 2>&1
check "publish.sh refuses a diff touching scripts/" $([ "$?" != "0" ] && echo 0 || echo 1)

(cd "$FAKE_REPO" && git checkout -- scripts/error-autofix/collect.sh)
echo "docs change" >> "$FAKE_REPO/README.md"
(
    cd "$FAKE_REPO" && GH_TOKEN=x GITHUB_REPOSITORY=x/x \
    "$FAKE_REPO/scripts/error-autofix/publish.sh" /dev/null /dev/null /dev/null
) > "$TMP_DIR/publish_out2.txt" 2>&1
check "publish.sh refuses a diff outside server/app or server/tests" $([ "$?" != "0" ] && echo 0 || echo 1)

################################################################################
# Summary
################################################################################
echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
