#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

: "${MATCHA_APPSTORE_EXPORT_OPTIONS:?Set MATCHA_APPSTORE_EXPORT_OPTIONS to an App Store export-options plist path}"
: "${MATCHA_APPSTORE_UPLOAD_KEY:?Set MATCHA_APPSTORE_UPLOAD_KEY to the App Store Connect API key path}"
: "${MATCHA_APPSTORE_KEY_ID:?Set MATCHA_APPSTORE_KEY_ID}"
: "${MATCHA_APPSTORE_ISSUER_ID:?Set MATCHA_APPSTORE_ISSUER_ID}"

xcodegen generate
archive_path="${MATCHA_SCHEDULE_ARCHIVE_PATH:-$PWD/build/MatchaSchedule.xcarchive}"
# App Store Connect rejects an upload whose build number it has already seen,
# and project.yml pins CURRENT_PROJECT_VERSION to 1. A UTC timestamp only ever
# increases; set MATCHA_SCHEDULE_BUILD_NUMBER to override.
build_number="${MATCHA_SCHEDULE_BUILD_NUMBER:-$(date -u +%Y%m%d%H%M)}"
echo "Archiving build number $build_number"
xcodebuild -project MatchaSchedule.xcodeproj -scheme MatchaSchedule \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$archive_path" \
  CURRENT_PROJECT_VERSION="$build_number" archive
xcodebuild -exportArchive -archivePath "$archive_path" \
  -exportOptionsPlist "$MATCHA_APPSTORE_EXPORT_OPTIONS" \
  -authenticationKeyPath "$MATCHA_APPSTORE_UPLOAD_KEY" \
  -authenticationKeyID "$MATCHA_APPSTORE_KEY_ID" \
  -authenticationKeyIssuerID "$MATCHA_APPSTORE_ISSUER_ID"
