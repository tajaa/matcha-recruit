#!/usr/bin/env bash
# Durable owner-PR lifecycle tests for both automation lanes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d "$REPO_ROOT/.autopr-coverage-test-XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin"

cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "pr list")
    if [[ "$*" == *"--label covers-prod-error"* ]]; then
      if [ "${OWNER_SET:-}" = recurrent ]; then
        printf '%s\n' '[
          {"number":300,"state":"MERGED","mergedAt":"2026-08-01T08:00:00Z","closedAt":"2026-08-01T08:00:00Z","createdAt":"2026-08-01T07:00:00Z"},
          {"number":334,"state":"MERGED","mergedAt":"2026-08-28T09:00:00Z","closedAt":"2026-08-28T09:00:00Z","createdAt":"2026-08-28T08:00:00Z"}
        ]'
      else
        printf '[{"number":334,"state":"%s","mergedAt":%s,"closedAt":%s,"createdAt":"2026-08-28T08:00:00Z"}]\n' \
          "${OWNER_STATE:-OPEN}" "${OWNER_MERGED_AT:-null}" "${OWNER_CLOSED_AT:-null}"
      fi
    elif [[ "$*" == *"--label autofix"* || "$*" == *"--label autopr"* ]]; then
      printf '0\n'
    else
      printf '[]\n'
    fi
    ;;
  "issue list") printf '0\n' ;;
  "api "*) printf '%s\n' '[{"body":"<!-- matcha-autofix-coverage-error: abc123abc123 -->"}]' ;;
  "pr view") printf '{"state":"%s"}\n' "${OWNER_STATE:-OPEN}" ;;
  *) exit 2 ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"

cat > "$TMP_DIR/incidents.json" <<'EOF'
[{"stable_key":"abc123abc123","first_seen":"2026-08-28T09:00:00Z","last_seen":"2026-08-28T10:00:00Z","occurrences":3}]
EOF

set +e
PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x AUTOFIX_CACHE_DIR="$TMP_DIR/prod-open" \
  "$REPO_ROOT/scripts/error-autofix/select.sh" "$TMP_DIR/incidents.json" >/dev/null
rc=$?
set -e
[ "$rc" = 3 ]
printf 'PASS: open covering PR suppresses the production incident\n'

selected="$(OWNER_STATE=CLOSED OWNER_CLOSED_AT='"2026-08-28T10:00:00Z"' \
  PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x AUTOFIX_CACHE_DIR="$TMP_DIR/prod-closed" \
  "$REPO_ROOT/scripts/error-autofix/select.sh" "$TMP_DIR/incidents.json")"
[ "$(printf '%s' "$selected" | jq -r '.stable_key')" = abc123abc123 ]
printf 'PASS: closed-unmerged covering PR releases the production incident\n'

set +e
OWNER_SET=recurrent PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x \
  AUTOFIX_CACHE_DIR="$TMP_DIR/prod-recurrent" \
  "$REPO_ROOT/scripts/error-autofix/select.sh" "$TMP_DIR/incidents.json" >/dev/null
rc=$?
set -e
[ "$rc" = 3 ]
printf 'PASS: newest merged owner controls recurrence deploy grace\n'

cat > "$TMP_DIR/card.json" <<'EOF'
[{"task_id":"790f0fa0-0000-4000-8000-000000000001","id8":"790f0fa0","project_id":"p","title":"linked","board_column":"in_progress","created_at":"2026-08-28T08:00:00Z","last_moved_at":"2026-08-28T08:00:00Z","progress_note":"🤖 AUTO SETUP · ALREADY SCOPED · PR #336 · source existing PR","pr_number":336}]
EOF
set +e
OWNER_STATE=OPEN PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x AUTOPR_CACHE_DIR="$TMP_DIR/card-open" \
  "$REPO_ROOT/scripts/kanban-autopr/select.sh" "$TMP_DIR/card.json" >/dev/null
rc=$?
set -e
[ "$rc" = 3 ]
printf 'PASS: open cross-lane PR suppresses its linked Kanban card\n'

selected="$(OWNER_STATE=CLOSED PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x \
  AUTOPR_CACHE_DIR="$TMP_DIR/card-closed" \
  "$REPO_ROOT/scripts/kanban-autopr/select.sh" "$TMP_DIR/card.json")"
[ "$(printf '%s' "$selected" | jq -r '.mode')" = investigate ]
printf 'PASS: closed-unmerged cross-lane PR releases its linked Kanban card\n'

cat > "$TMP_DIR/incident.json" <<'EOF'
{"stable_key":"abc123abc123","request_method":"POST","request_path":"/api/x","occurrences":4,"last_seen":"2026-08-28T10:00:00Z"}
EOF
cat > "$TMP_DIR/coverage.json" <<'EOF'
{"decision":"covered","confidence":"high","covering_pr":334,"covering_head_sha":"owner-sha"}
EOF
cat > "$TMP_DIR/decision.json" <<'EOF'
{"criticality":{"level":"yellow"},"confidence_score":70,"confidence_band":"medium"}
EOF
cat > "$TMP_DIR/bin/gh-record" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_CALLS"
case "$1 $2" in
  "pr view") printf '%s\n' '{"number":334,"state":"OPEN","headRefOid":"owner-sha","url":"https://example.invalid/334"}' ;;
  "api "*) printf '%s\n' '[{"body":"<!-- matcha-autofix-coverage-error: abc123abc123 -->"}]' ;;
  *) : ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh-record"
ln -sf "$TMP_DIR/bin/gh-record" "$TMP_DIR/bin/gh"
: > "$TMP_DIR/record-calls"
PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_CALLS="$TMP_DIR/record-calls" GITHUB_REPOSITORY=x/x \
  "$REPO_ROOT/scripts/error-autofix/record-coverage.sh" "$TMP_DIR/incident.json" \
    "$TMP_DIR/coverage.json" "$TMP_DIR/decision.json" >/dev/null 2>&1
! grep -q '^pr comment ' "$TMP_DIR/record-calls"
grep -q '^pr edit 334 .*--add-label covers-prod-error' "$TMP_DIR/record-calls"
printf 'PASS: production coverage recording is idempotent by exact comment marker\n'
