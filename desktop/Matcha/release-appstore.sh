#!/usr/bin/env bash
# Build, archive, and upload Matcha to App Store Connect.
#
# Auto-bumps CURRENT_PROJECT_VERSION (build number) before archiving so every
# upload gets a fresh number — App Store Connect rejects duplicates.
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
#   MARKETING_VERSION     If set, also overwrites MARKETING_VERSION
#                         (e.g. 1.2.3). Otherwise only build number bumps.
#
# Usage:
#   ./release-appstore.sh                 bump build, archive, upload
#   ./release-appstore.sh --no-upload     bump + archive only (test the build)
#   ./release-appstore.sh --no-bump       skip the build-number bump (re-upload
#                                         the same number — only useful if a
#                                         prior upload failed mid-flight)

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/Matcha.xcodeproj"
PBXPROJ="$PROJECT/project.pbxproj"
SCHEME="Matcha"
CONFIG="Release"
BUILD_DIR="$PROJECT_DIR/build/appstore"
ARCHIVE_PATH="$HOME/Library/Developer/Xcode/Archives/$(date +%Y-%m-%d)/Matcha.xcarchive"
EXPORT_PATH="$BUILD_DIR/export"
EXPORT_PLIST="$BUILD_DIR/ExportOptions.plist"
PKG_PATH=""  # filled in after export

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

NO_UPLOAD=false
NO_BUMP=false
for arg in "$@"; do
    case "$arg" in
        --no-upload) NO_UPLOAD=true ;;
        --no-bump)   NO_BUMP=true ;;
        -h|--help)   grep -E '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)           echo "${RED}unknown arg:${NC} $arg"; exit 1 ;;
    esac
done

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

# ─── Bump build number ────────────────────────────────────────────────────
# Read all CURRENT_PROJECT_VERSION occurrences in pbxproj (Debug + Release
# configs share a value usually, but we bump every match so they stay synced).
BUMP_DONE=false
PBXPROJ_BACKUP=""
OLD_VERSION=""
NEW_VERSION=""

bump_build_number() {
    OLD_VERSION=$(grep -oE 'CURRENT_PROJECT_VERSION = [0-9]+(\.[0-9]+)*' "$PBXPROJ" | head -1 | awk '{print $3}')
    if [[ -z "$OLD_VERSION" ]]; then
        echo "${RED}error:${NC} no CURRENT_PROJECT_VERSION found in pbxproj"
        exit 1
    fi
    # Bump the last numeric component (e.g. 2.1 → 2.2, 3 → 4)
    local prefix last
    prefix="${OLD_VERSION%.*}"
    last="${OLD_VERSION##*.}"
    if [[ "$prefix" == "$last" ]]; then
        NEW_VERSION=$(( last + 1 ))
    else
        NEW_VERSION="${prefix}.$((last + 1))"
    fi
    PBXPROJ_BACKUP="$(mktemp -t matcha-pbxproj.XXXXXX)"
    cp "$PBXPROJ" "$PBXPROJ_BACKUP"
    sed -i '' "s/CURRENT_PROJECT_VERSION = ${OLD_VERSION};/CURRENT_PROJECT_VERSION = ${NEW_VERSION};/g" "$PBXPROJ"
    BUMP_DONE=true
    echo "${GREEN}build number:${NC} ${OLD_VERSION} → ${NEW_VERSION}"
}

bump_marketing_version() {
    [[ -z "${MARKETING_VERSION:-}" ]] && return
    local old new
    old=$(grep -oE 'MARKETING_VERSION = [^;]+' "$PBXPROJ" | head -1 | awk -F' = ' '{print $2}')
    new="$MARKETING_VERSION"
    sed -i '' "s/MARKETING_VERSION = ${old};/MARKETING_VERSION = ${new};/g" "$PBXPROJ"
    echo "${GREEN}marketing version:${NC} ${old} → ${new}"
}

rollback_bump() {
    if $BUMP_DONE && [[ -f "$PBXPROJ_BACKUP" ]]; then
        cp "$PBXPROJ_BACKUP" "$PBXPROJ"
        echo "${YELLOW}rolled back build number to ${OLD_VERSION}${NC}"
    fi
    [[ -n "$PBXPROJ_BACKUP" ]] && rm -f "$PBXPROJ_BACKUP"
}

