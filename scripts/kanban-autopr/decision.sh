#!/usr/bin/env bash
# Validates the model's untrusted triage decision before it can drive a PR,
# labels, or a card update. Source this file for the helpers or run
# `decision.sh normalize-grounded raw.json decision.json`.
set -euo pipefail
_AUTOPR_DECISION_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Runs standalone from investigate.sh as well as sourced by the publishers
# (which already carry lib.sh's die). Standalone, a failed validation must
# still be a real exit with its message, not "die: command not found".
if ! command -v die >/dev/null 2>&1; then
    die() {
        printf 'kanban-autopr: %s\n' "$1" >&2
        exit 1
    }
fi

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
      def valid_acceptance_evidence:
        (.criterion | type == "string" and length > 0 and length <= 500)
        and (.path | type == "string" and length > 0 and test("^[A-Za-z0-9._/-]+$"))
        and (.line | type == "number" and floor == . and . >= 1)
        and (.commit | type == "string" and test("^[0-9a-f]{7,40}$"));
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
      and (.questions | type == "array" and length <= 10 and all(.[]; valid_question))
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
          # migration_required is deliberately absent. A schema change is
          # ordinary drafting work: the version file is authored for human
          # review and the operator applies it. "This needs a migration" was
          # the single most common refusal and it never protected anything.
          and (.no_safe_action_reason | IN("already_fixed", "policy_blocked", "external_dependency", "acceptance_criteria_met"))
          # Both "already fixed" verdicts need repository proof. The stricter
          # acceptance_criteria_met path still requires one entry per stated
          # criterion; already_fixed requires at least one concrete citation.
          and (if .no_safe_action_reason | IN("already_fixed", "acceptance_criteria_met") then
                 (.acceptance_evidence | type == "array" and length >= 1 and length <= 40
                  and all(.[]; valid_acceptance_evidence))
               else true end)
        end
      )
    ' "$file" >/dev/null
}

# Fresh PR investigations must explain why a remaining blocker needs the human.
# This stays separate from the base schema so malformed JSON and schema errors
# are diagnosed before grounding metadata is considered.
_autopr_grounding_ok() {
    jq -e '
      def evidence_text: type == "string" and test("\\S") and length <= 300;
      def why_text: type == "string" and test("\\S") and length <= 600;
      def resolution:
        type == "object"
        and (.kind | IN("product_decision", "private_context", "source_unavailable", "explicit_approval"))
        and (.evidence | type == "array" and length >= 1 and length <= 5
             and all(.[]; evidence_text))
        and (.why_user_needed | why_text);
      (.questions | type == "array" and all(.[]; .resolution | resolution))
      and (if .no_safe_action_reason | IN("policy_blocked", "external_dependency")
           then (.blocker_resolution | resolution) else true end)
    ' "$1" >/dev/null
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
         or (.no_safe_action_reason | IN("policy_blocked", "external_dependency", "acceptance_criteria_met")))
    ' "$decision_file" >/dev/null
}

# The evidence must survive contact with the repository, or "proof" is just
# another string the model can write. Each cited path:line has to exist at the
# commit it names -- otherwise a fabricated citation buys the same escape a
# bare already_fixed was denied.
#
# "Exists" is not enough on its own. This is the one verdict that overrides an
# owner's draft_pr directive, and every object the runner has ever fetched --
# an unrelated remote branch, a dangling commit -- is a real object. So the
# citation must be on this branch's own history, must point at a line that
# actually says something, and must still be there now: the claim is "already
# satisfied on main", not "was once written somewhere".
_autopr_acceptance_evidence_ok() {
    local decision_file="$1" commit path line lines content
    case "$(jq -r '.no_safe_action_reason // ""' "$decision_file")" in
        already_fixed|acceptance_criteria_met) ;;
        *) return 0 ;;
    esac
    jq -e '.acceptance_evidence | type == "array" and length >= 1 and length <= 40' \
        "$decision_file" >/dev/null 2>&1 \
        || { echo "autopr: existing-coverage verdict has no acceptance evidence" >&2; return 1; }
    while IFS=$'\t' read -r commit path line; do
        [ -n "$commit" ] || continue
        git cat-file -e "${commit}^{commit}" 2>/dev/null \
            || { echo "autopr: acceptance evidence cites unknown commit $commit" >&2; return 1; }
        git merge-base --is-ancestor "$commit" HEAD 2>/dev/null \
            || { echo "autopr: acceptance evidence cites $commit, which is not in this branch's history" >&2; return 1; }
        lines="$(git show "${commit}:${path}" 2>/dev/null | wc -l | tr -d ' ')" \
            || { echo "autopr: acceptance evidence cites unreadable $path at $commit" >&2; return 1; }
        [ -n "$lines" ] && [ "$lines" -ge "$line" ] 2>/dev/null \
            || { echo "autopr: acceptance evidence cites $path:$line beyond the file at $commit" >&2; return 1; }
        content="$(git show "${commit}:${path}" 2>/dev/null | sed -n "${line}p" | tr -d '[:space:]')"
        [ -n "$content" ] \
            || { echo "autopr: acceptance evidence cites blank line $path:$line at $commit" >&2; return 1; }
        git cat-file -e "HEAD:${path}" 2>/dev/null \
            || { echo "autopr: acceptance evidence cites $path, which no longer exists at HEAD" >&2; return 1; }
    done < <(jq -r '.acceptance_evidence[] | [.commit, .path, (.line | tostring)] | @tsv' "$decision_file")
}

