#!/usr/bin/env bash
# Archive Matcha Schedule and upload it to App Store Connect (TestFlight).
#
#   ./release-appstore.sh              archive and upload
#   ./release-appstore.sh --no-upload  archive only (check that signing works)
#
# Credentials load the same way as Espresso's release script: platforms/apple-env.sh
# reads secrets/apple.env (APPLE_API_ISSUER_ID) and secrets/AuthKey_<ID>.p8.
# Signing is manual (project.yml, Release): the "Apple Distribution" certificate
# in the login keychain and the "Matcha Schedule App Store" profile for
# com.matchasched.app, installed in ~/Library/MobileDevice/Provisioning Profiles.
# (Automatic signing needs a development profile, which needs registered
# devices; this team has none.) The app record must exist in App Store Connect.
set -euo pipefail
cd "$(dirname "$0")"
# shellcheck source=../../apple-env.sh
source "../../apple-env.sh"

NO_UPLOAD=false
[[ "${1:-}" == "--no-upload" ]] && NO_UPLOAD=true

: "${APPLE_API_KEY_ID:?Set APPLE_API_KEY_ID (or put secrets/AuthKey_<ID>.p8 in the repo)}"
: "${APPLE_API_ISSUER_ID:?Set APPLE_API_ISSUER_ID (secrets/apple.env)}"
: "${APPLE_API_KEY_PATH:?Set APPLE_API_KEY_PATH}"
[[ -f "$APPLE_API_KEY_PATH" ]] || { echo "error: API key not found at $APPLE_API_KEY_PATH" >&2; exit 1; }
TEAM_ID="${APPLE_TEAM_ID:-5D6TJVCPBK}"

xcodegen generate
mkdir -p build
archive_path="${MATCHA_SCHEDULE_ARCHIVE_PATH:-$PWD/build/MatchaSchedule.xcarchive}"
export_plist="$PWD/build/ExportOptions.plist"
# App Store Connect rejects a build number it has already seen, and project.yml
# pins CURRENT_PROJECT_VERSION to 1. A UTC timestamp only ever increases; set
# MATCHA_SCHEDULE_BUILD_NUMBER to override.
build_number="${MATCHA_SCHEDULE_BUILD_NUMBER:-$(date -u +%Y%m%d%H%M)}"

cat > "$export_plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string>
  <key>destination</key><string>upload</string>
  <key>teamID</key><string>$TEAM_ID</string>
  <key>signingStyle</key><string>manual</string>
  <key>signingCertificate</key><string>Apple Distribution</string>
  <key>provisioningProfiles</key>
  <dict><key>com.matchasched.app</key><string>${APPSTORE_PROFILE_NAME:-Matcha Schedule App Store}</string></dict>
  <key>uploadSymbols</key><true/>
</dict></plist>
PLIST

auth=(-authenticationKeyPath "$APPLE_API_KEY_PATH"
      -authenticationKeyID "$APPLE_API_KEY_ID"
      -authenticationKeyIssuerID "$APPLE_API_ISSUER_ID")

echo "Archiving build number $build_number"
rm -rf "$archive_path"
xcodebuild -project MatchaSchedule.xcodeproj -scheme MatchaSchedule \
  -configuration Release -destination 'generic/platform=iOS' \
  -archivePath "$archive_path" \
  CURRENT_PROJECT_VERSION="$build_number" archive

if $NO_UPLOAD; then
  echo "Archive OK (not uploaded): $archive_path"
  exit 0
fi
xcodebuild -exportArchive -archivePath "$archive_path" \
  -exportOptionsPlist "$export_plist" "${auth[@]}"
echo "Uploaded build $build_number. It appears in TestFlight once Apple finishes processing."
