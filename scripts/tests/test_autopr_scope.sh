#!/usr/bin/env bash
# Isolated coverage for cross-lane patch matching. No network or real model.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d "$REPO_ROOT/.autopr-scope-test-XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
TEST_REPO="$TMP_DIR/repo"
mkdir -p "$TEST_REPO/scripts" "$TMP_DIR/bin"
cp -R "$REPO_ROOT/scripts/autopr-scope" "$TEST_REPO/scripts/autopr-scope"
chmod +x "$TEST_REPO/scripts/autopr-scope/check-open-prs.sh"
git -C "$TEST_REPO" init -q
git -C "$TEST_REPO" config user.email test@example.com
git -C "$TEST_REPO" config user.name test
printf 'value = 1\n' > "$TEST_REPO/app.py"
git -C "$TEST_REPO" add --all
git -C "$TEST_REPO" commit -q -m baseline
git -C "$TEST_REPO" branch -M main
printf '{}\n' > "$TMP_DIR/evidence.json"
printf 'root cause\n' > "$TMP_DIR/report.md"

cat > "$TMP_DIR/bin/gh" <<'EOF'
#!/usr/bin/env bash
case "$1 $2" in
  "pr list")
    printf '%s\n' '[{"number":334,"title":"candidate","createdAt":"2026-08-28T08:00:00Z","headRefName":"bot/task-790f0fa0","headRefOid":"owner-sha","isDraft":true,"files":[{"path":"app.py"}],"url":"https://example.invalid/334"}]'
    ;;
  "pr diff")
    cat "$AUTOPR_TEST_CANDIDATE_DIFF"
    ;;
  *) exit 2 ;;
esac
EOF
chmod +x "$TMP_DIR/bin/gh"

cat > "$TMP_DIR/bin/codex" <<'EOF'
#!/usr/bin/env bash
echo called > "$AUTOPR_TEST_CODEX_CALLED"
exit 99
EOF
chmod +x "$TMP_DIR/bin/codex"

printf 'value = 2\n' > "$TEST_REPO/app.py"
git -C "$TEST_REPO" diff --binary > "$TMP_DIR/exact.diff"
PATH="$TMP_DIR/bin:$PATH" GH_TOKEN=secret GITHUB_REPOSITORY=x/x \
  AUTOPR_TEST_CANDIDATE_DIFF="$TMP_DIR/exact.diff" \
  bash "$TEST_REPO/scripts/autopr-scope/check-open-prs.sh" \
  --lane error --identity abc123abc123 --evidence "$TMP_DIR/evidence.json" \
  --report "$TMP_DIR/report.md" --output "$TMP_DIR/exact-result.json"
jq -e '.decision == "covered" and .confidence == "high" and .covering_pr == 334 and .covering_head_sha == "owner-sha"' \
  "$TMP_DIR/exact-result.json" >/dev/null
git -C "$TEST_REPO" diff --quiet --cached
printf 'PASS: exact patch is covered without touching the real index\n'

# A broader owner patch has a different patch-id. It must remain a human-review
# signal; public PR content never receives authority to suppress publication.
cp "$TMP_DIR/exact.diff" "$TMP_DIR/broader.diff"
printf '\ndiff --git a/extra.py b/extra.py\nnew file mode 100644\nindex 0000000..257cc56\n--- /dev/null\n+++ b/extra.py\n@@ -0,0 +1 @@\n+broader = True\n' >> "$TMP_DIR/broader.diff"
rm -f "$TMP_DIR/codex-not-called"
PATH="$TMP_DIR/bin:$PATH" GH_TOKEN=secret GITHUB_TOKEN=also-secret GITHUB_REPOSITORY=x/x \
  AUTOPR_TEST_CODEX_CALLED="$TMP_DIR/codex-not-called" \
  AUTOPR_TEST_CANDIDATE_DIFF="$TMP_DIR/broader.diff" \
  bash "$TEST_REPO/scripts/autopr-scope/check-open-prs.sh" \
  --lane error --identity abc123abc123 --evidence "$TMP_DIR/evidence.json" \
  --report "$TMP_DIR/report.md" --output "$TMP_DIR/broader-result.json"
jq -e '.decision == "uncertain" and .covering_pr == null and .possible_duplicate == true' "$TMP_DIR/broader-result.json" >/dev/null
[ ! -e "$TMP_DIR/codex-not-called" ]
printf 'PASS: broader public patch requires human review without model execution\n'

AUTOPR_SCOPE_DEDUPE_MODE=off PATH="$TMP_DIR/bin:$PATH" GITHUB_REPOSITORY=x/x \
  bash "$TEST_REPO/scripts/autopr-scope/check-open-prs.sh" \
  --lane kanban --identity task-id --evidence "$TMP_DIR/evidence.json" \
  --report "$TMP_DIR/report.md" --output "$TMP_DIR/off-result.json"
jq -e '.decision == "no_match" and .mode == "off"' "$TMP_DIR/off-result.json" >/dev/null
printf 'PASS: off mode bypasses GitHub and model comparison\n'
