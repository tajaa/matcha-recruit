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
cp "$REPO_ROOT/scripts/alembic_graph_snapshot.py" "$TEST_REPO/scripts/alembic_graph_snapshot.py"
mkdir -p "$TEST_REPO/server/app" "$TEST_REPO/server/alembic/versions"
printf 'pass\n' > "$TEST_REPO/server/app/example.py"
cat > "$TEST_REPO/server/alembic/versions/base_test.py" <<'EOF'
"""Test migration base."""

revision = "base_test"
down_revision = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
EOF
# Two mainline revisions, so "parent is a real revision but not the head" is a
# distinct case from "parent does not exist at all".
cat > "$TEST_REPO/server/alembic/versions/mid_test.py" <<'EOF'
"""Test migration middle."""

revision = "mid_test"
down_revision = "base_test"


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
EOF
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
  if [[ "$*" == *"--head bot/task-aaaa0000"* ]]; then
    printf '%s\n' "${AUTOPR_TEST_EXISTING_PRS:-[]}"
  elif [[ "$*" == *"--jq length"* ]]; then
    printf '0\n'
  else
    printf '[]\n'
  fi
elif [ "$1 $2" = "pr create" ]; then
  args=("$@")
  for ((i = 0; i < ${#args[@]}; i++)); do
    if [ "${args[$i]}" = "--body-file" ]; then cp "${args[$((i + 1))]}" "$AUTOPR_TEST_BODY"; break; fi
  done
  printf 'https://github.com/tajaa/matcha-recruit/pull/501\n'
elif [ "$1 $2" = "pr view" ]; then
  if [[ "$*" == *"--json labels"* ]]; then
    printf '%s\n' "${AUTOPR_TEST_LABELS:-}"
  else
    printf '{"comments":[{"id":"late-comment","body":"posted after investigation","author":{"login":"haley"}}],"reviews":[]}'
  fi
elif [ "$1 $2" = "pr edit" ]; then
  if [ "${AUTOPR_TEST_LABEL_FAIL:-0}" = 1 ] && [[ "$*" == *"--add-label"* ]]; then
    exit 1
  fi
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
  if [[ "$url" == */activity ]]; then
    printf '%s' "$payload" > "$AUTOPR_TEST_ACTIVITY"
  elif [[ "$url" == */autopr/context-request ]]; then
    printf '%s' "$payload" > "$AUTOPR_TEST_CONTEXT_REQUEST"
  elif [[ "$url" == */autopr/result-notification ]]; then
    printf '%s' "$payload" > "$AUTOPR_TEST_RESULT_NOTIFICATION"
    result_status="${AUTOPR_TEST_RESULT_NOTIFICATION_STATUS:-200}"
    if [ "$result_status" != 200 ]; then
      [ -z "$output_file" ] || printf '{"detail":"notification failure"}' > "$output_file"
      printf '%s' "$result_status"
      exit 0
    fi
  else
    printf '%s' "$payload" > "$AUTOPR_TEST_CARD_PATCH"
  fi
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
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Clarify terminology","category":"fix","mode":"investigate","autopr_reconsideration_event_id":"eeeeeeee-0000-4000-8000-000000000001","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
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
cat > "$TMP_DIR/publication-copy.json" <<'EOF'
{"schema_version":1,"commit_subject":"fix: clarify canonical terminology","card_note":"Needs the canonical term before labels and tests can be updated safely."}
EOF

"$TEST_REPO/scripts/kanban-autopr/decision.sh" normalize "$TMP_DIR/raw-decision.json" "$TMP_DIR/decision.json"
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/card.json" "$TMP_DIR/decision.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
)

PASS=0
FAIL=0
check() {
  local desc="$1" ok="$2"
  if [ "$ok" = 0 ]; then echo "PASS: $desc"; PASS=$((PASS + 1));
  else echo "FAIL: $desc"; FAIL=$((FAIL + 1)); fi
}

check "questions-only publication uses Luna's subject for an empty commit" \
  $([ "$(git -C "$TEST_REPO" log -1 --pretty=%s)" = 'fix: clarify canonical terminology' ] && echo 0 || echo 1)
check "question draft body contains answers and feedback trailers" \
  $(grep -q '## Answers needed' "$TMP_DIR/pr-body.md" \
    && grep -q 'matcha-feedback-comment-id: none' "$TMP_DIR/pr-body.md" \
    && grep -q 'matcha-autopr-note-state: awaiting_answers' "$TMP_DIR/pr-body.md" \
    && echo 0 || echo 1)
check "publisher does not checkpoint feedback that investigation never consumed" \
  $(! grep -q -- '--json comments,reviews' "$TMP_DIR/gh.log" && echo 0 || echo 1)
check "question draft title exposes criticality and confidence" \
  $(grep -q '🔴 \[C42\] \[QUESTIONS\] fix: Clarify terminology' "$TMP_DIR/gh.log" && echo 0 || echo 1)
check "card remains Changes Requested with a visible auto-setup note" \
  $(jq -e '.board_column == "changes_requested"
      and (.progress_note | startswith("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS"))
      and (.progress_note | contains("note: Needs the canonical term before labels and tests can be updated safely."))' \
    "$TMP_DIR/card-patch.json" >/dev/null && echo 0 || echo 1)
check "an awaiting-answers card carries the answer form the operator replies to" \
  $(jq -e '(.progress_note | contains("Answers needed — reply below with the numbered choices:"))
      and (.progress_note | contains("1. Which term is canonical?"))' \
    "$TMP_DIR/card-patch.json" >/dev/null && echo 0 || echo 1)
check "publisher replies to the triggering additional-context note" \
  $(jq -e '.kind == "note" and .reply_to == "eeeeeeee-0000-4000-8000-000000000001" and (.body | contains("still needs human answers in PR #501"))' "$TMP_DIR/activity.json" >/dev/null && echo 0 || echo 1)
check "publisher sends a decision-bound result notification to the context author" \
  $(jq -e '.reconsideration_event_id == "eeeeeeee-0000-4000-8000-000000000001"
      and (.expected_progress_note | startswith("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS"))
      and (.message | contains("still needs human answers in PR #501"))' \
    "$TMP_DIR/result-notification.json" >/dev/null && echo 0 || echo 1)
check "awaiting-input publication asks in project chat against the exact decision" \
  $(jq -e '(.reason | contains("canonical term")) and (.expected_progress_note | startswith("🤖 AUTO SETUP · BLOCKED: AWAITING ANSWERS"))' "$TMP_DIR/context-request.json" >/dev/null && echo 0 || echo 1)

unicode_sample="$(jq -nr '"a" * 3999 + "🙂tail"')"
unicode_truncated="$(printf '%s' "$unicode_sample" | jq -Rrs '.[0:4000]')"
check "context-request truncation preserves UTF-8 at the boundary" \
  $([ "$(printf '%s' "$unicode_truncated" | jq -Rrs 'length')" = 4000 ] \
    && [[ "$unicode_truncated" == *🙂 ]] \
    && grep -q "jq -Rsr '\.\[0:4000\]'" "$TEST_REPO/scripts/kanban-autopr/publish.sh" \
    && echo 0 || echo 1)

# The acceptance-evidence block is the payload, so its line structure has to
# reach the reader: flattening it cut the proof off after about four criteria.
multiline_reason="$(printf 'card note\n   - criterion one\n     path/to/file.tsx:12 @ abc1234')"
check "a multi-line context reason keeps its lines" \
  $([ "$(printf '%s' "$multiline_reason" | tr -d '\r' | jq -Rsr '.[0:4000]' | wc -l | tr -d ' ')" = "3" ] \
    && ! grep -q "tr '\\r\\n' '  '" "$TEST_REPO/scripts/kanban-autopr/publish.sh" \
    && echo 0 || echo 1)

cat > "$TMP_DIR/already-fixed-card.json" <<'EOF'
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Clarify terminology","category":"fix","mode":"investigate","pr_number":364,"progress_note":"🤖 AUTO SETUP · NO PR: ALREADY FIXED · [autopr:no-spec 2026-08-28T22:37:56Z] already_fixed","autopr_reconsideration_event_id":"ffffffff-0000-4000-8000-000000000002","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
EOF
cat > "$TMP_DIR/raw-already-fixed.json" <<'EOF'
{"schema_version":1,"outcome":"no_safe_action","confidence":{"requirements_clarity":{"score":30,"reason":"request is clear"},"evidence_quality":{"score":20,"reason":"implementation is present"},"code_localization":{"score":20,"reason":"existing code identified"},"verification_strength":{"score":15,"reason":"existing tests cover it"},"production_alignment":{"score":15,"reason":"baseline known"}},"criticality":{"level":"yellow","reasons":["existing behavior verified"]},"questions":[],"safe_changes_present":false,"no_safe_action_reason":"already_fixed"}
EOF
cat > "$TMP_DIR/already-fixed-publication-copy.json" <<'EOF'
{"schema_version":1,"commit_subject":"fix: clarify canonical terminology","card_note":"After reviewing the additional context, AutoPR still found this request already fixed."}
EOF
"$TEST_REPO/scripts/kanban-autopr/decision.sh" normalize "$TMP_DIR/raw-already-fixed.json" "$TMP_DIR/already-fixed.json"
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_RESULT_NOTIFICATION_STATUS=404 \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/already-fixed-card.json" "$TMP_DIR/already-fixed.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/already-fixed-publication-copy.json"
) 2>"$TMP_DIR/result-notification-404.stderr"

check "already-fixed reconsideration leaves a threaded note with the covering PR" \
  $(jq -e '.kind == "note" and .reply_to == "ffffffff-0000-4000-8000-000000000002" and (.body | startswith("After reviewing your additional context, AutoPR still found this request already fixed in PR #364."))' "$TMP_DIR/activity.json" >/dev/null && echo 0 || echo 1)
check "missing result-notification route does not fail completed publication" \
  $(grep -q 'result notification endpoint is not deployed; PR/card publication for task aaaa0000-0000-4000-8000-000000000001 remains complete' \
    "$TMP_DIR/result-notification-404.stderr" && echo 0 || echo 1)

set +e
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_RESULT_NOTIFICATION_STATUS=500 \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/already-fixed-card.json" "$TMP_DIR/already-fixed.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/already-fixed-publication-copy.json"
) >/dev/null 2>"$TMP_DIR/result-notification-500.stderr"
notification_500_rc=$?
set -e
check "result-notification server failures remain fatal" \
  $([ "$notification_500_rc" != 0 ] \
    && grep -q 'HTTP 500:.*notification failure' "$TMP_DIR/result-notification-500.stderr" \
    && echo 0 || echo 1)

cat > "$TMP_DIR/rework-card.json" <<'EOF'
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Clarify terminology","category":"fix","mode":"rework","progress_note":"from auto setup · build 849 · prod 1111111 · PR #501 · 🔴 C42 · awaiting answers · Human note","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
EOF
cat > "$TMP_DIR/raw-no-safe.json" <<'EOF'
{"schema_version":1,"outcome":"no_safe_action","confidence":{"requirements_clarity":{"score":30,"reason":"clear boundary"},"evidence_quality":{"score":20,"reason":"review confirms it"},"code_localization":{"score":20,"reason":"boundary identified"},"verification_strength":{"score":15,"reason":"no product diff allowed"},"production_alignment":{"score":15,"reason":"baseline known"}},"criticality":{"level":"orange","reasons":["third-party API change required"]},"questions":[],"safe_changes_present":false,"no_safe_action_reason":"external_dependency"}
EOF
cat > "$TMP_DIR/no-safe-publication-copy.json" <<'EOF'
{"schema_version":1,"commit_subject":"fix: clarify canonical terminology","card_note":"Blocked on a third-party API change AutoPR cannot make."}
EOF
"$TEST_REPO/scripts/kanban-autopr/decision.sh" normalize "$TMP_DIR/raw-no-safe.json" "$TMP_DIR/no-safe.json"
jq '. + {feedback_checkpoint:{comment_id:"answer-1",review_id:""}}' \
  "$TMP_DIR/no-safe.json" > "$TMP_DIR/no-safe-with-feedback.json"
mv "$TMP_DIR/no-safe-with-feedback.json" "$TMP_DIR/no-safe.json"

existing_pr='[{"number":501,"body":"<!-- matcha-feedback-comment-id: answer-1 -->\n<!-- matcha-feedback-review-id: none -->"}]'
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_EXISTING_PRS="$existing_pr" AUTOPR_TEST_LABELS=$'criticality:red\nconfidence:low\nautopr-awaiting-input' \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" \
    AUTOPR_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/rework-card.json" "$TMP_DIR/no-safe.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/no-safe-publication-copy.json"
)

check "rework no-safe-action reconciles the existing PR title and labels" \
  $(grep -q '🟠 \[C100\] \[NO SAFE ACTION\] fix: Clarify terminology' "$TMP_DIR/gh.log" \
    && grep -q -- '--remove-label criticality:red' "$TMP_DIR/gh.log" \
    && grep -q -- '--add-label criticality:orange' "$TMP_DIR/gh.log" \
    && echo 0 || echo 1)
check "rework no-safe-action keeps accurate PR and triage card provenance" \
  $(jq -e '.board_column == "changes_requested" and .pr_number == 501 and (.progress_note | startswith("🤖 AUTO SETUP · NO PR: EXTERNAL DEPENDENCY")) and (.progress_note | contains("PR #501 · 🟠 C100 · [autopr:no-spec")) and (.progress_note | contains("note: Blocked on a third-party API change AutoPR cannot make.")) and (.progress_note | endswith("Human note"))' "$TMP_DIR/card-patch.json" >/dev/null && echo 0 || echo 1)

rm -f "$TMP_DIR/card-patch.json"
set +e
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_EXISTING_PRS="$existing_pr" AUTOPR_TEST_LABELS='criticality:red' AUTOPR_TEST_LABEL_FAIL=1 \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" \
    AUTOPR_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/rework-card.json" "$TMP_DIR/no-safe.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/no-safe-publication-copy.json"
) >/dev/null 2>&1
label_failure_rc=$?
set -e
check "required triage label failure stops before the card is suppressed" \
  $([ "$label_failure_rc" != 0 ] && [ ! -e "$TMP_DIR/card-patch.json" ] && echo 0 || echo 1)

cat > "$TMP_DIR/raw-implementation.json" <<'EOF'
{"schema_version":1,"outcome":"implementation","confidence":{"requirements_clarity":{"score":30,"reason":"request is explicit"},"evidence_quality":{"score":20,"reason":"schema boundary is known"},"code_localization":{"score":20,"reason":"migration is localized"},"verification_strength":{"score":15,"reason":"migration can be reviewed"},"production_alignment":{"score":15,"reason":"baseline known"}},"criticality":{"level":"yellow","reasons":["scoped schema change"]},"questions":[],"safe_changes_present":true,"no_safe_action_reason":null}
EOF
"$TEST_REPO/scripts/kanban-autopr/decision.sh" normalize \
  "$TMP_DIR/raw-implementation.json" "$TMP_DIR/implementation.json"
cat > "$TEST_REPO/server/alembic/versions/task_test.py" <<'EOF'
"""Reviewed migration."""

revision = "task_test"
down_revision = "mid_test"


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
EOF
# Authoring a migration version file is ordinary drafting work: the operator
# applies every migration by hand, so no directive is involved.
rm -f "$TMP_DIR/gh.log"
set +e
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/card.json" "$TMP_DIR/implementation.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
) >/dev/null 2>"$TMP_DIR/draft-migration.stderr"
draft_migration_rc=$?
set -e
check "a migration version may be drafted with no directive at all" \
  $([ "$draft_migration_rc" = 0 ] \
    && git -C "$TEST_REPO" show --name-only --format= HEAD \
      | grep -qx 'server/alembic/versions/task_test.py' && echo 0 || echo 1)
