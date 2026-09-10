#!/usr/bin/env bash
# Run the model in a dedicated msandbox against a disposable, tracked-files-
# only clone. The trusted host owns evidence collection and publication; this
# script is the sole bridge that copies bounded inputs in and a patch/report
# out. Codex never receives the Actions checkout, its untracked secrets, or
# any host/GitHub/Matcha/production credential.
#
# Usage:
#   run-codex-sandboxed.sh PROMPT_TEMPLATE REPORT DECISION -f INPUT...
set -euo pipefail

PROMPT_TEMPLATE="${1:?usage: run-codex-sandboxed.sh PROMPT_TEMPLATE REPORT DECISION -f INPUT...}"
REPORT_FILE="${2:?missing report path}"
DECISION_FILE="${3:?missing decision path}"
shift 3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AUTOPR_SANDBOX_REPO_ROOT:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
MSANDBOX_BIN="${AUTOPR_MSANDBOX_BIN:-$REPO_ROOT/scripts/agent-sandbox.sh}"
SANDBOX_PROJECT="${AUTOPR_SANDBOX_PROJECT_NAME:-matcha-kanban-autopr-sandbox}"
GIT_DIR="$(git -C "$REPO_ROOT" rev-parse --absolute-git-dir)"
RUNTIME_ROOT="${AUTOPR_SANDBOX_RUNTIME_ROOT:-$GIT_DIR/matcha-kanban-autopr-sandbox}"
SANDBOX_WORKSPACE="$RUNTIME_ROOT/workspace"
EMPTY_AWS_DIR="$RUNTIME_ROOT/empty-aws"
AUTH_DIR="$RUNTIME_ROOT/codex-auth"
SANDBOX_CODEX_AUTH_FILE="$AUTH_DIR/auth.json"
HOST_CODEX_AUTH_FILE="${AUTOPR_HOST_CODEX_AUTH_FILE:-$HOME/.codex/auth.json}"
IO_DIR="$SANDBOX_WORKSPACE/.git/autopr-io"
MODEL_CONTAINER_ROOT="/workspace"
CODEX_MODEL="${AUTOPR_CODEX_MODEL:-gpt-5.6-sol}"
CODEX_REASONING_EFFORT="${AUTOPR_CODEX_REASONING_EFFORT:-medium}"
REQUIRE_EMPTY_PATCH="${AUTOPR_CODEX_REQUIRE_EMPTY_PATCH:-0}"
RESUME_PATCH="${AUTOPR_RESUME_PATCH:-}"
# Implementation and research kinds opt into live web search via lib.sh.
# Search executes on OpenAI's side; the container's network posture is unchanged.
# Image inputs remain a separate research-kind switch. Other callers (such as
# publication copy) opt into neither capability by default.
WEB_SEARCH="${AUTOPR_CODEX_WEB_SEARCH:-0}"
IMAGE_INPUTS="${AUTOPR_CODEX_IMAGE_INPUTS:-0}"
# Screenshots the model captured with browse-capture.py. They come back the
# same way report.md does — through one directory the trusted side empties and
# bounds — so a browsing run cannot widen what crosses the boundary.
COLLECT_ARTIFACTS="${AUTOPR_CODEX_COLLECT_ARTIFACTS:-0}"
ARTIFACTS_DIR="${AUTOPR_SANDBOX_ARTIFACTS_DIR:-}"
# The prompt is the same template for every research run, but the browser
# paragraph is only true where the bridge will actually collect screenshots.
# Nothing else reaches the container to say so, and a model told it has a
# browser on a board without the grant takes screenshots that are silently
# dropped and cites images that never attach. So the paragraph itself is
# switched here: the fragment when artifacts are collected, a one-line
# refusal otherwise. `BROWSE_TOOL_SECTION` in a template marks the spot.
BROWSE_SECTION_FILE=""
if [ "$COLLECT_ARTIFACTS" = 1 ] && [ -f "$(dirname "$PROMPT_TEMPLATE")/_prompt_research_browse.txt" ]; then
    BROWSE_SECTION_FILE="$(dirname "$PROMPT_TEMPLATE")/_prompt_research_browse.txt"
