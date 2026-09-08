#!/usr/bin/env bash
# Research cards: the Kanban lane's first artifact kind. Exercises selection
# (no GitHub ledger), the sandbox bridge's web-search / image-input switches,
# the research decision validator, and the report publisher — all with
# Matcha, GitHub, and Codex stubbed on PATH.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOPR_DIR="$REPO_ROOT/scripts/kanban-autopr"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/runner" "$TMP_DIR/cache"

PASS=0
FAIL=0
check() {
    local desc="$1" ok="$2"
    if [ "$ok" = "0" ]; then
        echo "PASS: $desc"; PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"; FAIL=$((FAIL + 1))
    fi
}

workflow="$REPO_ROOT/.github/workflows/kanban-autopr.yml"

################################################################################
# Kind registry: research is an artifact kind with its own prompt, model,
# sandbox switches, headings, validator, and publisher.
source "$AUTOPR_DIR/lib.sh"
check "the kind registry maps the research category to an artifact mode" \
    $([ "$(autopr_kind_for_category research)" = research ] \
      && [ "$(autopr_kind_for_category bug)" = investigate ] \
      && [ "$(autopr_kind_field research outcome)" = artifact ] \
      && [ "$(autopr_kind_field investigate outcome)" = pull_request ] \
      && [ "$(autopr_kind_field research model)" = gpt-5.6-luna ] \
      && [ "$(autopr_kind_field research effort)" = high ] \
      && [ "$(autopr_kind_field research publisher)" = publish-research.sh ] \
      && [ "$(autopr_kind_field research decision)" = normalize-research ] \
      && [ -f "$AUTOPR_DIR/$(autopr_kind_field research prompt)" ] \
      && echo 0 || echo 1)
check "research sandbox switches enforce an empty patch and enable search + images" \
    $(switches="$(autopr_kind_field research sandbox)"; \
      [[ "$switches" == *AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1* ]] \
      && [[ "$switches" == *AUTOPR_CODEX_WEB_SEARCH=1* ]] \
      && [[ "$switches" == *AUTOPR_CODEX_IMAGE_INPUTS=1* ]] \
      && [ -z "$(autopr_kind_field investigate sandbox)" ] \
      && echo 0 || echo 1)
check "an unknown mode is refused by the registry" \
    $(! autopr_kind_field shortlist model >/dev/null 2>&1 && echo 0 || echo 1)

################################################################################
# select.sh: a research card never consults the GitHub PR ledger.
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$RESEARCH_TEST_GH_LOG"
case "$1 $2" in
    "pr list") printf '[]\n' ;;
    "pr view") printf '{"state":"OPEN"}\n' ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"
printf '[]\n' > "$TMP_DIR/bot-prs.json"

run_select() {
    local cards="$1" out="$2"
    : > "$RESEARCH_TEST_GH_LOG"
    PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_BOT_PRS_FILE="${SELECT_BOT_PRS_FILE:-$TMP_DIR/bot-prs.json}" \
    AUTOPR_CACHE_DIR="$TMP_DIR/cache" AUTOPR_SELECT_READ_ONLY=true \
    MAX_OPEN_IMPLEMENTATION_PRS="${SELECT_MAX_OPEN:-10}" \
        "$AUTOPR_DIR/select.sh" "$cards" > "$out" 2>"$out.err"
}
export RESEARCH_TEST_GH_LOG="$TMP_DIR/gh.log"

cat > "$TMP_DIR/cards-todo.json" <<'EOF'
[{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Research how AWS Lambda works","board_column":"todo","category":"research","autopr_capabilities":["research"],"created_at":"2026-09-01T00:00:00Z","last_moved_at":"2026-09-01T00:00:00Z"}]
EOF
run_select "$TMP_DIR/cards-todo.json" "$TMP_DIR/select-todo.json"
check "a research card in Todo selects as mode research without any gh pr list call" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-todo.json" 2>/dev/null)" = research ] \
      && ! grep -q 'pr list' "$RESEARCH_TEST_GH_LOG" \
      && echo 0 || echo 1)

