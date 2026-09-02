#!/usr/bin/env bash
# Deterministic, read-only audit for the complete msandbox/AutoPR control
# plane. Repository failures may be handed to the isolated repair workflow;
# machine-state failures are reported as operator actions and never converted
# into invented code changes.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
JSON_FILE=""
SUMMARY_FILE=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --json) JSON_FILE="${2:?--json requires a path}"; shift 2 ;;
        --summary) SUMMARY_FILE="${2:?--summary requires a path}"; shift 2 ;;
        *) echo "usage: audit.sh --json FILE --summary FILE" >&2; exit 2 ;;
    esac
done
[ -n "$JSON_FILE" ] && [ -n "$SUMMARY_FILE" ] \
    || { echo "usage: audit.sh --json FILE --summary FILE" >&2; exit 2; }

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/matcha-autopr-audit.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT
RESULTS_FILE="$WORK_DIR/checks.json"
printf '[]\n' > "$RESULTS_FILE"

check_core_shell_syntax() {
    local file
    while IFS= read -r file; do
        bash -n "$file" || return 1
    done < <(find \
        "$REPO_ROOT/scripts/kanban-autopr" \
        "$REPO_ROOT/scripts/error-autofix" \
        "$REPO_ROOT/scripts/autopr-scope" \
        -type f -name '*.sh' -print | sort)
    bash -n "$REPO_ROOT/scripts/agent-sandbox.sh"
    python3 -m compileall -q "$REPO_ROOT/scripts/msandbox"
}

check_compose_contract() {
    command -v docker >/dev/null 2>&1 || return 77
    docker compose version >/dev/null 2>&1 || return 77
    local compose_tmp
    compose_tmp="$(mktemp -d "$WORK_DIR/compose.XXXXXX")"
    mkdir -p "$compose_tmp/workspace" "$compose_tmp/empty-aws"
    : > "$compose_tmp/auth.json"
    SANDBOX_WORKSPACE_DIR="$REPO_ROOT" SANDBOX_AWS_DIR="$compose_tmp/empty-aws" \
        docker compose --project-name matcha-agent-sandbox-audit \
        --file "$REPO_ROOT/docker-compose.sandbox.yml" config --quiet || return 1
    mkdir -p "$compose_tmp/git/objects" "$compose_tmp/isolated.git" \
        "$compose_tmp/home" "$compose_tmp/attachments"
    printf 'gitdir: /msandbox-git\n' > "$compose_tmp/workspace.git"
    SANDBOX_WORKSPACE_DIR="$REPO_ROOT" SANDBOX_AWS_DIR="$compose_tmp/empty-aws" \
        SANDBOX_GIT_OBJECTS_DIR="$compose_tmp/git/objects" \
        MSANDBOX_GIT_DIR="$compose_tmp/isolated.git" \
        MSANDBOX_GIT_POINTER_FILE="$compose_tmp/workspace.git" \
        MSANDBOX_SESSION_ID=audit MSANDBOX_SESSION_HOME="$compose_tmp/home" \
        MSANDBOX_ATTACHMENTS_HOST_DIR="$compose_tmp/attachments" \
        SANDBOX_SERVER_VENV_VOLUME=matcha-ms-audit-server \
        SANDBOX_CLIENT_NODE_MODULES_VOLUME=matcha-ms-audit-client \
        SANDBOX_TELLUS_NODE_MODULES_VOLUME=matcha-ms-audit-tellus \
        SANDBOX_OCEANLAB_NODE_MODULES_VOLUME=matcha-ms-audit-oceanlab \
        docker compose --project-name matcha-msandbox-session-audit \
        --file "$REPO_ROOT/docker-compose.sandbox.yml" \
        --file "$REPO_ROOT/docker-compose.sandbox-session.yml" \
        --file "$REPO_ROOT/docker-compose.sandbox-test.yml" config --quiet || return 1
    SANDBOX_WORKSPACE_DIR="$compose_tmp/workspace" SANDBOX_AWS_DIR="$compose_tmp/empty-aws" \
        SANDBOX_CODEX_AUTH_FILE="$compose_tmp/auth.json" \
        docker compose --project-name matcha-autopr-audit \
        --file "$REPO_ROOT/docker-compose.sandbox.yml" \
        --file "$REPO_ROOT/docker-compose.autopr-sandbox.yml" config --quiet || return 1
}

