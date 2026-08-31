#!/usr/bin/env bash
# Verifies the msandbox/AutoPR master switch without touching real Docker,
# launchd, tmux, GitHub, or the user's persistent state.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MSANDBOX="$REPO_ROOT/scripts/agent-sandbox.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/runtime" "$TMP_DIR/workspace" "$TMP_DIR/empty-aws"

PASS=0
FAIL=0
check() {
    local desc="$1" ok="$2"
    if [ "$ok" = 0 ]; then echo "PASS: $desc"; PASS=$((PASS + 1));
    else echo "FAIL: $desc"; FAIL=$((FAIL + 1)); fi
}

cat > "$TMP_DIR/bin/docker" <<'EOF'
#!/usr/bin/env bash
set -eu
[ "$1" != info ] || exit 0
if [ "$1" = exec ]; then
    if [ "${AUTOPR_TEST_PRIMARY_AGENT:-0}" = 1 ] \
        && [ "${2:-}" = matcha-agent-sandbox-container ]; then
        printf '%s\n' 'codex codex --sandboxed'
        exit 0
    fi
    if [ "${AUTOPR_TEST_AUDIT_AGENT:-0}" = 1 ] \
        && [ "${2:-}" = matcha-autopr-self-audit-sandbox-container ]; then
        printf '%s\n' 'opencode opencode run audit'
        exit 0
    fi
    exit 1
fi
[ "$1" != inspect ] || { printf '%s\n' running; exit 0; }
[ "$1" = compose ] || exit 1
shift
project=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --project-name) project="$2"; shift 2 ;;
        --file) shift 2 ;;
        *) break ;;
    esac
done
[ -n "$project" ] || exit 1
case "${1:-}" in
    up)
        : > "$AUTOPR_TEST_ROOT/$project.running"
        ;;
    ps)
        [ -f "$AUTOPR_TEST_ROOT/$project.running" ] && printf '%s\n' "$project-container"
        ;;
    stop)
        rm -f "$AUTOPR_TEST_ROOT/$project.running"
        ;;
    exec|build|port)
        ;;
    *) exit 1 ;;
esac
EOF

cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
[ "$1 $2" = "run list" ] || exit 1
if [ "${AUTOPR_TEST_ACTIVE:-0}" = 1 ]; then
    printf '%s\n' '[{"databaseId":9,"status":"in_progress","url":"https://example.invalid/run/9"}]'
else
    printf '%s\n' '[]'
fi
EOF

cat > "$TMP_DIR/bin/launchctl" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_ROOT/launchctl.log"
case "$*" in
    *github-actions-runner*) flag="$AUTOPR_TEST_ROOT/runner.loaded" ;;
    *) flag="$AUTOPR_TEST_ROOT/launchagent.loaded" ;;
esac
case "$1" in
    print) [ -f "$flag" ] ;;
    bootstrap|kickstart) : > "$flag" ;;
    bootout) rm -f "$flag" ;;
esac
EOF

cat > "$TMP_DIR/bin/tmux" <<'EOF'
#!/usr/bin/env bash
case "$1" in
    has-session) [ -f "$AUTOPR_TEST_ROOT/tmux.session" ] ;;
    list-panes)
        if [ -f "$AUTOPR_TEST_ROOT/dashboard.broken" ]; then printf '%s\n' 0 1 0 0;
        else printf '%s\n' 0 0 0 0; fi
        ;;
    kill-session) rm -f "$AUTOPR_TEST_ROOT/tmux.session" ;;
esac
EOF

cat > "$TMP_DIR/runtime/ensure-dashboard.sh" <<'EOF'
#!/usr/bin/env bash
: > "$AUTOPR_TEST_ROOT/tmux.session"
EOF
chmod +x "$TMP_DIR/bin/docker" "$TMP_DIR/bin/launchctl" "$TMP_DIR/bin/tmux" \
    "$TMP_DIR/bin/gh" "$TMP_DIR/runtime/ensure-dashboard.sh"
: > "$TMP_DIR/launch-agent.plist"
: > "$TMP_DIR/github-actions-runner.plist"
: > "$TMP_DIR/auth.json"

