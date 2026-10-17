#!/usr/bin/env bash
# Build, archive, and upload Matcha to App Store Connect.
#
# Build numbers come from App Store Connect, not the pbxproj: the upload runs
# with manageAppVersionAndBuildNumber, so Xcode gives each upload the next free
# build number (archives built at CURRENT_PROJECT_VERSION 97 went up as builds
# 125–129). The script used to bump CURRENT_PROJECT_VERSION and commit it
# before archiving. The Espresso target never read the number it bumped, and
# the commit landed on whatever branch was checked out — usually local main,
# which was then one commit ahead of origin, so the next `git pull` after any
# merge diverged. Nothing is bumped or committed now; release.log records the
# number App Store Connect assigned.
# Surfaces errors with context so you can fix and re-run.
#
# One-time setup (out of band):
#   1. In Apple Developer portal: register the app with bundle ID
#      com.matchawork.app under team 5D6TJVCPBK. Create an App Store
#      provisioning profile (auto-managed via Xcode also works).
#   2. Install certs in your login keychain:
#      - "Apple Distribution" (or "3rd Party Mac Developer Application")
#      - "3rd Party Mac Developer Installer"
#      Verify: security find-identity -p codesigning -v
#   3. Create an App Store Connect API key:
#        https://appstoreconnect.apple.com/access/integrations/api
#      Download the .p8, note the Key ID + Issuer ID.
#   4. Create the listing in App Store Connect for com.matchawork.app
#      (otherwise altool refuses the upload).
#
# Required env vars:
#   APPLE_API_KEY_ID      App Store Connect API Key ID
#   APPLE_API_ISSUER_ID   App Store Connect Issuer ID (UUID)
#   APPLE_API_KEY_PATH    Path to AuthKey_<id>.p8
#
# Optional:
#   APPLE_TEAM_ID         (default: 5D6TJVCPBK from pbxproj)
#   BUNDLE_ID             (default: com.matchawork.app from pbxproj)
#   MARKETING_VERSION     If set, overwrites MARKETING_VERSION (e.g. 1.2.3)
#                         in the pbxproj before archiving. The edit is left
#                         uncommitted for you to land through a PR.
#
# Usage:
#   ./release-appstore.sh                 archive, upload
#   ./release-appstore.sh --no-upload     archive only (test the build)
#   ./release-appstore.sh --status        show the last 20 attempts
#
# --no-bump and --set-build N are still accepted and do nothing: App Store
# Connect numbers every upload, so there is no local build number to manage.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=../../apple-env.sh
source "$PROJECT_DIR/../../apple-env.sh"
PROJECT="$PROJECT_DIR/Matcha.xcodeproj"
PBXPROJ="$PROJECT/project.pbxproj"
SCHEME="Matcha"
CONFIG="Release"
BUILD_DIR="$PROJECT_DIR/build/appstore"
ARCHIVE_PATH="$HOME/Library/Developer/Xcode/Archives/$(date +%Y-%m-%d)/Espresso.xcarchive"
EXPORT_PATH="$BUILD_DIR/export"   # legacy — only used if --no-upload is ever extended; current upload path skips local export
EXPORT_PLIST="$BUILD_DIR/ExportOptions.plist"
RELEASE_LOG="$PROJECT_DIR/release.log"

# Persistent attempt log — append-only history of every release attempt with
# build number + archive/upload status. Survives temp-dir cleanup so you can
# always see why a TestFlight number is missing. The build column is the number
# App Store Connect assigned ("-" when nothing was uploaded). Lines before
# 2026-10-17 show the pbxproj bump instead, which from the July Werk → Espresso
# rename until then was not the number the app carried.
log_attempt() {
    local build="$1" archive="$2" upload="$3" note="${4:-}"
    local ts
    ts=$(date +"%Y-%m-%d %H:%M:%S")
    printf "%s  build=%-6s archive=%-7s upload=%-9s %s\n" \
        "$ts" "$build" "$archive" "$upload" "$note" >> "$RELEASE_LOG"
}

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

