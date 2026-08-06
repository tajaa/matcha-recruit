#!/bin/bash
# Merge the tellus direct-upload CORS rules into the private S3 bucket's config.
# The bucket is shared with matcha/Cappe uploads — NEVER blind-replace its CORS
# config (put-bucket-cors is a full replace; a bare apply drops their origins).
# Usage: ./apply-s3-cors.sh [bucket]   (defaults to $S3_PRIVATE_BUCKET)
set -euo pipefail
BUCKET="${1:-${S3_PRIVATE_BUCKET:-}}"
if [ -z "$BUCKET" ]; then
  echo "usage: $0 <bucket>  (or set S3_PRIVATE_BUCKET)" >&2
  exit 1
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
BACKUP="$DIR/cors-backup-$BUCKET-$(date +%s).json"

if aws s3api get-bucket-cors --bucket "$BUCKET" > "$BACKUP" 2>/dev/null; then
  echo "Existing CORS config backed up to $BACKUP"
else
  echo '{"CORSRules": []}' > "$BACKUP"
  echo "No existing CORS config on $BUCKET"
fi

MERGED="$(mktemp)"
jq -s '{CORSRules: ((.[0].CORSRules // []) + .[1].CORSRules | unique)}' \
  "$BACKUP" "$DIR/s3-cors-tellus-uploads.json" > "$MERGED"

aws s3api put-bucket-cors --bucket "$BUCKET" --cors-configuration "file://$MERGED"
rm -f "$MERGED"
echo "Applied. Current config:"
aws s3api get-bucket-cors --bucket "$BUCKET"
