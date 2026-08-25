#!/usr/bin/env bash
# Exercise issue deduplication without contacting GitHub.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_TMP="$(mktemp -d)"
trap 'rm -rf "$TEST_TMP"' EXIT

cat > "$TEST_TMP/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -euo pipefail
if [ "$1" = api ]; then
    python3 - <<'PY'
import json

issues = [{"number": number, "title": f"ordinary issue {number}"} for number in range(1, 102)]
issues[0]["title"] = "mentions [ops-health:backup-integrity] but is not the marker suffix"
issues.append({"number": 277, "title": "ops: production backup integrity failed [ops-health:backup-integrity]"})
print(json.dumps([issues]))
PY
    exit 0
fi
printf '%s\n' "$*" >> "$CALL_LOG"
FAKE_GH
chmod +x "$TEST_TMP/gh"

BODY_FILE="$TEST_TMP/body.md"
printf 'test alert\n' > "$BODY_FILE"
export CALL_LOG="$TEST_TMP/calls.log"
export GITHUB_REPOSITORY="tajaa/matcha-recruit"
PATH="$TEST_TMP:$PATH" "$REPO_ROOT/scripts/ops-health/publish-issue.sh" \
    ops-health:backup-integrity 'ops: production backup integrity failed' "$BODY_FILE" ops-health

grep -q '^issue comment 277 ' "$CALL_LOG"
! grep -q '^issue create ' "$CALL_LOG"
echo "PASS: issue lookup paginates and matches the exact marker suffix"
