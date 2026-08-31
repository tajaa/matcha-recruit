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
MAX_CHANGED_FILES="${AUTOPR_SANDBOX_MAX_CHANGED_FILES:-25}"
MAX_PATCH_BYTES="${AUTOPR_SANDBOX_MAX_PATCH_BYTES:-5242880}"
MAX_REPORT_BYTES="${AUTOPR_SANDBOX_MAX_REPORT_BYTES:-1048576}"
MAX_DECISION_BYTES="${AUTOPR_SANDBOX_MAX_DECISION_BYTES:-262144}"

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

mkdir -p "$IO_DIR/input" "$IO_DIR/output"

MODEL_INPUT_LIST=""
PATH_MAP='{}'
CONTEXT_COPY=""
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
    ' "$CONTEXT_COPY" > "$CONTEXT_COPY.next"
    mv "$CONTEXT_COPY.next" "$CONTEXT_COPY"
fi

MODEL_REPORT="$MODEL_CONTAINER_ROOT/.git/autopr-io/output/report.md"
MODEL_DECISION="$MODEL_CONTAINER_ROOT/.git/autopr-io/output/decision.json"
PROMPT_TEXT="Read every input file listed below before acting. These are the only attached inputs available to you.
AUTOPR_INPUTS_BEGIN${MODEL_INPUT_LIST}
AUTOPR_INPUTS_END

$(sed -e "s#REPORT_PATH#$MODEL_REPORT#g" \
    -e "s#DECISION_PATH#$MODEL_DECISION#g" "$PROMPT_TEMPLATE")"

CODEX_ARGS=(exec --dangerously-bypass-approvals-and-sandbox --ephemeral
    --ignore-user-config --model "$CODEX_MODEL"
    -c "model_reasoning_effort=\"$CODEX_REASONING_EFFORT\""
    -C "$MODEL_CONTAINER_ROOT" "$PROMPT_TEXT")

if [ "${AUTOPR_SANDBOX_TEST_DIRECT:-0}" = 1 ]; then
    codex "${CODEX_ARGS[@]}"
else
    env -u GH_TOKEN -u MATCHA_BOT_PASSWORD -u SSH_KEY -u EC2_SSH_KEY \
        AGENT_SANDBOX_PROJECT_NAME="$SANDBOX_PROJECT" \
        AGENT_SANDBOX_AUTOPR=1 \
        SANDBOX_WORKSPACE_DIR="$SANDBOX_WORKSPACE" \
        SANDBOX_AWS_DIR="$EMPTY_AWS_DIR" \
        SANDBOX_CODEX_AUTH_FILE="$SANDBOX_CODEX_AUTH_FILE" \
        "$MSANDBOX_BIN" exec \
        codex "${CODEX_ARGS[@]}"
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

# Include new files with intent-to-add, then compare against the immutable
# pre-model commit. This still captures edits if a model ignored the prompt
# and committed locally; the disposable clone's history is never trusted.
git -C "$SANDBOX_WORKSPACE" add --intent-to-add --all -- .
PATCH_FILE="$RUNTIME_ROOT/model.patch"
git -C "$SANDBOX_WORKSPACE" diff --binary --full-index "$MODEL_BASE_SHA" -- . > "$PATCH_FILE"
CHANGED_FILE_COUNT="$(git -C "$SANDBOX_WORKSPACE" diff --name-only "$MODEL_BASE_SHA" -- . \
    | wc -l | tr -d '[:space:]')"
PATCH_BYTES="$(wc -c < "$PATCH_FILE" | tr -d '[:space:]')"
[ "$CHANGED_FILE_COUNT" -le "$MAX_CHANGED_FILES" ] \
    || die "sandbox patch touches $CHANGED_FILE_COUNT files (max $MAX_CHANGED_FILES)"
[ "$PATCH_BYTES" -le "$MAX_PATCH_BYTES" ] \
    || die "sandbox patch is $PATCH_BYTES bytes (max $MAX_PATCH_BYTES)"

# A symlink or gitlink can make an apparently allowed source path point
# elsewhere or smuggle repository topology into the patch. AutoPR has no
# legitimate need to create/change either, so reject those modes mechanically.
if git -C "$SANDBOX_WORKSPACE" diff --raw "$MODEL_BASE_SHA" -- . \
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
