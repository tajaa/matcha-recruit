#!/usr/bin/env bash
# refresh-dev-from-prod.sh
# Replace the DEV database with an ANONYMIZED clone of PRODUCTION.
#
# PROD = the matcha-prod RDS instance (app VPC). It is reachable ONLY from the
# app EC2 (54.177.107.107) — dump runs there via SSH and streams straight to
# this laptop.
# DEV = the LOCAL matcha-postgres docker container (managed by dev-remote.sh).
# The old DB EC2 (3.101.83.217, "matcha-postgres-db") is STOPPED and has no
# public IP anymore — dev moved off it entirely on 2026-06-15. There is no
# remote leg on the dev side anymore: everything below runs locally via
# `docker exec`.
#
# Copy path: pg_dump runs on the APP EC2 inside a disposable `postgres:15`
# container (the box's own bare-metal client is PG16 — its custom-format
# archives use a newer version tag that a PG15 pg_restore refuses to read;
# dumping from a matching-version container sidesteps that entirely, first
# run pulls the ~80MB image and it's cached after), streams over SSH to a
# local temp file, then restores into a staging DB inside the local
# matcha-postgres container. Rename-swap at the end, so a failed/aborted
# clone leaves the existing dev DB intact. A gzipped snapshot of dev is taken
# first for belt-and-suspenders recovery.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="${PEM:-$REPO_ROOT/secrets/roonMT-arm.pem}"
APP_EC2="${APP_EC2:-ec2-user@54.177.107.107}"
RDS_HOST="${RDS_HOST:-matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com}"

DEV_CONTAINER="${DEV_CONTAINER:-matcha-postgres}"          # local docker container (target, rebuilt)
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
SNAP_DIR="${SNAP_DIR:-$HOME/matcha-dev-snapshots}"   # local now — no more DB EC2 to hold these
KEEP_OLD=1   # how many matcha_old_* DBs to retain locally

RED=$'\033[0;31m'; GREEN=$'\033[0;32m'; YELLOW=$'\033[1;33m'; NC=$'\033[0m'

ddev() { docker exec -i "$DEV_CONTAINER" psql -U "$DB_USER" -v ON_ERROR_STOP=1 "$@"; }

# --- Safety rails ------------------------------------------------------------
# Destructive ops must NEVER target the prod container.
if [[ "$DEV_CONTAINER" == *prod* ]]; then
    echo "${RED}REFUSING: DEV_CONTAINER='$DEV_CONTAINER' looks like production.${NC}"; exit 1
fi
[[ -f "$PEM" ]]      || { echo "${RED}SSH key not found: $PEM${NC}"; exit 1; }
[[ -f "$ANON_SQL" ]] || { echo "${RED}Anonymizer not found: $ANON_SQL${NC}"; exit 1; }
command -v docker >/dev/null || { echo "${RED}docker not found on PATH.${NC}"; exit 1; }

if ! docker ps --format '{{.Names}}' | grep -qx "$DEV_CONTAINER"; then
    if docker ps -a --format '{{.Names}}' | grep -qx "$DEV_CONTAINER"; then
        echo "${YELLOW}Starting local $DEV_CONTAINER...${NC}"
        docker start "$DEV_CONTAINER" >/dev/null
        for _ in $(seq 1 30); do
            docker exec "$DEV_CONTAINER" pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1 && break
            sleep 1
        done
    else
        echo "${RED}Local container '$DEV_CONTAINER' not found. Run ./scripts/dev-remote.sh once first (it creates it).${NC}"
        exit 1
    fi
fi

PY="$REPO_ROOT/server/venv/bin/python"
[[ -x "$PY" ]] || PY="$(command -v python3 || true)"
[[ -n "$PY" ]] || { echo "${RED}No python found to generate the dev password hash.${NC}"; exit 1; }

echo "${YELLOW}Reminder: stop any running ./scripts/dev-remote.sh backend first — a live${NC}"
echo "${YELLOW}connection to $DB_NAME can block the rename-swap at the end.${NC}"

DRY_RUN=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true;;
        *) echo "${RED}Unknown arg: $arg${NC} (use --dry-run)"; exit 1;;
    esac
done

# RDS creds come from PROD_DATABASE_URL in server/.env (the laptop-tunnel form;
# only the password is reused here — host is the real endpoint, used from the
# app EC2 which is the only box that can route to RDS).
RDS_URL="$(sed -n 's/^PROD_DATABASE_URL=//p' "$REPO_ROOT/server/.env" | head -1 | tr -d "\"'")"
RDS_PW="$(printf '%s' "$RDS_URL" | sed -nE 's#^[a-z+]+://[^:/@]+:([^@]*)@.*#\1#p')"
[[ -n "$RDS_PW" ]] || { echo "${RED}Could not parse password from PROD_DATABASE_URL in server/.env${NC}"; exit 1; }

