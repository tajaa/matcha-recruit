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
if [ "$1" = list-panes ]; then
  if [ -e "${AUTOPR_TEST_BROKEN_SESSION:-/nonexistent}" ]; then
    printf '%s\n' 0 1 0 0
  else
    printf '%s\n' 0 0 0 0
  fi
  exit 0
fi
if [ "$1" = kill-session ]; then
  rm -rf "$AUTOPR_TEST_SESSION"
  [ -z "${AUTOPR_TEST_BROKEN_SESSION:-}" ] || rm -f "$AUTOPR_TEST_BROKEN_SESSION"
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

check "tmux observer creates one session with four panes" \
  $([ "$(grep -c '^new-session ' "$TMP_DIR/tmux.log")" = 1 ] \
    && [ "$(grep -c '^split-window ' "$TMP_DIR/tmux.log")" = 3 ] \
    && grep -q '^split-window -h -p 42 ' "$TMP_DIR/tmux.log" \
    && [ "$(grep -c '^split-window -v -p 50 ' "$TMP_DIR/tmux.log")" = 2 ] \
    && echo 0 || echo 1)
check "tmux panes receive operator-facing titles" \
  $(grep -q 'operations overview · Pacific time' "$TMP_DIR/tmux.log" \
    && grep -q 'live agent detail' "$TMP_DIR/tmux.log" \
    && grep -q 'automation health' "$TMP_DIR/tmux.log" \
    && grep -q 'active PR detail' "$TMP_DIR/tmux.log" && echo 0 || echo 1)
check "tmux observer preserves a large mouse-scrollable history" \
  $(grep -q '^set-option -t matcha-autopr history-limit 100000' "$TMP_DIR/tmux.log" \
    && grep -q '^set-option -t matcha-autopr mouse on' "$TMP_DIR/tmux.log" \
    && echo 0 || echo 1)

: > "$TMP_DIR/broken-session"
AUTOPR_TMUX_BIN="$TMP_DIR/tmux" AUTOPR_TEST_TMUX_LOG="$TMP_DIR/tmux.log" \
  AUTOPR_TEST_SESSION="$TMP_DIR/session" AUTOPR_TEST_SPLITS="$TMP_DIR/splits" \
  AUTOPR_TEST_BROKEN_SESSION="$TMP_DIR/broken-session" \
  "$AUTOPR_DIR/ensure-dashboard.sh" >/dev/null
