#!/usr/bin/env bash
# Shared helpers for scripts/kanban-autopr/*.sh. Source, don't execute.
set -uo pipefail

KANBAN_AUTOPR_PROD_API_URL="https://hey-matcha.com/api"
KANBAN_AUTOPR_PROJECT_IDS="7f728636-3219-4d83-9df3-a4682e3242de,fade10b4-36ff-4c60-af59-5cc6058285ab,84823d21-c752-4abd-9696-4c93c8b3c21e,8b924347-d6e4-4000-8e7d-ca8f46f76fba"

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

# A GitHub Actions job must never silently build PRs from a developer's
# localhost clone of the board. Local/manual script runs may still point at a
# dev API, but Actions is the production automation and therefore fails closed
# unless both its API and fixed project allowlist match the documented setup.
_kanban_autopr_validate_ci_scope() {
    [ "${GITHUB_ACTIONS:-}" = "true" ] || return 0

    local api_url="${MATCHA_API_URL%/}"
    [ "$api_url" = "$KANBAN_AUTOPR_PROD_API_URL" ] \
        || die "GitHub Actions must use $KANBAN_AUTOPR_PROD_API_URL (got $api_url)"

    local actual expected
    actual="$(printf '%s' "$MATCHA_PROJECT_IDS" | tr ',' '\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | sort | paste -sd, -)"
    expected="$(printf '%s' "$KANBAN_AUTOPR_PROJECT_IDS" | tr ',' '\n' | sort | paste -sd, -)"
    [ "$actual" = "$expected" ] \
        || die "GitHub Actions MATCHA_PROJECT_IDS must contain all four configured Espresso projects"
}

# Every board call must be bounded. The one-minute request watcher makes this
# call from inside a LaunchAgent, and an unbounded curl against a stalled host
# used to be able to sit on the shared dispatch lock until its fifteen-minute
# stale-lock reclaim, starving the production-error and self-audit lanes.
MW_CURL_TIMEOUTS=(--connect-timeout "${MATCHA_API_CONNECT_TIMEOUT:-10}"
                  --max-time "${MATCHA_API_MAX_TIME:-60}")

# Logs in once per job and caches the access token in $RUNNER_TEMP (falls
# back to a per-process tmp dir outside CI) so every script in the pipeline
# reuses the same token instead of re-authenticating.
mw_login() {
    _kanban_autopr_load_env
    local cache_dir="${RUNNER_TEMP:-${TMPDIR:-/tmp}}"
    local cache_identity token_file refresh="${1:-}"
    cache_identity="$(printf '%s' "$MATCHA_BOT_EMAIL" | tr -c '[:alnum:].@_-' '_')"
    token_file="$cache_dir/matcha-autopr-token-$cache_identity"
    if [ "$refresh" != "--refresh" ] && [ -s "$token_file" ]; then
        cat "$token_file"
        return
    fi
    local resp token
    resp="$(curl -sS "${MW_CURL_TIMEOUTS[@]}" -X POST "$MATCHA_API_URL/auth/login" \
        -H 'Content-Type: application/json' \
        -d "$(jq -n --arg email "$MATCHA_BOT_EMAIL" --arg password "$MATCHA_BOT_PASSWORD" \
            '{email: $email, password: $password}')")"
    token="$(printf '%s' "$resp" | jq -r '.access_token // empty')"
    [ -n "$token" ] || die "login failed: $(printf '%s' "$resp" | jq -c '.detail // .' 2>/dev/null || echo "$resp")"
    (umask 077; printf '%s' "$token" > "$token_file")
    chmod 600 "$token_file"
    printf '%s' "$token"
}

_mw_api_request() {
    local method="$1" path="$2" body="$3" token="$4" body_file="$5"
    local -a args=(-sS "${MW_CURL_TIMEOUTS[@]}" -o "$body_file" -w '%{http_code}'
        -X "$method" "$MATCHA_API_URL$path"
        -H "Authorization: Bearer $token" -H 'Content-Type: application/json')
    [ -z "$body" ] || args+=(-d "$body")
    curl "${args[@]}"
}

# mw_api METHOD PATH [JSON_BODY]
# Emits the response body on stdout; a non-2xx status is fatal.
mw_api() {
    local method="$1" path="$2" body="${3:-}"
    local token status body_file

    # `token="$(mw_login)"` executes mw_login in a subshell. Environment
    # variables sourced only inside that command substitution disappear before
    # the curl below runs, which previously made publish.sh die with
    # `MATCHA_API_URL: unbound variable` after it had already opened the PR.
    _kanban_autopr_load_env
    _kanban_autopr_validate_ci_scope
    token="$(mw_login)"
    body_file="$(mktemp)"
    status="$(_mw_api_request "$method" "$path" "$body" "$token" "$body_file")"
    if [ "$status" = "401" ]; then
        # Tokens can expire between scheduled runs, and the configured API
        # identity can change. Re-authenticate once and retry the request;
        # a 401 means the server rejected it before applying any mutation.
        token="$(mw_login --refresh)"
        status="$(_mw_api_request "$method" "$path" "$body" "$token" "$body_file")"
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
