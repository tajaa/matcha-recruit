#!/usr/bin/env bash
set -euo pipefail

INPUT="${1:?usage: check-decision.sh INPUT OUTPUT}"
OUTPUT="${2:?usage: check-decision.sh INPUT OUTPUT}"
[ -s "$INPUT" ] || { echo "audit model produced no decision" >&2; exit 1; }
jq -e '
  type == "object"
  and .schema_version == 1
  and (.outcome | IN("fix", "operator_action"))
  and (.safe_changes_present | type == "boolean")
  and (.summary | type == "string" and length > 0)
  and (if .outcome == "fix" then .safe_changes_present else (.safe_changes_present | not) end)
' "$INPUT" >/dev/null || { echo "audit model decision failed validation" >&2; exit 1; }
jq '{schema_version,outcome,safe_changes_present,summary}' "$INPUT" > "$OUTPUT"
