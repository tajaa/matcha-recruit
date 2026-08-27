#!/usr/bin/env bash
# Tests the tmux layout and the dashboard renderers without GitHub or Matcha.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOPR_DIR="$REPO_ROOT/scripts/kanban-autopr"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
PASS=0
FAIL=0

check() {
  local desc="$1" ok="$2"
  if [ "$ok" = 0 ]; then echo "PASS: $desc"; PASS=$((PASS + 1));
  else echo "FAIL: $desc"; FAIL=$((FAIL + 1)); fi
}

cat > "$TMP_DIR/tmux" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_TMUX_LOG"
if [ "$1" = has-session ]; then [ -e "$AUTOPR_TEST_SESSION" ]; exit; fi
if [ "$1" = new-session ]; then
  mkdir "$AUTOPR_TEST_SESSION" 2>/dev/null || { echo "duplicate session" >&2; exit 1; }
  exit 0
fi
if [ "$1" = display-message ]; then printf '%%0\n'; exit 0; fi
if [ "$1" = split-window ]; then
  count=0
  [ ! -e "$AUTOPR_TEST_SPLITS" ] || count="$(cat "$AUTOPR_TEST_SPLITS")"
  count=$((count + 1)); printf '%s' "$count" > "$AUTOPR_TEST_SPLITS"; printf '%%%s\n' "$count"; exit 0
fi
exit 0
EOF
chmod +x "$TMP_DIR/tmux"

AUTOPR_TMUX_BIN="$TMP_DIR/tmux" AUTOPR_TEST_TMUX_LOG="$TMP_DIR/tmux.log" \
  AUTOPR_TEST_SESSION="$TMP_DIR/session" AUTOPR_TEST_SPLITS="$TMP_DIR/splits" \
  "$AUTOPR_DIR/ensure-dashboard.sh" >/dev/null
AUTOPR_TMUX_BIN="$TMP_DIR/tmux" AUTOPR_TEST_TMUX_LOG="$TMP_DIR/tmux.log" \
  AUTOPR_TEST_SESSION="$TMP_DIR/session" AUTOPR_TEST_SPLITS="$TMP_DIR/splits" \
  "$AUTOPR_DIR/ensure-dashboard.sh" >/dev/null

check "tmux observer creates one session with three panes" \
  $([ "$(grep -c '^new-session ' "$TMP_DIR/tmux.log")" = 1 ] \
    && [ "$(grep -c '^split-window ' "$TMP_DIR/tmux.log")" = 2 ] && echo 0 || echo 1)
check "tmux panes receive operator-facing titles" \
  $(grep -q '24h queue + PR dashboard' "$TMP_DIR/tmux.log" \
    && grep -q 'live PR-creation work' "$TMP_DIR/tmux.log" \
    && grep -q 'timer + runner health' "$TMP_DIR/tmux.log" && echo 0 || echo 1)

rm -rf "$TMP_DIR/session" "$TMP_DIR/ensure.lock"
: > "$TMP_DIR/tmux.log"
rm -f "$TMP_DIR/splits"
AUTOPR_TMUX_BIN="$TMP_DIR/tmux" AUTOPR_TMUX_LOCK_DIR="$TMP_DIR/ensure.lock" \
  AUTOPR_TEST_TMUX_LOG="$TMP_DIR/tmux.log" AUTOPR_TEST_SESSION="$TMP_DIR/session" \
  AUTOPR_TEST_SPLITS="$TMP_DIR/splits" "$AUTOPR_DIR/ensure-dashboard.sh" >/dev/null &
first_pid=$!
AUTOPR_TMUX_BIN="$TMP_DIR/tmux" AUTOPR_TMUX_LOCK_DIR="$TMP_DIR/ensure.lock" \
  AUTOPR_TEST_TMUX_LOG="$TMP_DIR/tmux.log" AUTOPR_TEST_SESSION="$TMP_DIR/session" \
  AUTOPR_TEST_SPLITS="$TMP_DIR/splits" "$AUTOPR_DIR/ensure-dashboard.sh" >/dev/null &
second_pid=$!
set +e
wait "$first_pid"
first_rc=$?
wait "$second_pid"
second_rc=$?
set -e
check "simultaneous dashboard starts create exactly one tmux session" \
  $([ "$first_rc" = 0 ] && [ "$second_rc" = 0 ] \
    && [ "$(grep -c '^new-session ' "$TMP_DIR/tmux.log")" = 1 ] && echo 0 || echo 1)

VIEW_DIR="$TMP_DIR/view"
mkdir "$VIEW_DIR"
cp "$AUTOPR_DIR/dashboard.sh" "$VIEW_DIR/dashboard.sh"
cat > "$VIEW_DIR/collect.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '[{"task_id":"a","id8":"aaaa0000","project_title":"MATCHA","title":"Fix intake","board_column":"changes_requested","last_moved_at":"2026-08-27T00:00:00Z","created_at":"2026-08-27T00:00:00Z","progress_note":""},{"task_id":"b","id8":"bbbb0000","project_title":"MATCHA","title":"Polish reports","board_column":"todo","last_moved_at":"2026-08-27T01:00:00Z","created_at":"2026-08-27T01:00:00Z","progress_note":""}]'
EOF
cat > "$VIEW_DIR/select.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '{"id8":"aaaa0000","project_title":"MATCHA","title":"Fix intake","board_column":"changes_requested","mode":"rework"}'
EOF
chmod +x "$VIEW_DIR"/*.sh

cat > "$TMP_DIR/gh" <<'EOF'
#!/usr/bin/env bash
if [ "$1 $2" = "run list" ]; then
  printf '%s\n' '[{"databaseId":900,"status":"in_progress","conclusion":null,"event":"workflow_dispatch","createdAt":"2099-08-27T01:00:00Z","updatedAt":"2099-08-27T01:01:00Z","url":"x","displayTitle":"Kanban autopr"}]'
elif [ "$1 $2" = "pr list" ] && [[ "$*" == *"--state open"* ]]; then
  printf '%s\n' '[{"number":307,"title":"🟡 [C91] fix: Intake","isDraft":true,"headRefName":"bot/task-aaaa0000","updatedAt":"2099-08-27T01:00:00Z","labels":[{"name":"autopr"}],"url":"x"}]'
elif [ "$1 $2" = "pr list" ]; then
  printf '%s\n' '[{"number":306,"title":"🟠 [C80] fix: Reports","mergedAt":"2099-08-27T00:00:00Z","url":"x"}]'
fi
EOF
chmod +x "$TMP_DIR/gh"

AUTOPR_DASHBOARD_ONCE=1 AUTOPR_GH_BIN="$TMP_DIR/gh" "$VIEW_DIR/dashboard.sh" > "$TMP_DIR/dashboard.out"
check "24-hour dashboard shows now, next, queue, open PRs, and history" \
  $(grep -q 'WORKFLOW NOW' "$TMP_DIR/dashboard.out" \
    && grep -q 'UP NEXT' "$TMP_DIR/dashboard.out" \
    && grep -q 'BOARD QUEUE' "$TMP_DIR/dashboard.out" \
    && grep -q 'OPEN AUTO PRS' "$TMP_DIR/dashboard.out" \
    && grep -q 'MERGED AUTO PRS · LAST 24 HOURS' "$TMP_DIR/dashboard.out" \
    && grep -q 'Fix intake' "$TMP_DIR/dashboard.out" && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
