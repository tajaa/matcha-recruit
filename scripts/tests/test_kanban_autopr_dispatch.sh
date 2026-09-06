#!/usr/bin/env bash
# Isolated dispatcher tests: no GitHub, launchd, board, or model access.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DISPATCHER="$REPO_ROOT/scripts/kanban-autopr/dispatch-if-idle.sh"
TEMPLATE="$REPO_ROOT/scripts/kanban-autopr/launchd/com.matcha.kanban-autopr-dispatch.plist.in"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
PASS=0
FAIL=0

check() {
    local desc="$1" ok="$2"
    if [ "$ok" = 0 ]; then echo "PASS: $desc"; PASS=$((PASS + 1));
    else echo "FAIL: $desc"; FAIL=$((FAIL + 1)); fi
}

cat > "$TMP_DIR/gh" <<'EOF'
#!/usr/bin/env bash
[ -z "${AUTOPR_TEST_GH_CALLS:-}" ] || printf '%s\n' "$*" >> "$AUTOPR_TEST_GH_CALLS"
if [ "$1 $2" = "run list" ]; then
  [ "${AUTOPR_TEST_LIST_FAIL:-0}" = 0 ] || exit 1
  jq -cn \
    --argjson errors "${AUTOPR_TEST_ERROR_RUNS:-[]}" \
    --argjson audit "${AUTOPR_TEST_AUDIT_RUNS:-[]}" \
    --argjson admin "${AUTOPR_TEST_ADMIN_UPDATES_RUNS:-[]}" \
    --argjson kanban "${AUTOPR_TEST_KANBAN_RUNS:-[]}" '
      ($errors | map(. + {workflowName:"Silent error autofix"}))
      + ($audit | map(. + {workflowName:"AutoPR self audit"}))
      + ($admin | map(. + {workflowName:"Publish production admin updates"}))
      + ($kanban | map(. + {workflowName:"Kanban autopr"}))
    '
  exit 0
fi
if [ "$1" = api ] && [[ "$*" == *"/actions/workflows/"*"/dispatches"* ]]; then
  [ "${AUTOPR_TEST_DISPATCH_FAIL:-0}" = 0 ] || exit 1
  for arg in "$@"; do
    case "$arg" in
      repos/*/actions/workflows/*/dispatches)
        workflow="${arg%/dispatches}"
        printf '%s\n' "${workflow##*/}" >> "$AUTOPR_TEST_DISPATCHES"
        ;;
    esac
  done
  exit 0
fi
exit 1
EOF
chmod +x "$TMP_DIR/gh"

cat > "$TMP_DIR/docker" <<'EOF'
#!/usr/bin/env bash
[ "$1" = ps ] || exit 1
[ "${AUTOPR_TEST_CONTAINER_OFF:-0}" = 0 ] || exit 0
printf 'primary-container-id\n'
EOF
chmod +x "$TMP_DIR/docker"
touch "$TMP_DIR/autopr-enabled"

# Stand-in for has-run-request.sh: 0 = a card is queued, 3 = nothing, 1 = the
# board could not be asked.
cat > "$TMP_DIR/run-request-probe" <<'EOF'
#!/usr/bin/env bash
[ -z "${AUTOPR_TEST_PROBE_CALLS:-}" ] || printf 'probe\n' >> "$AUTOPR_TEST_PROBE_CALLS"
exit "${AUTOPR_TEST_PROBE_EXIT:-3}"
EOF
chmod +x "$TMP_DIR/run-request-probe"

# Stand-in for ensure-dashboard.sh. The observer panes it (re)creates are
# themselves GitHub readers, so only the five-minute scheduler may call it.
cat > "$TMP_DIR/ensure-dashboard" <<'EOF'
#!/usr/bin/env bash
printf 'ensure\n' >> "$AUTOPR_TEST_DASHBOARD_CALLS"
EOF
chmod +x "$TMP_DIR/ensure-dashboard"

run_dispatcher() {
  AUTOPR_GH_BIN="$TMP_DIR/gh" AUTOPR_DISPATCH_LOG="$TMP_DIR/log.jsonl" \
    AUTOPR_DOCKER_BIN="$TMP_DIR/docker" AUTOPR_ENABLE_FILE="$TMP_DIR/autopr-enabled" \
    AUTOPR_DISPATCH_LOCK_DIR="$TMP_DIR/lock" AUTOPR_TEST_DISPATCHES="$TMP_DIR/dispatches" \
    AUTOPR_GITHUB_SNAPSHOT_CACHE_DIR="$TMP_DIR/github-cache" \
    AUTOPR_GITHUB_SNAPSHOT_TTL_SECONDS=0 \
    AUTOPR_TMUX_DASHBOARD="${AUTOPR_TMUX_DASHBOARD:-0}" \
    AUTOPR_RUN_REQUEST_PROBE="$TMP_DIR/run-request-probe" \
    AUTOPR_DISPATCH_STATE_DIR="$TMP_DIR/state" \
    "$DISPATCHER" "$@" >/dev/null 2>&1
}