check_local_schema_state() {
    command -v docker >/dev/null 2>&1 || return 77
    docker inspect matcha-postgres >/dev/null 2>&1 || return 77
    local revisions python_bin pending schedule_index
    revisions="$(docker exec matcha-postgres psql -U matcha -d matcha -Atqc \
        'SELECT version_num FROM alembic_version ORDER BY version_num' 2>/dev/null)" || return 77
    [ -n "$revisions" ] || { echo "local alembic_version is empty"; return 1; }
    python_bin="$REPO_ROOT/server/venv/bin/python"
    [ -x "$python_bin" ] || python_bin="$(command -v python3 || true)"
    [ -n "$python_bin" ] || return 77
    # shellcheck disable=SC2086 -- Alembic revisions are whitespace-free ids.
    pending="$("$python_bin" "$REPO_ROOT/scripts/alembic_pending.py" $revisions 2>&1)" || return 77
    if [ -n "$pending" ]; then
        echo "Local development DB has unapplied repository migrations:"
        printf '%s\n' "$pending"
        echo "Operator action: review, then run ./scripts/migrate-dev.sh. The audit never applies DDL."
        return 1
    fi

    # A revision stamp is not proof its DDL ran. This exact invariant backs
    # schedule_eligibility_events.py's partial ON CONFLICT target; losing it
    # produces InvalidColumnReferenceError even with empsched11 represented by
    # a later stamped head. Keep this read-only and require reviewed repair DDL.
    schedule_index="$(docker exec matcha-postgres psql -U matcha -d matcha -Atqc \
        "SELECT to_regclass('public.uniq_ems_schedule_eligibility_source')" 2>/dev/null)" \
        || return 77
    if [ "$schedule_index" != uniq_ems_schedule_eligibility_source ]; then
        echo "Local Alembic heads are current, but required index uniq_ems_schedule_eligibility_source is absent."
        echo "Impact: schedule eligibility EMS upserts fail because PostgreSQL cannot infer their partial ON CONFLICT arbiter."
        echo "Operator action: reconcile the stamped schema with a new reviewed migration; rerunning migrate-dev.sh cannot replay an already-stamped revision."
        return 1
    fi
}

check_control_plane_state() {
    command -v docker >/dev/null 2>&1 || return 77
    docker info >/dev/null 2>&1 || return 77
    "$REPO_ROOT/scripts/agent-sandbox.sh" autopr-ready || {
        echo "AutoPR control plane is not fully ready. Run msandbox status, then msandbox start."
        return 1
    }
}

check_contract_tests() {
    local test_file
    for test_file in \
        test_agent_sandbox_lifecycle.sh \
        test_agent_sandbox_networking.sh \
        test_kanban_autopr.sh \
        test_kanban_autopr_dispatch.sh \
        test_kanban_autopr_dashboard.sh \
        test_kanban_autopr_publish.sh \
        test_kanban_autopr_checkout_cleanup.sh \
        test_error_autofix.sh \
        test_autopr_scope.sh \
        test_autopr_coverage_lifecycle.sh \
        test_msandbox_attachments.sh \
        test_msandbox_sessions.sh \
        test_msandbox_worktrees.sh; do
        bash "$REPO_ROOT/scripts/tests/$test_file" || return 1
    done
}

check_built_toolchain() {
    command -v docker >/dev/null 2>&1 || return 77
    docker image inspect matcha-agent-sandbox-workspace:latest >/dev/null 2>&1 || return 77
    docker run --rm --entrypoint bash matcha-agent-sandbox-workspace:latest -lc \
        'node --version && npm --version && npx --version && /opt/bootstrap/server-venv/bin/python -m pytest --version'
}

