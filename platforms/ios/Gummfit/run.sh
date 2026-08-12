#!/usr/bin/env bash
# Build and launch Gummfit in the iOS simulator.
# Usage:
#   ./run.sh          build + install + launch (default)
#   ./run.sh build    build only
#   ./run.sh clean    clean then build + install + launch
#   SIM="iPhone 16" ./run.sh    override simulator (default: iPhone 17 Pro)
#   SIM_UDID="..." ./run.sh     target an exact simulator when names repeat
set -euo pipefail

CMD="${1:-run}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/Gummfit.xcodeproj"
SCHEME="Gummfit"
CONFIG="Debug"
SIM="${SIM:-iPhone 17 Pro}"
SIM_UDID="${SIM_UDID:-}"
BUNDLE_ID="com.gummcap.app"

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

cd "$PROJECT_DIR"

# A name can match more than one runtime/device. Resolve it once so xcodebuild
# and simctl cannot choose different simulators during the same run.
if [[ -z "$SIM_UDID" ]]; then
    SIM_UDID=$(xcrun simctl list devices available | awk -v name="$SIM" \
        'index($0, name " (") { match($0, /\([0-9A-F-]+\)/); print substr($0, RSTART + 1, RLENGTH - 2); exit }')
fi
if [[ -z "$SIM_UDID" ]]; then
    echo "${RED}simulator not found: $SIM${NC}"
    exit 1
fi

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
LOG="$(mktemp -t gummfit-build.XXXXXX)"
set +e
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" \
    -destination "platform=iOS Simulator,id=$SIM_UDID" build >"$LOG" 2>&1
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
    -destination "platform=iOS Simulator,id=$SIM_UDID" -showBuildSettings 2>/dev/null \
    | awk '/ CODESIGNING_FOLDER_PATH = /{print $3}' | head -1)

if [[ ! -d "$APP_PATH" ]]; then
    echo "${RED}app not found at $APP_PATH${NC}"
    exit 1
fi

echo "${DIM}booting $SIM...${NC}"
open -a Simulator
xcrun simctl boot "$SIM_UDID" 2>/dev/null || true

echo "${DIM}installing + launching $BUNDLE_ID...${NC}"
xcrun simctl install "$SIM_UDID" "$APP_PATH"
xcrun simctl terminate "$SIM_UDID" "$BUNDLE_ID" 2>/dev/null || true
xcrun simctl launch "$SIM_UDID" "$BUNDLE_ID"
