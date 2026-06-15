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
echo "Running Alembic upgrade on dev..."
cd "$REPO_ROOT/server"
DATABASE_URL="$DEV_DATABASE_URL" ./venv/bin/alembic upgrade head
echo "Done."
