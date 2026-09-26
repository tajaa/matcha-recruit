#!/usr/bin/env bash
# Build/test/open one of the repo's Xcode projects. HOST ONLY — Xcode,
# xcodebuild, codesigning, and the login Keychain cannot run in the Linux
# agent sandbox (apps/msandbox/docs/AGENT_SANDBOX.md). An agent inside the sandbox can
# still edit Swift/project.pbxproj through the bind mount; run this script on
# the Mac to actually build.
#
# Usage: ./scripts/xcode-build.sh <target> [build|build-for-testing|test|open]
# Set XCODE_DESTINATION to override a target's default xcodebuild destination.
#
# Targets:
#   espresso     platforms/desktop/Espresso/Matcha.xcodeproj  (scheme Matcha, macOS)
#   matchatutor  platforms/ios/MatchaTutor/MatchaTutor.xcodeproj
#   tellus       platforms/ios/TellUs/TellUs.xcodeproj
#   gummfit      platforms/ios/Gummfit/Gummfit.xcodeproj
#   storefront   platforms/ios/Storefront/Storefront.xcodeproj
#   matchaschedule platforms/ios/MatchaSchedule/MatchaSchedule.xcodeproj
#
# Every run first lints project.pbxproj (`plutil -lint`) — a hand-edited
# pbxproj that's gone invalid is the most common failure mode after an agent
# adds a file to one of these projects, and it's cheap to catch before a
# multi-minute xcodebuild run.
#
# This script does NOT handle signing/notarization/App Store or prod-tunneled
# runs — use the existing, more specific scripts for those:
#   platforms/desktop/Espresso/release.sh          Developer ID sign+notarize+package
#   platforms/desktop/Espresso/release-appstore.sh App Store submission
#   platforms/desktop/Espresso/run-prod.sh         build + launch against prod EC2
set -euo pipefail

case "${AGENT_SANDBOX:-${CODEX_SANDBOX:-}}" in
    1|true|TRUE|yes|YES)
        echo "Xcode cannot run inside the agent sandbox (no macOS/Xcode in the Linux container)." >&2
        echo "Run this on the host instead: ./scripts/xcode-build.sh $*" >&2
        exit 1
        ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TARGET="${1:-}"
ACTION="${2:-build}"
GENERATE_PROJECT=false
VERIFY_STOREFRONT=false

usage() {
    sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

case "$TARGET" in
    espresso)
        PROJECT="$REPO_ROOT/platforms/desktop/Espresso/Matcha.xcodeproj"
        SCHEME="Matcha"
        DESTINATION="platform=macOS"
        ;;
    matchatutor)
        PROJECT="$REPO_ROOT/platforms/ios/MatchaTutor/MatchaTutor.xcodeproj"
        SCHEME="MatchaTutor"
        DESTINATION="platform=iOS Simulator,name=iPhone 16"
        ;;
    tellus)
        PROJECT="$REPO_ROOT/platforms/ios/TellUs/TellUs.xcodeproj"
        SCHEME="TellUs"
        DESTINATION="platform=iOS Simulator,name=iPhone 16"
        ;;
    gummfit)
        PROJECT="$REPO_ROOT/platforms/ios/Gummfit/Gummfit.xcodeproj"
        SCHEME="Gummfit"
        DESTINATION="platform=iOS Simulator,name=iPhone 16"
        ;;
    storefront)
        PROJECT_DIR="$REPO_ROOT/platforms/ios/Storefront"
        PROJECT="$PROJECT_DIR/Storefront.xcodeproj"
        SCHEME="Ahnimal"
        # A generic simulator destination compiles the app and test bundle
        # without hard-coding one simulator device name. Xcode still needs an
        # installed iOS Simulator runtime to compile the asset catalog.
        DESTINATION="generic/platform=iOS Simulator"
        GENERATE_PROJECT=true
        VERIFY_STOREFRONT=true
        ;;
    matchaschedule)
        PROJECT_DIR="$REPO_ROOT/platforms/ios/MatchaSchedule"
        PROJECT="$PROJECT_DIR/MatchaSchedule.xcodeproj"
        SCHEME="MatchaSchedule"
        DESTINATION="generic/platform=iOS Simulator"
        GENERATE_PROJECT=true
        ;;
    -h|--help|"")
        usage
        exit 0
        ;;
    *)
        echo "Unknown target: $TARGET" >&2
        usage >&2
        exit 1
        ;;
esac