NO_UPLOAD=false
SHOW_STATUS=false
NO_BUILD_NUMBERS="${DIM}App Store Connect assigns the build number at upload; there is no local build number to manage${NC}"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-upload) NO_UPLOAD=true; shift ;;
        --no-bump)   echo "--no-bump does nothing now: $NO_BUILD_NUMBERS"; shift ;;
        --status)    SHOW_STATUS=true; shift ;;
        --set-build|--set-build=*)
            echo "--set-build does nothing now: $NO_BUILD_NUMBERS"; exit 0 ;;
        -h|--help)   grep -E '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)           echo "${RED}unknown arg:${NC} $1"; exit 1 ;;
    esac
done

if $SHOW_STATUS; then
    if [[ -f "$RELEASE_LOG" ]]; then
        echo "${DIM}last 20 release attempts (release.log):${NC}"
        tail -20 "$RELEASE_LOG" | sed 's/^/  /'
    else
        echo "${DIM}no release.log yet${NC}"
    fi
    echo
    echo "${DIM}TestFlight (live):${NC} https://appstoreconnect.apple.com/apps → Matcha → TestFlight"
    exit 0
fi

require() {
    local name="$1"
    if [[ -z "${!name:-}" ]]; then
        echo "${RED}error:${NC} env var $name is required"
        exit 1
    fi
}

step() { echo "${DIM}==>${NC} $*"; }

# Defaults from pbxproj — overridable via env
APPLE_TEAM_ID="${APPLE_TEAM_ID:-5D6TJVCPBK}"
BUNDLE_ID_OVERRIDE="${BUNDLE_ID:-}"

# Validate auth env up front — failing here saves a 5-minute archive
if ! $NO_UPLOAD; then
    require APPLE_API_KEY_ID
    require APPLE_API_ISSUER_ID
    require APPLE_API_KEY_PATH
    if [[ ! -f "$APPLE_API_KEY_PATH" ]]; then
        echo "${RED}error:${NC} API key not found at $APPLE_API_KEY_PATH"
        exit 1
    fi
fi

# ─── Marketing version ────────────────────────────────────────────────────
# Only when MARKETING_VERSION is set. Rolled back if the archive fails;
# otherwise left in the working tree for you to commit.
MARKETING_DONE=false
PBXPROJ_BACKUP=""

set_marketing_version() {
    [[ -z "${MARKETING_VERSION:-}" ]] && return
    local old
    old=$(grep -oE 'MARKETING_VERSION = [^;]+' "$PBXPROJ" | head -1 | awk -F' = ' '{print $2}')
    PBXPROJ_BACKUP="$(mktemp -t matcha-pbxproj.XXXXXX)"
    cp "$PBXPROJ" "$PBXPROJ_BACKUP"
    sed -i '' "s/MARKETING_VERSION = ${old};/MARKETING_VERSION = ${MARKETING_VERSION};/g" "$PBXPROJ"
    MARKETING_DONE=true
    echo "${GREEN}marketing version:${NC} ${old} → ${MARKETING_VERSION}"
}

rollback_marketing_version() {
    if $MARKETING_DONE && [[ -f "$PBXPROJ_BACKUP" ]]; then
        cp "$PBXPROJ_BACKUP" "$PBXPROJ"
        echo "${YELLOW}rolled back marketing version${NC}"
    fi
    [[ -n "$PBXPROJ_BACKUP" ]] && rm -f "$PBXPROJ_BACKUP"
}

# The build number App Store Connect gave this archive's upload: xcodebuild
# writes it into the archive's Distributions entry. Empty if none was given.
uploaded_build_number() {
    local plist="$ARCHIVE_PATH/Info.plist" i=0 n="" v
    while /usr/libexec/PlistBuddy -c "Print :Distributions:${i}" "$plist" >/dev/null 2>&1; do
        v=$(/usr/libexec/PlistBuddy -c "Print :Distributions:${i}:uploadedBuildNumber" "$plist" 2>/dev/null) && n="$v"
        i=$((i + 1))
    done
    echo "$n"
}

