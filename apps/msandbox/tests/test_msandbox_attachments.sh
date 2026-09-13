#!/usr/bin/env bash
# Attachment import is host-only and must work without starting Docker or
# exposing arbitrary host paths inside the container.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MSANDBOX="$REPO_ROOT/scripts/agent-sandbox.sh"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/matcha-attachments-test.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/bin" "$TMP_DIR/inbox" "$TMP_DIR/source folder"

printf 'screenshot bytes\n' > "$TMP_DIR/source folder/Screen Shot.png"
output="$(MSANDBOX_ATTACHMENTS_DIR="$TMP_DIR/inbox" \
    "$MSANDBOX" attach "$TMP_DIR/source folder/Screen Shot.png")"
imported="$TMP_DIR/inbox/$(basename "$output")"
[ -f "$imported" ]
cmp "$TMP_DIR/source folder/Screen Shot.png" "$imported"
[[ "$output" == /workspace/.msandbox/attachments/*-Screen\ Shot.png ]]
printf 'PASS: dragged paths are copied into the sandbox-readable evidence inbox\n'

second="$(MSANDBOX_ATTACHMENTS_DIR="$TMP_DIR/inbox" \
    "$MSANDBOX" attach "$TMP_DIR/source folder/Screen Shot.png")"
[ "$second" = "$output" ]
[ "$(find "$TMP_DIR/inbox" -type f | wc -l | tr -d '[:space:]')" = 1 ]
printf 'PASS: content hashes make repeated imports idempotent\n'

set +e
MSANDBOX_ATTACHMENTS_DIR="$TMP_DIR/inbox" MSANDBOX_ATTACHMENT_MAX_BYTES=1 \
    "$MSANDBOX" attach "$TMP_DIR/source folder/Screen Shot.png" >/dev/null 2>&1
large_rc=$?
set -e
[ "$large_rc" -ne 0 ]
printf 'PASS: oversized evidence is rejected before copying\n'

cat > "$TMP_DIR/bin/osascript" <<'EOF'
#!/usr/bin/env bash
if [ "${AUTOPR_TEST_CLIPBOARD_MODE:-file}" = image ]; then
  if [ "$#" -eq 0 ]; then exit 0; fi
  printf 'clipboard png bytes\n' > "$2"
  printf 'OK\n'
else
  printf '%s\n' "$AUTOPR_TEST_CLIPBOARD_FILE"
fi
EOF
chmod +x "$TMP_DIR/bin/osascript"
printf 'pdf bytes\n' > "$TMP_DIR/source folder/context.pdf"
paste_output="$(PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_CLIPBOARD_FILE="$TMP_DIR/source folder/context.pdf" \
    MSANDBOX_ATTACHMENTS_DIR="$TMP_DIR/inbox" "$MSANDBOX" paste)"
paste_imported="$TMP_DIR/inbox/$(basename "$paste_output")"
cmp "$TMP_DIR/source folder/context.pdf" "$paste_imported"
[[ "$paste_output" == /workspace/.msandbox/attachments/*-context.pdf ]]
printf 'PASS: copied Finder files and PDFs use the same bounded import path\n'

image_output="$(PATH="$TMP_DIR/bin:$PATH" AUTOPR_TEST_CLIPBOARD_MODE=image \
    MSANDBOX_ATTACHMENTS_DIR="$TMP_DIR/inbox" "$MSANDBOX" paste)"
image_imported="$TMP_DIR/inbox/$(basename "$image_output")"
[ -s "$image_imported" ]
[[ "$image_output" == /workspace/.msandbox/attachments/*-matcha-msandbox-clipboard.*.png ]]
printf 'PASS: pasted screenshot pixels retain a PNG extension for multimodal CLIs\n'
