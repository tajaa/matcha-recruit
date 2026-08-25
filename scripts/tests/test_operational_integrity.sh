#!/usr/bin/env bash
# Static safety checks for read-only backup/schema monitoring scripts and workflow.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP="$REPO_ROOT/scripts/ops-health/backup-probe.sh"
SCHEMA="$REPO_ROOT/scripts/ops-health/schema-snapshot.sh"
WORKFLOW="$REPO_ROOT/.github/workflows/operational-integrity-checks.yml"
PASS=0
FAIL=0

check() {
    if [ "$2" = 0 ]; then
        echo "PASS: $1"
        PASS=$((PASS + 1))
    else
        echo "FAIL: $1"
        FAIL=$((FAIL + 1))
    fi
}

check "backup probe validates keys before SSH" \
    $(grep -q 'unsafe backup key' "$BACKUP" && grep -q 'mktemp /tmp/matcha-backup-check' "$BACKUP" && echo 0 || echo 1)
check "backup probe verifies complete download before pg_restore" \
    $(grep -q 'downloaded_size.*expected_size' "$BACKUP" && grep -q 'pg_restore --list' "$BACKUP" && echo 0 || echo 1)
check "backup probe removes remote temporary archives" \
    $(grep -q "trap 'rm -f" "$BACKUP" && echo 0 || echo 1)
check "schema probe never starts the shared dev container" \
    $(! grep -qE 'docker (start|run|create)' "$SCHEMA" && echo 0 || echo 1)
check "schema probe uses read-only sessions" \
    $(grep -q 'default_transaction_read_only=on' "$SCHEMA" && echo 0 || echo 1)
check "schema probe targets only live production container" \
    $(grep -q '13.56.253.173' "$SCHEMA" && grep -q 'matcha-postgres-prod' "$SCHEMA" && ! grep -q '3.101.83.217' "$SCHEMA" && echo 0 || echo 1)
check "schema dumps use deterministic read-only schema flags" \
    $(grep -q -- '--schema-only --quote-all-identifiers --no-owner --no-privileges' "$SCHEMA" && grep -q -- '--no-comments --no-security-labels --no-publications --no-subscriptions' "$SCHEMA" && echo 0 || echo 1)
check "workflow guards dumps behind revision drift" \
    $(grep -q "if: steps.compare.outputs.status == 'drift'" "$WORKFLOW" && echo 0 || echo 1)
check "workflow cleans SSH keys and raw schema dumps" \
    $(grep -q 'Delete backup probe files and SSH key' "$WORKFLOW" && grep -q 'Delete schema dumps and SSH key' "$WORKFLOW" && ! grep -q 'upload-artifact' "$WORKFLOW" && echo 0 || echo 1)

echo
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ]
