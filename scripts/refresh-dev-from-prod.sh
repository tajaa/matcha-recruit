#!/usr/bin/env bash
# refresh-dev-from-prod.sh
# Replace the DEV database with an ANONYMIZED clone of PRODUCTION.
#
# PROD = the matcha-prod RDS instance (app VPC). It is reachable ONLY from the
# app EC2 (54.177.107.107) — the DB EC2 is a different VPC and cannot route to
# it. DEV = the matcha-postgres container (:5432) on the DB EC2 (3.101.83.217).
#
# Copy path: pg_dump runs on the APP EC2 (PG16 client, dumps the PG15 RDS,
# read-only) and streams through this laptop into a dump file on the DB EC2,
# then restores into a staging DB inside the dev container. Rename-swap at the
# end, so a failed/aborted clone leaves the existing dev DB intact. A gzipped
# snapshot of dev is taken first for belt-and-suspenders recovery.
# NOTE: the dump transits this laptop (the two EC2s have no SSH trust). Fine
# pre-customer; revisit once real PII exists.
#
# --legacy-source: clone from the OLD prod container (matcha-postgres-prod
# :5433 on the DB EC2, host-side pipe like the original flow) — the live DB
# until cutover, frozen afterwards.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="${PEM:-$REPO_ROOT/roonMT-arm.pem}"
DB_EC2="${DB_EC2:-ec2-user@3.101.83.217}"
APP_EC2="${APP_EC2:-ec2-user@54.177.107.107}"
RDS_HOST="${RDS_HOST:-matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com}"

PROD_CONTAINER="${PROD_CONTAINER:-matcha-postgres-prod}"   # legacy source (read-only)
DEV_CONTAINER="${DEV_CONTAINER:-matcha-postgres}"          # target (rebuilt)
DB_NAME="${DB_NAME:-matcha}"
DB_USER="${DB_USER:-matcha}"
DEV_LOGIN_PASSWORD="${DEV_LOGIN_PASSWORD:-devpass123}"     # password for every NON-preserved dev user
# Emails to PRESERVE through anonymization (the dev owner's own accounts): they
# keep their REAL email + REAL password so you can sign into dev as yourself
# rather than being gated to anonymized test users. Comma-separated. Falls back
# to a DEV_PRESERVE_EMAILS line in server/.env so you set it once.
DEV_PRESERVE_EMAILS="${DEV_PRESERVE_EMAILS:-}"
if [[ -z "$DEV_PRESERVE_EMAILS" && -f "$REPO_ROOT/server/.env" ]]; then
    DEV_PRESERVE_EMAILS="$(sed -n 's/^DEV_PRESERVE_EMAILS=//p' "$REPO_ROOT/server/.env" | head -1 | tr -d "\"'")"
fi

# Turn anonymization OFF entirely: clone prod -> dev verbatim (real emails +
# passwords, every account usable, no allowlist to maintain). Pre-customer
# convenience — UNSET it (or =0) once real customer data exists so dev goes back
# to scrubbed. Env var or a SKIP_ANONYMIZE line in server/.env.
SKIP_ANONYMIZE="${SKIP_ANONYMIZE:-}"
if [[ -z "$SKIP_ANONYMIZE" && -f "$REPO_ROOT/server/.env" ]]; then
    SKIP_ANONYMIZE="$(sed -n 's/^SKIP_ANONYMIZE=//p' "$REPO_ROOT/server/.env" | head -1 | tr -d "\"'")"
fi
case "$(echo "${SKIP_ANONYMIZE:-}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) SKIP_ANON=true;;
    *)             SKIP_ANON=false;;
esac

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
SOURCE="rds"
for arg in "$@"; do
    case "$arg" in
        --dry-run)       DRY_RUN=true;;
        --legacy-source) SOURCE="container";;
        *) echo "${RED}Unknown arg: $arg${NC} (use --dry-run / --legacy-source)"; exit 1;;
    esac
done

# RDS creds come from PROD_DATABASE_URL in server/.env (the laptop-tunnel form;
# only the password is reused here — host is the real endpoint, used from the
# app EC2 which is the only box that can route to RDS).
RDS_PW=""
if [[ "$SOURCE" == "rds" ]]; then
    RDS_URL="$(sed -n 's/^PROD_DATABASE_URL=//p' "$REPO_ROOT/server/.env" | head -1 | tr -d "\"'")"
    RDS_PW="$(printf '%s' "$RDS_URL" | sed -nE 's#^[a-z+]+://[^:/@]+:([^@]*)@.*#\1#p')"
    [[ -n "$RDS_PW" ]] || { echo "${RED}Could not parse password from PROD_DATABASE_URL in server/.env${NC}"; exit 1; }
