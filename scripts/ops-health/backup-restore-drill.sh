#!/usr/bin/env bash
# Full restore drill of the newest prod logical backup, run ON the app EC2.
#
# operational-integrity-checks.yml only proves the newest dump is readable
# (`pg_restore --list`). This proves it RESTORES: download it, load it into a
# throwaway pgvector/pg15 container, count what came back, tear it down. It is
# the only recurring test of the one recovery path prod has (no RDS PITR, no
# EBS snapshot policy). Read-only against S3; never touches the live database.
#
# Emits one JSON object on stdout. Non-zero exit = the drill itself could not
# run; a completed drill that restored badly exits 0 with status=unhealthy so
# the workflow can file the report before failing.
set -euo pipefail

SSH_KEY="${SSH_KEY:?SSH_KEY must point to the production SSH key}"
PROD_HOST="${PROD_HOST:-54.177.107.107}"
PROD_USER="${PROD_USER:-ec2-user}"
BUCKET="matcha-recruit-backups"
PREFIX="postgres-selfhosted/"
# pgvector/pgvector:pg15 (prod's dumps contain `CREATE EXTENSION vector`,
# which stock postgres:15 cannot restore). Pinned to the multi-arch index
# digest that tag resolved to on 2026-09-07; bump deliberately and confirm the
# new digest pulls before committing it (see backup-probe.sh for why).
DRILL_IMAGE='docker.io/pgvector/pgvector@sha256:a947c45cdc5906a1bc951f20a8709e321256343ee0f251e4ae00b5e7def4e6da'
# Hard floors: a "successful" restore that produced fewer than this many
# tables or no companies rows is a broken dump, not a healthy one.
MIN_TABLES="${MIN_TABLES:-150}"

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$PROD_USER@$PROD_HOST" "bash -s" -- "$BUCKET" "$PREFIX" "$DRILL_IMAGE" "$MIN_TABLES" <<'REMOTE'
set -euo pipefail
bucket="$1"; prefix="$2"; image="$3"; min_tables="$4"

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
name="matcha-restore-drill-$$"
dump_file="$(mktemp /tmp/matcha-restore-drill.XXXXXX.dump)"
chmod 600 "$dump_file"

cleanup() {
    docker rm -f "$name" >/dev/null 2>&1 || true
    rm -f "$dump_file"
}
trap cleanup EXIT

emit() {
    # $1 status, $2 key, $3 size, $4 tables, $5 companies, $6 revisions json, $7 restore_rc, $8 note
    printf '{"status":"%s","key":"%s","size_bytes":%s,"tables":%s,"companies":%s,"alembic_revisions":%s,"restore_rc":%s,"image":"%s","started_at":"%s","finished_at":"%s","note":"%s"}\n' \
        "$1" "$2" "${3:-0}" "${4:-0}" "${5:-0}" "${6:-[]}" "${7:--1}" "$image" "$started_at" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$8"
}

key="$(aws s3api list-objects-v2 --bucket "$bucket" --prefix "$prefix" \
    --query 'sort_by(Contents[?ends_with(Key, `.dump`)], &LastModified)[-1].Key' --output text)"
if [ -z "$key" ] || [ "$key" = "None" ]; then
    emit unhealthy "" 0 0 0 "[]" -1 "no .dump objects under s3://$bucket/$prefix"
    exit 0
fi

aws s3 cp "s3://$bucket/$key" "$dump_file" --only-show-errors
size="$(wc -c < "$dump_file" | tr -d '[:space:]')"

if ! docker image inspect "$image" >/dev/null 2>&1; then
    docker pull -q "$image" >/dev/null
fi

# Memory-capped and on the default bridge only: this must never compete with
# the live backend for the host, and nothing else should be able to reach it.
docker run -d --name "$name" --memory 1g --memory-swap 1g \
    -e POSTGRES_USER=matcha -e POSTGRES_PASSWORD=drill -e POSTGRES_DB=matcha \
    "$image" >/dev/null

for _ in $(seq 1 60); do
    if docker exec "$name" pg_isready -U matcha -d matcha >/dev/null 2>&1; then break; fi
    sleep 1
done
docker exec "$name" pg_isready -U matcha -d matcha >/dev/null

set +e
docker exec -i "$name" pg_restore --no-owner --no-privileges --exit-on-error \
    -U matcha -d matcha < "$dump_file" > /tmp/matcha-restore-drill.log 2>&1
restore_rc=$?
set -e

q() { docker exec "$name" psql -X -At -U matcha -d matcha -c "$1"; }
tables="$(q "SELECT count(*) FROM pg_tables WHERE schemaname='public'" 2>/dev/null || echo 0)"
companies="$(q "SELECT count(*) FROM companies" 2>/dev/null || echo 0)"
revisions="$(q "SELECT COALESCE(json_agg(version_num ORDER BY version_num), '[]'::json) FROM alembic_version" 2>/dev/null || echo '[]')"

status=healthy
note="restored $key"
if [ "$restore_rc" -ne 0 ]; then
    status=unhealthy
    note="pg_restore exited $restore_rc: $(tail -n 3 /tmp/matcha-restore-drill.log | tr -d '"' | tr '\n' ' ')"
elif [ "$tables" -lt "$min_tables" ]; then
    status=unhealthy
    note="only $tables public tables restored (floor $min_tables)"
elif [ "$companies" -lt 1 ]; then
    status=unhealthy
    note="companies table restored empty"
elif [ "$revisions" = "[]" ]; then
    status=unhealthy
    note="alembic_version restored empty"
fi
rm -f /tmp/matcha-restore-drill.log

emit "$status" "$key" "$size" "$tables" "$companies" "$revisions" "$restore_rc" "$note"
REMOTE