# ─── Archive ──────────────────────────────────────────────────────────────
do_archive() {
    rm -rf "$ARCHIVE_PATH" "$EXPORT_PATH"
    mkdir -p "$BUILD_DIR" "$(dirname "$ARCHIVE_PATH")"

    cat > "$EXPORT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>           <string>app-store</string>
    <key>destination</key>      <string>export</string>
    <key>teamID</key>           <string>$APPLE_TEAM_ID</string>
    <key>signingStyle</key>     <string>automatic</string>
    <key>uploadSymbols</key>    <true/>
</dict>
</plist>
PLIST

    local xcode_settings=(
        DEVELOPMENT_TEAM="$APPLE_TEAM_ID"
        CODE_SIGN_STYLE=Automatic
    )
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
            archive >"$log" 2>&1; then
        echo "${RED}archive failed${NC}"
        grep -E ": (error|fatal error):" "$log" | sed 's/^/  /' || tail -40 "$log" | sed 's/^/  /'
        echo "${DIM}full log: $log${NC}"
        return 1
    fi

    step "exporting signed .pkg for App Store..."
    if ! xcodebuild \
            -exportArchive \
            -archivePath "$ARCHIVE_PATH" \
            -exportPath "$EXPORT_PATH" \
            -exportOptionsPlist "$EXPORT_PLIST" >>"$log" 2>&1; then
        echo "${RED}export failed${NC}"
        grep -E "error:" "$log" | sed 's/^/  /' || tail -40 "$log" | sed 's/^/  /'
        echo "${DIM}full log: $log${NC}"
        return 1
    fi

    PKG_PATH=$(find "$EXPORT_PATH" -name "*.pkg" -maxdepth 2 2>/dev/null | head -1)
    if [[ -z "$PKG_PATH" || ! -f "$PKG_PATH" ]]; then
        echo "${RED}error:${NC} export succeeded but no .pkg produced under $EXPORT_PATH"
        ls -la "$EXPORT_PATH" 2>/dev/null | sed 's/^/  /' || true
        return 1
    fi
    echo "${GREEN}exported:${NC} $PKG_PATH"
    rm -f "$log"
    return 0
}

# ─── Upload ───────────────────────────────────────────────────────────────
do_upload() {
    # altool requires the .p8 in a standard location OR the API_PRIVATE_KEYS_DIR
    # env var pointing at its directory. We use the env-var path so we don't
    # have to copy keys around.
    local key_dir
    key_dir=$(dirname "$APPLE_API_KEY_PATH")
    export API_PRIVATE_KEYS_DIR="$key_dir"

    local upload_log
    upload_log="$(mktemp -t matcha-upload.XXXXXX)"

    step "uploading to App Store Connect (this can take 1–10 min)..."
    if ! xcrun altool --upload-app \
            -f "$PKG_PATH" \
            -t macos \
            --apiKey "$APPLE_API_KEY_ID" \
            --apiIssuer "$APPLE_API_ISSUER_ID" 2>&1 | tee "$upload_log"; then
        echo "${RED}upload failed${NC}"
        echo "${DIM}common causes:${NC}"
        echo "  - bundle id not registered in App Store Connect"
        echo "  - build number ($NEW_VERSION) already used (re-run normally to bump again)"
        echo "  - cert / provisioning-profile mismatch"
        echo "  - missing 'Mac Installer Distribution' cert for .pkg signing"
        echo "${DIM}full log: $upload_log${NC}"
        return 1
    fi

    # altool writes warnings/errors to stdout even on "success" exit — sanity check
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
trap 'rollback_bump' ERR

if ! $NO_BUMP; then
    bump_build_number
    bump_marketing_version
fi

if ! do_archive; then
    rollback_bump
    exit 1
fi

# At this point the bump is "earned" — even if upload fails, the build number
# was used in a real archive and shouldn't be reused for a different build.
trap - ERR
[[ -n "$PBXPROJ_BACKUP" ]] && rm -f "$PBXPROJ_BACKUP"

# Auto-commit the pbxproj bump so subsequent runs (and fresh checkouts) see
# the correct baseline. Without this, the bump lives only in the uncommitted
# working tree — any `git checkout -- pbxproj` or branch switch silently
# regresses the build number, and the next run bumps from the old committed
# value, producing a duplicate build number that App Store Connect rejects.
# Only stage the pbxproj explicitly so unrelated working-tree changes don't
# get swept in.
if ! $NO_BUMP && [[ -n "$NEW_VERSION" ]]; then
    if git -C "$(dirname "$PBXPROJ")" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git add "$PBXPROJ"
        if ! git diff --cached --quiet -- "$PBXPROJ"; then
            git commit -m "chore(desktop): bump build to ${NEW_VERSION}" -- "$PBXPROJ" >/dev/null
            echo "${GREEN}committed:${NC} build ${NEW_VERSION} pbxproj bump"
        fi
    fi
fi

if $NO_UPLOAD; then
    echo
    echo "${GREEN}archive ready (upload skipped)${NC}"
    echo "  pkg:     $PKG_PATH"
    echo "  archive: $ARCHIVE_PATH"
    exit 0
fi

if ! do_upload; then
    exit 1
fi

echo
echo "${GREEN}uploaded to App Store Connect${NC}"
echo "  build:   $NEW_VERSION"
echo "  pkg:     $PKG_PATH"
echo "  next:    https://appstoreconnect.apple.com/ → Matcha → TestFlight (Mac)"
echo
echo "${DIM}note: ASC needs ~5–15 min to process the build before it appears${NC}"
