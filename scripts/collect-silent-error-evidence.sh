#!/usr/bin/env bash
# Collect a small, redacted incident bundle for the self-hosted OpenCode runner.
# It intentionally reads logs only; no production mutation occurs here.
#
# Fallback source for scripts/error-autofix/collect.sh (which reads
# server_error_reports directly) when that DB path is unreachable.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./error-autofix/lib.sh
source "$SCRIPT_DIR/error-autofix/lib.sh"

: "${SSH_KEY:?SSH_KEY must point to the EC2 private key}"

PROD_HOST="${PROD_HOST:-54.177.107.107}"
PROD_USER="${PROD_USER:-ec2-user}"
WINDOW_MINUTES="${WINDOW_MINUTES:-20}"
EVIDENCE_FILE="${EVIDENCE_FILE:-silent-error-evidence.txt}"

ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$PROD_USER@$PROD_HOST" \
  "WINDOW_MINUTES='$WINDOW_MINUTES' bash -s" <<'REMOTE' > "$EVIDENCE_FILE"
set -uo pipefail

container_logs() {
  local prefix="$1"
  local container
  local signals
  container="$(docker ps --format '{{.Names}}' | grep "^${prefix}" | head -n 1 || true)"
  [ -n "$container" ] || return 0
  signals="$(docker logs --since "${WINDOW_MINUTES}m" --timestamps "$container" 2>&1 \
    | grep -E 'ERROR|Traceback|" 5[0-9][0-9] ' || true)"
  if [ -n "$signals" ]; then
    printf '=== %s log signals ===\n%s\n' "$prefix" "$signals"
  fi
}

container_logs matcha-backend
container_logs matcha-worker

nginx_5xx="$(sudo tail -n 5000 /var/log/nginx/access.log 2>/dev/null \
  | grep -E '" [5][0-9][0-9] ' || true)"
if [ -n "$nginx_5xx" ]; then
  printf '=== nginx 5xx ===\n%s\n' "$nginx_5xx"
fi

nginx_errors="$(sudo tail -n 1000 /var/log/nginx/error.log 2>/dev/null \
  | grep -Ei 'error|crit|alert|emerg' || true)"
if [ -n "$nginx_errors" ]; then
  printf '=== nginx errors ===\n%s\n' "$nginx_errors"
fi
REMOTE

for url in "${PROD_HEALTH_URL:-}" "${PROD_API_HEALTH_URL:-}"; do
  [ -n "$url" ] || continue
  if ! curl --fail --silent --show-error --max-time 15 "$url" >/dev/null; then
    printf '=== health check failed ===\n%s\n' "$url" >> "$EVIDENCE_FILE"
  fi
done

# Strip credentials and common customer identifiers before model access. The model
# receives no raw URL query strings, auth headers, cookies, emails, IPs, UUIDs,
# or long numeric identifiers. Timestamps are normalized later by the workflow.
tmp_file="${EVIDENCE_FILE}.redacted"
redact_stream < "$EVIDENCE_FILE" > "$tmp_file"
mv "$tmp_file" "$EVIDENCE_FILE"

# Keep model input bounded even during a noisy outage.
if [ "$(wc -c < "$EVIDENCE_FILE")" -gt 50000 ]; then
  head -c 50000 "$EVIDENCE_FILE" > "$tmp_file"
  mv "$tmp_file" "$EVIDENCE_FILE"
fi