check "migration work is published as a GitHub draft PR" \
  $(grep -q -- '^pr create .*--draft' "$TMP_DIR/gh.log" && echo 0 || echo 1)

# A second draft may chain onto the first: it extends a head this same change
# introduced, which is not the same thing as forking the graph.
git -C "$TEST_REPO" reset --hard -q HEAD
cat > "$TEST_REPO/server/alembic/versions/chain_a_test.py" <<'EOF'
"""Chained migration A."""

revision = "chain_a_test"
down_revision = "task_test"


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
EOF
cat > "$TEST_REPO/server/alembic/versions/chain_b_test.py" <<'EOF'
"""Chained migration B."""

revision = "chain_b_test"
down_revision = "chain_a_test"


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
EOF
set +e
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/card.json" "$TMP_DIR/implementation.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
) >/dev/null 2>"$TMP_DIR/chained-migration.stderr"
chained_migration_rc=$?
set -e
check "chained drafts extending each other are published" \
  $([ "$chained_migration_rc" = 0 ] \
    && git -C "$TEST_REPO" show --name-only --format= HEAD \
      | grep -qx 'server/alembic/versions/chain_b_test.py' && echo 0 || echo 1)

printf '\n# forbidden rewrite\n' >> "$TEST_REPO/server/alembic/versions/base_test.py"
set +e
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/card.json" "$TMP_DIR/implementation.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
) >/dev/null 2>"$TMP_DIR/existing-migration.stderr"
existing_migration_rc=$?
set -e
check "publisher rejects edits to migrations already present on main" \
  $([ "$existing_migration_rc" != 0 ] \
    && grep -q 'already present on main' "$TMP_DIR/existing-migration.stderr" \
    && ! grep -q 'forbidden rewrite' "$TEST_REPO/server/alembic/versions/base_test.py" \
    && echo 0 || echo 1)

