#!/usr/bin/env bash
# Migrate prod DB (matcha-postgres-prod:5433) via SSH tunnel.
# Reads PROD_DATABASE_URL from server/.env (or from env if already set).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="$REPO_ROOT/roonMT-arm.pem"
EC2="ec2-user@3.101.83.217"
LOCAL_PORT=5433

# Load PROD_DATABASE_URL from server/.env if not already in environment
if [[ -z "${PROD_DATABASE_URL:-}" ]]; then
  ENV_FILE="$REPO_ROOT/server/.env"
  if [[ -f "$ENV_FILE" ]]; then
    PROD_DATABASE_URL=$(grep '^PROD_DATABASE_URL' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ')
  fi
fi

: "${PROD_DATABASE_URL:?Add PROD_DATABASE_URL=postgresql://user:pass@localhost:5433/matcha to server/.env}"

echo "Connecting as: $(echo "$PROD_DATABASE_URL" | sed 's|://[^:]*:[^@]*@|://***:***@|')"

# Open tunnel EC2:5433 → localhost:5433, kill on exit
ssh -i "$PEM" -L "${LOCAL_PORT}:localhost:5433" "$EC2" -N -f -o ExitOnForwardFailure=yes
trap 'pkill -f "ssh.*${LOCAL_PORT}:localhost:5433" 2>/dev/null; exit' EXIT INT TERM
sleep 1

echo "Running Alembic upgrade on prod..."
cd "$REPO_ROOT/server"
DATABASE_URL="$PROD_DATABASE_URL" ./venv/bin/alembic upgrade head
echo "Done."
