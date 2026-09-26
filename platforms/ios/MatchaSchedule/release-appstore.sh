#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

: "${MATCHA_APPSTORE_EXPORT_OPTIONS:?Set MATCHA_APPSTORE_EXPORT_OPTIONS to an App Store export-options plist path}"
: "${MATCHA_APPSTORE_UPLOAD_KEY:?Set MATCHA_APPSTORE_UPLOAD_KEY to the App Store Connect API key path}"
: "${MATCHA_APPSTORE_KEY_ID:?Set MATCHA_APPSTORE_KEY_ID}"
: "${MATCHA_APPSTORE_ISSUER_ID:?Set MATCHA_APPSTORE_ISSUER_ID}"

xcodegen generate
archive_path="${MATCHA_SCHEDULE_ARCHIVE_PATH:-$PWD/build/MatchaSchedule.xcarchive}"
xcodebuild -project MatchaSchedule.xcodeproj -scheme MatchaSchedule \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$archive_path" archive
xcodebuild -exportArchive -archivePath "$archive_path" \
  -exportOptionsPlist "$MATCHA_APPSTORE_EXPORT_OPTIONS" \
  -authenticationKeyPath "$MATCHA_APPSTORE_UPLOAD_KEY" \
  -authenticationKeyID "$MATCHA_APPSTORE_KEY_ID" \
  -authenticationKeyIssuerID "$MATCHA_APPSTORE_ISSUER_ID"
