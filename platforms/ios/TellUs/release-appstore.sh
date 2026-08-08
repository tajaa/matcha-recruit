#!/usr/bin/env bash
# Build, archive, and upload Tell-Us to App Store Connect.
#
# Auto-bumps CURRENT_PROJECT_VERSION (build number) before archiving so every
# upload gets a fresh number — App Store Connect rejects duplicates. Unlike
# Espresso's Matcha.xcodeproj (hand-maintained pbxproj), TellUs is XcodeGen-
# managed: the bump edits project.yml, then `xcodegen generate` regenerates
# TellUs.xcodeproj before archiving, so both files stay in sync.
#
# One-time setup (out of band):
#   1. In Apple Developer portal: register the app with bundle ID
#      com.beetlejuse.app under team 5D6TJVCPBK. Create an App Store
#      provisioning profile (auto-managed via Xcode also works).
#   2. Install certs in your login keychain:
#      - "Apple Distribution"
#      Verify: security find-identity -p codesigning -v
#   3. App Store Connect API key — reuse the one already set up for
#      Espresso's release-appstore.sh (same team), or create one:
#        https://appstoreconnect.apple.com/access/integrations/api
#      Download the .p8, note the Key ID + Issuer ID.
#   4. Create the listing in App Store Connect for com.beetlejuse.app
#      (otherwise the upload is refused).
#
# Required env vars:
#   APPLE_API_KEY_ID      App Store Connect API Key ID
#   APPLE_API_ISSUER_ID   App Store Connect Issuer ID (UUID)
#   APPLE_API_KEY_PATH    Path to AuthKey_<id>.p8
#
# Optional:
#   APPLE_TEAM_ID         (default: 5D6TJVCPBK from project.yml)
#   BUNDLE_ID             (default: com.beetlejuse.app from project.yml)
#   MARKETING_VERSION     If set, also overwrites MARKETING_VERSION
#                         (e.g. 1.2.3). Otherwise only build number bumps.
#
# Usage:
#   ./release-appstore.sh                 bump build, archive, upload
#   ./release-appstore.sh --no-upload     bump + archive only (test the build)
#   ./release-appstore.sh --no-bump       skip the build-number bump (re-upload
#                                         the same number — only useful if a
#                                         prior upload failed mid-flight)
#   ./release-appstore.sh --status        show project.yml build + last 20 attempts
#   ./release-appstore.sh --set-build N   force project.yml to N (recover from drift
#                                         when project.yml falls behind ASC because
#                                         a previous archive failed and rolled
#                                         back). Next run bumps from N.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/TellUs.xcodeproj"
PROJECT_YML="$PROJECT_DIR/project.yml"
SCHEME="TellUs"
CONFIG="Release"
BUILD_DIR="$PROJECT_DIR/build/appstore"
ARCHIVE_PATH="$HOME/Library/Developer/Xcode/Archives/$(date +%Y-%m-%d)/TellUs.xcarchive"
EXPORT_PLIST="$BUILD_DIR/ExportOptions.plist"
RELEASE_LOG="$PROJECT_DIR/release.log"

# Persistent attempt log — append-only history of every release attempt with
# build number + archive/upload status. Survives temp-dir cleanup so you can
# always see why a TestFlight number is missing.
log_attempt() {
    local build="$1" archive="$2" upload="$3" note="${4:-}"
    local ts
    ts=$(date +"%Y-%m-%d %H:%M:%S")
    printf "%s  build=%-6s archive=%-7s upload=%-9s %s\n" \
        "$ts" "$build" "$archive" "$upload" "$note" >> "$RELEASE_LOG"
}

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

NO_UPLOAD=false
NO_BUMP=false
SHOW_STATUS=false
SET_BUILD=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-upload) NO_UPLOAD=true; shift ;;
        --no-bump)   NO_BUMP=true; shift ;;
        --status)    SHOW_STATUS=true; shift ;;
        --set-build) SET_BUILD="$2"; shift 2 ;;
        --set-build=*) SET_BUILD="${1#*=}"; shift ;;
        -h|--help)   grep -E '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)           echo "${RED}unknown arg:${NC} $1"; exit 1 ;;
    esac
done

