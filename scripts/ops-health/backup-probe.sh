#!/usr/bin/env bash
# Read-only backup inspection through the app EC2, whose AWS identity already
# writes this bucket. GitHub's OIDC role is intentionally ECR-only.
set -euo pipefail

MODE="${1:?usage: backup-probe.sh inventory|readable KEY EXPECTED_SIZE_BYTES}"
SSH_KEY="${SSH_KEY:?SSH_KEY must point to the production SSH key}"
PROD_HOST="${PROD_HOST:-54.177.107.107}"
PROD_USER="${PROD_USER:-ec2-user}"
BUCKET="matcha-recruit-backups"
PREFIX="postgres-selfhosted/"

ssh_app() {
    ssh -i "$SSH_KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
        "$PROD_USER@$PROD_HOST" "bash -s"
}

case "$MODE" in
    inventory)
        ssh_app <<'REMOTE'
set -euo pipefail
aws s3api list-objects-v2 \
  --bucket matcha-recruit-backups \
  --prefix postgres-selfhosted/ \
  --query 'Contents[].{key:Key,last_modified:LastModified,size_bytes:Size}' \
  --output json
REMOTE
        ;;
    readable)
        KEY="${2:?missing backup key}"
        EXPECTED_SIZE="${3:?missing expected size}"
        # The key comes from S3 inventory, but validate before embedding it in
        # the remote script so a malformed result cannot alter remote commands.
        [[ "$KEY" =~ ^postgres-selfhosted/[A-Za-z0-9._/-]+\.dump$ && "$KEY" != *..* ]] || {
            echo "unsafe backup key" >&2
            exit 2
        }
        [[ "$EXPECTED_SIZE" =~ ^[0-9]+$ ]] || {
            echo "expected size must be an integer" >&2
            exit 2
        }
        # Pinned by digest, not floating tag: cleanup() prunes all unused images
        # every deploy, so --pull=missing re-fetches on essentially every run —
        # a floating tag means the probe silently runs whatever content that
        # tag points to at fetch time. Bump deliberately via:
        #   crane digest public.ecr.aws/docker/library/postgres:15-alpine
        PROBE_IMAGE='public.ecr.aws/docker/library/postgres@sha256:61fb6a038c515f2e2ed86cab0a683a1560ba08ad4c86d367cf98a279aa82a807'
        ssh_app <<REMOTE
set -euo pipefail
key='$KEY'
expected_size='$EXPECTED_SIZE'
probe_image='$PROBE_IMAGE'
dump_file=\$(mktemp /tmp/matcha-backup-check.XXXXXX.dump)
toc_file=\$(mktemp /tmp/matcha-backup-check.XXXXXX.toc)
trap 'rm -f "\$dump_file" "\$toc_file"' EXIT
chmod 600 "\$dump_file" "\$toc_file"

set +e
aws s3 cp "s3://$BUCKET/\$key" "\$dump_file" --only-show-errors >/dev/null 2>&1
s3_rc=\$?
set -e
downloaded_size=0
if [ -f "\$dump_file" ]; then
    downloaded_size=\$(wc -c < "\$dump_file" | tr -d '[:space:]')
fi

restore_list_rc=-1
restore_scan_rc=-1
toc_entries=0
if [ "\$s3_rc" -eq 0 ] && [ "\$downloaded_size" = "\$expected_size" ]; then
    # A complete local download avoids pipe/SIGPIPE ambiguity. First inspect the
    # TOC, then extract every archive entry to /dev/null so corrupt data blocks
    # cannot pass merely because the TOC is intact. Network-disabled Docker and
    # no --dbname guarantee this never connects to or restores into any DB.
    set +e
    docker run --rm --pull=missing --network none --read-only --cap-drop ALL \
      --security-opt no-new-privileges \
      -v "\$dump_file:/backup.dump:ro" \
      "\$probe_image" \
      pg_restore --list /backup.dump > "\$toc_file" 2>/dev/null
    restore_list_rc=\$?
    set -e
    if [ "\$restore_list_rc" -eq 0 ]; then
        toc_entries=\$(grep -cE '^[0-9]+;' "\$toc_file" || true)
        set +e
        docker run --rm --pull=missing --network none --read-only --cap-drop ALL \
          --security-opt no-new-privileges \
          -v "\$dump_file:/backup.dump:ro" \
          "\$probe_image" \
          pg_restore --exit-on-error --file=/dev/null /backup.dump >/dev/null 2>&1
        restore_scan_rc=\$?
        set -e
    fi
fi

python3 - "\$key" "\$expected_size" "\$downloaded_size" "\$s3_rc" "\$restore_list_rc" "\$restore_scan_rc" "\$toc_entries" <<'PY'
import json
import sys

key, expected, downloaded, s3_rc, restore_list_rc, restore_scan_rc, toc_entries = sys.argv[1:]
print(json.dumps({
    "key": key,
    "expected_size_bytes": int(expected),
    "downloaded_size_bytes": int(downloaded),
    "s3_read_rc": int(s3_rc),
    "restore_list_rc": int(restore_list_rc),
    "restore_scan_rc": int(restore_scan_rc),
    "toc_entries": int(toc_entries),
}))
PY
REMOTE
        ;;
    *)
        echo "usage: backup-probe.sh inventory|readable KEY EXPECTED_SIZE_BYTES" >&2
        exit 2
        ;;
esac