fi
GROUNDING_SECTION_FILE=""
if [ -f "$(dirname "$PROMPT_TEMPLATE")/_prompt_grounding.txt" ]; then
    GROUNDING_SECTION_FILE="$(dirname "$PROMPT_TEMPLATE")/_prompt_grounding.txt"
fi
MAX_ARTIFACTS="${AUTOPR_SANDBOX_MAX_ARTIFACTS:-12}"
MAX_ARTIFACT_BYTES="${AUTOPR_SANDBOX_MAX_ARTIFACT_BYTES:-4194304}"
MAX_CHANGED_FILES="${AUTOPR_SANDBOX_MAX_CHANGED_FILES:-25}"
MAX_PATCH_BYTES="${AUTOPR_SANDBOX_MAX_PATCH_BYTES:-5242880}"
MAX_REPORT_BYTES="${AUTOPR_SANDBOX_MAX_REPORT_BYTES:-1048576}"
MAX_DECISION_BYTES="${AUTOPR_SANDBOX_MAX_DECISION_BYTES:-262144}"
# Paths the model's patch may never touch, enforced HERE — at the moment the
# patch reaches the trusted checkout — not only in the publisher. Between this
# bridge and publish.sh the workflow still executes scripts out of that
# checkout (scope check, coverage recording, the sandbox controller itself),
# so a patch that rewrote one of them used to run as the runner user before
# any guard looked at it. The self-audit lane, whose job is repairing the
# harness, narrows this to CI/deploy/secrets via AUTOPR_SANDBOX_PATH_DENY_RE.
PATH_DENY_RE="${AUTOPR_SANDBOX_PATH_DENY_RE:-^(\.github/|deploy/|docker/|scripts/|\.claude/|\.codex/|\.githooks/|secrets/|opencode\.jsonc$|(.*/)?docker-compose[^/]*\.ya?ml$|(.*/)?Dockerfile[^/]*$|(.*/)?\.env[^/]*$)}"
CODEX_BACKOFF="${AUTOPR_CODEX_BACKOFF:-$SCRIPT_DIR/codex-backoff.sh}"
HANDOFF_CONTROL="$(dirname "$SCRIPT_DIR")/msandbox/autopr_control.py"

die() {
    printf 'kanban-autopr sandbox: %s\n' "$1" >&2
    exit 1
}

case "$SANDBOX_WORKSPACE" in
    "$RUNTIME_ROOT/workspace") ;;
    *) die "refusing unsafe sandbox workspace: $SANDBOX_WORKSPACE" ;;
esac

[ -f "$PROMPT_TEMPLATE" ] || die "missing prompt template: $PROMPT_TEMPLATE"
[ "$#" -gt 0 ] || die "at least one model input is required"
if [ "${AUTOPR_SANDBOX_TEST_DIRECT:-0}" = 1 ]; then
    [ "${GITHUB_ACTIONS:-}" != true ] || die "direct model execution is forbidden in GitHub Actions"
    MODEL_CONTAINER_ROOT="$SANDBOX_WORKSPACE"
else
    [ -x "$MSANDBOX_BIN" ] || die "msandbox is not executable: $MSANDBOX_BIN"
    # AutoPR uses the runner user's existing Codex/ChatGPT login.
    # Copy only its auth.json into a private runtime directory, then bind it
    # read-only into the container. Do not mount the host Codex home: its
    # history, logs, database, and every unrelated credential stay outside.
    [ -r "$HOST_CODEX_AUTH_FILE" ] \
        || die "missing host Codex auth file: $HOST_CODEX_AUTH_FILE"
    mkdir -p "$AUTH_DIR"
    chmod 700 "$AUTH_DIR"
    cp "$HOST_CODEX_AUTH_FILE" "$SANDBOX_CODEX_AUTH_FILE"
    chmod 600 "$SANDBOX_CODEX_AUTH_FILE"
