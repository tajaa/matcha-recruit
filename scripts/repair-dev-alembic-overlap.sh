#!/usr/bin/env bash
# Repair the known dev-only Alembic bookkeeping overlap:
#
#   tellus_app_16 -> oceanlab_app_02 -> oceanlab_app_03
#
# Some dev databases recorded both tellus_app_16 and oceanlab_app_03 as active
# heads. Alembic correctly refuses to upgrade because an ancestor and its
# descendant cannot both be current. This removes only the stale ancestor row,
# then delegates schema work to the normal migration command.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/server/.env"
DEV_DATABASE_URL="${DEV_DATABASE_URL:-}"

if [[ -z "$DEV_DATABASE_URL" ]] && [[ -f "$ENV_FILE" ]]; then
  DEV_DATABASE_URL=$(grep '^DEV_DATABASE_URL=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' ' || true)
fi
if [[ -z "$DEV_DATABASE_URL" ]]; then
  DEV_DATABASE_URL="postgresql://matcha:matcha_dev@localhost:5432/matcha"
fi

echo "Connecting as: $(echo "$DEV_DATABASE_URL" | sed 's|://[^:]*:[^@]*@|://***:***@|')"

CURRENT_REVISIONS=$(psql "$DEV_DATABASE_URL" -v ON_ERROR_STOP=1 -Atc \
  "SELECT version_num FROM alembic_version WHERE version_num IN ('tellus_app_16', 'oceanlab_app_03') ORDER BY version_num")

if [[ "$CURRENT_REVISIONS" != *"tellus_app_16"* ]]; then
  echo "No repair needed: tellus_app_16 is not recorded as a current revision."
elif [[ "$CURRENT_REVISIONS" != *"oceanlab_app_03"* ]]; then
  echo "Refusing repair: tellus_app_16 is current but descendant oceanlab_app_03 is not." >&2
  echo "The database does not match the known safe overlap." >&2
  exit 1
else
  echo "Removing stale ancestor marker tellus_app_16 (oceanlab_app_03 remains current)..."
  psql "$DEV_DATABASE_URL" -v ON_ERROR_STOP=1 <<'SQL'
BEGIN;
LOCK TABLE alembic_version IN EXCLUSIVE MODE;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM alembic_version WHERE version_num = 'tellus_app_16')
     OR NOT EXISTS (SELECT 1 FROM alembic_version WHERE version_num = 'oceanlab_app_03') THEN
    RAISE EXCEPTION 'Alembic revisions changed during repair; no rows modified';
  END IF;
END $$;

DELETE FROM alembic_version WHERE version_num = 'tellus_app_16';
COMMIT;
SQL
  echo "Alembic bookkeeping repaired."
fi

echo "Running the normal dev migration..."
DEV_DATABASE_URL="$DEV_DATABASE_URL" "$REPO_ROOT/scripts/migrate-dev.sh"
