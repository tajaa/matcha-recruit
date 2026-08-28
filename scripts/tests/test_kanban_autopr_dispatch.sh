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
if [ "$1 $2" = "run list" ]; then
  [ "${AUTOPR_TEST_LIST_FAIL:-0}" = 0 ] || exit 1
  printf '%s\n' "${AUTOPR_TEST_RUNS:-[]}"
  exit 0
fi
if [ "$1 $2" = "workflow run" ]; then
  [ "${AUTOPR_TEST_DISPATCH_FAIL:-0}" = 0 ] || exit 1
  printf 'dispatched\n' >> "$AUTOPR_TEST_DISPATCHES"
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

run_dispatcher() {
  AUTOPR_GH_BIN="$TMP_DIR/gh" AUTOPR_DISPATCH_LOG="$TMP_DIR/log.jsonl" \
    AUTOPR_DOCKER_BIN="$TMP_DIR/docker" AUTOPR_ENABLE_FILE="$TMP_DIR/autopr-enabled" \
    AUTOPR_DISPATCH_LOCK_DIR="$TMP_DIR/lock" AUTOPR_TEST_DISPATCHES="$TMP_DIR/dispatches" \
    AUTOPR_TMUX_DASHBOARD=0 \
    "$DISPATCHER" >/dev/null 2>&1
}

rm "$TMP_DIR/autopr-enabled"
run_dispatcher
check "msandbox-off master switch skips before dispatch" \
  $(grep -q 'msandbox-off' "$TMP_DIR/log.jsonl" \
    && [ ! -e "$TMP_DIR/dispatches" ] && echo 0 || echo 1)
touch "$TMP_DIR/autopr-enabled"

AUTOPR_TEST_CONTAINER_OFF=1 run_dispatcher
check "stopped primary sandbox skips before dispatch" \
  $(grep -q 'msandbox-off' "$TMP_DIR/log.jsonl" \
    && [ ! -e "$TMP_DIR/dispatches" ] && echo 0 || echo 1)

AUTOPR_TEST_RUNS='[]' run_dispatcher
check "idle workflow dispatches once" \
  $([ "$(wc -l < "$TMP_DIR/dispatches" | tr -d '[:space:]')" = 1 ] && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_RUNS='[{"databaseId":7,"status":"in_progress","event":"workflow_dispatch","createdAt":"2026-08-27T00:00:00Z","url":"x"}]' run_dispatcher
check "active workflow skips dispatch" \
  $([ ! -e "$TMP_DIR/dispatches" ] && grep -q 'active-workflow' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)

rm -f "$TMP_DIR/dispatches"
AUTOPR_TEST_LIST_FAIL=1 run_dispatcher || list_rc=$?
check "run-list failure fails closed" \
  $([ "${list_rc:-0}" != 0 ] && [ ! -e "$TMP_DIR/dispatches" ] && echo 0 || echo 1)

AUTOPR_TEST_DISPATCH_FAIL=1 AUTOPR_TEST_RUNS='[]' run_dispatcher || dispatch_rc=$?
check "dispatch failure is visible and nonzero" \
  $([ "${dispatch_rc:-0}" != 0 ] && grep -q 'dispatch-failed' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)

mkdir "$TMP_DIR/lock"
AUTOPR_TEST_RUNS='[]' run_dispatcher
check "local lock produces a harmless skip" \
  $(grep -q 'local-lock' "$TMP_DIR/log.jsonl" && echo 0 || echo 1)
rmdir "$TMP_DIR/lock"

rendered="$TMP_DIR/com.matcha.kanban-autopr-dispatch.plist"
sed -e "s|__DISPATCHER_PATH__|$DISPATCHER|g" -e "s|__USER_HOME__|$TMP_DIR|g" "$TEMPLATE" > "$rendered"
plutil -lint "$rendered" >/dev/null
check "LaunchAgent plist is valid and uses the required timer" \
  $(grep -q '<integer>300</integer>' "$rendered" && grep -q '<key>RunAtLoad</key>' "$rendered" && echo 0 || echo 1)
check "LaunchAgent PATH can reach the Docker Desktop CLI used by msandbox" \
  $(grep -q '<string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>' "$rendered" && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
