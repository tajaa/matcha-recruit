#!/usr/bin/env bash
# Migrate PROD via SSH tunnel.
#
# Default target: matcha-postgres-prod, a self-hosted Postgres container on
# the dedicated DB EC2 (13.56.253.173). RDS (matcha-prod) was retired
# 2026-08-21 — the instance still exists but is STOPPED, kept only as a cold
# fallback. The DB EC2 sits in its own VPC and its security group only allows
# 5432/5433 from the app EC2's IP, so the tunnel still jumps through the app
# box:
#   localhost:5434 -> app EC2 (54.177.107.107) -> DB EC2 (13.56.253.173) :5433
# Reads PROD_DATABASE_URL from server/.env (expects localhost:5434 +
# sslmode=require — the container has ssl=on).
#
# The DB EC2 also runs a second container, matcha-postgres on :5432 — that one
# is a frozen pre-cutover multi-app snapshot (last write 2026-06-06), NOT
# live prod. Don't point anything at it.
#
# --legacy: target the OLD prod container instead (matcha-postgres-prod :5433
# on the now-STOPPED original DB EC2, 3.101.83.217) — frozen since the RDS
# cutover, kept only for historical reference. Reads PROD_LEGACY_DATABASE_URL.
# Will simply fail to connect until/unless that host is started again.
#
# ---------------------------------------------------------------------------
# This script is deliberately hard to run by accident. Five gates stand between
# the tunnel and `alembic upgrade heads`, and each one is a bug that already bit:
#
#   1. dirty-tree     — jparent01 was applied to prod from an UNCOMMITTED file,
#                       while dev had run an older version of the same revision.
#   2. preview        — `upgrade heads` never said what it was about to do.
#   3. backup         — most downgrade()s are `pass`. A pg_dump to S3, taken
#                       right before the apply, is the only rollback that exists.
#   4. rehearsal      — run it for real, roll it back. This is what caught a
#                       UniqueViolation on prod data, before prod. It also times
#                       the run: a migration that crawls here will hang for real.
#   5. confirmation   — type it out.
#
# Escape hatches: --allow-dirty, --no-snapshot, --skip-rehearsal. There is no
# flag that skips the typed confirmation.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="$REPO_ROOT/secrets/roonMT-arm.pem"
ENV_FILE="$REPO_ROOT/server/.env"

APP_EC2="ec2-user@54.177.107.107"
DB_EC2="ec2-user@3.101.83.217"
PROD_DB_HOST="13.56.253.173"
PROD_DB_SSH="ec2-user@${PROD_DB_HOST}"
PROD_DB_CONTAINER="matcha-postgres-prod"
PROD_DB_PORT=5433
S3_BACKUP_BUCKET="s3://matcha-recruit-backups"
AWS_REGION_DEFAULT="us-west-1"

LEGACY=0
ALLOW_DIRTY=0
NO_SNAPSHOT=0
SKIP_REHEARSAL=0
SNAP_CREATED=0

for arg in "$@"; do
  case "$arg" in
    --legacy)         LEGACY=1 ;;
    --allow-dirty)    ALLOW_DIRTY=1 ;;
    --no-snapshot)    NO_SNAPSHOT=1 ;;
    --skip-rehearsal) SKIP_REHEARSAL=1 ;;
    -h|--help)
      sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *)
      echo "Unknown flag: $arg" >&2
      exit 1 ;;
  esac
done

