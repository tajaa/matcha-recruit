#!/usr/bin/env bash
# Email cards: the Kanban lane's second artifact kind. Exercises the registry
# row, the sandbox switches it does (and does not) get, the prompt's no-send
# and reply-shape rules, the email decision validator, the publisher, and the
# workflow wiring — with Matcha and GitHub stubbed on PATH. All addresses are
# RFC 2606 reserved (example.com / .org / .net / .invalid).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOPR_DIR="$REPO_ROOT/scripts/kanban-autopr"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/runner" "$TMP_DIR/cache"

PASS=0
FAIL=0
check() {
    local desc="$1" ok="${2:-1}"
    if [ "$ok" = "0" ]; then
        echo "PASS: $desc"; PASS=$((PASS + 1))
    else
        echo "FAIL: $desc"; FAIL=$((FAIL + 1))
    fi
}

workflow="$REPO_ROOT/.github/workflows/kanban-autopr.yml"
ci_workflow="$REPO_ROOT/.github/workflows/ci.yml"
prompt="$AUTOPR_DIR/_prompt_email.txt"

################################################################################
# Kind registry
source "$AUTOPR_DIR/lib.sh"
check "the kind registry maps the email category to its own artifact row" \
    $([ "$(autopr_kind_for_category email)" = email ] \
      && [ "$(autopr_kind_for_category research)" = research ] \
      && [ "$(autopr_kind_for_category bug)" = investigate ] \
      && [ "$(autopr_kind_field email outcome)" = artifact ] \
      && [ "$(autopr_kind_field email prompt)" = _prompt_email.txt ] \
      && [ -f "$AUTOPR_DIR/$(autopr_kind_field email prompt)" ] \
      && [ "$(autopr_kind_field email model)" = gpt-5.6-luna ] \
      && [ "$(autopr_kind_field email effort)" = medium ] \
      && [ "$(autopr_kind_field email decision)" = normalize-email ] \
      && [ "$(autopr_kind_field email publisher)" = publish-email.sh ] \
      && [ -x "$AUTOPR_DIR/$(autopr_kind_field email publisher)" ] \
      && [ "$(autopr_kind_field email capability)" = email ] \
      && [ "$(autopr_kind_field email headings)" = "$(printf '### Summary\n### Emails reviewed\n### Recommended actions\n### Confidence\n')" ] \
      && ! autopr_kind_field email bogus >/dev/null 2>&1 \
      && echo 0 || echo 1)

check "email sandbox switches enforce an empty patch and turn on neither web search nor image inputs" \
    $(switches="$(autopr_kind_field email sandbox)"; \
      [[ "$switches" == *AUTOPR_CODEX_REQUIRE_EMPTY_PATCH=1* ]] \
      && [[ "$switches" != *AUTOPR_CODEX_WEB_SEARCH* ]] \
      && [[ "$switches" != *AUTOPR_CODEX_IMAGE_INPUTS* ]] \
      && [[ "$switches" != *AUTOPR_CODEX_COLLECT_ARTIFACTS* ]] \
      && echo 0 || echo 1)

# investigate.sh used to hand EVERY artifact kind live web search, and the
# browser on a `browse` board. Run its real grant block, lifted out of the
# script, for each kind: the registry row decides, not the outcome.
grant_block="$(awk '/^BROWSE_GRANTED=false$/ { on = 1 } on { print } on && /^fi$/ { exit }' \
    "$AUTOPR_DIR/investigate.sh")"
grant_probe() {
    local mode="$1" caps="$2"
    (
        KIND_OUTCOME="$(autopr_kind_field "$mode" outcome)"
        KIND_SANDBOX_ENV="$(autopr_kind_field "$mode" sandbox)"
        BOARD_CAPABILITIES="$caps"
        eval "$grant_block"
        printf '%s %s' "$SEARCH_GRANTED" "$BROWSE_GRANTED"
    )
}
check "an email run gets neither search nor a browser even on a board granted research and browse" \
    $([ -n "$grant_block" ] \
      && [ "$(grant_probe email "$(printf 'email\nresearch\nbrowse\noutreach')")" = "false false" ] \
      && [ "$(grant_probe research "$(printf 'research\nbrowse')")" = "true true" ] \
      && [ "$(grant_probe research research)" = "true false" ] \
      && [ "$(grant_probe investigate research)" = "true false" ] \
      && [ "$(grant_probe investigate "")" = "false false" ] \
      && echo 0 || echo 1)

