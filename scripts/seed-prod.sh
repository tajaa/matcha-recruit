#!/usr/bin/env bash
# Seed test/demo data into PROD (or dev) with guardrails — replaces the ad-hoc
# "python3 seed_x.py | ssh ... psql" pipelines that made prod seeding painful.
#
#   ./scripts/seed-prod.sh <seedfile> [flags]
#
# Seed file formats:
#   foo.sql   — plain SQL, applied as-is. Undo pair: foo.undo.sql
#   foo.py    — python script that PRINTS SQL to stdout (the existing
#               seed_regina_demo.py convention). Undo: the script is invoked
#               with --undo and must print the reversing SQL.
#
# Flags:
#   --dry-run            run everything inside BEGIN…ROLLBACK — full execution
#                        against the real DB (catches FK/constraint errors),
#                        commits nothing. Do this first, always.
#   --undo               apply the seed's undo SQL instead of the seed
#   --dev                target local dev DB instead of prod (no confirm)
#   --allow-ddl          permit CREATE/ALTER/DROP/TRUNCATE (blocked by default —
#                        seeds are DATA, schema goes through migrate-prod.sh)
#   --allow-real-emails  permit email addresses outside the RFC 2606 reserved
#                        domains (blocked by default — realistic fake domains
#                        cause real bounce-storms; see CLAUDE.md)
#   --yes                skip GUARD 4's typed confirm. Only honored when the
#                        env var MATCHA_SYNC_AUTONOMOUS=1 is ALSO set — double
#                        keyed on purpose so this can't be casually passed to
#                        an interactive invocation. Reserved for
#                        scripts/sync-test-tenants.sh --auto, where the SQL is
#                        machine-generated, rooted exclusively at is_test
#                        companies, restricted to descend-reachable rows
#                        (never a shared parent), never deletes, and still
#                        goes through guards 1/1b/2/3 + the pre-image undo
#                        file written before this runs.
#
# Guardrails, each one a real incident:
#   1. DDL block         — a seed once CREATE TABLE'd on live prod
#   2. reserved-domains  — the 2026-05-15 medcenter.com bounce-storm
#   3. single txn        — half-applied seed = untagged orphan rows
#   4. typed confirm     — prod writes require typing 'seed prod'
#
# Conventions for writing seeds: scripts/seed/README.md
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PEM="$REPO_ROOT/secrets/roonMT-arm.pem"
ENV_FILE="$REPO_ROOT/server/.env"
APP_EC2="ec2-user@54.177.107.107"
RDS_HOST="matcha-prod.cbego6cwwdqy.us-west-1.rds.amazonaws.com"

env_val() { grep "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d ' '; }

SEEDFILE=""
DRY_RUN=0
UNDO=0
DEV=0
ALLOW_DDL=0
ALLOW_REAL_EMAILS=0
ASSUME_YES=0

for arg in "$@"; do
  case "$arg" in
    --dry-run)           DRY_RUN=1 ;;
    --undo)              UNDO=1 ;;
    --dev)               DEV=1 ;;
    --allow-ddl)         ALLOW_DDL=1 ;;
    --allow-real-emails) ALLOW_REAL_EMAILS=1 ;;
    --yes)               ASSUME_YES=1 ;;
    -h|--help)           sed -n '2,41p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)                  echo "Unknown flag: $arg" >&2; exit 1 ;;
    *)
      if [[ -n "$SEEDFILE" ]]; then echo "Only one seed file allowed" >&2; exit 1; fi
      SEEDFILE="$arg" ;;
  esac
done

[[ -n "$SEEDFILE" ]] || { echo "Usage: $0 <seedfile.sql|seedfile.py> [flags]  (-h for help)" >&2; exit 1; }
[[ -f "$SEEDFILE" ]] || { echo "No such file: $SEEDFILE" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Materialize the SQL to apply.
# ---------------------------------------------------------------------------
SQL_TMP="$(mktemp -t seed-prod.XXXXXX.sql)"
trap 'rm -f "$SQL_TMP"' EXIT

case "$SEEDFILE" in
  *.py)
    if [[ "$UNDO" == "1" ]]; then
      python3 "$SEEDFILE" --undo > "$SQL_TMP"
    else
      python3 "$SEEDFILE" > "$SQL_TMP"
    fi
    ;;
  *.sql)
    if [[ "$UNDO" == "1" ]]; then
      UNDO_FILE="${SEEDFILE%.sql}.undo.sql"
      [[ -f "$UNDO_FILE" ]] || { echo "No undo file: $UNDO_FILE" >&2; exit 1; }
      cp "$UNDO_FILE" "$SQL_TMP"
    else
      cp "$SEEDFILE" "$SQL_TMP"
    fi
    ;;
  *)
    echo "Seed file must be .sql or .py" >&2; exit 1 ;;
esac

[[ -s "$SQL_TMP" ]] || { echo "Seed produced no SQL — nothing to do." >&2; exit 1; }

