#!/usr/bin/env bash
# refresh-dev-from-prod.sh
# Replace the DEV database with an ANONYMIZED clone of PRODUCTION.
#
# Both Postgres instances live as containers on the SAME DB EC2 (3.101.83.217):
#   prod  = matcha-postgres-prod  (:5433)  -- READ ONLY here, never mutated
#   dev   = matcha-postgres       (:5432)  -- destroyed + rebuilt
#
# The prod->dev copy happens host-side (docker exec | docker exec) so no
# customer data leaves the EC2 box. Strategy is clone-into-staging then
# rename-swap, so a failed/aborted clone leaves the existing dev DB intact.
# A gzipped snapshot of dev is taken first for belt-and-suspenders recovery.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="${PEM:-$REPO_ROOT/roonMT-arm.pem}"
DB_EC2="${DB_EC2:-ec2-user@3.101.83.217}"

PROD_CONTAINER="${PROD_CONTAINER:-matcha-postgres-prod}"   # source (read-only)
DEV_CONTAINER="${DEV_CONTAINER:-matcha-postgres}"          # target (rebuilt)
DB_NAME="${DB_NAME:-matcha}"
DB_USER="${DB_USER:-matcha}"
DEV_LOGIN_PASSWORD="${DEV_LOGIN_PASSWORD:-devpass123}"     # password for every dev user after refresh
ANON_SQL="$REPO_ROOT/scripts/sql/anonymize_dev.sql"
KEEP_OLD=1   # how many matcha_old_* DBs to retain on the host

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'

# --- Safety rails (local) ---------------------------------------------------
# Destructive ops must NEVER target the prod container.
if [[ "$DEV_CONTAINER" == *prod* ]]; then
    echo "${RED}REFUSING: DEV_CONTAINER='$DEV_CONTAINER' looks like production.${NC}"; exit 1
fi
[[ -f "$PEM" ]]      || { echo "${RED}SSH key not found: $PEM${NC}"; exit 1; }
[[ -f "$ANON_SQL" ]] || { echo "${RED}Anonymizer not found: $ANON_SQL${NC}"; exit 1; }

PY="$REPO_ROOT/server/venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3 || true)"
[[ -n "$PY" ]] || { echo "${RED}No python found to generate the dev password hash.${NC}"; exit 1; }

# Warn if a local dev stack is holding connections to dev :5432 (blocks the swap).
if lsof -n -P -iTCP:5432 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "${YELLOW}Warning: something is listening on localhost:5432 (dev-remote tunnel?).${NC}"
    echo "${YELLOW}A running dev backend reconnects to the dev DB and can block the rename-swap.${NC}"
    echo "${YELLOW}Recommend: ./scripts/dev-remote.sh stop  before continuing.${NC}"
fi

DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

cat <<EOF
${YELLOW}This will REPLACE the dev database with an anonymized copy of PRODUCTION.${NC}
  source (prod, read-only): $DB_EC2  ->  $PROD_CONTAINER : $DB_NAME
  target (dev,  REBUILT)  : $DB_EC2  ->  $DEV_CONTAINER  : $DB_NAME
  every dev user password becomes: $DEV_LOGIN_PASSWORD
  dry run (clone+anonymize into staging, NO swap): $DRY_RUN
EOF
read -r -p "Type 'refresh-dev' to proceed: " CONFIRM
[[ "$CONFIRM" == "refresh-dev" ]] || { echo "Aborted."; exit 0; }

# --- Render the anonymizer with a real bcrypt(cost 10) hash -----------------
echo "${YELLOW}Generating dev password hash (bcrypt, matching app/core/services/auth.py)...${NC}"
DEV_PW_HASH="$("$PY" - "$DEV_LOGIN_PASSWORD" <<'PY'
import sys, bcrypt
print(bcrypt.hashpw(sys.argv[1].encode()[:72], bcrypt.gensalt(rounds=10)).decode())
PY
)"
[[ "$DEV_PW_HASH" == \$2* ]] || { echo "${RED}bcrypt hash generation failed.${NC}"; exit 1; }

RENDERED="$(mktemp -t anonymize_dev.XXXXXX.sql)"
REMOTE_SCRIPT="$(mktemp -t refresh_dev_remote.XXXXXX.sh)"
trap 'rm -f "$RENDERED" "$REMOTE_SCRIPT"' EXIT
sed "s|__DEV_PW_HASH__|$DEV_PW_HASH|g" "$ANON_SQL" > "$RENDERED"

# Remote driver shipped as a FILE (not piped to `bash -s`): if it were on stdin,
# the first `docker exec -i` would swallow the rest of the script as its stdin.
cat > "$REMOTE_SCRIPT" <<'REMOTE'
set -euo pipefail
TS=$(date +%F_%H-%M-%S)
SNAP_DIR=/home/ec2-user/dev-snapshots
ddev()  { docker exec -i "$DEV"  psql -U "$U" -v ON_ERROR_STOP=1 "$@"; }   # stdin free (script is a file)