# A revision round keeps the newest prior report and drops older rounds, now
# for email reports too; the snapshots Espresso attached are never dropped.
cat > "$TMP_DIR/own-files.json" <<'EOF'
[{"filename":"email-18c3f0a1.md","created_at":"2026-09-01T00:00:00Z"},
 {"filename":"email-report-aaaa0000-r1.md","created_at":"2026-09-02T00:00:00Z"},
 {"filename":"email-report-aaaa0000-r2.md","created_at":"2026-09-03T00:00:00Z"},
 {"filename":"invoice-1042.pdf","created_at":"2026-09-04T00:00:00Z"}]
EOF
own_defs="$(grep -m1 'def mine:' "$AUTOPR_DIR/investigate.sh") $(grep -m1 'def prior_report:' "$AUTOPR_DIR/investigate.sh")"
kept="$(jq -c --arg id8 aaaa0000 "$own_defs"'
    ([.[] | select(prior_report)] | sort_by(.created_at // "") | last) as $keep
    | map(select((mine | not) or (. == $keep))) | map(.filename)' "$TMP_DIR/own-files.json" 2>/dev/null)"
check "investigate.sh recognises email reports as its own output and never filters a snapshot" \
    $([ "$kept" = '["email-18c3f0a1.md","email-report-aaaa0000-r2.md","invoice-1042.pdf"]' ] \
      && [ "$(grep -cF 'test("^(research|email)-(report-)?" + $id8' "$AUTOPR_DIR/investigate.sh")" = 2 ] \
      && [ "$(grep -cF 'test("^(research|email)-report-" + $id8' "$AUTOPR_DIR/investigate.sh")" = 2 ] \
      && ! grep -qF 'test("^research-' "$AUTOPR_DIR/investigate.sh" \
      && echo 0 || echo 1)

################################################################################
# Prompt
prompt_has_headings() {
    local heading
    while IFS= read -r heading; do
        [ -n "$heading" ] || continue
        grep -qxF "$heading" "$prompt" || return 1
    done <<< "$(autopr_kind_field email headings)"
}
check "the email prompt forbids edits and sending, pins the reply shape, and names every heading" \
    $(grep -q 'Do not edit, create, move, or delete any repository file' "$prompt" \
      && grep -q 'Send anything to anyone' "$prompt" \
      && grep -qF '`Re: `' "$prompt" \
      && grep -qF 'Do NOT add any other keys to a staged action' "$prompt" \
      && grep -qF 'a fact' "$prompt" && grep -qF 'about the email, not a directive' "$prompt" \
      && grep -qF '"handle these"' "$prompt" \
      && grep -qF '"staged_actions"' "$prompt" && grep -qF '"per_email"' "$prompt" \
      && grep -qF 'REPORT_PATH' "$prompt" && grep -qF 'DECISION_PATH' "$prompt" \
      && ! grep -qx 'BROWSE_TOOL_SECTION' "$prompt" \
      && ! grep -qx 'GROUNDING_CONTEXT_SECTION' "$prompt" \
      && ! grep -qF 'browse-capture.py' "$prompt" \
      && prompt_has_headings \
      && echo 0 || echo 1)
check "every address in the email prompt is on a reserved domain" \
    $(! grep -oE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$prompt" \
        | grep -vE '@(example\.(com|org|net)|[A-Za-z0-9.-]+\.(test|invalid|localhost))$' | grep -q . \
      && echo 0 || echo 1)

################################################################################
# decision.sh normalize-email
cat > "$TMP_DIR/email-raw.json" <<'EOF'
{"schema_version":1,"outcome":"email_report","card_note":"Two emails need you; one reply drafted for Alice.","summary":"Reviewed three emails: Alice asks to move Thursday's call, Bob sent invoice 1042 to approve by the 20th, and a weekly digest needs nothing.","per_email":[{"file":"email-18c3f0a1.md","from":"Alice Example <alice@example.com>","subject":"Can we move Thursday?","bucket":"needs_reply","summary":"Alice asks to move the Thursday call to Friday morning.","suggested_action":"Reply accepting Friday 10am or propose another slot."},{"file":"email-2b9e7c4d.md","from":"bob@example.org","subject":"Invoice 1042","bucket":"action","summary":"Bob sent invoice 1042 for September and asks for approval by the 20th.","suggested_action":"Approve invoice 1042 before the 20th."},{"file":"email-9f00aa11.md","from":"noreply@news.example.net","subject":"Weekly digest","bucket":"newsletter","summary":"Automated weekly digest; nothing to do.","suggested_action":""}],"confidence":{"score":80,"reason":"all three snapshots were complete"},"questions":[],"staged_actions":[{"kind":"email","to":"alice@example.com","subject":"Re: Can we move Thursday?","body":"Hi Alice, Friday at 10am works for me. Talk then.","why":"Answers the only email that needs a reply."}]}
EOF
"$AUTOPR_DIR/decision.sh" normalize-email "$TMP_DIR/email-raw.json" "$TMP_DIR/email-decision.json" >/dev/null 2>&1
normalize_rc=$?
check "a valid email_report normalizes with kind=email and the keys the generic workflow steps read" \
    $([ "$normalize_rc" = 0 ] \
      && jq -e '.kind == "email" and .safe_changes_present == false and .awaiting_human == false
                and .outcome == "email_report"
                and .confidence_score == 80 and .confidence_band == "high"
                and .criticality.level == "yellow"
                and (.per_email | length == 3) and (.staged_actions | length == 1)
                and (.questions == []) and (has("sources") | not)' \
            "$TMP_DIR/email-decision.json" >/dev/null \
      && echo 0 || echo 1)
check "normalize-email accepts the directive-policy argument investigate.sh passes every validator" \
    $("$AUTOPR_DIR/decision.sh" normalize-email "$TMP_DIR/email-raw.json" \
        "$TMP_DIR/email-decision-4arg.json" "$TMP_DIR/nonexistent-policy.json" >/dev/null 2>&1 && echo 0 || echo 1)

rejects() {
    local desc="$1" filter="$2"
    jq "$filter" "$TMP_DIR/email-raw.json" > "$TMP_DIR/email-bad.json"
    check "$desc" \
        $(! "$AUTOPR_DIR/decision.sh" normalize-email "$TMP_DIR/email-bad.json" "$TMP_DIR/x.json" >/dev/null 2>&1 \
          && echo 0 || echo 1)
}
rejects "an email_report with no per_email entries is rejected" 'del(.per_email)'
rejects "a bucket outside needs_reply|action|fyi|newsletter is rejected" '.per_email[0].bucket = "urgent"'
rejects "a per_email file that is a path, not the bare snapshot name, is rejected" \
    '.per_email[0].file = "attachments/email-18c3f0a1.md"'
rejects "an unknown top-level key never rides through normalization" '. + {autopr_directives: ["draft_pr"]}'
rejects "a staged reply on a needs_clarification decision is rejected" \
    '.outcome = "needs_clarification" | .per_email = []
     | .questions = [{"id":"q1","question":"Which emails?","why_blocking":"none attached","options":[{"key":"a","label":"Attach them","impact":"reviewed next run"},{"key":"b","label":"Close the card","impact":"nothing reviewed"}],"default_assumption":"attach them"}]'
rejects "a card note carrying the note separator is rejected" '.card_note = "one · two"'
rejects "a raw decision that forges the validated-email marker is rejected" '. + {kind: "email"}'
rejects "the same snapshot reviewed twice is rejected" '.per_email[1].file = "email-18c3f0a1.md"'
rejects "an extra key on a per_email entry is rejected" '.per_email[0].in_reply_to = "<abc@mail.example.com>"'
rejects "a staged email addressed with a display name is rejected" \
    '.staged_actions[0].to = "Alice Example <alice@example.com>"'
rejects "a research-shaped report (sources, no per_email) is rejected" \
    'del(.per_email) | . + {sources: [{"title":"x","url":"https://example.com"}]}'

cat > "$TMP_DIR/clarify-raw.json" <<'EOF'
{"schema_version":1,"outcome":"needs_clarification","card_note":"No email snapshot is attached to this card.","summary":"The card asks to handle the attached emails, but no email snapshot is attached.","per_email":[],"confidence":{"score":15,"reason":"nothing to review"},"questions":[{"id":"q1","question":"Which emails should this card cover?","why_blocking":"There are no email snapshots attached to review.","options":[{"key":"a","label":"I will attach them with Send to board","impact":"the next run reviews those emails"},{"key":"b","label":"Close the card","impact":"nothing is reviewed"}],"default_assumption":"You will attach the emails from Espresso."}],"staged_actions":[]}
EOF
"$AUTOPR_DIR/decision.sh" normalize-email "$TMP_DIR/clarify-raw.json" "$TMP_DIR/clarify-decision.json" >/dev/null 2>&1
check "a needs_clarification decision normalizes as awaiting_human" \
    $(jq -e '.kind == "email" and .awaiting_human == true and (.questions | length == 1)
             and .confidence_band == "low" and .per_email == []' \
        "$TMP_DIR/clarify-decision.json" >/dev/null 2>&1 && echo 0 || echo 1)

################################################################################
# select.sh: an email card needs the `email` grant and never reads the PR ledger.
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$EMAIL_TEST_GH_LOG"
case "$1 $2" in
    "pr list") printf '[]\n' ;;
    "pr view") printf '{"state":"OPEN"}\n' ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"
printf '[]\n' > "$TMP_DIR/bot-prs.json"
export EMAIL_TEST_GH_LOG="$TMP_DIR/gh.log"

run_select() {
    local cards="$1" out="$2"
    : > "$EMAIL_TEST_GH_LOG"
    PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_BOT_PRS_FILE="$TMP_DIR/bot-prs.json" \
    AUTOPR_CACHE_DIR="$TMP_DIR/cache" AUTOPR_SELECT_READ_ONLY=true \
        "$AUTOPR_DIR/select.sh" "$cards" > "$out" 2>"$out.err"
}
cat > "$TMP_DIR/cards-todo.json" <<'EOF'
[{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Email: Can we move Thursday? (+2)","board_column":"todo","category":"email","autopr_capabilities":["email"],"created_at":"2026-09-01T00:00:00Z","last_moved_at":"2026-09-01T00:00:00Z"}]
EOF
run_select "$TMP_DIR/cards-todo.json" "$TMP_DIR/select-todo.json"
check "an email card on a board granted email selects as mode email, outcome artifact, without gh" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-todo.json" 2>/dev/null)" = email ] \
      && [ "$(jq -r '.outcome' "$TMP_DIR/select-todo.json" 2>/dev/null)" = artifact ] \
      && ! grep -q 'pr list' "$EMAIL_TEST_GH_LOG" \
      && echo 0 || echo 1)
jq '.[0].autopr_capabilities = ["research","outreach","browse"]' "$TMP_DIR/cards-todo.json" \
    > "$TMP_DIR/cards-ungranted.json"
run_select "$TMP_DIR/cards-ungranted.json" "$TMP_DIR/select-ungranted.json"
ungranted_rc=$?
check "the research, outreach, and browse grants do not stand in for the email grant" \
    $([ "$ungranted_rc" = 3 ] \
      && jq -e 'any(.[]; .id8 == "aaaa0000" and .capability == "email")' \
          "$TMP_DIR/cache/ungranted.json" >/dev/null 2>&1 \
      && echo 0 || echo 1)
jq '.[0] |= (.board_column = "changes_requested" | .review_note = "Make the reply to Alice shorter"
             | .last_moved_at = "2026-09-02T00:00:00Z")' "$TMP_DIR/cards-todo.json" > "$TMP_DIR/cards-cr.json"
run_select "$TMP_DIR/cards-cr.json" "$TMP_DIR/select-cr.json"
check "an email card sent back with a review note reruns as email (next report round)" \
    $([ "$(jq -r '.mode' "$TMP_DIR/select-cr.json" 2>/dev/null)" = email ] && echo 0 || echo 1)

################################################################################
# publish-email.sh
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
printf '%s %s\n' "$method" "$url" >> "$EMAIL_TEST_CURL_LOG"
respond() { [ -z "$output_file" ] || printf '%s' "$1" > "$output_file"; printf 200; }
case "$url" in
  */auth/login) printf '{"access_token":"test-token"}' ;;
  */files)
    if [ "$method" = POST ]; then
      src="${form#file=@}"; src="${src%%;*}"
      name="$(basename "$src")"
      cp "$src" "$EMAIL_TEST_UPLOADED"; printf '%s\n' "$name" > "$EMAIL_TEST_UPLOADED_NAME"
      respond "{\"id\":\"file-$name\",\"filename\":\"$name\"}"
    else
      respond "${EMAIL_TEST_EXISTING_FILES:-[]}"
    fi ;;
  */autopr/staged-actions) printf '%s' "$payload" > "$EMAIL_TEST_STAGED"; respond '{"ok":true,"staged":1,"action_ids":["act-1"]}' ;;
  */activity) printf '%s' "$payload" > "$EMAIL_TEST_ACTIVITY"; respond '{"ok":true}' ;;
  */autopr/context-request) printf '%s' "$payload" > "$EMAIL_TEST_CONTEXT_REQUEST"; respond '{"ok":true}' ;;
  */autopr/result-notification) printf '%s' "$payload" > "$EMAIL_TEST_RESULT_NOTIFICATION"; respond '{"ok":true}' ;;
  */history) respond "${EMAIL_TEST_EXISTING_HISTORY:-[]}" ;;
  */tasks/*) printf '%s' "$payload" > "$EMAIL_TEST_CARD_PATCH"; respond '{"ok":true}' ;;
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
Three emails reviewed; Alice needs a reply and Bob's invoice needs approval.
### Emails reviewed
- email-18c3f0a1.md — Alice Example — Can we move Thursday? — needs reply.
- email-2b9e7c4d.md — bob@example.org — Invoice 1042 — action.
- email-9f00aa11.md — Weekly digest — newsletter.
### Recommended actions
1. Approve the drafted reply to Alice.
2. Approve invoice 1042 before the 20th.
### Confidence
high — every snapshot was complete.
EOF
cat > "$TMP_DIR/card.json" <<'EOF'
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Email: Can we move Thursday? (+2)","category":"email","autopr_capabilities":["email","outreach"],"mode":"email","autopr_reconsideration_event_id":"eeeeeeee-0000-4000-8000-000000000001","progress_note":"🤖 AUTO SETUP · READY FOR REVIEW · build 800 · prod 1111111 · 🟡 C50 · note: earlier round\nkeep this human line","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
EOF
export EMAIL_TEST_CURL_LOG="$TMP_DIR/curl.log" EMAIL_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    EMAIL_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" EMAIL_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    EMAIL_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    EMAIL_TEST_UPLOADED="$TMP_DIR/uploaded.md" EMAIL_TEST_UPLOADED_NAME="$TMP_DIR/uploaded-name" \
    EMAIL_TEST_STAGED="$TMP_DIR/staged-actions.json"

run_publisher() {
    local card="$1" decision="$2"
    : > "$EMAIL_TEST_CURL_LOG"
    : > "$EMAIL_TEST_GH_LOG"
    rm -f "$EMAIL_TEST_ACTIVITY" "$EMAIL_TEST_CARD_PATCH" "$EMAIL_TEST_CONTEXT_REQUEST" \
        "$EMAIL_TEST_RESULT_NOTIFICATION" "$EMAIL_TEST_UPLOADED" "$EMAIL_TEST_UPLOADED_NAME" \
        "$EMAIL_TEST_STAGED"
    PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
        "$AUTOPR_DIR/publish-email.sh" "$card" "$TMP_DIR/report.md" "$decision"
}

# Round 1 is on the card and announced, and the card also carries the email
# snapshots it was created with — which must not count as report rounds.
export EMAIL_TEST_EXISTING_FILES='[{"id":"file-snap","filename":"email-18c3f0a1.md","created_at":"2026-09-01T00:00:00+00:00"},{"id":"file-old","filename":"email-report-aaaa0000-r1.md","created_at":"2026-09-02T00:00:00+00:00"}]'
export EMAIL_TEST_EXISTING_HISTORY='[{"id":"h0","event_type":"activity","metadata":{"kind":"note","body":"Report attached: email-report-aaaa0000-r1.md"}}]'
run_publisher "$TMP_DIR/card.json" "$TMP_DIR/email-decision.json" > "$TMP_DIR/publish.log" 2>&1
publish_rc=$?
[ "$publish_rc" = 0 ] || sed -n '1,40p' "$TMP_DIR/publish.log"
check "the report is uploaded as the next round, email-report-<id8>-r2.md, beside the snapshots" \
    $([ "$publish_rc" = 0 ] \
      && grep -q 'POST https://example.invalid/api/matcha-work/projects/8b924347-d6e4-4000-8e7d-ca8f46f76fba/tasks/aaaa0000-0000-4000-8000-000000000001/files' "$EMAIL_TEST_CURL_LOG" \
      && [ "$(cat "$EMAIL_TEST_UPLOADED_NAME")" = email-report-aaaa0000-r2.md ] \
      && echo 0 || echo 1)
check "the uploaded report carries the trusted email provenance header and the unsent reply draft" \
    $(head -1 "$EMAIL_TEST_UPLOADED" | grep -qE '^_AutoPR email review · [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2} UTC · model gpt-5\.6-luna · round 2 · 3 email\(s\) reviewed_$' \
      && grep -q '^### Emails reviewed' "$EMAIL_TEST_UPLOADED" \
      && grep -q '^### Proposed actions (not sent)' "$EMAIL_TEST_UPLOADED" \
      && grep -q '\[email\] to: alice@example.com · subject: Re: Can we move Thursday?' "$EMAIL_TEST_UPLOADED" \
      && echo 0 || echo 1)
check "a summary note is posted with the report attached and threaded under the additional-context event" \
    $(jq -e '.kind == "note" and .attachment_ids == ["file-email-report-aaaa0000-r2.md"]
             and (.body | startswith("Reviewed three emails"))
             and (.body | contains("Report attached: email-report-aaaa0000-r2.md"))
             and (.body | contains("NOT sent"))
             and (.body | contains("waiting for your approval"))
             and .reply_to == "eeeeeeee-0000-4000-8000-000000000001"' \
        "$EMAIL_TEST_ACTIVITY" >/dev/null 2>&1 && echo 0 || echo 1)
check "an outreach-granted board gets the reply draft staged for approval, keyed on the report" \
    $(jq -e '(.actions | length) == 1 and .actions[0].kind == "email"
             and .actions[0].to == "alice@example.com"
             and .actions[0].subject == "Re: Can we move Thursday?"
             and .run_key == "file-email-report-aaaa0000-r2.md"' "$EMAIL_TEST_STAGED" >/dev/null 2>&1 \
      && echo 0 || echo 1)
check "the card moves to Review with a structured note that replaces the prior prefix and keeps the human line" \
    $(jq -e '.board_column == "review"
             and (.progress_note | startswith("🤖 AUTO SETUP · READY FOR REVIEW · build 850 · prod 68a70f4 · 🟢 C80 · note: Two emails need you; one reply drafted for Alice."))
             and (.progress_note | contains("keep this human line"))
             and (.progress_note | contains("C50") | not)' \
        "$EMAIL_TEST_CARD_PATCH" >/dev/null 2>&1 && echo 0 || echo 1)
check "drafts are staged before the note announces them and the note lands before the card moves" \
    $(awk '/autopr\/staged-actions/ {s=NR} /\/activity$/ {n=NR} /^PATCH .*\/tasks\/aaaa0000-0000-4000-8000-000000000001$/ {m=NR} END {exit !(s && n && m && s < n && n < m)}' \
        "$EMAIL_TEST_CURL_LOG" && echo 0 || echo 1)
check "the additional-context author is told which email report round landed" \
    $(jq -e '(.message | contains("email report round 2"))
             and (.expected_progress_note | startswith("🤖 AUTO SETUP · READY FOR REVIEW"))' \
        "$EMAIL_TEST_RESULT_NOTIFICATION" >/dev/null 2>&1 && echo 0 || echo 1)
check "the email publisher never calls gh and posts no context request for a delivered report" \
    $([ ! -s "$EMAIL_TEST_GH_LOG" ] && [ ! -e "$EMAIL_TEST_CONTEXT_REQUEST" ] && echo 0 || echo 1)

# Without the outreach grant the drafts stay in the report only.
jq '.autopr_capabilities = ["email"]' "$TMP_DIR/card.json" > "$TMP_DIR/card-noreach.json"
run_publisher "$TMP_DIR/card-noreach.json" "$TMP_DIR/email-decision.json" > "$TMP_DIR/publish-noreach.log" 2>&1
noreach_rc=$?
check "a board without the outreach grant stages nothing and says so in the report" \
    $([ "$noreach_rc" = 0 ] \
      && [ ! -e "$EMAIL_TEST_STAGED" ] \
      && ! grep -q 'autopr/staged-actions' "$EMAIL_TEST_CURL_LOG" \
      && grep -q 'not granted outreach' "$EMAIL_TEST_UPLOADED" \
      && echo 0 || echo 1)

# A pass that died after uploading round 2 but before announcing it: the next
# pass reuses that orphan instead of starting round 3.
export EMAIL_TEST_EXISTING_FILES='[{"id":"file-snap","filename":"email-18c3f0a1.md","created_at":"2026-09-01T00:00:00+00:00"},{"id":"file-old","filename":"email-report-aaaa0000-r1.md","created_at":"2026-09-02T00:00:00+00:00"},{"id":"file-mine","filename":"email-report-aaaa0000-r2.md","created_at":"2026-09-08T10:00:05+00:00"}]'
run_publisher "$TMP_DIR/card.json" "$TMP_DIR/email-decision.json" > "$TMP_DIR/publish-retry.log" 2>&1
retry_rc=$?
check "a later pass reuses the orphaned email report, uploads nothing, and announces it once" \
    $([ "$retry_rc" = 0 ] \
      && [ ! -e "$EMAIL_TEST_UPLOADED" ] \
      && ! grep -q 'POST .*/files' "$EMAIL_TEST_CURL_LOG" \
      && jq -e '.attachment_ids == ["file-mine"]
               and (.body | contains("Report attached: email-report-aaaa0000-r2.md"))' \
          "$EMAIL_TEST_ACTIVITY" >/dev/null 2>&1 \
      && jq -e '.run_key == "file-mine"' "$EMAIL_TEST_STAGED" >/dev/null 2>&1 \
      && grep -q 'reusing it' "$TMP_DIR/publish-retry.log" \
      && echo 0 || echo 1)

