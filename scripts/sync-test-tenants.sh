#!/usr/bin/env bash
# Copy the test tenants (and the /admin/updates changelog) from dev to prod.
#
#   ./scripts/sync-test-tenants.sh           # show what would change, change nothing
#   ./scripts/sync-test-tenants.sh --apply   # do it
#
# These are demo/test accounts, so DEV IS THE SOURCE OF TRUTH: new rows are
# inserted and rows prod already has are refreshed to match dev. Nothing is ever
# deleted — a prod row this sync does not mention is left alone, so real tenants
# and anything else on prod cannot be touched by it.
#
# The tenant list below is the entire blast radius. A company not named here is
# unreachable by this script; that allowlist is the only thing standing between
# "refresh the demo data" and "overwrite a customer", so add to it deliberately.
#
# Under the hood this is just:
#   export-dev-data.py --mode update --scrub-emails …   (reads dev, writes SQL)
#   seed-prod.sh <that file>                            (the only prod-write path)
# — run those by hand if you need a tenant that is not in the list, or want to
# read the SQL before it goes anywhere.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# --- the blast radius -------------------------------------------------------
TENANTS=(
  "Sunset Smile Dental Group"   # Maria Chen — maria.chen@example.com
  "720 Behavioral"
  "Onc"
)
TABLES=(
  admin_updates                 # the /admin/updates changelog
)

APPLY=0
for a in "$@"; do
  case "$a" in
    --apply)   APPLY=1 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)         echo "Unknown flag: $a" >&2; exit 1 ;;
  esac
done

PY="$REPO_ROOT/server/venv/bin/python"
[[ -x "$PY" ]] || PY=python3
OUT="$REPO_ROOT/scripts/sql/sync_test_tenants.sql"

ARGS=()
for t in "${TENANTS[@]}"; do ARGS+=(--tenant "$t"); done
for t in "${TABLES[@]}"; do ARGS+=(--table  "$t"); done

echo "==> Reading dev"
# --scrub-emails is not optional here: the demo tenants carry realistic fake
# domains (@360bh.org, @nexuscorp.com) that resolve in DNS, and on prod those are
# reachable by the invitation and reminder senders. That is the 2026-05-15
# bounce storm.
"$PY" scripts/export-dev-data.py "${ARGS[@]}" --mode update --scrub-emails --out "$OUT"

# --allow-ddl only because seed-prod.sh greps string literals too and the tenant
# prose contains words like "create"; the generator has no DDL in it. --allow-ddl
# does not permit anything here beyond turning off that text search.
SEED_FLAGS=(--allow-ddl)

if [[ "$APPLY" == "1" ]]; then
  echo
  echo "==> Applying to PROD"
  ./scripts/seed-prod.sh "$OUT" "${SEED_FLAGS[@]}"
else
  echo
  echo "==> Dry run against PROD (executes everything, commits nothing)"
  ./scripts/seed-prod.sh "$OUT" --dry-run "${SEED_FLAGS[@]}"
  echo
  echo "Nothing was committed. Re-run with --apply to push it."
fi
