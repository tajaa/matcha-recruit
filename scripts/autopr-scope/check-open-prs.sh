#!/usr/bin/env bash
# Compare the current uncommitted proposal with older open PRs. GitHub data is
# collected by the trusted harness; the semantic comparison receives no creds.
#
# Usage: check-open-prs.sh --lane error|kanban --identity ID --evidence FILE
#        --report FILE --output FILE
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

LANE=""
IDENTITY=""
EVIDENCE=""
REPORT=""
OUTPUT=""
PROPOSAL_DIFF=""
EXCLUDE_PR=""
CREATED_BEFORE=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --lane) LANE="${2:-}"; shift 2 ;;
        --identity) IDENTITY="${2:-}"; shift 2 ;;
        --evidence) EVIDENCE="${2:-}"; shift 2 ;;
        --report) REPORT="${2:-}"; shift 2 ;;
        --output) OUTPUT="${2:-}"; shift 2 ;;
        --proposal-diff) PROPOSAL_DIFF="${2:-}"; shift 2 ;;
        --exclude-pr) EXCLUDE_PR="${2:-}"; shift 2 ;;
        --created-before) CREATED_BEFORE="${2:-}"; shift 2 ;;
        *) autopr_scope_die "unknown argument: $1" ;;
    esac
done

[[ "$LANE" = error || "$LANE" = kanban ]] || autopr_scope_die "--lane must be error or kanban"
[ -n "$IDENTITY" ] || autopr_scope_die "--identity is required"
[ -f "$EVIDENCE" ] || autopr_scope_die "--evidence must be a readable file"
[ -f "$REPORT" ] || autopr_scope_die "--report must be a readable file"
[ -n "$OUTPUT" ] || autopr_scope_die "--output is required"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
MODEL="${AUTOPR_SCOPE_MODEL:-openai/gpt-5.6-terra}"
MODE="$(autopr_scope_mode)"
WORK_DIR="$(mktemp -d "${RUNNER_TEMP:-/tmp}/autopr-scope-XXXXXX")"
TREE_DIR="$WORK_DIR/tree"
trap 'git -C "$REPO_ROOT" worktree remove --force "$TREE_DIR" >/dev/null 2>&1 || true; rm -rf "$WORK_DIR"' EXIT

emit_none() {
    jq -n --arg mode "$MODE" --arg decision "${1:-no_match}" --arg reason "${2:-No overlapping open pull request.}" \
        '{decision:$decision,confidence:"high",covering_pr:null,covering_head_sha:null,reason:$reason,mode:$mode,possible_duplicate:false}' > "$OUTPUT"
}

if [ "$MODE" = off ]; then
    emit_none no_match "Cross-lane deduplication is disabled."
    exit 0
fi

proposal="$WORK_DIR/proposal.diff"
if [ -n "$PROPOSAL_DIFF" ]; then
    [ -s "$PROPOSAL_DIFF" ] || autopr_scope_die "--proposal-diff must be a nonempty file"
    cp "$PROPOSAL_DIFF" "$proposal"
else
    autopr_scope_capture_diff "$REPO_ROOT" "$proposal"
fi
if [ ! -s "$proposal" ]; then
    emit_none no_match "The investigation produced no patch to compare."
    exit 0
fi

proposal_files="$WORK_DIR/proposal-files.txt"
sed -nE 's#^diff --git a/(.*) b/.*#\1#p' "$proposal" | sort -u > "$proposal_files"
[ -s "$proposal_files" ] || autopr_scope_die "could not identify files in proposed patch"

all_prs="$WORK_DIR/open-prs.json"
gh pr list --repo "$REPO" --state open --base main --limit 100 \
    --json number,title,createdAt,headRefName,headRefOid,isDraft,files,url > "$all_prs"
jq --arg head "$(git -C "$REPO_ROOT" branch --show-current)" \
   --arg exclude "$EXCLUDE_PR" --arg before "$CREATED_BEFORE" '
    map(select(.headRefName != $head))
    | map(select($exclude == "" or (.number | tostring) != $exclude))
    | map(select($before == "" or .createdAt < $before))
    | sort_by(.createdAt)
' "$all_prs" > "$WORK_DIR/sorted-prs.json"