fi

# Refuse to overwrite a checkout whose takeover was interrupted. This guard
# also covers writing-only callers that share the lane's runtime directory.
python3 "$HANDOFF_CONTROL" protect-workspace "$SANDBOX_WORKSPACE"

# Stop only the dedicated AutoPR container before replacing its bind-mounted
# clone. Named tool/dependency volumes remain intact between runs; the auth
# file itself is freshly copied by the trusted bridge for each invocation.
if [ "${AUTOPR_SANDBOX_TEST_DIRECT:-0}" != 1 ]; then
    env AGENT_SANDBOX_PROJECT_NAME="$SANDBOX_PROJECT" \
        AGENT_SANDBOX_AUTOPR=1 \
        SANDBOX_WORKSPACE_DIR="$SANDBOX_WORKSPACE" \
        SANDBOX_AWS_DIR="$EMPTY_AWS_DIR" \
        SANDBOX_CODEX_AUTH_FILE="$SANDBOX_CODEX_AUTH_FILE" \
        "$MSANDBOX_BIN" stop >/dev/null 2>&1 || true
fi

mkdir -p "$RUNTIME_ROOT" "$EMPTY_AWS_DIR"
rm -rf -- "$SANDBOX_WORKSPACE"

# A local clone carries tracked code and git history, but none of the real
# checkout's untracked .env files, PEM keys, caches, or hooks. Remove its
# local-path remote as well: the container has no route back to the source
# repository and cannot push. The trusted host later applies one binary patch.
git clone --quiet --no-hardlinks --no-checkout "$REPO_ROOT" "$SANDBOX_WORKSPACE"
MODEL_BASE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
if git -C "$REPO_ROOT" rev-parse --verify main^{commit} >/dev/null 2>&1; then
    MAIN_SHA="$(git -C "$REPO_ROOT" rev-parse main^{commit})"
elif git -C "$REPO_ROOT" rev-parse --verify origin/main^{commit} >/dev/null 2>&1; then
    MAIN_SHA="$(git -C "$REPO_ROOT" rev-parse origin/main^{commit})"
else
    # Disposable/local test worktrees may intentionally have no main ref.
    MAIN_SHA="$MODEL_BASE_SHA"
fi
git -C "$SANDBOX_WORKSPACE" checkout --quiet --detach "$MODEL_BASE_SHA"
git -C "$SANDBOX_WORKSPACE" branch --force main "$MAIN_SHA" >/dev/null
git -C "$SANDBOX_WORKSPACE" remote remove origin
git -C "$SANDBOX_WORKSPACE" config core.hooksPath /dev/null

mkdir -p "$IO_DIR/input" "$IO_DIR/output" "$IO_DIR/output/artifacts"
printf '%s\n' "$MODEL_BASE_SHA" > "$IO_DIR/model-base-sha"
# Bind this clone to the card it was made for. The runtime root survives
# between runs and is only wiped here, so a checkpoint taken by a run that died
# before reaching this point must be able to tell that the workspace still
# holds the PREVIOUS card's work.
[ -z "${AUTOPR_TASK_ID:-}" ] || printf '%s\n' "$AUTOPR_TASK_ID" > "$IO_DIR/task-id"

# Apply saved model work only in the disposable clone. Later patch checks still
# decide whether it may reach the trusted checkout.
if [ -n "$RESUME_PATCH" ]; then
    if [ -f "$RESUME_PATCH" ] && [ ! -s "$RESUME_PATCH" ] \
        && [ "${AUTOPR_REQUIRE_RESUME_PATCH:-0}" = 1 ]; then
        printf 'Restored operator hand-back with instructions only (no file changes)\n'
    elif [ -f "$RESUME_PATCH" ] \
        && [ "$(wc -c < "$RESUME_PATCH" | tr -d '[:space:]')" -le "$MAX_PATCH_BYTES" ] \
        && git -C "$SANDBOX_WORKSPACE" apply --check --binary "$RESUME_PATCH"; then
        git -C "$SANDBOX_WORKSPACE" apply --binary "$RESUME_PATCH"
        printf 'Restored interrupted AutoPR patch inside msandbox\n'
    else
        [ "${AUTOPR_REQUIRE_RESUME_PATCH:-0}" != 1 ] \
            || die "operator hand-back no longer applies; preserved checkout needs conflict resolution"
        printf 'Saved AutoPR patch no longer applies; continuing with its textual checkpoint only\n' >&2
    fi
