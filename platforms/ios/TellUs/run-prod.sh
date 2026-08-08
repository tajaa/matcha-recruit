#!/usr/bin/env bash
# Build and launch Tell-Us in the iOS simulator, pointed at the production
# API (https://hey-matcha.com/api/tellus) instead of the local dev backend.
# Tell-Us's API is public — unlike Espresso's run-prod.sh, no SSH tunnel is
# needed here.
#
# Usage:
#   ./run-prod.sh                build + install + launch against prod
#   SIM="iPhone 16" ./run-prod.sh    override simulator
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$PROJECT_DIR/TellUs.xcodeproj"
SCHEME="TellUs"
CONFIG="Debug"
SIM="${SIM:-iPhone 17 Pro}"
BUNDLE_ID="com.beetlejuse.app"
PROD_API_URL="https://hey-matcha.com/api/tellus"

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

echo "${YELLOW}==> POINTED AT PROD: $PROD_API_URL${NC}"

cd "$PROJECT_DIR"
if ! which xcodegen >/dev/null 2>&1; then
    echo "${DIM}installing xcodegen...${NC}"
    brew install xcodegen
fi
xcodegen generate >/dev/null

echo "${DIM}building $SCHEME ($CONFIG, sim: $SIM)...${NC}"
LOG="$(mktemp -t tellus-build.XXXXXX)"
set +e
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" \
    -destination "platform=iOS Simulator,name=$SIM" build >"$LOG" 2>&1
STATUS=$?
set -e

ERRORS=$(grep -E ": (error|fatal error):" "$LOG" || true)
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

echo "${DIM}installing + launching $BUNDLE_ID (prod API)...${NC}"
xcrun simctl install "$SIM" "$APP_PATH"
xcrun simctl terminate "$SIM" "$BUNDLE_ID" 2>/dev/null || true
# SIMCTL_CHILD_<NAME> is how simctl forwards env vars into the launched
# process — the app reads it as plain TELLUS_API_URL via
# ProcessInfo.processInfo.environment (Services/APIClient.swift).
SIMCTL_CHILD_TELLUS_API_URL="$PROD_API_URL" xcrun simctl launch "$SIM" "$BUNDLE_ID"

echo "${YELLOW}==> running against prod: $PROD_API_URL${NC}"
