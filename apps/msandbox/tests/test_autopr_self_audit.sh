#!/usr/bin/env bash
# Sealed self-audit lane contracts; no Docker, model, GitHub, or host state.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUDIT_DIR="$REPO_ROOT/scripts/autopr-self-audit"
WORKFLOW="$REPO_ROOT/.github/workflows/autopr-self-audit.yml"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/matcha-self-audit-test.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

! grep -qF 'schedule:' "$WORKFLOW"
grep -qF './scripts/agent-sandbox.sh autopr-ready' "$WORKFLOW"
grep -qF 'matcha-autopr-self-audit-sandbox' "$WORKFLOW"
grep -qF 'scripts/autopr-self-audit/verify.sh' "$WORKFLOW"
grep -qF 'write-commit-subject.sh fix' "$WORKFLOW"
grep -qF 'AUDIT_MAX_AGE_SECONDS="${AUTOPR_AUDIT_MAX_AGE_SECONDS:-21600}"' \
    "$REPO_ROOT/scripts/kanban-autopr/dispatch-if-idle.sh"
grep -qF 'scripts/autopr-self-audit/' "$AUDIT_DIR/_prompt.txt"
grep -qF "test_autopr_self_audit.sh'" "$AUDIT_DIR/publish.sh"
printf 'PASS: self-audit uses the one local clock, master switch, verifier, and sealed prompt\n'

cat > "$TMP_DIR/decision.json" <<'EOF'
{"schema_version":1,"outcome":"fix","safe_changes_present":true,"summary":"Repair the dispatcher contract."}
EOF
"$AUDIT_DIR/check-decision.sh" "$TMP_DIR/decision.json" "$TMP_DIR/normalized.json"
jq -e '.outcome == "fix" and .safe_changes_present == true' "$TMP_DIR/normalized.json" >/dev/null

cat > "$TMP_DIR/invalid.json" <<'EOF'
{"schema_version":1,"outcome":"operator_action","safe_changes_present":true,"summary":"Invalid disagreement."}
EOF
set +e
"$AUDIT_DIR/check-decision.sh" "$TMP_DIR/invalid.json" "$TMP_DIR/invalid-normalized.json" >/dev/null 2>&1
invalid_rc=$?
set -e
[ "$invalid_rc" -ne 0 ]
printf 'PASS: trusted shell validates model decision/diff agreement\n'

TEST_REPO="$TMP_DIR/repo"
mkdir -p "$TEST_REPO/scripts/autopr-self-audit" "$TEST_REPO/scripts/kanban-autopr" "$TMP_DIR/bin"
cp "$AUDIT_DIR/publish.sh" "$TEST_REPO/scripts/autopr-self-audit/publish.sh"
printf 'before\n' > "$TEST_REPO/scripts/kanban-autopr/example.sh"
git -C "$TEST_REPO" init -q
git -C "$TEST_REPO" config user.name test
git -C "$TEST_REPO" config user.email test@example.com
git -C "$TEST_REPO" add --all
git -C "$TEST_REPO" commit -qm initial
git -C "$TEST_REPO" branch -M main
git init --bare -q "$TMP_DIR/origin.git"
git -C "$TEST_REPO" remote add origin "$TMP_DIR/origin.git"
git -C "$TEST_REPO" switch -q -c bot/autopr-audit-abc123abc123

cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_GH_LOG"
case "$1 $2" in
  "pr list") : ;;
  "pr create") printf 'https://example.invalid/pull/1\n' ;;
  "pr edit") : ;;
  *) exit 2 ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"
cat > "$TMP_DIR/audit.json" <<'EOF'
{"fingerprint":"abc123abc123"}
EOF
cp "$TMP_DIR/decision.json" "$TMP_DIR/publish-decision.json"
printf '### Root cause\ncontract failed\n' > "$TMP_DIR/report.md"
printf '## Verification\nall green\n' > "$TMP_DIR/verification.md"
printf '%s\n' '{"schema_version":1,"commit_subject":"fix: restore AutoPR dispatcher contract"}' > "$TMP_DIR/commit-subject.json"
printf 'after\n' > "$TEST_REPO/scripts/kanban-autopr/example.sh"
PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" \
    GITHUB_REPOSITORY=x/x "$TEST_REPO/scripts/autopr-self-audit/publish.sh" \
    "$TMP_DIR/audit.json" "$TMP_DIR/publish-decision.json" \
    "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/commit-subject.json" >/dev/null