if [[ -n "$SET_BUILD" ]]; then
    if ! [[ "$SET_BUILD" =~ ^[0-9]+(\.[0-9]+)*$ ]]; then
        echo "${RED}error:${NC} --set-build value must be numeric (e.g. 18)"
        exit 1
    fi
    OLD=$(grep -oE 'CURRENT_PROJECT_VERSION: "[0-9]+(\.[0-9]+)*"' "$PROJECT_YML" | head -1 | sed -E 's/.*"([0-9.]+)"/\1/')
    sed -i '' "s/CURRENT_PROJECT_VERSION: \"${OLD}\"/CURRENT_PROJECT_VERSION: \"${SET_BUILD}\"/g" "$PROJECT_YML"
    echo "${GREEN}build number:${NC} ${OLD} → ${SET_BUILD} (manual override)"
    echo "${DIM}use this to recover from project.yml/ASC drift; next run will bump from ${SET_BUILD}${NC}"
    exit 0
fi

if $SHOW_STATUS; then
    echo "${DIM}project.yml build:${NC} $(grep -oE 'CURRENT_PROJECT_VERSION: "[0-9]+(\.[0-9]+)*"' "$PROJECT_YML" | head -1 | sed -E 's/.*"([0-9.]+)"/\1/')"
    if [[ -f "$RELEASE_LOG" ]]; then
        echo "${DIM}last 20 release attempts (release.log):${NC}"
        tail -20 "$RELEASE_LOG" | sed 's/^/  /'
    else
        echo "${DIM}no release.log yet${NC}"
    fi
    echo
    echo "${DIM}TestFlight (live):${NC} https://appstoreconnect.apple.com/apps → Tell-Us → TestFlight"
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

# Defaults from project.yml — overridable via env
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

if ! which xcodegen >/dev/null 2>&1; then
    echo "${RED}error:${NC} xcodegen not installed (brew install xcodegen)"
    exit 1
fi

# ─── Bump build number ────────────────────────────────────────────────────
# XcodeGen-managed project: the bump edits project.yml (source of truth),
# then `xcodegen generate` regenerates TellUs.xcodeproj from it — unlike
# Espresso's hand-maintained pbxproj, editing the pbxproj directly here would
# be silently discarded on the next generate.
BUMP_DONE=false
PROJECT_YML_BACKUP=""
OLD_VERSION=""
NEW_VERSION=""

bump_build_number() {
    OLD_VERSION=$(grep -oE 'CURRENT_PROJECT_VERSION: "[0-9]+(\.[0-9]+)*"' "$PROJECT_YML" | head -1 | sed -E 's/.*"([0-9.]+)"/\1/')
    if [[ -z "$OLD_VERSION" ]]; then
        echo "${RED}error:${NC} no CURRENT_PROJECT_VERSION found in project.yml"
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
    PROJECT_YML_BACKUP="$(mktemp -t tellus-projectyml.XXXXXX)"
    cp "$PROJECT_YML" "$PROJECT_YML_BACKUP"
    sed -i '' "s/CURRENT_PROJECT_VERSION: \"${OLD_VERSION}\"/CURRENT_PROJECT_VERSION: \"${NEW_VERSION}\"/g" "$PROJECT_YML"
    BUMP_DONE=true
    echo "${GREEN}build number:${NC} ${OLD_VERSION} → ${NEW_VERSION}"
}

bump_marketing_version() {
    [[ -z "${MARKETING_VERSION:-}" ]] && return
    local old new
    old=$(grep -oE 'MARKETING_VERSION: "[^"]+"' "$PROJECT_YML" | head -1 | sed -E 's/.*"([^"]+)"/\1/')
    new="$MARKETING_VERSION"
    sed -i '' "s/MARKETING_VERSION: \"${old}\"/MARKETING_VERSION: \"${new}\"/g" "$PROJECT_YML"
    echo "${GREEN}marketing version:${NC} ${old} → ${new}"
}

rollback_bump() {
    if $BUMP_DONE && [[ -f "$PROJECT_YML_BACKUP" ]]; then
        cp "$PROJECT_YML_BACKUP" "$PROJECT_YML"
        xcodegen generate >/dev/null 2>&1 || true
        echo "${YELLOW}rolled back build number to ${OLD_VERSION}${NC}"
    fi
    [[ -n "$PROJECT_YML_BACKUP" ]] && rm -f "$PROJECT_YML_BACKUP"
}

