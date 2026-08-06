#!/bin/bash
# Apply the tellus direct-upload CORS rules to the private S3 bucket.
# Usage: ./apply-s3-cors.sh [bucket]   (defaults to $S3_PRIVATE_BUCKET)
set -euo pipefail
BUCKET="${1:-${S3_PRIVATE_BUCKET:-}}"
if [ -z "$BUCKET" ]; then
  echo "usage: $0 <bucket>  (or set S3_PRIVATE_BUCKET)" >&2
  exit 1
fi
DIR="$(cd "$(dirname "$0")" && pwd)"
aws s3api put-bucket-cors --bucket "$BUCKET" --cors-configuration "file://$DIR/s3-cors-tellus-uploads.json"
echo "Applied. Current config:"
aws s3api get-bucket-cors --bucket "$BUCKET"
