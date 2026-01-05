#!/bin/bash

# Development startup script for Matcha Recruit (Remote DB)
# Connects to EC2 Postgres via SSH Tunnel

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="matcha-dev-remote"
KEY_FILE="$PROJECT_ROOT/roonMT-arm.pem"
REMOTE_HOST="ec2-user@3.101.83.217"
REMOTE_PORT="5432"
LOCAL_PORT="5432"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

if [ ! -f "$KEY_FILE" ]; then
    echo -e "${RED}Error: SSH key not found at $KEY_FILE${NC}"
    exit 1
fi

# Handle stop command
if [ "$1" = "stop" ]; then
    echo "Stopping Matcha remote dev environment..."
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null && echo "Stopped!" || echo "Not running."
    exit 0
fi

echo -e "${GREEN}Starting Matcha Recruit Remote Dev environment...${NC}"

# Stop local postgres if running
if docker ps --format '{{.Names}}' | grep -q '^matcha-postgres$'; then
    echo -e "${YELLOW}Stopping local matcha-postgres container to free port $LOCAL_PORT...${NC}"
    docker stop matcha-postgres
fi

# Check/Start Redis (Local)
echo -e "${YELLOW}Checking Redis...${NC}"
if docker ps --format '{{.Names}}' | grep -q '^matcha-redis$'; then
    echo -e "${GREEN}Redis is already running${NC}"
else
    # Remove stopped container if exists
    docker rm matcha-redis 2>/dev/null || true
    echo -e "${YELLOW}Starting Redis...${NC}"
    docker run -d \
        --name matcha-redis \
        -p 6380:6379 \
        -v matcha_redis_data:/data \
        redis:7-alpine \
        redis-server --appendonly yes
fi

# Kill existing tmux session
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Create new tmux session
echo -e "${YELLOW}Creating tmux session...${NC}"

# Pane 0: SSH Tunnel
# We run it in a loop so it reconnects if it drops, and print status
tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_ROOT" \
    "while true; do echo 'Starting SSH Tunnel...'; ssh -i $KEY_FILE -N -L $LOCAL_PORT:localhost:$REMOTE_PORT $REMOTE_HOST -o ExitOnForwardFailure=yes; echo 'Tunnel dropped. Respawning in 2s...'; sleep 2; done"
tmux rename-window -t "$SESSION_NAME:0" "dev"

echo -e "${YELLOW}Waiting for tunnel...${NC}"
sleep 2 

# Pane 1: Backend (Split horizontally from tunnel)
tmux split-window -t "$SESSION_NAME:dev" -h -c "$PROJECT_ROOT/server" \
    "source venv/bin/activate && python run.py; echo -e '\n${RED}Backend exited.${NC}'; read"

# Pane 2: Worker (Split vertically from Backend)
tmux split-window -t "$SESSION_NAME:dev" -v -c "$PROJECT_ROOT/server" \
    "source venv/bin/activate && celery -A app.workers.celery_app worker --loglevel=info; echo -e '\n${RED}Worker exited.${NC}'; read"

# Pane 3: Frontend (Split vertically from Tunnel)
tmux select-pane -t "$SESSION_NAME:dev.0"
tmux split-window -t "$SESSION_NAME:dev" -v -c "$PROJECT_ROOT/client" \
    "npm run dev; echo -e '\n${RED}Frontend exited.${NC}'; read"

echo -e "${GREEN}Remote Dev environment started!${NC}"
echo -e "  - Database: Tunnel to $REMOTE_HOST:$REMOTE_PORT (mapped to localhost:$LOCAL_PORT)"
echo -e "  - Redis:    Local (6380)"
echo -e "  - Backend:  http://localhost:8001"
echo -e "  - Frontend: http://localhost:5174"

tmux attach-session -t "$SESSION_NAME"
