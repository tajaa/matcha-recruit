#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cat > "$TMP_DIR/cards.json" <<'EOF'
[
  {"task_id":"11111111-0000-4000-8000-000000000001","id8":"11111111","project_id":"p","project_title":"MATCHA","title":"Credential selector still omits jobs","description":"The employee credential filter works but job credentials are absent","board_column":"todo","priority":"medium","element_id":"credentials","repo_paths":["client/src/work/credentials/**"],"created_at":"2026-08-01T00:00:00Z","last_moved_at":"2026-08-30T00:00:00Z","progress_note":"NO PR [autopr:no-spec 2026-08-30T00:00:00Z] already_fixed","autopr_reconsideration_pending":true},
  {"task_id":"22222222-0000-4000-8000-000000000002","id8":"22222222","project_id":"p","project_title":"MATCHA","title":"Share credential selector with jobs","description":"Extract the shared credential selector foundation","board_column":"todo","priority":"medium","element_id":"credentials","repo_paths":["client/src/work/credentials/**"],"created_at":"2026-08-02T00:00:00Z","last_moved_at":"2026-08-02T00:00:00Z"},
  {"task_id":"33333333-0000-4000-8000-000000000003","id8":"33333333","project_id":"p","project_title":"MATCHA","title":"Unrelated report copy","board_column":"changes_requested","priority":"high","repo_paths":["server/app/reports/**"],"created_at":"2026-08-01T00:00:00Z","last_moved_at":"2026-08-01T00:00:00Z","pr_number":33}
]
EOF

cat > "$TMP_DIR/prs.json" <<'EOF'
[
  {"number":33,"title":"fix: report copy","isDraft":false,"state":"OPEN","headRefName":"bot/task-33333333","createdAt":"2026-08-01T00:00:00Z","updatedAt":"2026-08-02T00:00:00Z","labels":["autopr"],"checks":[],"files":["server/app/reports/copy.py"],"comments":[],"reviews":[]},
  {"number":41,"title":"fix: employee credential filtering","isDraft":true,"state":"OPEN","headRefName":"bot/err-credential","createdAt":"2026-08-03T00:00:00Z","updatedAt":"2026-08-04T00:00:00Z","labels":["autofix"],"checks":[],"files":["client/src/work/credentials/selector.ts"],"comments":[{"author":"owner","body":"This fixed employees but the jobs screen still omits credentials."}],"reviews":[]}
]
EOF

python3 "$REPO_ROOT/scripts/kanban-autopr/plan.py" \
  --cards "$TMP_DIR/cards.json" --prs "$TMP_DIR/prs.json" \
  --output "$TMP_DIR/plan.json" --cards-output "$TMP_DIR/planned.json"

jq -e '
  .work_order[0].task_id == "11111111-0000-4000-8000-000000000001"
  and .work_order[0].urgency == "escalated additional context"
  and .work_order[1].task_id == "22222222-0000-4000-8000-000000000002"
  and .work_order[0].cluster_id == .work_order[1].cluster_id
  and ([.ready_prs_excluded[].pr_number] | index(33)) != null
  and ([.merge_order[].pr_number] | index(33)) == null
  and .merge_order[0].pr_number == 41
  and (.release_blockers | length) == 1
' "$TMP_DIR/plan.json" >/dev/null

jq -e '
  .[0].autopr_plan.related_bot_prs[0].number == 41
  and (.[0].autopr_plan.related_bot_prs[0].comment_evidence[0].body | contains("jobs screen"))
  and (.[0].autopr_plan.related_tickets[0].description | contains("shared credential selector"))
' "$TMP_DIR/planned.json" >/dev/null

# The release fingerprint covers the substantive neighboring-card context, and
# an unanswered already-fixed decision remains an explicit merge contingency
# even before the human supplies the rebuttal.
first_plan_id="$(jq -r '.plan_id' "$TMP_DIR/plan.json")"
jq '.[1].description = "A materially changed shared foundation" | .[0].autopr_reconsideration_pending = false' \
  "$TMP_DIR/cards.json" > "$TMP_DIR/changed-cards.json"
