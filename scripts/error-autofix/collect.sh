#!/usr/bin/env bash
# Collect unresolved backend errors from prod's server_error_reports table
# (read-only, enforced at the connection level in _query.py) and emit them as
# redacted JSON on stdout.
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
        --hours) HOURS="$2"; shift 2 ;;
        --limit) LIMIT="$2"; shift 2 ;;
        *) die "unknown argument: $1" ;;
    esac
done

QUERY_PY="$(cat "$SCRIPT_DIR/_query.py")"

raw_json="$(
    ssh_prod <<REMOTE
CONTAINER="\$($(resolve_backend_container_cmd))"
if [ -z "\$CONTAINER" ]; then
    echo '[]'
    exit 0
fi
docker exec -i -e AUTOFIX_HOURS="$HOURS" -e AUTOFIX_LIMIT="$LIMIT" "\$CONTAINER" python - <<'PYEOF'
$QUERY_PY
PYEOF
REMOTE
)"

if [ -z "$raw_json" ]; then
    echo '[]'
    exit 0
fi

if ! printf '%s' "$raw_json" | jq -e . >/dev/null 2>&1; then
    die "collector received non-JSON output from prod"
fi

skipped_infra="$(printf '%s' "$raw_json" | jq -r '.skipped_infra // 0')"
[ "$skipped_infra" -gt 0 ] && printf 'error-autofix: skipped %s infra-kind errors (not autofixable)\n' "$skipped_infra" >&2

raw_json="$(printf '%s' "$raw_json" | jq -c '.incidents // []')"

# Redact free-text fields only (message, traceback, request_path). stable_key/
# error_id/occurrences/timestamps are structural and must survive byte-for-
# byte — redact_stream's UUID/digit rules would corrupt them.
count="$(printf '%s' "$raw_json" | jq 'length')"
out="[]"
for ((i = 0; i < count; i++)); do
    incident="$(printf '%s' "$raw_json" | jq -c ".[$i]")"

    redacted_message="$(printf '%s' "$incident" | jq -r '.message // ""' | redact_stream)"
    redacted_traceback="$(printf '%s' "$incident" | jq -r '.traceback // ""' | redact_stream)"
    redacted_path="$(printf '%s' "$incident" | jq -r '.request_path // ""' | redact_stream)"
    redacted_company="$(printf '%s' "$incident" | jq -r '.company_id // ""' | redact_stream)"

    updated="$(printf '%s' "$incident" | jq -c \
        --arg message "$redacted_message" \
        --arg traceback "$redacted_traceback" \
        --arg request_path "$redacted_path" \
        --arg company_id "$redacted_company" \
        '.message = $message | .traceback = $traceback |
         .request_path = $request_path |
         .company_id = (if $company_id == "" then null else $company_id end) |
         del(.user_email)')"

    out="$(printf '%s' "$out" | jq -c --argjson item "$updated" '. + [$item]')"
done

printf '%s\n' "$out"
