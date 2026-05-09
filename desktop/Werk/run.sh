#!/usr/bin/env bash
# Build and launch the Matcha macOS Swift app.
# Usage:
#   ./run.sh          build + launch (default)
#   ./run.sh build    build only
#   ./run.sh clean    clean then build + launch
set -euo pipefail

CMD="${1:-run}"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/Matcha.xcodeproj"
SCHEME="Matcha"
CONFIG="Debug"
DEST="platform=macOS"

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

if [[ "$CMD" == "clean" ]]; then
    echo "${DIM}cleaning...${NC}"
    xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" clean >/dev/null
fi

echo "${DIM}building $SCHEME ($CONFIG)...${NC}"
LOG="$(mktemp -t matcha-build.XXXXXX)"
set +e
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" -destination "$DEST" build >"$LOG" 2>&1
STATUS=$?
set -e

# Surface errors/warnings compactly.
ERRORS=$(grep -E ": (error|fatal error):" "$LOG" || true)
WARNINGS=$(grep -E ": warning:" "$LOG" | grep -v "appintentsmetadataprocessor" || true)

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

APP_PATH=$(xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" -showBuildSettings 2>/dev/null \
    | awk '/ BUILT_PRODUCTS_DIR = /{print $3}' | head -1)/Matcha.app

if [[ ! -d "$APP_PATH" ]]; then
    echo "${RED}app not found at $APP_PATH${NC}"
    exit 1
fi

# Kill any prior instance so launch is clean.
pkill -x Matcha 2>/dev/null || true
sleep 0.2
echo "${DIM}launching $APP_PATH${NC}"
open "$APP_PATH"
