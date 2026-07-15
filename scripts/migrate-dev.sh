#!/usr/bin/env bash
# Migrate the LOCAL dev DB (matcha-postgres container on localhost:5432).
# The old EC2 dev Postgres was retired; this targets the local pgvector/pg15
# container that dev-remote.sh manages. Mirror of migrate-prod.sh so the schema
# workflow stays symmetric:
#   author migration -> ./scripts/migrate-dev.sh -> test -> ./scripts/migrate-prod.sh
# Override the target with DEV_DATABASE_URL (env or server/.env).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCAL_PORT=5432

DEV_DATABASE_URL="${DEV_DATABASE_URL:-}"
if [[ -z "$DEV_DATABASE_URL" ]]; then
  ENV_FILE="$REPO_ROOT/server/.env"
  if [[ -f "$ENV_FILE" ]] && grep -q '^DEV_DATABASE_URL' "$ENV_FILE"; then
    DEV_DATABASE_URL=$(grep '^DEV_DATABASE_URL' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
  else
    DEV_DATABASE_URL="postgresql://matcha:matcha_dev@localhost:${LOCAL_PORT}/matcha"
  fi
fi

# Ensure the local dev Postgres container is up (created/started by dev-remote.sh).
if ! docker ps --format '{{.Names}}' | grep -q '^matcha-postgres$'; then
  if docker ps -a --format '{{.Names}}' | grep -q '^matcha-postgres$'; then
    echo "Starting local matcha-postgres container..."
    docker start matcha-postgres
  else
    echo "Error: local matcha-postgres container not found. Run ./scripts/dev-remote.sh first (it creates it)." >&2
    exit 1
  fi
  for _ in $(seq 1 30); do
    docker exec matcha-postgres pg_isready -U matcha -d matcha >/dev/null 2>&1 && break
    sleep 1
  done
fi

echo "Connecting as: $(echo "$DEV_DATABASE_URL" | sed 's|://[^:]*:[^@]*@|://***:***@|')"

# Dev is disposable, so this warns rather than blocks — but it warns, because
# "dev ran a different version of the same revision than prod did" is exactly how
# jparent01 left dev with 222 stale canonical_key rows that prod does not have.
# migrate-prod.sh makes this a hard gate.
DIRTY="$(cd "$REPO_ROOT" && git status --porcelain -- server/alembic 2>/dev/null || true)"
if [[ -n "$DIRTY" ]]; then
  echo "!! Uncommitted migrations — dev is about to run code git does not have:"
  echo "$DIRTY" | sed 's/^/     /'
  echo "!! Commit before running migrate-prod.sh, or the two DBs run different bytes."
fi

echo "Running Alembic upgrade on dev..."
cd "$REPO_ROOT/server"
# `heads` (plural): the history carries several permanent branch heads (no branch
# labels), so `upgrade head` singular is ambiguous.
DATABASE_URL="$DEV_DATABASE_URL" ./venv/bin/alembic upgrade heads
echo "Done."

echo
echo "Tip: MIGRATE_REHEARSAL=1 runs a migration for real and rolls it back."
