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
if [ "$3" = 502 ]; then
  printf '{"state":"MERGED","headRefName":"bot/err-abc123abc123"}\n'
else
  printf '{"state":"MERGED","headRefName":"bot/task-aaaa0000"}\n'
fi
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