cat > "$TMP_DIR/cards-cr.json" <<'EOF'
[{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Research how AWS Lambda works","board_column":"changes_requested","review_note":"Compare cold-start cost too","category":"research","autopr_capabilities":["research"],"created_at":"2026-09-01T00:00:00Z","last_moved_at":"2026-09-02T00:00:00Z","progress_note":"🤖 AUTO SETUP · READY FOR REVIEW · build 900 · prod abc1234 · 🟡 C80 · note: Lambda fits the worker tier"}]
EOF
run_select "$TMP_DIR/cards-cr.json" "$TMP_DIR/select-cr.json"
check "a research card sent back with a review note reruns as research (next report round)" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-cr.json" 2>/dev/null)" = research ] \
      && ! grep -q 'pr ' "$RESEARCH_TEST_GH_LOG" \
      && echo 0 || echo 1)

cat > "$TMP_DIR/cards-nospec.json" <<'EOF'
[{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Research stuff","board_column":"changes_requested","category":"research","autopr_capabilities":["research"],"created_at":"2026-09-01T00:00:00Z","last_moved_at":"2026-09-07T00:00:00Z","progress_note":"🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build 900 · prod abc1234 · 🟡 C20 · [autopr:no-spec 2026-09-08T01:00:00Z] needs_clarification · note: subject too broad\n\nAnswers needed — reply below with the numbered choices:\n1. Which system?"}]
EOF
run_select "$TMP_DIR/cards-nospec.json" "$TMP_DIR/select-nospec.json"
nospec_rc=$?
check "a research card parked with a fresh needs_clarification marker is skipped" \
    $([ "$nospec_rc" = 3 ] && echo 0 || echo 1)

jq '.[0] += {autopr_run_requested_at: "2026-09-08T02:00:00Z"}' "$TMP_DIR/cards-nospec.json" \
    > "$TMP_DIR/cards-nospec-run.json"
run_select "$TMP_DIR/cards-nospec-run.json" "$TMP_DIR/select-nospec-run.json"
check "Run AutoPR now on a parked research card overrides the marker" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-nospec-run.json" 2>/dev/null)" = research ] && echo 0 || echo 1)

jq '.[0] += {autopr_reconsideration_pending: true, autopr_reconsideration_at: "2026-09-08T02:00:00Z"}' \
    "$TMP_DIR/cards-nospec.json" > "$TMP_DIR/cards-nospec-ctx.json"
run_select "$TMP_DIR/cards-nospec-ctx.json" "$TMP_DIR/select-nospec-ctx.json"
check "additional context on a parked research card overrides the marker" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-nospec-ctx.json" 2>/dev/null)" = research ] && echo 0 || echo 1)

# The open-PR cap bounds NEW implementation drafts; a report opens none.
jq -n '[range(10) | {number: (100 + .), labels: ["autopr"]}]' > "$TMP_DIR/bot-prs-full.json"
SELECT_BOT_PRS_FILE="$TMP_DIR/bot-prs-full.json" run_select "$TMP_DIR/cards-todo.json" "$TMP_DIR/select-capped.json"
check "the open-PR cap does not block a research card" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-capped.json" 2>/dev/null)" = research ] && echo 0 || echo 1)

# Capability grants are per board and default to none. An ungranted board must
# leave the card alone rather than fall back to drafting a PR: a Research card
# is not a request for code.
jq '.[0].autopr_capabilities = []' "$TMP_DIR/cards-todo.json" > "$TMP_DIR/cards-ungranted.json"
run_select "$TMP_DIR/cards-ungranted.json" "$TMP_DIR/select-ungranted.json"
ungranted_rc=$?
check "a research card on a board without the research grant is skipped, not downgraded to a PR" \
  $([ "$ungranted_rc" = 3 ] && echo 0 || echo 1)

jq '.[0].autopr_capabilities = ["outreach","browse"]' "$TMP_DIR/cards-todo.json" > "$TMP_DIR/cards-othercaps.json"
run_select "$TMP_DIR/cards-othercaps.json" "$TMP_DIR/select-othercaps.json"
othercaps_rc=$?
check "another board's grants do not stand in for the research grant" \
  $([ "$othercaps_rc" = 3 ] && echo 0 || echo 1)

