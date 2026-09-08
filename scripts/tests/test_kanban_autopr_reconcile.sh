#!/usr/bin/env bash
# Isolated recovery test: a missed pull_request webhook must be repaired before
# selection, while unrelated Todo work remains in the candidate stream.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RECONCILE="$REPO_ROOT/scripts/kanban-autopr/reconcile-merged-cards.sh"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/runner"

cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
[ -z "${AUTOPR_TEST_GH_LOG:-}" ] || printf '%s\n' "$*" >> "$AUTOPR_TEST_GH_LOG"
case "$3" in
  502) printf '{"state":"MERGED","headRefName":"bot/err-abc123abc123"}\n' ;;
  503) printf '{"state":"CLOSED","headRefName":"bot/task-dddd0000"}\n' ;;
  504) printf '{"state":"CLOSED","headRefName":"bot/err-ffffffffffff"}\n' ;;
  505) printf '{"state":"OPEN","headRefName":"bot/task-eeee0000"}\n' ;;
  *) printf '{"state":"MERGED","headRefName":"bot/task-aaaa0000"}\n' ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"

cat > "$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
output_file="" payload="" url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output_file="$2"; shift 2 ;;
    -d) payload="$2"; shift 2 ;;
    http://*|https://*) url="$1"; shift ;;
    *) shift ;;
  esac
done
if [[ "$url" == */auth/login ]]; then
  printf '{"access_token":"test-token"}'
else
  printf '%s\n' "$payload" >> "$AUTOPR_TEST_CARD_PATCH"
  [ -z "$output_file" ] || printf '{"ok":true}' > "$output_file"
  printf 200
fi
EOF
chmod +x "$TMP_DIR/bin/curl"

cat > "$TMP_DIR/env" <<'EOF'
MATCHA_API_URL=https://example.invalid/api
MATCHA_BOT_EMAIL=bot@example.com
MATCHA_BOT_PASSWORD=secret
MATCHA_PROJECT_IDS=one
MATCHA_ASSIGNEE_EMAIL=haley@oceaneca.com
EOF

cat > "$TMP_DIR/cards.json" <<'EOF'
[
  {"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"project-a","title":"Merged work","board_column":"changes_requested","progress_note":"from auto setup · PR #501 · ready for review","pr_number":501},
  {"task_id":"cccc0000-0000-4000-8000-000000000003","id8":"cccc0000","project_id":"project-c","title":"Cross-lane work","board_column":"in_progress","progress_note":"🤖 AUTO SETUP · ALREADY SCOPED · PR #502 · source existing PR","pr_number":502},
  {"task_id":"bbbb0000-0000-4000-8000-000000000002","id8":"bbbb0000","project_id":"project-b","title":"New work","board_column":"todo","progress_note":null,"pr_number":null}
]
EOF

PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
  AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" GITHUB_REPOSITORY=tajaa/matcha-recruit \
  "$RECONCILE" "$TMP_DIR/cards.json" > "$TMP_DIR/remaining.json"

jq -e 'length == 1 and .[0].id8 == "bbbb0000"' "$TMP_DIR/remaining.json" >/dev/null
jq -s -e 'length == 2 and all(.[]; .board_column == "review")' "$TMP_DIR/card-patch.json" >/dev/null
printf 'PASS: merged task-branch and cross-lane cards are repaired before Todo selection\n'

# A human closing this lane's own draft without merging hands the card back to
# Todo; a cross-lane draft closed as superseded/duplicate is not a rejection
# and is left where it is. A PR the run already knows is OPEN costs no
# `gh pr view` at all.
cat > "$TMP_DIR/cards2.json" <<'EOF'
[
  {"task_id":"dddd0000-0000-4000-8000-000000000004","id8":"dddd0000","project_id":"project-d","title":"Rejected draft","board_column":"in_progress","progress_note":"🤖 AUTO SETUP · READY FOR REVIEW · PR #503","pr_number":503},
  {"task_id":"ffff0000-0000-4000-8000-000000000006","id8":"ffff0000","project_id":"project-f","title":"Superseded cross-lane","board_column":"in_progress","progress_note":"🤖 AUTO SETUP · ALREADY SCOPED · PR #504","pr_number":504},
  {"task_id":"eeee0000-0000-4000-8000-000000000005","id8":"eeee0000","project_id":"project-e","title":"Still open","board_column":"changes_requested","progress_note":"🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS · PR #505","pr_number":505}
]
EOF
printf '[{"number":505,"state":"OPEN","labels":["autopr","autopr-awaiting-input"]}]\n' > "$TMP_DIR/bot-prs.json"
: > "$TMP_DIR/card-patch2.json"
PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" RUNNER_TEMP="$TMP_DIR/runner" \
  AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch2.json" AUTOPR_TEST_GH_LOG="$TMP_DIR/gh2.log" \
  AUTOPR_BOT_PRS_FILE="$TMP_DIR/bot-prs.json" GITHUB_REPOSITORY=tajaa/matcha-recruit \
  "$RECONCILE" "$TMP_DIR/cards2.json" > "$TMP_DIR/remaining2.json"
jq -s -e 'length == 1 and .[0].board_column == "todo"' "$TMP_DIR/card-patch2.json" >/dev/null
jq -e 'length == 2 and (map(.id8) | sort) == ["eeee0000","ffff0000"]' "$TMP_DIR/remaining2.json" >/dev/null
! grep -q '^pr view 505 ' "$TMP_DIR/gh2.log"
grep -q '^pr view 503 ' "$TMP_DIR/gh2.log"
printf 'PASS: a closed-unmerged own draft returns its card to Todo; cross-lane closes and known-open PRs are untouched\n'