fi

if [[ "$SKIP_ANON" == true ]]; then
    ANON_STATUS="${RED}OFF — dev becomes a FULL, UNSCRUBBED copy of prod (real emails/passwords/PII)${NC}"
else
    ANON_STATUS="on (PII scrubbed; preserve list keeps your real logins)"
fi

if [[ "$SOURCE" == "rds" ]]; then
    SRC_DESC="RDS $RDS_HOST : $DB_NAME (dumped on $APP_EC2)"
else
    SRC_DESC="$DB_EC2 -> $PROD_CONTAINER : $DB_NAME (LEGACY container)"
fi

cat <<EOF
${YELLOW}This will REPLACE the dev database with a copy of PRODUCTION.${NC}
  source (prod, read-only): $SRC_DESC
  target (dev,  REBUILT)  : $DB_EC2  ->  $DEV_CONTAINER  : $DB_NAME
  anonymize PII: $ANON_STATUS
  non-preserved dev user password becomes: $DEV_LOGIN_PASSWORD
  preserved real logins (keep real email + password): ${DEV_PRESERVE_EMAILS:-(none)}
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

# Build the SQL allowlist literal from DEV_PRESERVE_EMAILS: 'a@x.com','b@y.com'.
# Empty => "" => ARRAY[]::text[] in the SQL => every user scrubbed (default).
PRESERVE_SQL=""
if [[ -n "$DEV_PRESERVE_EMAILS" ]]; then
    IFS=',' read -ra _PE <<< "$DEV_PRESERVE_EMAILS"
    for _e in "${_PE[@]}"; do
        _e="$(echo "$_e" | tr '[:upper:]' '[:lower:]' | xargs)"   # trim + lowercase
        [[ -z "$_e" ]] && continue
        [[ -n "$PRESERVE_SQL" ]] && PRESERVE_SQL+=","
        PRESERVE_SQL+="'$_e'"
    done
fi

RENDERED="$(mktemp -t anonymize_dev.XXXXXX.sql)"
REMOTE_SCRIPT="$(mktemp -t refresh_dev_remote.XXXXXX.sh)"
trap 'rm -f "$RENDERED" "$REMOTE_SCRIPT"' EXIT
sed -e "s|__DEV_PW_HASH__|$DEV_PW_HASH|g" \
    -e "s|__PRESERVE_EMAILS__|$PRESERVE_SQL|g" "$ANON_SQL" > "$RENDERED"

# Remote driver shipped as a FILE (not piped to `bash -s`): if it were on stdin,
# the first `docker exec -i` would swallow the rest of the script as its stdin.
cat > "$REMOTE_SCRIPT" <<'REMOTE'
set -euo pipefail
TS=$(date +%F_%H-%M-%S)
SNAP_DIR=/home/ec2-user/dev-snapshots
ddev()  { docker exec -i "$DEV"  psql -U "$U" -v ON_ERROR_STOP=1 "$@"; }   # stdin free (script is a file)

if [ "$SOURCE" = "container" ]; then
    docker ps --format '{{.Names}}' | grep -qx "$PROD" || { echo "prod container $PROD not running"; exit 1; }
else
    [ -s /tmp/prod_rds.dump ] || { echo "missing/empty /tmp/prod_rds.dump (RDS dump stage failed?)"; exit 1; }
fi
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

if [ "$SOURCE" = "container" ]; then
    echo "[3/6] Cloning legacy prod container -> ${DB}_new (host-local pipe)..."
    docker exec "$PROD" pg_dump -U "$U" -Fc "$DB" \
      | docker exec -i "$DEV" pg_restore -U "$U" -d "${DB}_new" --no-owner --no-privileges --exit-on-error
else
    echo "[3/6] Restoring staged RDS dump -> ${DB}_new ($(du -h /tmp/prod_rds.dump | cut -f1))..."
    docker exec -i "$DEV" pg_restore -U "$U" -d "${DB}_new" --no-owner --no-privileges --exit-on-error < /tmp/prod_rds.dump
    rm -f /tmp/prod_rds.dump
fi