# ---------------------------------------------------------------------------
# GUARD 1 — no DDL in a seed. Schema changes go through migrate-prod.sh.
# (Strips SQL comments first so a mention of DROP in a comment doesn't trip.)
# ---------------------------------------------------------------------------
# A naive `sed 's/--.*$//'` is NOT safe as a general-purpose comment
# stripper once lit() (export-dev-data.py) started emitting multi-line
# values as single-line E'' strings: a literal "--" inside prose ("reported
# 3--4 times") reads as a comment-start and truncates the rest of that
# physical line — including anything after it, like a later email address
# GUARD 2 needs to see. strip_sql_comments_outside_literals() strips real
# `--` comments while walking single-quoted string literals correctly
# (doubled '' = an escaped quote, matching lit()/psql convention), so
# content genuinely inside a string literal is preserved verbatim.
strip_sql_comments_outside_literals() {
  python3 -c '
import sys
s = sys.stdin.read()
out = []
i, n = 0, len(s)
in_str = False
while i < n:
    c = s[i]
    if in_str:
        if c == "\x27":
            if i + 1 < n and s[i + 1] == "\x27":
                out.append("\x27\x27"); i += 2; continue
            in_str = False
        out.append(c); i += 1; continue
    if c == "\x27":
        in_str = True
        out.append(c); i += 1; continue
    if c == "-" and i + 1 < n and s[i + 1] == "-":
        j = s.find("\n", i)
        i = n if j == -1 else j
        continue
    out.append(c); i += 1
sys.stdout.write("".join(out))
'
}
STRIPPED="$(strip_sql_comments_outside_literals < "$SQL_TMP")"
# GUARDs 1 and 1b additionally scan a literal-stripped copy: a data value can
# legitimately contain "...done; begin next phase..." (demo/narrative text)
# and that must not read as SQL. Comments are stripped the same
# literal-aware way first, THEN literals are blanked, so a "--" inside
# prose can't eat a later real statement either. GUARD 2 (emails)
# deliberately keeps scanning $STRIPPED (comments removed, literals intact),
# since the values it's checking for LIVE inside string literals.
STRIPPED_NOLIT="$(echo "$STRIPPED" | sed "s/'[^']*'/''/g")"
if [[ "$ALLOW_DDL" != "1" ]]; then
  DDL_HITS="$(echo "$STRIPPED_NOLIT" | grep -inE '\b(create|drop|alter|truncate|grant|revoke)\b' || true)"
  if [[ -n "$DDL_HITS" ]]; then
    echo "ABORT: seed contains DDL/privilege statements:" >&2
    echo "$DDL_HITS" | head -10 | sed 's/^/    /' >&2
    echo "Seeds are data-only. Schema → migrate-prod.sh. Override: --allow-ddl" >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# GUARD 1b — no transaction control in a seed. The runner owns the envelope
# (BEGIN … ROLLBACK/COMMIT); an embedded COMMIT would end the outer
# transaction early, everything after would run in autocommit, and --dry-run
# would silently WRITE TO PROD while reporting "nothing committed". No
# override flag on purpose — there is no legitimate reason for a seed to
# manage its own transaction. Anchored to statement starts ((^|;)) so
# CASE … END expressions don't false-positive; bare `END;` (COMMIT synonym)
# is left to the runtime savepoint canary below for the same reason.
# ---------------------------------------------------------------------------
TXN_HITS="$(echo "$STRIPPED_NOLIT" | grep -inE '(^|;)[[:space:]]*(begin|commit|rollback|savepoint|release|start[[:space:]]+transaction|end[[:space:]]+(transaction|work)|prepare[[:space:]]+transaction)\b' || true)"
if [[ -n "$TXN_HITS" ]]; then
  echo "ABORT: seed contains transaction-control statements:" >&2
  echo "$TXN_HITS" | head -10 | sed 's/^/    /' >&2
  echo "The runner wraps seeds in its own transaction (that is what makes" >&2
  echo "--dry-run safe). Remove BEGIN/COMMIT/ROLLBACK/SAVEPOINT from the seed." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# GUARD 2 — reserved email domains only (RFC 2606/6761). Realistic fake
# domains resolve, Gmail attempts delivery, bounces flood the sender for days.
# ---------------------------------------------------------------------------
if [[ "$ALLOW_REAL_EMAILS" != "1" ]]; then
  BAD_EMAILS="$(echo "$STRIPPED" \
    | grep -ioE '[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}' \
    | grep -ivE '@(example\.(com|org|net)|[a-z0-9.-]+\.(test|invalid|localhost))$' \
    | sort -u || true)"
  if [[ -n "$BAD_EMAILS" ]]; then
    echo "ABORT: seed contains non-reserved email domains (bounce-storm risk):" >&2
    echo "$BAD_EMAILS" | head -10 | sed 's/^/    /' >&2
    echo "Use @example.com / @*.test / @*.invalid. Override (e.g. your own" >&2
    echo "real gmail alias, deliberately): --allow-real-emails" >&2
    exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Target resolution + tunnel (same pattern as prod-psql.sh / migrate-prod.sh).
