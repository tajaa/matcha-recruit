#!/usr/bin/env bash
# Validate and normalize the coding model's untrusted error triage. The result
# may drive only presentation (title/labels/email); publish.sh independently
# verifies that the claimed fix/no-fix outcome matches the actual git diff.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

_error_decision_schema_ok() {
    local file="$1"
    jq -e '
      def bounded($key; $max):
        (.confidence[$key].score | type == "number" and floor == . and . >= 0 and . <= $max)
        and (.confidence[$key].reason | type == "string" and length > 0);
      type == "object"
      and .schema_version == 1
      and (.outcome | IN("fix", "no_safe_fix"))
      and (.safe_changes_present | type == "boolean")
      and (.criticality | type == "object")
      and (.criticality.level | IN("red", "orange", "yellow"))
      and (.criticality.reasons | type == "array" and length > 0
           and all(.[]; type == "string" and length > 0))
      and bounded("evidence_quality"; 25)
      and bounded("root_cause_clarity"; 25)
      and bounded("code_localization"; 20)
      and bounded("verification_readiness"; 15)
      and bounded("production_impact"; 15)
      and (
        if .outcome == "fix" then
          .safe_changes_present and .no_safe_fix_reason == null
        else
          (.safe_changes_present | not)
          and (.no_safe_fix_reason | type == "string" and length > 0)
        end
      )
    ' "$file" >/dev/null
}

normalize_error_decision() {
    local raw_file="$1" normalized_file="$2"
    [ -s "$raw_file" ] || die "investigation produced no triage decision at $raw_file"
    _error_decision_schema_ok "$raw_file" \
        || die "triage decision failed schema or safety validation"
    jq '
      def total:
        [.confidence.evidence_quality.score,
         .confidence.root_cause_clarity.score,
         .confidence.code_localization.score,
         .confidence.verification_readiness.score,
         .confidence.production_impact.score] | add;
      . + {
        confidence_score: total,
        confidence_band: (if total >= 75 then "high" elif total >= 45 then "medium" else "low" end)
      }
    ' "$raw_file" > "$normalized_file"
}

error_criticality_emoji() {
    case "$1" in
        red) printf '🔴' ;;
        orange) printf '🟠' ;;
        yellow) printf '🟡' ;;
        *) die "unknown criticality: $1" ;;
    esac
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    [ "${1:-}" = normalize ] && [ "$#" -eq 3 ] \
        || die "usage: decision.sh normalize raw-decision.json decision.json"
    normalize_error_decision "$2" "$3"
fi
