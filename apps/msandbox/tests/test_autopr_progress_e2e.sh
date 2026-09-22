#!/usr/bin/env bash
# End-to-end rehearsal of the progress + runtime-ladder path, through the REAL
# producers rather than hand-written fixtures.
#
# The unit tests in test_kanban_autopr.sh assert each piece in isolation, and
# that is exactly how the pin shipped broken the first time: the ladder tests
# hand-wrote `autopr_model` into a card.json that the real collect.sh never
# produces, so a pin that could never reach the harness still passed. This
# walks the actual chain instead —
#
#   collect.sh  →  card.json  →  runtime-policy.sh
#                                checkpoint.sh save  →  stall.json + board writes
#                                runtime-policy.sh (continuation)
#                                run-journal.sh
#
# — with a stubbed board and a real (tiny) git workspace carrying the same
# ownership stamps run-codex-sandboxed.sh writes. No network, no containers,
# no model call.
set -uo pipefail
# Fixtures point at example.invalid; harness/lib.sh fail-closes on that under Actions.
unset GITHUB_ACTIONS

# This disposable end-to-end fixture intentionally targets example.invalid.
# GitHub Actions exports GITHUB_ACTIONS to every test, so remove that ambient
# marker before the real harness helpers apply their production-board guard.
# The guard itself remains covered explicitly in test_kanban_autopr.sh.
unset GITHUB_ACTIONS

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
AUTOPR_DIR="$REPO_ROOT/apps/msandbox/harness"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

PASS=0
FAIL=0
check() {
  local desc="$1" ok="$2"
  if [ "$ok" = 0 ]; then echo "PASS: $desc"; PASS=$((PASS + 1));
  else echo "FAIL: $desc"; FAIL=$((FAIL + 1)); fi
}

PROJECT_ID=11111111-1111-4111-8111-111111111111
TASK_ID=aaaaaaaa-0000-4000-8000-00000000000e
SUBTASK_DONE=cccccccc-0000-4000-8000-0000000000c1
SUBTASK_OPEN=cccccccc-0000-4000-8000-0000000000c2

mkdir -p "$TMP_DIR/bin" "$TMP_DIR/runner" "$TMP_DIR/uploads" "$TMP_DIR/checkpoints"

cat > "$TMP_DIR/env" <<ENV
MATCHA_API_URL=https://example.invalid/api
MATCHA_BOT_EMAIL=bot@example.com
MATCHA_BOT_PASSWORD=secret
MATCHA_PROJECT_IDS=$PROJECT_ID
MATCHA_ASSIGNEE_EMAIL=bot@example.com
ENV

# ── Stub board ─────────────────────────────────────────────────────────────
# One card, assigned to the bot, in changes_requested, PINNED to a runtime.
# The pin is the thing under test: it has to survive collect.sh's projection.
cat > "$TMP_DIR/bundle.json" <<JSON
{
  "project": {"id": "$PROJECT_ID", "title": "Espresso"},
  "elements": [],
  "tasks": [
    {
      "id": "$TASK_ID",
      "title": "Build the onboarding wizard",
      "description": "Wire the new-account flow.",
      "board_column": "changes_requested",
      "category": "feat",
      "priority": "high",
      "status": "pending",
      "assigned_email": "bot@example.com",
      "progress_note": "",
      "created_at": "2026-09-12T00:00:00Z",
      "last_moved_at": "2026-09-12T00:00:00Z",
      "subtask_total": 5,
      "subtask_done": 0,
      "pr_number": null,
      "pr_url": null,
      "autopr_model": "gpt-6-astra",
      "autopr_effort": "xhigh",
      "autopr_runtime_source": "manual",
      "autopr_paused": false,
      "attachments": []
    }
  ]
}
JSON

cat > "$TMP_DIR/bin/curl" <<'STUB'
#!/usr/bin/env bash
output_file="" payload="" url="" method=GET form="" write_status=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output_file="$2"; shift 2 ;;
    -d) payload="$2"; shift 2 ;;
    -X) method="$2"; shift 2 ;;
    -F) form="$2"; shift 2 ;;
    -w) write_status=1; shift 2 ;;
    http://*|https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done