if [ "${SKIP_ANON:-false}" = "true" ]; then
    echo "[4/6] SKIPPING anonymization — dev will be a FULL UNSCRUBBED prod mirror (SKIP_ANONYMIZE set)."
else
    echo "[4/6] Anonymizing ${DB}_new..."
    # Read the SQL from the HOST file via stdin: `-f /path` would look inside the
    # container, where the scp'd file doesn't exist.
    docker exec -i "$DEV" psql -U "$U" -d "${DB}_new" -v ON_ERROR_STOP=1 < /tmp/anonymize_dev.sql
fi

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
if [ "${SKIP_ANON:-false}" = "true" ]; then
    echo "      anonymization SKIPPED — dev holds REAL prod data by request; leak check not applicable."
else
    LEAK=$(ddev -tA -d "$DB" -c "SELECT count(*) FROM users WHERE email NOT LIKE '%@example.com' AND email <> ALL(ARRAY[${PRESERVE_SQL}]::text[]);")
    echo "      non-reserved user emails, excl. preserved (must be 0): $LEAK"
    [ "$LEAK" = "0" ] || { echo "PII LEAK DETECTED — anonymizer missed rows."; exit 1; }
fi
echo "      sample logins:"
ddev -tA -d "$DB" -c "SELECT '        '||role||'  ->  '||email FROM users WHERE role IN ('admin','client','individual') ORDER BY role LIMIT 6;"
REMOTE

scp -q -i "$PEM" "$RENDERED" "$DB_EC2:/tmp/anonymize_dev.sql"
scp -q -i "$PEM" "$REMOTE_SCRIPT" "$DB_EC2:/tmp/refresh_dev_remote.sh"

if [[ "$SOURCE" == "rds" ]]; then
    echo "${YELLOW}Dumping RDS prod on the app EC2, staging on the DB EC2 (via laptop)...${NC}"
    # Password rides stdin (read by the remote shell) so it never appears in
    # argv/ps on the app EC2. PGSSLMODE=require: rds.force_ssl=1.
    printf '%s\n' "$RDS_PW" | ssh -i "$PEM" "$APP_EC2" \
        "IFS= read -r PGPASSWORD; export PGPASSWORD PGSSLMODE=require; pg_dump -h '$RDS_HOST' -p 5432 -U '$DB_USER' -d '$DB_NAME' -Fc" \
      | ssh -i "$PEM" "$DB_EC2" "cat > /tmp/prod_rds.dump"
    ssh -n -i "$PEM" "$DB_EC2" "du -h /tmp/prod_rds.dump"
fi

# -n: don't let our local stdin (the confirm pipe) leak into the remote command.
ssh -n -i "$PEM" "$DB_EC2" \
    "SOURCE='$SOURCE' PROD='$PROD_CONTAINER' DEV='$DEV_CONTAINER' DB='$DB_NAME' U='$DB_USER' DRY_RUN='$DRY_RUN' KEEP_OLD='$KEEP_OLD' PRESERVE_SQL=\"$PRESERVE_SQL\" SKIP_ANON='$SKIP_ANON' bash /tmp/refresh_dev_remote.sh; rc=\$?; rm -f /tmp/refresh_dev_remote.sh /tmp/anonymize_dev.sql /tmp/prod_rds.dump; exit \$rc"

echo
if [[ "$DRY_RUN" == "true" ]]; then
    echo "${GREEN}Dry run complete. Review matcha_new on the host, then re-run without --dry-run.${NC}"
else
    if [[ "$SKIP_ANON" == true ]]; then
        echo "${GREEN}Dev DB refreshed from prod — UNSCRUBBED full mirror.${NC}"
        echo "${GREEN}Log in with your REAL prod email + REAL password (every account works).${NC}"
        echo "${YELLOW}Re-enable scrubbing once you have customers: unset SKIP_ANONYMIZE.${NC}"
    else
        echo "${GREEN}Dev DB refreshed from prod (anonymized).${NC}"
        echo "${GREEN}Anonymized test users: any listed email + password: ${DEV_LOGIN_PASSWORD}${NC}"
        if [[ -n "$DEV_PRESERVE_EMAILS" ]]; then
            echo "${GREEN}Preserved accounts: real email + real password: ${DEV_PRESERVE_EMAILS}${NC}"
        fi
    fi
    echo "Restart your stack: ./scripts/dev-remote.sh"
fi
