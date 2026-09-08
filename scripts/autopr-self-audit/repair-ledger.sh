#!/usr/bin/env bash
# Memory for the self-audit repair lane: which failure set was last handed to
# Codex, and what came of it.
#
# The audit itself is cheap and deterministic; the repair is a full Sol run.
# Without this ledger the same non-repairable failure (one Codex cannot fix
# from inside the repo — a missing host package, a machine-state check that
# was misclassified as repo-repairable) was re-dispatched every six hours,
# rejected by verify.sh every time, and burned the ChatGPT quota every lane
# shares: 15/15 failed runs between 2026-08-31 and 2026-09-07.
#
#   repair-ledger.sh should-repair AUDIT_JSON   # 0 = dispatch the repair;
#                                               # 3 = same failing checks as the
#                                               #     last attempt, inside the
#                                               #     retry window
#   repair-ledger.sh record AUDIT_JSON OUTCOME  # attempted|rejected|failed|published
#
# A different set of failing check ids (fingerprint) always repairs. The same
# set repairs again only after AUTOPR_AUDIT_REPAIR_RETRY_SECONDS (default 7 d)
# — a merged fix changes the fingerprint anyway, and the audit keeps running
# every six hours regardless, so a fix is noticed the moment it lands.
#
# `published` is deliberately NOT exempt. An open, unmerged repair PR leaves the
# failing checks failing, so the fingerprint is unchanged and exempting it would
# rerun a 15-minute Sol run every six hours until a human merges — the loop this
# ledger exists to stop. The merge itself changes the fingerprint and unblocks
# the next real repair.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
STATE_DIR="${AUTOPR_DISPATCH_STATE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard/dispatch}"
LEDGER="${AUTOPR_SELF_AUDIT_LEDGER:-$STATE_DIR/self-audit-repair-ledger.json}"
RETRY_SECONDS="${AUTOPR_AUDIT_REPAIR_RETRY_SECONDS:-604800}"
NOW="${AUTOPR_LEDGER_NOW:-$(date +%s)}"
SKIP=3

fingerprint_of() {
    jq -r '.fingerprint // empty' "$1"
}

should_repair() {
    local audit="${1:?usage: repair-ledger.sh should-repair AUDIT_JSON}" fp last_fp last_outcome last_at
    fp="$(fingerprint_of "$audit")"
    [ -n "$fp" ] || exit 0
    [ -s "$LEDGER" ] || exit 0
    last_fp="$(jq -r '.fingerprint // empty' "$LEDGER" 2>/dev/null)"
    last_outcome="$(jq -r '.outcome // empty' "$LEDGER" 2>/dev/null)"
    last_at="$(jq -r '.recorded_at // 0' "$LEDGER" 2>/dev/null)"
    [ "$last_fp" = "$fp" ] || exit 0
    [[ "$last_at" =~ ^[0-9]+$ ]] || exit 0
    if [ $((NOW - last_at)) -ge "$RETRY_SECONDS" ]; then
        exit 0
    fi
    printf 'self-audit: failing check set %s was already handed to Codex (%s at %s); not repairing again yet\n' \
        "$fp" "$last_outcome" "$last_at" >&2
    exit "$SKIP"
}

record() {
    local audit="${1:?usage: repair-ledger.sh record AUDIT_JSON OUTCOME}" outcome="${2:?missing outcome}" fp
    case "$outcome" in
        attempted|rejected|failed|published) ;;
        *) echo "repair-ledger.sh: unknown outcome $outcome" >&2; exit 2 ;;
    esac
    fp="$(fingerprint_of "$audit")"
    [ -n "$fp" ] || exit 0
    mkdir -p "$(dirname "$LEDGER")"
    jq -cn --arg fp "$fp" --arg outcome "$outcome" --argjson now "$NOW" \
        --argjson failing "$(jq -c '[.checks[]? | select(.status == "fail" and .repairability == "repo") | .id]' "$audit")" \
        '{fingerprint:$fp,outcome:$outcome,recorded_at:$now,failing_checks:$failing}' > "$LEDGER.tmp"
    mv "$LEDGER.tmp" "$LEDGER"
}

case "${1:-}" in
    should-repair) shift; should_repair "$@" ;;
    record) shift; record "$@" ;;
    *) echo "usage: repair-ledger.sh should-repair AUDIT_JSON | record AUDIT_JSON OUTCOME" >&2; exit 2 ;;
esac