if [[ "$url" == */auth/login ]]; then printf '{"access_token":"stub-token"}'; exit 0; fi
if [ -n "$form" ]; then
  src="${form#file=@}"; src="${src%%;*}"
  cp "$src" "$AUTOPR_TEST_UPLOADS/$(basename "$src")"
  printf 'UPLOAD %s\n' "$(basename "$src")" >> "$AUTOPR_TEST_CALLS"
  [ -z "$output_file" ] || printf '{"id":"f1"}' > "$output_file"
  [ "$write_status" = 0 ] || printf 200
  exit 0
fi
[ -z "$payload" ] || payload="$(printf '%s' "$payload" | jq -c . 2>/dev/null || printf '%s' "$payload")"
printf '%s %s %s\n' "$method" "${url#https://example.invalid/api}" "$payload" >> "$AUTOPR_TEST_CALLS"
body='{"ok":true}'
case "$url" in
  */bundle) body="$(cat "$AUTOPR_TEST_BUNDLE")" ;;
  */subtasks) body="$(cat "$AUTOPR_TEST_SUBTASKS")" ;;
  */history) body='[]' ;;
  */files) body='[]' ;;
  */tasks) body="$(jq -c '.tasks' "$AUTOPR_TEST_BUNDLE")" ;;
esac
[ -z "$output_file" ] || printf '%s' "$body" > "$output_file"
[ "$write_status" = 0 ] || printf 200
STUB
chmod +x "$TMP_DIR/bin/curl"

jq -n --arg a "$SUBTASK_DONE" --arg b "$SUBTASK_OPEN" \
  '[{id:$a,title:"Schema",is_done:false},{id:$b,title:"Tests",is_done:false}]' \
  > "$TMP_DIR/subtasks.json"

run_autopr() {
  PATH="$TMP_DIR/bin:$PATH" \
  MATCHA_AUTOPR_ENV="$TMP_DIR/env" \
  RUNNER_TEMP="$TMP_DIR/runner" \
  TMPDIR="$TMP_DIR" \
  AUTOPR_TEST_CALLS="$TMP_DIR/calls" \
  AUTOPR_TEST_BUNDLE="$TMP_DIR/bundle.json" \
  AUTOPR_TEST_SUBTASKS="$TMP_DIR/subtasks.json" \
  AUTOPR_TEST_UPLOADS="$TMP_DIR/uploads" \
  AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints" \
  AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox" \
  AUTOPR_INVESTIGATION_EXIT_FILE="$TMP_DIR/runner/investigation-exit-code" \
  AUTOPR_LIVE_LOG="$TMP_DIR/live.log" \
  GITHUB_RUN_ID=9001 \
  "$@"
}

# ── 1. The real producer carries the pin ───────────────────────────────────
: > "$TMP_DIR/calls"
cards="$(run_autopr "$AUTOPR_DIR/collect.sh" 2>"$TMP_DIR/collect.err")"
card="$(printf '%s' "$cards" | jq -c --arg id "$TASK_ID" 'map(select(.task_id == $id)) | .[0] // {}')"
check "collect.sh carries the card's runtime pin into card.json" \
  $(printf '%s' "$card" | jq -e '.autopr_model == "gpt-6-astra" and .autopr_effort == "xhigh"' \
    >/dev/null && echo 0 || echo 1)

# select.sh appends exactly these two and nothing else (its only mutation of
# the card), so the file the workflow hands downstream is this.
printf '%s' "$card" | jq -c '. + {mode:"rework", outcome:"pull_request"}' > "$TMP_DIR/card.json"

# ── 2. The pin survives into the resolved runtime ──────────────────────────
printf '[]' > "$TMP_DIR/history.json"
run_autopr env AUTOPR_RUNTIME_HISTORY_FILE="$TMP_DIR/history.json" \
  "$AUTOPR_DIR/runtime-policy.sh" "$TMP_DIR/card.json" "$TMP_DIR/policy-pinned.json" \
  >/dev/null 2>&1
check "a pinned card resolves to its pinned runtime, marked manual" \
  $(jq -e '.model == "gpt-6-astra" and .effort == "xhigh" and .runtime_source == "manual"' \
    "$TMP_DIR/policy-pinned.json" >/dev/null && echo 0 || echo 1)
