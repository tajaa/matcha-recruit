#!/usr/bin/env bash
# card-control.sh against stubbed curl/gh: resolution rules, the hold reason,
# unstick ordering, and the cancel-run sequence. No board, GitHub, or runner.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CONTROL="$REPO_ROOT/scripts/kanban-autopr/card-control.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/worktree"
PASS=0
FAIL=0
check() {
  local desc="$1" ok="$2"
  if [ "$ok" = 0 ]; then echo "PASS: $desc"; PASS=$((PASS + 1));
  else echo "FAIL: $desc"; FAIL=$((FAIL + 1)); fi
}

cat > "$TMP_DIR/env" <<'EOF'
MATCHA_API_URL=https://example.invalid/api
MATCHA_BOT_EMAIL=bot@example.com
MATCHA_BOT_PASSWORD=secret
MATCHA_PROJECT_IDS=11111111-1111-4111-8111-111111111111,22222222-2222-4222-8222-222222222222
MATCHA_ASSIGNEE_EMAIL=haley@example.com
EOF

# Two boards. "landing" is ambiguous across them; an id8 is exact even though
# another card's title contains those characters.
cat > "$TMP_DIR/bundle-1.json" <<'EOF'
{"tasks":[
 {"id":"aaaa0000-0000-4000-8000-000000000001","title":"Update landing page copy","board_column":"changes_requested","pr_number":317,"autopr_paused":false,"status":"open"},
 {"id":"bbbb0000-0000-4000-8000-000000000002","title":"Add per-location pricing","board_column":"in_progress","pr_number":null,"autopr_paused":false,"status":"open"},
 {"id":"cccc0000-0000-4000-8000-000000000003","title":"Old landing cleanup","board_column":"done","pr_number":null,"autopr_paused":false,"status":"cancelled"}
]}
EOF
cat > "$TMP_DIR/bundle-2.json" <<'EOF'
{"tasks":[
 {"id":"dddd0000-0000-4000-8000-000000000004","title":"Landing hero aaaa0000","board_column":"todo","pr_number":null,"autopr_paused":true,"autopr_hold_reason":"docs allowlist","status":"open"},
 {"id":"eeee0000-0000-4000-8000-000000000005","title":"Pricing rollout","board_column":"in_progress","pr_number":320,"autopr_paused":false,"status":"open"}
]}
EOF

cat > "$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
output_file="" payload="" url="" method=GET
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output_file="$2"; shift 2 ;;
    -d) payload="$2"; shift 2 ;;
    -X) method="$2"; shift 2 ;;
    http://*|https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done
if [[ "$url" == */auth/login ]]; then printf '{"access_token":"test-token"}'; exit 0; fi
# lib.sh helpers emit pretty-printed JSON; one compact line per call keeps the
# assertions below readable.
[ -z "$payload" ] || payload="$(printf '%s' "$payload" | jq -c . 2>/dev/null || printf '%s' "$payload")"
printf '%s %s %s\n' "$method" "${url#https://example.invalid/api}" "$payload" >> "$AUTOPR_TEST_CALLS"
body='{"ok":true}'
case "$url" in
  */projects/11111111-1111-4111-8111-111111111111/bundle) body="$(cat "$AUTOPR_TEST_BUNDLE_DIR/bundle-1.json")" ;;
  */projects/22222222-2222-4222-8222-222222222222/bundle) body="$(cat "$AUTOPR_TEST_BUNDLE_DIR/bundle-2.json")" ;;
  */tasks/bbbb0000-0000-4000-8000-000000000002/files) body="$(cat "$AUTOPR_TEST_BUNDLE_DIR/files-bbbb.json")" ;;
  https://example.invalid/cdn/*) cat "$AUTOPR_TEST_BUNDLE_DIR/journal-body.md"; exit 0 ;;
esac
[ -z "$output_file" ] || printf '%s' "$body" > "$output_file"
printf 200
EOF
cat > "$TMP_DIR/files-bbbb.json" <<'EOF'
[{"id":"f2","filename":"autopr-run-901-20260912T040500Z.md","created_at":"2026-09-12T04:05:00+00:00","url":"https://example.invalid/cdn/f2.md"},
 {"id":"f0","filename":"Screenshot.png","created_at":"2026-09-11T09:08:27+00:00","url":"https://example.invalid/cdn/f0.png"},
 {"id":"f1","filename":"autopr-run-800-20260912T032000Z.md","created_at":"2026-09-12T03:20:00+00:00","url":"https://example.invalid/cdn/f1.md"}]
