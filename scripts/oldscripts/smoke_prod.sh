#!/usr/bin/env bash
# Post-deploy smoke test for the four fixes that have been shipped to prod
# but were reported as still broken. Run after any backend deploy to verify
# the live image actually serves the corrected behavior.
#
# Usage:
#   TOKEN=<jwt> bash scripts/smoke_prod.sh
#   TOKEN=<jwt> PID=<project-uuid> TID=<task-uuid> BLOG_PID=<blog-project-uuid> bash scripts/smoke_prod.sh
#
# Env:
#   API       — base URL, default https://hey-matcha.com/api
#   TOKEN     — Bearer JWT (required for any auth'd check)
#   PID, TID  — kanban project + task UUIDs (skipped if unset)
#   BLOG_PID  — blog project UUID (skipped if unset)
#
# Exits non-zero if any check fails.

set -u

API="${API:-https://hey-matcha.com/api}"
TOKEN="${TOKEN:-}"
PASS=0
FAIL=0

pass() { echo "[PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "[FAIL] $1"; echo "       $2"; FAIL=$((FAIL+1)); }
skip() { echo "[SKIP] $1 ($2)"; }

require_token() {
    if [ -z "$TOKEN" ]; then
        skip "$1" "TOKEN env var not set"
        return 1
    fi
}

# ─────────────────────────────────────────────────────────────────────
# 1. Compliance baseline calendar
# ─────────────────────────────────────────────────────────────────────
check_compliance_calendar() {
    local name="compliance/calendar baseline rows"
    require_token "$name" || return
    local body
    body=$(curl -s -H "Authorization: Bearer $TOKEN" "$API/compliance/calendar")
    if echo "$body" | grep -q '"baseline:fed:'; then
        pass "$name"
    else
        fail "$name" "no baseline:fed:* ids in response — image lacks compliance_baseline.py or merge filter dropped them"
    fi
}

# ─────────────────────────────────────────────────────────────────────
# 2. Invite search — both encoded and unencoded `+`
# ─────────────────────────────────────────────────────────────────────
check_invitable_users() {
    local name_a="channels/invitable-users (%2B encoded)"
    local name_b="channels/invitable-users (raw +, Starlette decodes as space)"
    require_token "$name_a" || return

    local code_a
    code_a=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API/channels/invitable-users?q=tessu2022%2Bmon%40gmail.com")
    if [ "$code_a" = "200" ]; then
        pass "$name_a"
    else
        fail "$name_a" "HTTP $code_a (expected 200)"
    fi

    local code_b
    code_b=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        --get --data-urlencode "q=tessu2022 mon@gmail.com" \
        "$API/channels/invitable-users")
    if [ "$code_b" = "200" ]; then
        pass "$name_b"
    else
        fail "$name_b" "HTTP $code_b (expected 200) — workaround for raw + → space missing"
    fi
}

# ─────────────────────────────────────────────────────────────────────
# 3. Kanban PATCH (asyncpg ambiguous param fix)
# ─────────────────────────────────────────────────────────────────────
check_kanban_patch() {
    local name="matcha-work kanban PATCH (asyncpg \$3::text fix)"
    require_token "$name" || return
    if [ -z "${PID:-}" ] || [ -z "${TID:-}" ]; then
        skip "$name" "PID and TID env vars not set"
        return
    fi

    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" \
        -X PATCH \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"board_column":"done","status":"completed"}' \
        "$API/matcha-work/projects/$PID/tasks/$TID")
    if [ "$code" = "200" ]; then
        pass "$name"
    else
        fail "$name" "HTTP $code (expected 200) — pre-fix returned 500 with AmbiguousParameterError in container logs"
    fi
}

# ─────────────────────────────────────────────────────────────────────
# 4. PDF export (fontconfig + memory)
# ─────────────────────────────────────────────────────────────────────
check_pdf_export() {
    local name="matcha-work blog PDF export"
    require_token "$name" || return
    if [ -z "${BLOG_PID:-}" ]; then
        skip "$name" "BLOG_PID env var not set"
        return
    fi

    local tmp
    tmp=$(mktemp -t pdf_smoke.XXXXXX)
    local code
    code=$(curl -s -o "$tmp" -w "%{http_code}" \
        -H "Authorization: Bearer $TOKEN" \
        "$API/matcha-work/projects/$BLOG_PID/export/pdf")
    if [ "$code" = "200" ] && head -c 4 "$tmp" | grep -q '%PDF'; then
        pass "$name"
    else
        local snippet
        snippet=$(head -c 200 "$tmp" 2>/dev/null | tr -d '\0')
        fail "$name" "HTTP $code, body starts with: $snippet"
    fi
    rm -f "$tmp"
}

echo "Smoke testing $API"
echo "──────────────────────────────────────────────────"
check_compliance_calendar
check_invitable_users
check_kanban_patch
check_pdf_export
echo "──────────────────────────────────────────────────"
echo "Result: $PASS pass, $FAIL fail"
[ "$FAIL" -eq 0 ]
