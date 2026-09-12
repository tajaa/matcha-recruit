#!/usr/bin/env bash
# run-journal.sh attaches one journal per run and writes a STOPPED header only
# when nothing else already explained the stop. No network, no board.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOPR_DIR="$REPO_ROOT/scripts/kanban-autopr"
JOURNAL="$AUTOPR_DIR/run-journal.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/uploads" "$TMP_DIR/runner" "$TMP_DIR/checkpoint"
PASS=0
FAIL=0
check() {
  local desc="$1" ok="$2"
  if [ "$ok" = 0 ]; then echo "PASS: $desc"; PASS=$((PASS + 1));
  else echo "FAIL: $desc"; FAIL=$((FAIL + 1)); fi
}

cat > "$TMP_DIR/env" <<'ENV'
MATCHA_API_URL=https://example.invalid/api
MATCHA_BOT_EMAIL=bot@example.com
MATCHA_BOT_PASSWORD=secret
MATCHA_PROJECT_IDS=11111111-1111-4111-8111-111111111111
MATCHA_ASSIGNEE_EMAIL=haley@example.com
ENV
cat > "$TMP_DIR/bin/curl" <<'STUB'
#!/usr/bin/env bash
output_file="" payload="" url="" method=GET form=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output_file="$2"; shift 2 ;;
    -d) payload="$2"; shift 2 ;;
    -X) method="$2"; shift 2 ;;
    -F) form="$2"; shift 2 ;;
    http://*|https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done
if [[ "$url" == */auth/login ]]; then printf '{"access_token":"test-token"}'; exit 0; fi
if [ -n "$form" ]; then
  src="${form#file=@}"; src="${src%%;*}"
  cp "$src" "$AUTOPR_TEST_UPLOADS/$(basename "$src")"
  printf 'UPLOAD %s %s\n' "${url#https://example.invalid/api}" "$(basename "$src")" >> "$AUTOPR_TEST_CALLS"
  [ "${AUTOPR_TEST_UPLOAD_FAIL:-0}" = 0 ] || { printf '{"detail":"boom"}' > "$output_file"; printf 500; exit 0; }
  printf '{"id":"f1"}' > "$output_file"; printf 200; exit 0
fi
[ -z "$payload" ] || payload="$(printf '%s' "$payload" | jq -c . 2>/dev/null || printf '%s' "$payload")"
printf '%s %s %s\n' "$method" "${url#https://example.invalid/api}" "$payload" >> "$AUTOPR_TEST_CALLS"
[ -z "$output_file" ] || printf '{"ok":true}' > "$output_file"
printf 200
STUB
chmod +x "$TMP_DIR/bin/curl"

cat > "$TMP_DIR/card.json" <<'CARD'
{"project_id":"11111111-1111-4111-8111-111111111111","task_id":"bbbb0000-0000-4000-8000-000000000002","id8":"bbbb0000","title":"Add per-location pricing","project_title":"MATCHA","mode":"todo","progress_note":"🤖 AUTO SETUP · READY FOR REVIEW · build 14 · note: old"}
CARD
cat > "$TMP_DIR/report.md" <<'REPORT'
# Report
### Summary
Added a per-location price column and wired the admin editor.
Two files still need tests.
### Details
irrelevant
REPORT
printf '%s\n' '{"outcome":"implementation","summary":"Pricing column added; tests pending.","acceptance_criteria_met":false,"questions":[{"question":"Should overrides cascade to child locations?"}]}' > "$TMP_DIR/decision.json"
printf '%s\n' '{"schema_version":1,"task_id":"bbbb0000-0000-4000-8000-000000000002","id8":"bbbb0000","run_id":"77","created_at":"2026-09-12T04:00:00Z","patch_saved":true,"patch_bytes":36321,"changed_file_count":2,"changed_files":["client/src/pages/admin/Products.tsx","client/src/utils/tier.ts"],"report_saved":true,"decision_saved":true,"transcript_saved":true}' > "$TMP_DIR/checkpoint/metadata.json"

run_journal() {
  : > "$TMP_DIR/calls"
  PATH="$TMP_DIR/bin:$PATH" TMPDIR="$TMP_DIR" RUNNER_TEMP="$TMP_DIR/runner" MATCHA_AUTOPR_ENV="$TMP_DIR/env" \
    AUTOPR_TEST_CALLS="$TMP_DIR/calls" AUTOPR_TEST_UPLOADS="$TMP_DIR/uploads" \
    GITHUB_RUN_ID=77 GITHUB_SERVER_URL=https://github.com GITHUB_REPOSITORY=tajaa/matcha-recruit \
    "$JOURNAL" "$@"
}