EOF
printf '# AutoPR run #901 · FAILURE\n\n## Why it stopped\n\npublishing the result failed.\n' > "$TMP_DIR/journal-body.md"
mkdir -p "$TMP_DIR/cache/attempts" "$TMP_DIR/worktree/.git/matcha-kanban-autopr-checkpoints/bbbb0000-0000-4000-8000-000000000002/901-1-inflight"
printf '2\tpublish\t2026-09-12T04:05:00Z' > "$TMP_DIR/cache/attempts/bbbb0000"
printf '901-1-inflight\n' > "$TMP_DIR/worktree/.git/matcha-kanban-autopr-checkpoints/bbbb0000-0000-4000-8000-000000000002/active"
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_GH_LOG"
exit 0
EOF
cat > "$TMP_DIR/run-snapshot" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "${AUTOPR_TEST_RUNS:-[]}"
EOF
cat > "$TMP_DIR/queue-handoff-marker" <<'EOF'
EOF
chmod +x "$TMP_DIR/bin/curl" "$TMP_DIR/bin/gh" "$TMP_DIR/run-snapshot"
git -C "$TMP_DIR/worktree" init -q && git -C "$TMP_DIR/worktree" checkout -q -b bot/task-bbbb0000

run_control() {
  : > "$TMP_DIR/calls"
  PATH="$TMP_DIR/bin:$PATH" TMPDIR="$TMP_DIR" MATCHA_AUTOPR_ENV="$TMP_DIR/env" \
    AUTOPR_TEST_CALLS="$TMP_DIR/calls" AUTOPR_TEST_BUNDLE_DIR="$TMP_DIR" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_GH_BIN="$TMP_DIR/bin/gh" \
    AUTOPR_RUN_SNAPSHOT="$TMP_DIR/run-snapshot" AUTOPR_RUNNER_WORKTREE="$TMP_DIR/worktree" \
    AUTOPR_CACHE_DIR="$TMP_DIR/cache" \
    "$CONTROL" "$@"
}

set +e
resolved="$(run_control resolve aaaa0000 2>"$TMP_DIR/err")"; rc=$?
set -e
check "resolve prefers an exact id8 over a title that contains it" \
  $([ "$rc" = 0 ] && [ "$resolved" = "$(printf '11111111-1111-4111-8111-111111111111\taaaa0000-0000-4000-8000-000000000001\tchanges_requested\t317\tfalse\tUpdate landing page copy')" ] && echo 0 || echo 1)

set +e
run_control resolve landing >/dev/null 2>"$TMP_DIR/err"; rc=$?
set -e
check "an ambiguous title exits 2 and lists the candidates without a cancelled card" \
  $([ "$rc" = 2 ] && grep -q 'matches 2 cards' "$TMP_DIR/err" \
    && grep -q 'aaaa0000' "$TMP_DIR/err" && grep -q 'dddd0000' "$TMP_DIR/err" \
    && ! grep -q 'cccc0000' "$TMP_DIR/err" && echo 0 || echo 1)

set +e
run_control resolve nothing-like-this >/dev/null 2>"$TMP_DIR/err"; rc=$?
set -e
check "an unknown target exits 2" $([ "$rc" = 2 ] && grep -q 'no card matches' "$TMP_DIR/err" && echo 0 || echo 1)

json="$(run_control resolve "hero" --json)"
check "resolve --json carries the hold reason" \
  $(printf '%s' "$json" | jq -e '.autopr_paused == true and .autopr_hold_reason == "docs allowlist" and .id8 == "dddd0000"' >/dev/null && echo 0 || echo 1)

out="$(run_control hold aaaa0000 --reason "docs allowlist")"
check "hold posts unqueue with the reason and reports it" \
  $(grep -q '^POST /matcha-work/projects/11111111-1111-4111-8111-111111111111/tasks/aaaa0000-0000-4000-8000-000000000001/autopr/unqueue {"reason":"docs allowlist"}$' "$TMP_DIR/calls" \
    && [ "$out" = "held aaaa0000 · Update landing page copy · docs allowlist" ] && echo 0 || echo 1)

out="$(run_control release dddd0000)"
check "release posts run-defer (no queueing)" \
  $(grep -q '/tasks/dddd0000-0000-4000-8000-000000000004/autopr/run-defer {}$' "$TMP_DIR/calls" \
    && ! grep -q 'run-now' "$TMP_DIR/calls" && [ "$out" = "released dddd0000 · Landing hero aaaa0000" ] && echo 0 || echo 1)

out="$(run_control unstick bbbb0000 --hold --reason "wait for docs fix")"
check "unstick moves a PR-less card to todo and only then holds it" \
  $([ "$(grep -n 'PATCH .*bbbb0000.* {"board_column":"todo"}' "$TMP_DIR/calls" | cut -d: -f1)" = 3 ] \
    && [ "$(grep -n 'unqueue {"reason":"wait for docs fix"}' "$TMP_DIR/calls" | cut -d: -f1)" = 4 ] \
    && grep -q '^moved bbbb0000 · Add per-location pricing → todo$' <<< "$out" \
    && grep -q '^held bbbb0000' <<< "$out" && echo 0 || echo 1)

out="$(run_control unstick eeee0000)"
check "unstick sends an In Progress card with a PR to changes_requested" \
  $(grep -q 'PATCH .*eeee0000.* {"board_column":"changes_requested"}' "$TMP_DIR/calls" \
    && ! grep -q unqueue "$TMP_DIR/calls" && echo 0 || echo 1)

