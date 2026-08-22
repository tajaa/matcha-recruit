#!/usr/bin/env bash
# Collect a small, redacted incident bundle for the self-hosted OpenCode runner.
# It intentionally reads logs only; no production mutation occurs here.
set -euo pipefail

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
sed -E \
  -e 's/[Bb]earer[[:space:]]+[^[:space:]]+/Bearer [REDACTED]/g' \
  -e 's/[Bb]asic[[:space:]]+[^[:space:]]+/Basic [REDACTED]/g' \
  -e 's#(https?://)[^/@[:space:]]+:[^/@[:space:]]+@#\1[USERINFO_REDACTED]@#gI' \
  -e 's/[?][^[:space:]]*/?[QUERY_REDACTED]/g' \
  -e 's/((authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-auth-token)[[:space:]]*[:=][[:space:]]*)[^[:cntrl:]]*/\1[REDACTED]/gI' \
  -e 's/("(password|passwd|secret|token|access_token|refresh_token|api_key|authorization|cookie)"[[:space:]]*:[[:space:]]*)"[^"]*"/\1"[REDACTED]"/gI' \
  -e 's/((password|passwd|secret|token|access_token|refresh_token|api_key|signature|key)[[:space:]]*=[[:space:]]*)[^[:space:],;"]+/\1[REDACTED]/gI' \
  -e 's/(^|[^[:alnum:]_])(AKIA|ASIA)[[:alnum:]]{16}([^[:alnum:]_]|$)/\1[AWS_KEY_REDACTED]\3/g' \
  -e 's/(^|[^[:alnum:]_])(ghp_[[:alnum:]]+|github_pat_[[:alnum:]_]+)([^[:alnum:]_]|$)/\1[GITHUB_TOKEN_REDACTED]\3/g' \
  -e 's/(^|[^[:alnum:]_])eyJ[[:alnum:]_-]+\.[[:alnum:]_-]+\.[[:alnum:]_-]+([^[:alnum:]_]|$)/\1[JWT_REDACTED]\2/g' \
  -e 's/[[:alnum:]._%+-]+@[[:alnum:].-]+\.[[:alpha:]]{2,}/[EMAIL]/g' \
  -e 's/([0-9]{1,3}\.){3}[0-9]{1,3}/[IP]/g' \
  -e 's/([[:xdigit:]]{1,4}:){2,}[[:xdigit:]:]+/[IP]/gI' \
  -e 's/[0-9a-f]{8}-[0-9a-f-]{27,}/[UUID]/gI' \
  -e 's/[0-9]{7,}/[NUMBER]/g' \
  "$EVIDENCE_FILE" > "$tmp_file"
mv "$tmp_file" "$EVIDENCE_FILE"

# Keep model input bounded even during a noisy outage.
if [ "$(wc -c < "$EVIDENCE_FILE")" -gt 50000 ]; then
  head -c 50000 "$EVIDENCE_FILE" > "$tmp_file"
  mv "$tmp_file" "$EVIDENCE_FILE"
fi
