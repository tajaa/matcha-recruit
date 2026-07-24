#!/usr/bin/env bash
# Bidirectional dev <-> prod sync for test/demo tenants (Sunset Smile Dental
# Group, 720 Behavioral, Onc, ...) — edit on EITHER side, this converges both.
#
#   ./scripts/sync-test-tenants.sh           # show what would change, change nothing
#   ./scripts/sync-test-tenants.sh --apply   # do it (interactive prod confirm)
#   ./scripts/sync-test-tenants.sh --auto    # do it, unattended, quiet — for the
#                                             # deploy hook (update-ec2.sh) and
#                                             # manual re-runs between deploys
#   --require-push  (combine with --auto) — turn the quiet skip paths (lock
#                    held, dev PG unreachable, tunnel failed, and the merge
#                    engine exiting 2 for drift/warnings — which can mean an
#                    EMPTY sync_to_prod.sql, e.g. `companies` itself is
#                    schema-drifted) into hard failures (exit 3) instead of
#                    exit 0. The deploy hook wants a skip to be a harmless
#                    no-op; a caller like refresh-dev-from-prod.sh that is
#                    about to DESTROY dev needs to know the push genuinely
#                    happened, not just that nothing crashed.
#
# Tenants are whatever `companies.is_test = true` on either DB (no hardcoded
# allowlist to maintain — flip the flag in the admin company-detail page and
# the next sync run picks it up). Merge rules, schema-drift handling, and the
# "never touch a shared/ascended row" safety rule live in scripts/sync_tenants.py
# — read that module's docstring before changing behavior here.
#
# Under the hood:
#   sync_tenants.py --dev-dsn ... --prod-dsn ...   (reads BOTH, writes 2 SQL files)
#   seed-prod.sh <to_prod.sql>                     (the only prod-write path)
#   seed-prod.sh <to_dev.sql> --dev                 (dev writes go through the
#                                                     same guarded runner too)
# `admin_updates` (the /admin/updates changelog) stays a separate one-way
# dev->prod push, same as before this file grew a merge engine — it isn't
# company-scoped, so the FK-walk never reaches it, and its `position` column
# is dev-authored on purpose.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="$REPO_ROOT/server/.env"
PEM="$REPO_ROOT/secrets/roonMT-arm.pem"
APP_EC2="ec2-user@54.177.107.107"
RDS_HOST="matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com"
LOCAL_PORT=5434
LOCK_DIR="${TMPDIR:-/tmp}/matcha-sync-test-tenants.lock"
OUT_DIR="$REPO_ROOT/scripts/sql"
UNDO_ARCHIVE_DIR="${UNDO_ARCHIVE_DIR:-$HOME/matcha-sync-undo}"   # outside the repo, like ~/matcha-dev-snapshots

env_val() { grep "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' '; }

# Archive the just-APPLIED dev->prod sync pair with a timestamp. The live
# scripts/sql/sync_to_prod{,.undo}.sql files are OVERWRITTEN by the next
# deploy's sync run (sync_tenants.py regenerates them every time), and they
# are the only rollback for this unattended prod write — if a bad push isn't
# noticed within one deploy cycle, the pre-image is gone without this.
archive_prod_undo() {
  mkdir -p "$UNDO_ARCHIVE_DIR"
  local ts; ts="$(date -u +%Y%m%dT%H%M%SZ)"
  cp "$OUT_DIR/sync_to_prod.sql"      "$UNDO_ARCHIVE_DIR/sync_to_prod.$ts.sql"
  cp "$OUT_DIR/sync_to_prod.undo.sql" "$UNDO_ARCHIVE_DIR/sync_to_prod.$ts.undo.sql"
  ls -1t "$UNDO_ARCHIVE_DIR"/sync_to_prod.*.undo.sql 2>/dev/null | tail -n +21 | while read -r f; do
    rm -f "$f" "${f%.undo.sql}.sql"
  done
  log "Archived applied prod sync + undo -> $UNDO_ARCHIVE_DIR (sync_to_prod.$ts.*)"
}

MODE="dry-run"   # dry-run | apply | auto
REQUIRE_PUSH=0
for a in "$@"; do
  case "$a" in
    --apply)         MODE="apply" ;;
    --auto)          MODE="auto" ;;
    --require-push)  REQUIRE_PUSH=1 ;;
    -h|--help)       sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)               echo "Unknown flag: $a" >&2; exit 1 ;;
  esac
done
QUIET=0; [[ "$MODE" == "auto" ]] && QUIET=1

log() { if [[ "$QUIET" == "1" ]]; then echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; else echo "$*"; fi; }

