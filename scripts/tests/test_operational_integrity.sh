#!/usr/bin/env bash
# Static safety checks for read-only backup/schema monitoring scripts and workflow.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKUP="$REPO_ROOT/scripts/ops-health/backup-probe.sh"
SCHEMA="$REPO_ROOT/scripts/ops-health/schema-snapshot.sh"
WORKFLOW="$REPO_ROOT/.github/workflows/operational-integrity-checks.yml"
SCHEMA_WORKFLOW="$REPO_ROOT/.github/workflows/schema-drift-checks.yml"
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
    $(grep -q 'downloaded_size.*expected_size' "$BACKUP" && grep -q 'pg_restore --list' "$BACKUP" && grep -q 'pg_restore --exit-on-error --file=/dev/null' "$BACKUP" && echo 0 || echo 1)
check "backup probe removes remote temporary archives" \
    $(grep -q "trap 'rm -f" "$BACKUP" && echo 0 || echo 1)
check "backup probe pins the probe image by digest, never a floating tag" \
    $(grep -qE "PROBE_IMAGE='public\.ecr\.aws/docker/library/postgres@sha256:[0-9a-f]{64}'" "$BACKUP" && echo 0 || echo 1)
check "backup probe pulls the image explicitly and gates pg_restore on the pull" \
    $(grep -qF 'docker pull --quiet "\$probe_image"' "$BACKUP" && grep -q 'image_pull_rc' "$BACKUP" && grep -qF 'if [ "\$image_pull_rc" -eq 0 ]' "$BACKUP" && echo 0 || echo 1)
check "backup integrity distinguishes an unpullable image from a bad restore" \
    $(grep -q 'image_pull_rc' "$REPO_ROOT/scripts/ops-health/backup-integrity.py" && grep -q 'backup probe image could not be pulled' "$REPO_ROOT/scripts/ops-health/backup-integrity.py" && echo 0 || echo 1)

if [ "${OPS_NETWORK_CHECKS:-0}" = 1 ]; then
    PINNED_DIGEST="$(grep -oE 'postgres@sha256:[0-9a-f]{64}' "$BACKUP" | head -1 | cut -d: -f2)"
    check "pinned probe image digest resolves on public.ecr.aws" \
        $(TOK=$(curl -s "https://public.ecr.aws/token/?scope=repository:docker/library/postgres:pull&service=public.ecr.aws" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])' 2>/dev/null); \
          curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOK" \
            -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
            "https://public.ecr.aws/v2/docker/library/postgres/manifests/sha256:$PINNED_DIGEST" | grep -q '^200$' && echo 0 || echo 1)
fi
check "schema probe never starts the shared dev container" \
    $(! grep -qE 'docker (start|run|create)' "$SCHEMA" && echo 0 || echo 1)
check "schema probe uses read-only sessions" \
    $(grep -q 'default_transaction_read_only=on' "$SCHEMA" && echo 0 || echo 1)
check "schema probe targets only live production container" \
    $(grep -q '13.56.253.173' "$SCHEMA" && grep -q 'matcha-postgres-prod' "$SCHEMA" && ! grep -q '3.101.83.217' "$SCHEMA" && echo 0 || echo 1)
check "schema dumps use deterministic read-only schema flags" \
    $(grep -q -- '--schema-only --quote-all-identifiers --no-owner --no-privileges' "$SCHEMA" && grep -q -- '--no-comments --no-security-labels --no-publications --no-subscriptions' "$SCHEMA" && echo 0 || echo 1)
check "backup-integrity workflow cleans up its SSH key" \
    $(grep -q 'Delete backup probe files and SSH key' "$WORKFLOW" && ! grep -q 'upload-artifact' "$WORKFLOW" && echo 0 || echo 1)
check "schema-drift workflow runs on its own cron, decoupled from the backup timer window" \
    $(grep -q "cron: '17 17 \* \* \*'" "$SCHEMA_WORKFLOW" && ! grep -q '^  schema-drift:' "$WORKFLOW" && echo 0 || echo 1)
check "schema-drift workflow guards dumps behind revision drift" \
    $(grep -q "if: steps.compare.outputs.status == 'drift'" "$SCHEMA_WORKFLOW" && echo 0 || echo 1)
check "schema-drift workflow retains revision-only alert when schema diagnostics fail" \
    $(grep -q 'schema-revision-report.md' "$SCHEMA_WORKFLOW" && grep -q 'read-only schema diagnostics failed' "$SCHEMA_WORKFLOW" && echo 0 || echo 1)
check "schema-drift workflow cleans SSH keys and raw schema dumps" \
    $(grep -q 'Delete schema dumps and SSH key' "$SCHEMA_WORKFLOW" && ! grep -q 'upload-artifact' "$SCHEMA_WORKFLOW" && echo 0 || echo 1)

echo
echo "----------------------------------------"
echo "PASS: $PASS  FAIL: $FAIL"
[ "$FAIL" -eq 0 ]
