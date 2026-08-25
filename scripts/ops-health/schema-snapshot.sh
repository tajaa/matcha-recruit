#!/usr/bin/env bash
# Read-only schema snapshots. Never start the shared dev container: a stopped
# local database is an unknown comparison, not a reason for automation to alter it.
set -euo pipefail

MODE="${1:?usage: schema-snapshot.sh local-revisions|prod-revisions|local-dump|prod-dump|local-client-version|prod-client-version}"
DEV_CONTAINER="${DEV_CONTAINER:-matcha-postgres}"
DB_NAME="${DB_NAME:-matcha}"
DB_USER="${DB_USER:-matcha}"
SSH_KEY="${SSH_KEY:-}"
PROD_DB_HOST="${PROD_DB_HOST:-13.56.253.173}"
PROD_DB_USER="${PROD_DB_USER:-ec2-user}"
PROD_CONTAINER="matcha-postgres-prod"
READ_ONLY_OPTIONS="-c default_transaction_read_only=on -c lock_timeout=5000 -c statement_timeout=120000"
REVISION_SQL="SELECT json_build_object('revisions', COALESCE(json_agg(version_num ORDER BY version_num), '[]'::json)) FROM public.alembic_version;"

local_running() {
    docker ps --format '{{.Names}}' | grep -qx "$DEV_CONTAINER"
}

local_psql() {
    local_running || { echo "local dev container '$DEV_CONTAINER' is not running" >&2; exit 1; }
    docker exec -e "PGOPTIONS=$READ_ONLY_OPTIONS" "$DEV_CONTAINER" \
        psql -X --no-psqlrc -v ON_ERROR_STOP=1 -At -U "$DB_USER" -d "$DB_NAME" "$@"
}

local_dump() {
    local_running || { echo "local dev container '$DEV_CONTAINER' is not running" >&2; exit 1; }
    docker exec -e "PGOPTIONS=$READ_ONLY_OPTIONS" "$DEV_CONTAINER" \
        pg_dump --schema-only --quote-all-identifiers --no-owner --no-privileges \
        --no-comments --no-security-labels --no-publications --no-subscriptions \
        --no-tablespaces -U "$DB_USER" -d "$DB_NAME"
}

prod_command() {
    [ -n "$SSH_KEY" ] || { echo "SSH_KEY must point to the production SSH key" >&2; exit 2; }
    ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        "$PROD_DB_USER@$PROD_DB_HOST" "bash -s" -- "$1" <<'REMOTE'
set -euo pipefail
mode="$1"
readonly_options='-c default_transaction_read_only=on -c lock_timeout=5000 -c statement_timeout=120000'
revision_sql="SELECT json_build_object('revisions', COALESCE(json_agg(version_num ORDER BY version_num), '[]'::json)) FROM public.alembic_version;"
case "$mode" in
  revisions)
    sudo -n docker exec -e "PGOPTIONS=$readonly_options" matcha-postgres-prod \
      psql -X --no-psqlrc -v ON_ERROR_STOP=1 -At -U matcha -d matcha -c "$revision_sql"
    ;;
  dump)
    sudo -n docker exec -e "PGOPTIONS=$readonly_options" matcha-postgres-prod \
      pg_dump --schema-only --quote-all-identifiers --no-owner --no-privileges \
      --no-comments --no-security-labels --no-publications --no-subscriptions \
      --no-tablespaces -U matcha -d matcha
    ;;
  client-version)
    sudo -n docker exec matcha-postgres-prod pg_dump --version
    ;;
  *)
    echo "unknown production snapshot mode" >&2
    exit 2
    ;;
esac
REMOTE
}

case "$MODE" in
    local-revisions) local_psql -c "$REVISION_SQL" ;;
    prod-revisions) prod_command revisions ;;
    local-dump) local_dump ;;
    prod-dump) prod_command dump ;;
    local-client-version)
        local_running || { echo "local dev container '$DEV_CONTAINER' is not running" >&2; exit 1; }
        docker exec "$DEV_CONTAINER" pg_dump --version
        ;;
    prod-client-version) prod_command client-version ;;
    *)
        echo "usage: schema-snapshot.sh local-revisions|prod-revisions|local-dump|prod-dump|local-client-version|prod-client-version" >&2
        exit 2
        ;;
esac