# ---------------------------------------------------------------------------
# Mutex — a deploy hook and a manual run (or two overlapping deploys) must
# not race the same output files / prod transaction. Stale after 30 min so a
# killed run doesn't wedge every future one.
# ---------------------------------------------------------------------------
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  if [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +30 2>/dev/null)" ]]; then
    log "Stale lock (>30min) — removing and continuing."
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR"
  elif [[ "$MODE" == "auto" ]]; then
    if [[ "$REQUIRE_PUSH" == "1" ]]; then
      log "Another sync is running — FAILING (--require-push)."
      exit 3
    fi
    log "Another sync is running — skipping this tick."
    exit 0
  else
    echo "Another sync is running ($LOCK_DIR exists). Aborting." >&2
    exit 1
  fi
fi
trap 'rm -rf "$LOCK_DIR"' EXIT

# ---------------------------------------------------------------------------
# Dev reachability — auto mode treats "docker/dev DB down" as a quiet no-op,
# not a failure (this runs unattended after every deploy).
# ---------------------------------------------------------------------------
DEV_URL="${DATABASE_URL:-$(env_val DATABASE_URL)}"
DEV_URL="${DEV_URL:-postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha}"
if ! psql "$DEV_URL" -c 'SELECT 1' >/dev/null 2>&1; then
  if [[ "$MODE" == "auto" ]]; then
    if [[ "$REQUIRE_PUSH" == "1" ]]; then
      log "Local dev Postgres unreachable — FAILING (--require-push)."
      exit 3
    fi
    log "Local dev Postgres unreachable — skipping this tick."
    exit 0
  fi
  echo "Local dev Postgres unreachable at $DEV_URL." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Prod tunnel — same pattern as seed-prod.sh / migrate-prod.sh, reused (not
# reopened) if seed-prod.sh's own invocations below need it too.
# ---------------------------------------------------------------------------
PROD_URL="${PROD_DATABASE_URL:-$(env_val PROD_DATABASE_URL)}"
if [[ -z "$PROD_URL" ]]; then
  echo "PROD_DATABASE_URL not set in server/.env." >&2
  exit 1
fi

OPENED_TUNNEL=0
if lsof -n -P -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  log "Reusing existing tunnel on localhost:${LOCAL_PORT}."
else
  log "Opening SSH tunnel to ${APP_EC2}..."
  if [[ "$MODE" == "auto" ]]; then
    if ! ssh -i "$PEM" -L "${LOCAL_PORT}:${RDS_HOST}:5432" "$APP_EC2" -N -f \
         -o BatchMode=yes -o ConnectTimeout=5 -o ExitOnForwardFailure=yes 2>/dev/null; then
      if [[ "$REQUIRE_PUSH" == "1" ]]; then
        log "Prod unreachable (tunnel failed) — FAILING (--require-push)."
        exit 3
      fi
      log "Prod unreachable (tunnel failed) — skipping this tick."
      exit 0
    fi
  else
    ssh -i "$PEM" -L "${LOCAL_PORT}:${RDS_HOST}:5432" "$APP_EC2" -N -f -o ExitOnForwardFailure=yes
  fi
  OPENED_TUNNEL=1
  sleep 1
fi
if [[ "$OPENED_TUNNEL" == "1" ]]; then
  trap 'rm -rf "$LOCK_DIR"; pkill -f "ssh.*${LOCAL_PORT}:${RDS_HOST}:5432" 2>/dev/null || true' EXIT
fi

# ---------------------------------------------------------------------------
# Run the merge engine — reads both sides, writes scripts/sql/sync_to_{prod,dev}.sql
# (+ .undo.sql for each) with pre-image-based undo. Exit 2 = drift/warnings
# present but files were still generated for the tables that ARE in sync;
# exit 1 = real error.
# ---------------------------------------------------------------------------
PY="$REPO_ROOT/server/venv/bin/python"
[[ -x "$PY" ]] || PY=python3

log "==> Computing dev <-> prod diff for is_test tenants"
set +e
"$PY" scripts/sync_tenants.py --dev-dsn "$DEV_URL" --prod-dsn "$PROD_URL" --out-dir "$OUT_DIR" \
  $( [[ "$QUIET" == "1" ]] && echo --quiet )
ENGINE_EXIT=$?
set -e
# Only 0 (clean) and 2 (drift/warnings, still wrote output files) are
# defined success paths — see sync_tenants.py's run_sync docstring/return
# values. Anything else (1 = real error, but also 137 SIGKILL/OOM, 130
# Ctrl-C, or any other crash) must NOT fall through: _write_outputs() only
# runs on the normal exit paths, so a crash leaves the PREVIOUS run's
# sync_to_prod.sql on disk — has_mutations() below would see it as fresh and
# --auto would re-apply a stale diff to live prod with GUARD 4 bypassed.
if [[ "$ENGINE_EXIT" != "0" && "$ENGINE_EXIT" != "2" ]]; then
  echo "sync_tenants.py failed (exit $ENGINE_EXIT) — see output above." >&2
  exit 1
fi
# Exit 2 = drift/warnings — possibly an EMPTY sync_to_prod.sql (e.g. the
# `companies` table itself is schema-drifted, which aborts the merge
# entirely before it even looks at test-tenant rows). A quiet fallthrough to
# "Nothing to push to prod" below is indistinguishable from a real
# convergence to a --require-push caller (refresh-dev-from-prod.sh) that is
# about to DESTROY dev and needs to know its test-tenant edits genuinely
# reached prod, not that the merge silently skipped itself.
if [[ "$ENGINE_EXIT" == "2" && "$REQUIRE_PUSH" == "1" ]]; then
  log "sync_tenants.py reported drift/warnings (exit 2) — FAILING (--require-push)." \
      "The push this caller depends on may not have happened. See output above."
  exit 3
fi

has_mutations() { grep -qE '^(INSERT|UPDATE)' "$1" 2>/dev/null; }

# GUARD 1 (--allow-ddl) is no longer bypassed here: seed-prod.sh now strips
# string literals before scanning for DDL/txn-control keywords, so tenant
# prose ("create a new policy", "admin approved") can't false-positive it.
# The DDL guard is live on this automated prod path again — a real safety win.

# ---------------------------------------------------------------------------
# Apply dev -> prod
# ---------------------------------------------------------------------------
TO_PROD="$OUT_DIR/sync_to_prod.sql"
if ! has_mutations "$TO_PROD"; then
  log "==> Nothing to push to prod."
elif [[ "$MODE" == "auto" ]]; then
  log "==> Applying to PROD (auto)"
  MATCHA_SYNC_AUTONOMOUS=1 ./scripts/seed-prod.sh "$TO_PROD" --yes
  archive_prod_undo
elif [[ "$MODE" == "apply" ]]; then
  log "==> Applying to PROD"
  ./scripts/seed-prod.sh "$TO_PROD"
  archive_prod_undo
else
  log "==> Dry run: dev -> prod (executes everything, commits nothing)"
  ./scripts/seed-prod.sh "$TO_PROD" --dry-run
fi

# ---------------------------------------------------------------------------
# Apply prod -> dev (seed-prod.sh --dev never prompts, in any mode)
# ---------------------------------------------------------------------------
TO_DEV="$OUT_DIR/sync_to_dev.sql"
if ! has_mutations "$TO_DEV"; then
  log "==> Nothing to push to dev."
elif [[ "$MODE" == "dry-run" ]]; then
  log "==> Dry run: prod -> dev (executes everything, commits nothing)"
  ./scripts/seed-prod.sh "$TO_DEV" --dev --dry-run
else
  log "==> Applying to dev"
  ./scripts/seed-prod.sh "$TO_DEV" --dev
fi

# ---------------------------------------------------------------------------
# admin_updates — unchanged one-way dev->prod push (not company-scoped, so
# the merge engine above never touches it).
# ---------------------------------------------------------------------------
ADMIN_OUT="$OUT_DIR/sync_admin_updates.sql"
log "==> Reading dev admin_updates changelog"
# --dsn must be the SAME resolved $DEV_URL the merge engine above diffed
# against — without it this falls back to $DEV_DATABASE_URL (usually unset)
# then a hardcoded default, silently reading the changelog from a different
# database than the one this run just diffed if the operator's dev DSN
# differs (different db name/port).
"$PY" scripts/export-dev-data.py --dsn "$DEV_URL" --table admin_updates --mode update --scrub-emails --out "$ADMIN_OUT" >&2

if has_mutations "$ADMIN_OUT"; then
  if [[ "$MODE" == "auto" ]]; then
    log "==> Applying admin_updates to PROD (auto)"
    MATCHA_SYNC_AUTONOMOUS=1 ./scripts/seed-prod.sh "$ADMIN_OUT" --yes
  elif [[ "$MODE" == "apply" ]]; then
    log "==> Applying admin_updates to PROD"
    ./scripts/seed-prod.sh "$ADMIN_OUT"
  else
    log "==> Dry run: admin_updates dev -> prod"
    ./scripts/seed-prod.sh "$ADMIN_OUT" --dry-run
  fi
else
  log "==> admin_updates already in sync."
fi

if [[ "$MODE" == "dry-run" ]]; then
  echo
  echo "Nothing was committed. Re-run with --apply to push it, or --auto for the unattended form."
fi
