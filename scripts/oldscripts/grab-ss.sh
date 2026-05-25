#!/usr/bin/env bash
# Copies the most recent screenshot from ~/Desktop into .screenshots/
# Usage: ./scripts/grab-ss.sh
#
# Run this after taking a screenshot (⌘⇧4), then drag .screenshots/latest.png
# into Claude Code. Works in sandbox/plan mode since it's within the project dir.

set -e

DEST="$(dirname "$0")/../.screenshots"
LATEST=$(ls -t ~/Desktop/*.png ~/Desktop/*.jpg 2>/dev/null | head -1)

if [[ -z "$LATEST" ]]; then
  echo "No screenshots found on Desktop."
  exit 1
fi

cp "$LATEST" "$DEST/latest.png"
echo "Copied: $(basename "$LATEST") → .screenshots/latest.png"
