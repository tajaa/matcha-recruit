#!/usr/bin/env bash
# Interactive psql into PROD for data review — READ-ONLY by default.
#
# Opens the same SSH tunnel migrate-prod.sh uses and runs psql LOCALLY through
# it, so your credentials never leave your laptop (nothing is sent to the remote
# process list). psql must be installed locally.
#
#   Default: matcha-prod RDS, tunnelled via the app EC2:
#     localhost:5434 -> app EC2 (54.177.107.107) -> matcha-prod RDS :5432
#   --legacy: the OLD prod container instead (matcha-postgres-prod :5433 on the
#     DB EC2) — live until cutover, frozen after.
#
# Reads PROD_DATABASE_URL / PROD_LEGACY_DATABASE_URL from server/.env
# (RDS expects sslmode=require — rds.force_ssl=1 rejects plaintext).
#
# Flags:
#   --legacy   target the old :5433 container (DB EC2) instead of RDS
#   --write    allow writes (default session is default_transaction_read_only=on)
# Any other args are passed straight to psql, e.g.:
#   ./scripts/prod-psql.sh -c "SELECT count(*) FROM companies;"
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="$REPO_ROOT/secrets/roonMT-arm.pem"
ENV_FILE="$REPO_ROOT/server/.env"

APP_EC2="ec2-user@54.177.107.107"
DB_EC2="ec2-user@3.101.83.217"
RDS_HOST="matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com"

env_val() { grep "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' '; }

LEGACY=0
WRITE=0
PSQL_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --legacy) LEGACY=1 ;;
    --write)  WRITE=1 ;;
    *)        PSQL_ARGS+=("$arg") ;;
  esac
done

if [[ "$LEGACY" == "1" ]]; then
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

# Reuse an existing listener on the local port if one is already up; otherwise
# open our own tunnel and tear it down on exit.
if lsof -n -P -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Reusing existing listener on localhost:${LOCAL_PORT}."
else
  echo "Opening SSH tunnel ${JUMP} (${FORWARD})..."
  ssh -i "$PEM" -L "$FORWARD" "$JUMP" -N -f -o ExitOnForwardFailure=yes
  trap 'pkill -f "ssh.*${FORWARD}" 2>/dev/null; exit' EXIT INT TERM
  sleep 1
fi

if [[ "$WRITE" == "1" ]]; then
  echo "⚠️  WRITE mode — this is LIVE PROD. Mutations will persist."
else
  echo "Read-only session (pass --write to allow mutations)."
  export PGOPTIONS="-c default_transaction_read_only=on"
fi

if [[ ${#PSQL_ARGS[@]} -gt 0 ]]; then
  psql "$URL" "${PSQL_ARGS[@]}"
else
  psql "$URL"
fi