autopr_normalize_decision() {
    local raw_file="$1" normalized_file="$2" directive_file="${3:-}"
    local directive_policy='{"directives":[],"test_route":null}'
    [ -s "$raw_file" ] || die "investigation produced no triage decision at $raw_file"
    _autopr_decision_schema_ok "$raw_file" || die "triage decision failed schema or safety validation"
    _autopr_directive_policy_ok "$raw_file" "$directive_file" \
        || die "triage decision violated the decision-bound AutoPR directive"
    _autopr_acceptance_evidence_ok "$raw_file" \
        || die "triage decision claimed existing coverage with unverifiable evidence"
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

# ---- research (artifact) decisions -----------------------------------------
# The research pass writes a report, not a patch, so its decision carries a
# summary, sources, one confidence score, and — when the subject was too vague
# — the same numbered questions the PR lane uses. `staged_actions` lets the
# report propose outreach (an email, a contact, a review request); the
# harness renders them on the card and NEVER sends one. Sending is a human
# action in Espresso, per item.
_autopr_research_decision_schema_ok() {
    local file="$1"
    jq -e '
      def valid_question:
        (.id | type == "string" and length > 0)
        and (.question | type == "string" and length > 0)
        and (.why_blocking | type == "string" and length > 0)
        and (.default_assumption | type == "string" and length > 0)
        and (.options | type == "array" and length >= 2
             and all(.[]; (.key | type == "string" and length > 0)
                         and (.label | type == "string" and length > 0)
                         and (.impact | type == "string" and length > 0)));
      def valid_source:
        type == "object"
        and (.title | type == "string" and length > 0 and length <= 200)
        and (.url | type == "string" and test("^https?://") and length <= 2000);
      def valid_staged_action:
        type == "object"
        and (.kind | IN("email", "contact", "review_request"))
        and (.to | type == "string" and length > 0 and length <= 200)
        # `to` on an email is the RFC 5322 To: header the send path uses
        # verbatim, so it must be an address here. contact / review_request
        # name someone for a human to approach and are never handed to a
        # mail server, so a name or a role is fine there.
        and (if .kind == "email"
             then (.to | test("^[^@[:space:],;<>]+@[^@[:space:],;<>]+\\.[A-Za-z]{2,}$"))
             else true end)
        and (.subject | type == "string" and length > 0 and length <= 200)
        and (.body | type == "string" and length > 0 and length <= 4000)
        and (.why | type == "string" and length > 0 and length <= 600);
      type == "object"
      # Top-level keys are an allowlist, so the model cannot author `kind`.
      # publish-research.sh refuses any decision whose kind is not "research",
      # and that guard is only worth anything if the marker can be written
      # solely by the normalizer below.
      and ((keys_unsorted - ["schema_version", "outcome", "card_note", "summary",
                             "sources", "confidence", "questions", "staged_actions"])
           | length == 0)
      and .schema_version == 1
      and (.outcome | IN("research_report", "needs_clarification"))
      and (.card_note | type == "string" and length >= 1 and length <= 240
           and (test("[\r\n·]") | not))
      and (.summary | type == "string" and length >= 1 and length <= 1200)
      and (.sources | type == "array" and length <= 50 and all(.[]; valid_source))
      and (.confidence | type == "object")
      and (.confidence.score | type == "number" and floor == . and . >= 0 and . <= 100)
      and (.confidence.reason | type == "string" and length > 0)
      and ((.questions // []) | type == "array" and all(.[]; valid_question))
      and ([(.questions // [])[].id] | length == (unique | length))
      and ((.staged_actions // []) | type == "array" and length <= 10
           and all(.[]; valid_staged_action))
      and (if .outcome == "research_report" then
             (.sources | length >= 1) and ((.questions // []) | length == 0)
           else
             ((.questions // []) | length >= 1) and ((.staged_actions // []) | length == 0)
           end)
    ' "$file" >/dev/null
}

# Emits the normalized decision. The generic workflow steps read
# safe_changes_present / awaiting_human / confidence_score from every kind,
# so those keys are filled in here even though research has no patch.
autopr_normalize_research_decision() {
    local raw_file="$1" normalized_file="$2"
    [ -s "$raw_file" ] || die "research produced no decision at $raw_file"
    _autopr_research_decision_schema_ok "$raw_file" \
        || die "research decision failed schema validation"
    # Rebuilt field by field rather than `. + {...}`: the output is exactly the
    # keys listed here, so nothing the model wrote can ride through into a file
    # the trusted publisher treats as validated.
    jq '
      {
        kind: "research",
        schema_version: .schema_version,
        outcome: .outcome,
        card_note: .card_note,
        summary: .summary,
        sources: (.sources // []),
        confidence: .confidence,
        questions: (.questions // []),
        staged_actions: (.staged_actions // []),
        safe_changes_present: false,
        awaiting_human: (.outcome == "needs_clarification"),
        confidence_score: .confidence.score,
        confidence_band: (if .confidence.score >= 75 then "high"
                          elif .confidence.score >= 45 then "medium"
                          else "low" end),
        criticality: {level: "yellow", reasons: ["research report; no product change"]}
      }
    ' "$raw_file" > "$normalized_file"
}

# Rendered for the card note and the report tail. Plain text, one action per
# bullet, always headed by the fact that nothing was sent.
autopr_render_staged_actions() {
    local decision_file="$1"
    jq -r '
      if ((.staged_actions // []) | length) == 0 then empty else
        "Proposed actions — NOT sent; each needs your approval:\n" +
        ([.staged_actions[] |
          "- [" + .kind + "] to: " + .to + " · subject: " + .subject + "\n  why: " + .why
        ] | join("\n"))
      end
    ' "$decision_file"
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

# Keep model-authored prose inside the byte budgets of downstream APIs without
# cutting a multibyte UTF-8 character in half. The caller still performs a
# final whole-body check because several independently bounded sections are
# composed together.
autopr_bound_text() {
    local max_bytes="$1" label="$2"
    python3 -c '
import sys

limit = int(sys.argv[1])
label = sys.argv[2]
data = sys.stdin.buffer.read()
if len(data) <= limit:
    sys.stdout.buffer.write(data)
    raise SystemExit(0)
suffix = ("\n\n_[AutoPR " + label + " truncated to fit the PR body.]_\n").encode()
prefix = data[:max(0, limit - len(suffix))]
while True:
    try:
        prefix.decode("utf-8")
        break
    except UnicodeDecodeError:
        prefix = prefix[:-1]
sys.stdout.buffer.write(prefix.rstrip() + suffix)
' "$max_bytes" "$label"
}

autopr_render_questions() {
    local decision_file="$1"
    jq -r '
      if (.questions | length) == 0 then empty else
        "## Answers needed\n\n" +
        ([.questions | to_entries[] |
          ((.key + 1) | tostring) + ". " + .value.question + "\n" +
          (.value.options | map("   - " + .key + ": " + .label + " — " + .impact) | join("\n")) + "\n" +
          "   - Suggested default: " + .value.default_assumption + "\n" +
          "   - Why this blocks implementation: " + .value.why_blocking +
          (if ((.value.resolution | type) == "object"
                   and (.value.resolution.why_user_needed | type) == "string"
                   and (.value.resolution.why_user_needed | test("\\S"))
                   and (.value.resolution.evidence | type) == "array"
                   and (.value.resolution.evidence | length > 0)
                   and (.value.resolution.evidence
                        | all(.[]; type == "string" and test("\\S")))) then
            "\n   - Why your input is needed: " + .value.resolution.why_user_needed +
            "\n   - Already checked: " + (.value.resolution.evidence | join("; "))
           else "" end)
        ] | join("\n\n")) +
        "\n\nAnswer in the linked Kanban ticket with **Add additional context**, or reply on this PR. You can answer in plain language, add context, or tell AutoPR what to research; numbered choices are optional. The next local cycle will ingest that guidance and update this same draft."
      end
    ' "$decision_file" | autopr_bound_text 18000 "question details"
}

# Per-criterion proof, rendered for the card. This is the artifact that makes a
# false-premise ticket legible to a human: each thing the card asked for, and
# where it already lives.
autopr_render_acceptance_evidence() {
    local decision_file="$1"
    jq -r '
      if (.acceptance_evidence // [] | length) == 0 then empty else
        "Already satisfied on main — every criterion this card asks for:\n" +
        ([.acceptance_evidence[] |
          "   - " + .criterion + "\n     " + .path + ":" + (.line | tostring) + " @ " + .commit
        ] | join("\n"))
      end
    ' "$decision_file"
}

autopr_render_card_questions() {
    local decision_file="$1"
    jq -r '
      if (.questions | length) == 0 then empty else
        "Answers needed — reply below with the numbered choices:\n" +
        ([.questions | to_entries[] |
          ((.key + 1) | tostring) + ". " + .value.question + "\n" +
          (.value.options | map("   " + .key + ": " + .label + " — " + .impact) | join("\n")) + "\n" +
          "   Suggested default: " + .value.default_assumption
        ] | join("\n\n")) +
        "\n\nYou may answer in your own words, add context, or tell AutoPR what to research."
      end
    ' "$decision_file"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    case "${1:-}" in
        schema-ok)
            [ "$#" -eq 2 ] || die "usage: decision.sh schema-ok raw-decision.json"
            _autopr_decision_schema_ok "$2"
            ;;
        grounding-ok)
            [ "$#" -eq 2 ] || die "usage: decision.sh grounding-ok raw-decision.json"
            _autopr_grounding_ok "$2"
            ;;
        acceptance-ok)
            [ "$#" -eq 2 ] || die "usage: decision.sh acceptance-ok raw-decision.json"
            _autopr_acceptance_evidence_ok "$2"
            ;;
        normalize-grounded)
            { [ "$#" -eq 3 ] || [ "$#" -eq 4 ]; } \
                || die "usage: decision.sh normalize-grounded raw-decision.json decision.json [directive-policy.json]"
            autopr_normalize_decision "$2" "$3" "${4:-}"
            if ! _autopr_grounding_ok "$2"; then
                rm -f "$3"
                die "triage decision lacks context/research resolution evidence for its blockers"
            fi
            ;;
        directive-ok)
            # Directive check only, so a caller can distinguish "the model
            # contradicted the owner's directive" (retryable) from a malformed
            # or unsafe decision (fatal). Normalize still re-checks both.
            [ "$#" -eq 3 ] || die "usage: decision.sh directive-ok raw-decision.json directive-policy.json"
            _autopr_directive_policy_ok "$2" "$3"
            ;;
        feedback-snapshot)
            [ "$#" -eq 2 ] || die "usage: decision.sh feedback-snapshot feedback.json"
            autopr_feedback_snapshot_file "$2"
            ;;
        normalize-research)
            # A third argument (the directive policy) is accepted and ignored
            # so investigate.sh can call every validator the same way.
            { [ "$#" -eq 3 ] || [ "$#" -eq 4 ]; } \
                || die "usage: decision.sh normalize-research raw-decision.json decision.json"
            autopr_normalize_research_decision "$2" "$3"
            ;;
        *)
            die "usage: decision.sh normalize-grounded raw-decision.json decision.json | decision.sh schema-ok raw-decision.json | decision.sh grounding-ok raw-decision.json | decision.sh acceptance-ok raw-decision.json | decision.sh normalize-research raw-decision.json decision.json | decision.sh directive-ok raw-decision.json directive-policy.json | decision.sh feedback-snapshot feedback.json"
            ;;
    esac
fi
