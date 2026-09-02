#!/usr/bin/env bash
# Revalidate the model result, then atomically upsert only fixed changelog
# columns through the active backend's own production DB connection.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAN="${1:?usage: publish.sh PLAN DRAFT RECEIPT}"
DRAFT="${2:?missing validated draft}"
RECEIPT="${3:?missing receipt path}"
SSH_KEY="${SSH_KEY:?SSH_KEY must point to the production SSH key}"
PROD_HOST="${PROD_HOST:-54.177.107.107}"
PROD_USER="${PROD_USER:-ec2-user}"
REVALIDATED="$(mktemp "${RUNNER_TEMP:-/tmp}/admin-updates-revalidated.XXXXXX.json")"
trap 'rm -f "$REVALIDATED"' EXIT

python3 "$SCRIPT_DIR/validate.py" "$PLAN" "$DRAFT" "$REVALIDATED"
payload="$(base64 < "$REVALIDATED" | tr -d '\n')"
publisher="$(<"$SCRIPT_DIR/_publish.py")"

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$PROD_USER@$PROD_HOST" "bash -s" > "$RECEIPT" <<REMOTE
set -euo pipefail
container=\$(docker ps --format '{{.Names}}' | grep '^matcha-backend' | head -n 1)
[ -n "\$container" ] || { echo 'no active backend container' >&2; exit 1; }
docker exec -i -e ADMIN_UPDATES_PAYLOAD_B64='$payload' "\$container" python - <<'PYEOF'
$publisher
PYEOF
REMOTE

jq -e --argjson target "$(jq '.targetWatermark' "$PLAN")" \
    '.processed_through_pr >= $target and (.inserted.matcha | type == "number") and (.inserted.tellus | type == "number")' \
    "$RECEIPT" >/dev/null
printf 'Published production admin updates through PR #%s\n' "$(jq -r '.processed_through_pr' "$RECEIPT")"
