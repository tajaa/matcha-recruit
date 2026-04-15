#!/usr/bin/env bash
# Build, sign, notarize, staple, and package Matcha for Developer ID distribution.
#
# One-time setup (out of band):
#   1. Install "Developer ID Application" cert in login keychain.
#      Verify:  security find-identity -p codesigning -v | grep 'Developer ID'
#   2. (Recommended) Create an App Store Connect API key at
#      https://appstoreconnect.apple.com/access/integrations/api — download the
#      .p8 file and note the Key ID + Issuer ID.
#      OR: generate an app-specific password at https://account.apple.com and
#      set APPLE_ID + APPLE_APP_PASSWORD instead.
#   3. Make sure the bundle ID resolves under your team. Default is
#      com.matcha.Matcha — override via BUNDLE_ID=com.yourteam.matcha if needed.
#
# Env vars:
#   APPLE_TEAM_ID         (required) 10-char Apple Developer Team ID
#   BUNDLE_ID             (optional) overrides PRODUCT_BUNDLE_IDENTIFIER
#
#   Either API-key auth (preferred):
#     APPLE_API_KEY_ID      App Store Connect API Key ID
#     APPLE_API_ISSUER_ID   App Store Connect Issuer ID (UUID)
#     APPLE_API_KEY_PATH    Path to AuthKey_*.p8
#
#   Or password auth:
#     APPLE_ID              Apple ID email
#     APPLE_APP_PASSWORD    App-specific password
#
# Usage:
#   ./release.sh                 build + sign + notarize + staple + zip
#   ./release.sh --dmg           also produce a .dmg
#   ./release.sh --skip-notarize local signed build only (for testing)
#
# Outputs land in desktop/Matcha/build/release/.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/Matcha.xcodeproj"
SCHEME="Matcha"
CONFIG="Release"
BUILD_DIR="$PROJECT_DIR/build/release"
ARCHIVE_PATH="$BUILD_DIR/Matcha.xcarchive"
EXPORT_PATH="$BUILD_DIR/export"
EXPORT_PLIST="$BUILD_DIR/ExportOptions.plist"
APP_PATH="$EXPORT_PATH/Matcha.app"
ZIP_PATH="$BUILD_DIR/Matcha.zip"
DMG_PATH="$BUILD_DIR/Matcha.dmg"

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

MAKE_DMG=false
SKIP_NOTARIZE=false
for arg in "$@"; do
    case "$arg" in
        --dmg) MAKE_DMG=true ;;
        --skip-notarize) SKIP_NOTARIZE=true ;;
        -h|--help) grep -E '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "${RED}unknown arg:${NC} $arg"; exit 1 ;;
    esac
done

require() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then
        echo "${RED}error:${NC} env var $name is required"
        exit 1
    fi
}

# Default team + bundle come from the pbxproj (DEVELOPMENT_TEAM = 5D6TJVCPBK,
# PRODUCT_BUNDLE_IDENTIFIER = com.ahnimal.matcha). Both can be overridden via env.
APPLE_TEAM_ID="${APPLE_TEAM_ID:-5D6TJVCPBK}"
BUNDLE_ID_OVERRIDE="${BUNDLE_ID:-}"

