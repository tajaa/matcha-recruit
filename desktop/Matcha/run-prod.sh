#!/usr/bin/env bash
# Build and launch the Matcha macOS app against the production EC2 backend.
#
# Sets up SSH tunnels to EC2, then builds and launches the app with
# MATCHA_API_URL pointing at the tunneled backend.
#
# Usage:
#   ./run-prod.sh              build + launch against prod
#   ./run-prod.sh build        build only (tunnels stay up)
#   ./run-prod.sh tunnels      tunnels only, no build
#   ./run-prod.sh stop         tear down tunnels
#
# Requirements:
#   - SSH key: roonMT-arm.pem in the repo root
#   - EC2 hosts reachable

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$PROJECT_DIR/../.." && pwd)"
PROJECT="$PROJECT_DIR/Matcha.xcodeproj"
SCHEME="Matcha"
CONFIG="Debug"
DEST="platform=macOS"
KEY_FILE="$REPO_ROOT/roonMT-arm.pem"

# EC2 hosts
DB_HOST="ec2-user@3.101.83.217"       # PostgreSQL
APP_HOST="ec2-user@54.177.107.107"     # Backend containers

# Local tunnel ports
LOCAL_API_PORT=8002   # avoid clash with local dev on 8001
LOCAL_DB_PORT=5433    # avoid clash with local postgres on 5432

# PID file for tunnel cleanup
PID_FILE="/tmp/matcha-prod-tunnels.pids"

RED=$'\033[0;31m'; YELLOW=$'\033[0;33m'; GREEN=$'\033[0;32m'; DIM=$'\033[2m'; NC=$'\033[0m'

CMD="${1:-run}"

stop_tunnels() {
    if [[ -f "$PID_FILE" ]]; then
        while IFS= read -r pid; do
            kill "$pid" 2>/dev/null || true
        done < "$PID_FILE"
        rm -f "$PID_FILE"
        echo "${GREEN}tunnels stopped${NC}"
    else
        echo "${DIM}no tunnels running${NC}"
    fi
}

if [[ "$CMD" == "stop" ]]; then
    stop_tunnels
    exit 0
fi

# Validate SSH key
if [[ ! -f "$KEY_FILE" ]]; then
    echo "${RED}error:${NC} SSH key not found at $KEY_FILE"
    exit 1
fi

# Kill stale tunnels before starting fresh
stop_tunnels 2>/dev/null || true

SSH_OPTS=(-o ExitOnForwardFailure=yes -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o ConnectTimeout=15 -o StrictHostKeyChecking=no)

# Start DB tunnel (local 5433 → EC2 DB 5432)
echo "${DIM}tunneling DB: localhost:$LOCAL_DB_PORT → $DB_HOST:5432${NC}"
ssh -i "$KEY_FILE" -N -f -L "$LOCAL_DB_PORT:localhost:5432" "$DB_HOST" "${SSH_OPTS[@]}"
DB_PID=$(lsof -ti "TCP:$LOCAL_DB_PORT" -sTCP:LISTEN 2>/dev/null | head -1)

# Start API tunnel (local 8002 → EC2 app 8001)
echo "${DIM}tunneling API: localhost:$LOCAL_API_PORT → $APP_HOST:8001${NC}"
ssh -i "$KEY_FILE" -N -f -L "$LOCAL_API_PORT:localhost:8001" "$APP_HOST" "${SSH_OPTS[@]}"
API_PID=$(lsof -ti "TCP:$LOCAL_API_PORT" -sTCP:LISTEN 2>/dev/null | head -1)

# Save PIDs for cleanup
echo "$DB_PID" > "$PID_FILE"
echo "$API_PID" >> "$PID_FILE"

# Verify tunnels
sleep 1
if ! lsof -n -P -iTCP:"$LOCAL_API_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "${RED}error:${NC} API tunnel failed to start on port $LOCAL_API_PORT"
    stop_tunnels
    exit 1
fi
if ! lsof -n -P -iTCP:"$LOCAL_DB_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "${RED}error:${NC} DB tunnel failed to start on port $LOCAL_DB_PORT"
    stop_tunnels
    exit 1
fi

echo "${GREEN}tunnels up${NC}"
echo "  API: http://localhost:$LOCAL_API_PORT/api"
echo "  DB:  postgresql://matcha:...@localhost:$LOCAL_DB_PORT/matcha"

if [[ "$CMD" == "tunnels" ]]; then
    echo "${DIM}tunnels running in background — run '$0 stop' to tear down${NC}"
    exit 0
fi

# Build
echo "${DIM}building $SCHEME ($CONFIG)...${NC}"
LOG="$(mktemp -t matcha-build.XXXXXX)"
set +e
xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" -destination "$DEST" build >"$LOG" 2>&1
STATUS=$?
set -e

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
    stop_tunnels
    exit 1
fi

echo "${GREEN}build succeeded${NC}"
rm -f "$LOG"

if [[ "$CMD" == "build" ]]; then
    echo "${DIM}tunnels still running — run '$0 stop' to tear down${NC}"
    exit 0
fi

APP_PATH=$(xcodebuild -project "$PROJECT" -scheme "$SCHEME" -configuration "$CONFIG" -showBuildSettings 2>/dev/null \
    | awk '/ BUILT_PRODUCTS_DIR = /{print $3}' | head -1)/Matcha.app

if [[ ! -d "$APP_PATH" ]]; then
    echo "${RED}app not found at $APP_PATH${NC}"
    stop_tunnels
    exit 1
fi

# Kill any prior instance
pkill -x Matcha 2>/dev/null || true
sleep 0.2

# Launch with MATCHA_API_URL pointing at the tunneled EC2 backend.
# Must launch the binary directly — `open` doesn't pass env vars to the app.
echo "${DIM}launching against prod backend (localhost:$LOCAL_API_PORT)${NC}"
export MATCHA_API_URL="http://localhost:$LOCAL_API_PORT/api"
"$APP_PATH/Contents/MacOS/Matcha" &
APP_PID=$!

echo "${GREEN}running (pid $APP_PID)${NC} — tunnels stay up until you run: $0 stop"