docker ps --format '{{.Names}}' | grep -qx "$PROD" || { echo "prod container $PROD not running"; exit 1; }
docker ps --format '{{.Names}}' | grep -qx "$DEV"  || { echo "dev container $DEV not running";  exit 1; }

echo "[1/6] Pre-refresh dev snapshot..."
mkdir -p "$SNAP_DIR"
docker exec "$DEV" pg_dump -U "$U" "$DB" | gzip > "$SNAP_DIR/dev_pre_refresh_$TS.sql.gz"
echo "      $(du -h "$SNAP_DIR/dev_pre_refresh_$TS.sql.gz" | cut -f1) -> $SNAP_DIR/dev_pre_refresh_$TS.sql.gz"
ls -1t "$SNAP_DIR"/dev_pre_refresh_*.sql.gz | tail -n +6 | xargs -r rm -f   # keep last 5

echo "[2/6] Staging fresh DB ${DB}_new..."
ddev -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB}_new' AND pid<>pg_backend_pid();" >/dev/null
ddev -d postgres -c "DROP DATABASE IF EXISTS ${DB}_new;"
ddev -d postgres -c "CREATE DATABASE ${DB}_new OWNER $U;"

echo "[3/6] Cloning prod -> ${DB}_new (host-local pipe, no egress)..."
docker exec "$PROD" pg_dump -U "$U" -Fc "$DB" \
  | docker exec -i "$DEV" pg_restore -U "$U" -d "${DB}_new" --no-owner --no-privileges --exit-on-error

echo "[4/6] Anonymizing ${DB}_new..."
# Read the SQL from the HOST file via stdin: `-f /path` would look inside the
# container, where the scp'd file doesn't exist.
docker exec -i "$DEV" psql -U "$U" -d "${DB}_new" -v ON_ERROR_STOP=1 < /tmp/anonymize_dev.sql

if [ "$DRY_RUN" = "true" ]; then
    echo "[5/6] DRY RUN — leaving anonymized clone as ${DB}_new, NOT swapping."
    echo "      Inspect: docker exec -it $DEV psql -U $U -d ${DB}_new"
    echo "[6/6] Skipped swap."
    exit 0
fi

echo "[5/6] Swapping ${DB} <- ${DB}_new ..."
# Double-quote the timestamped name: $TS has hyphens/colons, illegal in an
# unquoted SQL identifier. matcha / matcha_new are bare-identifier-safe.
ddev -d postgres <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('${DB}','${DB}_new') AND pid<>pg_backend_pid();
ALTER DATABASE ${DB} RENAME TO "${DB}_old_${TS}";
ALTER DATABASE ${DB}_new RENAME TO ${DB};
SQL
for old in $(ddev -tA -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE '${DB}_old_%' ORDER BY datname DESC OFFSET ${KEEP_OLD};"); do
    echo "      dropping stale $old"
    ddev -d postgres -c "DROP DATABASE IF EXISTS \"$old\";"
done

echo "[6/6] Verifying live dev DB..."
ddev -tA -d "$DB" -c "SELECT 'companies='||count(*) FROM companies UNION ALL SELECT 'users='||count(*) FROM users;"
LEAK=$(ddev -tA -d "$DB" -c "SELECT count(*) FROM users WHERE email NOT LIKE '%@example.com';")
echo "      non-reserved user emails (must be 0): $LEAK"
echo "      sample logins:"
ddev -tA -d "$DB" -c "SELECT '        '||role||'  ->  '||email FROM users WHERE role IN ('admin','client','individual') ORDER BY role LIMIT 6;"
[ "$LEAK" = "0" ] || { echo "PII LEAK DETECTED — anonymizer missed rows."; exit 1; }
REMOTE

scp -q -i "$PEM" "$RENDERED" "$DB_EC2:/tmp/anonymize_dev.sql"
scp -q -i "$PEM" "$REMOTE_SCRIPT" "$DB_EC2:/tmp/refresh_dev_remote.sh"

# -n: don't let our local stdin (the confirm pipe) leak into the remote command.
ssh -n -i "$PEM" "$DB_EC2" \
    "PROD='$PROD_CONTAINER' DEV='$DEV_CONTAINER' DB='$DB_NAME' U='$DB_USER' DRY_RUN='$DRY_RUN' KEEP_OLD='$KEEP_OLD' bash /tmp/refresh_dev_remote.sh; rc=\$?; rm -f /tmp/refresh_dev_remote.sh /tmp/anonymize_dev.sql; exit \$rc"

echo
if [[ "$DRY_RUN" == "true" ]]; then
    echo "${GREEN}Dry run complete. Review matcha_new on the host, then re-run without --dry-run.${NC}"
else
    echo "${GREEN}Dev DB refreshed from prod (anonymized).${NC}"
    echo "${GREEN}Log in to local dev with any listed email + password: ${DEV_LOGIN_PASSWORD}${NC}"
    echo "Restart your stack: ./scripts/dev-remote.sh"
fi