if ! $SKIP_NOTARIZE; then
    if [[ -n "${APPLE_API_KEY_ID:-}" ]]; then
        require APPLE_API_KEY_ID
        require APPLE_API_ISSUER_ID
        require APPLE_API_KEY_PATH
        if [[ ! -f "$APPLE_API_KEY_PATH" ]]; then
            echo "${RED}error:${NC} API key not found at $APPLE_API_KEY_PATH"
            exit 1
        fi
        NOTARY_AUTH=(--key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER_ID")
    elif [[ -n "${APPLE_ID:-}" ]]; then
        require APPLE_ID
        require APPLE_APP_PASSWORD
        NOTARY_AUTH=(--apple-id "$APPLE_ID" --password "$APPLE_APP_PASSWORD" --team-id "$APPLE_TEAM_ID")
    else
        echo "${RED}error:${NC} set either APPLE_API_KEY_* or APPLE_ID + APPLE_APP_PASSWORD, or pass --skip-notarize"
        exit 1
    fi
fi

echo "${DIM}team:${NC} $APPLE_TEAM_ID"
if [[ -n "$BUNDLE_ID_OVERRIDE" ]]; then
    echo "${DIM}bundle id:${NC} $BUNDLE_ID_OVERRIDE (overridden)"
fi

# Fresh build dir each run to avoid stale artifacts
rm -rf "$ARCHIVE_PATH" "$EXPORT_PATH"
mkdir -p "$BUILD_DIR"

# Generate ExportOptions.plist for Developer ID
cat > "$EXPORT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>
    <string>developer-id</string>
    <key>teamID</key>
    <string>$APPLE_TEAM_ID</string>
    <key>signingStyle</key>
    <string>automatic</string>
</dict>
</plist>
PLIST

# Extra xcodebuild settings — injected via command line so the pbxproj stays clean
XCODE_SETTINGS=(
    DEVELOPMENT_TEAM="$APPLE_TEAM_ID"
    CODE_SIGN_STYLE=Automatic
    CODE_SIGN_IDENTITY="Developer ID Application"
    ENABLE_HARDENED_RUNTIME=YES
)
if [[ -n "$BUNDLE_ID_OVERRIDE" ]]; then
    XCODE_SETTINGS+=(PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID_OVERRIDE")
fi

LOG="$(mktemp -t matcha-release.XXXXXX)"

step() { echo "${DIM}==>${NC} $*"; }

step "archiving..."
if ! xcodebuild \
    -project "$PROJECT" \
    -scheme "$SCHEME" \
    -configuration "$CONFIG" \
    -destination 'generic/platform=macOS' \
    -archivePath "$ARCHIVE_PATH" \
    "${XCODE_SETTINGS[@]}" \
    archive >"$LOG" 2>&1; then
    echo "${RED}archive failed${NC}"
    grep -E ": (error|fatal error):" "$LOG" | sed 's/^/  /' || tail -30 "$LOG" | sed 's/^/  /'
    echo "${DIM}full log: $LOG${NC}"
    exit 1
fi

step "exporting signed app..."
if ! xcodebuild \
    -exportArchive \
    -archivePath "$ARCHIVE_PATH" \
    -exportPath "$EXPORT_PATH" \
    -exportOptionsPlist "$EXPORT_PLIST" >>"$LOG" 2>&1; then
    echo "${RED}export failed${NC}"
    grep -E "error:" "$LOG" | sed 's/^/  /' || tail -30 "$LOG" | sed 's/^/  /'
    echo "${DIM}full log: $LOG${NC}"
    exit 1
fi

if [[ ! -d "$APP_PATH" ]]; then
    echo "${RED}error:${NC} exported app not found at $APP_PATH"
    exit 1
fi

# Verify the signature before notarizing
step "verifying signature..."
codesign --verify --deep --strict --verbose=2 "$APP_PATH" 2>&1 | tail -5 | sed 's/^/  /'

step "zipping for distribution..."
rm -f "$ZIP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

if $SKIP_NOTARIZE; then
    echo "${YELLOW}skipping notarization${NC} (--skip-notarize)"
else
    step "submitting to notary service (this usually takes 1–5 minutes)..."
    if ! xcrun notarytool submit "$ZIP_PATH" "${NOTARY_AUTH[@]}" --wait 2>&1 | tee -a "$LOG"; then
        echo "${RED}notarization failed${NC}"
        echo "${DIM}full log: $LOG${NC}"
        exit 1
    fi

    step "stapling ticket..."
    xcrun stapler staple "$APP_PATH"

    # Re-zip after stapling so the archive contains the notarization ticket
    rm -f "$ZIP_PATH"
    ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

    step "gatekeeper check..."
    if spctl --assess --type execute --verbose "$APP_PATH" 2>&1 | sed 's/^/  /'; then
        echo "${GREEN}gatekeeper: accepted${NC}"
    else
        echo "${YELLOW}gatekeeper check did not succeed; inspect manually${NC}"
    fi
fi

if $MAKE_DMG; then
    step "creating DMG..."
    rm -f "$DMG_PATH"
    hdiutil create -volname "Matcha" -srcfolder "$APP_PATH" -ov -format UDZO "$DMG_PATH" >/dev/null
    if ! $SKIP_NOTARIZE; then
        step "notarizing DMG..."
        xcrun notarytool submit "$DMG_PATH" "${NOTARY_AUTH[@]}" --wait >>"$LOG" 2>&1
        xcrun stapler staple "$DMG_PATH"
    fi
fi

echo
echo "${GREEN}release ready${NC}"
echo "  app:  $APP_PATH"
echo "  zip:  $ZIP_PATH"
if $MAKE_DMG; then
    echo "  dmg:  $DMG_PATH"
fi
rm -f "$LOG"