# ─── Archive ──────────────────────────────────────────────────────────────
do_archive() {
    rm -rf "$ARCHIVE_PATH" "$EXPORT_PATH"
    mkdir -p "$BUILD_DIR" "$(dirname "$ARCHIVE_PATH")"

    # Manual signing: automatic export asks Apple for cloud-managed distribution
    # signing, which API keys may not use ("Cloud signing permission error").
    # Needs the Apple Distribution + Mac Installer certs in the keychain and the
    # "Espresso Mac App Store" profile (override APPSTORE_PROFILE_NAME).
    # destination=upload tells `xcodebuild -exportArchive` to ship the build
    # straight to App Store Connect (instead of writing a .pkg locally) AND
    # write a Distributions entry into the .xcarchive's Info.plist — which is
    # what flips Xcode Organizer's "Status" column to "Uploaded to Apple".
    # altool ships the .pkg but never touches the archive, so Organizer
    # showed `—` for every build despite ASC accepting the upload.
    cat > "$EXPORT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>           <string>app-store</string>
    <key>destination</key>      <string>upload</string>
    <key>teamID</key>           <string>$APPLE_TEAM_ID</string>
    <key>signingStyle</key>     <string>manual</string>
    <key>signingCertificate</key> <string>Apple Distribution</string>
    <key>installerSigningCertificate</key> <string>3rd Party Mac Developer Installer</string>
    <key>provisioningProfiles</key>
    <dict><key>${BUNDLE_ID_OVERRIDE:-com.matchawork.app}</key><string>${APPSTORE_PROFILE_NAME:-Espresso Mac App Store}</string></dict>
    <key>uploadSymbols</key>    <true/>
    <key>manageAppVersionAndBuildNumber</key> <true/>
</dict>
</plist>
PLIST

    # Embed Codex rejects anything but arm64 (see CodexRuntime/README.md).
    local xcode_settings=(
        DEVELOPMENT_TEAM="$APPLE_TEAM_ID"
        CODE_SIGN_STYLE=Automatic
        ARCHS=arm64
        ONLY_ACTIVE_ARCH=NO
    )
    # Let Xcode create/refresh certs and profiles with the API key when this
    # machine's keychain doesn't have them (automatic signing).
    local auth_args=()
    if [[ -n "${APPLE_API_KEY_ID:-}" && -f "${APPLE_API_KEY_PATH:-}" ]]; then
        auth_args=(-allowProvisioningUpdates
            -authenticationKeyPath "$APPLE_API_KEY_PATH"
            -authenticationKeyID "$APPLE_API_KEY_ID"
            -authenticationKeyIssuerID "${APPLE_API_ISSUER_ID:-}")
    fi
    [[ -n "$BUNDLE_ID_OVERRIDE" ]] && xcode_settings+=(PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID_OVERRIDE")

    local log
    log="$(mktemp -t matcha-asc.XXXXXX)"

    step "archiving (Release, Apple Distribution)..."
    if ! xcodebuild \
            -project "$PROJECT" \
            -scheme "$SCHEME" \
            -configuration "$CONFIG" \
            -destination 'generic/platform=macOS' \
            -archivePath "$ARCHIVE_PATH" \
            "${xcode_settings[@]}" \
            ${auth_args[@]+"${auth_args[@]}"} \
            archive >"$log" 2>&1; then
        echo "${RED}archive failed${NC}"
        grep -E ": (error|fatal error):" "$log" | sed 's/^/  /' || tail -40 "$log" | sed 's/^/  /'
        echo "${DIM}full log: $log${NC}"
        return 1
    fi

    rm -f "$log"
    return 0
}

# ─── Upload ───────────────────────────────────────────────────────────────
# Uses xcodebuild -exportArchive with destination=upload so the archive's
# Distributions plist gets a new entry — Organizer reads that to populate
# the Status column. Auth via -authenticationKey* flags (same path Xcode's
# Distribute App uses), no .pkg or altool round-trip.
do_upload() {
    local upload_log
    upload_log="$(mktemp -t matcha-upload.XXXXXX)"

    step "uploading to App Store Connect (this can take 1–10 min)..."
    if ! xcodebuild \
            -exportArchive \
            -archivePath "$ARCHIVE_PATH" \
            -exportOptionsPlist "$EXPORT_PLIST" \
            -allowProvisioningUpdates \
            -authenticationKeyPath "$APPLE_API_KEY_PATH" \
            -authenticationKeyID "$APPLE_API_KEY_ID" \
            -authenticationKeyIssuerID "$APPLE_API_ISSUER_ID" >"$upload_log" 2>&1; then
        echo "${RED}upload failed${NC}"
        echo "${DIM}common causes:${NC}"
        echo "  - bundle id not registered in App Store Connect"
        echo "  - invalid App Store Connect API key (check APPLE_API_KEY_ID / ISSUER_ID / PATH)"
        echo "  - cert / provisioning-profile mismatch"
        grep -E ": (error|fatal error):|error:" "$upload_log" | head -20 | sed 's/^/  /' || tail -40 "$upload_log" | sed 's/^/  /'
        echo "${DIM}full log: $upload_log${NC}"
        return 1
    fi

    # xcodebuild may exit 0 but still log an ITMS / Transporter problem.
    if grep -qE "ERROR ITMS|UNEXPECTED|No suitable" "$upload_log"; then
        echo "${RED}upload reported errors despite zero exit:${NC}"
        grep -E "ERROR ITMS|UNEXPECTED|No suitable" "$upload_log" | sed 's/^/  /'
        echo "${DIM}full log: $upload_log${NC}"
        return 1
    fi

    rm -f "$upload_log"
    return 0
}

# ─── Main ─────────────────────────────────────────────────────────────────
trap 'rollback_marketing_version' ERR

set_marketing_version

if ! do_archive; then
    log_attempt "-" "FAIL" "skipped" "archive failed"
    rollback_marketing_version
    exit 1
fi

trap - ERR
[[ -n "$PBXPROJ_BACKUP" ]] && rm -f "$PBXPROJ_BACKUP"
if $MARKETING_DONE; then
    echo "${DIM}MARKETING_VERSION ${MARKETING_VERSION} is in the pbxproj, uncommitted — land it through a PR${NC}"
fi

if $NO_UPLOAD; then
    log_attempt "-" "OK" "skipped" "--no-upload"
    echo
    echo "${GREEN}archive ready (upload skipped)${NC}"
    echo "  archive: $ARCHIVE_PATH"
    exit 0
fi

if ! do_upload; then
    log_attempt "-" "OK" "FAIL" "upload to ASC failed — fix and re-run"
    exit 1
fi

BUILD_NUMBER="$(uploaded_build_number)"
log_attempt "${BUILD_NUMBER:-?}" "OK" "OK" "uploaded to ASC; processing 5–15 min before TestFlight"

echo
echo "${GREEN}uploaded to App Store Connect${NC}"
echo "  build:   ${BUILD_NUMBER:-? (not recorded in the archive — check TestFlight)}"
echo "  archive: $ARCHIVE_PATH"
echo "  next:    https://appstoreconnect.apple.com/ → Matcha → TestFlight (Mac)"
echo
echo "${DIM}note: ASC needs ~5–15 min to process the build before it appears${NC}"
echo "${DIM}note: Xcode Organizer Status column updates once xcodebuild writes the Distributions entry${NC}"
echo "${DIM}history: ./release-appstore.sh --status${NC}"