# The stamp is absent entirely when the capabilities endpoint could not be read.
jq 'map(del(.autopr_capabilities))' "$TMP_DIR/cards-todo.json" > "$TMP_DIR/cards-nocaps.json"
run_select "$TMP_DIR/cards-nocaps.json" "$TMP_DIR/select-nocaps.json"
nocaps_rc=$?
check "an unreadable capability stamp fails closed" \
  $([ "$nocaps_rc" = 3 ] && echo 0 || echo 1)

check "the kind registry names the grant each artifact kind needs" \
    $([ "$(autopr_kind_field research capability)" = research ] \
      && [ -z "$(autopr_kind_field investigate capability)" ] \
      && [ -z "$(autopr_kind_field rework capability)" ] \
      && echo 0 || echo 1)

cat > "$TMP_DIR/cards-eng.json" <<'EOF'
[{"task_id":"bbbb0000-0000-4000-8000-000000000002","id8":"bbbb0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Add a route","board_column":"todo","category":"engineering","created_at":"2026-09-01T00:00:00Z","last_moved_at":"2026-09-01T00:00:00Z"}]
EOF
run_select "$TMP_DIR/cards-eng.json" "$TMP_DIR/select-eng.json"
check "a PR-kind card still goes through the GitHub ledger and selects investigate" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-eng.json" 2>/dev/null)" = investigate ] \
      && grep -q 'pr list' "$RESEARCH_TEST_GH_LOG" \
      && echo 0 || echo 1)

################################################################################
# run-codex-sandboxed.sh: the two research switches, default off.
SANDBOX_TEST_REPO="$TMP_DIR/sandbox-repo"
mkdir -p "$SANDBOX_TEST_REPO/client/src"
git -C "$SANDBOX_TEST_REPO" init -q
git -C "$SANDBOX_TEST_REPO" config user.name test
git -C "$SANDBOX_TEST_REPO" config user.email test@example.com
printf 'export const a = 1;\n' > "$SANDBOX_TEST_REPO/client/src/a.ts"
git -C "$SANDBOX_TEST_REPO" add . && git -C "$SANDBOX_TEST_REPO" commit -qm initial
git -C "$SANDBOX_TEST_REPO" branch -M main

cat > "$TMP_DIR/bin/codex" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$RESEARCH_TEST_CODEX_ARGS"
prompt="${!#}"
report_path="$(printf '%s\n' "$prompt" | sed -n 's/^REPORT=//p')"
decision_path="$(printf '%s\n' "$prompt" | sed -n 's/^DECISION=//p')"
workspace=""; args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do [ "${args[$i]}" != -C ] || workspace="${args[$((i + 1))]}"; done
mkdir -p "$(dirname "$report_path")" "$(dirname "$decision_path")"
printf '### Summary\nstub\n' > "$report_path"
printf '{"schema_version":1}\n' > "$decision_path"
[ "${CODEX_STUB_TOUCH:-0}" != 1 ] || printf 'export const b = 2;\n' > "$workspace/client/src/b.ts"
EOF
chmod +x "$TMP_DIR/bin/codex"
printf '%s\n' 'REPORT=REPORT_PATH' 'DECISION=DECISION_PATH' > "$TMP_DIR/sandbox-prompt.txt"
printf '{"downloaded_attachments":[]}\n' > "$TMP_DIR/context.json"
printf 'PNGSTUB\n' > "$TMP_DIR/shot.png"
printf 'notes\n' > "$TMP_DIR/notes.txt"

run_bridge() {
    PATH="$TMP_DIR/bin:$PATH" AUTOPR_SANDBOX_TEST_DIRECT=1 \
    AUTOPR_SANDBOX_REPO_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox-runtime" \
    AUTOPR_CODEX_BACKOFF_FILE="$TMP_DIR/backoff.json" \
    RESEARCH_TEST_CODEX_ARGS="$TMP_DIR/codex-args" \
    "$@" "$AUTOPR_DIR/run-codex-sandboxed.sh" "$TMP_DIR/sandbox-prompt.txt" \
        "$TMP_DIR/bridge-report.md" "$TMP_DIR/bridge-decision.json" \
        -f "$TMP_DIR/context.json" -f "$TMP_DIR/shot.png" -f "$TMP_DIR/notes.txt"
}