if [[ "$SKIP_ANON" == true ]]; then
    ANON_STATUS="${RED}OFF — dev becomes a FULL, UNSCRUBBED copy of prod (real emails/passwords/PII)${NC}"
else
    ANON_STATUS="on (PII scrubbed; preserve list keeps your real logins)"
fi

cat <<EOF
${YELLOW}This will REPLACE the dev database with a copy of PRODUCTION.${NC}
  source (prod, read-only): RDS $RDS_HOST : $DB_NAME (dumped on $APP_EC2)
  target (dev,  REBUILT)  : local docker $DEV_CONTAINER : $DB_NAME
  anonymize PII: $ANON_STATUS
  non-preserved dev user password becomes: $DEV_LOGIN_PASSWORD
  preserved real logins (keep real email + password): ${DEV_PRESERVE_EMAILS:-(none)}
  first step after confirm: push test-tenant edits dev -> prod (sync-test-tenants.sh)
  dry run (clone+anonymize into staging, NO swap): $DRY_RUN
EOF
read -r -p "Type 'refresh-dev' to proceed: " CONFIRM
[[ "$CONFIRM" == "refresh-dev" ]] || { echo "Aborted."; exit 0; }

# Test tenants (Sunset Smile Dental Group, 720 Behavioral, Onc, ...) can have
# dev-only edits at this moment — this refresh is about to REPLACE dev
# wholesale from a prod snapshot, which would silently destroy them. Push
# dev's current state to prod FIRST, so the fresh clone this script builds
# carries it right back in. If the push fails, abort before anything is
# touched — that's a fail-safe compared to trying to restore afterward.
# --require-push turns sync-test-tenants.sh's normally-quiet --auto skip
# paths (lock held, dev PG unreachable, tunnel failed) into hard failures —
# a silent skip here would read as "nothing to push" and let the refresh
# proceed to destroy dev-only edits that were never actually synced.
if [[ "$DRY_RUN" != true ]]; then
    echo "==> Pushing test tenants dev -> prod first (refresh would otherwise destroy dev-only edits)..."
    if ! "$REPO_ROOT/scripts/sync-test-tenants.sh" --auto --require-push; then
        echo "${RED}Test-tenant sync failed — aborting refresh. Dev-only test-tenant edits" \
             "would be destroyed by continuing. Run ./scripts/sync-test-tenants.sh by hand," \
             "fix whatever failed, then retry.${NC}"
        exit 1
    fi
fi

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
DUMP_FILE="$(mktemp -t prod_rds.XXXXXX.dump)"
trap 'rm -f "$RENDERED" "$DUMP_FILE"' EXIT
sed -e "s|__DEV_PW_HASH__|$DEV_PW_HASH|g" \
    -e "s|__PRESERVE_EMAILS__|$PRESERVE_SQL|g" "$ANON_SQL" > "$RENDERED"

TS=$(date +%F_%H-%M-%S)

echo "${YELLOW}[1/6] Pre-refresh dev snapshot...${NC}"
mkdir -p "$SNAP_DIR"
docker exec "$DEV_CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$SNAP_DIR/dev_pre_refresh_$TS.sql.gz"
echo "      $(du -h "$SNAP_DIR/dev_pre_refresh_$TS.sql.gz" | cut -f1) -> $SNAP_DIR/dev_pre_refresh_$TS.sql.gz"
ls -1t "$SNAP_DIR"/dev_pre_refresh_*.sql.gz 2>/dev/null | tail -n +6 | xargs -r rm -f   # keep last 5

echo "${YELLOW}Dumping RDS prod on the app EC2 (via a PG15 dump container), streaming to this laptop...${NC}"
# Password rides stdin (read by the remote shell) so it never appears in
# argv/ps on the app EC2. PGSSLMODE=require: rds.force_ssl=1. pg_dump runs
# inside `postgres:15` (--network host, -e VARNAME with no '=' forwards the
# value from the remote shell's env without it showing up in `docker run`'s
# own argv) so the archive version matches the local PG15 restore target.
printf '%s\n' "$RDS_PW" | ssh -i "$PEM" "$APP_EC2" \
    "IFS= read -r PGPASSWORD; export PGPASSWORD PGSSLMODE=require; docker run --rm --network host -e PGPASSWORD -e PGSSLMODE postgres:15 pg_dump -h '$RDS_HOST' -p 5432 -U '$DB_USER' -d '$DB_NAME' -Fc" \
    > "$DUMP_FILE"
echo "      $(du -h "$DUMP_FILE" | cut -f1) dumped"

