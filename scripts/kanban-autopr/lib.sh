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

# The stored content_type is whatever this says, and the CDN serves the object
# with it — a screenshot announced as text/markdown is a screenshot no consumer
# can render. Derived from the extension rather than pinned, because this helper
# uploads both the report and the browsing run's PNGs.
_mw_upload_content_type() {
    case "${1##*.}" in
        md|markdown) printf 'text/markdown' ;;
        png)         printf 'image/png' ;;
        jpg|jpeg)    printf 'image/jpeg' ;;
        webp)        printf 'image/webp' ;;
        gif)         printf 'image/gif' ;;
        pdf)         printf 'application/pdf' ;;
        txt|log)     printf 'text/plain' ;;
        json)        printf 'application/json' ;;
        *)           printf 'application/octet-stream' ;;
    esac
}

_mw_api_upload_request() {
    local path="$1" file="$2" token="$3" body_file="$4"
    local content_type
    content_type="$(_mw_upload_content_type "$file")"
    # No JSON content type: curl builds the multipart boundary itself. The
    # basename becomes the stored filename, so callers name the file first.
    curl -sS "${MW_CURL_TIMEOUTS[@]}" -o "$body_file" -w '%{http_code}' \
        -X POST "$MATCHA_API_URL$path" \
        -H "Authorization: Bearer $token" \
        -F "file=@$file;type=$content_type"
}

# mw_api_upload PATH FILE
# Multipart upload as the bot (task/project file endpoints). Same login and
# one-shot 401 retry as mw_api; emits the response body, non-2xx is fatal.
mw_api_upload() {
    local path="$1" file="$2"
    local token status body_file
    [ -f "$file" ] || die "upload source is missing: $file"
    _kanban_autopr_load_env
    _kanban_autopr_validate_ci_scope
    token="$(mw_login)"
    body_file="$(mktemp)"
    status="$(_mw_api_upload_request "$path" "$file" "$token" "$body_file")"
    if [ "$status" = "401" ]; then
        token="$(mw_login --refresh)"
        status="$(_mw_api_upload_request "$path" "$file" "$token" "$body_file")"
    fi
    if [[ "$status" != 2* ]]; then
        die "POST $path (multipart) -> HTTP $status: $(cat "$body_file")"
    fi
    cat "$body_file"
    rm -f "$body_file"
}

mw_move_card() {
    local project_id="$1" task_id="$2" column="$3"
    mw_api PATCH "/matcha-work/projects/$project_id/tasks/$task_id" \
        "$(jq -n --arg col "$column" '{board_column: $col}')" >/dev/null
}

