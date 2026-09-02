#!/usr/bin/env bash
# Replace ONE local Matcha tenant with its current production data.
#
# This does not clone the rest of the shared database. Cappe, TellUs,
# Oceanlab, other Matcha tenants, and unrelated shared catalogs stay intact.
# Matcha Work / Matcha Ops rows which belong to the selected companies.id are
# included through the live FK graph. Production is opened read-only.
# The selected tenant is copied verbatim; this workflow does not anonymize it.
#
# Usage:
#   ./scripts/pull-tenant-from-prod.sh "Po Coffee Co" --dry-run
#   ./scripts/pull-tenant-from-prod.sh "Po Coffee Co"
#
# Safety:
#   * exact production name or UUID required;
#   * target DSN must be localhost/127.0.0.1;
#   * generated SQL is rehearsed with ROLLBACK before any prompt/apply;
#   * actual apply gets a full local PG15 recovery dump first;
#   * one local transaction replaces only descendant tenant rows;
#   * usage_events and infrastructure bookkeeping remain excluded.
#   * selected-tenant production data is not anonymized.
set -euo pipefail
umask 077

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/server/.env"
PEM="${PEM:-$REPO_ROOT/secrets/roonMT-arm.pem}"
APP_EC2="${APP_EC2:-ec2-user@54.177.107.107}"
PROD_DB_HOST="${PROD_DB_HOST:-13.56.253.173}"
PROD_DB_PORT="${PROD_DB_PORT:-5433}"
LOCAL_TUNNEL_PORT="${LOCAL_TUNNEL_PORT:-5434}"
DEV_CONTAINER="${DEV_CONTAINER:-matcha-postgres}"
DEV_URL="${DEV_DATABASE_URL:-postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha}"
SNAP_DIR="${SNAP_DIR:-$HOME/matcha-dev-snapshots}"

env_val() {
  grep "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' '
}

TENANT=""
DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      awk 'NR == 1 { next } /^set -euo pipefail$/ { exit } { sub(/^# ?/, ""); print }' "$0"
      exit 0
      ;;
    -*) echo "Unknown flag: $arg" >&2; exit 1 ;;
    *)
      [[ -z "$TENANT" ]] || { echo "Pass exactly one tenant name or UUID." >&2; exit 1; }
      TENANT="$arg"
      ;;
  esac
done
[[ -n "$TENANT" ]] || { echo "Usage: $0 <tenant-name-or-uuid> [--dry-run]" >&2; exit 1; }

# Never let a caller repoint the destructive leg at a non-local database.
case "$DEV_URL" in
  postgresql://*@127.0.0.1:*/*|postgresql://*@localhost:*/*) ;;
  *) echo "REFUSING: DEV_DATABASE_URL must target localhost or 127.0.0.1: $DEV_URL" >&2; exit 1 ;;
esac

[[ -f "$PEM" ]] || { echo "SSH key not found: $PEM" >&2; exit 1; }
command -v psql >/dev/null || { echo "psql not found on PATH" >&2; exit 1; }
command -v docker >/dev/null || { echo "docker not found on PATH" >&2; exit 1; }
docker ps --format '{{.Names}}' | grep -qx "$DEV_CONTAINER" || {
  echo "Local container '$DEV_CONTAINER' is not running. Start dev-remote.sh first." >&2
  exit 1
}

PROD_URL="${PROD_DATABASE_URL:-$(env_val PROD_DATABASE_URL)}"
[[ -n "$PROD_URL" ]] || { echo "PROD_DATABASE_URL is missing from server/.env" >&2; exit 1; }

PY="$REPO_ROOT/server/venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3)"
WORK_DIR="$(mktemp -d -t matcha-pull-tenant.XXXXXX)"
SQL_FILE="$WORK_DIR/pull.sql"
SUMMARY_FILE="$WORK_DIR/summary.json"
REHEARSAL_LOG="$WORK_DIR/rehearsal.log"
OPENED_TUNNEL=0

cleanup() {
  rm -rf "$WORK_DIR"
  if [[ "$OPENED_TUNNEL" == "1" ]]; then
    pkill -f "ssh.*${LOCAL_TUNNEL_PORT}:${PROD_DB_HOST}:${PROD_DB_PORT}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

if lsof -n -P -iTCP:"$LOCAL_TUNNEL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Reusing existing listener on localhost:${LOCAL_TUNNEL_PORT}."
else
  echo "Opening read-only production tunnel through $APP_EC2..."
  ssh -i "$PEM" -L "${LOCAL_TUNNEL_PORT}:${PROD_DB_HOST}:${PROD_DB_PORT}" \
    "$APP_EC2" -N -f -o BatchMode=yes -o ConnectTimeout=10 -o ExitOnForwardFailure=yes
  OPENED_TUNNEL=1
  sleep 1
fi

PROD_DATABASE_URL="$PROD_URL" DEV_DATABASE_URL="$DEV_URL" \
"$PY" "$REPO_ROOT/scripts/pull_tenant_from_prod.py" \
  --tenant "$TENANT" \
  --out "$SQL_FILE" \
  --summary-out "$SUMMARY_FILE" \
  --progress

TENANT_NAME="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["tenant_name"])' "$SUMMARY_FILE")"
TENANT_ID="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["tenant_id"])' "$SUMMARY_FILE")"

echo "Rehearsing the exact replacement locally (ROLLBACK)..."
if ! psql "$DEV_URL" -X -v ON_ERROR_STOP=1 -c 'BEGIN;' -f "$SQL_FILE" -c 'ROLLBACK;' \
     >"$REHEARSAL_LOG" 2>&1; then
  tail -n 30 "$REHEARSAL_LOG" >&2
  echo "FAILED: rehearsal rolled back; local data was not changed." >&2
  exit 1
fi
echo "Rehearsal passed; nothing committed."

if [[ "$DRY_RUN" == "1" ]]; then
  echo "Dry run complete for $TENANT_NAME ($TENANT_ID)."
  exit 0
fi

echo
echo "This will replace only local tenant data for: $TENANT_NAME ($TENANT_ID)"
echo "Production stays read-only. Other local tenants/apps remain untouched."
read -r -p "Type 'pull $TENANT_NAME' to continue: " CONFIRM
[[ "$CONFIRM" == "pull $TENANT_NAME" ]] || { echo "Aborted; nothing changed."; exit 1; }

mkdir -p "$SNAP_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SNAPSHOT="$SNAP_DIR/tenant_pre_pull_${TENANT_ID}_${TS}.dump"
echo "Creating local recovery snapshot: $SNAPSHOT"
docker exec "$DEV_CONTAINER" pg_dump -U matcha -d matcha -Fc > "$SNAPSHOT"
[[ -s "$SNAPSHOT" ]] || { echo "Recovery snapshot is empty; refusing to apply." >&2; exit 1; }

echo "Applying replacement to LOCAL dev in one transaction..."
psql "$DEV_URL" -X -v ON_ERROR_STOP=1 --single-transaction -f "$SQL_FILE" >/dev/null
echo "Pulled $TENANT_NAME ($TENANT_ID) from production into local dev."
echo "Recovery snapshot: $SNAPSHOT"
