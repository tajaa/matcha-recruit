#!/usr/bin/env bash
# Build and launch Tell-Us in the iOS simulator.
# Usage:
#   ./run.sh          build + install + launch (default)
#   ./run.sh build    build only
#   ./run.sh clean    clean then build + install + launch
#   SIM="iPhone 16" ./run.sh    override simulator (default: iPhone 17 Pro)
set -euo pipefail

CMD="${1:-run}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/TellUs.xcodeproj"
SCHEME="TellUs"
CONFIG="Debug"
SIM="${SIM:-iPhone 17 Pro}"
BUNDLE_ID="com.beetlejuse.app"

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

cd "$PROJECT_DIR"
if ! which xcodegen >/dev/null 2>&1; then
    echo "${DIM}installing xcodegen...${NC}"
    brew install xcodegen
fi
xcodegen generate >/dev/null

if [[ "$CMD" == "clean" ]]; then
    echo "${DIM}cleaning...${NC}"
    xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" clean >/dev/null
fi

echo "${DIM}building $SCHEME ($CONFIG, sim: $SIM)...${NC}"
LOG="$(mktemp -t tellus-build.XXXXXX)"
set +e
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" \
    -destination "platform=iOS Simulator,name=$SIM" build >"$LOG" 2>&1
STATUS=$?
set -e

# Surface errors/warnings compactly.
ERRORS=$(grep -E ": (error|fatal error):" "$LOG" || true)
WARNINGS=$(grep -E ": warning:" "$LOG" || true)

if [[ -n "$WARNINGS" ]]; then
    echo "${YELLOW}warnings:${NC}"
    echo "$WARNINGS" | sed 's/^/  /'
fi

if [[ $STATUS -ne 0 || -n "$ERRORS" ]]; then
    echo "${RED}build failed:${NC}"
    if [[ -n "$ERRORS" ]]; then
        echo "$ERRORS" | sed 's/^/  /'
    else
        tail -30 "$LOG" | sed 's/^/  /'
    fi
    echo "${DIM}full log: $LOG${NC}"
    exit 1
fi

echo "${GREEN}build succeeded${NC}"
rm -f "$LOG"

if [[ "$CMD" == "build" ]]; then
    exit 0
fi

APP_PATH=$(xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" \
    -destination "platform=iOS Simulator,name=$SIM" -showBuildSettings 2>/dev/null \
    | awk '/ CODESIGNING_FOLDER_PATH = /{print $3}' | head -1)

if [[ ! -d "$APP_PATH" ]]; then
    echo "${RED}app not found at $APP_PATH${NC}"
    exit 1
fi

echo "${DIM}booting $SIM...${NC}"
open -a Simulator
xcrun simctl boot "$SIM" 2>/dev/null || true

echo "${DIM}installing + launching $BUNDLE_ID...${NC}"
xcrun simctl install "$SIM" "$APP_PATH"
xcrun simctl terminate "$SIM" "$BUNDLE_ID" 2>/dev/null || true
xcrun simctl launch "$SIM" "$BUNDLE_ID"
