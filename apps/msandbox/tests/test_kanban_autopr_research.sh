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
check "explicit screenshot deliverables are distinguished from input-evidence mentions and waivers" \
    $(autopr_research_screenshots_required '{"title":"EMS documentation","description":"Expected output: graphs, data, and screenshots from your research"}' \
      && ! autopr_research_screenshots_required '{"title":"Review attached screenshot","description":"Explain what this input shows"}' \
      && ! autopr_research_screenshots_required '{"title":"EMS documentation","description":"Include screenshots","review_note":"No need for screenshots this round"}' \
      && autopr_research_screenshots_required '{"title":"EMS documentation","description":"Short report","review_note":"The last report had no screenshots; add them"}' \
      && echo 0 || echo 1)
check "research sandbox switches enforce an empty patch and enable search + images" \
    $(switches="$(autopr_kind_field research sandbox)"; \
      [[ "$switches" == *AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1* ]] \
      && [[ "$switches" == *AUTOPR_CODEX_WEB_SEARCH=1* ]] \
      && [[ "$switches" == *AUTOPR_CODEX_IMAGE_INPUTS=1* ]] \
      && echo 0 || echo 1)
check "both PR lanes validate grounded blockers while search remains grant-gated" \
    $([ -z "$(autopr_kind_field investigate sandbox)" ] \
      && [ -z "$(autopr_kind_field rework sandbox)" ] \
      && [ "$(autopr_kind_field investigate decision)" = normalize-grounded ] \
      && [ "$(autopr_kind_field rework decision)" = normalize-grounded ] \
      && [ -z "$(autopr_kind_field investigate capability)" ] \
      && echo 0 || echo 1)
check "an unknown mode is refused by the registry" \
    $(! autopr_kind_field shortlist model >/dev/null 2>&1 && echo 0 || echo 1)

check "the model's history copy drops the lane's bookkeeping rows and keeps discussion" \
    $(stripped="$(autopr_strip_bookkeeping_history '[{"event_type":"activity","metadata":{"kind":"note","body":"real comment"}},{"event_type":"activity","metadata":{"kind":"autopr_staged_action","action_body":"draft email"}},{"event_type":"activity","metadata":{"kind":"autopr_run_claim"}},{"event_type":"activity","metadata":{"kind":"autopr_staged_action_result","state":"sent"}},{"event_type":"column_change"}]')"; \
      [ "$(printf '%s' "$stripped" | jq 'length')" = 2 ] \
      && printf '%s' "$stripped" | jq -e 'any(.[]; (.metadata.body // "") == "real comment")' >/dev/null \
      && ! printf '%s' "$stripped" | grep -q 'draft email' \
      && grep -q 'history-for-model.json' "$AUTOPR_DIR/investigate.sh" \
      && echo 0 || echo 1)

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

jq '.[0] |= (.description = "Expected output: graphs, data, and screenshots from your research" | .autopr_capabilities = ["research"])' \
    "$TMP_DIR/cards-todo.json" > "$TMP_DIR/cards-shots-no-browse.json"
run_select "$TMP_DIR/cards-shots-no-browse.json" "$TMP_DIR/select-shots-no-browse.json"
shots_no_browse_rc=$?
check "a screenshot-required report is held when the board lacks browser capture" \
    $([ "$shots_no_browse_rc" = 3 ] \
      && jq -e 'any(.[]; .id8 == "aaaa0000" and .capability == "browse")' \
          "$TMP_DIR/cache/ungranted.json" >/dev/null \
      && echo 0 || echo 1)

jq '.[0].autopr_capabilities += ["browse"]' "$TMP_DIR/cards-shots-no-browse.json" \
    > "$TMP_DIR/cards-shots-browse.json"
run_select "$TMP_DIR/cards-shots-browse.json" "$TMP_DIR/select-shots-browse.json"
check "a screenshot-required report runs once both research and browse are granted" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-shots-browse.json" 2>/dev/null)" = research ] \
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

check "an ungranted skip leaves a hint the dashboard can name, even on a read-only pass" \
  $(jq -e --arg id8 aaaa0000 'type == "array" and any(.[]; .id8 == $id8 and .capability == "research")' \
        "$TMP_DIR/cache/ungranted.json" >/dev/null 2>&1 && echo 0 || echo 1)

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

# A pass whose only eligible card is an artifact kind touches no GitHub
# resource, so a gh outage must not block it. The open-PR count is resolved
# lazily, the first time a card would actually open a new PR.
mkdir -p "$TMP_DIR/gh-down"
cat > "$TMP_DIR/gh-down/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$RESEARCH_TEST_GH_LOG"
exit 1
EOF
chmod +x "$TMP_DIR/gh-down/gh"
: > "$RESEARCH_TEST_GH_LOG"
PATH="$TMP_DIR/gh-down:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
AUTOPR_BOT_PRS_FILE="$TMP_DIR/no-such-file.json" \
AUTOPR_CACHE_DIR="$TMP_DIR/cache" AUTOPR_SELECT_READ_ONLY=true \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/cards-todo.json" > "$TMP_DIR/select-ghdown.json" 2>"$TMP_DIR/select-ghdown.err"
check "a research-only pass still selects when GitHub is unreadable" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-ghdown.json" 2>/dev/null)" = research ] \
      && ! grep -q 'pr list' "$RESEARCH_TEST_GH_LOG" \
      && echo 0 || echo 1)
PATH="$TMP_DIR/gh-down:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
AUTOPR_BOT_PRS_FILE="$TMP_DIR/no-such-file.json" \
AUTOPR_CACHE_DIR="$TMP_DIR/cache" AUTOPR_SELECT_READ_ONLY=true \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/cards-eng.json" > "$TMP_DIR/select-ghdown-eng.json" 2>"$TMP_DIR/select-ghdown-eng.err"
ghdown_eng_rc=$?
check "a PR-kind card still consults GitHub and is passed over, not drafted blind, when it is unreadable" \
    $([ "$ghdown_eng_rc" != 0 ] \
      && [ -z "$(cat "$TMP_DIR/select-ghdown-eng.json")" ] \
      && grep -q 'pr list' "$RESEARCH_TEST_GH_LOG" \
      && echo 0 || echo 1)
