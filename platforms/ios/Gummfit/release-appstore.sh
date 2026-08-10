#!/usr/bin/env bash
# Build, archive, and upload Gummfit to App Store Connect.
#
# One-time setup:
#   1. Register com.gummcap.app in Apple Developer and App Store Connect.
#   2. Install an Apple Distribution certificate and the "Gummcap App Store"
#      provisioning profile (or allow xcodebuild to provision it).
#   3. Export an App Store Connect API key and set:
#        APPLE_API_KEY_ID, APPLE_API_ISSUER_ID, APPLE_API_KEY_PATH
#
# Usage:
#   ./release-appstore.sh                 bump, archive, upload
#   ./release-appstore.sh --no-upload     bump + archive only
#   ./release-appstore.sh --no-push       upload without pushing the build commit
#   ./release-appstore.sh --no-bump       re-upload the current build number
#   ./release-appstore.sh --status        show build number and release history
#   ./release-appstore.sh --set-build N   recover from App Store Connect drift
#
# Optional environment variables:
#   APPLE_TEAM_ID       default: 5D6TJVCPBK
#   BUNDLE_ID           default: com.gummcap.app
#   MARKETING_VERSION   overwrite the marketing version before archiving
#   PROVISIONING_PROFILE_NAME default: Gummcap App Store

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/Gummfit.xcodeproj"
PROJECT_YML="$PROJECT_DIR/project.yml"
SCHEME="Gummfit"
CONFIG="Release"
BUILD_DIR="$PROJECT_DIR/build/appstore"
ARCHIVE_PATH="$HOME/Library/Developer/Xcode/Archives/$(date +%Y-%m-%d)/Gummfit.xcarchive"
EXPORT_PLIST="$BUILD_DIR/ExportOptions.plist"
RELEASE_LOG="$PROJECT_DIR/release.log"

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

NO_UPLOAD=false
NO_PUSH=false
NO_BUMP=false
SHOW_STATUS=false
SET_BUILD=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-upload) NO_UPLOAD=true; shift ;;
        --no-push)   NO_PUSH=true; shift ;;
        --no-bump)   NO_BUMP=true; shift ;;
        --status)    SHOW_STATUS=true; shift ;;
        --set-build)
            [[ $# -ge 2 ]] || { echo "${RED}error:${NC} --set-build needs a value"; exit 1; }
            SET_BUILD="$2"; shift 2 ;;
        --set-build=*) SET_BUILD="${1#*=}"; shift ;;
        -h|--help) grep -E '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "${RED}unknown arg:${NC} $1"; exit 1 ;;
    esac
done

APPLE_TEAM_ID="${APPLE_TEAM_ID:-5D6TJVCPBK}"
BUNDLE_ID_OVERRIDE="${BUNDLE_ID:-com.gummcap.app}"
PROFILE_NAME="${PROVISIONING_PROFILE_NAME:-Gummcap App Store}"

log_attempt() {
    local build="$1" archive="$2" upload="$3" note="${4:-}"
    printf "%s  build=%-6s archive=%-7s upload=%-9s %s\n" \
        "$(date +"%Y-%m-%d %H:%M:%S")" "$build" "$archive" "$upload" "$note" >> "$RELEASE_LOG"
}

build_number() {
    grep -oE 'CURRENT_PROJECT_VERSION: "[0-9]+(\.[0-9]+)*"' "$PROJECT_YML" \
        | head -1 | sed -E 's/.*"([0-9.]+)"/\1/'
}

if [[ -n "$SET_BUILD" ]]; then
    [[ "$SET_BUILD" =~ ^[0-9]+(\.[0-9]+)*$ ]] || {
        echo "${RED}error:${NC} --set-build must be numeric (for example 18)"; exit 1;
    }
    OLD="$(build_number)"
    sed -i '' "s/CURRENT_PROJECT_VERSION: \"${OLD}\"/CURRENT_PROJECT_VERSION: \"${SET_BUILD}\"/g" "$PROJECT_YML"
    echo "${GREEN}build number:${NC} ${OLD} → ${SET_BUILD}"
    exit 0
