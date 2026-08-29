#!/usr/bin/env bash
# Email the production-alert recipient when an error fix PR is ready for human
# review. A durable PR comment makes delivery idempotent; --reconcile retries
# opted-in open PRs after a prior post-publication send failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./lib.sh
source "$SCRIPT_DIR/lib.sh"

REPO="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY must be set}"
RECIPIENT="${AUTOFIX_REVIEW_EMAIL:-aaron@hey-matcha.com}"
PENDING_PREFIX='<!-- matcha-autofix-notify-review:'
SENT_PREFIX='<!-- matcha-autofix-review-email:'

usage() {
    die "usage: notify-review-ready.sh --reconcile | --pr NUMBER [--incident FILE] [--decision FILE]"
}

comments_for() {
    gh api "repos/$REPO/issues/$1/comments?per_page=100"
}

marker_present() {
    local comments="$1" prefix="$2" key="$3"
    printf '%s' "$comments" | jq -e --arg marker "$prefix $key -->" \
        'any(.[]; (.body // "") | contains($marker))' >/dev/null
}

send_email() {
    local payload_json="$1" payload_b64
    payload_b64="$(printf '%s' "$payload_json" | base64 | tr -d '\n')"
    ssh_prod <<REMOTE
CONTAINER="\$($(resolve_backend_container_cmd))"
if [ -z "\$CONTAINER" ]; then
    echo 'error-autofix: live backend container not found' >&2
    exit 1
fi
docker exec -i -e MATCHA_AUTOFIX_EMAIL_PAYLOAD_B64="$payload_b64" "\$CONTAINER" python - <<'PYEOF'
import asyncio
import base64
import html
import json
import os

from app.core.services.email import get_email_service

payload = json.loads(base64.b64decode(os.environ["MATCHA_AUTOFIX_EMAIL_PAYLOAD_B64"]))
title = payload["title"]
url = payload["url"]
summary = payload["summary"]
criticality = payload["criticality"]
confidence = payload["confidence"]
key = payload["key"]
rows = (
    ("Production error", summary),
    ("Triage", f"{criticality} · confidence {confidence}/100"),
    ("Fingerprint", key),
    ("Pull request", title),
)
cells = "".join(
    '<tr><td style="padding:4px 12px 4px 0;color:#71717a;white-space:nowrap">'
    + html.escape(label)
    + '</td><td style="padding:4px 0;color:#18181b">'
    + html.escape(value)
    + "</td></tr>"
    for label, value in rows
)
html_body = (
    '<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:640px;margin:0 auto">'
    '<h2 style="font-size:17px;color:#18181b">Production error fix ready for review</h2>'
    f'<table style="width:100%;border-collapse:collapse">{cells}</table>'
    f'<p><a href="{html.escape(url, quote=True)}" style="color:#059669">Review the draft PR →</a></p>'
    '<p style="color:#71717a;font-size:12px">The bot never deploys or merges this fix.</p>'
    '</div>'
)
text_body = (
    "Production error fix ready for review\n\n"
    f"{summary}\nTriage: {criticality} · confidence {confidence}/100\n"
    f"Fingerprint: {key}\nPR: {title}\n{url}\n\n"
    "The bot never deploys or merges this fix."
)

sent = asyncio.run(get_email_service().send_email_with_fallback(
    to_email=payload["recipient"],
    to_name="Aaron",
    subject=(f"[Matcha] Fix ready for review: {title}")[:140],
    html_content=html_body,
    text_content=text_body,
))
raise SystemExit(0 if sent else 1)
PYEOF
REMOTE
}

