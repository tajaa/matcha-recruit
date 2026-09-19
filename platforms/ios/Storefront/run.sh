#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEME="${SCHEME:-Ahnimal}"
SIM="${SIM:-iPhone 17 Pro}"
BUNDLE_ID="${BUNDLE_ID:-com.ahnimal.app}"

cd "$PROJECT_DIR"
command -v xcodegen >/dev/null || { echo "xcodegen is required"; exit 1; }
xcodegen generate >/dev/null

SIM_UDID="${SIM_UDID:-$(xcrun simctl list devices available | awk -v name="$SIM" 'index($0, name " (") { match($0, /\([0-9A-F-]+\)/); print substr($0, RSTART + 1, RLENGTH - 2); exit }')}"
[[ -n "$SIM_UDID" ]] || { echo "simulator not found: $SIM"; exit 1; }

xcodebuild -project Storefront.xcodeproj -scheme "$SCHEME" -configuration Debug \
  -destination "platform=iOS Simulator,id=$SIM_UDID" build
APP_PATH="$(xcodebuild -project Storefront.xcodeproj -scheme "$SCHEME" -configuration Debug \
  -destination "platform=iOS Simulator,id=$SIM_UDID" -showBuildSettings 2>/dev/null \
  | awk '/ CODESIGNING_FOLDER_PATH = /{print $3}' | head -1)"
xcrun simctl boot "$SIM_UDID" 2>/dev/null || true
xcrun simctl install "$SIM_UDID" "$APP_PATH"
xcrun simctl terminate "$SIM_UDID" "$BUNDLE_ID" 2>/dev/null || true
xcrun simctl launch "$SIM_UDID" "$BUNDLE_ID"