# ...but passing it over must not read as an empty queue. The eager PR-count
# read used to die here; making it lazy (so the research pass above needs no
# GitHub at all) took the outage signal with it, and the workflow reports
# NOTHING_TO_DO as a green "Nothing to build this run." -- so a `gh` outage or
# an expired token stalled the whole lane silently, every minute, with nothing
# red anywhere.
check "an unreadable GitHub fails the pass instead of reporting an empty queue" \
    $([ "$ghdown_eng_rc" != 3 ] \
      && grep -q 'could not read GitHub' "$TMP_DIR/select-ghdown-eng.err" \
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
printf '%s\n' 'GROUNDING_CONTEXT_SECTION' 'REPORT=REPORT_PATH' 'DECISION=DECISION_PATH' > "$TMP_DIR/sandbox-prompt.txt"
cp "$AUTOPR_DIR/_prompt_grounding.txt" "$TMP_DIR/_prompt_grounding.txt"
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
check "the shared grounding contract is expanded for every implementation template" \
    $(grep -qF 'A reply in `metadata.body` may answer in plain language' "$TMP_DIR/codex-args" \
      && ! grep -qF 'GROUNDING_CONTEXT_SECTION' "$TMP_DIR/codex-args" \
      && [ "$(grep -lFx 'GROUNDING_CONTEXT_SECTION' "$AUTOPR_DIR/_prompt_todo.txt" "$AUTOPR_DIR/_prompt_rework.txt" | wc -l | tr -d '[:space:]')" = 2 ] \
      && echo 0 || echo 1)
check "the image input path is the workspace path codex runs in, not the host attachment path" \
    $(image_path="$(grep -A1 -x -- '-i' "$TMP_DIR/codex-args" | tail -1)"; \
      [[ "$image_path" == "$TMP_DIR/sandbox-runtime/workspace/"* ]] \
      && [ -f "$image_path" ] \
      && echo 0 || echo 1)

run_bridge env > "$TMP_DIR/bridge-off.log" 2>&1
bridge_off_rc=$?
check "with no kind switches (publication helpers), neither web search nor image inputs are passed" \
    $([ "$bridge_off_rc" = 0 ] \
      && ! grep -qxF 'web_search="live"' "$TMP_DIR/codex-args" \
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
# Screenshots: the bridge admits a bounded, image-only set from one directory.
mkdir -p "$TMP_DIR/shot-bin"
cat > "$TMP_DIR/shot-bin/codex" <<'EOF'
#!/usr/bin/env bash
prompt="${!#}"
report_path="$(printf '%s\n' "$prompt" | sed -n 's/^REPORT=//p')"
decision_path="$(printf '%s\n' "$prompt" | sed -n 's/^DECISION=//p')"
mkdir -p "$(dirname "$report_path")" "$(dirname "$report_path")/artifacts"
printf '### Summary\nstub\n' > "$report_path"
printf '{"schema_version":1}\n' > "$decision_path"
shots="$(dirname "$report_path")/artifacts"
printf 'PNG' > "$shots/01-pricing.png"
printf 'PNG' > "$shots/02-docs.jpg"
# Everything below must be refused by the trusted side.
printf 'secret' > "$shots/notes.txt"
printf 'PNG' > "$shots/.hidden.png"
head -c 5000000 /dev/zero > "$shots/03-huge.png"
EOF
chmod +x "$TMP_DIR/shot-bin/codex"

PATH="$TMP_DIR/shot-bin:$PATH" AUTOPR_SANDBOX_TEST_DIRECT=1 \
AUTOPR_SANDBOX_REPO_ROOT="$SANDBOX_TEST_REPO" \
AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox-runtime" \
AUTOPR_CODEX_COLLECT_ARTIFACTS=1 \
AUTOPR_SANDBOX_ARTIFACTS_DIR="$TMP_DIR/collected-shots" \
AUTOPR_SANDBOX_MAX_ARTIFACT_BYTES=4194304 \
  "$AUTOPR_DIR/run-codex-sandboxed.sh" "$TMP_DIR/sandbox-prompt.txt" \
  "$TMP_DIR/shot-report.md" "$TMP_DIR/shot-decision.json" \
  -f "$TMP_DIR/context.json" > "$TMP_DIR/shots.log" 2>&1
shots_rc=$?
check "the bridge collects screenshots and refuses non-images, dotfiles, and oversized captures" \
    $([ "$shots_rc" = 0 ] \
      && [ -f "$TMP_DIR/collected-shots/01-pricing.png" ] \
      && [ -f "$TMP_DIR/collected-shots/02-docs.jpg" ] \
      && [ ! -e "$TMP_DIR/collected-shots/notes.txt" ] \
      && [ ! -e "$TMP_DIR/collected-shots/.hidden.png" ] \
      && [ ! -e "$TMP_DIR/collected-shots/03-huge.png" ] \
      && grep -q 'ignoring non-image artifact notes.txt' "$TMP_DIR/shots.log" \
      && grep -q 'is 5000000 bytes' "$TMP_DIR/shots.log" \
      && echo 0 || echo 1)

printf '{"outcome":"research_report"}\n' > "$TMP_DIR/screenshot-contract-decision.json"
printf '### Findings\nNo visual references yet.\n' > "$TMP_DIR/screenshot-contract-report.md"
contract_error="$(autopr_research_screenshot_contract_error true \
    "$TMP_DIR/screenshot-contract-report.md" "$TMP_DIR/screenshot-contract-decision.json" \
    "$TMP_DIR/no-contract-shots")"
check "a required screenshot contract rejects a report with no captured images" \
    $([[ "$contract_error" == *'no admitted image files'* ]] && echo 0 || echo 1)
mkdir -p "$TMP_DIR/contract-shots"
printf 'PNG' > "$TMP_DIR/contract-shots/01-evidence.png"
contract_error="$(autopr_research_screenshot_contract_error true \
    "$TMP_DIR/screenshot-contract-report.md" "$TMP_DIR/screenshot-contract-decision.json" \
    "$TMP_DIR/contract-shots")"
check "a required screenshot contract rejects unreferenced captures" \
    $([[ "$contract_error" == *'does not name: 01-evidence.png'* ]] && echo 0 || echo 1)
printf '### Findings\nSee 01-evidence.png for the source UI.\n' > "$TMP_DIR/screenshot-contract-report.md"
check "a required screenshot contract accepts an admitted image named in the report" \
    $(! autopr_research_screenshot_contract_error true \
        "$TMP_DIR/screenshot-contract-report.md" "$TMP_DIR/screenshot-contract-decision.json" \
        "$TMP_DIR/contract-shots" >/dev/null \
      && echo 0 || echo 1)

rm -rf "$TMP_DIR/collected-shots"
PATH="$TMP_DIR/shot-bin:$PATH" AUTOPR_SANDBOX_TEST_DIRECT=1 \
AUTOPR_SANDBOX_REPO_ROOT="$SANDBOX_TEST_REPO" \
AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox-runtime" \
AUTOPR_SANDBOX_ARTIFACTS_DIR="$TMP_DIR/collected-shots" \
  "$AUTOPR_DIR/run-codex-sandboxed.sh" "$TMP_DIR/sandbox-prompt.txt" \
  "$TMP_DIR/shot-report-off.md" "$TMP_DIR/shot-decision-off.json" \
  -f "$TMP_DIR/context.json" > "$TMP_DIR/shots-off.log" 2>&1
shots_off_rc=$?
check "a run without the browse grant brings back no screenshots at all" \
    $([ "$shots_off_rc" = 0 ] && [ ! -e "$TMP_DIR/collected-shots" ] && echo 0 || echo 1)

# The capture helper's own refusals — the model never reaches an internal
# address even through a hostname that resolves to one.
capture_py="$AUTOPR_DIR/browse-capture.py"
check "the capture helper refuses non-http, credentialed, and internal URLs" \
    $(python3 "$capture_py" --url "file:///etc/passwd" --label x >/dev/null 2>&1; [ "$?" = 2 ] \
      && { python3 "$capture_py" --url "https://user:pw@example.com" --label x >/dev/null 2>&1; [ "$?" = 2 ]; } \
      && { python3 "$capture_py" --url "http://localhost:8001/admin" --label x >/dev/null 2>&1; [ "$?" = 2 ]; } \
      && { python3 "$capture_py" --url "http://127.0.0.1/" --label x >/dev/null 2>&1; [ "$?" = 2 ]; } \
      && { python3 "$capture_py" --url "http://host.docker.internal:5432/" --label x >/dev/null 2>&1; [ "$?" = 2 ]; } \
      && echo 0 || echo 1)

check "the browser paragraph lives in its own fragment, keyed into the prompt by a placeholder" \
    $(grep -qF 'browse-capture.py' "$AUTOPR_DIR/_prompt_research_browse.txt" \
      && grep -q 'Do not try to drive a browser any other way' "$AUTOPR_DIR/_prompt_research_browse.txt" \
      && grep -q 'hold the incomplete report' "$AUTOPR_DIR/_prompt_research_browse.txt" \
      && grep -qx 'BROWSE_TOOL_SECTION' "$AUTOPR_DIR/_prompt_research.txt" \
      && ! grep -qF 'browse-capture.py' "$AUTOPR_DIR/_prompt_research.txt" \
      && grep -qF 'required_deliverables.screenshots' "$AUTOPR_DIR/_prompt_research.txt" \
      && grep -qF 'required_screenshots_missing' "$AUTOPR_DIR/investigate.sh" \
      && echo 0 || echo 1)

# The same template serves every research run and nothing else reaches the
# container to say whether screenshots will be collected — so the prompt itself
# must tell the truth about the browser per run.
printf '%s\n' 'REPORT=REPORT_PATH' 'DECISION=DECISION_PATH' 'BROWSE_TOOL_SECTION' 'tail' > "$TMP_DIR/browse-prompt.txt"
cp "$AUTOPR_DIR/_prompt_research_browse.txt" "$TMP_DIR/_prompt_research_browse.txt"
run_browse_prompt() {
    PATH="$TMP_DIR/bin:$PATH" AUTOPR_SANDBOX_TEST_DIRECT=1 \
    AUTOPR_SANDBOX_REPO_ROOT="$SANDBOX_TEST_REPO" \
    AUTOPR_SANDBOX_RUNTIME_ROOT="$TMP_DIR/sandbox-runtime" \
    AUTOPR_CODEX_BACKOFF_FILE="$TMP_DIR/backoff.json" \
    RESEARCH_TEST_CODEX_ARGS="$TMP_DIR/codex-args" \
    "$@" "$AUTOPR_DIR/run-codex-sandboxed.sh" "$TMP_DIR/browse-prompt.txt" \
        "$TMP_DIR/bridge-report.md" "$TMP_DIR/bridge-decision.json" -f "$TMP_DIR/context.json"
}
run_browse_prompt env AUTOPR_CODEX_COLLECT_ARTIFACTS=1 AUTOPR_SANDBOX_ARTIFACTS_DIR="$TMP_DIR/prompt-shots" \
    > "$TMP_DIR/browse-prompt-on.log" 2>&1
check "with the browse grant the model is told about the capture command" \
    $(grep -q 'browse-capture.py' "$TMP_DIR/codex-args" \
      && ! grep -q 'BROWSE_TOOL_SECTION' "$TMP_DIR/codex-args" \
      && grep -qx 'tail' "$TMP_DIR/codex-args" \
      && echo 0 || echo 1)
run_browse_prompt env > "$TMP_DIR/browse-prompt-off.log" 2>&1
check "without the browse grant the model is told there is no browser, not handed a tool whose output is dropped" \
    $(! grep -q 'server/venv/bin/python scripts/kanban-autopr/browse-capture.py' "$TMP_DIR/codex-args" \
      && grep -q 'This board is not granted browsing' "$TMP_DIR/codex-args" \
      && ! grep -q 'BROWSE_TOOL_SECTION' "$TMP_DIR/codex-args" \
      && echo 0 || echo 1)

# A revision round keeps the newest prior report but drops the publisher's own
# screenshots, so the attachment budget goes to human files and to this round's
# evidence. That report names each screenshot by filename and treats the images
# as the evidence for its claims -- so the ones held back have to be named, or
# the model revises prose citing pictures it cannot see and cannot know were
# withheld rather than simply absent.
cat > "$TMP_DIR/withheld-files.json" <<'EOF'
[{"filename":"research-report-aaaa0000-r1.md","created_at":"2026-09-01T00:00:00Z"},
 {"filename":"research-aaaa0000-r1-01-pricing.png","created_at":"2026-09-01T00:00:01Z"},
 {"filename":"research-report-aaaa0000-r2.md","created_at":"2026-09-02T00:00:00Z"},
 {"filename":"research-aaaa0000-r2-01-latency.png","created_at":"2026-09-02T00:00:01Z"},
 {"filename":"customer-spreadsheet.xlsx","created_at":"2026-09-03T00:00:00Z"}]
EOF
withheld="$(jq -c --arg id8 aaaa0000 '
    def mine: ((.filename // "") | test("^research-(report-)?" + $id8 + "-r[0-9]+"));
    def prior_report: ((.filename // "") | test("^research-report-" + $id8 + "-r[0-9]+\\.md$"));
    ([.[] | select(prior_report)] | sort_by(.created_at // "") | last) as $keep
    | [.[] | select(mine and (. != $keep)) | (.filename // empty)]' \
    "$TMP_DIR/withheld-files.json")"
check "the screenshots a revision round holds back are named for the model" \
    $(printf '%s' "$withheld" | jq -e '
        (index("research-aaaa0000-r2-01-latency.png") != null)
        and (index("research-aaaa0000-r1-01-pricing.png") != null)
        and (index("research-report-aaaa0000-r2.md") == null)
        and (index("customer-spreadsheet.xlsx") == null)' >/dev/null \
      && grep -qF 'withheld_attachments' "$AUTOPR_DIR/investigate.sh" \
      && grep -qF 'withheld_attachments' "$AUTOPR_DIR/_prompt_research.txt" \
      && echo 0 || echo 1)

################################################################################
# decision.sh normalize-research
cat > "$TMP_DIR/research-raw.json" <<'EOF'
{"schema_version":1,"outcome":"research_report","card_note":"Lambda fits the worker tier; keep the API on containers.","summary":"Lambda suits bursty, stateless jobs. Matcha's Celery worker tier is the candidate; the FastAPI app is not.","sources":[{"title":"AWS Lambda pricing","url":"https://aws.example.com/lambda/pricing"},{"title":"Lambda cold starts","url":"https://aws.example.com/lambda/cold-starts"}],"confidence":{"score":82,"reason":"primary vendor docs plus the worker code"},"questions":[],"staged_actions":[{"kind":"email","to":"account-team@aws.example.com","subject":"Lambda pricing for a small workload","body":"Hi — we run ~2k jobs/day…","why":"Confirms the committed-use discount before we plan the move."}]}
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

# `to` is the To: header the send path uses verbatim, so a name there is a
# proposal that can only fail after a human has already approved it.
jq '.staged_actions[0].to = "AWS account team"' "$TMP_DIR/research-raw.json" > "$TMP_DIR/research-nameaddr.json"
check "an email proposal addressed to a name instead of an address is rejected" \
    $(! "$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-nameaddr.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

jq '.staged_actions[0] |= (.kind = "contact" | .to = "AWS account team")' "$TMP_DIR/research-raw.json" \
    > "$TMP_DIR/research-contact.json"
check "a contact proposal may name a person, because nothing sends it" \
    $("$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-contact.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

# publish-research.sh trusts `kind == "research"` as proof a decision went
# through the normalizer. That is only worth anything if the model cannot
# write the marker itself.
jq '. + {kind: "research"}' "$TMP_DIR/research-raw.json" > "$TMP_DIR/research-forged.json"
check "a raw decision that forges the validated-research marker is rejected" \
    $(! "$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-forged.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

jq '. + {autopr_directives: ["draft_pr"]}' "$TMP_DIR/research-raw.json" > "$TMP_DIR/research-extrakey.json"
check "an unknown top-level key never rides through normalization" \
    $(! "$AUTOPR_DIR/decision.sh" normalize-research "$TMP_DIR/research-extrakey.json" "$TMP_DIR/x.json" >/dev/null 2>&1 && echo 0 || echo 1)

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
      name="$(basename "$src")"
      case "$name" in
        *.md) cp "$src" "$RESEARCH_TEST_UPLOADED"; printf '%s\n' "$name" > "$RESEARCH_TEST_UPLOADED_NAME" ;;
      esac
      respond "{\"id\":\"file-$name\",\"filename\":\"$name\"}"
    else
      respond "${RESEARCH_TEST_EXISTING_FILES:-[]}"
    fi ;;
  */autopr/staged-actions)
    printf '%s' "$payload" > "$RESEARCH_TEST_STAGED"
    if [ "${RESEARCH_TEST_STAGE_STATUS:-201}" != 201 ]; then
      [ -z "$output_file" ] || printf '{"detail":"board lacks outreach"}' > "$output_file"
      printf '%s' "${RESEARCH_TEST_STAGE_STATUS}"
      exit 0
    fi
    respond '{"ok":true,"staged":1,"action_ids":["act-1"]}' ;;
  */activity) printf '%s' "$payload" > "$RESEARCH_TEST_ACTIVITY"; respond '{"ok":true}' ;;
  */autopr/context-request) printf '%s' "$payload" > "$RESEARCH_TEST_CONTEXT_REQUEST"; respond '{"ok":true}' ;;
  */autopr/result-notification) printf '%s' "$payload" > "$RESEARCH_TEST_RESULT_NOTIFICATION"; respond '{"ok":true}' ;;
  */history)
    if [ "${RESEARCH_TEST_HISTORY_STATUS:-200}" != 200 ]; then
      [ -z "$output_file" ] || printf '{"detail":"boom"}' > "$output_file"
      printf '%s' "${RESEARCH_TEST_HISTORY_STATUS}"
      exit 0
    fi
    respond "${RESEARCH_TEST_EXISTING_HISTORY:-[]}" ;;
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
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Research how AWS Lambda works","category":"research","autopr_capabilities":["research","outreach"],"mode":"research","autopr_reconsideration_event_id":"eeeeeeee-0000-4000-8000-000000000001","progress_note":"🤖 AUTO SETUP · READY FOR REVIEW · build 800 · prod 1111111 · 🟡 C50 · note: earlier round\nkeep this human line","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
EOF

run_publisher() {
    local card="$1" decision="$2"
    : > "$RESEARCH_TEST_CURL_LOG"
    rm -f "$RESEARCH_TEST_ACTIVITY" "$RESEARCH_TEST_CARD_PATCH" "$RESEARCH_TEST_CONTEXT_REQUEST" \
        "$RESEARCH_TEST_RESULT_NOTIFICATION" "$RESEARCH_TEST_UPLOADED" "$RESEARCH_TEST_UPLOADED_NAME" \
        "$RESEARCH_TEST_GH_LOG" "$RESEARCH_TEST_STAGED"
    PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
        "$AUTOPR_DIR/publish-research.sh" "$card" "$TMP_DIR/report.md" "$decision"
}
export RESEARCH_TEST_CURL_LOG="$TMP_DIR/curl.log" RESEARCH_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    RESEARCH_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" RESEARCH_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    RESEARCH_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    RESEARCH_TEST_UPLOADED="$TMP_DIR/uploaded.md" RESEARCH_TEST_UPLOADED_NAME="$TMP_DIR/uploaded-name" \
    RESEARCH_TEST_STAGED="$TMP_DIR/staged-actions.json"
export RESEARCH_TEST_EXISTING_FILES='[{"id":"file-old","filename":"research-report-aaaa0000-r1.md"},{"id":"file-shot","filename":"shot.png"}]'
# Round 1 was announced on the card, so it is a finished round and this pass
# writes round 2 rather than mistaking it for a crashed upload.
export RESEARCH_TEST_EXISTING_HISTORY='[{"id":"h0","event_type":"activity","metadata":{"kind":"note","body":"Report attached: research-report-aaaa0000-r1.md"}}]'

run_publisher "$TMP_DIR/card.json" "$TMP_DIR/research-decision.json" > "$TMP_DIR/publish.log" 2>&1
publish_rc=$?
[ "$publish_rc" = 0 ] || sed -n '1,40p' "$TMP_DIR/publish.log"
check "the report is uploaded to the task as the next numbered round" \
    $([ "$publish_rc" = 0 ] \
      && grep -q 'POST https://example.invalid/api/matcha-work/projects/8b924347-d6e4-4000-8e7d-ca8f46f76fba/tasks/aaaa0000-0000-4000-8000-000000000001/files' "$RESEARCH_TEST_CURL_LOG" \
      && [ "$(cat "$RESEARCH_TEST_UPLOADED_NAME")" = research-report-aaaa0000-r2.md ] \
      && jq -e '.attachment_ids == ["file-research-report-aaaa0000-r2.md"]' "$RESEARCH_TEST_ACTIVITY" >/dev/null \
      && echo 0 || echo 1)
check "the uploaded file carries a trusted provenance header, the model report, and the unsent staged actions" \
    $(head -1 "$RESEARCH_TEST_UPLOADED" | grep -q '^_AutoPR research · .* · model gpt-5.6-luna · round 2 · 2 source(s)_' \
      && grep -q '^### Findings' "$RESEARCH_TEST_UPLOADED" \
      && grep -q '^### Proposed actions (not sent)' "$RESEARCH_TEST_UPLOADED" \
      && grep -q 'NOT sent; each needs your approval' "$RESEARCH_TEST_UPLOADED" \
      && grep -q '\[email\] to: account-team@aws.example.com' "$RESEARCH_TEST_UPLOADED" \
      && echo 0 || echo 1)
check "a summary note is posted with the report attached and threaded under the additional-context event" \
    $(jq -e '.kind == "note" and .attachment_ids == ["file-research-report-aaaa0000-r2.md"]
             and (.body | startswith("Lambda suits bursty"))
             and (.body | contains("Report attached: research-report-aaaa0000-r2.md"))
             and (.body | contains("NOT sent"))
             and .reply_to == "eeeeeeee-0000-4000-8000-000000000001"' \
        "$RESEARCH_TEST_ACTIVITY" >/dev/null && echo 0 || echo 1)
check "the card moves to Review with a structured note that replaces the prior round's prefix and keeps the human line" \
    $(jq -e '.board_column == "review"
             and (.progress_note | startswith("🤖 AUTO SETUP · READY FOR REVIEW · build 850 · prod 68a70f4 · 🟢 C82 · note: Lambda fits the worker tier; keep the API on containers."))
             and (.progress_note | contains("keep this human line"))
             and (.progress_note | contains("C50") | not)' \
        "$RESEARCH_TEST_CARD_PATCH" >/dev/null && echo 0 || echo 1)
check "the additional-context author gets a decision-bound result notification" \
    $(jq -e '.reconsideration_event_id == "eeeeeeee-0000-4000-8000-000000000001"
             and (.message | contains("round 2"))
             and (.expected_progress_note | startswith("🤖 AUTO SETUP · READY FOR REVIEW"))' \
        "$RESEARCH_TEST_RESULT_NOTIFICATION" >/dev/null && echo 0 || echo 1)
check "an outreach-granted board gets the proposals posted for approval, keyed on the report, with nothing sent" \
  $(jq -e '(.actions | length) == 1
           and .actions[0].kind == "email"
           and .actions[0].to == "account-team@aws.example.com"
           and (.actions[0].body | length > 0)
           and .run_key == "file-research-report-aaaa0000-r2.md"' "$RESEARCH_TEST_STAGED" >/dev/null \
    && jq -e '.body | contains("waiting for your approval")' "$RESEARCH_TEST_ACTIVITY" >/dev/null \
    && grep -q 'POST https://example.invalid/api/matcha-work/projects/8b924347-d6e4-4000-8e7d-ca8f46f76fba/tasks/aaaa0000-0000-4000-8000-000000000001/autopr/staged-actions' "$RESEARCH_TEST_CURL_LOG" \
    && echo 0 || echo 1)

# Screenshots attach to the same ticket and the same note as the report, so the
# evidence sits beside the claim it supports.
mkdir -p "$TMP_DIR/publish-shots"
printf 'PNG' > "$TMP_DIR/publish-shots/01-pricing.png"
printf 'PNG' > "$TMP_DIR/publish-shots/02-docs.png"
run_publisher_with_shots() {
    : > "$RESEARCH_TEST_CURL_LOG"
    rm -f "$RESEARCH_TEST_ACTIVITY" "$RESEARCH_TEST_CARD_PATCH"
    PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
        "$AUTOPR_DIR/publish-research.sh" "$TMP_DIR/card.json" "$TMP_DIR/report.md" \
        "$TMP_DIR/research-decision.json" "$TMP_DIR/publish-shots"
}
run_publisher_with_shots > "$TMP_DIR/publish-shots.log" 2>&1
shots_publish_rc=$?
check "screenshots are attached to the same note as the report" \
  $([ "$shots_publish_rc" = 0 ] \
    && [ "$(grep -c 'POST https://example.invalid/api/matcha-work/projects/.*/files' "$RESEARCH_TEST_CURL_LOG")" = 3 ] \
    && jq -e '(.attachment_ids | length) == 3
              and (.attachment_ids | unique | length) == 3
              and (.attachment_ids[0] | startswith("file-research-report-"))
              and ([.attachment_ids[] | select(endswith(".png"))] | length) == 2
              and (.body | contains("Screenshots attached: 2"))' \
        "$RESEARCH_TEST_ACTIVITY" >/dev/null \
    && echo 0 || echo 1)

check "proposals are staged before the note announces them and before the card moves" \
  $(awk '/autopr\/staged-actions/ {s=NR} /\/activity$/ {n=NR} /^PATCH .*\/tasks\/aaaa0000-0000-4000-8000-000000000001$/ {m=NR} END {exit !(s && n && m && s < n && n < m)}' \
        "$RESEARCH_TEST_CURL_LOG" && echo 0 || echo 1)

check "the research publisher never calls gh" \
    $([ ! -s "$RESEARCH_TEST_GH_LOG" ] && echo 0 || echo 1)
check "no context request is posted for a delivered report" \
    $([ ! -e "$RESEARCH_TEST_CONTEXT_REQUEST" ] && echo 0 || echo 1)

# Without the outreach grant the same proposals stay report-only: no POST, no
# approve buttons, and the report says why rather than dropping them silently.
jq '.autopr_capabilities = ["research"]' "$TMP_DIR/card.json" > "$TMP_DIR/card-noreach.json"
run_publisher "$TMP_DIR/card-noreach.json" "$TMP_DIR/research-decision.json" > "$TMP_DIR/publish-noreach.log" 2>&1
noreach_rc=$?
check "a board without the outreach grant stages nothing and says so in the report" \
  $([ "$noreach_rc" = 0 ] \
    && [ ! -e "$RESEARCH_TEST_STAGED" ] \
    && ! grep -q 'autopr/staged-actions' "$RESEARCH_TEST_CURL_LOG" \
    && grep -q 'not granted outreach' "$RESEARCH_TEST_UPLOADED" \
    && grep -q '\[email\] to: account-team@aws.example.com' "$RESEARCH_TEST_UPLOADED" \
    && echo 0 || echo 1)

# A grant revoked between selection and publication answers 409. The report is
# the deliverable; losing the approve buttons must not discard the run.
RESEARCH_TEST_STAGE_STATUS=409 run_publisher "$TMP_DIR/card.json" "$TMP_DIR/research-decision.json" \
  > "$TMP_DIR/publish-stage409.log" 2>&1
stage409_rc=$?
check "a staging refusal is reported on the card note and never discards a completed report" \
  $([ "$stage409_rc" = 0 ] \
    && grep -q 'could not stage' "$TMP_DIR/publish-stage409.log" \
    && jq -e '.body | contains("could not be staged")' "$RESEARCH_TEST_ACTIVITY" >/dev/null \
    && jq -e '.board_column == "review"' "$RESEARCH_TEST_CARD_PATCH" >/dev/null \
    && echo 0 || echo 1)

# A publication that died after the upload is retried by the NEXT scheduled
# pass -- a fresh workflow run on a fresh runner, which is the only retry path
# that exists. Nothing derived from a run (its start time, its RUNNER_TEMP)
# survives that, so the key is the card: the newest report with no
# "Report attached:" line in the discussion was uploaded by a pass that died
# before announcing it. No AUTOPR_RUN_STARTED_AT is set here, deliberately --
# that is what the previous key needed and could not have.
export RESEARCH_TEST_EXISTING_FILES='[{"id":"file-old","filename":"research-report-aaaa0000-r1.md","created_at":"2026-09-01T00:00:00+00:00"},{"id":"file-mine","filename":"research-report-aaaa0000-r2.md","created_at":"2026-09-08T10:00:05.123456+00:00"},{"id":"file-shot-mine","filename":"research-aaaa0000-r2-01-pricing.png","created_at":"2026-09-08T10:00:06+00:00"}]'
export RESEARCH_TEST_EXISTING_HISTORY='[{"id":"h0","event_type":"activity","metadata":{"kind":"note","body":"Report attached: research-report-aaaa0000-r1.md"}}]'
: > "$RESEARCH_TEST_CURL_LOG"
rm -f "$RESEARCH_TEST_ACTIVITY" "$RESEARCH_TEST_CARD_PATCH" "$RESEARCH_TEST_UPLOADED" "$RESEARCH_TEST_STAGED"
PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
    "$AUTOPR_DIR/publish-research.sh" "$TMP_DIR/card.json" "$TMP_DIR/report.md" \
    "$TMP_DIR/research-decision.json" "$TMP_DIR/publish-shots" > "$TMP_DIR/publish-retry.log" 2>&1
retry_rc=$?
[ "$retry_rc" = 0 ] || sed -n '1,40p' "$TMP_DIR/publish-retry.log"
check "a later pass reuses the orphaned report and screenshot, uploads only what is missing, and announces it once" \
  $([ "$retry_rc" = 0 ] \
    && [ ! -e "$RESEARCH_TEST_UPLOADED" ] \
    && [ "$(grep -c 'POST https://example.invalid/api/matcha-work/projects/.*/files' "$RESEARCH_TEST_CURL_LOG")" = 1 ] \
    && jq -e '.attachment_ids == ["file-mine", "file-shot-mine", "file-research-aaaa0000-r2-02-docs.png"]
             and (.body | contains("Report attached: research-report-aaaa0000-r2.md"))' \
        "$RESEARCH_TEST_ACTIVITY" >/dev/null \
    && jq -e '.run_key == "file-mine"' "$RESEARCH_TEST_STAGED" >/dev/null \
    && jq -e '.board_column == "review"' "$RESEARCH_TEST_CARD_PATCH" >/dev/null \
    && grep -q 'reusing it' "$TMP_DIR/publish-retry.log" \
    && echo 0 || echo 1)

# The crash-after-note case: the report is announced, so it is a finished
# round and the retry writes the next one. That is the documented residual
# gap (one extra round), and it must never read as an orphan -- the same
# shape is also a person dragging a reviewed card back to Todo for a fresh
# run, where reusing the announced file would discard the new report.
export RESEARCH_TEST_EXISTING_FILES='[{"id":"file-old","filename":"research-report-aaaa0000-r1.md","created_at":"2026-09-01T00:00:00+00:00"}]'
export RESEARCH_TEST_EXISTING_HISTORY='[{"id":"h1","event_type":"activity","metadata":{"kind":"note","body":"Report attached: research-report-aaaa0000-r1.md"}}]'
jq '.board_column = "todo"' "$TMP_DIR/card.json" > "$TMP_DIR/card-todo.json"
run_publisher "$TMP_DIR/card-todo.json" "$TMP_DIR/research-decision.json" \
    > "$TMP_DIR/publish-dragback.log" 2>&1
dragback_rc=$?
check "an announced report on a Todo card is a finished round, so a fresh run writes the next one" \
  $([ "$dragback_rc" = 0 ] \
    && [ "$(cat "$RESEARCH_TEST_UPLOADED_NAME" 2>/dev/null)" = "research-report-aaaa0000-r2.md" ] \
    && jq -e '.body | contains("Report attached: research-report-aaaa0000-r2.md")' \
        "$RESEARCH_TEST_ACTIVITY" >/dev/null \
    && ! grep -q 'reusing it' "$TMP_DIR/publish-dragback.log" \
    && echo 0 || echo 1)

# The mirror image: a human read a finished report and sent the card back, so
# the newest report is a completed round, not an orphan. Reusing it there would
# silently overwrite the round the reviewer just commented on.
jq '.board_column = "changes_requested" | .review_note = "Compare cold-start cost too"' \
    "$TMP_DIR/card.json" > "$TMP_DIR/card-revision.json"
export RESEARCH_TEST_EXISTING_FILES='[{"id":"file-old","filename":"research-report-aaaa0000-r1.md","created_at":"2026-09-01T00:00:00+00:00"}]'
export RESEARCH_TEST_EXISTING_HISTORY='[{"id":"h1","event_type":"activity","metadata":{"kind":"note","body":"Report attached: research-report-aaaa0000-r1.md"}}]'
run_publisher "$TMP_DIR/card-revision.json" "$TMP_DIR/research-decision.json" \
    > "$TMP_DIR/publish-revision.log" 2>&1
revision_rc=$?
check "a send-back starts the next round instead of reusing the report it is revising" \
  $([ "$revision_rc" = 0 ] \
    && [ "$(cat "$RESEARCH_TEST_UPLOADED_NAME" 2>/dev/null)" = "research-report-aaaa0000-r2.md" ] \
    && jq -e '.body | contains("Report attached: research-report-aaaa0000-r2.md")' \
        "$RESEARCH_TEST_ACTIVITY" >/dev/null \
    && echo 0 || echo 1)

# The discussion is the key now, so publishing without it would mean guessing
# between a crashed pass and a finished one -- a duplicate report either way.
export RESEARCH_TEST_EXISTING_FILES='[]'
unset RESEARCH_TEST_EXISTING_HISTORY
RESEARCH_TEST_HISTORY_STATUS=500 run_publisher "$TMP_DIR/card.json" "$TMP_DIR/research-decision.json" \
    > "$TMP_DIR/publish-nohistory.log" 2>&1
nohistory_rc=$?
check "an unreadable discussion stops the publication instead of guessing" \
  $([ "$nohistory_rc" != 0 ] \
    && [ ! -e "$RESEARCH_TEST_UPLOADED" ] \
    && [ ! -e "$RESEARCH_TEST_CARD_PATCH" ] \
    && grep -q 'not publishing blind' "$TMP_DIR/publish-nohistory.log" \
    && echo 0 || echo 1)

unset RESEARCH_TEST_EXISTING_HISTORY

# A report does not depend on which build is live. Missing production context
# (an SSH or ECR hiccup on the runner) must not throw the run away.
export RESEARCH_TEST_EXISTING_FILES='[]'
jq 'del(.production)' "$TMP_DIR/card.json" > "$TMP_DIR/card-noprod.json"
jq '.staged_actions = []' "$TMP_DIR/research-decision.json" > "$TMP_DIR/research-decision-plain.json"
run_publisher "$TMP_DIR/card-noprod.json" "$TMP_DIR/research-decision-plain.json" > "$TMP_DIR/publish-noprod.log" 2>&1 \
    || true
check "missing production context publishes the report without a build label instead of dying" \
  $(grep -q 'production context is incomplete' "$TMP_DIR/publish-noprod.log" \
    && jq -e '.board_column == "review"
              and (.progress_note | startswith("🤖 AUTO SETUP · READY FOR REVIEW · 🟢 C82 · note: "))' \
        "$RESEARCH_TEST_CARD_PATCH" >/dev/null \
    && echo 0 || echo 1)

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
      && jq -e '.progress_note == "🤖 AUTO SETUP · READY FOR REVIEW · build 850 · prod 68a70f4 · 🟢 C82 · note: Lambda fits the worker tier; keep the API on containers."' "$RESEARCH_TEST_CARD_PATCH" >/dev/null \
      && echo 0 || echo 1)

# Too vague: park the card with the exact question form Espresso parses.
run_publisher "$TMP_DIR/card-fresh.json" "$TMP_DIR/clarify-decision.json" > "$TMP_DIR/publish-clarify.log" 2>&1
clarify_rc=$?
[ "$clarify_rc" = 0 ] || sed -n '1,40p' "$TMP_DIR/publish-clarify.log"
check "a needs_clarification result parks the card in Changes Requested with a durable no-spec marker" \
    $([ "$clarify_rc" = 0 ] \
      && jq -e '.board_column == "changes_requested"
                # 🔴, not 🟡: normalize-research already computed the band, and a
                # card face that marks every report amber says nothing about
                # which ones the model itself called thin.
                and (.progress_note | startswith("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build 850 · prod 68a70f4 · 🔴 C20 · [autopr:no-spec "))
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
# The workflow keys on the registry's `outcome`, never on a mode name: the next
# artifact kind must not fall through into branch creation or publish.sh.
check "workflow gates branch creation, coverage, verify, publication copy, and publish.sh on the registry outcome" \
    $(grep -qF "if: steps.select.outputs.skip == 'false' && steps.select.outputs.outcome != 'artifact'" "$workflow" \
      && [ "$(grep -c "steps.select.outputs.outcome != 'artifact'" "$workflow")" -ge 6 ] \
      && ! grep -q "steps.select.outputs.mode [!=]= 'research'" "$workflow" \
      && grep -qF 'echo "outcome=$(jq -r' "$workflow" \
      && echo 0 || echo 1)
check "select.sh stamps the registry outcome on the card it picks" \
    $([ "$(jq -r '.outcome' "$TMP_DIR/select-todo.json" 2>/dev/null)" = artifact ] \
      && [ "$(jq -r '.outcome' "$TMP_DIR/select-eng.json" 2>/dev/null)" = pull_request ] \
      && echo 0 || echo 1)
check "workflow publishes research from the trusted control root without a GitHub token" \
    $(grep -qF 'name: Publish research report' "$workflow" \
      && grep -qF '"$AUTOPR_CONTROL_ROOT/kanban-autopr/publish-research.sh"' "$workflow" \
      && grep -qF "steps.investigate.outcome == 'success' && steps.investigate.outputs.paused != 'true' && steps.select.outputs.outcome == 'artifact'" "$workflow" \
      && ! grep -qF 'AUTOPR_RUN_STARTED_AT' "$workflow" \
      && ! awk '/name: Publish research report/,/name: Cleanup/' "$workflow" | grep -qE '^[[:space:]]*GH_TOKEN:' \
      && echo 0 || echo 1)
check "ci syntax-checks the research publisher and the self-audit runs this suite" \
    $(grep -qF 'scripts/kanban-autopr/publish-research.sh' "$REPO_ROOT/.github/workflows/ci.yml" \
      && grep -qF 'test_kanban_autopr_research.sh' "$REPO_ROOT/scripts/autopr-self-audit/audit.sh" \
      && echo 0 || echo 1)
################################################################################
# An ungranted board with an explicit "Run research now": the request is still
# consumed (an unconsumed one re-dispatches every minute forever), but the card
# has to say why, or the operator sees only the button come back and presses it
# again forever — Espresso's run button knows nothing about grants.
jq '.[0] |= (.autopr_capabilities = [] | .autopr_run_requested_at = "2026-09-08T02:00:00Z")' \
    "$TMP_DIR/cards-todo.json" > "$TMP_DIR/cards-ungranted-run.json"
: > "$RESEARCH_TEST_CURL_LOG"
rm -f "$RESEARCH_TEST_ACTIVITY"
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
MATCHA_AUTOPR_ENV="$TMP_DIR/env" \
AUTOPR_BOT_PRS_FILE="$TMP_DIR/bot-prs.json" AUTOPR_CACHE_DIR="$TMP_DIR/cache-ungranted" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/cards-ungranted-run.json" \
    > "$TMP_DIR/select-ungranted-run.json" 2>"$TMP_DIR/select-ungranted-run.err"
ungranted_run_rc=$?
check "an explicit run on an ungranted board is answered on the card, not silently eaten" \
    $([ "$ungranted_run_rc" = 3 ] \
      && grep -q 'autopr/run-defer' "$RESEARCH_TEST_CURL_LOG" \
      && jq -e '.kind == "note" and (.body | contains("research")) and (.body | contains("Admin"))' \
            "$RESEARCH_TEST_ACTIVITY" >/dev/null \
      && echo 0 || echo 1)

# The kind's research grant is present here; only the deliverable-specific
# browser grant is missing. The same visible response must name the actual
# capability that blocked this particular card.
jq '.[0].autopr_run_requested_at = "2026-09-08T02:00:00Z"' \
    "$TMP_DIR/cards-shots-no-browse.json" > "$TMP_DIR/cards-shots-no-browse-run.json"
: > "$RESEARCH_TEST_CURL_LOG"
rm -f "$RESEARCH_TEST_ACTIVITY"
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
MATCHA_AUTOPR_ENV="$TMP_DIR/env" \
AUTOPR_BOT_PRS_FILE="$TMP_DIR/bot-prs.json" AUTOPR_CACHE_DIR="$TMP_DIR/cache-no-browse" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/cards-shots-no-browse-run.json" \
    > "$TMP_DIR/select-shots-no-browse-run.json" 2>"$TMP_DIR/select-shots-no-browse-run.err"
shots_no_browse_run_rc=$?
check "an explicit screenshot run names the missing browse grant on the card" \
    $([ "$shots_no_browse_run_rc" = 3 ] \
      && grep -q 'autopr/run-defer' "$RESEARCH_TEST_CURL_LOG" \
      && jq -e '.kind == "note" and (.body | contains("`browse` capability"))' \
            "$RESEARCH_TEST_ACTIVITY" >/dev/null \
      && echo 0 || echo 1)

# No press, no note: a cron pass over the same ungranted card must stay silent
# rather than posting the same paragraph every twenty minutes.
: > "$RESEARCH_TEST_CURL_LOG"
rm -f "$RESEARCH_TEST_ACTIVITY"
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
MATCHA_AUTOPR_ENV="$TMP_DIR/env" \
AUTOPR_BOT_PRS_FILE="$TMP_DIR/bot-prs.json" AUTOPR_CACHE_DIR="$TMP_DIR/cache-ungranted2" \
    "$AUTOPR_DIR/select.sh" "$TMP_DIR/cards-ungranted.json" \
    > "$TMP_DIR/select-ungranted-quiet.json" 2>"$TMP_DIR/select-ungranted-quiet.err"
quiet_rc=$?
check "a scheduled pass over an ungranted card posts nothing" \
    $([ "$quiet_rc" = 3 ] && [ ! -f "$RESEARCH_TEST_ACTIVITY" ] && echo 0 || echo 1)

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
