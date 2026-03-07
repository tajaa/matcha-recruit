#!/bin/bash

# Start the agent API + Preact UI for local development
#   API: http://localhost:9100
#   UI:  http://localhost:5176 (proxies API calls to :9100)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Start API server in background
cd "$PROJECT_ROOT/server"
source venv/bin/activate
echo -e "${GREEN}Starting agent API on http://localhost:9100${NC}"
python -m uvicorn agent.api:app --host 127.0.0.1 --port 9100 --reload &
API_PID=$!

# Start Vite dev server
cd "$PROJECT_ROOT/agent-ui"
echo -e "${GREEN}Starting agent UI on http://localhost:5176${NC}"
npx vite &
UI_PID=$!

echo ""
echo -e "${YELLOW}Agent dev environment running:${NC}"
echo -e "  API: http://localhost:9100"
echo -e "  UI:  http://localhost:5176"
echo ""

cleanup() {
    kill $API_PID $UI_PID 2>/dev/null
    wait $API_PID $UI_PID 2>/dev/null
}

trap cleanup EXIT INT TERM
wait