fi

MODEL_INPUT_LIST=""
PATH_MAP='{}'
CONTEXT_COPY=""
IMAGE_ARGS=()
input_index=0
while [ "$#" -gt 0 ]; do
    [ "$1" = -f ] || die "unexpected argument: $1"
    [ "$#" -ge 2 ] || die "-f requires a path"
    input_path="$2"
    shift 2
    [ -f "$input_path" ] || die "missing model input: $input_path"

    input_index=$((input_index + 1))
    safe_name="$(printf '%s' "$(basename "$input_path")" | tr -cs '[:alnum:]_. -' '_' | cut -c1-120)"
    [ -n "$safe_name" ] || safe_name="input"
    copied_path="$IO_DIR/input/$(printf '%02d' "$input_index")-$safe_name"
    model_path="$MODEL_CONTAINER_ROOT/.git/autopr-io/input/$(basename "$copied_path")"
    cp "$input_path" "$copied_path"
    MODEL_INPUT_LIST="${MODEL_INPUT_LIST}
- $model_path"
    PATH_MAP="$(jq -c --arg old "$input_path" --arg new "$model_path" '. + {($old): $new}' <<< "$PATH_MAP")"
    [ -n "$CONTEXT_COPY" ] || CONTEXT_COPY="$copied_path"
    # The container path, not the host one: codex opens the image where it runs.
    if [ "$IMAGE_INPUTS" = 1 ]; then
        case "$(printf '%s' "$safe_name" | tr '[:upper:]' '[:lower:]')" in
            *.png|*.jpg|*.jpeg|*.gif|*.webp) IMAGE_ARGS+=(-i "$model_path") ;;
        esac
    fi
done