python3 "$REPO_ROOT/scripts/kanban-autopr/plan.py" \
  --cards "$TMP_DIR/changed-cards.json" --prs "$TMP_DIR/prs.json" \
  --output "$TMP_DIR/changed-plan.json" --cards-output "$TMP_DIR/changed-planned.json"
[ "$(jq -r '.plan_id' "$TMP_DIR/changed-plan.json")" != "$first_plan_id" ]
jq -e '
  any(.context_blockers[];
    .task_id == "11111111-0000-4000-8000-000000000001"
    and (.state | contains("already-fixed decision")))
' "$TMP_DIR/changed-plan.json" >/dev/null

# A plan with unresolved context must fail before any GitHub mutation.
mkdir "$TMP_DIR/bin"
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_GH_LOG"
exit 99
EOF
chmod +x "$TMP_DIR/bin/gh"
set +e
PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" \
  AUTOPR_RELEASE_EXECUTE=true GITHUB_REPOSITORY=example/repo \
  "$REPO_ROOT/scripts/kanban-autopr/release-plan.sh" \
  "$TMP_DIR/plan.json" "$(jq -r '.plan_id' "$TMP_DIR/plan.json")" >/dev/null 2>&1
release_rc=$?
set -e
[ "$release_rc" -ne 0 ]
[ ! -s "$TMP_DIR/gh.log" ]
! grep -q -- '--admin' "$REPO_ROOT/scripts/kanban-autopr/release-plan.sh"

# With every contingency resolved, the explicit release transitions the draft
# to ready and conclusively merges it before moving on.
jq '.release_blockers=[] | .merge_order[0].blockers=[] | .merge_order[0].context_dependencies=[]' \
  "$TMP_DIR/plan.json" > "$TMP_DIR/releasable-plan.json"
cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_GH_LOG"
if [ "$1 $2" = "pr view" ]; then
  if [[ "$*" == *"--jq .state"* ]]; then
    [ ! -e "$AUTOPR_TEST_MERGED" ] || { printf 'MERGED\n'; exit 0; }
    printf 'OPEN\n'
  elif [[ "$*" == *"--json state"* ]] && [[ "$*" != *"statusCheckRollup"* ]]; then
    printf '{"state":"MERGED"}\n'
  elif [[ "$*" == *"--json labels"* ]]; then
    printf '\n'
  else
    printf '%s\n' '{"number":41,"state":"OPEN","isDraft":true,"reviewDecision":null,"mergeStateStatus":"CLEAN","labels":[{"name":"autofix"}],"statusCheckRollup":[],"headRefOid":"abc"}'
  fi
elif [ "$1 $2" = "pr merge" ]; then
  : > "$AUTOPR_TEST_MERGED"
fi
EOF
chmod +x "$TMP_DIR/bin/gh"
: > "$TMP_DIR/gh.log"
PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" \
  AUTOPR_TEST_MERGED="$TMP_DIR/merged" AUTOPR_RELEASE_EXECUTE=true \
  AUTOPR_MERGE_WAIT_SECONDS=1 AUTOPR_MERGE_POLL_SECONDS=1 \
  GITHUB_REPOSITORY=example/repo \
  "$REPO_ROOT/scripts/kanban-autopr/release-plan.sh" \
  "$TMP_DIR/releasable-plan.json" "$(jq -r '.plan_id' "$TMP_DIR/releasable-plan.json")" >/dev/null
ready_line="$(grep -n '^pr ready ' "$TMP_DIR/gh.log" | cut -d: -f1)"
merge_line="$(grep -n '^pr merge ' "$TMP_DIR/gh.log" | cut -d: -f1)"
[ "$ready_line" -lt "$merge_line" ]

echo "PASS: cross-card plan, bot comment relevance, ready exclusion, and release gate"