# The model's budget and the step's are two numbers: the supervisor stops the
# model at `minutes`, the Investigate step allows `step_minutes` so validation
# after the model is never cut short.
check "runtime policy emits the step budget as minutes plus the grace window" \
  $(jq -e '.minutes == 20 and .step_minutes == 23' "$TMP_DIR/policy-pinned.json" >/dev/null && echo 0 || echo 1)

# ── 3. A stalled run: real workspace, real stamps, real progress log ───────
# Same shape run-codex-sandboxed.sh leaves behind: a git clone whose
# .git/autopr-io carries the task id and the base sha it was cloned at.
WS="$TMP_DIR/sandbox/workspace"
mkdir -p "$WS/.git" && git init -q "$WS" 2>/dev/null
git -C "$WS" config user.email bot@example.com
git -C "$WS" config user.name bot
echo base > "$WS/file.txt"
git -C "$WS" add -A && git -C "$WS" commit -qm base
BASE_SHA="$(git -C "$WS" rev-parse HEAD)"
mkdir -p "$WS/.git/autopr-io/output"
printf '%s' "$TASK_ID" > "$WS/.git/autopr-io/task-id"
printf '%s' "$BASE_SHA" > "$WS/.git/autopr-io/model-base-sha"
# Uncommitted work, so the checkpoint has a patch to save.
echo "half-written" >> "$WS/file.txt"

# The model's running account. One finished subtask, one not.
cat > "$WS/.git/autopr-io/output/progress.jsonl" <<LOG
{"at":"2026-09-12T19:10:00Z","phase":"explore","note":"Read the signup routes","next":"Write the migration","subtask_id":null,"subtask_done":false}
{"at":"2026-09-12T19:20:00Z","phase":"implement","note":"Added the wizard step","next":"Wire the API","subtask_id":"$SUBTASK_DONE","subtask_done":true}
{"at":"2026-09-12T19:30:00Z","phase":"implement","note":"Wiring the API","next":"Run the tests","subtask_id":"$SUBTASK_OPEN","subtask_done":false}
LOG
# A truncated trailing line — the normal case when a run is killed mid-write.
printf '{"at":"2026-09-12T19:31:00Z","phase":"impl' >> "$WS/.git/autopr-io/output/progress.jsonl"

# 143 = SIGTERM: the only trustworthy evidence the step hit its time budget.
printf '143' > "$TMP_DIR/runner/investigation-exit-code"

: > "$TMP_DIR/calls"
run_autopr "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/card.json" \
  /dev/null /dev/null "$(( $(date +%s) - 20 * 60 ))" 20 >/dev/null 2>"$TMP_DIR/save.err"

check "a killed run checks off exactly the subtask its progress log reported done" \
  $(grep -q "PATCH /matcha-work/projects/$PROJECT_ID/tasks/$TASK_ID/subtasks/$SUBTASK_DONE {\"is_done\":true}" "$TMP_DIR/calls" \
    && ! grep -q "subtasks/$SUBTASK_OPEN" "$TMP_DIR/calls" && echo 0 || echo 1)

check "a truncated trailing line costs one step, not the whole progress log" \
  $(jq -e '.progress_step_count == 3 and .progress_phase == "implement"' \
    "$TMP_DIR/checkpoints/$TASK_ID"/*/metadata.json >/dev/null \
    && [ "$(jq -s 'length' "$TMP_DIR/checkpoints/$TASK_ID"/*/progress.jsonl)" = 3 ] \
    && echo 0 || echo 1)