check "dashboard helper replaces an existing session with a dead pane" \
  $([ "$(grep -c '^new-session ' "$TMP_DIR/tmux.log")" = 2 ] \
    && grep -q '^kill-session ' "$TMP_DIR/tmux.log" \
    && [ ! -e "$TMP_DIR/broken-session" ] \
    && echo 0 || echo 1)

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
cp "$AUTOPR_DIR/plan.py" "$VIEW_DIR/plan.py"
cp "$AUTOPR_DIR/run-snapshot.sh" "$VIEW_DIR/run-snapshot.sh"
cat > "$VIEW_DIR/collect.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '[{"task_id":"a","id8":"aaaa0000","project_title":"MATCHA","title":"Fix intake","board_column":"changes_requested","last_moved_at":"2026-08-27T00:00:00Z","created_at":"2026-08-27T00:00:00Z","progress_note":""},{"task_id":"b","id8":"bbbb0000","project_title":"MATCHA","title":"Polish reports","board_column":"todo","last_moved_at":"2026-08-27T01:00:00Z","created_at":"2026-08-27T01:00:00Z","progress_note":""}]'
EOF
cat > "$VIEW_DIR/collect-pr-context.sh" <<'EOF'
#!/usr/bin/env bash
[ "${GITHUB_REPOSITORY:-}" = "tajaa/matcha-recruit" ] || exit 1
[ "${AUTOPR_TEST_PR_CONTEXT_FAIL:-false}" != true ] || exit 1
printf '%s\n' '[{"number":307,"title":"fix: Intake","isDraft":true,"state":"OPEN","headRefName":"bot/task-aaaa0000","headRefOid":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","createdAt":"2099-08-27T00:00:00Z","updatedAt":"2099-08-27T01:00:00Z","labels":["autopr"],"reviewDecision":null,"checks":[],"files":["server/app/intake.py"],"comments":[{"author":"reviewer","body":"still fails for emailed intake"}],"reviews":[]}]'
EOF
cat > "$VIEW_DIR/select.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '{"id8":"aaaa0000","project_title":"MATCHA","title":"Fix intake","board_column":"changes_requested","mode":"rework"}'
EOF
chmod +x "$VIEW_DIR"/*.sh

cat > "$TMP_DIR/gh" <<'EOF'
#!/usr/bin/env bash
if [ "$1 $2" = "run list" ]; then
  printf '%s\n' '[{"databaseId":900,"status":"in_progress","conclusion":null,"event":"workflow_dispatch","createdAt":"2099-08-27T01:00:00Z","updatedAt":"2099-08-27T01:01:00Z","url":"x","displayTitle":"Kanban autopr","workflowName":"Kanban autopr"}]'
elif [ "$1 $2" = "run view" ]; then
  printf '%s\n' '{"jobs":[{"name":"build","steps":[{"name":"Investigate","status":"in_progress"}]}]}'
elif [ "$1 $2" = "pr list" ] && [[ "$*" == *"--state open"* ]]; then
  printf '%s\n' '[{"number":307,"title":"🟡 [C91] fix: Intake","isDraft":true,"headRefName":"bot/task-aaaa0000","createdAt":"2099-08-27T00:00:00Z","updatedAt":"2099-08-27T01:00:00Z","labels":[{"name":"autopr"}],"url":"x"}]'
elif [ "$1 $2" = "pr list" ]; then
  printf '%s\n' '[{"number":306,"title":"🟠 [C80] fix: Reports","createdAt":"2099-08-27T00:00:00Z","mergedAt":"2099-08-27T01:00:00Z","headRefName":"bot/task-bbbbbbbb","labels":[{"name":"autopr"}],"url":"x"},{"number":305,"title":"fix: Error recovery","createdAt":"2099-08-27T00:00:00Z","mergedAt":"2099-08-27T00:30:00Z","headRefName":"bot/err-305","labels":[{"name":"autofix"}],"url":"x"}]'
fi
EOF
chmod +x "$TMP_DIR/gh"

cat > "$TMP_DIR/dispatch.log" <<'EOF'
{"timestamp":"2099-08-27T01:30:00Z","action":"dispatch","reason":"kanban-pass"}
EOF
dashboard_now="$(jq -nr '"2099-08-27T02:30:00Z" | fromdateiso8601')"

AUTOPR_DASHBOARD_ONCE=1 AUTOPR_GH_BIN="$TMP_DIR/gh" \
  AUTOPR_DASHBOARD_NOW_EPOCH="$dashboard_now" AUTOPR_DASHBOARD_CACHE_DIR="$TMP_DIR/dashboard-cache" \
  AUTOPR_DISPATCH_LOG="$TMP_DIR/dispatch.log" AUTOPR_CARD_SNAPSHOT="$TMP_DIR/cards-snapshot.json" \
  "$VIEW_DIR/dashboard.sh" > "$TMP_DIR/dashboard.out"
check "control board shows cross-queue plan, exact next, PR timing, and Pacific history" \
  $(grep -q 'MATCHA AUTOPR CONTROL BOARD' "$TMP_DIR/dashboard.out" \
    && grep -q 'NOW · INVESTIGATING · 1h 30m' "$TMP_DIR/dashboard.out" \
    && grep -q 'NEXT · EXACT SELECTOR RESULT' "$TMP_DIR/dashboard.out" \
    && grep -q 'QUEUE · 2 tracked' "$TMP_DIR/dashboard.out" \
    && grep -q 'PLAN · ' "$TMP_DIR/dashboard.out" \
    && grep -q 'NOT-READY PRS ONLY' "$TMP_DIR/dashboard.out" \
    && grep -q 'MERGE ORDER · 1 draft(s)' "$TMP_DIR/dashboard.out" \
    && grep -q 'OPEN BOT PRS · AGE' "$TMP_DIR/dashboard.out" \
    && grep -q 'RECENT BOT PRS · OPEN → MERGE · PACIFIC' "$TMP_DIR/dashboard.out" \
    && grep -q '#305.*ERROR' "$TMP_DIR/dashboard.out" \
    && ! grep -q '#305.*AWAITING DEPLOY/CHECK' "$TMP_DIR/dashboard.out" \
    && grep -q 'RECENT RUNS · DURATION · PACIFIC' "$TMP_DIR/dashboard.out" \
    && grep -q '6:00 PM PDT' "$TMP_DIR/dashboard.out" \
    && grep -q 'Fix intake' "$TMP_DIR/dashboard.out" \
    && jq -e 'length == 2' "$TMP_DIR/cards-snapshot.json" >/dev/null && echo 0 || echo 1)

AUTOPR_DASHBOARD_ONCE=1 AUTOPR_GH_BIN="$TMP_DIR/gh" AUTOPR_TEST_PR_CONTEXT_FAIL=true \
  AUTOPR_DASHBOARD_NOW_EPOCH="$dashboard_now" AUTOPR_DASHBOARD_CACHE_DIR="$TMP_DIR/dashboard-no-pr-cache" \
  AUTOPR_DISPATCH_LOG="$TMP_DIR/dispatch.log" AUTOPR_CARD_SNAPSHOT="$TMP_DIR/cards-snapshot.json" \
  "$VIEW_DIR/dashboard.sh" > "$TMP_DIR/dashboard-no-pr-context.out"
check "PR-context failure cannot produce a live release plan" \
  $(grep -q 'PLAN · unavailable · NOT-READY PRS ONLY' "$TMP_DIR/dashboard-no-pr-context.out" \
    && grep -q 'unavailable · existing queue remains visible below' "$TMP_DIR/dashboard-no-pr-context.out" \
    && ! grep -q '  RELEASE gh workflow run' "$TMP_DIR/dashboard-no-pr-context.out" \
    && echo 0 || echo 1)

cat > "$VIEW_DIR/select.sh" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$VIEW_DIR/select.sh"
AUTOPR_DASHBOARD_ONCE=1 AUTOPR_GH_BIN="$TMP_DIR/gh" \
  AUTOPR_DASHBOARD_NOW_EPOCH="$dashboard_now" AUTOPR_DASHBOARD_CACHE_DIR="$TMP_DIR/dashboard-cache" \
  AUTOPR_DISPATCH_LOG="$TMP_DIR/dispatch.log" AUTOPR_CARD_SNAPSHOT="$TMP_DIR/cards-snapshot.json" \
  "$VIEW_DIR/dashboard.sh" > "$TMP_DIR/dashboard-selector-error.out"
check "selector failure is explicit instead of looking like an empty queue" \
  $(grep -q 'Selector failed (exit 1); this does not mean the queue is empty.' "$TMP_DIR/dashboard-selector-error.out" \
    && echo 0 || echo 1)

cat > "$TMP_DIR/gh-unavailable" <<'EOF'
#!/usr/bin/env bash
exit 1
EOF
chmod +x "$TMP_DIR/gh-unavailable"
AUTOPR_DASHBOARD_ONCE=1 AUTOPR_GH_BIN="$TMP_DIR/gh-unavailable" \
  AUTOPR_DASHBOARD_NOW_EPOCH="$dashboard_now" AUTOPR_DASHBOARD_CACHE_DIR="$TMP_DIR/dashboard-cache" \
  AUTOPR_DISPATCH_LOG="$TMP_DIR/dispatch.log" AUTOPR_CARD_SNAPSHOT="$TMP_DIR/cards-snapshot.json" \
  "$VIEW_DIR/dashboard.sh" > "$TMP_DIR/dashboard-stale.out"
check "GitHub failure retains cached data and labels the overview stale" \
  $(grep -q 'STALE · showing last-known-good data' "$TMP_DIR/dashboard-stale.out" \
    && grep -q '#307' "$TMP_DIR/dashboard-stale.out" && echo 0 || echo 1)

cat > "$TMP_DIR/git-pr" <<'EOF'
#!/usr/bin/env bash
[ "$1" = -C ] && shift 2
case "$1 $2" in
  "rev-parse --is-inside-work-tree") printf 'true\n' ;;
  "branch --show-current") printf 'bot/task-80fa1e82\n' ;;
  "rev-parse --verify") exit 0 ;;
  "status --short") printf ' M client/src/ComplianceLocationModal.tsx\n' ;;
  "diff --shortstat") printf ' 4 files changed, 26 insertions(+), 2 deletions(-)\n' ;;
  "diff --name-status") printf 'M\tclient/src/ComplianceLocationModal.tsx\nM\tserver/app/compliance.py\n' ;;
  "diff --no-ext-diff") printf 'diff --git a/client/src/ComplianceLocationModal.tsx b/client/src/ComplianceLocationModal.tsx\n+require manager approval\n' ;;
esac
EOF
cat > "$TMP_DIR/gh-pr" <<'EOF'
#!/usr/bin/env bash
if [ "$1 $2" = "pr list" ]; then
  if [[ "$*" == *"--json number"* ]]; then printf '310\n';
  else printf '[{"headRefName":"bot/task-80fa1e82","updatedAt":"2099-08-27T01:00:00Z"}]\n'; fi
elif [ "$1 $2" = "pr view" ]; then
  printf '%s\n' '{"number":310,"title":"🟡 [C93] Prevent double-booking","isDraft":true,"state":"OPEN","url":"https://example.invalid/pr/310","labels":[{"name":"autopr"},{"name":"needs-work"}],"headRefName":"bot/task-80fa1e82","updatedAt":"2099-08-27T01:00:00Z","reviewDecision":null,"statusCheckRollup":[{"status":"COMPLETED","conclusion":"SUCCESS"}],"files":[{"path":"client/src/ComplianceLocationModal.tsx","additions":20,"deletions":2}],"additions":26,"deletions":2}'
fi
EOF
chmod +x "$TMP_DIR/git-pr" "$TMP_DIR/gh-pr"

AUTOPR_DASHBOARD_ONCE=1 AUTOPR_GH_BIN="$TMP_DIR/gh-pr" AUTOPR_GIT_BIN="$TMP_DIR/git-pr" \
  AUTOPR_GH_CACHE_DIR="$TMP_DIR/gh-cache" \
  AUTOPR_RUNNER_WORKTREE="$TMP_DIR/runner-worktree" "$AUTOPR_DIR/watch-pr.sh" > "$TMP_DIR/pr-pane.out"
check "PR pane shows real metadata, labels, worktree files, and live diff" \
  $(grep -q 'PR #310  DRAFT' "$TMP_DIR/pr-pane.out" \
    && grep -q 'needs-work' "$TMP_DIR/pr-pane.out" \
    && grep -q '4 files changed' "$TMP_DIR/pr-pane.out" \
    && grep -q 'CHANGED FILES · LIVE RUNNER WORKTREE' "$TMP_DIR/pr-pane.out" \
    && grep -q 'ComplianceLocationModal' "$TMP_DIR/pr-pane.out" && echo 0 || echo 1)

# A second redraw of the same pane must not spend a second GitHub request:
# the observer panes were re-listing PRs every cycle, every pane.
cat > "$TMP_DIR/gh-pr-counting" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$1 $2" >> "$AUTOPR_TEST_GH_CALLS"
exec "$AUTOPR_TEST_REAL_GH" "$@"
EOF
chmod +x "$TMP_DIR/gh-pr-counting"
: > "$TMP_DIR/pr-gh-calls.log"
for _ in 1 2 3; do
  AUTOPR_DASHBOARD_ONCE=1 AUTOPR_GH_BIN="$TMP_DIR/gh-pr-counting" AUTOPR_GIT_BIN="$TMP_DIR/git-pr" \
    AUTOPR_TEST_REAL_GH="$TMP_DIR/gh-pr" AUTOPR_TEST_GH_CALLS="$TMP_DIR/pr-gh-calls.log" \
    AUTOPR_GH_CACHE_DIR="$TMP_DIR/gh-cache-ttl" \
    AUTOPR_RUNNER_WORKTREE="$TMP_DIR/runner-worktree" "$AUTOPR_DIR/watch-pr.sh" >/dev/null
done
check "repeat observer redraws reuse cached PR metadata instead of re-asking GitHub" \
  $([ "$(grep -c 'pr view' "$TMP_DIR/pr-gh-calls.log")" = 1 ] \
    && [ "$(grep -c 'pr list' "$TMP_DIR/pr-gh-calls.log")" -le 2 ] && echo 0 || echo 1)

cat > "$TMP_DIR/gh-work" <<'EOF'
#!/usr/bin/env bash
if [ "$1 $2" = "run list" ]; then
  printf '%s\n' '[{"databaseId":900,"status":"in_progress","createdAt":"2099-08-27T01:00:00Z","workflowName":"Kanban autopr"}]'
elif [ "$1 $2" = "run view" ]; then
  printf '%s\n' '{"jobs":[{"name":"build","steps":[{"name":"Investigate","status":"in_progress"}]}]}'
fi
EOF
chmod +x "$TMP_DIR/gh-work"
cat > "$TMP_DIR/live-work.log" <<'EOF'
MATCHA KANBAN AUTOPR · CODEX LIVE STREAM
Codex: reading project files
Codex: editing the scheduling guard
Bearer this-token-must-not-render
sk-abcdefghijklmnopqrstuvwxyz123456
-----BEGIN TEST PRIVATE KEY-----
private-key-body-must-not-render
-----END TEST PRIVATE KEY-----
Codex: running focused tests
EOF

AUTOPR_DASHBOARD_ONCE=1 AUTOPR_GH_BIN="$TMP_DIR/gh-work" \
  AUTOPR_GITHUB_SNAPSHOT_CACHE_DIR="$TMP_DIR/work-github-cache" \
  AUTOPR_GH_CACHE_DIR="$TMP_DIR/gh-cache-work" \
  AUTOPR_LIVE_LOG="$TMP_DIR/live-work.log" "$AUTOPR_DIR/watch-work.sh" > "$TMP_DIR/work-pane.out"
check "live-work pane shows model activity and redacts common credentials" \
  $(grep -q 'LIVE CODEX WORK' "$TMP_DIR/work-pane.out" \
    && grep -q 'STEP build · Investigate' "$TMP_DIR/work-pane.out" \
    && grep -q 'editing the scheduling guard' "$TMP_DIR/work-pane.out" \
    && grep -q '\[REDACTED_OPENAI_KEY\]' "$TMP_DIR/work-pane.out" \
    && grep -q '\[REDACTED PRIVATE KEY\]' "$TMP_DIR/work-pane.out" \
    && ! grep -q 'private-key-body-must-not-render' "$TMP_DIR/work-pane.out" \
    && ! grep -q 'this-token-must-not-render' "$TMP_DIR/work-pane.out" \
    && echo 0 || echo 1)

AUTOPR_DASHBOARD_MAX_ITERATIONS=1 AUTOPR_GH_BIN="$TMP_DIR/gh-work" \
  AUTOPR_GITHUB_SNAPSHOT_CACHE_DIR="$TMP_DIR/work-github-cache" \
  AUTOPR_GH_CACHE_DIR="$TMP_DIR/gh-cache-work" \
  AUTOPR_LIVE_LOG="$TMP_DIR/live-work.log" "$AUTOPR_DIR/watch-work.sh" > "$TMP_DIR/work-history.out"
check "interactive live-work pane appends sanitized output without clearing history" \
  $(grep -q 'append-only history' "$TMP_DIR/work-history.out" \
    && grep -q 'Scroll with mouse/trackpad or Ctrl-b \[' "$TMP_DIR/work-history.out" \
    && grep -q 'Codex: reading project files' "$TMP_DIR/work-history.out" \
    && grep -q '\[REDACTED_OPENAI_KEY\]' "$TMP_DIR/work-history.out" \
    && ! grep -q 'private-key-body-must-not-render' "$TMP_DIR/work-history.out" \
    && ! grep -qF '|| clear' "$AUTOPR_DIR/watch-work.sh" \
    && echo 0 || echo 1)

cat > "$TMP_DIR/msandbox-health" <<'EOF'
#!/usr/bin/env bash
case "${AUTOPR_TEST_SANDBOX_STATE:-absent}" in
  error) printf 'docker unavailable\n' >&2; exit 1 ;;
  *) printf '%s\n' "${AUTOPR_TEST_SANDBOX_STATE:-absent}" ;;
esac
EOF
chmod +x "$TMP_DIR/msandbox-health"
AUTOPR_DASHBOARD_ONCE=1 AUTOPR_MSANDBOX_BIN="$TMP_DIR/msandbox-health" \
  AUTOPR_TEST_SANDBOX_STATE=created "$AUTOPR_DIR/watch-health.sh" > "$TMP_DIR/health-created.out"
AUTOPR_DASHBOARD_ONCE=1 AUTOPR_MSANDBOX_BIN="$TMP_DIR/msandbox-health" \
  AUTOPR_TEST_SANDBOX_STATE=running "$AUTOPR_DIR/watch-health.sh" > "$TMP_DIR/health-running.out"
check "health pane distinguishes a blocked container from a running worker" \
  $(grep -q 'blocked · container state created' "$TMP_DIR/health-created.out" \
    && grep -q 'running · matcha-kanban-autopr-sandbox' "$TMP_DIR/health-running.out" \
    && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