run_bridge env AUTOPR_CODEX_WEB_SEARCH=1 AUTOPR_CODEX_IMAGE_INPUTS=1 > "$TMP_DIR/bridge-on.log" 2>&1
bridge_on_rc=$?
[ "$bridge_on_rc" = 0 ] || sed -n '1,40p' "$TMP_DIR/bridge-on.log"
check "with the research switches on, codex exec gets live web search and the png as an image input" \
    $([ "$bridge_on_rc" = 0 ] \
      && grep -qxF 'web_search="live"' "$TMP_DIR/codex-args" \
      && grep -qxF -- '-i' "$TMP_DIR/codex-args" \
      && grep -qE '/\.git/autopr-io/input/02-shot\.png$' "$TMP_DIR/codex-args" \
      && [ "$(grep -cx -- '-i' "$TMP_DIR/codex-args")" = 1 ] \
      && echo 0 || echo 1)
check "the image input path is the workspace path codex runs in, not the host attachment path" \
    $(image_path="$(grep -A1 -x -- '-i' "$TMP_DIR/codex-args" | tail -1)"; \
      [[ "$image_path" == "$TMP_DIR/sandbox-runtime/workspace/"* ]] \
      && [ -f "$image_path" ] \
      && echo 0 || echo 1)

run_bridge env > "$TMP_DIR/bridge-off.log" 2>&1
bridge_off_rc=$?
check "with the switches off (every PR lane), neither web search nor image inputs are passed" \
    $([ "$bridge_off_rc" = 0 ] \
      && ! grep -q 'web_search' "$TMP_DIR/codex-args" \
      && ! grep -qx -- '-i' "$TMP_DIR/codex-args" \
      && echo 0 || echo 1)

run_bridge env AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1 AUTOPR_CODEX_WEB_SEARCH=1 CODEX_STUB_TOUCH=1 \
    > "$TMP_DIR/bridge-touch.log" 2>&1
bridge_touch_rc=$?
check "a research pass that changes a repository file is discarded before it reaches the checkout" \
    $([ "$bridge_touch_rc" != 0 ] \
      && grep -q 'unexpectedly changed repository files' "$TMP_DIR/bridge-touch.log" \
      && [ ! -e "$SANDBOX_TEST_REPO/client/src/b.ts" ] \
      && echo 0 || echo 1)