rm "$TMP_DIR/autopr-enabled"
run_dispatcher
check "msandbox-off master switch skips before dispatch" \
  $(grep -q 'msandbox-off' "$TMP_DIR/log.jsonl" \
    && [ ! -e "$TMP_DIR/dispatches" ] && echo 0 || echo 1)
touch "$TMP_DIR/autopr-enabled"

AUTOPR_GH_BIN="$TMP_DIR/gh" AUTOPR_TEST_GH_CALLS="$TMP_DIR/snapshot-gh.log" \
  AUTOPR_GITHUB_SNAPSHOT_CACHE_DIR="$TMP_DIR/shared-snapshot" \
  AUTOPR_GITHUB_SNAPSHOT_TTL_SECONDS=60 \
  "$REPO_ROOT/scripts/kanban-autopr/run-snapshot.sh" >/dev/null
AUTOPR_GH_BIN="$TMP_DIR/gh" AUTOPR_TEST_GH_CALLS="$TMP_DIR/snapshot-gh.log" \
  AUTOPR_GITHUB_SNAPSHOT_CACHE_DIR="$TMP_DIR/shared-snapshot" \
  AUTOPR_GITHUB_SNAPSHOT_TTL_SECONDS=60 \
  "$REPO_ROOT/scripts/kanban-autopr/run-snapshot.sh" >/dev/null
check "dashboard panes share one cached GitHub run-list request" \
  $([ "$(grep -c '^run list ' "$TMP_DIR/snapshot-gh.log")" = 1 ] && echo 0 || echo 1)

AUTOPR_TEST_CONTAINER_OFF=1 run_dispatcher
check "stopped primary sandbox skips before dispatch" \
  $(grep -q 'msandbox-off' "$TMP_DIR/log.jsonl" \
    && [ ! -e "$TMP_DIR/dispatches" ] && echo 0 || echo 1)

AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_KANBAN_RUNS='[]' run_dispatcher
check "stale error lane gets the first idle slot" \
  $([ "$(cat "$TMP_DIR/dispatches")" = "silent-error-autofix.yml" ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
recent="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
AUTOPR_TEST_ERROR_RUNS="[{\"databaseId\":6,\"status\":\"completed\",\"event\":\"workflow_dispatch\",\"createdAt\":\"$recent\",\"updatedAt\":\"$recent\",\"url\":\"x\"}]" \
  AUTOPR_TEST_AUDIT_RUNS='[]' \
  AUTOPR_TEST_KANBAN_RUNS='[]' run_dispatcher
check "recent error pass gives a stale self-audit the next idle slot" \
  $([ "$(cat "$TMP_DIR/dispatches")" = "autopr-self-audit.yml" ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_ERROR_RUNS="[{\"databaseId\":6,\"status\":\"completed\",\"event\":\"workflow_dispatch\",\"createdAt\":\"$recent\",\"updatedAt\":\"$recent\",\"url\":\"x\"}]" \
  AUTOPR_TEST_AUDIT_RUNS="[{\"databaseId\":8,\"status\":\"completed\",\"event\":\"workflow_dispatch\",\"createdAt\":\"$recent\",\"updatedAt\":\"$recent\",\"url\":\"x\"}]" \
  AUTOPR_TEST_KANBAN_RUNS='[]' run_dispatcher
check "recent error and audit passes advance the Kanban lane" \
  $([ "$(cat "$TMP_DIR/dispatches")" = "kanban-autopr.yml" ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_ERROR_RUNS='[]' \
  AUTOPR_TEST_AUDIT_RUNS='[]' \
  AUTOPR_TEST_KANBAN_RUNS='[{"databaseId":7,"status":"in_progress","event":"workflow_dispatch","createdAt":"2026-08-27T00:00:00Z","updatedAt":"2026-08-27T00:00:00Z","url":"x"}]' \
  run_dispatcher
check "active work in either lane skips dispatch" \
  $([ ! -e "$TMP_DIR/dispatches" ] && grep -q 'active-autopr-workflow' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_ERROR_RUNS='[]' \
  AUTOPR_TEST_AUDIT_RUNS='[]' \
  AUTOPR_TEST_KANBAN_RUNS='[]' \
  AUTOPR_TEST_ADMIN_UPDATES_RUNS='[{"databaseId":10,"status":"queued","event":"workflow_dispatch","createdAt":"2026-08-31T00:00:00Z","updatedAt":"2026-08-31T00:00:00Z","url":"x"}]' \
  run_dispatcher
check "queued admin-update publication blocks a competing AutoPR dispatch" \
  $([ ! -e "$TMP_DIR/dispatches" ] && grep -q 'active-autopr-workflow' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)

# ── the Kanban lane is the slow one, and the card button is the way past it ──
rm -f "$TMP_DIR/dispatches"
recent_kanban="[{\"databaseId\":9,\"status\":\"completed\",\"event\":\"workflow_dispatch\",\"createdAt\":\"$recent\",\"updatedAt\":\"$recent\",\"url\":\"x\"}]"
stale="$(date -u -v-30M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '30 minutes ago' +%Y-%m-%dT%H:%M:%SZ)"
stale_kanban="[{\"databaseId\":9,\"status\":\"completed\",\"event\":\"workflow_dispatch\",\"createdAt\":\"$stale\",\"updatedAt\":\"$stale\",\"url\":\"x\"}]"
recent_error="[{\"databaseId\":6,\"status\":\"completed\",\"event\":\"workflow_dispatch\",\"createdAt\":\"$recent\",\"updatedAt\":\"$recent\",\"url\":\"x\"}]"
recent_audit="[{\"databaseId\":8,\"status\":\"completed\",\"event\":\"workflow_dispatch\",\"createdAt\":\"$recent\",\"updatedAt\":\"$recent\",\"url\":\"x\"}]"

AUTOPR_TEST_ERROR_RUNS="$recent_error" AUTOPR_TEST_AUDIT_RUNS="$recent_audit" \
  AUTOPR_TEST_KANBAN_RUNS="$recent_kanban" run_dispatcher
check "a Kanban pass inside the twenty-minute window does not re-dispatch" \
  $([ ! -e "$TMP_DIR/dispatches" ] && grep -q 'kanban-not-due' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_ERROR_RUNS="$recent_error" AUTOPR_TEST_AUDIT_RUNS="$recent_audit" \
  AUTOPR_TEST_KANBAN_RUNS="$stale_kanban" run_dispatcher
check "the Kanban lane still runs once its twenty minutes are up" \
  $([ "$(cat "$TMP_DIR/dispatches")" = "kanban-autopr.yml" ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches" "$TMP_DIR/probe.log" "$TMP_DIR/watch-gh.log"
rm -rf "$TMP_DIR/state"
AUTOPR_TEST_PROBE_EXIT=3 AUTOPR_TEST_PROBE_CALLS="$TMP_DIR/probe.log" \
  AUTOPR_TEST_GH_CALLS="$TMP_DIR/watch-gh.log" \
  AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_AUDIT_RUNS='[]' AUTOPR_TEST_KANBAN_RUNS='[]' \
  run_dispatcher --if-requested
check "an idle watch tick asks the board and never touches GitHub" \
  $([ ! -e "$TMP_DIR/dispatches" ] && [ ! -e "$TMP_DIR/watch-gh.log" ] \
    && [ -s "$TMP_DIR/probe.log" ] && echo 0 || echo 1)

check "an idle watch tick leaves the shared dispatch log alone" \
  $(! grep -q 'no-run-request' "$TMP_DIR/log.jsonl" \
    && [ -f "$TMP_DIR/state/last-watch-tick" ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches" "$TMP_DIR/dashboard-calls"
AUTOPR_TEST_DASHBOARD_CALLS="$TMP_DIR/dashboard-calls" \
  AUTOPR_DASHBOARD_ENSURE="$TMP_DIR/ensure-dashboard" AUTOPR_TMUX_DASHBOARD=1 \
  AUTOPR_TEST_PROBE_EXIT=3 AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_AUDIT_RUNS='[]' \
  AUTOPR_TEST_KANBAN_RUNS='[]' run_dispatcher --if-requested
check "an idle watch tick never re-primes the observer panes" \
  $([ ! -e "$TMP_DIR/dashboard-calls" ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_DASHBOARD_CALLS="$TMP_DIR/dashboard-calls" \
  AUTOPR_DASHBOARD_ENSURE="$TMP_DIR/ensure-dashboard" AUTOPR_TMUX_DASHBOARD=1 \
  AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_AUDIT_RUNS='[]' \
  AUTOPR_TEST_KANBAN_RUNS='[]' run_dispatcher
check "the five-minute scheduler still keeps the observer panes alive" \
  $([ -s "$TMP_DIR/dashboard-calls" ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_PROBE_EXIT=1 AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_AUDIT_RUNS='[]' \
  AUTOPR_TEST_KANBAN_RUNS='[]' run_dispatcher --if-requested
check "an unreachable board never forces a run" \
  $([ ! -e "$TMP_DIR/dispatches" ] \
    && grep -q 'run-request-probe-failed' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_PROBE_EXIT=0 AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_AUDIT_RUNS='[]' \
  AUTOPR_TEST_KANBAN_RUNS="$recent_kanban" run_dispatcher --if-requested
check "a queued card jumps the twenty-minute wait and the other lanes" \
  $([ "$(cat "$TMP_DIR/dispatches")" = "kanban-autopr.yml" ] \
    && grep -q 'kanban-run-request' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_PROBE_EXIT=0 AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_AUDIT_RUNS='[]' \
  AUTOPR_TEST_KANBAN_RUNS="$recent_kanban" run_dispatcher --if-requested
check "a card that cannot be picked up cannot spin the runner every minute" \
  $([ ! -e "$TMP_DIR/dispatches" ] && [ -f "$TMP_DIR/state/last-forced-kanban" ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_LIST_FAIL=1 run_dispatcher || list_rc=$?
check "run-list failure fails closed" \
  $([ "${list_rc:-0}" != 0 ] && [ ! -e "$TMP_DIR/dispatches" ] && echo 0 || echo 1)

AUTOPR_TEST_DISPATCH_FAIL=1 AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_AUDIT_RUNS='[]' AUTOPR_TEST_KANBAN_RUNS='[]' run_dispatcher || dispatch_rc=$?
check "dispatch failure is visible and nonzero" \
  $([ "${dispatch_rc:-0}" != 0 ] && grep -q 'silent-error-autofix.yml-dispatch-failed' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)

mkdir "$TMP_DIR/lock"
AUTOPR_TEST_ERROR_RUNS='[]' AUTOPR_TEST_AUDIT_RUNS='[]' AUTOPR_TEST_KANBAN_RUNS='[]' run_dispatcher
check "local lock produces a harmless skip" \
  $(grep -q 'local-lock' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)
rmdir "$TMP_DIR/lock"

rendered="$TMP_DIR/com.matcha.kanban-autopr-dispatch.plist"
sed -e "s|__DISPATCHER_PATH__|$DISPATCHER|g" -e "s|__USER_HOME__|$TMP_DIR|g" "$TEMPLATE" > "$rendered"
if command -v plutil >/dev/null 2>&1; then
  plutil -lint "$rendered" >/dev/null
else
  python3 -c 'import plistlib, sys; plistlib.load(open(sys.argv[1], "rb"))' "$rendered"
fi
check "LaunchAgent plist is valid and uses the required timer" \
  $(grep -q '<integer>300</integer>' "$rendered" && grep -q '<key>RunAtLoad</key>' "$rendered" && echo 0 || echo 1)
check "LaunchAgent PATH can reach the Docker Desktop CLI used by msandbox" \
  $(grep -q '<string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>' "$rendered" && echo 0 || echo 1)

watch_template="$REPO_ROOT/scripts/kanban-autopr/launchd/com.matcha.kanban-autopr-request-watch.plist.in"
watch_rendered="$TMP_DIR/com.matcha.kanban-autopr-request-watch.plist"
sed -e "s|__DISPATCHER_PATH__|$DISPATCHER|g" -e "s|__USER_HOME__|$TMP_DIR|g" \
  "$watch_template" > "$watch_rendered"
if command -v plutil >/dev/null 2>&1; then
  plutil -lint "$watch_rendered" >/dev/null
else
  python3 -c 'import plistlib, sys; plistlib.load(open(sys.argv[1], "rb"))' "$watch_rendered"
fi
check "request watcher runs the same dispatcher every minute in requested mode" \
  $(grep -q '<integer>60</integer>' "$watch_rendered" \
    && grep -q '<string>--if-requested</string>' "$watch_rendered" \
    && grep -q "$DISPATCHER" "$watch_rendered" && echo 0 || echo 1)
check "installer ships the probe and both LaunchAgents" \
  $(grep -q 'has-run-request.sh' "$REPO_ROOT/scripts/kanban-autopr/install-launch-agent.sh" \
    && grep -q 'WATCH_PLIST_DESTINATION' "$REPO_ROOT/scripts/kanban-autopr/install-launch-agent.sh" \
    && grep -q 'kanban-autopr-request-watch' "$REPO_ROOT/scripts/agent-sandbox.sh" && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