if [[ ( "$TARGET" == "storefront" || "$TARGET" == "matchaschedule" ) && "$ACTION" == "test" ]]; then
    if [[ -z "${XCODE_DESTINATION:-}" || "${XCODE_DESTINATION:-}" == generic/* ]]; then
        if [[ "$TARGET" == "storefront" ]]; then
            echo "Storefront test requires XCODE_DESTINATION to name a concrete iOS Simulator." >&2
        else
            echo "Matcha Schedule test requires XCODE_DESTINATION to name a concrete iOS Simulator." >&2
        fi
        exit 1
    fi
fi
DESTINATION="${XCODE_DESTINATION:-$DESTINATION}"

if [[ "$GENERATE_PROJECT" == "true" ]]; then
    command -v xcodegen >/dev/null 2>&1 || {
        echo "xcodegen is required for $TARGET (brew install xcodegen)" >&2
        exit 1
    }
    echo "==> Generating $PROJECT from $PROJECT_DIR/project.yml"
    (cd "$PROJECT_DIR" && xcodegen generate)
fi

[[ -d "$PROJECT" ]] || { echo "Project not found: $PROJECT" >&2; exit 1; }

echo "==> Linting $PROJECT/project.pbxproj"
plutil -lint "$PROJECT/project.pbxproj"

verify_storefront_project_resources() {
    local resources_phase
    resources_phase="$(sed -n '/Begin PBXResourcesBuildPhase section/,/End PBXResourcesBuildPhase section/p' \
        "$PROJECT/project.pbxproj")"
    grep -qF 'Assets.xcassets in Resources' <<< "$resources_phase" || {
        echo "Generated Storefront project does not include Assets.xcassets in its resources phase." >&2
        return 1
    }
    grep -qF 'PrivacyInfo.xcprivacy in Resources' <<< "$resources_phase" || {
        echo "Generated Storefront project does not include PrivacyInfo.xcprivacy in its resources phase." >&2
        return 1
    }
    plutil -lint "$PROJECT_DIR/Resources/PrivacyInfo.xcprivacy"
}

verify_storefront_products() {
    local derived_data="$1"
    local app_bundle test_bundle
    app_bundle="$(find "$derived_data/Build/Products" -type d -name 'Ahnimal.app' -print -quit)"
    test_bundle="$(find "$derived_data/Build/Products" -type d -name 'StorefrontTests.xctest' -print -quit)"

    [[ -n "$app_bundle" ]] || {
        echo "Storefront build produced no Ahnimal.app bundle." >&2
        return 1
    }
    [[ -n "$test_bundle" ]] || {
        echo "Storefront build-for-testing did not compile StorefrontTests.xctest." >&2
        return 1
    }
    [[ -f "$app_bundle/Assets.car" ]] || {
        echo "Storefront app bundle is missing compiled Assets.car." >&2
        return 1
    }
    [[ -f "$app_bundle/PrivacyInfo.xcprivacy" ]] || {
        echo "Storefront app bundle is missing PrivacyInfo.xcprivacy." >&2
        return 1
    }
    echo "==> Verified Storefront app resources and compiled test bundle"
}

if [[ "$VERIFY_STOREFRONT" == "true" ]]; then
    verify_storefront_project_resources
fi

# GitHub-hosted macOS runners intentionally have no Matcha signing identity.
# Compile the desktop target unsigned in CI; local builds retain the project's
# normal development signing, while release scripts keep their explicit
# Developer ID / App Store signing paths.
# NB: expanded as ${ARR[@]+"${ARR[@]}"} below — macOS ships bash 3.2, where a
# plain "${ARR[@]}" on an EMPTY array trips `set -u` with "unbound variable".
XCODEBUILD_SETTINGS=()
if [[ "${CI:-}" == "true" && ( "$TARGET" == "espresso" || "$TARGET" == "storefront" || "$TARGET" == "matchaschedule" ) ]]; then
    XCODEBUILD_SETTINGS+=(CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO)
fi

case "$ACTION" in
    open)
        open "$PROJECT"
        ;;
    build)
        xcodebuild -project "$PROJECT" -scheme "$SCHEME" -destination "$DESTINATION" \
            ${XCODEBUILD_SETTINGS[@]+"${XCODEBUILD_SETTINGS[@]}"} build
        ;;
    build-for-testing)
        DERIVED_DATA_PATH="${XCODE_DERIVED_DATA_PATH:-$(mktemp -d "${TMPDIR:-/tmp}/matcha-xcode-$TARGET.XXXXXX")}"
        xcodebuild -project "$PROJECT" -scheme "$SCHEME" -destination "$DESTINATION" \
            -derivedDataPath "$DERIVED_DATA_PATH" \
            ${XCODEBUILD_SETTINGS[@]+"${XCODEBUILD_SETTINGS[@]}"} build-for-testing
        if [[ "$VERIFY_STOREFRONT" == "true" ]]; then
            verify_storefront_products "$DERIVED_DATA_PATH"
        fi
        ;;
    test)
        xcodebuild -project "$PROJECT" -scheme "$SCHEME" -destination "$DESTINATION" \
            ${XCODEBUILD_SETTINGS[@]+"${XCODEBUILD_SETTINGS[@]}"} test
        ;;
    *)
        echo "Unknown action: $ACTION (expected build, build-for-testing, test, or open)" >&2
        exit 1
        ;;
esac