set +e
run_control unstick aaaa0000 >/dev/null 2>"$TMP_DIR/err"; rc=$?
set -e
check "unstick refuses a card that is not In Progress and moves nothing" \
  $([ "$rc" = 2 ] && grep -q 'not In Progress' "$TMP_DIR/err" \
    && ! grep -q PATCH "$TMP_DIR/calls" && echo 0 || echo 1)

set +e
AUTOPR_TEST_RUNS='[]' run_control cancel-run >/dev/null 2>"$TMP_DIR/err"; rc=$?
set -e
check "cancel-run with no active Kanban run exits 3 and touches nothing" \
  $([ "$rc" = 3 ] && [ ! -s "$TMP_DIR/calls" ] && [ ! -e "$TMP_DIR/gh.log" ] && echo 0 || echo 1)

runs='[{"databaseId":900,"lane":"errors","status":"in_progress"},{"databaseId":901,"lane":"kanban","status":"in_progress"},{"databaseId":800,"lane":"kanban","status":"completed"}]'
set +e
AUTOPR_TEST_RUNS="$runs" run_control cancel-run landing >/dev/null 2>"$TMP_DIR/err"; rc=$?
set -e
check "cancel-run resolves the card before cancelling, so an ambiguous target cancels nothing" \
  $([ "$rc" = 2 ] && [ ! -e "$TMP_DIR/gh.log" ] && ! grep -q PATCH "$TMP_DIR/calls" && echo 0 || echo 1)

out="$(AUTOPR_TEST_RUNS="$runs" run_control cancel-run --hold)"
check "cancel-run cancels the Kanban run, waits, then unsticks and holds the runner's card" \
  $(grep -q '^run cancel 901 --repo tajaa/matcha-recruit$' "$TMP_DIR/gh.log" \
    && grep -q '^run watch 901 --repo' "$TMP_DIR/gh.log" \
    && ! grep -q '900' "$TMP_DIR/gh.log" \
    && grep -q 'PATCH .*bbbb0000.* {"board_column":"todo"}' "$TMP_DIR/calls" \
    && grep -q 'bbbb0000.*unqueue {"reason":"held by operator"}' "$TMP_DIR/calls" \
    && grep -q '^cancelled run #901$' <<< "$out" && echo 0 || echo 1)

check "installer ships card-control.sh and its hand-off helper next to the dispatcher" \
  $(grep -q 'card-control.sh' "$REPO_ROOT/scripts/kanban-autopr/install-launch-agent.sh" \
    && grep -q 'queue-handoff.sh' "$REPO_ROOT/scripts/kanban-autopr/install-launch-agent.sh" && echo 0 || echo 1)

out="$(run_control log bbbb0000)"
check "log lists the card's run journals newest first, prints the newest, the ledger, and checkpoints" \
  $(grep -q '^Run journals: 2$' <<< "$out" \
    && [ "$(grep -n 'autopr-run-901-' <<< "$out" | head -1 | cut -d: -f1)" -lt "$(grep -n 'autopr-run-800-' <<< "$out" | head -1 | cut -d: -f1)" ] \
    && ! grep -q 'Screenshot.png' <<< "$out" \
    && grep -q '^publishing the result failed\.$' <<< "$out" \
    && grep -q '^Failure ledger: 2 consecutive × publish (last 2026-09-12T04:05:00Z)$' <<< "$out" \
    && grep -qE '^Checkpoints on the runner: 901-1-inflight +\(resumes from 901-1-inflight\)$' <<< "$out" \
    && ! grep -q 'POST\|PATCH' "$TMP_DIR/calls" && echo 0 || echo 1)

# An unmatched */ glob makes ls exit non-zero; under set -euo pipefail that
# killed log mid-line and returned the ambiguous-target code.
rm -rf "$TMP_DIR/worktree/.git/matcha-kanban-autopr-checkpoints/bbbb0000-0000-4000-8000-000000000002"
mkdir -p "$TMP_DIR/worktree/.git/matcha-kanban-autopr-checkpoints/bbbb0000-0000-4000-8000-000000000002"
set +e
out="$(run_control log bbbb0000)"; rc=$?
set -e
check "log survives a checkpoint directory with no runs in it" \
  $([ "$rc" = 0 ] && grep -q '^Checkpoints on the runner: none$' <<< "$out" \
    && grep -q '^Failure ledger: 2 consecutive × publish' <<< "$out" && echo 0 || echo 1)

usage_out="$(run_control 2>&1 || true)"
check "usage prints the whole header including the exit codes, and no shell source" \
  $(grep -q 'card-control.sh log' <<< "$usage_out" \
    && grep -q '1 for a failed board call (via die)\.' <<< "$usage_out" \
    && ! grep -q 'set -euo pipefail' <<< "$usage_out" && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