printf '"""missing revision metadata and entrypoints"""\n' \
  > "$TEST_REPO/server/alembic/versions/malformed_test.py"
set +e
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/card.json" "$TMP_DIR/implementation.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
) >/dev/null 2>"$TMP_DIR/malformed-migration.stderr"
malformed_migration_rc=$?
set -e
check "publisher rejects malformed migration drafts before opening a PR" \
  $([ "$malformed_migration_rc" != 0 ] \
    && grep -q 'Refusing migration draft:' "$TMP_DIR/malformed-migration.stderr" \
    && grep -q 'missing migration entrypoint(s): downgrade, upgrade' "$TMP_DIR/malformed-migration.stderr" \
    && [ ! -e "$TEST_REPO/server/alembic/versions/malformed_test.py" ] \
    && echo 0 || echo 1)

# Graph-shape rules. Each of these parses and carries valid metadata, so only
# comparing the drafted graph with main's catches them — and each one would
# reach the operator's `alembic upgrade head` as "Multiple head revisions are
# present" if it merged.
publish_migration_draft() {
  local label="$1"
  set +e
  (
    cd "$TEST_REPO"
    PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
      AUTOPR_MIGRATION_BASE_REF="${AUTOPR_TEST_BASE_REF:-main}" \
      AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
      AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
      AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
      ./scripts/kanban-autopr/publish.sh "$TMP_DIR/card.json" "$TMP_DIR/implementation.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
  ) >/dev/null 2>"$TMP_DIR/$label.stderr"
  printf '%s' "$?"
  set -e
}

