#!/usr/bin/env bash
# Build/test/open one of the repo's Xcode projects. HOST ONLY — Xcode,
# xcodebuild, codesigning, and the login Keychain cannot run in the Linux
# agent sandbox (docs/ops/AGENT_SANDBOX.md). An agent inside the sandbox can
# still edit Swift/project.pbxproj through the bind mount; run this script on
# the Mac to actually build.
#
# Usage: ./scripts/xcode-build.sh <target> [build|test|open]
#
# Targets:
#   espresso     platforms/desktop/Espresso/Matcha.xcodeproj  (scheme Matcha, macOS)
#   matchatutor  platforms/ios/MatchaTutor/MatchaTutor.xcodeproj
#   tellus       platforms/ios/TellUs/TellUs.xcodeproj
#   gummfit      platforms/ios/Gummfit/Gummfit.xcodeproj
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

[[ -d "$PROJECT" ]] || { echo "Project not found: $PROJECT" >&2; exit 1; }

echo "==> Linting $PROJECT/project.pbxproj"
plutil -lint "$PROJECT/project.pbxproj"

# GitHub-hosted macOS runners intentionally have no Matcha signing identity.
# Compile the desktop target unsigned in CI; local builds retain the project's
# normal development signing, while release scripts keep their explicit
# Developer ID / App Store signing paths.
# NB: expanded as ${ARR[@]+"${ARR[@]}"} below — macOS ships bash 3.2, where a
# plain "${ARR[@]}" on an EMPTY array trips `set -u` with "unbound variable".
XCODEBUILD_SETTINGS=()
if [[ "${CI:-}" == "true" && "$TARGET" == "espresso" ]]; then
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
    test)
        xcodebuild -project "$PROJECT" -scheme "$SCHEME" -destination "$DESTINATION" \
            ${XCODEBUILD_SETTINGS[@]+"${XCODEBUILD_SETTINGS[@]}"} test
        ;;
    *)
        echo "Unknown action: $ACTION (expected build, test, or open)" >&2
        exit 1
        ;;
esac
