#!/usr/bin/env bash
# Archive and optionally upload a white-label Cappe storefront target.
# Required for upload: APPLE_API_KEY_ID, APPLE_API_ISSUER_ID, APPLE_API_KEY_PATH.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCHEME="${SCHEME:-Ahnimal}"
BUNDLE_ID="${BUNDLE_ID:-com.ahnimal.app}"
APPLE_TEAM_ID="${APPLE_TEAM_ID:-5D6TJVCPBK}"
PROVISIONING_PROFILE_NAME="${PROVISIONING_PROFILE_NAME:-Ahnimal App Store}"
NO_UPLOAD=false
[[ "${1:-}" == "--no-upload" ]] && NO_UPLOAD=true

cd "$PROJECT_DIR"
command -v xcodegen >/dev/null || { echo "xcodegen is required"; exit 1; }
xcodegen generate

BUILD_DIR="$PROJECT_DIR/build/appstore/$SCHEME"
ARCHIVE_PATH="$BUILD_DIR/$SCHEME.xcarchive"
EXPORT_PLIST="$BUILD_DIR/ExportOptions.plist"
mkdir -p "$BUILD_DIR"

xcodebuild -project Storefront.xcodeproj -scheme "$SCHEME" -configuration Release \
  -destination 'generic/platform=iOS' -archivePath "$ARCHIVE_PATH" \
  DEVELOPMENT_TEAM="$APPLE_TEAM_ID" PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID" \
  -allowProvisioningUpdates archive

if $NO_UPLOAD; then
  echo "archive ready: $ARCHIVE_PATH"
  exit 0
fi

: "${APPLE_API_KEY_ID:?APPLE_API_KEY_ID is required}"
: "${APPLE_API_ISSUER_ID:?APPLE_API_ISSUER_ID is required}"
: "${APPLE_API_KEY_PATH:?APPLE_API_KEY_PATH is required}"
[[ -f "$APPLE_API_KEY_PATH" ]] || { echo "API key not found: $APPLE_API_KEY_PATH"; exit 1; }

cat > "$EXPORT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>method</key><string>app-store-connect</string>
<key>destination</key><string>upload</string>
<key>teamID</key><string>$APPLE_TEAM_ID</string>
<key>signingStyle</key><string>manual</string>
<key>provisioningProfiles</key><dict><key>$BUNDLE_ID</key><string>$PROVISIONING_PROFILE_NAME</string></dict>
</dict></plist>
PLIST

xcodebuild -exportArchive -archivePath "$ARCHIVE_PATH" -exportOptionsPlist "$EXPORT_PLIST" \
  -authenticationKeyPath "$APPLE_API_KEY_PATH" -authenticationKeyID "$APPLE_API_KEY_ID" \
  -authenticationKeyIssuerID "$APPLE_API_ISSUER_ID"