# The model writes this file, so a non-string field is a thing that happens.
# Coercion belongs at capture: uncoerced, the journal's slice raises
# "Cannot index number with object" and takes the whole section down.
check "a non-string note is coerced at capture instead of poisoning the log" \
  $(printf '\n{"at":"2026-09-12T19:40:00Z","phase":"test","note":5,"next":{"a":1}}\n' \
      >> "$WS/.git/autopr-io/output/progress.jsonl"; \
    PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
      TMPDIR="$TMP_DIR" AUTOPR_TEST_CALLS="$TMP_DIR/calls-coerce" \
      AUTOPR_TEST_BUNDLE="$TMP_DIR/bundle.json" AUTOPR_TEST_SUBTASKS="$TMP_DIR/subtasks.json" \
      AUTOPR_TEST_UPLOADS="$TMP_DIR/uploads" AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints-coerce" \
      AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox" \
      AUTOPR_INVESTIGATION_EXIT_FILE="$TMP_DIR/runner/investigation-exit-code" \
      AUTOPR_LIVE_LOG="$TMP_DIR/live.log" GITHUB_RUN_ID=9003 \
      "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/card.json" /dev/null /dev/null \
      "$(( $(date +%s) - 20 * 60 ))" 20 >/dev/null 2>/dev/null; \
    jq -se 'all(.[]; (.note | type) == "string" and (.next | type) == "string")
            and length == 4' \
      "$TMP_DIR/checkpoints-coerce/$TASK_ID"/*/progress.jsonl >/dev/null \
    && echo 0 || echo 1)

# The trailing fragment above is the easy half: jq streams the objects before
# it regardless. The real hazard is an OVERSIZED log, because capture_progress
# keeps the tail — which always starts mid-line. A whole-stream parse dies on
# that first fragment and drops every step behind it, so the run reports no
# progress at all in exactly the case where it logged the most.
BIG_WS="$TMP_DIR/sandbox-big/workspace"
mkdir -p "$BIG_WS/.git/autopr-io/output"
git init -q "$BIG_WS" 2>/dev/null
git -C "$BIG_WS" config user.email bot@example.com
git -C "$BIG_WS" config user.name bot
echo base > "$BIG_WS/file.txt"
git -C "$BIG_WS" add -A && git -C "$BIG_WS" commit -qm base
printf '%s' "$TASK_ID" > "$BIG_WS/.git/autopr-io/task-id"
printf '%s' "$(git -C "$BIG_WS" rev-parse HEAD)" > "$BIG_WS/.git/autopr-io/model-base-sha"
for i in $(seq 1 40); do
  printf '{"at":"2026-09-12T19:%02d:00Z","phase":"implement","note":"step %s padded %s","next":"keep going","subtask_id":null,"subtask_done":false}\n' \
    "$((i % 60))" "$i" "$(printf 'x%.0s' $(seq 1 60))"
done > "$BIG_WS/.git/autopr-io/output/progress.jsonl"
full_bytes="$(wc -c < "$BIG_WS/.git/autopr-io/output/progress.jsonl" | tr -d '[:space:]')"
# A cap that is NOT a line boundary, so the kept tail necessarily starts inside
# a line — the shape `tail -c` produces on every oversized log.
cap=$(( full_bytes / 3 + 37 ))
# Its own call log: the pause-note assertion below reads the FIRST save's
# board writes, and sharing one file here silently emptied them.
PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
  TMPDIR="$TMP_DIR" AUTOPR_TEST_CALLS="$TMP_DIR/calls-big" AUTOPR_TEST_BUNDLE="$TMP_DIR/bundle.json" \
  AUTOPR_TEST_SUBTASKS="$TMP_DIR/subtasks.json" AUTOPR_TEST_UPLOADS="$TMP_DIR/uploads" \
  AUTOPR_CHECKPOINT_ROOT="$TMP_DIR/checkpoints-big" \
  AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox-big" \
  AUTOPR_INVESTIGATION_EXIT_FILE="$TMP_DIR/runner/investigation-exit-code" \
  AUTOPR_LIVE_LOG="$TMP_DIR/live.log" GITHUB_RUN_ID=9002 \
  AUTOPR_CHECKPOINT_MAX_PROGRESS_BYTES="$cap" \
  "$AUTOPR_DIR/checkpoint.sh" save "$TMP_DIR/card.json" \
  /dev/null /dev/null "$(( $(date +%s) - 20 * 60 ))" 20 >/dev/null 2>&1
big_meta="$(find "$TMP_DIR/checkpoints-big/$TASK_ID" -name metadata.json | head -1)"
check "an oversized log truncated mid-line keeps its remaining steps" \
  $([ -n "$big_meta" ] \
    && jq -e '.progress_saved == true and .progress_step_count > 1
              and .progress_phase == "implement"' "$big_meta" >/dev/null \
    && echo 0 || echo 1)

check "the stall is classified and recorded at the task root, not only in the checkpoint dir" \
  $(jq -e '.stall_reason == "implementing" and .stall_attempt == 1
           and .suggested_model == "gpt-5.6-sol" and .suggested_effort == "high"' \
    "$TMP_DIR/checkpoints/$TASK_ID/stall.json" >/dev/null && echo 0 || echo 1)

note="$(grep -o 'PATCH /matcha-work/projects/[^ ]* .*progress_note.*' "$TMP_DIR/calls" | head -1)"
check "the pause note says the pin outranks the escalation rather than promising a switch" \
  $(printf '%s' "$note" | grep -q 'pinned on the card to gpt-6-astra' \
    && printf '%s' "$note" | grep -q 'pause #1 for this card' \
    && printf '%s' "$note" | grep -q 'Checked off 1 checklist item' && echo 0 || echo 1)

# ── 4. An UNPINNED card inherits the escalation on its continuation ────────
jq 'del(.autopr_model, .autopr_effort) + {autopr_runtime_source: null}' \
  "$TMP_DIR/card.json" > "$TMP_DIR/card-unpinned.json"
run_autopr env AUTOPR_RUNTIME_HISTORY_FILE="$TMP_DIR/history.json" \
  "$AUTOPR_DIR/runtime-policy.sh" "$TMP_DIR/card-unpinned.json" "$TMP_DIR/policy-auto.json" \
  >/dev/null 2>&1
check "an unpinned continuation inherits the runtime the stall suggested" \
  $(jq -e '.model == "gpt-5.6-sol" and .effort == "high"
           and .runtime_source == "auto" and .stall_reason == "implementing"' \
    "$TMP_DIR/policy-auto.json" >/dev/null && echo 0 || echo 1)

# ── 5. A shipped round resets the per-card stall state ─────────────────────
ledger_before="$(cat "$TMP_DIR/checkpoints/$TASK_ID/ticked-subtasks" 2>/dev/null || true)"
run_autopr "$AUTOPR_DIR/checkpoint.sh" consume "$TMP_DIR/card.json" >/dev/null 2>&1
check "consuming a published round clears the round's stall state" \
  $([ ! -f "$TMP_DIR/checkpoints/$TASK_ID/stalls" ] \
    && [ ! -f "$TMP_DIR/checkpoints/$TASK_ID/stall.json" ] && echo 0 || echo 1)
# Deleting the ledger here achieved nothing: consume runs before run-journal.sh
# in the same Cleanup step, so final_tick rebuilt it seconds later and every
# published round re-PATCHed each of its subtasks. Run-keyed entries make the
# delete unnecessary — a later round ticks its own items regardless.
run_autopr "$AUTOPR_DIR/checkpoint.sh" tick "$TMP_DIR/card.json" >/dev/null 2>&1
check "a post-consume tick re-PATCHes nothing and leaves the ledger run-keyed" \
  $([ "$(cat "$TMP_DIR/checkpoints/$TASK_ID/ticked-subtasks" 2>/dev/null || true)" = "$ledger_before" ] \
    && grep -q "^9001 $SUBTASK_DONE$" "$TMP_DIR/checkpoints/$TASK_ID/ticked-subtasks" \
    && echo 0 || echo 1)

# ── 6. The journal tells the operator the story ────────────────────────────
checkpoint_dir="$(find "$TMP_DIR/checkpoints/$TASK_ID" -maxdepth 1 -type d -name '9001-*' | head -1)"
: > "$TMP_DIR/calls"
run_autopr "$AUTOPR_DIR/run-journal.sh" "$TMP_DIR/card.json" --outcome failure \
  --reason investigate --checkpoint "$checkpoint_dir" >/dev/null 2>&1
journal="$(ls "$TMP_DIR/uploads" | grep '^autopr-run-9001-' | head -1)"
body="$(cat "$TMP_DIR/uploads/$journal" 2>/dev/null || true)"
check "the journal renders the progress log rather than 'no report was produced'" \
  $(grep -q '## Progress log' <<< "$body" \
    && grep -q 'Last phase: \*\*implement\*\*' <<< "$body" \
    && grep -q 'Added the wizard step' <<< "$body" \
    && grep -q 'next: Wire the API' <<< "$body" \
    && grep -q 'Checked off 1 checklist item' <<< "$body" && echo 0 || echo 1)

check "the journal reports the checkpoint time in Pacific, converted from UTC" \
  $(grep -qE 'saved 20[0-9]{2}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} P[DS]T' <<< "$body" \
    && ! grep -qE 'saved 20[0-9]{2}-[0-9]{2}-[0-9]{2}T' <<< "$body" && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" = 0 ]
