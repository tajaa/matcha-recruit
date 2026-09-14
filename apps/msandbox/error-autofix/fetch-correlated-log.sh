#!/usr/bin/env bash
# Best-effort enrichment: log lines correlated to an incident's request_id.
# Error-row writes are fire-and-forget, so this is supplementary context, not
# the primary evidence — failure here must never block the investigation.
# Run BEFORE the prod SSH key is deleted; investigate.sh itself has no
# network access.
#
# Usage: ./fetch-correlated-log.sh incident.json > correlated-log.txt
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

INCIDENT_FILE="${1:?usage: fetch-correlated-log.sh incident.json}"
request_id="$(jq -r '.request_id // empty' "$INCIDENT_FILE")"

if [ -z "$request_id" ] || [ -z "${SSH_KEY:-}" ]; then
    exit 0
fi

# The id is interpolated into a shell command that runs on the production
# host. Server ids are minted by app.core.request_context; a CLIENT incident's
# id comes from the free-form `context` dict of the unauthenticated
# POST /api/client-errors endpoint, so it is attacker-controlled. _query.py
# already drops non-conforming ids, and this is the last line of defense:
# refuse anything outside the safe alphabet rather than quote around it.
if ! [[ "$request_id" =~ ^[A-Za-z0-9-]{4,64}$ ]]; then
    printf 'error-autofix: ignoring request_id with unsafe characters\n' >&2
    exit 0
fi

ssh_prod <<REMOTE 2>/dev/null | redact_stream || true
CONTAINER="\$($(resolve_backend_container_cmd))"
[ -n "\$CONTAINER" ] && docker logs --since 2h "\$CONTAINER" 2>&1 | grep -F -- "[rid=$request_id]" | head -n 200
REMOTE