# Keep context.json's attachment paths truthful inside the container. The
# files are also enumerated in the prompt, and this mapping lets the model correlate a
# discussion attachment id with the exact readable path without guessing.
if jq -e '.downloaded_attachments | type == "array"' "$CONTEXT_COPY" >/dev/null 2>&1; then
    jq --argjson paths "$PATH_MAP" '
      .downloaded_attachments |= map(
        if (.local_path // "") != "" then
          .local_path = ($paths[.local_path] // .local_path)
        else . end
      )
      | if (.test_tenant_evidence.screenshot_path // "") != "" then
          .test_tenant_evidence.screenshot_path =
            ($paths[.test_tenant_evidence.screenshot_path] // .test_tenant_evidence.screenshot_path)
        else . end
    ' "$CONTEXT_COPY" > "$CONTEXT_COPY.next"
    mv "$CONTEXT_COPY.next" "$CONTEXT_COPY"
fi

MODEL_REPORT="$MODEL_CONTAINER_ROOT/.git/autopr-io/output/report.md"
MODEL_DECISION="$MODEL_CONTAINER_ROOT/.git/autopr-io/output/decision.json"
PROMPT_TEXT="Read every input file listed below before acting. These are the only attached inputs available to you.
AUTOPR_INPUTS_BEGIN${MODEL_INPUT_LIST}
AUTOPR_INPUTS_END

$(sed -e "s#REPORT_PATH#$MODEL_REPORT#g" \
    -e "s#DECISION_PATH#$MODEL_DECISION#g" "$PROMPT_TEMPLATE" \
    | awk -v browse_file="$BROWSE_SECTION_FILE" \
          -v grounding_file="$GROUNDING_SECTION_FILE" '
        /^BROWSE_TOOL_SECTION$/ {
            if (browse_file != "") { while ((getline line < browse_file) > 0) print line }
            else print "- No browser. This board is not granted browsing: `browse-capture.py` is\n  not available to you, no screenshot would be collected, and the attempt\n  only spends your time. Use web search alone."
            next
        }
        /^GROUNDING_CONTEXT_SECTION$/ {
            if (grounding_file == "") {
                print "Grounding instructions are unavailable; do not guess or claim web research."
            } else {
                while ((getline line < grounding_file) > 0) print line
            }
            next
        }
        { print }')"

CODEX_ARGS=(exec --dangerously-bypass-approvals-and-sandbox --ephemeral
    --ignore-user-config --model "$CODEX_MODEL"
    -c "model_reasoning_effort=\"$CODEX_REASONING_EFFORT\"")
# `codex exec` has no --search flag (the TUI does); the config key is the
# documented route and --ignore-user-config leaves -c overrides in force.
# Verified against codex-cli 0.153.4, the pinned sandbox version.
[ "$WEB_SEARCH" != 1 ] || CODEX_ARGS+=(-c 'web_search="live"')
# Bash 3.2 + set -u: an empty array expands as unbound without this guard.
[ "$IMAGE_INPUTS" != 1 ] || CODEX_ARGS+=(${IMAGE_ARGS[@]+"${IMAGE_ARGS[@]}"})
CODEX_ARGS+=(-C "$MODEL_CONTAINER_ROOT" "$PROMPT_TEXT")

# Keep one copy of the transcript on the trusted side. A non-zero exit that
# names an exhausted usage limit is a lane-wide condition, not a per-card one:
# record it so the dispatcher stops launching runs until the quota returns.
CODEX_TRANSCRIPT="$RUNTIME_ROOT/codex-last-run.log"
# Called with errexit OFF (see below): `set` inside a function is global, so
# toggling it here would re-arm errexit before the non-zero return reached
# the caller and the script would die without recording anything.
run_codex_cli() {
    if [ "${AUTOPR_SANDBOX_TEST_DIRECT:-0}" = 1 ]; then
        codex "${CODEX_ARGS[@]}" 2>&1 | tee "$CODEX_TRANSCRIPT"
    else
        local -a supervised=()
        if [ -n "${AUTOPR_HANDOFF_CARD:-}" ]; then
            supervised=(python3 "$HANDOFF_CONTROL" supervise
                --card "$AUTOPR_HANDOFF_CARD" --workspace "$SANDBOX_WORKSPACE"
                --repo "$REPO_ROOT" --project "$SANDBOX_PROJECT" --)
        fi
        env -u GH_TOKEN -u GITHUB_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY \
            -u AUTOPR_TEST_TENANT_EMAIL -u AUTOPR_TEST_TENANT_PASSWORD \
            AGENT_SANDBOX_PROJECT_NAME="$SANDBOX_PROJECT" \
            AGENT_SANDBOX_AUTOPR=1 \
            SANDBOX_WORKSPACE_DIR="$SANDBOX_WORKSPACE" \
            SANDBOX_AWS_DIR="$EMPTY_AWS_DIR" \
            SANDBOX_CODEX_AUTH_FILE="$SANDBOX_CODEX_AUTH_FILE" \
            AUTOPR_MSANDBOX_BIN="$MSANDBOX_BIN" \
            AUTOPR_SANDBOX_PROJECT_NAME="$SANDBOX_PROJECT" \
            ${supervised[@]+"${supervised[@]}"} "$MSANDBOX_BIN" exec \
            codex "${CODEX_ARGS[@]}" 2>&1 | tee "$CODEX_TRANSCRIPT"
    fi
    return "${PIPESTATUS[0]}"
}
set +e
run_codex_cli
codex_rc=$?
set -e
if [ "$codex_rc" -ne 0 ]; then
    if [ -x "$CODEX_BACKOFF" ]; then
        "$CODEX_BACKOFF" record "$CODEX_TRANSCRIPT" || true
    fi
    # Preserve Codex's own status: the callers log and act on it.
    printf 'kanban-autopr sandbox: Codex exited %s inside msandbox\n' "$codex_rc" >&2
    exit "$codex_rc"
fi
# A completed Codex call proves the quota is back. Nothing else clears the
# marker, so without this one usage-limit hit holds every lane until resume_at
# (up to 24 h) even after the account has recovered.
if [ -x "$CODEX_BACKOFF" ]; then
    "$CODEX_BACKOFF" clear || true
fi

HOST_REPORT="$IO_DIR/output/report.md"
HOST_DECISION="$IO_DIR/output/decision.json"
[ -s "$HOST_REPORT" ] || die "Codex produced no report inside msandbox"
[ -s "$HOST_DECISION" ] || die "Codex produced no decision inside msandbox"
[ "$(wc -c < "$HOST_REPORT" | tr -d '[:space:]')" -le "$MAX_REPORT_BYTES" ] \
    || die "Codex report exceeds $MAX_REPORT_BYTES bytes"
[ "$(wc -c < "$HOST_DECISION" | tr -d '[:space:]')" -le "$MAX_DECISION_BYTES" ] \
    || die "Codex decision exceeds $MAX_DECISION_BYTES bytes"
cp "$HOST_REPORT" "$REPORT_FILE"
cp "$HOST_DECISION" "$DECISION_FILE"

# Screenshots, if this run was allowed to take any. Every one of them is about
# to be uploaded to a real ticket, so the filter is an allowlist of image
# extensions on a flat directory — never a copy of whatever the model left
# behind. A file that fails any check is skipped and named on stderr rather
# than silently dropped.
if [ "$COLLECT_ARTIFACTS" = 1 ] && [ -n "$ARTIFACTS_DIR" ]; then
    mkdir -p "$ARTIFACTS_DIR"
    artifact_count=0
    while IFS= read -r -d '' artifact; do
        artifact_name="$(basename "$artifact")"
        case "$(printf '%s' "$artifact_name" | tr '[:upper:]' '[:lower:]')" in
            *.png|*.jpg|*.jpeg|*.webp) ;;
            *)
                printf 'kanban-autopr sandbox: ignoring non-image artifact %s\n' "$artifact_name" >&2
                continue ;;
        esac
        # Reject a name that could escape the destination or hide as a dotfile.
        case "$artifact_name" in
            .*|*/*|*..*)
                printf 'kanban-autopr sandbox: ignoring unsafe artifact name %s\n' "$artifact_name" >&2
                continue ;;
        esac
        if [ "$artifact_count" -ge "$MAX_ARTIFACTS" ]; then
            printf 'kanban-autopr sandbox: artifact cap reached (%s); ignoring %s\n' \
                "$MAX_ARTIFACTS" "$artifact_name" >&2
            continue
        fi
        artifact_bytes="$(wc -c < "$artifact" | tr -d '[:space:]')"
        if [ "$artifact_bytes" -gt "$MAX_ARTIFACT_BYTES" ]; then
            printf 'kanban-autopr sandbox: artifact %s is %s bytes (max %s); ignoring\n' \
                "$artifact_name" "$artifact_bytes" "$MAX_ARTIFACT_BYTES" >&2
            continue
        fi
        cp "$artifact" "$ARTIFACTS_DIR/$artifact_name"
        artifact_count=$((artifact_count + 1))
    done < <(find "$IO_DIR/output/artifacts" -maxdepth 1 -type f -print0 2>/dev/null | sort -z)
    printf 'Collected %s screenshot(s) from the sandbox\n' "$artifact_count"
fi

# Include new files with intent-to-add, then compare against the immutable
# pre-model commit. This still captures edits if a model ignored the prompt
# and committed locally; the disposable clone's history is never trusted.
git -C "$SANDBOX_WORKSPACE" add --intent-to-add --all -- .

# Rename detection collapses a rename pair into the destination path only, so a
# model could move a protected file onto an allowed path and have the deletion
# applied to the trusted checkout without the path guard ever seeing the source.
# Every read of the sandbox diff goes through this helper with renames off, so a
# rename is always recorded as delete + add and both paths reach the guard, the
# changed-file cap, and the patch itself.
sandbox_diff() {
    git -C "$SANDBOX_WORKSPACE" -c diff.renames=false diff "$@"
}

# Repository instruction files are operator-owned context, not product output.
# A model may occasionally append implementation notes to one despite the
# prompt. Restore tracked instruction files mechanically before constructing
# the patch so an otherwise valid product change is not abandoned at publish.
# A newly-created instruction file remains in the patch and is rejected by the
# downstream path guard; only files already present at MODEL_BASE_SHA qualify.
while IFS= read -r -d '' changed_path; do
    case "/$changed_path" in
        */CLAUDE.md|*/AGENTS.md)
            if git -C "$SANDBOX_WORKSPACE" cat-file -e "$MODEL_BASE_SHA:$changed_path" 2>/dev/null; then
                git -C "$SANDBOX_WORKSPACE" restore --source "$MODEL_BASE_SHA" --worktree -- "$changed_path"
                printf 'Ignored model edit to operator instruction file: %s\n' "$changed_path"
            fi
            ;;
    esac
done < <(sandbox_diff --name-only -z "$MODEL_BASE_SHA" -- .)

PATCH_FILE="$RUNTIME_ROOT/model.patch"
sandbox_diff --binary --full-index "$MODEL_BASE_SHA" -- . > "$PATCH_FILE"
CHANGED_FILE_COUNT="$(sandbox_diff --name-only "$MODEL_BASE_SHA" -- . \
    | wc -l | tr -d '[:space:]')"
PATCH_BYTES="$(wc -c < "$PATCH_FILE" | tr -d '[:space:]')"
[ "$CHANGED_FILE_COUNT" -le "$MAX_CHANGED_FILES" ] \
    || die "sandbox patch touches $CHANGED_FILE_COUNT files (max $MAX_CHANGED_FILES)"
[ "$PATCH_BYTES" -le "$MAX_PATCH_BYTES" ] \
    || die "sandbox patch is $PATCH_BYTES bytes (max $MAX_PATCH_BYTES)"

# Harness, CI, container, deploy, and agent-config paths never reach the
# trusted checkout from a model patch (see PATH_DENY_RE above). Deletions and
# renames count too: the list comes from the same rename-free diff that becomes
# the patch, so a rename out of a protected path still shows the source path.
denied_paths="$(sandbox_diff --name-only "$MODEL_BASE_SHA" -- . \
    | grep -E "$PATH_DENY_RE" || true)"
if [ -n "$denied_paths" ]; then
    printf 'kanban-autopr sandbox: refusing model changes to protected paths:\n%s\n' "$denied_paths" >&2
    die "sandbox patch touches a protected path"
fi

# A symlink or gitlink can make an apparently allowed source path point
# elsewhere or smuggle repository topology into the patch. AutoPR has no
# legitimate need to create/change either, so reject those modes mechanically.
if sandbox_diff --raw "$MODEL_BASE_SHA" -- . \
    | awk '$1 ~ /^:(120000|160000)$/ || $2 ~ /^(120000|160000)$/ {found=1} END {exit !found}'; then
    die "sandbox patch contains a symlink or submodule change"
fi

if [ "$REQUIRE_EMPTY_PATCH" = 1 ] && [ -s "$PATCH_FILE" ]; then
    die "Codex writing task unexpectedly changed repository files"
fi

if [ -s "$PATCH_FILE" ]; then
    git -C "$REPO_ROOT" apply --check --binary "$PATCH_FILE" \
        || die "sandbox patch no longer applies cleanly to the trusted checkout"
    git -C "$REPO_ROOT" apply --binary "$PATCH_FILE"
fi

printf 'Sandbox patch bridge complete: %s changed files\n' \
    "$CHANGED_FILE_COUNT"
