#!/usr/bin/env bash
# Validates the model's untrusted triage decision before it can drive a PR,
# labels, or a card update. Source this file for the helpers or run
# `decision.sh normalize raw.json decision.json`.
set -euo pipefail
_AUTOPR_DECISION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_autopr_decision_schema_ok() {
    local file="$1"
    jq -L "$_AUTOPR_DECISION_DIR" -e '
      include "production-check";
      def bounded($key; $max):
        (.confidence[$key].score | type == "number" and floor == . and . >= 0 and . <= $max)
        and (.confidence[$key].reason | type == "string" and length > 0);
      def total:
        [.confidence.requirements_clarity.score,
         .confidence.evidence_quality.score,
         .confidence.code_localization.score,
         .confidence.verification_strength.score,
         .confidence.production_alignment.score] | add;
      def valid_question:
        (.id | type == "string" and length > 0)
        and (.question | type == "string" and length > 0)
        and (.why_blocking | type == "string" and length > 0)
        and (.default_assumption | type == "string" and length > 0)
        and (.options | type == "array" and length >= 2
             and all(.[]; (.key | type == "string" and length > 0)
                         and (.label | type == "string" and length > 0)
                         and (.impact | type == "string" and length > 0)));
      def valid_production_verification:
        type == "object"
        and (.target | IN("backend", "frontend", "both"))
        and (.mode | IN("automatic_http", "manual"))
        and (.reason | type == "string" and length > 0 and length <= 600)
        and (.checks | type == "array")
        and (.steps | type == "array" and all(.[]; type == "string" and length > 0 and length <= 500))
        and (if .mode == "automatic_http" then
               (.checks | length >= 1 and length <= 5 and all(.[]; valid_production_http_check))
               and (.steps | length == 0)
             else
               (.checks | length == 0) and (.steps | length >= 1 and length <= 8)
             end);
      type == "object"
      and .schema_version == 1
      and (.outcome | IN("implementation", "partial_implementation", "questions_only", "no_safe_action"))
      and (.safe_changes_present | type == "boolean")
      and (.questions | type == "array" and all(.[]; valid_question))
      and ([.questions[].id] | length == ([.[]] | unique | length))
      and (.criticality | type == "object")
      and (.criticality.level | IN("red", "orange", "yellow"))
      and (.criticality.reasons | type == "array" and length > 0 and all(.[]; type == "string" and length > 0))
      and bounded("requirements_clarity"; 30)
      and bounded("evidence_quality"; 20)
      and bounded("code_localization"; 20)
      and bounded("verification_strength"; 15)
      and bounded("production_alignment"; 15)
      and ((.production_verification // {
        target:"both",mode:"manual",reason:"No production plan supplied",checks:[],steps:["Verify the reported behavior in production."]
      }) | valid_production_verification)
      and (
        if .outcome == "implementation" then
          total >= 75 and .safe_changes_present and (.questions | length == 0) and .no_safe_action_reason == null
        elif .outcome == "partial_implementation" then
          total >= 45 and .safe_changes_present and (.questions | length > 0) and .no_safe_action_reason == null
        elif .outcome == "questions_only" then
          (.safe_changes_present | not) and (.questions | length > 0) and .no_safe_action_reason == null
        else
          (.safe_changes_present | not) and (.questions | length == 0)
          and (.no_safe_action_reason | IN("already_fixed", "migration_required", "policy_blocked", "external_dependency"))
        end
      )
    ' "$file" >/dev/null
}