grep -q 'pr create' "$TMP_DIR/gh.log"
grep -q -- '--title fix: restore AutoPR dispatcher contract' "$TMP_DIR/gh.log"
[ "$(git -C "$TEST_REPO" log -1 --pretty=%s)" = 'fix: restore AutoPR dispatcher contract' ]
printf 'PASS: allowed AutoPR script repair publishes only a draft branch\n'

mkdir -p "$TEST_REPO/.github/workflows"
printf 'forbidden\n' > "$TEST_REPO/.github/workflows/escape.yml"
set +e
PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" \
    GITHUB_REPOSITORY=x/x "$TEST_REPO/scripts/autopr-self-audit/publish.sh" \
    "$TMP_DIR/audit.json" "$TMP_DIR/publish-decision.json" \
    "$TMP_DIR/report.md" "$TMP_DIR/verification.md" >/dev/null 2>&1
forbidden_rc=$?
set -e
[ "$forbidden_rc" -ne 0 ]
printf 'PASS: publisher rejects workflow and sealed-capsule changes\n'

# The audit is cheap; the repair is a Sol run. The same failing check set is
# handed to Codex once, not every six hours (15/15 failed runs, 2026-08-31 →
# 2026-09-07, all rejected by verify.sh for the same asyncpg import).
LEDGER_SH="$AUDIT_DIR/repair-ledger.sh"
export AUTOPR_SELF_AUDIT_LEDGER="$TMP_DIR/ledger.json"
printf '{"fingerprint":"aaaaaaaaaaaa","checks":[{"id":"contract_tests","status":"fail","repairability":"repo"}]}\n' > "$TMP_DIR/audit-a.json"
"$LEDGER_SH" should-repair "$TMP_DIR/audit-a.json"
"$LEDGER_SH" record "$TMP_DIR/audit-a.json" attempted
"$LEDGER_SH" record "$TMP_DIR/audit-a.json" rejected
set +e
"$LEDGER_SH" should-repair "$TMP_DIR/audit-a.json" 2>/dev/null; same_rc=$?
set -e
[ "$same_rc" -eq 3 ]
printf '{"fingerprint":"bbbbbbbbbbbb","checks":[]}\n' > "$TMP_DIR/audit-b.json"
"$LEDGER_SH" should-repair "$TMP_DIR/audit-b.json"
AUTOPR_LEDGER_NOW=$(( $(date +%s) + 700000 )) "$LEDGER_SH" should-repair "$TMP_DIR/audit-a.json"
"$LEDGER_SH" record "$TMP_DIR/audit-a.json" published
# A published-but-unmerged repair leaves the same checks failing: re-dispatching
# would burn a Sol run every six hours until a human merges.
set +e
"$LEDGER_SH" should-repair "$TMP_DIR/audit-a.json" 2>/dev/null; published_rc=$?
set -e
[ "$published_rc" -eq 3 ]
AUTOPR_LEDGER_NOW=$(( $(date +%s) + 700000 )) "$LEDGER_SH" should-repair "$TMP_DIR/audit-a.json"
jq -e '.failing_checks == ["contract_tests"] and .outcome == "published"' "$TMP_DIR/ledger.json" >/dev/null
grep -qF 'repair-ledger.sh should-repair' "$WORKFLOW"
grep -qF "if: steps.ledger.outputs.repair == 'true'" "$WORKFLOW"
grep -qF 'repair-ledger.sh record "$RUNNER_TEMP/autopr-audit.json" rejected' "$WORKFLOW"
unset AUTOPR_SELF_AUDIT_LEDGER
printf 'PASS: a repair is not retried for the same failing checks until the ledger window elapses\n'

# The repair lane may touch the harness, so the bridge's default apply-time
# denylist is narrowed here — but never to CI, deploy, secrets, or the
# sealed capsule itself.
grep -qF "AUTOPR_SANDBOX_PATH_DENY_RE='^(\\.github/|deploy/|secrets/|\\.githooks/|(.*/)?\\.env[^/]*$|scripts/autopr-self-audit/)'" "$AUDIT_DIR/investigate.sh"
grep -qF 'check_installed_dispatcher' "$AUDIT_DIR/audit.sh"
grep -qF 'git reset --hard HEAD' "$WORKFLOW"
printf 'PASS: repair lane keeps CI/deploy/secrets/capsule out of reach and audits the installed dispatcher\n'
