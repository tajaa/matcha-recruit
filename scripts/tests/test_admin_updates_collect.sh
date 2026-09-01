#!/usr/bin/env bash
# Verify GraphQL-truncated PR files are replaced with the REST-paginated list.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/admin-updates-collect-test.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin"

cat > "$TMP_DIR/bin/gh" <<'GH'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1 $2" = "pr list" ]; then
  jq -n '[range(0; 100) | {path:("docs/hidden-" + tostring + ".md")}] as $files | [{number:42,title:"Large deployed change",body:"",mergedAt:"2026-08-31T00:00:00Z",mergeCommit:{oid:"merge-42"},files:$files,url:"https://github.test/pull/42"}]'
elif [ "$1 $2" = "api --paginate" ]; then
  jq -n '[{filename:"server/app/core/visible.py"},{filename:"client/tellus/src/visible.ts"}]'
else
  echo "unexpected gh invocation: $*" >&2
  exit 1
fi
GH
cat > "$TMP_DIR/bin/python3" <<'PY'
#!/usr/bin/env bash
set -euo pipefail
for arg in "$@"; do
  if [ -f "$arg" ] && jq -e '.[0].files == [{"path":"server/app/core/visible.py"},{"path":"client/tellus/src/visible.ts"}]' "$arg" >/dev/null 2>&1; then
    found_merged_prs=1
  fi
done
[ "${found_merged_prs:-0}" = 1 ] || { echo "REST files were not passed to collector" >&2; exit 1; }
output="${@: -1}"
printf '{"hasWork":false,"needsDraft":false}\n' > "$output"
PY
chmod +x "$TMP_DIR/bin/gh" "$TMP_DIR/bin/python3"

printf '{}\n' > "$TMP_DIR/context.json"
printf '{}\n' > "$TMP_DIR/state.json"
printf '{}\n' > "$TMP_DIR/deployment.json"
PATH="$TMP_DIR/bin:$PATH" "$REPO_ROOT/scripts/admin-updates/collect.sh" \
  "$TMP_DIR/context.json" "$TMP_DIR/state.json" "$TMP_DIR/deployment.json" "$TMP_DIR/output.json"
jq -e '.hasWork == false and .needsDraft == false' "$TMP_DIR/output.json" >/dev/null
echo 'PASS: collector expands GraphQL-capped PR files through REST pagination'