reset_test_repo() {
  git -C "$TEST_REPO" reset --hard -q HEAD
  git -C "$TEST_REPO" clean -fdq -- server/alembic
}

write_migration() {
  cat > "$TEST_REPO/server/alembic/versions/$1" <<EOF
"""Draft."""

revision = "$2"
down_revision = $3


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
EOF
}

reset_test_repo
write_migration new_base_test.py new_base_test None
new_base_rc="$(publish_migration_draft new-base-migration)"
check "publisher rejects a draft that adds a second base" \
  $([ "$new_base_rc" != 0 ] \
    && grep -q 'may not add a new base' "$TMP_DIR/new-base-migration.stderr" \
    && [ ! -e "$TEST_REPO/server/alembic/versions/new_base_test.py" ] \
    && echo 0 || echo 1)

reset_test_repo
write_migration fork_test.py fork_test '"base_test"'
fork_rc="$(publish_migration_draft fork-migration)"
check "publisher rejects a draft that forks the graph at a mid-chain revision" \
  $([ "$fork_rc" != 0 ] \
    && grep -q 'is not a current head' "$TMP_DIR/fork-migration.stderr" \
    && [ ! -e "$TEST_REPO/server/alembic/versions/fork_test.py" ] \
    && echo 0 || echo 1)