out="$(run_journal "$TMP_DIR/card.json" --outcome failure --reason investigate \
  --report "$TMP_DIR/report.md" --decision "$TMP_DIR/decision.json" --checkpoint "$TMP_DIR/checkpoint")"
journal="$(ls "$TMP_DIR/uploads" | grep '^autopr-run-77-' | head -1)"
body="$(cat "$TMP_DIR/uploads/$journal")"
check "a failed run attaches one journal named after the run" \
  $([ -n "$journal" ] && grep -q "^UPLOAD /matcha-work/projects/11111111-1111-4111-8111-111111111111/tasks/bbbb0000-0000-4000-8000-000000000002/files $journal$" "$TMP_DIR/calls" \
    && [ "$out" = "journal attached: $journal" ] && echo 0 || echo 1)
check "the journal says what was done, what is left, why it stopped, and how it resumes" \
  $(grep -q '^# AutoPR run #77 · FAILURE' <<< "$body" \
    && grep -q 'Run log: https://github.com/tajaa/matcha-recruit/actions/runs/77' <<< "$body" \
    && grep -q 'Added a per-location price column and wired the admin editor. Two files still need tests.' <<< "$body" \
    && grep -q 'Files changed (2, from the saved checkpoint):' <<< "$body" \
    && grep -q -- '- `client/src/utils/tier.ts`' <<< "$body" \
    && grep -q 'Acceptance criteria met: false' <<< "$body" \
    && grep -q -- '- Should overrides cascade to child locations?' <<< "$body" \
    && grep -q 'the model pass failed or timed out before producing a valid report\.' <<< "$body" \
    && grep -q 'A checkpoint with 2 changed file(s) (36321-byte patch, saved 2026-09-12T04:00:00Z)' <<< "$body" \
    && grep -q 'msandbox autopr run-now bbbb0000' <<< "$body" && echo 0 || echo 1)
check "a failure nothing else explained gets a STOPPED header that points at the journal" \
  $(grep -q "^PATCH /matcha-work/projects/11111111-1111-4111-8111-111111111111/tasks/bbbb0000-0000-4000-8000-000000000002 {\"progress_note\":\"🤖 AUTO SETUP · STOPPED: MODEL PASS FAILED · run #77 · note: see $journal\"}$" "$TMP_DIR/calls" \
    && ! grep -q 'READY FOR REVIEW' "$TMP_DIR/calls" && echo 0 || echo 1)