candidates="$WORK_DIR/candidates.json"
jq -n '[]' > "$candidates"
while IFS= read -r pr; do
    overlap=false
    while IFS= read -r path; do
        if printf '%s' "$pr" | jq -e --arg path "$path" 'any(.files[]?; .path == $path)' >/dev/null; then
            overlap=true
            break
        fi
    done < "$proposal_files"
    [ "$overlap" = true ] || continue
    number="$(printf '%s' "$pr" | jq -r '.number')"
    diff="$WORK_DIR/pr-$number.diff"
    gh pr diff "$number" --repo "$REPO" > "$diff"
    [ -s "$diff" ] || continue
    jq --arg diff "$diff" '. + {diff_file:$diff}' <<< "$pr" \
        | jq -s --slurpfile existing "$candidates" '$existing[0] + .' > "$WORK_DIR/next.json"
    mv "$WORK_DIR/next.json" "$candidates"
done < <(jq -c '.[]' "$WORK_DIR/sorted-prs.json")

[ "$(jq 'length' "$candidates")" -gt 0 ] || { emit_none; exit 0; }

proposal_patch_id="$(autopr_scope_patch_id "$proposal")"
if [ -n "$proposal_patch_id" ]; then
    while IFS= read -r candidate; do
        diff="$(printf '%s' "$candidate" | jq -r '.diff_file')"
        if [ "$(autopr_scope_patch_id "$diff")" = "$proposal_patch_id" ]; then
            printf '%s' "$candidate" | jq --arg mode "$MODE" --arg id "$proposal_patch_id" \
                '{decision:"covered",confidence:"high",covering_pr:.number,covering_head_sha:.headRefOid,reason:("Stable patch-id matches exactly: " + $id),mode:$mode,possible_duplicate:($mode == "observe")}' > "$OUTPUT"
            exit 0
        fi
    done < <(jq -c '.[]' "$candidates")
fi

result="$WORK_DIR/model-result.json"
prompt="$WORK_DIR/prompt.txt"
sed "s#RESULT_PATH#$result#g" "$SCRIPT_DIR/_match_prompt.txt" > "$prompt"
attachments=(-f "$EVIDENCE" -f "$REPORT" -f "$proposal" -f "$candidates")
while IFS= read -r diff; do attachments+=(-f "$diff"); done < <(jq -r '.[].diff_file' "$candidates")

# The comparator may inspect current source, but it never receives the live
# checkout. Any accidental edits are confined to this disposable worktree.
git -C "$REPO_ROOT" worktree add --detach "$TREE_DIR" HEAD >/dev/null

if ! env -u GH_TOKEN -u GITHUB_TOKEN -u EC2_SSH_KEY -u SSH_KEY \
    opencode run --auto --model "$MODEL" --variant high --dir "$TREE_DIR" \
    "${attachments[@]}" -- "$(<"$prompt")"; then
    jq -n --arg mode "$MODE" '{decision:"uncertain",confidence:"low",covering_pr:null,covering_head_sha:null,reason:"Semantic comparator failed.",mode:$mode,possible_duplicate:true}' > "$OUTPUT"
    exit 0
fi

if ! jq -e '
    (.decision == "covered" or .decision == "no_match" or .decision == "uncertain") and
    (.confidence == "high" or .confidence == "medium" or .confidence == "low") and
    (.reason | type == "string" and length > 0) and
    (if .decision == "covered" then (.covering_pr | type == "number") else .covering_pr == null end)
' "$result" >/dev/null 2>&1; then
    jq -n --arg mode "$MODE" '{decision:"uncertain",confidence:"low",covering_pr:null,covering_head_sha:null,reason:"Semantic comparator returned an invalid verdict.",mode:$mode,possible_duplicate:true}' > "$OUTPUT"
    exit 0
fi

if [ "$(jq -r '.decision' "$result")" = covered ]; then
    covering_pr="$(jq -r '.covering_pr' "$result")"
    jq -e --argjson number "$covering_pr" 'any(.[]; .number == $number)' "$candidates" >/dev/null \
        || autopr_scope_die "semantic comparator selected a non-candidate PR"
    covering_sha="$(jq -r --argjson number "$covering_pr" '.[] | select(.number == $number) | .headRefOid' "$candidates")"
else
    covering_sha=""
fi
jq --arg mode "$MODE" --arg sha "$covering_sha" \
    '. + {
        mode:$mode,
        covering_head_sha:(if $sha == "" then null else $sha end),
        possible_duplicate:(.decision == "uncertain" or .confidence != "high" or ($mode == "observe" and .decision == "covered"))
    }' "$result" > "$OUTPUT"