reset_test_repo
cat > "$TEST_REPO/server/alembic/versions/no_down_test.py" <<'EOF'
"""Draft with no downgrade."""

revision = "no_down_test"
down_revision = "chain_b_test"


def upgrade() -> None:
    pass
EOF
no_down_rc="$(publish_migration_draft no-downgrade-migration)"
check "publisher rejects a draft missing downgrade()" \
  $([ "$no_down_rc" != 0 ] \
    && grep -q 'missing migration entrypoint(s): downgrade' "$TMP_DIR/no-downgrade-migration.stderr" \
    && [ ! -e "$TEST_REPO/server/alembic/versions/no_down_test.py" ] \
    && echo 0 || echo 1)

# __init__.py sits in the versions directory but the graph loader skips it, so
# it is the one bot-writable path no validation would ever inspect.
reset_test_repo
printf 'import os\n' > "$TEST_REPO/server/alembic/versions/__init__.py"
init_py_rc="$(publish_migration_draft init-py-migration)"
check "publisher refuses a versions/__init__.py the graph loader would skip" \
  $([ "$init_py_rc" != 0 ] \
    && grep -q 'Refusing unsafe automated change:' "$TMP_DIR/init-py-migration.stderr" \
    && [ ! -e "$TEST_REPO/server/alembic/versions/__init__.py" ] \
    && echo 0 || echo 1)

