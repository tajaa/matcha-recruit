#!/bin/bash
# Logical pg_dump of the matcha-prod RDS instance → S3, run ON the app EC2.
#
# Replaces the dead ~/backup-postgres.sh, which still pointed at the
# `matcha-postgres` container that no longer exists on this host ("No such
# container" on every run since the RDS cutover). This one dumps RDS itself.
#
# Design:
#   - Reads DATABASE_URL from ~/matcha/.env.backend (already points at RDS)
#     and normalizes it for libpq — the app value is asyncpg-shaped
#     (`postgresql+asyncpg://`, `ssl=` params) which pg_dump rejects.
#   - pg_dump runs inside a postgres:15-alpine container so the client major
#     version matches the PG 15 server without installing anything host-side.
#   - Custom-format dump (-Fc): compressed, pg_restore-able table-by-table.
#   - STREAMED straight into `aws s3 cp -` — the dump never lands on local
#     disk, so it can't race the deploy's image pull for /tmp space and a
#     failed upload can't strand a plaintext prod dump on the host.
#   - 7-day retention prune in S3, mirroring the old script.
#
# Intended to be fired in the BACKGROUND by update-ec2.sh (nohup) so deploys
# never block on it; safe to run by hand or from cron too. RDS automated
# snapshots (7-day PITR) remain the primary recovery story — this is the
# offsite/logical layer on top.
set -euo pipefail

S3_BUCKET="s3://matcha-recruit-backups"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
RETENTION_DAYS=7
ENV_FILE="$HOME/matcha/.env.backend"
PG_IMAGE="public.ecr.aws/docker/library/postgres:15-alpine"
S3_KEY="postgres-rds/matcha_rds_${DATE}.dump"

DATABASE_URL=$(grep '^DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -z "$DATABASE_URL" ]; then
  echo "$(date): ERROR — no DATABASE_URL in $ENV_FILE" >&2
  exit 1
fi
# libpq normalization: strip any SQLAlchemy driver suffix, rename asyncpg's
# `ssl=` query param to libpq's `sslmode=` (unknown params are a hard error).
DATABASE_URL=$(printf '%s' "$DATABASE_URL" \
  | sed -e 's|^postgresql+[a-z]*://|postgresql://|' \
        -e 's|\([?\&]\)ssl=|\1sslmode=|g')

echo "$(date): Starting RDS logical backup (streaming to S3)..."
# --expected-size sizes the multipart upload for a stream of unknown length
# (1GB estimate; harmless when the dump is smaller, required well before the
# ~50GB default-part ceiling if it ever grows). pipefail makes a mid-stream
# pg_dump failure fail the whole run rather than uploading a truncated dump.
docker run --rm "$PG_IMAGE" \
  pg_dump --format=custom --no-owner --dbname="$DATABASE_URL" \
  | aws s3 cp - "$S3_BUCKET/$S3_KEY" --only-show-errors --expected-size 1073741824

SIZE=$(aws s3 ls "$S3_BUCKET/$S3_KEY" | awk '{print $3}' || true)
echo "$(date): Upload complete (${SIZE:-?} bytes): $S3_KEY"

# Retention prune (S3 side, postgres-rds/ prefix only). `|| true` on the ls:
# on the very first run the prefix may not exist yet and a nonzero ls under
# pipefail would turn a SUCCESSFUL backup into a failed-looking log.
(aws s3 ls "$S3_BUCKET/postgres-rds/" || true) | while read -r line; do
  file_date=$(echo "$line" | awk '{print $1}')
  file_name=$(echo "$line" | awk '{print $4}')
  if [[ -n "$file_date" && -n "$file_name" ]]; then
    file_age=$(( ($(date +%s) - $(date -d "$file_date" +%s)) / 86400 ))
    if [[ $file_age -gt $RETENTION_DAYS ]]; then
      echo "Pruning old backup: $file_name"
      aws s3 rm "$S3_BUCKET/postgres-rds/$file_name" --only-show-errors
    fi
  fi
done

echo "$(date): RDS backup complete"
