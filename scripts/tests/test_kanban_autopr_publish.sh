#!/usr/bin/env bash
# Exercises the question-only publication path in a disposable Git repository.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AUTOPR_SOURCE="$REPO_ROOT/scripts/kanban-autopr"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
TEST_REPO="$TMP_DIR/repo"
mkdir -p "$TEST_REPO/scripts"
cp -R "$AUTOPR_SOURCE" "$TEST_REPO/scripts/kanban-autopr"
mkdir -p "$TEST_REPO/server/app"
printf 'pass\n' > "$TEST_REPO/server/app/example.py"
git -C "$TEST_REPO" init -q
git -C "$TEST_REPO" config user.name test
git -C "$TEST_REPO" config user.email test@example.com
git -C "$TEST_REPO" add .
git -C "$TEST_REPO" commit -qm initial
git -C "$TEST_REPO" branch -M main
git init --bare -q "$TMP_DIR/origin.git"
git -C "$TEST_REPO" remote add origin "$TMP_DIR/origin.git"
git -C "$TEST_REPO" switch -q -c bot/task-aaaa0000 main

mkdir -p "$TMP_DIR/bin"
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_GH_LOG"
if [ "$1 $2" = "pr list" ]; then
  if [[ "$*" == *"--jq length"* ]]; then printf '0\n'; else printf '[]\n'; fi
elif [ "$1 $2" = "pr create" ]; then
  printf 'https://github.com/tajaa/matcha-recruit/pull/501\n'
elif [ "$1 $2" = "pr view" ]; then
  printf '{"comments":[],"reviews":[]}'
elif [ "$1 $2" = "pr edit" ]; then
  while [ "$#" -gt 0 ]; do
    if [ "$1" = "--body-file" ]; then cp "$2" "$AUTOPR_TEST_BODY"; break; fi
    shift
  done
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
  printf '%s' "$payload" > "$AUTOPR_TEST_CARD_PATCH"
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
cat > "$TMP_DIR/card.json" <<'EOF'
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Clarify terminology","category":"fix","mode":"investigate","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
EOF
cat > "$TMP_DIR/raw-decision.json" <<'EOF'
{"schema_version":1,"outcome":"questions_only","confidence":{"requirements_clarity":{"score":20,"reason":"term is unclear"},"evidence_quality":{"score":10,"reason":"screenshots conflict"},"code_localization":{"score":5,"reason":"multiple labels"},"verification_strength":{"score":2,"reason":"choice changes tests"},"production_alignment":{"score":5,"reason":"production baseline known"}},"criticality":{"level":"red","reasons":["current core workflow is blocked"]},"questions":[{"id":"q1","question":"Which term is canonical?","why_blocking":"both labels refer to the same object","options":[{"key":"a","label":"Journal","impact":"changes all labels to Journal"},{"key":"b","label":"Note","impact":"changes all labels to Note"}],"default_assumption":"Use Journal"}],"safe_changes_present":false,"no_safe_action_reason":null}
EOF
cat > "$TMP_DIR/report.md" <<'EOF'
### Summary
Need an answer.
### Changes
None.
### Blast radius
Unknown until terminology is chosen.
### Confidence
low
EOF
cat > "$TMP_DIR/verification.md" <<'EOF'
## Verification

Not run.
EOF

"$TEST_REPO/scripts/kanban-autopr/decision.sh" normalize "$TMP_DIR/raw-decision.json" "$TMP_DIR/decision.json"
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/card.json" "$TMP_DIR/decision.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md"
)

PASS=0
FAIL=0
check() {
  local desc="$1" ok="$2"
  if [ "$ok" = 0 ]; then echo "PASS: $desc"; PASS=$((PASS + 1));
  else echo "FAIL: $desc"; FAIL=$((FAIL + 1)); fi
}

check "questions-only publication uses an empty commit" \
  $(git -C "$TEST_REPO" log -1 --pretty=%s | grep -q '(questions)' && echo 0 || echo 1)
check "question draft body contains answers and feedback trailers" \
  $(grep -q '## Answers needed' "$TMP_DIR/pr-body.md" && grep -q 'matcha-feedback-comment-id: none' "$TMP_DIR/pr-body.md" && echo 0 || echo 1)
check "question draft title exposes criticality and confidence" \
  $(grep -q '🔴 \[C42\] \[QUESTIONS\] fix: Clarify terminology' "$TMP_DIR/gh.log" && echo 0 || echo 1)
check "card remains Changes Requested with a visible auto-setup note" \
  $(jq -e '.board_column == "changes_requested" and (.progress_note | contains("from auto setup")) and (.progress_note | contains("awaiting answers"))' "$TMP_DIR/card-patch.json" >/dev/null && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
