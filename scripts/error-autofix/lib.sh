#!/usr/bin/env bash
# Shared helpers for scripts/error-autofix/*.sh. Source, don't execute.
set -uo pipefail

PROD_HOST="${PROD_HOST:-54.177.107.107}"
PROD_USER="${PROD_USER:-ec2-user}"

die() {
    printf 'error-autofix: %s\n' "$1" >&2
    exit 1
}

# Run a remote bash script (read from stdin) over SSH against the prod host.
# Stubbed by scripts/tests/test_error_autofix.sh via a fake `ssh` on PATH.
ssh_prod() {
    : "${SSH_KEY:?SSH_KEY must point to the EC2 private key}"
    ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        "$PROD_USER@$PROD_HOST" bash -s
}

# Emits the docker invocation used to find the live blue-green backend container.
# Same pattern as collect-silent-error-evidence.sh and scripts/logs.sh.
resolve_backend_container_cmd() {
    printf "docker ps --format '{{.Names}}' | grep '^matcha-backend' | head -n 1"
}

# Redact free-text fields only. Lifted verbatim from the sed pipeline in
# collect-silent-error-evidence.sh so there is exactly one copy. Do NOT run
# this over structural fields (ids, occurrence counts, timestamps) — the UUID
# rule eats a row's own `id` and the 7+-digit rule mangles `occurrences`.
redact_stream() {
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
        -e 's/[0-9]{7,}/[NUMBER]/g'
}

# Rid normalization for dedup signatures (mirrors the fix in
# silent-error-autofix.yml's "Derive incident identity" step).
redact_rid() {
    sed -E 's/\[rid=[^]]*\]/[rid=RID]/g'
}