rm -f "$TMP_DIR/uploads"/*
run_journal "$TMP_DIR/card.json" --outcome success --pr 500 --report "$TMP_DIR/report.md" >/dev/null
body="$(cat "$TMP_DIR/uploads"/autopr-run-77-*.md)"
check "a success attaches a journal naming the PR and leaves the card note alone" \
  $(grep -q 'Draft PR #500 was published\.' <<< "$body" && grep -q '^# AutoPR run #77 · SUCCESS' <<< "$body" \
    && grep -q 'Files changed: none recorded\.' <<< "$body" \
    && ! grep -q PATCH "$TMP_DIR/calls" && echo 0 || echo 1)

rm -f "$TMP_DIR/uploads"/*
run_journal "$TMP_DIR/card.json" --outcome failure --reason disallowed_paths >/dev/null
check "a refusal the publisher already parked gets a journal but no second header" \
  $(grep -q '^UPLOAD' "$TMP_DIR/calls" && ! grep -q PATCH "$TMP_DIR/calls" \
    && grep -q 'outside the approved product source paths' "$TMP_DIR/uploads"/autopr-run-77-*.md && echo 0 || echo 1)

rm -f "$TMP_DIR/uploads"/*
run_journal "$TMP_DIR/card.json" --outcome paused --reason operator_takeover >/dev/null
body="$(cat "$TMP_DIR/uploads"/autopr-run-77-*.md)"
check "an operator takeover says a human holds the checkout, not that time ran out" \
  $(grep -q '^UPLOAD' "$TMP_DIR/calls" && ! grep -q PATCH "$TMP_DIR/calls" \
    && grep -q 'an operator took the checkout over' <<< "$body" \
    && grep -q 'the working tree is held by the operator outside this workflow' <<< "$body" \
    && grep -q 'Finish or hand back the manual session' <<< "$body" \
    && ! grep -q 'Approve 10 more minutes' <<< "$body" \
    && ! grep -q 'No resumable work was saved' <<< "$body" && echo 0 || echo 1)

# A timeout reaches Cleanup as a plain step failure (investigate.sh writes
# paused=true only for codex rc 75), but checkpoint.sh has already parked the
# card. Overwriting that header would strip the "approve 10 more minutes"
# affordance select.sh and Espresso both prefix-match.
rm -f "$TMP_DIR/uploads"/*
printf '%s\n' '{"runtime_limited":true,"patch_saved":true,"patch_bytes":10,"changed_file_count":1,"changed_files":["a.tsx"],"created_at":"2026-09-12T04:00:00Z"}' \
  > "$TMP_DIR/checkpoint/metadata.json"
run_journal "$TMP_DIR/card.json" --outcome failure --reason investigate --checkpoint "$TMP_DIR/checkpoint" >/dev/null
body="$(cat "$TMP_DIR/uploads"/autopr-run-77-*.md)"
check "a timed-out run is reported as a pause and never overwrites the checkpoint's PAUSED header" \
  $(! grep -q PATCH "$TMP_DIR/calls" \
    && grep -q '^# AutoPR run #77 · PAUSED' <<< "$body" \
    && grep -q 'hit its time budget; the card is parked in Changes Requested' <<< "$body" \
    && grep -q 'Approve 10 more minutes from the ticket' <<< "$body" \
    && ! grep -q 'MODEL PASS FAILED' <<< "$body" && echo 0 || echo 1)
printf '%s\n' '{"schema_version":1,"task_id":"bbbb0000-0000-4000-8000-000000000002","id8":"bbbb0000","run_id":"77","created_at":"2026-09-12T04:00:00Z","patch_saved":true,"patch_bytes":36321,"changed_file_count":2,"changed_files":["client/src/pages/admin/Products.tsx","client/src/utils/tier.ts"],"report_saved":true,"decision_saved":true,"transcript_saved":true}' \
  > "$TMP_DIR/checkpoint/metadata.json"

# jq treats "" as truthy, so `join(", ") // "nothing"` never fired.
rm -f "$TMP_DIR/uploads"/*
mkdir -p "$TMP_DIR/bare-checkpoint"
printf '%s\n' '{"patch_saved":false,"report_saved":false,"decision_saved":false,"transcript_saved":false,"changed_file_count":0}' \
  > "$TMP_DIR/bare-checkpoint/metadata.json"
run_journal "$TMP_DIR/card.json" --outcome failure --reason verify --checkpoint "$TMP_DIR/bare-checkpoint" >/dev/null
check "a checkpoint holding nothing says so instead of rendering an empty list" \
  $(grep -q 'holds no model patch (it saved nothing)' "$TMP_DIR/uploads"/autopr-run-77-*.md && echo 0 || echo 1)

rm -f "$TMP_DIR/uploads"/*
set +e
AUTOPR_TEST_UPLOAD_FAIL=1 run_journal "$TMP_DIR/card.json" --outcome failure --reason setup >"$TMP_DIR/out" 2>"$TMP_DIR/err"; rc=$?
set -e
check "a failed upload warns, still records the stop reason, and never fails the caller" \
  $([ "$rc" = 0 ] && grep -q 'could not attach' "$TMP_DIR/err" \
    && grep -q 'STOPPED: DIED IN SETUP · run #77' "$TMP_DIR/calls" && echo 0 || echo 1)

# The header regex must recognise every machine header, or the next cycle
# prefixes its own state to the stale one instead of replacing it.
source "$AUTOPR_DIR/lib.sh"
dedupe() {
  local got; got="$(progress_note_with_origin "$1" "$2")"
  [ "$got" = "$3" ] && echo 0 || { printf '   got: %s\n' "$got" >&2; echo 1; }
}
check "STOPPED header is replaced wholesale on the next cycle" \
  $(dedupe "🤖 AUTO SETUP · READY FOR REVIEW" "🤖 AUTO SETUP · STOPPED: MODEL PASS FAILED · run #5 · note: see autopr-run-5-x.md" "🤖 AUTO SETUP · READY FOR REVIEW")
check "BLOCKED: DISALLOWED PATHS with its rejected marker is replaced" \
  $(dedupe "🤖 AUTO SETUP · STOPPED: CANCELLED · run #6 · note: see j.md" "🤖 AUTO SETUP · BLOCKED: DISALLOWED PATHS · build 15 · [autopr:rejected 2026-09-12T00:00:00Z] disallowed_paths · docs/PRODUCTS.md, CLAUDE.md · note: AutoPR refused it" "🤖 AUTO SETUP · STOPPED: CANCELLED · run #6 · note: see j.md")
check "ON HOLD with its parked marker is replaced" \
  $(dedupe "🤖 AUTO SETUP · READY FOR REVIEW" "🤖 AUTO SETUP · ON HOLD: REPEATED FAILURES · [autopr:parked 2026-09-12T00:00:00Z] investigate · note: three strikes" "🤖 AUTO SETUP · READY FOR REVIEW")
check "COSMETIC DIFF header is replaced" \
  $(dedupe "🤖 AUTO SETUP · READY FOR REVIEW" "🤖 AUTO SETUP · BLOCKED: COSMETIC DIFF · build 15 · prod 1.2 · 🟡 C55 · [autopr:rejected 2026-09-12T00:00:00Z] cosmetic_only · note: x" "🤖 AUTO SETUP · READY FOR REVIEW")
check "an off-CI journal header is replaced too (run #local, not just digits)" \
  $(dedupe "🤖 AUTO SETUP · READY FOR REVIEW" "🤖 AUTO SETUP · STOPPED: DIED IN SETUP · run #local · note: see autopr-run-local-x.md" "🤖 AUTO SETUP · READY FOR REVIEW")
check "the PAUSED header survives untouched when the journal writes none" \
  $(dedupe "🤖 AUTO SETUP · PAUSED: APPROVE 10 MORE MINUTES · checkpoint 77" $'🤖 AUTO SETUP · PAUSED: APPROVE 10 MORE MINUTES · checkpoint 77\nWhy more time: budget\nNext step: Approve 10 more minutes to continue from the saved checkpoint.' "🤖 AUTO SETUP · PAUSED: APPROVE 10 MORE MINUTES · checkpoint 77")
check "a human-authored note survives every machine header" \
  $(dedupe "🤖 AUTO SETUP · READY FOR REVIEW" $'Human wrote this\nand this' $'🤖 AUTO SETUP · READY FOR REVIEW · Human wrote this\nand this')

# Finding: journals are card attachments, and investigate.sh feeds card
# attachments to the model. One lands per run, so without an exclusion the
# fourth run spends three of its twelve slots re-reading its own prose.
feed_filter() {
  jq -c --argjson round 1 --arg id8 bbbb0000 --arg outcome "$1" '
    def journal: ((.filename // "") | test("^autopr-run-.*\\.md$"));
    def mine: ((.filename // "") | test("^(research|email)-(report-)?" + $id8 + "-r[0-9]+"));
    def prior_report: ((.filename // "") | test("^(research|email)-report-" + $id8 + "-r[0-9]+\\.md$"));
    map(select(journal | not))
    | (if $outcome == "artifact" then
        ([.[] | select(prior_report)] | sort_by(.created_at // "") | last) as $keep
        | map(select((mine | not) or (. == $keep)))
       else . end)
    | [.[] | .filename] | join(",")'
}
files_json='[{"filename":"autopr-run-77-20260912T040000Z.md","round_index":1,"created_at":"2026-09-12T04:00:00Z"},
             {"filename":"autopr-run-78-20260912T050000Z.md","round_index":1,"created_at":"2026-09-12T05:00:00Z"},
             {"filename":"spec.pdf","round_index":1,"created_at":"2026-09-12T03:00:00Z"},
             {"filename":"research-report-bbbb0000-r1.md","round_index":1,"created_at":"2026-09-12T02:00:00Z"}]'
check "run journals are never fed back to the model, in either mode" \
  $([ "$(printf '%s' "$files_json" | feed_filter pull_request)" = '"spec.pdf,research-report-bbbb0000-r1.md"' ] \
    && [ "$(printf '%s' "$files_json" | feed_filter artifact)" = '"spec.pdf,research-report-bbbb0000-r1.md"' ] && echo 0 || echo 1)
check "investigate.sh carries that exclusion in its own attachment filter" \
  $(grep -q 'def journal: ((.filename // "") | test("\^autopr-run-.\*' "$AUTOPR_DIR/investigate.sh" \
    && grep -q 'map(select(journal | not))' "$AUTOPR_DIR/investigate.sh" && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