fi

if $SHOW_STATUS; then
    echo "${DIM}project.yml build:${NC} $(build_number)"
    if [[ -f "$RELEASE_LOG" ]]; then
        echo "${DIM}last 20 release attempts:${NC}"
        tail -20 "$RELEASE_LOG" | sed 's/^/  /'
    else
        echo "${DIM}no release.log yet${NC}"
    fi
    echo
    echo "${DIM}TestFlight:${NC} https://appstoreconnect.apple.com/apps"
    exit 0
fi

if ! $NO_UPLOAD; then
    for name in APPLE_API_KEY_ID APPLE_API_ISSUER_ID APPLE_API_KEY_PATH; do
        [[ -n "${!name:-}" ]] || { echo "${RED}error:${NC} env var $name is required"; exit 1; }
    done
    [[ -f "$APPLE_API_KEY_PATH" ]] || {
        echo "${RED}error:${NC} API key not found at $APPLE_API_KEY_PATH"; exit 1;
    }
fi

command -v xcodegen >/dev/null 2>&1 || {
    echo "${RED}error:${NC} xcodegen is not installed (brew install xcodegen)"; exit 1;
}

BUMP_DONE=false
PROJECT_YML_BACKUP=""
OLD_VERSION=""
NEW_VERSION=""
RELEASE_COMMIT=""
PRE_RELEASE_HEAD=""
PRE_RELEASE_UPSTREAM=""

capture_git_state() {
    if ! git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        return 0
    fi
    PRE_RELEASE_HEAD="$(git -C "$PROJECT_DIR" rev-parse HEAD)"
    local upstream
    upstream="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
    if [[ -n "$upstream" ]]; then
        PRE_RELEASE_UPSTREAM="$(git -C "$PROJECT_DIR" rev-parse "$upstream")"
    fi
}

verify_signing_prerequisites() {
    if ! security find-identity -v -p codesigning 2>/dev/null | grep -Fq 'Apple Distribution:'; then
        echo "${RED}error:${NC} no valid Apple Distribution signing identity is installed"
        echo "  Install the Apple Distribution certificate for team ${APPLE_TEAM_ID} in Keychain Access."
        return 1
    fi

    local profile_dir="$HOME/Library/MobileDevice/Provisioning Profiles"
    local profile name
    if [[ -d "$profile_dir" ]]; then
        while IFS= read -r -d '' profile; do
            name="$(security cms -D -i "$profile" 2>/dev/null | plutil -extract Name raw -o - - 2>/dev/null || true)"
            if [[ "$name" == "$PROFILE_NAME" ]]; then
                return 0
            fi
        done < <(find "$profile_dir" -maxdepth 1 -type f -name '*.mobileprovision' -print0)
    fi

    echo "${RED}error:${NC} App Store provisioning profile \"${PROFILE_NAME}\" is not installed"
    echo "  Download it for ${BUNDLE_ID_OVERRIDE} from Apple Developer, then open the .mobileprovision file."
    return 1
}

bump_build_number() {
    OLD_VERSION="$(build_number)"
    [[ -n "$OLD_VERSION" ]] || { echo "${RED}error:${NC} no build number in project.yml"; exit 1; }
    local prefix last
    prefix="${OLD_VERSION%.*}"
    last="${OLD_VERSION##*.}"
    if [[ "$prefix" == "$last" ]]; then NEW_VERSION=$((last + 1)); else NEW_VERSION="${prefix}.$((last + 1))"; fi
    PROJECT_YML_BACKUP="$(mktemp -t gummfit-projectyml.XXXXXX)"
    cp "$PROJECT_YML" "$PROJECT_YML_BACKUP"
    sed -i '' "s/CURRENT_PROJECT_VERSION: \"${OLD_VERSION}\"/CURRENT_PROJECT_VERSION: \"${NEW_VERSION}\"/g" "$PROJECT_YML"
    BUMP_DONE=true
    echo "${GREEN}build number:${NC} ${OLD_VERSION} → ${NEW_VERSION}"
}