# ─── Archive ──────────────────────────────────────────────────────────────
do_archive() {
    rm -rf "$ARCHIVE_PATH"
    mkdir -p "$BUILD_DIR" "$(dirname "$ARCHIVE_PATH")"

    step "regenerating TellUs.xcodeproj from project.yml..."
    (cd "$PROJECT_DIR" && xcodegen generate) >/dev/null

    # destination=upload tells `xcodebuild -exportArchive` to ship the build
    # straight to App Store Connect (instead of writing a .pkg locally) AND
    # write a Distributions entry into the .xcarchive's Info.plist — which is
    # what flips Xcode Organizer's "Status" column to "Uploaded to Apple".
    cat > "$EXPORT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key>           <string>app-store</string>
    <key>destination</key>      <string>upload</string>
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
    log="$(mktemp -t tellus-asc.XXXXXX)"

    step "archiving (Release, Apple Distribution)..."
    if ! xcodebuild \
            -project "$PROJECT" \
            -scheme "$SCHEME" \
            -configuration "$CONFIG" \
            -destination 'generic/platform=iOS' \
            -archivePath "$ARCHIVE_PATH" \
            "${xcode_settings[@]}" \
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
    upload_log="$(mktemp -t tellus-upload.XXXXXX)"

    step "uploading to App Store Connect (this can take 1–10 min)..."
    if ! xcodebuild \
            -exportArchive \
            -archivePath "$ARCHIVE_PATH" \
            -exportOptionsPlist "$EXPORT_PLIST" \
            -authenticationKeyPath "$APPLE_API_KEY_PATH" \
            -authenticationKeyID "$APPLE_API_KEY_ID" \
            -authenticationKeyIssuerID "$APPLE_API_ISSUER_ID" >"$upload_log" 2>&1; then
        echo "${RED}upload failed${NC}"
        echo "${DIM}common causes:${NC}"
        echo "  - bundle id not registered in App Store Connect"
        echo "  - build number ($NEW_VERSION) already used (re-run normally to bump again)"
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
trap 'rollback_bump' ERR

if ! $NO_BUMP; then
    bump_build_number
    bump_marketing_version
fi

if ! do_archive; then
    log_attempt "$NEW_VERSION" "FAIL" "skipped" "archive failed — rolled back to $OLD_VERSION"
    rollback_bump
    exit 1
fi

# At this point the bump is "earned" — even if upload fails, the build number
# was used in a real archive and shouldn't be reused for a different build.
trap - ERR
[[ -n "$PROJECT_YML_BACKUP" ]] && rm -f "$PROJECT_YML_BACKUP"

# Auto-commit the project.yml bump (+ the regenerated pbxproj) so subsequent
# runs and fresh checkouts see the correct baseline. Without this, the bump
# lives only in the uncommitted working tree — any `git checkout -- project.yml`
# or branch switch silently regresses the build number, and the next run
# bumps from the old committed value, producing a duplicate App Store Connect
# rejects. Only stage these two files explicitly so unrelated working-tree
# changes don't get swept in.
if ! $NO_BUMP && [[ -n "$NEW_VERSION" ]]; then
    if git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        git -C "$PROJECT_DIR" add "$PROJECT_YML" "$PROJECT_DIR/TellUs.xcodeproj/project.pbxproj"
        if ! git -C "$PROJECT_DIR" diff --cached --quiet -- "$PROJECT_YML" "$PROJECT_DIR/TellUs.xcodeproj/project.pbxproj"; then
            git -C "$PROJECT_DIR" commit -m "chore(tellus-ios): bump build to ${NEW_VERSION}" \
                -- "$PROJECT_YML" "$PROJECT_DIR/TellUs.xcodeproj/project.pbxproj" >/dev/null
            echo "${GREEN}committed:${NC} build ${NEW_VERSION} project.yml bump"
        fi
    fi
fi

if $NO_UPLOAD; then
    log_attempt "$NEW_VERSION" "OK" "skipped" "--no-upload"
    echo
    echo "${GREEN}archive ready (upload skipped)${NC}"
    echo "  archive: $ARCHIVE_PATH"
    exit 0
fi

if ! do_upload; then
    log_attempt "$NEW_VERSION" "OK" "FAIL" "upload to ASC failed — build number kept; re-run with --no-bump to retry"
    exit 1
fi

log_attempt "$NEW_VERSION" "OK" "OK" "uploaded to ASC; processing 5–15 min before TestFlight"

echo
echo "${GREEN}uploaded to App Store Connect${NC}"
echo "  build:   $NEW_VERSION"
echo "  archive: $ARCHIVE_PATH"
echo "  next:    https://appstoreconnect.apple.com/ → Tell-Us → TestFlight"
echo
echo "${DIM}note: ASC needs ~5–15 min to process the build before it appears${NC}"
echo "${DIM}note: Xcode Organizer Status column updates once xcodebuild writes the Distributions entry${NC}"
echo "${DIM}history: ./release-appstore.sh --status${NC}"