env_val() { grep "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' '; }

if [[ "$LEGACY" == "1" ]]; then
  LABEL="LEGACY prod container (matcha-postgres-prod :5433 on DB EC2)"
  LOCAL_PORT=5433
  JUMP="$DB_EC2"
  FORWARD="${LOCAL_PORT}:localhost:5433"
  URL="${PROD_LEGACY_DATABASE_URL:-$(env_val PROD_LEGACY_DATABASE_URL)}"
  : "${URL:?Add PROD_LEGACY_DATABASE_URL=postgresql://user:pass@localhost:5433/matcha to server/.env}"
else
  LABEL="self-hosted ${PROD_DB_CONTAINER} (via app EC2)"
  LOCAL_PORT=5434
  JUMP="$APP_EC2"
  FORWARD="${LOCAL_PORT}:${PROD_DB_HOST}:${PROD_DB_PORT}"
  URL="${PROD_DATABASE_URL:-$(env_val PROD_DATABASE_URL)}"
  : "${URL:?Add PROD_DATABASE_URL=postgresql://matcha:pass@localhost:5434/matcha?sslmode=require to server/.env}"
fi

echo "Target: $LABEL"
echo "Connecting as: $(echo "$URL" | sed 's|://[^:]*:[^@]*@|://***:***@|')"
echo

# ---------------------------------------------------------------------------
# GATE 1 — the migrations must be committed.
#
# Whatever runs against prod has to be recoverable from git afterwards, and has
# to be the same bytes dev ran. An uncommitted migration satisfies neither.
# ---------------------------------------------------------------------------
DIRTY="$(cd "$REPO_ROOT" && git status --porcelain -- server/alembic 2>/dev/null || true)"
if [[ -n "$DIRTY" ]]; then
  if [[ "$ALLOW_DIRTY" == "1" ]]; then
    echo "!! --allow-dirty: applying migrations that are NOT committed:"
    echo "$DIRTY" | sed 's/^/     /'
    echo "!! Whatever prod ends up running will not be reconstructible from git."
    echo
  else
    echo "ABORT: uncommitted changes under server/alembic:" >&2
    echo "$DIRTY" | sed 's/^/    /' >&2
    echo >&2
    echo "Commit them first. Prod must run code that git has (and that dev ran)." >&2
    echo "Override with --allow-dirty if you know what you are doing." >&2
    exit 1
  fi
fi

# Tunnel. Reuse an existing listener on the local port if one is already up;
# otherwise open our own and tear it down on exit.
if lsof -n -P -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Reusing existing listener on localhost:${LOCAL_PORT}."
else
  echo "Opening SSH tunnel ${JUMP} (${FORWARD})..."
  ssh -i "$PEM" -L "$FORWARD" "$JUMP" -N -f -o ExitOnForwardFailure=yes
  trap 'pkill -f "ssh.*${FORWARD}" 2>/dev/null; exit' EXIT INT TERM
  sleep 1
fi

cd "$REPO_ROOT/server"

# ---------------------------------------------------------------------------
# GATE 2 — say what is about to happen, and do nothing if nothing is pending.
#
# `alembic upgrade heads` used to run blind. `heads` is plural because the
# history carries several permanent branch heads (no branch labels), so `head`
# singular is ambiguous — but it also means "heads" silently covers branches you
# were not thinking about. Print them.
# ---------------------------------------------------------------------------
echo
echo "Reading current revision(s) from prod..."
CURRENT_REVS="$(DATABASE_URL="$URL" ./venv/bin/alembic current 2>/dev/null \
  | grep -vE '^(INFO|WARNING|DEBUG)' \
  | awk '{print $1}' \
  | grep -E '^[a-z0-9_]+$' || true)"

echo "  prod is at: ${CURRENT_REVS:-<empty — no alembic_version>}" | tr '\n' ' '
echo
echo "  local heads: $(./venv/bin/alembic heads 2>/dev/null | awk '{print $1}' | tr '\n' ' ')"
echo

PENDING="$("$REPO_ROOT/server/venv/bin/python" "$REPO_ROOT/scripts/alembic_pending.py" $CURRENT_REVS)"

if [[ -z "$PENDING" ]]; then
  echo "Prod is already at every head — nothing to do."
  exit 0
fi

echo "PENDING revisions (oldest first):"
echo "$PENDING" | sed 's/^/    /'
echo
PENDING_COUNT="$(echo "$PENDING" | wc -l | tr -d ' ')"
FIRST_PENDING="$(echo "$PENDING" | head -1 | awk '{print $1}')"
echo "  $PENDING_COUNT revision(s) will be applied to ${LABEL}."
echo

# ---------------------------------------------------------------------------
# GATE 3 — a backup, because there is no downgrade.
#
# Most recent downgrade()s are `pass`. There's no RDS snapshot API to lean on
# for the self-hosted box, so the rollback story is a pg_dump taken over SSH
# straight from the container, streamed to S3 without touching local/remote
# disk (mirrors deploy/backup-prod-rds.sh's streaming approach).
# ---------------------------------------------------------------------------
if [[ "$NO_SNAPSHOT" == "1" ]]; then
  echo "!! --no-snapshot: proceeding with NO rollback path. If this goes wrong,"
  echo "!! there is nothing to restore from."
  echo
elif [[ "$LEGACY" == "1" ]]; then
  echo "Note: --legacy targets a frozen historical container — backup gate does not apply."
  echo "      Take your own backup if this migration is not reversible."
  echo
elif command -v aws >/dev/null 2>&1 && aws sts get-caller-identity >/dev/null 2>&1; then
  SNAP_SLUG="$(printf '%s' "$FIRST_PENDING" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -e 's/[^a-z0-9]\{1,\}/-/g' -e 's/^-*//' -e 's/-*$//')"
  SNAP_ID="matcha_prod_pre_${SNAP_SLUG:-migration}_$(date +%Y%m%d%H%M%S)"
  S3_KEY="postgres-selfhosted/${SNAP_ID}.dump"
  read -r -p "pg_dump matcha to ${S3_BACKUP_BUCKET}/${S3_KEY} before migrating? [Y/n] " reply
  if [[ "${reply:-Y}" =~ ^[Yy]?$ ]]; then
    echo "Dumping ${PROD_DB_CONTAINER} and streaming to S3..."
    if ssh -i "$PEM" "$PROD_DB_SSH" \
        "sudo docker exec ${PROD_DB_CONTAINER} pg_dump --format=custom --no-owner -U matcha matcha" \
        | aws s3 cp - "${S3_BACKUP_BUCKET}/${S3_KEY}" --expected-size 1073741824; then
      SNAP_CREATED=1
      echo "Backup of record: ${S3_BACKUP_BUCKET}/${S3_KEY} (verified again before apply)"
      echo
    else
      echo "ABORT: pg_dump/S3 upload failed — no rollback path exists." >&2
      exit 1
    fi
  else
    echo "!! Skipping backup: proceeding with NO rollback path. If this goes wrong,"
    echo "!! there is nothing to restore from."
    echo
  fi
else
  echo "aws CLI unavailable or not credentialed — cannot back up automatically."
  read -r -p "Name an EXISTING S3 backup to roll back to (or blank to abort): " existing_snap
  if [[ -z "$existing_snap" ]]; then
    echo "ABORT: no rollback path." >&2
    exit 1
  fi
  echo "Rollback backup of record: $existing_snap"
  echo
fi

# ---------------------------------------------------------------------------
# GATE 4 — rehearse against real prod rows, then roll back.
#
# MIGRATE_REHEARSAL=1 makes env.py raise at the end of the (single) upgrade
# transaction, so every pending revision executes against live data — hitting
# the real constraints, on the real row counts, over the real tunnel — and
# commits nothing. Anything that would have blown up mid-migration blows up here
# instead, where the cost is a rollback.
#
# The elapsed time it reports is the other half of the point: a data migration
# that is round-trip-bound (row-by-row Python) will crawl here and then hang for
# real. If the rehearsal is slow, rewrite the migration set-based.
# ---------------------------------------------------------------------------
if [[ "$SKIP_REHEARSAL" == "1" ]]; then
  echo "!! --skip-rehearsal: applying untested migrations directly to prod."
  echo
else
  echo "REHEARSAL — running all pending revisions against prod, then rolling back."
  echo
  set +e
  REHEARSAL_OUT="$(MIGRATE_REHEARSAL=1 DATABASE_URL="$URL" ./venv/bin/alembic upgrade heads 2>&1)"
  set -e

  if echo "$REHEARSAL_OUT" | grep -q "MIGRATE_REHEARSAL"; then
    echo "$REHEARSAL_OUT" | grep -E "Running upgrade|MIGRATE_REHEARSAL" | sed 's/^/    /'
    echo
    echo "Rehearsal PASSED — nothing committed."
    echo
  else
    echo "REHEARSAL FAILED — prod is untouched. The migration would have broken:" >&2
    echo >&2
    echo "$REHEARSAL_OUT" >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# GATE 3b — verify the backup survived, now that the rehearsal has given it
# time. The `aws s3 cp` exit code above already caught a failed stream, but
# a cheap head-object confirms the object is actually sitting in the bucket
# (not e.g. silently truncated by a killed pipe) before touching real data.
# ---------------------------------------------------------------------------
if [[ "$SNAP_CREATED" == "1" ]]; then
  if aws s3api head-object --bucket "${S3_BACKUP_BUCKET#s3://}" --key "$S3_KEY" >/dev/null 2>&1; then
    echo "Backup ${S3_BACKUP_BUCKET}/${S3_KEY} confirmed in S3 — rollback path confirmed."
    echo
  else
    echo "ABORT: backup ${S3_BACKUP_BUCKET}/${S3_KEY} not found in S3 — the rollback" >&2
    echo "path does not exist. Fix the backup (or --no-snapshot) before migrating." >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# GATE 5 — type it. No -y flag; this prompt is the product.
# ---------------------------------------------------------------------------
echo "About to apply $PENDING_COUNT revision(s) to ${LABEL} FOR REAL."
read -r -p "Type 'migrate prod' to proceed: " confirm
if [[ "$confirm" != "migrate prod" ]]; then
  echo "Aborted. Nothing was applied."
  exit 1
fi

echo
echo "Running Alembic upgrade on prod..."
DATABASE_URL="$URL" ./venv/bin/alembic upgrade heads
echo "Done."