echo "${YELLOW}[2/6] Staging fresh ${DB_NAME}_new...${NC}"
ddev -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}_new' AND pid<>pg_backend_pid();" >/dev/null
ddev -d postgres -c "DROP DATABASE IF EXISTS ${DB_NAME}_new;"
ddev -d postgres -c "CREATE DATABASE ${DB_NAME}_new OWNER $DB_USER;"

echo "${YELLOW}[3/6] Restoring staged RDS dump -> ${DB_NAME}_new...${NC}"
docker exec -i "$DEV_CONTAINER" pg_restore -U "$DB_USER" -d "${DB_NAME}_new" --no-owner --no-privileges --exit-on-error < "$DUMP_FILE"

if [[ "$SKIP_ANON" == true ]]; then
    echo "${YELLOW}[4/6] SKIPPING anonymization — dev will be a FULL UNSCRUBBED prod mirror (SKIP_ANONYMIZE set).${NC}"
else
    echo "${YELLOW}[4/6] Anonymizing ${DB_NAME}_new...${NC}"
    docker exec -i "$DEV_CONTAINER" psql -U "$DB_USER" -d "${DB_NAME}_new" -v ON_ERROR_STOP=1 < "$RENDERED"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    echo "${YELLOW}[5/6] DRY RUN — leaving anonymized clone as ${DB_NAME}_new, NOT swapping.${NC}"
    echo "      Inspect: docker exec -it $DEV_CONTAINER psql -U $DB_USER -d ${DB_NAME}_new"
    echo "${YELLOW}[6/6] Skipped swap.${NC}"
    exit 0
fi

echo "${YELLOW}[5/6] Swapping ${DB_NAME} <- ${DB_NAME}_new ...${NC}"
# Double-quote the timestamped name: $TS has hyphens/colons, illegal in an
# unquoted SQL identifier. matcha / matcha_new are bare-identifier-safe.
ddev -d postgres <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('${DB_NAME}','${DB_NAME}_new') AND pid<>pg_backend_pid();
ALTER DATABASE ${DB_NAME} RENAME TO "${DB_NAME}_old_${TS}";
ALTER DATABASE ${DB_NAME}_new RENAME TO ${DB_NAME};
SQL
for old in $(ddev -tA -d postgres -c "SELECT datname FROM pg_database WHERE datname LIKE '${DB_NAME}_old_%' ORDER BY datname DESC OFFSET ${KEEP_OLD};"); do
    echo "      dropping stale $old"
    ddev -d postgres -c "DROP DATABASE IF EXISTS \"$old\";"
done

echo "${YELLOW}[6/6] Verifying live dev DB...${NC}"
ddev -tA -d "$DB_NAME" -c "SELECT 'companies='||count(*) FROM companies UNION ALL SELECT 'users='||count(*) FROM users;"
if [[ "$SKIP_ANON" == true ]]; then
    echo "      anonymization SKIPPED — dev holds REAL prod data by request; leak check not applicable."
else
    # is_test-company users are also intentionally real post-scrub (see the
    # note atop anonymize_dev.sql) — exclude them the same way the anonymizer
    # itself does. Column may not exist yet if prod hasn't run testacct01, so
    # this degrades to the plain (pre-is_test) check rather than aborting the
    # refresh over a migration that just hasn't landed.
    HAS_IS_TEST=$(ddev -tA -d "$DB_NAME" -c "SELECT 1 FROM information_schema.columns WHERE table_name='companies' AND column_name='is_test';")
    if [[ "$HAS_IS_TEST" == "1" ]]; then
        LEAK=$(ddev -tA -d "$DB_NAME" -c "SELECT count(*) FROM users WHERE email NOT LIKE '%@example.com' AND email <> ALL(ARRAY[${PRESERVE_SQL}]::text[])
            AND id NOT IN (
              SELECT user_id FROM clients WHERE user_id IS NOT NULL AND company_id IN (SELECT id FROM companies WHERE is_test)
              UNION
              SELECT user_id FROM employees WHERE user_id IS NOT NULL AND org_id IN (SELECT id FROM companies WHERE is_test)
            );")
    else
        LEAK=$(ddev -tA -d "$DB_NAME" -c "SELECT count(*) FROM users WHERE email NOT LIKE '%@example.com' AND email <> ALL(ARRAY[${PRESERVE_SQL}]::text[]);")
    fi
    echo "      non-reserved user emails, excl. preserved (must be 0): $LEAK"
    [[ "$LEAK" == "0" ]] || { echo "${RED}PII LEAK DETECTED — anonymizer missed rows.${NC}"; exit 1; }
fi
echo "      sample logins:"
ddev -tA -d "$DB_NAME" -c "SELECT '        '||role||'  ->  '||email FROM users WHERE role IN ('admin','client','individual') ORDER BY role LIMIT 6;"

echo
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
