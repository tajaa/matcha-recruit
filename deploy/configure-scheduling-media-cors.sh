#!/usr/bin/env bash
# Public scheduling media only. Dry-run by default; preserve existing CORS rules.
set -euo pipefail
umask 077

usage() {
  echo "Usage: $0 PUBLIC_BUCKET [--apply]" >&2
  echo 'Defaults to printing a merged proposal without changing AWS.' >&2
}
if [[ $# -lt 1 || $# -gt 2 || -z "$1" ]]; then usage; exit 2; fi
media_bucket="$1"
media_apply="${2:-}"
if [[ -n "$media_apply" && "$media_apply" != '--apply' ]]; then usage; exit 2; fi
media_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
media_tmp="$(mktemp -d)"
trap 'rm -rf "$media_tmp"' EXIT

if ! aws s3api get-bucket-cors --bucket "$media_bucket" > "$media_tmp/current.json" 2> "$media_tmp/error"; then
  # Missing CORS is the only failure that means an empty configuration. Never
  # treat AccessDenied, bad credentials, or an unreachable bucket as empty.
  if grep -Fq '(NoSuchCORSConfiguration)' "$media_tmp/error"; then
    printf '{"CORSRules": []}\n' > "$media_tmp/current.json"
  else
    cat "$media_tmp/error" >&2
    echo 'Stopped: could not read existing CORS. No policy was changed.' >&2
    exit 1
  fi
fi

python3 - "$media_tmp/current.json" "$media_dir/s3-cors-scheduling-commercial.json" > "$media_tmp/merged.json" <<'PY'
import json
import sys
with open(sys.argv[1]) as source:
    existing = json.load(source)
with open(sys.argv[2]) as source:
    proposed = json.load(source)
rules = existing['CORSRules']
if not isinstance(rules, list):
    raise ValueError('Existing CORSRules must be a list')
for rule in proposed['CORSRules']:
    if rule not in rules:
        rules.append(rule)
if len(rules) > 100:
    raise ValueError('Merged CORS would exceed the S3 limit of 100 rules')
print(json.dumps({'CORSRules': rules}, indent=2))
PY

if [[ "$media_apply" != '--apply' ]]; then
  cat "$media_tmp/merged.json"
  echo 'Dry run only. Review the public bucket and proposal, then rerun with --apply.' >&2
  exit 0
fi
media_backup="$(mktemp "${TMPDIR:-/tmp}/scheduling-media-cors-backup.XXXXXX")"
cp "$media_tmp/current.json" "$media_backup"
echo "Existing CORS backed up to $media_backup" >&2
aws s3api put-bucket-cors --bucket "$media_bucket" --cors-configuration "file://$media_tmp/merged.json"
echo 'Applied scheduling upload CORS. Bucket ACLs and public-access settings were not changed.' >&2
