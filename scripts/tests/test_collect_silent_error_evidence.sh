#!/usr/bin/env bash
# Exercise the collector through stubbed SSH and curl so its redaction boundary
# is tested without connecting to production. Run:
#   ./scripts/tests/test_collect_silent_error_evidence.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COLLECTOR="$REPO_ROOT/scripts/collect-silent-error-evidence.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

mkdir "$TMP_DIR/bin"
cat > "$TMP_DIR/bin/ssh" <<'EOF'
#!/usr/bin/env bash
cat <<'LOG'
Authorization: Bearer bearer-secret
Cookie: session=super-secret; preferences=private
X-API-Key: api-key-secret
Basic basic-secret
POST https://username:password@example.invalid/error?unknown_secret=exposed
body={"password":"database-password","customer_id":123456789}
user@example.com 203.0.113.10 2001:db8::1 123e4567-e89b-12d3-a456-426614174000
AKIA1234567890ABCDEF ghp_abcdefghijklmno eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature
LOG
EOF
cat > "$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$TMP_DIR/bin/ssh" "$TMP_DIR/bin/curl"

EVIDENCE_FILE="$TMP_DIR/evidence.txt"
export EVIDENCE_FILE
PATH="$TMP_DIR/bin:$PATH" \
  SSH_KEY="$TMP_DIR/key.pem" \
  "$COLLECTOR"

for secret in bearer-secret super-secret api-key-secret basic-secret exposed database-password 123456789 user@example.com 203.0.113.10 2001:db8::1 123e4567-e89b-12d3-a456-426614174000 AKIA1234567890ABCDEF ghp_abcdefghijklmno eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature; do
  if grep -qF "$secret" "$EVIDENCE_FILE"; then
    echo "FAIL: unredacted value: $secret"
    exit 1
  fi
done

for marker in '[REDACTED]' '[QUERY_REDACTED]' '[EMAIL]' '[IP]' '[UUID]' '[NUMBER]' '[AWS_KEY_REDACTED]' '[GITHUB_TOKEN_REDACTED]' '[JWT_REDACTED]'; do
  if ! grep -qF "$marker" "$EVIDENCE_FILE"; then
    echo "FAIL: missing redaction marker: $marker"
    exit 1
  fi
done

echo "PASS: collector redacts sensitive evidence"