run_msandbox() {
    env PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_ROOT="$TMP_DIR" \
        AGENT_SANDBOX_SKIP_HOST_SERVICES=1 AUTOPR_GH_BIN="$TMP_DIR/bin/gh" \
        AUTOPR_STATE_DIR="$TMP_DIR/state" \
        MSANDBOX_STATE_DIR="$TMP_DIR/v2-state" \
        MSANDBOX_DATA_DIR="$TMP_DIR/v2-data" \
        MSANDBOX_CONFIG_DIR="$TMP_DIR/v2-config" \
        AUTOPR_DISPATCH_INSTALL_ROOT="$TMP_DIR/runtime" \
        AUTOPR_LAUNCH_AGENT_PLIST="$TMP_DIR/launch-agent.plist" \
        AUTOPR_LAUNCHCTL_BIN="$TMP_DIR/bin/launchctl" \
        AUTOPR_TMUX_BIN="$TMP_DIR/bin/tmux" \
        AUTOPR_RUNNER_LAUNCH_LABEL=com.matcha.github-actions-runner \
        AUTOPR_RUNNER_LAUNCH_AGENT_PLIST="$TMP_DIR/github-actions-runner.plist" \
        "$MSANDBOX" "$@"
}

run_msandbox start >/dev/null
check "msandbox start enables the primary container, timer, dashboard, and runner" \
    $([ -f "$TMP_DIR/matcha-agent-sandbox.running" ] \
      && [ -f "$TMP_DIR/state/autopr-enabled" ] \
      && [ -f "$TMP_DIR/launchagent.loaded" ] \
      && [ -f "$TMP_DIR/runner.loaded" ] \
      && [ -f "$TMP_DIR/tmux.session" ] \
      && grep -q '^kickstart ' "$TMP_DIR/launchctl.log" \
      && echo 0 || echo 1)

run_msandbox autopr-ready
check "autopr-ready succeeds only while the master switch is on" $?

primary_state="$(run_msandbox workspace-state)"
check "workspace-state reports the selected Compose project's real state" \
    $([ "$primary_state" = running ] && echo 0 || echo 1)

primary_activity="$(AUTOPR_TEST_PRIMARY_AGENT=1 run_msandbox status)"
check "activity status identifies a coding agent in the primary sandbox" \
    $(printf '%s' "$primary_activity" | grep -q \
      'ACTIVE — a coding agent is running in the primary sandbox' && echo 0 || echo 1)

env PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_ROOT="$TMP_DIR" \
    AGENT_SANDBOX_SKIP_HOST_SERVICES=1 AGENT_SANDBOX_AUTOPR=1 \
    AUTOPR_STATE_DIR="$TMP_DIR/state" \
    AUTOPR_LAUNCHCTL_BIN="$TMP_DIR/bin/launchctl" AUTOPR_TMUX_BIN="$TMP_DIR/bin/tmux" \
    SANDBOX_CODEX_AUTH_FILE="$TMP_DIR/auth.json" \
    SANDBOX_WORKSPACE_DIR="$TMP_DIR/workspace" SANDBOX_AWS_DIR="$TMP_DIR/empty-aws" \
    "$MSANDBOX" exec true >/dev/null
check "dedicated AutoPR lane starts while the master switch is on" \
    $([ -f "$TMP_DIR/matcha-kanban-autopr-sandbox.running" ] && echo 0 || echo 1)

: > "$TMP_DIR/matcha-error-autofix-sandbox.running"
: > "$TMP_DIR/matcha-autopr-self-audit-sandbox.running"
audit_activity="$(AUTOPR_TEST_AUDIT_AGENT=1 run_msandbox status)"
check "activity detection includes the error and self-audit worker sandboxes" \
    $(printf '%s' "$audit_activity" | grep -q \
      'ACTIVE — an AutoPR coding agent is running' && echo 0 || echo 1)

bare_output="$(run_msandbox)"
check "non-interactive bare msandbox reports sessions without changing the control plane" \
    $(printf '%s' "$bare_output" | grep -q 'No active msandbox sessions' \
      && [ -f "$TMP_DIR/state/autopr-enabled" ] \
      && [ -f "$TMP_DIR/matcha-agent-sandbox.running" ] \
      && [ -f "$TMP_DIR/tmux.session" ] \
      && echo 0 || echo 1)