notify_pr_key() {
    local pr_number="$1" key="$2" incident_file="${3:-}" decision_file="${4:-}"
    [[ "$pr_number" =~ ^[0-9]+$ ]] || die "invalid PR number: $pr_number"
    [[ "$key" =~ ^[0-9a-f]{12}$ ]] || die "invalid incident key: $key"

    local pr comments combined criticality confidence summary payload marker_file
    pr="$(gh pr view "$pr_number" --repo "$REPO" --json number,state,title,url,body)"
    [ "$(printf '%s' "$pr" | jq -r '.state')" = OPEN ] || return 0
    comments="$(comments_for "$pr_number")"
    printf '%s' "$comments" | jq -e 'type == "array"' >/dev/null \
        || die "comments for PR #$pr_number returned invalid JSON"
    marker_present "$comments" "$SENT_PREFIX" "$key" && return 0

    combined="$(printf '%s\n' "$(printf '%s' "$pr" | jq -r '.body // ""')" \
        "$(printf '%s' "$comments" | jq -r '.[].body // ""')")"
    if [ -n "$decision_file" ]; then
        criticality="$(jq -r '.criticality.level' "$decision_file")"
        confidence="$(jq -r '.confidence_score' "$decision_file")"
    else
        criticality="$(printf '%s' "$combined" | sed -nE \
            's/.*<!-- matcha-autopr-criticality: (red|orange|yellow) -->.*/\1/p' | tail -1)"
        confidence="$(printf '%s' "$combined" | sed -nE \
            's/.*<!-- matcha-autopr-confidence-score: ([0-9]{1,3}) -->.*/\1/p' | tail -1)"
    fi
    [ -n "$criticality" ] || die "PR #$pr_number has no criticality marker"
    [[ "$confidence" =~ ^[0-9]{1,3}$ ]] || die "PR #$pr_number has no confidence marker"
    [ "$confidence" -le 100 ] || die "PR #$pr_number has invalid confidence marker"

    if [ -n "$incident_file" ]; then
        summary="$(jq -r '
          [(.exception_type // .kind // "Error"), (.message // ""),
           ((.request_method // "") + " " + (.request_path // "") | gsub("^ +| +$"; ""))]
          | map(select(length > 0)) | join(" · ")
        ' "$incident_file")"
    else
        summary="$(printf '%s' "$pr" | jq -r '.title')"
    fi

    payload="$(jq -cn \
        --arg recipient "$RECIPIENT" \
        --arg title "$(printf '%s' "$pr" | jq -r '.title')" \
        --arg url "$(printf '%s' "$pr" | jq -r '.url')" \
        --arg summary "$summary" --arg criticality "$criticality" \
        --arg confidence "$confidence" --arg key "$key" \
        '{recipient:$recipient,title:$title,url:$url,summary:$summary,criticality:$criticality,confidence:$confidence,key:$key}')"
    send_email "$payload"

    marker_file="$(mktemp)"
    printf '%s %s -->\nFix-ready email sent to %s.\n' "$SENT_PREFIX" "$key" "$RECIPIENT" > "$marker_file"
    gh pr comment "$pr_number" --repo "$REPO" --body-file "$marker_file" >/dev/null
    rm -f "$marker_file"
}

reconcile() {
    local prs pr pr_number body comments combined
    prs="$(
        {
            gh pr list --repo "$REPO" --state open --label autofix --limit 100 \
                --json number,state,title,url,body
            gh pr list --repo "$REPO" --state open --label covers-prod-error --limit 100 \
                --json number,state,title,url,body
        } | jq -s 'add | unique_by(.number)'
    )"
    while IFS= read -r pr; do
        [ -n "$pr" ] || continue
        pr_number="$(printf '%s' "$pr" | jq -r '.number')"
        body="$(printf '%s' "$pr" | jq -r '.body // ""')"
        comments="$(comments_for "$pr_number")"
        combined="$(printf '%s\n%s\n' "$body" \
            "$(printf '%s' "$comments" | jq -r '.[].body // ""')")"
        while IFS= read -r key; do
            [ -n "$key" ] || continue
            notify_pr_key "$pr_number" "$key"
        done < <(printf '%s' "$combined" \
            | grep -oE '<!-- matcha-autofix-notify-review: [0-9a-f]{12} -->' \
            | sed -E 's/.*: ([0-9a-f]{12}) -->/\1/' | sort -u || true)
    done < <(printf '%s' "$prs" | jq -c '.[]')
}

case "${1:-}" in
    --reconcile)
        [ "$#" -eq 1 ] || usage
        reconcile
        ;;
    --pr)
        [ "$#" -ge 2 ] || usage
        pr_number="$2"
        shift 2
        incident_file=""
        decision_file=""
        while [ "$#" -gt 0 ]; do
            case "$1" in
                --incident) [ "$#" -ge 2 ] || usage; incident_file="$2"; shift 2 ;;
                --decision) [ "$#" -ge 2 ] || usage; decision_file="$2"; shift 2 ;;
                *) usage ;;
            esac
        done
        if [ -n "$incident_file" ]; then
            key="$(jq -r '.stable_key' "$incident_file")"
        else
            pr_json="$(gh pr view "$pr_number" --repo "$REPO" --json body)"
            key="$(printf '%s' "$pr_json" | jq -r '.body // ""' \
                | sed -nE 's/.*<!-- matcha-autofix-notify-review: ([0-9a-f]{12}) -->.*/\1/p' | tail -1)"
        fi
        notify_pr_key "$pr_number" "$key" "$incident_file" "$decision_file"
        ;;
    *) usage ;;
esac