# Alembic's own commented-out file_template produces this shape; the prompts
# now state the charset, and the refusal must still be the path guard's.
reset_test_repo
write_migration '2026-09-05_bad-name.py' dated_test '"chain_b_test"'
bad_name_rc="$(publish_migration_draft bad-name-migration)"
check "publisher refuses a date-prefixed migration filename" \
  $([ "$bad_name_rc" != 0 ] \
    && grep -q 'Refusing unsafe automated change:' "$TMP_DIR/bad-name-migration.stderr" \
    && [ ! -e "$TEST_REPO/server/alembic/versions/2026-09-05_bad-name.py" ] \
    && echo 0 || echo 1)

reset_test_repo
git -C "$TEST_REPO" rm -q server/alembic/versions/mid_test.py
deleted_rc="$(publish_migration_draft deleted-migration)"
check "publisher rejects deleting a migration already on main" \
  $([ "$deleted_rc" != 0 ] \
    && grep -q 'may not be edited or deleted' "$TMP_DIR/deleted-migration.stderr" \
    && [ -e "$TEST_REPO/server/alembic/versions/mid_test.py" ] \
    && echo 0 || echo 1)

# An unusable base ref is a refusal like any other: it must reset the tree, not
# leave the bot's staged diff behind for the next run's `git add --all`.
reset_test_repo
write_migration base_ref_test.py base_ref_test '"chain_b_test"'
AUTOPR_TEST_BASE_REF=does-not-exist
missing_base_rc="$(publish_migration_draft missing-base-migration)"
unset AUTOPR_TEST_BASE_REF
check "an unusable migration base ref resets the tree before failing" \
  $([ "$missing_base_rc" != 0 ] \
    && grep -q 'migration safety base is unavailable' "$TMP_DIR/missing-base-migration.stderr" \
    && git -C "$TEST_REPO" diff --cached --quiet \
    && [ ! -e "$TEST_REPO/server/alembic/versions/base_ref_test.py" ] \
    && echo 0 || echo 1)

