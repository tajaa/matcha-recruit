#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir "$TMP_DIR/bin"

auto_spec='{"target":"frontend","mode":"automatic_http","reason":"Public build marker proves the UI fix is live.","checks":[{"path":"/version.json","expected_status":200,"body_contains":"fixed-build","body_absent":"old-build"}],"steps":[]}'
manual_spec='{"target":"both","mode":"manual","reason":"The workflow requires an authenticated production account.","checks":[],"steps":["Sign in to the production test tenant.","Open the jobs editor and confirm credentials are visible."]}'
auto_b64="$(printf '%s' "$auto_spec" | base64 | tr -d '\r\n')"
manual_b64="$(printf '%s' "$manual_spec" | base64 | tr -d '\r\n')"
head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD)"
jq -n --arg sha "$head_sha" --arg auto "$auto_b64" --arg manual "$manual_b64" '[
  {number:501,title:"automatic",mergeCommit:{oid:$sha},mergedAt:"2026-09-01T00:00:00Z",url:"x",labels:[{name:"autopr"}],body:("<!-- matcha-production-verification: " + $auto + " -->")},
  {number:502,title:"manual",mergeCommit:{oid:$sha},mergedAt:"2026-09-01T00:01:00Z",url:"x",labels:[{name:"autopr"}],body:("<!-- matcha-production-verification: " + $manual + " -->")}
]' > "$TMP_DIR/prs.json"

cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$AUTOPR_TEST_GH_LOG"
if [ "$1 $2" = "pr list" ]; then
  cat "$AUTOPR_TEST_PRS"
elif [ "$1 $2" = "pr view" ]; then
  printf '\n'
fi
EOF
cat > "$TMP_DIR/bin/curl" <<'EOF'
#!/usr/bin/env bash
output=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -o) output="$2"; shift 2 ;;
    -w) shift 2 ;;
    *) shift ;;
  esac
done
printf '%s\n' 'fixed-build' > "$output"
printf 200
EOF
chmod +x "$TMP_DIR/bin/gh" "$TMP_DIR/bin/curl"

PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" \
  AUTOPR_TEST_PRS="$TMP_DIR/prs.json" GITHUB_REPOSITORY=example/repo \
  "$REPO_ROOT/scripts/kanban-autopr/verify-production-fixes.sh" \
  "$head_sha" matcha > "$TMP_DIR/result.json"

jq -e '.processed == 2 and .passed == 1 and .manual_required == 1 and .failed == 0' \
  "$TMP_DIR/result.json" >/dev/null
grep -q -- '--add-label production-verified' "$TMP_DIR/gh.log"
grep -q -- '--add-label production-verification-needed' "$TMP_DIR/gh.log"
grep -q '^pr comment 501 ' "$TMP_DIR/gh.log"
grep -q '^pr comment 502 ' "$TMP_DIR/gh.log"

# A backend-only rollout cannot prove a frontend or both-target fix.
: > "$TMP_DIR/gh.log"
PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_GH_LOG="$TMP_DIR/gh.log" \
  AUTOPR_TEST_PRS="$TMP_DIR/prs.json" GITHUB_REPOSITORY=example/repo \
  "$REPO_ROOT/scripts/kanban-autopr/verify-production-fixes.sh" \
  "$head_sha" backend > "$TMP_DIR/backend-result.json"
jq -e '.processed == 0 and .passed == 0 and .manual_required == 0 and .failed == 0' \
  "$TMP_DIR/backend-result.json" >/dev/null
! grep -q '^pr comment ' "$TMP_DIR/gh.log"

echo "PASS: merged-and-deployed fixes get automatic proof or an explicit manual production gate"