################################################################################
# decision.sh normalize-research
cat > "$TMP_DIR/research-raw.json" <<'EOF'
{"schema_version":1,"outcome":"research_report","card_note":"Lambda fits the worker tier; keep the API on containers.","summary":"Lambda suits bursty, stateless jobs. Matcha's Celery worker tier is the candidate; the FastAPI app is not.","sources":[{"title":"AWS Lambda pricing","url":"https://aws.example.com/lambda/pricing"},{"title":"Lambda cold starts","url":"https://aws.example.com/lambda/cold-starts"}],"confidence":{"score":82,"reason":"primary vendor docs plus the worker code"},"questions":[],"staged_actions":[{"kind":"email","to":"AWS account team","subject":"Lambda pricing for a small workload","body":"Hi — we run ~2k jobs/day…","why":"Confirms the committed-use discount before we plan the move."}]}
EOF
"$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-raw.json" "$TMP_DIR/research-decision.json" >/dev/null 2>&1
normalize_rc=$?
check "a valid research decision normalizes with the keys the generic workflow steps read" \
    $([ "$normalize_rc" = 0 ] \
      && jq -e '.kind == "research" and .safe_changes_present == false and .awaiting_human == false
                and .confidence_score == 82 and .confidence_band == "high"
                and .criticality.level == "yellow" and (.staged_actions | length == 1)' \
            "$TMP_DIR/research-decision.json" >/dev/null \
      && echo 0 || echo 1)
check "normalize-research also accepts the directive-policy argument investigate.sh passes to every validator" \
    $("$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-raw.json" \
        "$TMP_DIR/research-decision-4arg.json" "$TMP_DIR/nonexistent-policy.json" >/dev/null 2>&1 && echo 0 || echo 1)

jq '.sources = []' "$TMP_DIR/research-raw.json" > "$TMP_DIR/research-nosources.json"
check "a report with no sources is rejected" \
    $(! "$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-nosources.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

jq '.outcome = "needs_clarification"' "$TMP_DIR/research-raw.json" > "$TMP_DIR/research-noq.json"
check "needs_clarification without questions is rejected" \
    $(! "$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-noq.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

jq '.outcome = "implementation"' "$TMP_DIR/research-raw.json" > "$TMP_DIR/research-badoutcome.json"
check "a PR-lane outcome is rejected by the research validator" \
    $(! "$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-badoutcome.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

jq '.staged_actions[0].kind = "send_now"' "$TMP_DIR/research-raw.json" > "$TMP_DIR/research-badaction.json"
check "a staged action outside email|contact|review_request is rejected" \
    $(! "$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-badaction.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

jq '.card_note = "one · two"' "$TMP_DIR/research-raw.json" > "$TMP_DIR/research-badnote.json"
check "a card note carrying the note separator is rejected" \
    $(! "$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-badnote.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

cat > "$TMP_DIR/clarify-raw.json" <<'EOF'
{"schema_version":1,"outcome":"needs_clarification","card_note":"Which system the card means is undecided.","summary":"The card says 'see how we can benefit' without naming a workload.","sources":[],"confidence":{"score":20,"reason":"no scope"},"questions":[{"id":"q1","question":"Which workload should the research target?","why_blocking":"benefit depends entirely on the workload","options":[{"key":"a","label":"Celery worker jobs","impact":"cost and cold-start analysis of the worker tier"},{"key":"b","label":"The FastAPI app","impact":"latency analysis of request handling"}],"default_assumption":"Celery worker jobs"}]}
EOF
"$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/clarify-raw.json" "$TMP_DIR/clarify-decision.json" >/dev/null 2>&1
check "a needs_clarification decision normalizes as awaiting_human" \
    $(jq -e '.awaiting_human == true and (.questions | length == 1) and .confidence_band == "low"' \
        "$TMP_DIR/clarify-decision.json" >/dev/null 2>&1 && echo 0 || echo 1)

################################################################################
# publish-research.sh
cat > "$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
output_file="" payload="" url="" method="GET" form=""
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
printf '%s %s\n' "$method" "$url" >> "$RESEARCH_TEST_CURL_LOG"
respond() { [ -z "$output_file" ] || printf '%s' "$1" > "$output_file"; printf 200; }
case "$url" in
  */auth/login) printf '{"access_token":"test-token"}' ;;
  */files)
    if [ "$method" = POST ]; then
      src="${form#file=@}"; src="${src%%;*}"
      cp "$src" "$RESEARCH_TEST_UPLOADED"
      printf '%s\n' "$(basename "$src")" > "$RESEARCH_TEST_UPLOADED_NAME"
      respond '{"id":"file-new-1","filename":"uploaded.md"}'
    else
      respond "${RESEARCH_TEST_EXISTING_FILES:-[]}"
    fi ;;
  */activity) printf '%s' "$payload" > "$RESEARCH_TEST_ACTIVITY"; respond '{"ok":true}' ;;
  */autopr/context-request) printf '%s' "$payload" > "$RESEARCH_TEST_CONTEXT_REQUEST"; respond '{"ok":true}' ;;
  */autopr/result-notification) printf '%s' "$payload" > "$RESEARCH_TEST_RESULT_NOTIFICATION"; respond '{"ok":true}' ;;
  */tasks/*) printf '%s' "$payload" > "$RESEARCH_TEST_CARD_PATCH"; respond '{"ok":true}' ;;
  *) respond '{"ok":true}' ;;
esac
EOF
chmod +x "$TMP_DIR/bin/curl"
cat > "$TMP_DIR/env" <<'EOF'
MATCHA_API_URL=https://example.invalid/api
MATCHA_BOT_EMAIL=bot@example.com
MATCHA_BOT_PASSWORD=secret
MATCHA_PROJECT_IDS=one
MATCHA_ASSIGNEE_EMAIL=bot@example.com
EOF
cat > "$TMP_DIR/report.md" <<'EOF'
### Summary
Lambda suits bursty, stateless jobs. Matcha's Celery worker tier is the candidate.
### Findings
- Per-invocation billing [1].
### How it applies to Matcha
`server/app/workers/celery_app.py:1` runs continuously; the periodic tasks could move.
### Recommendation
Pilot one periodic task.
### Sources
1. AWS Lambda pricing — https://aws.example.com/lambda/pricing
2. Lambda cold starts — https://aws.example.com/lambda/cold-starts
### Confidence
high — a cost model against real job counts would raise it further.
EOF
cat > "$TMP_DIR/card.json" <<'EOF'
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Research how AWS Lambda works","category":"research","autopr_capabilities":["research"],"mode":"research","autopr_reconsideration_event_id":"eeeeeeee-0000-4000-8000-000000000001","progress_note":"🤖 AUTO SETUP · READY FOR REVIEW · build 800 · prod 1111111 · 🟡 C50 · note: earlier round\nkeep this human line","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
EOF

run_publisher() {
    local card="$1" decision="$2"
    : > "$RESEARCH_TEST_CURL_LOG"
    rm -f "$RESEARCH_TEST_ACTIVITY" "$RESEARCH_TEST_CARD_PATCH" "$RESEARCH_TEST_CONTEXT_REQUEST" \
        "$RESEARCH_TEST_RESULT_NOTIFICATION" "$RESEARCH_TEST_UPLOADED" "$RESEARCH_TEST_UPLOADED_NAME" "$RESEARCH_TEST_GH_LOG"
    PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
        "$AUTOPR_DIR/publish-research.sh" "$card" "$TMP_DIR/report.md" "$decision"
}
export RESEARCH_TEST_CURL_LOG="$TMP_DIR/curl.log" RESEARCH_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    RESEARCH_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" RESEARCH_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    RESEARCH_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    RESEARCH_TEST_UPLOADED="$TMP_DIR/uploaded.md" RESEARCH_TEST_UPLOADED_NAME="$TMP_DIR/uploaded-name"
export RESEARCH_TEST_EXISTING_FILES='[{"id":"file-old","filename":"research-report-aaaa0000-r1.md"},{"id":"file-shot","filename":"shot.png"}]'

run_publisher "$TMP_DIR/card.json" "$TMP_DIR/research-decision.json" > "$TMP_DIR/publish.log" 2>&1
publish_rc=$?
[ "$publish_rc" = 0 ] || sed -n '1,40p' "$TMP_DIR/publish.log"
check "the report is uploaded to the task as the next numbered round" \
    $([ "$publish_rc" = 0 ] \
      && grep -q 'POST https://example.invalid/api/matcha-work/projects/8b924347-d6e4-4000-8e7d-ca8f46f76fba/tasks/aaaa0000-0000-4000-8000-000000000001/files' "$RESEARCH_TEST_CURL_LOG" \
      && [ "$(cat "$RESEARCH_TEST_UPLOADED_NAME")" = research-report-aaaa0000-r2.md ] \
      && echo 0 || echo 1)
check "the uploaded file carries a trusted provenance header, the model report, and the unsent staged actions" \
    $(head -1 "$RESEARCH_TEST_UPLOADED" | grep -q '^_AutoPR research · .* · model gpt-5.6-luna · round 2 · 2 source(s)_' \
      && grep -q '^### Findings' "$RESEARCH_TEST_UPLOADED" \
      && grep -q '^### Proposed actions (not sent)' "$RESEARCH_TEST_UPLOADED" \
      && grep -q 'NOT sent; each needs your approval' "$RESEARCH_TEST_UPLOADED" \
      && grep -q '\[email\] to: AWS account team' "$RESEARCH_TEST_UPLOADED" \
      && echo 0 || echo 1)
check "a summary note is posted with the report attached and threaded under the additional-context event" \
    $(jq -e '.kind == "note" and .attachment_ids == ["file-new-1"]
             and (.body | startswith("Lambda suits bursty"))
             and (.body | contains("Report attached: research-report-aaaa0000-r2.md"))
             and (.body | contains("NOT sent"))
             and .reply_to == "eeeeeeee-0000-4000-8000-000000000001"' \
        "$RESEARCH_TEST_ACTIVITY" >/dev/null && echo 0 || echo 1)
check "the card moves to Review with a structured note that replaces the prior round's prefix and keeps the human line" \
    $(jq -e '.board_column == "review"
             and (.progress_note | startswith("🤖 AUTO SETUP · READY FOR REVIEW · build 850 · prod 68a70f4 · 🟡 C82 · note: Lambda fits the worker tier; keep the API on containers."))
             and (.progress_note | contains("keep this human line"))
             and (.progress_note | contains("C50") | not)' \
        "$RESEARCH_TEST_CARD_PATCH" >/dev/null && echo 0 || echo 1)
check "the additional-context author gets a decision-bound result notification" \
    $(jq -e '.reconsideration_event_id == "eeeeeeee-0000-4000-8000-000000000001"
             and (.message | contains("round 2"))
             and (.expected_progress_note | startswith("🤖 AUTO SETUP · READY FOR REVIEW"))' \
        "$RESEARCH_TEST_RESULT_NOTIFICATION" >/dev/null && echo 0 || echo 1)
check "the research publisher never calls gh" \
    $([ ! -s "$RESEARCH_TEST_GH_LOG" ] && echo 0 || echo 1)
check "no context request is posted for a delivered report" \
    $([ ! -e "$RESEARCH_TEST_CONTEXT_REQUEST" ] && echo 0 || echo 1)

# First report on a fresh card, no staged actions, no reconsideration.
export RESEARCH_TEST_EXISTING_FILES='[]'
jq 'del(.autopr_reconsideration_event_id) | .progress_note = ""' "$TMP_DIR/card.json" > "$TMP_DIR/card-fresh.json"
jq '.staged_actions = []' "$TMP_DIR/research-decision.json" > "$TMP_DIR/research-decision-plain.json"
run_publisher "$TMP_DIR/card-fresh.json" "$TMP_DIR/research-decision-plain.json" > "$TMP_DIR/publish-fresh.log" 2>&1
fresh_rc=$?
check "a fresh card gets round 1, a plain note, and no result notification" \
    $([ "$fresh_rc" = 0 ] \
      && [ "$(cat "$RESEARCH_TEST_UPLOADED_NAME")" = research-report-aaaa0000-r1.md ] \
      && ! grep -q 'Proposed actions' "$RESEARCH_TEST_UPLOADED" \
      && jq -e '(.body | contains("NOT sent") | not) and (has("reply_to") | not)' "$RESEARCH_TEST_ACTIVITY" >/dev/null \
      && [ ! -e "$RESEARCH_TEST_RESULT_NOTIFICATION" ] \
      && jq -e '.progress_note == "🤖 AUTO SETUP · READY FOR REVIEW · build 850 · prod 68a70f4 · 🟡 C82 · note: Lambda fits the worker tier; keep the API on containers."' "$RESEARCH_TEST_CARD_PATCH" >/dev/null \
      && echo 0 || echo 1)

# Too vague: park the card with the exact question form Espresso parses.
run_publisher "$TMP_DIR/card-fresh.json" "$TMP_DIR/clarify-decision.json" > "$TMP_DIR/publish-clarify.log" 2>&1
clarify_rc=$?
[ "$clarify_rc" = 0 ] || sed -n '1,40p' "$TMP_DIR/publish-clarify.log"
check "a needs_clarification result parks the card in Changes Requested with a durable no-spec marker" \
    $([ "$clarify_rc" = 0 ] \
      && jq -e '.board_column == "changes_requested"
                and (.progress_note | startswith("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build 850 · prod 68a70f4 · 🟡 C20 · [autopr:no-spec "))
                and (.progress_note | contains("] needs_clarification · note: Which system the card means is undecided."))
                and (.progress_note | contains("Answers needed — reply below with the numbered choices:"))
                and (.progress_note | contains("1. Which workload should the research target?"))' \
            "$RESEARCH_TEST_CARD_PATCH" >/dev/null \
      && echo 0 || echo 1)
check "the clarification asks the owner in project chat, bound to the exact note, and uploads nothing" \
    $(jq -e '(.reason | contains("Which workload should the research target?"))
             and (.expected_progress_note | startswith("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS"))' \
        "$RESEARCH_TEST_CONTEXT_REQUEST" >/dev/null \
      && ! grep -q 'POST .*/files' "$RESEARCH_TEST_CURL_LOG" \
      && [ ! -e "$RESEARCH_TEST_ACTIVITY" ] \
      && echo 0 || echo 1)
check "the parked note round-trips through select.sh as a skip until a human acts" \
    $(jq -n --slurpfile patch "$RESEARCH_TEST_CARD_PATCH" \
        '[{task_id:"aaaa0000-0000-4000-8000-000000000001",id8:"aaaa0000",project_id:"p",title:"Research stuff",board_column:"changes_requested",category:"research",created_at:"2026-09-01T00:00:00Z",last_moved_at:"2026-09-01T00:00:00Z",progress_note:$patch[0].progress_note}]' \
        > "$TMP_DIR/cards-parked.json" \
      && run_select "$TMP_DIR/cards-parked.json" "$TMP_DIR/select-parked.json"; [ "$?" = 3 ] && echo 0 || echo 1)

# The raw model JSON never drives a board write.
run_publisher "$TMP_DIR/card-fresh.json" "$TMP_DIR/research-raw.json" > "$TMP_DIR/publish-raw.log" 2>&1
raw_rc=$?
check "an unvalidated (raw) decision is refused before any board write" \
    $([ "$raw_rc" != 0 ] && [ ! -s "$RESEARCH_TEST_CURL_LOG" ] && echo 0 || echo 1)

################################################################################
# Workflow wiring: PR-only steps are gated off for research; the research
# publisher runs from the control-plane snapshot.
check "workflow skips branch creation, coverage, verify, publication copy, and publish.sh for research" \
    $(grep -qF "if: steps.select.outputs.skip == 'false' && steps.select.outputs.mode != 'research'" "$workflow" \
      && [ "$(grep -c "steps.select.outputs.mode != 'research'" "$workflow")" -ge 6 ] \
      && echo 0 || echo 1)
check "workflow publishes research from the trusted control root without a GitHub token" \
    $(grep -qF 'name: Publish research report' "$workflow" \
      && grep -qF '"$AUTOPR_CONTROL_ROOT/kanban-autopr/publish-research.sh"' "$workflow" \
      && grep -qF "steps.investigate.outcome == 'success' && steps.select.outputs.mode == 'research'" "$workflow" \
      && ! awk '/name: Publish research report/,/name: Cleanup/' "$workflow" | grep -qE '^[[:space:]]*GH_TOKEN:' \
      && echo 0 || echo 1)
check "ci syntax-checks the research publisher and the self-audit runs this suite" \
    $(grep -qF 'scripts/kanban-autopr/publish-research.sh' "$REPO_ROOT/.github/workflows/ci.yml" \
      && grep -qF 'test_kanban_autopr_research.sh' "$REPO_ROOT/scripts/autopr-self-audit/audit.sh" \
      && echo 0 || echo 1)
check "the research prompt forbids repository edits and sending, and names every required heading" \
    $(prompt="$AUTOPR_DIR/_prompt_research.txt"; \
      grep -q 'Do not edit, create, move, or delete any repository file' "$prompt" \
      && grep -q 'Send anything to anyone' "$prompt" \
      && grep -qF '### How it applies to Matcha' "$prompt" \
      && grep -qF '### Sources' "$prompt" \
      && grep -qF '"staged_actions"' "$prompt" \
      && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