reset_test_repo

# The runner and its configuration stay permanently closed — that is the part
# that could actually touch a database.
printf 'unsafe = True\n' > "$TEST_REPO/server/alembic/env.py"
set +e
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/card.json" "$TMP_DIR/implementation.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
) >/dev/null 2>&1
alembic_runner_rc=$?
set -e
check "Alembic runner and configuration changes are always rejected" \
  $([ "$alembic_runner_rc" != 0 ] && [ ! -e "$TEST_REPO/server/alembic/env.py" ] \
    && echo 0 || echo 1)

# migration_required cannot even be expressed any more.
jq '.no_safe_action_reason = "migration_required"' "$TMP_DIR/raw-no-safe.json" \
  > "$TMP_DIR/raw-migration-required.json"
set +e
"$TEST_REPO/scripts/kanban-autopr/decision.sh" normalize \
  "$TMP_DIR/raw-migration-required.json" "$TMP_DIR/migration-required.json" >/dev/null 2>&1
migration_reason_rc=$?
set -e
check "migration_required is no longer a decision the harness accepts" \
  $([ "$migration_reason_rc" != 0 ] && echo 0 || echo 1)

################################################################################
# Cosmetic-diff guard. PR #418's shape reached publication as an
# `implementation`; a `partial_implementation` carrying the identical diff used
# to walk straight past the guard, and the refusal itself left no trace on the
# card for a human to see.
################################################################################
git -C "$TEST_REPO" reset --hard -q HEAD
mkdir -p "$TEST_REPO/client/src/components/sidebars"
cat > "$TEST_REPO/client/src/components/sidebars/ClientSidebar.tsx" <<'EOF'
const nav = [
  { to: '/app/credential-templates', icon: BadgeCheck, label: 'Credentialing' },
]
EOF
git -C "$TEST_REPO" add -A
git -C "$TEST_REPO" commit -qm "sidebar baseline"

cat > "$TMP_DIR/structure-card.json" <<'EOF'
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Register the credential templates route in the sidebar","description":"The nav row should point at the credential templates page.","category":"fix","mode":"investigate","progress_note":"🤖 AUTO SETUP · READY FOR REVIEW","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
EOF
cat > "$TMP_DIR/raw-partial.json" <<'EOF'
{"schema_version":1,"outcome":"partial_implementation","confidence":{"requirements_clarity":{"score":15,"reason":"mostly clear"},"evidence_quality":{"score":10,"reason":"nav is visible"},"code_localization":{"score":10,"reason":"one file"},"verification_strength":{"score":5,"reason":"rendered check"},"production_alignment":{"score":10,"reason":"baseline known"}},"criticality":{"level":"yellow","reasons":["nav wording"]},"questions":[{"id":"q1","question":"Which label is canonical?","why_blocking":"two spellings exist","options":[{"key":"a","label":"Credentialing","impact":"keeps today's label"},{"key":"b","label":"Credential Templates","impact":"matches the page title"}],"default_assumption":"Credential Templates"}],"safe_changes_present":true,"no_safe_action_reason":null}
EOF
"$TEST_REPO/scripts/kanban-autopr/decision.sh" normalize \
  "$TMP_DIR/raw-partial.json" "$TMP_DIR/partial.json"