# ---------------------------------------------------------------------------
if [[ "$DEV" == "1" ]]; then
  LABEL="LOCAL DEV (matcha-postgres :5432)"
  URL="${DATABASE_URL:-$(env_val DATABASE_URL)}"
  URL="${URL:-postgresql://matcha:matcha_dev@127.0.0.1:5432/matcha}"
else
  LABEL="LIVE PROD (RDS matcha-prod via app EC2)"
  LOCAL_PORT=5434
  FORWARD="${LOCAL_PORT}:${RDS_HOST}:5432"
  URL="${PROD_DATABASE_URL:-$(env_val PROD_DATABASE_URL)}"
  : "${URL:?Add PROD_DATABASE_URL=postgresql://matcha:pass@localhost:5434/matcha?sslmode=require to server/.env}"
  if lsof -n -P -iTCP:"$LOCAL_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Reusing existing tunnel on localhost:${LOCAL_PORT}."
  else
    echo "Opening SSH tunnel ${APP_EC2} (${FORWARD})..."
    ssh -i "$PEM" -L "$FORWARD" "$APP_EC2" -N -f -o ExitOnForwardFailure=yes
    trap 'rm -f "$SQL_TMP"; pkill -f "ssh.*${FORWARD}" 2>/dev/null; exit' EXIT INT TERM
    sleep 1
  fi
fi

ACTION="SEED"; [[ "$UNDO" == "1" ]] && ACTION="UNDO"
MODE="APPLY";  [[ "$DRY_RUN" == "1" ]] && MODE="DRY-RUN (rolled back)"
echo
echo "  Target : $LABEL"
echo "  File   : $SEEDFILE"
echo "  Action : $ACTION — $MODE"
echo "  SQL    : $(grep -cE '^\s*(insert|update|delete)' <<<"$(echo "$STRIPPED" | tr '[:upper:]' '[:lower:]')" || true) mutation statement(s), $(wc -l < "$SQL_TMP" | tr -d ' ') lines"
echo

# ---------------------------------------------------------------------------
# GUARD 4 — typed confirmation for real prod writes.
#
# --yes bypasses this ONLY when MATCHA_SYNC_AUTONOMOUS=1 is also set (double
# key — see the --yes help text above). Any other combination falls through
# to the normal prompt, including a bare --yes with the env var unset.
# ---------------------------------------------------------------------------
if [[ "$DEV" != "1" && "$DRY_RUN" != "1" && ! ("$ASSUME_YES" == "1" && "${MATCHA_SYNC_AUTONOMOUS:-}" == "1") ]]; then
  read -r -p "This WRITES TO LIVE PROD. Type 'seed prod' to proceed: " confirm
  if [[ "$confirm" != "seed prod" ]]; then
    echo "Aborted. Nothing was applied."
    exit 1
  fi
elif [[ "$DEV" != "1" && "$DRY_RUN" != "1" ]]; then
  echo "GUARD 4 bypassed: --yes + MATCHA_SYNC_AUTONOMOUS=1 (autonomous test-tenant sync)."
fi

# ---------------------------------------------------------------------------
# GUARD 3 — single transaction. Dry-run = same execution, ROLLBACK at the end.
#
# The savepoint is a runtime canary backing up GUARD 1b: if the seed somehow
# smuggles in its own COMMIT (a form the regex missed), the savepoint dies
# with the original transaction and the RELEASE errors — so the runner can
# never claim "nothing committed" when something was.
# ---------------------------------------------------------------------------
RUN_TMP="$(mktemp -t seed-prod-run.XXXXXX.sql)"
{
  echo "BEGIN;"
  echo "SAVEPOINT seed_guard;"
  cat "$SQL_TMP"
  echo "RELEASE SAVEPOINT seed_guard;"
  if [[ "$DRY_RUN" == "1" ]]; then echo "ROLLBACK;"; else echo "COMMIT;"; fi
} > "$RUN_TMP"

PSQL_ERR="$(mktemp -t seed-prod-err.XXXXXX)"
if psql "$URL" -v ON_ERROR_STOP=1 -f "$RUN_TMP" 2>"$PSQL_ERR"; then
  cat "$PSQL_ERR" >&2
  rm -f "$RUN_TMP" "$PSQL_ERR"
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "Dry-run PASSED — every statement executed, nothing committed."
  else
    echo "$ACTION applied to: $LABEL"
  fi
else
  cat "$PSQL_ERR" >&2
  # ON_ERROR_STOP halts at the FIRST error, so an error mentioning SAVEPOINT
  # can only be the canary itself failing ("can only be used in transaction
  # blocks" / "does not exist") — i.e. the seed destroyed the envelope.
  # A seed's own error can't mention savepoints; GUARD 1b bans them from seeds.
  if grep -qi 'savepoint' "$PSQL_ERR" 2>/dev/null; then
    rm -f "$RUN_TMP" "$PSQL_ERR"
    echo "FAILED — seed broke the transaction envelope (embedded COMMIT?)." >&2
    echo "Data MAY have been committed. Inspect the DB before re-running." >&2
    exit 1
  fi
  rm -f "$RUN_TMP" "$PSQL_ERR"
  echo "FAILED — transaction rolled back, nothing was applied." >&2
  exit 1
fi
