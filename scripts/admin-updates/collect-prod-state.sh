#!/usr/bin/env bash
# Read the narrow changelog automation state through the active production
# backend. No content rows, credentials, or unrestricted SQL reach the model.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY="${SSH_KEY:?SSH_KEY must point to the production SSH key}"
PROD_HOST="${PROD_HOST:-54.177.107.107}"
PROD_USER="${PROD_USER:-ec2-user}"
QUERY="$(<"$SCRIPT_DIR/_prod_state.py")"

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$PROD_USER@$PROD_HOST" "bash -s" <<REMOTE
set -euo pipefail
container=\$(docker ps --format '{{.Names}}' | grep '^matcha-backend' | head -n 1)
[ -n "\$container" ] || { echo 'no active backend container' >&2; exit 1; }
docker exec -i "\$container" python - <<'PYEOF'
$QUERY
PYEOF
REMOTE