# Cannot review as asked: park the card with the question form.
export EMAIL_TEST_EXISTING_FILES='[]'
jq 'del(.autopr_reconsideration_event_id) | .progress_note = ""' "$TMP_DIR/card.json" > "$TMP_DIR/card-fresh.json"
run_publisher "$TMP_DIR/card-fresh.json" "$TMP_DIR/clarify-decision.json" > "$TMP_DIR/publish-clarify.log" 2>&1
clarify_rc=$?
check "a needs_clarification result parks the card in Changes Requested, asks the owner, and uploads nothing" \
    $([ "$clarify_rc" = 0 ] \
      && jq -e '.board_column == "changes_requested"
                and (.progress_note | startswith("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · build 850 · prod 68a70f4 · 🔴 C15 · [autopr:no-spec "))
                and (.progress_note | contains("1. Which emails should this card cover?"))' \
          "$EMAIL_TEST_CARD_PATCH" >/dev/null 2>&1 \
      && jq -e '(.reason | contains("Send to board"))' "$EMAIL_TEST_CONTEXT_REQUEST" >/dev/null 2>&1 \
      && ! grep -q 'POST .*/files' "$EMAIL_TEST_CURL_LOG" \
      && [ ! -e "$EMAIL_TEST_ACTIVITY" ] \
      && echo 0 || echo 1)

# Only a decision normalize-email produced may drive a board write.
cat > "$TMP_DIR/research-decision.json" <<'EOF'
{"kind":"research","schema_version":1,"outcome":"research_report","card_note":"Lambda fits the worker tier.","summary":"Lambda suits bursty jobs.","sources":[{"title":"x","url":"https://example.com"}],"confidence":{"score":82,"reason":"docs"},"questions":[],"staged_actions":[],"safe_changes_present":false,"awaiting_human":false,"confidence_score":82,"confidence_band":"high","criticality":{"level":"yellow","reasons":["research report; no product change"]}}
EOF
run_publisher "$TMP_DIR/card-fresh.json" "$TMP_DIR/research-decision.json" > "$TMP_DIR/publish-research-kind.log" 2>&1
research_kind_rc=$?
run_publisher "$TMP_DIR/card-fresh.json" "$TMP_DIR/email-raw.json" > "$TMP_DIR/publish-raw.log" 2>&1
raw_rc=$?
check "a research-kind decision and a raw email decision are both refused before any board write" \
    $([ "$research_kind_rc" != 0 ] && [ "$raw_rc" != 0 ] \
      && grep -q 'not a validated email decision' "$TMP_DIR/publish-research-kind.log" \
      && [ ! -s "$EMAIL_TEST_CURL_LOG" ] \
      && echo 0 || echo 1)

################################################################################
# Workflow wiring: the artifact publish step dispatches on the selected mode,
# and each branch names its publisher literally for test_ci_guards.sh.
publish_step="$(awk '/- name: Publish research report/ { on = 1 } on && /- name: Cleanup/ { exit } on { print }' "$workflow")"
check "the workflow publish step has literal research and email branches and refuses any other mode" \
    $(printf '%s\n' "$publish_step" | grep -qF '"$AUTOPR_CONTROL_ROOT/kanban-autopr/publish-email.sh"' \
      && printf '%s\n' "$publish_step" | grep -qF '"$AUTOPR_CONTROL_ROOT/kanban-autopr/publish-research.sh"' \
      && printf '%s\n' "$publish_step" | grep -qE '^[[:space:]]+email\)$' \
      && printf '%s\n' "$publish_step" | grep -qE '^[[:space:]]+research\)$' \
      && printf '%s\n' "$publish_step" | grep -qE '^[[:space:]]+\*\)$' \
      && printf '%s\n' "$publish_step" | grep -qF 'MODE: ${{ steps.select.outputs.mode }}' \
      && printf '%s\n' "$publish_step" | grep -qF "steps.select.outputs.outcome == 'artifact'" \
      && ! printf '%s\n' "$publish_step" | grep -qE '^[[:space:]]*GH_TOKEN:' \
      && echo 0 || echo 1)

# Run the step's actual script against stub publishers under GitHub's default
# `bash -e` shell: right script per mode, a failing publisher fails the step
# through the tee, and an unknown mode runs nothing.
mkdir -p "$TMP_DIR/control/kanban-autopr"
for publisher in publish-research.sh publish-email.sh; do
    cat > "$TMP_DIR/control/kanban-autopr/$publisher" <<EOF
#!/usr/bin/env bash
printf '%s %s\n' "$publisher" "\$#" >> "$TMP_DIR/dispatch.log"
exit "\${STUB_PUBLISHER_RC:-0}"
EOF
    chmod +x "$TMP_DIR/control/kanban-autopr/$publisher"
done
run_script="$(printf '%s\n' "$publish_step" | awk '/^        run: \|$/ { on = 1; next } on { sub(/^          /, ""); print }')"
run_step() {
    : > "$TMP_DIR/dispatch.log"
    env MODE="$1" AUTOPR_CONTROL_ROOT="$TMP_DIR/control" RUNNER_TEMP="$TMP_DIR/runner" \
        GITHUB_STEP_SUMMARY="$TMP_DIR/step-summary.md" STUB_PUBLISHER_RC="${2:-0}" \
        bash -e -c "$run_script" >/dev/null 2>&1
}
run_step email; email_step_rc=$?
email_dispatch="$(cat "$TMP_DIR/dispatch.log")"
run_step research; research_step_rc=$?
research_dispatch="$(cat "$TMP_DIR/dispatch.log")"
run_step email 1; failing_step_rc=$?
run_step shortlist; unknown_step_rc=$?
unknown_dispatch="$(cat "$TMP_DIR/dispatch.log")"
check "the publish step runs publish-email.sh (3 args) for email and publish-research.sh (4 args) for research" \
    $([ -n "$run_script" ] \
      && [ "$email_step_rc" = 0 ] && [ "$email_dispatch" = "publish-email.sh 3" ] \
      && [ "$research_step_rc" = 0 ] && [ "$research_dispatch" = "publish-research.sh 4" ] \
      && echo 0 || echo 1)
check "a failing publisher fails the step through the tee, and an unknown artifact mode runs nothing" \
    $([ "$failing_step_rc" != 0 ] && [ "$unknown_step_rc" != 0 ] && [ -z "$unknown_dispatch" ] \
      && echo 0 || echo 1)

check "ci syntax-checks the email publisher and the self-audit runs this suite" \
    $(grep -qF 'scripts/kanban-autopr/publish-email.sh' "$ci_workflow" \
      && grep -qF 'test_kanban_autopr_email.sh' "$REPO_ROOT/scripts/autopr-self-audit/audit.sh" \
      && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