check_installed_controller() {
    local installed
    installed="$(command -v msandbox || true)"
    [ -n "$installed" ] || return 77
    case "$(readlink "$installed" 2>/dev/null || true)" in
        *'/Documents/github/matcha/'*)
            echo "Installed msandbox still points into the mutable repository checkout: $installed"
            echo "Operator action: run msandbox install after merging the v2 controller."
            return 1
            ;;
    esac
    msandbox --version
}

run_check() {
    local id="$1" title="$2" repairability="$3"
    shift 3
    local output_file="$WORK_DIR/$id.log" rc status output next
    "$@" > "$output_file" 2>&1
    rc=$?
    case "$rc" in
        0) status=pass ;;
        77) status=skip ;;
        *) status=fail ;;
    esac
    output="$(head -c 16000 "$output_file" | sed "s|$HOME|\$HOME|g; s|$REPO_ROOT|\$REPO_ROOT|g")"
    next="$RESULTS_FILE.next"
    jq --arg id "$id" --arg title "$title" --arg status "$status" \
        --arg repairability "$repairability" --arg output "$output" --argjson exit_code "$rc" \
        '. + [{id:$id,title:$title,status:$status,repairability:$repairability,exit_code:$exit_code,output:$output}]' \
        "$RESULTS_FILE" > "$next"
    mv "$next" "$RESULTS_FILE"
}

cd "$REPO_ROOT"
run_check shell_syntax "AutoPR shell syntax" repo check_core_shell_syntax
run_check compose_contract "Sandbox Compose contracts" repo check_compose_contract
run_check contract_tests "AutoPR and msandbox contract tests" repo check_contract_tests
run_check git_patch_hygiene "Patch whitespace and conflict markers" repo git diff --check
run_check local_schema "Local dev migration alignment" operator check_local_schema_state
run_check control_plane "msandbox control-plane readiness" operator check_control_plane_state
run_check built_toolchain "Built sandbox login-shell test toolchain" operator check_built_toolchain
run_check installed_controller "Versioned msandbox installation" operator check_installed_controller

repairable_failures="$(jq '[.[] | select(.status == "fail" and .repairability == "repo")] | length' "$RESULTS_FILE")"
operator_failures="$(jq '[.[] | select(.status == "fail" and .repairability == "operator")] | length' "$RESULTS_FILE")"
skipped_checks="$(jq '[.[] | select(.status == "skip")] | length' "$RESULTS_FILE")"
failure_material="$(jq -c '[.[] | select(.status == "fail" and .repairability == "repo") | {id,output}]' "$RESULTS_FILE")"
fingerprint="$(printf '%s' "$failure_material" | shasum -a 256 | awk '{print substr($1,1,12)}')"

jq -n --arg generated_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg fingerprint "$fingerprint" --argjson checks "$(cat "$RESULTS_FILE")" \
    --argjson repairable_failures "$repairable_failures" \
    --argjson operator_failures "$operator_failures" --argjson skipped_checks "$skipped_checks" \
    '{schema_version:1,generated_at:$generated_at,fingerprint:$fingerprint,
      repairable_failures:$repairable_failures,operator_failures:$operator_failures,
      skipped_checks:$skipped_checks,checks:$checks}' > "$JSON_FILE"

{
    echo "# Matcha AutoPR audit"
    echo
    printf 'Repairable failures: **%s** · operator actions: **%s** · skipped checks: **%s**\n\n' \
        "$repairable_failures" "$operator_failures" "$skipped_checks"
    jq -r '.checks[] | "- " + (if .status == "pass" then "✅" elif .status == "skip" then "⏭️" else "❌" end) + " **" + .title + "** — " + .status + (if .status == "fail" then " (" + .repairability + ")" else "" end)' "$JSON_FILE"
    if [ "$repairable_failures" -gt 0 ] || [ "$operator_failures" -gt 0 ]; then
        echo
        echo "## Failure detail"
        jq -r '.checks[] | select(.status == "fail") | "\n### " + .title + "\n\n```text\n" + (if (.output | length) == 0 then "(no output)" else .output end) + "\n```"' "$JSON_FILE"
    fi
} > "$SUMMARY_FILE"

# Findings are data, not a harness crash. Callers decide whether to dispatch a
# repair lane from repairable_failures and can still render operator actions.
exit 0