# autopr_research_screenshots_required CARD_JSON
# Returns 0 when a Research card explicitly asks the report to include
# screenshots. This is deliberately narrower than "the card mentions a
# screenshot": attached screenshots are commonly input evidence, while this
# flag governs an output deliverable that the trusted harness must enforce.
# A revision note may explicitly waive the original requirement for that
# round; otherwise an original requirement remains in force on every revision.
autopr_research_screenshots_required() {
    local card_json="$1"
    printf '%s' "$card_json" | jq -e '
      def normalized: tostring | ascii_downcase;
      def mentions: test("screenshots?");
      def requests:
        test("(^|[^[:alnum:]_])(include|attach|capture|provide|add|need|want|show)[[:space:]][^\\n.]{0,60}screenshots?")
        or test("screenshots?[^\\n.]{0,60}(from|in|with|for) (the |your )?(report|research|output|deliverable)")
        or test("expected output[\\s\\S]{0,600}screenshots?");
      def waives:
        test("screenshots? (are )?(optional|unnecessary|not (needed|required))"
             + "|no need for screenshots?"
             + "|without screenshots?"
             + "|do not (include|attach|capture|provide|add) screenshots?"
             + "|don.t (include|attach|capture|provide|add) screenshots?"
             + "|skip (the )?screenshots?");
      ((.review_note // "") | normalized) as $review
      | (([.title // "", .description // ""] | join("\n")) | normalized) as $brief
      | if ($review | waives) then false
        elif ($review | mentions) then true
        else (($brief | requests) and (($brief | waives) | not))
        end
    ' >/dev/null 2>&1
}

# autopr_research_screenshot_contract_error REQUIRED REPORT DECISION ARTIFACTS
# Prints the reason a completed research report does not satisfy its requested
# screenshot deliverable and returns 0. Returns 1 when the contract is met or
# does not apply (including a needs_clarification decision).
autopr_research_screenshot_contract_error() {
    local required="$1" report_file="$2" decision_file="$3" artifacts_dir="$4"
    local count=0 unnamed="" shot shot_name
    [ "$required" = true ] || return 1
    [ "$(jq -r '.outcome // empty' "$decision_file" 2>/dev/null)" = research_report ] \
        || return 1
    if [ -d "$artifacts_dir" ]; then
        while IFS= read -r shot; do
            [ -n "$shot" ] || continue
            count=$((count + 1))
            shot_name="$(basename "$shot")"
            if ! grep -qF "$shot_name" "$report_file" 2>/dev/null; then
                unnamed="${unnamed}${unnamed:+, }$shot_name"
            fi
        done < <(find "$artifacts_dir" -maxdepth 1 -type f | sort)
    fi
    if [ "$count" -eq 0 ]; then
        printf 'the card requires screenshots, but the browser produced no admitted image files'
        return 0
    fi
    if [ -n "$unnamed" ]; then
        printf 'the browser produced %s screenshot(s), but the report does not name: %s' "$count" "$unnamed"
        return 0
    fi
    return 1
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

# ---- shared publisher helpers ----------------------------------------------
# Used by every publisher (publish.sh for PR kinds, publish-research.sh and
# publish-email.sh for artifact kinds). They only shape text; the caller owns
# the board write.

# progress_note_with_origin MARKER EXISTING_NOTE
# Replace this system's prior structured prefix instead of nesting it every
# round, and preserve any human-authored text after it.
progress_note_with_origin() {
    local marker="$1" existing="$2" header body preserved remainder
    header="${existing%%$'\n'*}"
    if [ "$header" = "$existing" ]; then
        body=""
    else
        body="${existing#*$'\n'}"
    fi
    if [[ "$header" != "from auto setup"* ]] && [[ "$header" != "🤖 AUTO SETUP"* ]]; then
        # Entirely human-authored: nothing of it is this system's to rewrite.
        header="$existing"
        body=""
    fi
    # Drop only the machine-written blocks below the header: the pause report
    # and the question form (always written last). Everything else on those
    # lines is the operator's and survives the next cycle.
    preserved="$(printf '%s\n' "$body" | awk '
        /^Answers needed — reply below with the numbered choices:/ { exit }
        /^(Why more time|Done so far|Latest progress|Next step):/ { next }
        NF { seen = 1 }
        seen { lines[n++] = $0 }
        END {
            while (n > 0 && lines[n-1] ~ /^[[:space:]]*$/) n--
            for (i = 0; i < n; i++) print lines[i]
        }
    ')"
    remainder="$(printf '%s' "$header" | sed -E \
        's/^from auto setup( · build [^·]+)?( · prod( backend)? [^·]+( \/ frontend [^·]+)?)?( · PR #[0-9]+)?( · [^·]+ C[0-9]+ · (awaiting answers|ready for review|no safe action))?( · \[autopr:directives [^]]+\])?( · \[autopr:no-spec [^]]+\] (already_fixed|acceptance_criteria_met|migration_required|policy_blocked|external_dependency|needs_clarification))?( · note: [^·]+)?( · )?//')"
    # New notes put the state first so the narrow card face shows the reason
    # for a stall before build provenance. Keep accepting the legacy lowercase
    # prefix above so an upgrade does not duplicate an existing human note.
    # PAUSED belongs in this alternation: checkpoint.sh writes it, so without
    # it every recovery run would re-append its own stale pause header here.
    # The same goes for every other machine header (BLOCKED: <reason>,
    # ON HOLD: …, STOPPED: … from run-journal.sh) and the rejected/parked
    # ledger markers: any header this alternation does not recognise survives
    # as a "remainder" and the next cycle prefixes its own state to it.
    remainder="$(printf '%s' "$remainder" | sed -E \
        's/^🤖 AUTO SETUP · (READY FOR REVIEW|BLOCKED: [A-Z0-9_-]+( [A-Z0-9_-]+)*|ON HOLD: [A-Z0-9_-]+( [A-Z0-9_-]+)*|STOPPED: [A-Z0-9_-]+( [A-Z0-9_-]+)*|PAUSED: [A-Z0-9]+( [A-Z0-9]+)*|NO PR: [A-Z_ -]+)( · checkpoint [^·]+)?( · run #[0-9]+)?( · build [^·]+)?( · prod( backend)? [^·]+( \/ frontend [^·]+)?)?( · PR #[0-9]+)?( · [^·]+ C[0-9]+)?( · \[autopr:directives [^]]+\])?( · \[autopr:no-spec [^]]+\] (already_fixed|acceptance_criteria_met|migration_required|policy_blocked|external_dependency|needs_clarification))?( · \[autopr:(rejected|parked) [^]]+\] [A-Za-z0-9_.:-]+( · [^·]+)?)?( · note: [^·]+)?( · )?//')"
    if [ -n "$remainder" ] && [ "$remainder" != "$header" ]; then
        printf '%s · %s' "$marker" "$remainder"
    elif [ -n "$header" ] \
        && [[ "$header" != "from auto setup"* ]] \
        && [[ "$header" != "🤖 AUTO SETUP"* ]]; then
        printf '%s · %s' "$marker" "$header"
    else
        printf '%s' "$marker"
    fi
    [ -z "$preserved" ] || printf '\n%s' "$preserved"
}

# autopr_report_summary REPORT_FILE
# The `### Summary` section flattened to one line, capped at 1200 characters.
autopr_report_summary() {
    awk '
      /^### Summary[[:space:]]*$/ { capture=1; next }
      /^### / && capture { exit }
      capture { print }
    ' "$1" | tr '\n' ' ' | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//' \
        | jq -Rsr '.[0:1200]'
}

# autopr_post_context_request PROJECT_ID TASK_ID REASON EXPECTED_NOTE
# Ask the card owner for a decision in project chat, bound to the exact note
# just written. Non-fatal: the card state is authoritative; chat delivery
# loss is surfaced without rolling back an otherwise complete publication.
autopr_post_context_request() {
    local project_id="$1" task_id="$2" reason="$3" expected_note="$4"
    # Newlines survive: the acceptance-evidence block is the payload here, and
    # flattening it to one line at 600 characters cut the proof off after about
    # four criteria. The server sanitizes and bounds it again.
    reason="$(printf '%s' "$reason" | tr -d '\r' | jq -Rsr '.[0:4000]')"
    if ! (mw_api POST "/matcha-work/projects/$project_id/tasks/$task_id/autopr/context-request" \
        "$(jq -n --arg reason "$reason" --arg note "$expected_note" \
            '{reason:$reason,expected_progress_note:$note}')" >/dev/null); then
        printf 'kanban-autopr: warning: could not post Espresso context request for task %s\n' \
            "$task_id" >&2
    fi
}

# autopr_record_outcome TASK_ID success|failure [REASON]
# The per-card failure ledger behind select.sh's give-up rule. One file per
# card under the attempts dir select.sh already uses for its cooldown:
# `count<TAB>reason<TAB>iso-ts`. The same reason again increments; a different
# reason starts over at 1 (a new failure is new information, not a repeat);
# success deletes the file. The mtime keeps meaning "last attempt" for the
# cooldown, which reads nothing else. Without this ledger a run that dies the
# same way every time — a policy refusal, a verify failure — was re-selected
# every cooldown window forever with nothing on the card.
autopr_record_outcome() {
    local task_id="$1" outcome="$2" reason="${3:-unknown}" id8 dir marker
    local previous_count=0 previous_reason="" count=1
    [ -n "$task_id" ] || return 0
    id8="$(printf '%s' "$task_id" | tr -d '-' | cut -c1-8)"
    dir="${AUTOPR_CACHE_DIR:-$HOME/.cache/matcha-autopr}/attempts"
    marker="$dir/$id8"
    if [ "$outcome" = success ]; then
        rm -f "$marker"
        return 0
    fi
    # One token: the reason lands in a card note and a hold reason verbatim.
    reason="$(printf '%s' "$reason" | tr -c 'A-Za-z0-9_.:-' '_' | cut -c1-64)"
    [ -n "$reason" ] || reason=unknown
    mkdir -p "$dir"
    if [ -f "$marker" ]; then
        IFS=$'\t' read -r previous_count previous_reason _ < "$marker" 2>/dev/null || true
    fi
    if [[ "$previous_count" =~ ^[0-9]+$ ]] && [ "$previous_reason" = "$reason" ]; then
        count=$((previous_count + 1))
    fi
    printf '%s\t%s\t%s\n' "$count" "$reason" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$marker"
}

# autopr_strip_bookkeeping_history HISTORY_JSON
# The lane's own history rows (run requests, claims, staged outreach and its
# outcomes) ride event_type='activity' but are not discussion. They stay in
# the raw history the directive resolver reads; they must not reach the model
# as "what people said" — a research run would otherwise read its own staged
# email drafts back as a teammate's comment on the next round.
autopr_strip_bookkeeping_history() {
    printf '%s' "$1" | jq -c '
      if type == "array" then
        map(select(((.metadata // {}).kind // "")
                   | IN("autopr_run_request", "autopr_run_claim",
                        "autopr_staged_action", "autopr_staged_action_result")
                   | not))
      else . end'
}

# ---- task-kind registry -----------------------------------------------------
# One row per mode the Kanban lane knows how to run. select.sh maps a card to
# a mode; everything downstream (prompt, model, sandbox switches, required
# report headings, decision validator, publisher) is looked up here by mode
# instead of being special-cased in each script. A kind whose deliverable is
# not a PR — a report, a shortlist, staged outreach — is a row here plus a
# publisher, not another branch in the PR path.
#
# autopr_kind_field MODE FIELD  → prints the value; exit 1 on an unknown pair.
#   prompt     template under scripts/kanban-autopr/
#   model      Codex model for the investigation pass
#   effort     Codex reasoning effort
#   sandbox    extra AUTOPR_CODEX_* switches for run-codex-sandboxed.sh (an
#              artifact kind reads the web only if this sets WEB_SEARCH=1)
#   headings   required `### …` headings in report.md, one per line
#   decision   decision.sh subcommand that validates the model's JSON
#   publisher  script that turns the validated result into board/GitHub state
#   outcome    pull_request | artifact (artifact kinds own no branch, no PR)
#   capability the per-board grant this kind needs, or empty for "always on"
autopr_kind_field() {
    local mode="$1" field="$2"
    case "$mode" in
        investigate|rework)
            case "$field" in
                prompt) [ "$mode" = rework ] && printf '_prompt_rework.txt' || printf '_prompt_todo.txt' ;;
                model) printf 'gpt-5.6-sol' ;;
                effort) printf 'medium' ;;
                sandbox) printf '' ;;
                headings) printf '### Summary\n### Changes\n### Blast radius\n### Confidence\n' ;;
                decision) printf 'normalize-grounded' ;;
                publisher) printf 'publish.sh' ;;
                outcome) printf 'pull_request' ;;
                # Drafting code PRs is what this lane has always done on every
                # board it watches; it is not behind a grant.
                capability) printf '' ;;
                *) return 1 ;;
            esac ;;
        research)
            case "$field" in
                prompt) printf '_prompt_research.txt' ;;
                model) printf 'gpt-5.6-luna' ;;
                effort) printf 'high' ;;
                # Live web search runs on OpenAI's side; the card's screenshots
                # go in as native image inputs; and the pass may not change a
                # single repository file.
                sandbox) printf 'AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1 AUTOPR_CODEX_WEB_SEARCH=1 AUTOPR_CODEX_IMAGE_INPUTS=1' ;;
                headings) printf '### Summary\n### Findings\n### How it applies to Matcha\n### Recommendation\n### Sources\n### Confidence\n' ;;
                decision) printf 'normalize-research' ;;
                publisher) printf 'publish-research.sh' ;;
                outcome) printf 'artifact' ;;
                capability) printf 'research' ;;
                *) return 1 ;;
            esac ;;
        email)
            case "$field" in
                prompt) printf '_prompt_email.txt' ;;
                model) printf 'gpt-5.6-luna' ;;
                effort) printf 'medium' ;;
                # The corpus is the email snapshots Espresso attached to the
                # card, so this pass gets no web search and no image inputs —
                # only the rule that it may not change a repository file.
                # investigate.sh keys an artifact kind's search and browse
                # grants on AUTOPR_CODEX_WEB_SEARCH=1 here, so leaving it out
                # also keeps the browser away on a board granted `browse`.
                sandbox) printf 'AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1' ;;
                headings) printf '### Summary\n### Emails reviewed\n### Recommended actions\n### Confidence\n' ;;
                decision) printf 'normalize-email' ;;
                publisher) printf 'publish-email.sh' ;;
                outcome) printf 'artifact' ;;
                capability) printf 'email' ;;
                *) return 1 ;;
            esac ;;
        *) return 1 ;;
    esac
}

# autopr_kind_for_category CATEGORY → the mode a fresh card of that kind runs
# as. PR kinds still let select.sh choose investigate vs rework from the GitHub
# ledger; artifact kinds have no ledger and rerun the same pass, so a research
# card sent back with a review note simply produces the next report round.
autopr_kind_for_category() {
    case "${1:-}" in
        research) printf 'research' ;;
        email) printf 'email' ;;
        *) printf 'investigate' ;;
    esac
}