bump_marketing_version() {
    [[ -n "${MARKETING_VERSION:-}" ]] || return 0
    local old
    old=$(grep -oE 'MARKETING_VERSION: "[^"]+"' "$PROJECT_YML" | head -1 | sed -E 's/.*"([^"]+)"/\1/')
    sed -i '' "s/MARKETING_VERSION: \"${old}\"/MARKETING_VERSION: \"${MARKETING_VERSION}\"/g" "$PROJECT_YML"
    echo "${GREEN}marketing version:${NC} ${old} → ${MARKETING_VERSION}"
}

rollback_bump() {
    if $BUMP_DONE && [[ -f "$PROJECT_YML_BACKUP" ]]; then
        cp "$PROJECT_YML_BACKUP" "$PROJECT_YML"
        xcodegen generate >/dev/null 2>&1 || true
        echo "${YELLOW}rolled back build number to ${OLD_VERSION}${NC}"
    fi
    [[ -n "$PROJECT_YML_BACKUP" ]] && rm -f "$PROJECT_YML_BACKUP"
}

do_archive() {
    rm -rf "$ARCHIVE_PATH"
    mkdir -p "$BUILD_DIR" "$(dirname "$ARCHIVE_PATH")"
    (cd "$PROJECT_DIR" && xcodegen generate) >/dev/null

    cat > "$EXPORT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key><string>app-store</string>
    <key>destination</key><string>upload</string>
    <key>teamID</key><string>$APPLE_TEAM_ID</string>
    <key>signingStyle</key><string>manual</string>
    <key>signingCertificate</key><string>Apple Distribution</string>
    <key>provisioningProfiles</key>
    <dict><key>$BUNDLE_ID_OVERRIDE</key><string>$PROFILE_NAME</string></dict>
    <key>uploadSymbols</key><true/>
</dict>
</plist>
PLIST

    local provisioning_args=(-allowProvisioningUpdates)
    if [[ -n "${APPLE_API_KEY_PATH:-}" && -f "${APPLE_API_KEY_PATH}" ]]; then
        provisioning_args+=(
            -authenticationKeyPath "$APPLE_API_KEY_PATH"
            -authenticationKeyID "$APPLE_API_KEY_ID"
            -authenticationKeyIssuerID "$APPLE_API_ISSUER_ID"
        )
    fi
    local log
    log="$(mktemp -t gummfit-asc.XXXXXX)"
    if ! xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" \
        -destination 'generic/platform=iOS' -archivePath "$ARCHIVE_PATH" \
        "${provisioning_args[@]}" DEVELOPMENT_TEAM="$APPLE_TEAM_ID" \
        PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE_ID_OVERRIDE" archive >"$log" 2>&1; then
        echo "${RED}archive failed${NC}"
        grep -E ": (error|fatal error):" "$log" | sed 's/^/  /' || tail -40 "$log" | sed 's/^/  /'
        echo "${DIM}full log: $log${NC}"
        return 1
    fi
    rm -f "$log"
}

do_upload() {
    local log="$(mktemp -t gummfit-upload.XXXXXX)"
    if ! xcodebuild -exportArchive -archivePath "$ARCHIVE_PATH" \
        -exportOptionsPlist "$EXPORT_PLIST" \
        -authenticationKeyPath "$APPLE_API_KEY_PATH" \
        -authenticationKeyID "$APPLE_API_KEY_ID" \
        -authenticationKeyIssuerID "$APPLE_API_ISSUER_ID" >"$log" 2>&1; then
        echo "${RED}upload failed${NC}"
        grep -E ": (error|fatal error):|error:" "$log" | head -20 | sed 's/^/  /' || tail -40 "$log" | sed 's/^/  /'
        echo "${DIM}full log: $log${NC}"
        return 1
    fi
    if grep -qE 'ERROR ITMS|UNEXPECTED|No suitable' "$log"; then
        echo "${RED}upload reported errors despite zero exit:${NC}"
        grep -E 'ERROR ITMS|UNEXPECTED|No suitable' "$log" | sed 's/^/  /'
        echo "${DIM}full log: $log${NC}"
        return 1
    fi
    rm -f "$log"
}