# The only change: the label text. Route, row and gate are untouched.
sed -i.bak "s/label: 'Credentialing'/label: 'Credential Templates'/" \
  "$TEST_REPO/client/src/components/sidebars/ClientSidebar.tsx"
rm -f "$TEST_REPO/client/src/components/sidebars/ClientSidebar.tsx.bak"
rm -f "$TMP_DIR/card-patch.json" "$TMP_DIR/context-request.json"
set +e
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/structure-card.json" "$TMP_DIR/partial.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
) >/dev/null 2>&1
cosmetic_partial_rc=$?
set -e
check "a partial_implementation cannot smuggle a string-literal-only diff past the guard" \
  $([ "$cosmetic_partial_rc" != 0 ] \
    && git -C "$TEST_REPO" diff --quiet \
    && echo 0 || echo 1)
check "the cosmetic-diff refusal is recorded on the card" \
  $(jq -e '.progress_note | contains("BLOCKED: COSMETIC DIFF") and contains("[autopr:rejected")' \
    "$TMP_DIR/card-patch.json" >/dev/null && echo 0 || echo 1)
check "the cosmetic-diff refusal asks the card owner for a decision" \
  $(jq -e '(.reason | contains("only rewrites string literals"))
      and (.expected_progress_note | contains("BLOCKED: COSMETIC DIFF"))' \
    "$TMP_DIR/context-request.json" >/dev/null && echo 0 || echo 1)

# The same diff on a card that asks for a copy change is legitimate.
cat > "$TMP_DIR/copy-card.json" <<'EOF'
{"task_id":"aaaa0000-0000-4000-8000-000000000001","id8":"aaaa0000","project_id":"8b924347-d6e4-4000-8e7d-ca8f46f76fba","title":"Rename Credentialing to Credential Templates","description":"Use one spelling for this feature.","category":"fix","mode":"investigate","production":{"build_number":850,"containers":{"backend":{"git_sha":"68a70f4"},"frontend":{"git_sha":"68a70f4"}}}}
EOF
sed -i.bak "s/label: 'Credentialing'/label: 'Credential Templates'/" \
  "$TEST_REPO/client/src/components/sidebars/ClientSidebar.tsx"
rm -f "$TEST_REPO/client/src/components/sidebars/ClientSidebar.tsx.bak"
(
  cd "$TEST_REPO"
  PATH="$TMP_DIR/bin:$PATH" MATCHA_AUTOPR_ENV="$TMP_DIR/env" GITHUB_REPOSITORY="tajaa/matcha-recruit" \
    AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" AUTOPR_TEST_BODY="$TMP_DIR/pr-body.md" \
    AUTOPR_TEST_CARD_PATCH="$TMP_DIR/card-patch.json" AUTOPR_TEST_ACTIVITY="$TMP_DIR/activity.json" \
    AUTOPR_TEST_CONTEXT_REQUEST="$TMP_DIR/context-request.json" \
    AUTOPR_TEST_RESULT_NOTIFICATION="$TMP_DIR/result-notification.json" \
    ./scripts/kanban-autopr/publish.sh "$TMP_DIR/copy-card.json" "$TMP_DIR/partial.json" "$TMP_DIR/report.md" "$TMP_DIR/verification.md" "$TMP_DIR/publication-copy.json"
) >/dev/null 2>&1
copy_card_rc=$?
check "a card that genuinely asks for a copy change still publishes" \
  $([ "$copy_card_rc" = 0 ] && echo 0 || echo 1)

echo
echo "$PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
