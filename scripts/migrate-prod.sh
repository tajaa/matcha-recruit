#!/usr/bin/env bash
# Migrate PROD via SSH tunnel.
#
# Default target: the matcha-prod RDS instance. RDS lives in the APP VPC and is
# reachable only from the app EC2 (the DB EC2 is a different VPC and cannot
# route to it), so the tunnel jumps through the app box:
#   localhost:5434 -> app EC2 (54.177.107.107) -> matcha-prod RDS :5432
# Reads PROD_DATABASE_URL from server/.env (expects localhost:5434 +
# sslmode=require — rds.force_ssl=1 rejects plaintext even through the tunnel).
#
# --legacy: target the OLD prod container instead (matcha-postgres-prod :5433
# on the DB EC2) — the live DB until cutover, a frozen copy afterwards. Reads
# PROD_LEGACY_DATABASE_URL. Pre-cutover, a migration that must reach live prod
# goes here; run BOTH paths if you migrate before cutover so RDS doesn't drift.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="$REPO_ROOT/roonMT-arm.pem"
ENV_FILE="$REPO_ROOT/server/.env"

APP_EC2="ec2-user@54.177.107.107"
DB_EC2="ec2-user@3.101.83.217"
RDS_HOST="matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com"

env_val() { grep "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' '; }

if [[ "${1:-}" == "--legacy" ]]; then
  LABEL="LEGACY prod container (matcha-postgres-prod :5433 on DB EC2)"
  LOCAL_PORT=5433
  JUMP="$DB_EC2"
  FORWARD="${LOCAL_PORT}:localhost:5433"
  URL="${PROD_LEGACY_DATABASE_URL:-$(env_val PROD_LEGACY_DATABASE_URL)}"
  : "${URL:?Add PROD_LEGACY_DATABASE_URL=postgresql://user:pass@localhost:5433/matcha to server/.env}"
else
  LABEL="RDS matcha-prod (via app EC2)"
  LOCAL_PORT=5434
  JUMP="$APP_EC2"
  FORWARD="${LOCAL_PORT}:${RDS_HOST}:5432"
  URL="${PROD_DATABASE_URL:-$(env_val PROD_DATABASE_URL)}"
  : "${URL:?Add PROD_DATABASE_URL=postgresql://matcha:pass@localhost:5434/matcha?sslmode=require to server/.env}"
fi

echo "Target: $LABEL"
echo "Connecting as: $(echo "$URL" | sed 's|://[^:]*:[^@]*@|://***:***@|')"

# Reuse an existing listener on the local port if one is already up;
# otherwise open our own tunnel and tear it down on exit.
if lsof -n -P -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Reusing existing listener on localhost:${LOCAL_PORT}."
else
  echo "Opening SSH tunnel ${JUMP} (${FORWARD})..."
  ssh -i "$PEM" -L "$FORWARD" "$JUMP" -N -f -o ExitOnForwardFailure=yes
  trap 'pkill -f "ssh.*${FORWARD}" 2>/dev/null; exit' EXIT INT TERM
  sleep 1
fi

echo "Running Alembic upgrade on prod..."
cd "$REPO_ROOT/server"
# `heads` (plural): two permanent branch heads (matcha + cappe, no branch
# labels) make `upgrade head` ambiguous.
DATABASE_URL="$URL" ./venv/bin/alembic upgrade heads
echo "Done."
