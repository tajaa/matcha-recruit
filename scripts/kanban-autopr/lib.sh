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

# A card whose criteria are already met, on a run forbidden from saying so,
# produces a diff that changes nothing real. PR #418 shipped exactly one such
# line: a nav label reworded while the route, the row, and the feature gate it
# asked for had all existed for weeks. Only meaningful when the card asked for
# structure — a card that genuinely asks for a copy change has the same shape
# and is legitimate.
#
# autopr_cosmetic_only_diff DIFF_COMMAND_OUTPUT_FILE TITLE DESCRIPTION
# Returns 0 when the diff is a string-literal reword of a structure card.
autopr_cosmetic_only_diff() {
    local diff_file="$1" title="$2" description="$3" script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [ -s "$diff_file" ] || return 1
    printf '%s\n%s' "$title" "$description" \
        | grep -Eqi '\b(route|router|sidebar|nav|navigation|menu|endpoint|expose|register|wire up)\b' \
        || return 1
    python3 "$script_dir/cosmetic_diff.py" < "$diff_file"
}

# The only shape the bot may create under server/alembic/: a NEW version file
# named for its revision id. A leading underscore is excluded so
# `__init__.py` — the one file the graph loader skips, and therefore the one
# file no validation would inspect — can never be staged as "a migration".
AUTOPR_MIGRATION_DRAFT_RE='^server/alembic/versions/[A-Za-z0-9][A-Za-z0-9_]*\.py$'

# autopr_migration_draft_errors REPO_ROOT BASE_REF
# Prints every reason the working tree's server/alembic/ changes could not be
# published (one per line) and returns 1; returns 0 silently when there is
# nothing to publish or the drafts are valid.
#
# investigate.sh calls this right after the model pass so an unpublishable
# migration costs one corrective retry, and publish.sh calls it as the hard
# gate. Sharing the check is the point: two copies would eventually disagree
# about what the model was told, and only the publisher's copy discards the
# run.
autopr_migration_draft_errors() {
    local repo_root="$1" base_ref="$2"
    local script_dir tracked untracked alembic_paths bad drafts path status errors=""

    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # Cheap pre-check against HEAD, which always resolves: a run that touched
    # no migration at all must not depend on the base ref existing.
    untracked="$(git -C "$repo_root" ls-files --others --exclude-standard -- server/alembic || true)"
    tracked="$(git -C "$repo_root" diff --no-renames --name-only HEAD -- server/alembic || true)"
    [ -n "$untracked$tracked" ] || return 0

    git -C "$repo_root" rev-parse --verify "$base_ref^{commit}" >/dev/null 2>&1 \
        || { printf 'migration safety base is unavailable: %s\n' "$base_ref"; return 1; }

    # Worktree vs base covers staged and unstaged edits alike, so this reads
    # the same before publish.sh's `git add --all` and after it, and it also
    # catches a migration an earlier rework run already committed.
    tracked="$(git -C "$repo_root" diff --no-renames --name-only "$base_ref" -- server/alembic || true)"
    alembic_paths="$(printf '%s\n%s\n' "$tracked" "$untracked" | sed '/^$/d' | sort -u)"
    [ -n "$alembic_paths" ] || return 0

    bad="$(printf '%s\n' "$alembic_paths" | grep -vE "$AUTOPR_MIGRATION_DRAFT_RE" || true)"
    if [ -n "$bad" ]; then
        errors="only new server/alembic/versions/<revision>.py files may change (letters, digits and underscore, no leading underscore):"$'\n'"$bad"$'\n'
    fi

    drafts="$(printf '%s\n' "$alembic_paths" | grep -E "$AUTOPR_MIGRATION_DRAFT_RE" || true)"
    while IFS= read -r path; do
        [ -n "$path" ] || continue
        # Untracked file: no status line at all. Otherwise only "A" (absent
        # from the base ref) is a draft; M/D/R mean a merged migration.
        status="$(git -C "$repo_root" diff --no-renames --name-status "$base_ref" -- "$path" \
            | awk 'NR == 1 {print $1}')"
        [ -z "$status" ] || [ "$status" = A ] \
            || errors="${errors}${path}: migration already present on ${base_ref} may not be edited or deleted"$'\n'
    done <<< "$drafts"

    if [ -z "$errors" ] && [ -n "$drafts" ]; then
        # Intentional word splitting: AUTOPR_MIGRATION_DRAFT_RE guarantees each
        # path is [A-Za-z0-9_/.] only.
        # shellcheck disable=SC2046
        errors="$(cd "$repo_root" && python3 "$script_dir/../alembic_graph_snapshot.py" \
            --check-drafts server/alembic/versions $drafts 2>&1 >/dev/null || true)"
        [ -z "$errors" ] || errors="${errors}"$'\n'
    fi

    [ -n "$errors" ] || return 0
    printf '%s' "$errors"
    return 1
}
