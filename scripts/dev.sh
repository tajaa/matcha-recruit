#!/bin/bash

# Development startup script for Matcha Recruit
# Uses tmux to manage all services in split panes
#
# Usage:
#   ./scripts/dev.sh        - Start all services
#   ./scripts/dev.sh stop   - Stop all services

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="matcha-dev"

# Handle stop command
if [ "$1" = "stop" ]; then
    echo "Stopping Matcha development environment..."
    tmux kill-session -t "$SESSION_NAME" 2>/dev/null && echo "Stopped!" || echo "Not running."
    exit 0
fi

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Matcha Recruit development environment...${NC}"

# Check if Docker is running, start if not
if ! docker info > /dev/null 2>&1; then
    echo -e "${YELLOW}Docker is not running. Starting Docker Desktop...${NC}"
    open -a Docker

    # Wait for Docker to be ready
    echo -e "${YELLOW}Waiting for Docker to start...${NC}"
    while ! docker info > /dev/null 2>&1; do
        sleep 1
    done
    echo -e "${GREEN}Docker is ready${NC}"
fi

# Check/Start PostgreSQL
echo -e "${YELLOW}Checking PostgreSQL...${NC}"
if docker ps --format '{{.Names}}' | grep -q '^matcha-postgres$'; then
    echo -e "${GREEN}PostgreSQL is already running${NC}"
else
    # Check if container exists but is stopped
    if docker ps -a --format '{{.Names}}' | grep -q '^matcha-postgres$'; then
        echo -e "${YELLOW}Starting PostgreSQL...${NC}"
        docker start matcha-postgres
    else
        echo -e "${RED}matcha-postgres container does not exist!${NC}"
        echo -e "${RED}Please create it first with the shared postgres setup.${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Waiting for PostgreSQL to be ready...${NC}"
    until docker exec matcha-postgres pg_isready -U matcha 2>/dev/null; do
        sleep 1
    done
    echo -e "${GREEN}PostgreSQL started${NC}"
fi

# Check/Start Redis
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

    echo -e "${YELLOW}Waiting for Redis to be ready...${NC}"
    until docker exec matcha-redis redis-cli ping 2>/dev/null | grep -q PONG; do
        sleep 1
    done
    echo -e "${GREEN}Redis started${NC}"
fi

# Kill existing tmux session if it exists
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Create new tmux session with backend pane
echo -e "${YELLOW}Creating tmux session...${NC}"
tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_ROOT/server" \
    "source venv/bin/activate && python run.py; echo -e '\n${RED}Backend exited. Press Enter to close.${NC}'; read"

# Rename the first window
tmux rename-window -t "$SESSION_NAME:0" "dev"

# Small delay to let first pane initialize
sleep 0.5

# Split for Celery worker
tmux split-window -t "$SESSION_NAME:dev" -v -c "$PROJECT_ROOT/server" \
    "source venv/bin/activate && celery -A app.workers.celery_app worker --loglevel=info; echo -e '\n${RED}Worker exited. Press Enter to close.${NC}'; read"

# Small delay
sleep 0.5

# Split for frontend
tmux split-window -t "$SESSION_NAME:dev" -v -c "$PROJECT_ROOT/client" \
    "npm run dev; echo -e '\n${RED}Frontend exited. Press Enter to close.${NC}'; read"

# Even out the panes
tmux select-layout -t "$SESSION_NAME:dev" even-vertical

# Select the first pane (backend)
tmux select-pane -t "$SESSION_NAME:dev.0"

echo -e "${GREEN}Development environment started!${NC}"
echo ""
echo -e "${YELLOW}Services:${NC}"
echo -e "  - Backend:  http://localhost:8001"
echo -e "  - Frontend: http://localhost:5174"
echo -e "  - Postgres: localhost:5432"
echo -e "  - Redis:    localhost:6380"
echo ""
echo -e "${YELLOW}Tmux Controls:${NC}"
echo -e "  ${GREEN}Navigation:${NC}"
echo -e "    Ctrl-b + ↑/↓       : Move between panes"
echo -e "    Ctrl-b + q         : Show pane numbers (then press number to jump)"
echo ""
echo -e "  ${GREEN}Session:${NC}"
echo -e "    Ctrl-b + d         : Detach (services keep running in background)"
echo -e "    tmux attach -t $SESSION_NAME  : Re-attach to session"
echo -e "    tmux kill-session -t $SESSION_NAME : Stop all services"
echo ""
echo -e "  ${GREEN}Scrolling:${NC}"
echo -e "    Ctrl-b + [         : Enter scroll mode (use arrow keys/PgUp/PgDn)"
echo -e "    q                  : Exit scroll mode"
echo ""
echo -e "  ${GREEN}Pane Management:${NC}"
echo -e "    Ctrl-b + z         : Toggle zoom (fullscreen current pane)"
echo -e "    Ctrl-b + x         : Kill current pane"
echo ""

# Attach to the session
tmux attach-session -t "$SESSION_NAME"