_autopr_directive_policy_ok() {
    local decision_file="$1" directive_file="${2:-}"
    [ -n "$directive_file" ] && [ -s "$directive_file" ] || return 0
    jq -e --slurpfile policy "$directive_file" '
      ($policy[0].directives // []) as $directives
      | (($directives | index("trust_still_broken")) == null
         or .no_safe_action_reason != "already_fixed")
      and (($directives | index("draft_pr")) == null
         or .outcome != "no_safe_action"
         or (.no_safe_action_reason | IN("migration_required", "policy_blocked", "external_dependency")))
    ' "$decision_file" >/dev/null
}

autopr_normalize_decision() {
    local raw_file="$1" normalized_file="$2" directive_file="${3:-}"
    local directive_policy='{"directives":[],"test_route":null}'
    [ -s "$raw_file" ] || die "investigation produced no triage decision at $raw_file"
    _autopr_decision_schema_ok "$raw_file" || die "triage decision failed schema or safety validation"
    _autopr_directive_policy_ok "$raw_file" "$directive_file" \
        || die "triage decision violated the decision-bound AutoPR directive"
    if [ -n "$directive_file" ] && [ -s "$directive_file" ]; then
        directive_policy="$(jq -c '{directives:(.directives // []),test_route:(.test_route // null)}' "$directive_file")"
    fi
    jq --argjson directive_policy "$directive_policy" '
      def total:
        [.confidence.requirements_clarity.score,
         .confidence.evidence_quality.score,
         .confidence.code_localization.score,
         .confidence.verification_strength.score,
         .confidence.production_alignment.score] | add;
      . + {
        confidence_score: total,
        confidence_band: (if total >= 75 then "high" elif total >= 45 then "medium" else "low" end),
        awaiting_human: (.outcome == "partial_implementation" or .outcome == "questions_only"),
        autopr_directives: ($directive_policy.directives // []),
        autopr_test_route: ($directive_policy.test_route // null),
        production_verification: (.production_verification // {
          target: "both",
          mode: "manual",
          reason: "The investigation did not supply an executable production check.",
          checks: [],
          steps: ["Reproduce the reported ticket behavior against the deployed production build."]
        })
      }
    ' "$raw_file" > "$normalized_file"
}

autopr_feedback_snapshot_file() {
    local feedback_file="$1"
    jq -c '
      def human:
        ((.author.login // "") | test("\\[bot\\]$"; "i") | not)
        and ((.author.login // "") != "matcha-kanban-autopr");
      {
        comment_id: ([.comments[]? | select(human and ((.body // "") | gsub("[[:space:]]"; "") | length > 0)) | .id] | last // ""),
        review_id: ([.reviews[]? | select(human and ((.body // "") | gsub("[[:space:]]"; "") | length > 0)) | .id] | last // "")
      }
    ' "$feedback_file"
}

autopr_criticality_emoji() {
    case "$1" in
        red) printf '🔴' ;;
        orange) printf '🟠' ;;
        yellow) printf '🟡' ;;
        *) die "unknown criticality: $1" ;;
    esac
}

autopr_title_marker() {
    local decision_file="$1" outcome level score emoji mode_marker=""
    outcome="$(jq -r '.outcome' "$decision_file")"
    level="$(jq -r '.criticality.level' "$decision_file")"
    score="$(jq -r '.confidence_score' "$decision_file")"
    emoji="$(autopr_criticality_emoji "$level")"
    case "$outcome" in
        questions_only) mode_marker=' [QUESTIONS]' ;;
        partial_implementation) mode_marker=' [PARTIAL]' ;;
        no_safe_action) mode_marker=' [NO SAFE ACTION]' ;;
    esac
    printf '%s [C%s]%s' "$emoji" "$score" "$mode_marker"
}

autopr_render_questions() {
    local decision_file="$1"
    jq -r '
      if (.questions | length) == 0 then empty else
        "## Answers needed\n\n" +
        ([.questions[] |
          "1. " + .question + "\n" +
          (.options | map("   - " + .key + ": " + .label + " — " + .impact) | join("\n")) + "\n" +
          "   - Suggested default: " + .default_assumption + "\n" +
          "   - Why this blocks implementation: " + .why_blocking
        ] | join("\n\n")) +
        "\n\nReply on this PR. The next local cycle will ingest a new human comment or review and update this same draft."
      end
    ' "$decision_file"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        normalize)
            { [ "$#" -eq 3 ] || [ "$#" -eq 4 ]; } \
                || die "usage: decision.sh normalize raw-decision.json decision.json [directive-policy.json]"
            autopr_normalize_decision "$2" "$3" "${4:-}"
            ;;
        feedback-snapshot)
            [ "$#" -eq 2 ] || die "usage: decision.sh feedback-snapshot feedback.json"
            autopr_feedback_snapshot_file "$2"
            ;;
        *)
            die "usage: decision.sh normalize raw-decision.json decision.json | decision.sh feedback-snapshot feedback.json"
            ;;
    esac
fi
