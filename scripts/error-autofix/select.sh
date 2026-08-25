#!/usr/bin/env bash
# Pick the first incident from incidents.json that isn't already handled by an
# open PR, a permanently-rejected PR, an already-fixed-and-deployed PR, or a
# just-attempted investigation. GitHub is the durable dedup ledger; a small
# local cache only prevents an in-flight/just-crashed run from being retried
# immediately on the next cron tick.
#
# Usage: ./select.sh incidents.json > incident.json
# Exit 3 (not 1) means "nothing to do" — the normal case on most runs. The
# workflow must treat 3 as success-and-stop, not failure.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

INCIDENTS_FILE="${1:?usage: select.sh incidents.json}"
REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
CACHE_DIR="${AUTOFIX_CACHE_DIR:-$HOME/.cache/matcha-autofix}"
ATTEMPTS_DIR="$CACHE_DIR/attempts"
mkdir -p "$ATTEMPTS_DIR"

NOTHING_TO_DO=3
MAX_OPEN_AUTOFIX_PRS=3
CLOSED_COOLDOWN_DAYS=7
DEPLOY_GRACE_HOURS=6
ATTEMPT_COOLDOWN_HOURS=2

count="$(jq 'length' "$INCIDENTS_FILE")"
[ "$count" -gt 0 ] || exit "$NOTHING_TO_DO"

# Backstop against a dedup bug nobody has found yet: never let a bad day
# produce an unbounded number of open bot PRs.
open_autofix_prs="$(gh pr list --repo "$REPO" --state open --label autofix --limit 100 --json number --jq 'length')"
if [ "$open_autofix_prs" -ge "$MAX_OPEN_AUTOFIX_PRS" ]; then
    printf 'error-autofix: %s open autofix PRs already \342\200\224 skipping this run\n' "$open_autofix_prs" >&2
    exit "$NOTHING_TO_DO"
fi

# already_handled STABLE_KEY LAST_SEEN
# Echoes "skip" or "investigate".
already_handled() {
    local key="$1" last_seen="$2" branch="bot/err-$key"

    local attempt_marker="$ATTEMPTS_DIR/$key"
    if [ -f "$attempt_marker" ]; then
        local age_h
        age_h=$(( ( $(date +%s) - $(date -r "$attempt_marker" +%s 2>/dev/null || echo 0) ) / 3600 ))
        if [ "$age_h" -lt "$ATTEMPT_COOLDOWN_HOURS" ]; then
            echo skip
            return
        fi
    fi

    # A prior investigation that found no safe fix opens an issue, not a PR
    # (publish.sh). Without checking for that, the top-ranked incident with
    # no safe fix would be re-selected and re-investigated (a ~12-minute
    # model run) on every single run forever, and every incident ranked
    # below it would starve. The issue title embeds "[KEY]" for exact,
    # reliable matching — GitHub's body/comment search index is not
    # reliable enough to dedup on (see publish.sh).
    [[ "$key" =~ ^[0-9a-f]{12}$ ]] || die "stable_key has unexpected shape: $key"
    local open_issue_hit
    open_issue_hit="$(gh issue list --repo "$REPO" --state open --label autofix-nofix --limit 100 \
        --json title,body --jq "map(select(
            (.title | contains(\"[$key]\")) and
            ((.body // \"\") | contains(\"Investigation failed or produced no report.\") | not)
        )) | length")"
    if [ "${open_issue_hit:-0}" -gt 0 ]; then
        echo skip
        return
    fi

    local prs
    prs="$(gh pr list --repo "$REPO" --head "$branch" --state all --limit 100 \
        --json state,mergedAt,closedAt,createdAt --jq 'sort_by(.createdAt) | reverse')"

    local n
    n="$(printf '%s' "$prs" | jq 'length')"
    [ "$n" -gt 0 ] || { echo investigate; return; }

    # Most recent PR for this branch decides. Sorted explicitly rather than
    # trusting gh's default ordering — .[0] on an unsorted list is only
    # "probably" the right one.
    local state merged_at closed_at
    state="$(printf '%s' "$prs" | jq -r '.[0].state')"
    merged_at="$(printf '%s' "$prs" | jq -r '.[0].mergedAt')"
    closed_at="$(printf '%s' "$prs" | jq -r '.[0].closedAt')"

    # gh reports state as OPEN, CLOSED, or MERGED — three distinct values,
    # not "CLOSED with mergedAt set" for a merged PR.
    case "$state" in
        OPEN)
            echo skip ;;
        MERGED)
            # Only re-open for a genuine recurrence observed well after the
            # fix could plausibly have been deployed — deploys are manual
            # here (deploy.yml is workflow_dispatch only), so merge time and
            # deploy time can differ by hours. Comparing on last_seen (not
            # first_seen) matters: the daily fingerprint bucket means an
            # aggregated incident's first_seen is nearly always "recent"
            # even for a bug fixed weeks ago, which would otherwise reopen
            # forever.
            local grace
            grace="$(_iso_plus_hours "$merged_at" "$DEPLOY_GRACE_HOURS")"
            if [[ "$last_seen" > "$grace" ]]; then
                echo investigate
            else
                echo skip
            fi
            ;;
        CLOSED)
            # A human rejected this investigation. Don't retry immediately,
            # but don't blind the system to it forever either — a wrong fix
            # today doesn't mean a wrong fix in 7 days, once more evidence
            # has accumulated.
            local cooldown_end now
            cooldown_end="$(_iso_plus_hours "$closed_at" $((CLOSED_COOLDOWN_DAYS * 24)))"
            now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
            if [[ "$now" < "$cooldown_end" ]]; then
                echo skip
            else
                echo investigate
            fi
            ;;
        *)
            echo skip ;;
    esac
}

# GNU/BSD date compatible ISO-8601 arithmetic (runner is macOS/BSD date).
_iso_plus_hours() {
    local iso="$1" hours="$2"
    date -u -j -v"+${hours}H" -f "%Y-%m-%dT%H:%M:%SZ" "$iso" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
        || date -u -d "$iso + ${hours} hours" +%Y-%m-%dT%H:%M:%SZ
}

for ((i = 0; i < count; i++)); do
    incident="$(jq -c ".[$i]" "$INCIDENTS_FILE")"
    key="$(printf '%s' "$incident" | jq -r '.stable_key')"
    last_seen="$(printf '%s' "$incident" | jq -r '.last_seen')"

    decision="$(already_handled "$key" "$last_seen")"
    if [ "$decision" = investigate ]; then
        touch "$ATTEMPTS_DIR/$key"
        printf '%s\n' "$incident"
        exit 0
    fi
done

exit "$NOTHING_TO_DO"
