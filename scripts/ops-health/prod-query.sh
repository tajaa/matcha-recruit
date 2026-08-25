#!/usr/bin/env bash
# Emit a narrow, read-only JSON view of production through the active backend.
set -euo pipefail

MODE="${1:?usage: prod-query.sh domains|errors}"
case "$MODE" in
    domains|errors) ;;
    *) echo "unknown mode: $MODE" >&2; exit 2 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_KEY="${SSH_KEY:?SSH_KEY must point to the production SSH key}"
PROD_HOST="${PROD_HOST:-54.177.107.107}"
PROD_USER="${PROD_USER:-ec2-user}"
QUERY="$(<"$SCRIPT_DIR/_prod_query.py")"

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$PROD_USER@$PROD_HOST" "bash -s" <<REMOTE
set -euo pipefail
container=\$(docker ps --format '{{.Names}}' | grep '^matcha-backend' | head -n 1)
[ -n "\$container" ] || { echo 'no active backend container' >&2; exit 1; }
docker exec -i "\$container" python - "$MODE" <<'PYEOF'
$QUERY
PYEOF
REMOTE
