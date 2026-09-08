#!/usr/bin/env bash
# Lane-wide backoff after Codex reports an exhausted ChatGPT quota.
#
# Every AutoPR lane (Kanban, production errors, self-audit) shares one Codex
# login. When that account hits its usage limit, each dispatched run costs a
# full prelude (checkout, labels, prod SSH, board reads) and then dies in two
# seconds at `codex exec`. This file is the one signal that stops the
# dispatcher from launching runs that cannot possibly work:
#
#   codex-backoff.sh record LOGFILE   # called by run-codex-sandboxed.sh on a
#                                     # non-zero Codex exit; writes the marker
#                                     # only when the transcript names a usage
#                                     # limit. Exit 0 = marker written, 3 = not
#                                     # a usage-limit failure.
#   codex-backoff.sh active           # exit 0 (and print resume time) while
#                                     # the backoff is in force, 3 otherwise.
#   codex-backoff.sh clear
#
# The marker is JSON: {"detected_at","resume_at","source"} with resume_at as a
# Unix epoch. "try again at 5:31 AM" is parsed as the next such local time;
# anything unparseable falls back to AUTOPR_CODEX_BACKOFF_SECONDS (1 h). The
# window is capped at 24 h so a bad parse can never silence the lanes forever.
set -uo pipefail

USER_HOME="${AUTOPR_USER_HOME:-$HOME}"
STATE_DIR="${AUTOPR_DISPATCH_STATE_DIR:-$USER_HOME/Library/Caches/matcha-autopr-dashboard/dispatch}"
MARKER="${AUTOPR_CODEX_BACKOFF_FILE:-$STATE_DIR/codex-usage-limit.json}"
DEFAULT_BACKOFF_SECONDS="${AUTOPR_CODEX_BACKOFF_SECONDS:-3600}"
MAX_BACKOFF_SECONDS="${AUTOPR_CODEX_BACKOFF_MAX_SECONDS:-86400}"
NOW="${AUTOPR_CODEX_BACKOFF_NOW:-$(date +%s)}"
NOT_ACTIVE=3

usage_limit_line() {
    grep -iE "usage limit|rate limit (reached|exceeded)|quota (exceeded|exhausted)|too many requests" "$1" 2>/dev/null | head -n 1
}

# "try again at 5:31 AM" → epoch of the next such local wall-clock time.
parse_resume_at() {
    local line="$1" clock today candidate
    clock="$(printf '%s' "$line" | sed -nE 's/.*[Tt]ry again at ([0-9]{1,2}:[0-9]{2}[[:space:]]*([AaPp][Mm])?).*/\1/p' | head -n 1)"
    [ -n "$clock" ] || return 1
    clock="$(printf '%s' "$clock" | tr '[:lower:]' '[:upper:]' | sed -E 's/[[:space:]]+//g')"
    today="$(date +%Y-%m-%d)"
    if [[ "$clock" == *[AP]M ]]; then
        candidate="$(date -j -f "%Y-%m-%d %I:%M%p" "$today ${clock}" +%s 2>/dev/null \
            || date -d "$today ${clock}" +%s 2>/dev/null)" || return 1
    else
        candidate="$(date -j -f "%Y-%m-%d %H:%M" "$today $clock" +%s 2>/dev/null \
            || date -d "$today $clock" +%s 2>/dev/null)" || return 1
    fi
    [[ "$candidate" =~ ^[0-9]+$ ]] || return 1
    [ "$candidate" -gt "$NOW" ] || candidate=$((candidate + 86400))
    printf '%s' "$candidate"
}

record() {
    local log_file="${1:?usage: codex-backoff.sh record LOGFILE}" line resume_at
    [ -f "$log_file" ] || exit "$NOT_ACTIVE"
    line="$(usage_limit_line "$log_file")"
    [ -n "$line" ] || exit "$NOT_ACTIVE"
    resume_at="$(parse_resume_at "$line")" || resume_at=$((NOW + DEFAULT_BACKOFF_SECONDS))
    if [ $((resume_at - NOW)) -gt "$MAX_BACKOFF_SECONDS" ]; then
        resume_at=$((NOW + MAX_BACKOFF_SECONDS))
    fi
    mkdir -p "$(dirname "$MARKER")"
    jq -cn --argjson detected_at "$NOW" --argjson resume_at "$resume_at" \
        --arg source "$(printf '%s' "$line" | cut -c1-200)" \
        '{detected_at:$detected_at,resume_at:$resume_at,source:$source}' > "$MARKER.tmp"
    mv "$MARKER.tmp" "$MARKER"
    printf 'codex usage limit recorded; AutoPR lanes back off until %s\n' \
        "$(date -r "$resume_at" '+%Y-%m-%d %H:%M %Z' 2>/dev/null || date -d "@$resume_at" '+%Y-%m-%d %H:%M %Z' 2>/dev/null || echo "$resume_at")" >&2
}

active() {
    local resume_at detected_at
    [ -s "$MARKER" ] || exit "$NOT_ACTIVE"
    resume_at="$(jq -r '.resume_at // empty' "$MARKER" 2>/dev/null)"
    detected_at="$(jq -r '.detected_at // empty' "$MARKER" 2>/dev/null)"
    [[ "$resume_at" =~ ^[0-9]+$ ]] || exit "$NOT_ACTIVE"
    [[ "$detected_at" =~ ^[0-9]+$ ]] || detected_at="$resume_at"
    # Cap from detection, not from resume: a marker whose resume time is a
    # day past detection is a parse error, not a real limit.
    if [ "$NOW" -ge "$resume_at" ] || [ $((NOW - detected_at)) -gt "$MAX_BACKOFF_SECONDS" ]; then
        exit "$NOT_ACTIVE"
    fi
    printf '%s\n' "$resume_at"
}

case "${1:-}" in
    record) shift; record "$@" ;;
    active) active ;;
    clear) rm -f "$MARKER" ;;
    *) echo "usage: codex-backoff.sh record LOGFILE | active | clear" >&2; exit 2 ;;
esac