set +e
AUTOPR_TEST_ACTIVE=1 run_msandbox codex >/dev/null 2>&1
active_entry_rc=$?
set -e
check "legacy single-workspace shorthand still refuses to collide with active work" \
    $([ "$active_entry_rc" != 0 ] && echo 0 || echo 1)

set +e
AUTOPR_TEST_ACTIVE=1 run_msandbox stop >/dev/null 2>&1
active_stop_rc=$?
set -e
check "msandbox stop refuses to interrupt active AutoPR work" \
    $([ "$active_stop_rc" != 0 ] \
      && [ -f "$TMP_DIR/state/autopr-enabled" ] \
      && [ -f "$TMP_DIR/matcha-agent-sandbox.running" ] \
      && echo 0 || echo 1)

AUTOPR_TEST_ACTIVE=1 run_msandbox stop --force >/dev/null
check "forced stop disables timer/dashboard/runner and stops both sandboxes" \
    $([ ! -e "$TMP_DIR/state/autopr-enabled" ] \
      && [ ! -e "$TMP_DIR/launchagent.loaded" ] \
      && [ ! -e "$TMP_DIR/runner.loaded" ] \
      && [ ! -e "$TMP_DIR/tmux.session" ] \
      && [ ! -e "$TMP_DIR/matcha-agent-sandbox.running" ] \
      && [ ! -e "$TMP_DIR/matcha-kanban-autopr-sandbox.running" ] \
      && [ ! -e "$TMP_DIR/matcha-error-autofix-sandbox.running" ] \
      && [ ! -e "$TMP_DIR/matcha-autopr-self-audit-sandbox.running" ] \
      && echo 0 || echo 1)

run_msandbox start >/dev/null
check "msandbox start bootstraps the self-hosted runner back after a stop" \
    $([ -f "$TMP_DIR/runner.loaded" ] && echo 0 || echo 1)
AUTOPR_TEST_ACTIVE=1 run_msandbox off >/dev/null
check "msandbox off immediately shuts down the dashboard, runner, and both sandboxes" \
    $([ ! -e "$TMP_DIR/state/autopr-enabled" ] \
      && [ ! -e "$TMP_DIR/launchagent.loaded" ] \
      && [ ! -e "$TMP_DIR/runner.loaded" ] \
      && [ ! -e "$TMP_DIR/tmux.session" ] \
      && [ ! -e "$TMP_DIR/matcha-agent-sandbox.running" ] \
      && [ ! -e "$TMP_DIR/matcha-kanban-autopr-sandbox.running" ] \
      && echo 0 || echo 1)

set +e
env PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_ROOT="$TMP_DIR" \
    AGENT_SANDBOX_SKIP_HOST_SERVICES=1 AGENT_SANDBOX_AUTOPR=1 \
    AUTOPR_STATE_DIR="$TMP_DIR/state" \
    AUTOPR_LAUNCHCTL_BIN="$TMP_DIR/bin/launchctl" AUTOPR_TMUX_BIN="$TMP_DIR/bin/tmux" \
    SANDBOX_CODEX_AUTH_FILE="$TMP_DIR/auth.json" \
    SANDBOX_WORKSPACE_DIR="$TMP_DIR/workspace" SANDBOX_AWS_DIR="$TMP_DIR/empty-aws" \
    "$MSANDBOX" exec true >/dev/null 2>&1
off_rc=$?
set -e
check "dedicated AutoPR lane fails closed after msandbox off" \
    $([ "$off_rc" != 0 ] \
      && [ ! -e "$TMP_DIR/matcha-kanban-autopr-sandbox.running" ] \
      && echo 0 || echo 1)

: > "$TMP_DIR/dashboard.broken"
set +e
run_msandbox start >/dev/null 2>&1
broken_start_rc=$?
set -e
check "partial startup rolls back instead of leaving an enabled system" \
    $([ "$broken_start_rc" != 0 ] \
      && [ ! -e "$TMP_DIR/state/autopr-enabled" ] \
      && [ ! -e "$TMP_DIR/matcha-agent-sandbox.running" ] \
      && [ ! -e "$TMP_DIR/tmux.session" ] \
      && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
