#!/usr/bin/env bash
# Shared helpers for scripts/kanban-autopr/*.sh. Source, don't execute.
set -uo pipefail

die() {
    printf 'kanban-autopr: %s\n' "$1" >&2
    exit 1
}

# Sources ~/.config/matcha-autopr/env (chmod 600, never committed, never a
# GitHub secret — see docs/ops/KANBAN_AUTOPR.md) and hard-fails on any
# missing key, mirroring error-autofix's fail-loud posture on missing
# SSH_KEY.
_kanban_autopr_load_env() {
    local env_file="${MATCHA_AUTOPR_ENV:-$HOME/.config/matcha-autopr/env}"
    [ -f "$env_file" ] || die "missing config: $env_file"
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
    for key in MATCHA_API_URL MATCHA_BOT_EMAIL MATCHA_BOT_PASSWORD MATCHA_PROJECT_IDS MATCHA_ASSIGNEE_EMAIL; do
        [ -n "${!key:-}" ] || die "missing config key: $key (in $env_file)"
    done
}

# Logs in once per job and caches the access token in $RUNNER_TEMP (falls
# back to a per-process tmp dir outside CI) so every script in the pipeline
# reuses the same token instead of re-authenticating.
mw_login() {
    _kanban_autopr_load_env
    local cache_dir="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
    local token_file="$cache_dir/matcha-autopr-token"
    if [ -s "$token_file" ]; then
        cat "$token_file"
        return
    fi
    local resp token
    resp="$(curl -sS -X POST "$MATCHA_API_URL/auth/login" \
        -H 'Content-Type: application/json' \
        -d "$(jq -n --arg email "$MATCHA_BOT_EMAIL" --arg password "$MATCHA_BOT_PASSWORD" \
            '{email: $email, password: $password}')")"
    token="$(printf '%s' "$resp" | jq -r '.access_token // empty')"
    [ -n "$token" ] || die "login failed: $(printf '%s' "$resp" | jq -c '.detail // .' 2>/dev/null || echo "$resp")"
    printf '%s' "$token" > "$token_file"
    printf '%s' "$token"
}

# mw_api METHOD PATH [JSON_BODY]
# Emits the response body on stdout; a non-2xx status is fatal.
mw_api() {
    local method="$1" path="$2" body="${3:-}"
    local token status body_file
    token="$(mw_login)"
    body_file="$(mktemp)"
    if [ -n "$body" ]; then
        status="$(curl -sS -o "$body_file" -w '%{http_code}' -X "$method" "$MATCHA_API_URL$path" \
            -H "Authorization: Bearer $token" -H 'Content-Type: application/json' \
            -d "$body")"
    else
        status="$(curl -sS -o "$body_file" -w '%{http_code}' -X "$method" "$MATCHA_API_URL$path" \
            -H "Authorization: Bearer $token")"
    fi
    if [[ "$status" != 2* ]]; then
        die "$method $path -> HTTP $status: $(cat "$body_file")"
    fi
    cat "$body_file"
    rm -f "$body_file"
}

mw_move_card() {
    local project_id="$1" task_id="$2" column="$3"
    mw_api PATCH "/matcha-work/projects/$project_id/tasks/$task_id" \
        "$(jq -n --arg col "$column" '{board_column: $col}')" >/dev/null
}