trap rollback_bump ERR
verify_signing_prerequisites
capture_git_state
if ! $NO_BUMP; then
    bump_build_number
    bump_marketing_version
fi

if ! do_archive; then
    log_attempt "${NEW_VERSION:-$(build_number)}" FAIL skipped "archive failed — rolled back to ${OLD_VERSION:-unknown}"
    rollback_bump
    exit 1
fi

trap - ERR
[[ -n "$PROJECT_YML_BACKUP" ]] && rm -f "$PROJECT_YML_BACKUP"

# Persist an earned build number, and stage only the generated release inputs.
if ! $NO_BUMP && [[ -n "$NEW_VERSION" ]] && git -C "$PROJECT_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$PROJECT_DIR" add "$PROJECT_YML" "$PROJECT_DIR/Gummfit.xcodeproj/project.pbxproj"
    if ! git -C "$PROJECT_DIR" diff --cached --quiet -- "$PROJECT_YML" "$PROJECT_DIR/Gummfit.xcodeproj/project.pbxproj"; then
        git -C "$PROJECT_DIR" commit -m "chore(gummfit-ios): bump build to ${NEW_VERSION}" \
            -- "$PROJECT_YML" "$PROJECT_DIR/Gummfit.xcodeproj/project.pbxproj" >/dev/null
        RELEASE_COMMIT="$(git -C "$PROJECT_DIR" rev-parse HEAD)"
        echo "${GREEN}committed:${NC} build ${NEW_VERSION} project.yml bump"
    fi
fi

if $NO_UPLOAD; then
    log_attempt "$NEW_VERSION" OK skipped "--no-upload"
    echo "${GREEN}archive ready (upload skipped)${NC}"
    echo "  archive: $ARCHIVE_PATH"
    exit 0
fi

if ! do_upload; then
    log_attempt "$NEW_VERSION" OK FAIL "upload failed — build number kept; retry with --no-bump"
    exit 1
fi

if ! $NO_PUSH && [[ -n "$RELEASE_COMMIT" ]]; then
    current_branch="$(git -C "$PROJECT_DIR" branch --show-current)"
    upstream_ref="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"
    if [[ -z "$current_branch" || -z "$upstream_ref" ]]; then
        log_attempt "$NEW_VERSION" OK OK "upload succeeded; push skipped — branch has no upstream"
        echo "${YELLOW}upload succeeded, but the release commit was not pushed${NC}"
        echo "  push manually: git push"
        exit 1
    fi
    if [[ "$PRE_RELEASE_HEAD" != "$PRE_RELEASE_UPSTREAM" ]]; then
        log_attempt "$NEW_VERSION" OK OK "upload succeeded; push skipped — branch had unpublished commits before release"
        echo "${YELLOW}upload succeeded, but the release commit was not pushed${NC}"
        echo "  push manually after review: git push"
        exit 1
    fi
    upstream_remote="${upstream_ref%%/*}"
    upstream_branch="${upstream_ref#*/}"
    if ! git -C "$PROJECT_DIR" push "$upstream_remote" "HEAD:$upstream_branch"; then
        log_attempt "$NEW_VERSION" OK OK "upload succeeded; push failed — push manually"
        echo "${YELLOW}upload succeeded, but pushing the release commit failed${NC}"
        echo "  retry manually: git push"
        exit 1
    fi
    echo "${GREEN}pushed:${NC} build ${NEW_VERSION} commit"
fi

log_attempt "$NEW_VERSION" OK OK "uploaded to ASC; processing 5–15 min before TestFlight"
echo "${GREEN}uploaded to App Store Connect${NC}"
echo "  bundle:  $BUNDLE_ID_OVERRIDE"
echo "  build:   $NEW_VERSION"
echo "  archive: $ARCHIVE_PATH"
echo "  history: ./release-appstore.sh --status"
