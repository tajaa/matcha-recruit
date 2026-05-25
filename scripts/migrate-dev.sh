#!/usr/bin/env bash
# Migrate the DEV DB (matcha-postgres:5432) via SSH tunnel.
# Mirror of migrate-prod.sh so the schema workflow is symmetric:
#   author migration -> ./scripts/migrate-dev.sh -> test -> ./scripts/migrate-prod.sh
# Reads DEV_DATABASE_URL from server/.env, or falls back to the standard dev URL.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="$REPO_ROOT/roonMT-arm.pem"
EC2="ec2-user@3.101.83.217"
LOCAL_PORT=5432

if [[ -z "${DEV_DATABASE_URL:-}" ]]; then
  ENV_FILE="$REPO_ROOT/server/.env"
  if [[ -f "$ENV_FILE" ]] && grep -q '^DEV_DATABASE_URL' "$ENV_FILE"; then
    DEV_DATABASE_URL=$(grep '^DEV_DATABASE_URL' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
  else
    DEV_DATABASE_URL="postgresql://matcha:matcha_dev@localhost:${LOCAL_PORT}/matcha"
  fi
fi

echo "Connecting as: $(echo "$DEV_DATABASE_URL" | sed 's|://[^:]*:[^@]*@|://***:***@|')"

# Reuse an existing tunnel (e.g. from dev-remote.sh) if :5432 is already open;
# otherwise open our own and tear it down on exit.
if lsof -n -P -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Reusing existing listener on localhost:${LOCAL_PORT} (dev-remote tunnel?)."
else
  echo "Opening SSH tunnel ${EC2}:5432 -> localhost:${LOCAL_PORT}..."
  ssh -i "$PEM" -L "${LOCAL_PORT}:localhost:5432" "$EC2" -N -f -o ExitOnForwardFailure=yes
  trap 'pkill -f "ssh.*${LOCAL_PORT}:localhost:5432" 2>/dev/null; exit' EXIT INT TERM
  sleep 1
fi

echo "Running Alembic upgrade on dev..."
cd "$REPO_ROOT/server"
DATABASE_URL="$DEV_DATABASE_URL" ./venv/bin/alembic upgrade head
echo "Done."
