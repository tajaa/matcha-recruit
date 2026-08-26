#!/usr/bin/env bash
# Collect actionable server and browser errors from prod's reporting tables
# (read-only, enforced at the connection level in _query.py) and emit redacted
# incident JSON on stdout.
#
# Usage: SSH_KEY=... ./collect.sh [--hours N] [--limit N] > incidents.json
# Exits 0 with `[]` when nothing is found or the backend container can't be
# resolved. Never queries prod for anything beyond this table.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

HOURS="${AUTOFIX_HOURS:-24}"
LIMIT="${AUTOFIX_LIMIT:-25}"

while [ $# -gt 0 ]; do
    case "$1" in
        --hours) [ $# -ge 2 ] || die "--hours needs a value"; HOURS="$2"; shift 2 ;;
        --limit) [ $# -ge 2 ] || die "--limit needs a value"; LIMIT="$2"; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done

QUERY_PY="$(cat "$SCRIPT_DIR/_query.py")"

# A real SSH/connection failure must be fatal, not silently treated as "no
# errors" — otherwise a prod outage that takes the box unreachable is
# reported by this pipeline as a clean, quiet run.
raw_json="$(
    ssh_prod <<REMOTE
CONTAINER="\$($(resolve_backend_container_cmd))"
if [ -z "\$CONTAINER" ]; then
    echo '{"incidents":[],"skipped_infra":0}'
    exit 0
fi
docker exec -i -e AUTOFIX_HOURS="$HOURS" -e AUTOFIX_LIMIT="$LIMIT" "\$CONTAINER" python - <<'PYEOF'
$QUERY_PY
PYEOF
REMOTE
)"
ssh_rc=$?
if [ "$ssh_rc" -ne 0 ]; then
    die "ssh/docker collection failed (exit $ssh_rc) — prod may be unreachable"
fi

if [ -z "$raw_json" ] || ! printf '%s' "$raw_json" | jq -e . >/dev/null 2>&1; then
    die "collector received non-JSON output from prod"
fi

skipped_infra="$(printf '%s' "$raw_json" | jq -r '.skipped_infra // 0')"
skipped_client="$(printf '%s' "$raw_json" | jq -r '.skipped_client // 0')"
suppressed_correlated="$(printf '%s' "$raw_json" | jq -r '.suppressed_correlated // 0')"
[ "$skipped_infra" -gt 0 ] && printf 'error-autofix: skipped %s infrastructure server errors\n' "$skipped_infra" >&2
[ "$skipped_client" -gt 0 ] && printf 'error-autofix: skipped %s non-actionable client errors\n' "$skipped_client" >&2
[ "$suppressed_correlated" -gt 0 ] && printf 'error-autofix: suppressed %s client API errors correlated to server incidents\n' "$suppressed_correlated" >&2

raw_json="$(printf '%s' "$raw_json" | jq -c '.incidents // []')"

# Redact free-text fields only. stable_key/error_id/occurrences/timestamps are
# structural and must survive byte-for-byte — redact_stream's UUID/digit rules
# would corrupt them.
count="$(printf '%s' "$raw_json" | jq 'length')"
count="${count:-0}"
out="[]"
for ((i = 0; i < count; i++)); do
    incident="$(printf '%s' "$raw_json" | jq -c ".[$i]")"

    redacted_message="$(printf '%s' "$incident" | jq -r '.message // ""' | redact_stream)"
    redacted_traceback="$(printf '%s' "$incident" | jq -r '.traceback // ""' | redact_stream)"
    redacted_path="$(printf '%s' "$incident" | jq -r '.request_path // ""' | redact_stream)"
    redacted_company="$(printf '%s' "$incident" | jq -r '.company_id // ""' | redact_stream)"
    redacted_context="$(printf '%s' "$incident" | jq -r '.context_excerpt // ""' | redact_stream)"

    updated="$(printf '%s' "$incident" | jq -c \
        --arg message "$redacted_message" \
        --arg traceback "$redacted_traceback" \
        --arg request_path "$redacted_path" \
        --arg company_id "$redacted_company" \
        --arg context_excerpt "$redacted_context" \
        '.message = $message | .traceback = $traceback |
         .request_path = $request_path |
         .company_id = (if $company_id == "" then null else $company_id end) |
         .context_excerpt = (if $context_excerpt == "" then null else $context_excerpt end) |
         del(.user_email)')"

    out="$(printf '%s' "$out" | jq -c --argjson item "$updated" '. + [$item]')"
done

printf '%s\n' "$out"
