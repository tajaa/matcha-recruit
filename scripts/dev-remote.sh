#!/bin/bash

# Development startup script for Matcha Recruit (Remote DB)
# Connects to EC2 Postgres via SSH Tunnel

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="matcha-dev-remote"
KEY_FILE="$PROJECT_ROOT/roonMT-arm.pem"
REMOTE_HOST="ec2-user@3.101.83.217"
REMOTE_PORT="5432"
DEFAULT_LOCAL_PORT="5432"
DEFAULT_REDIS_PORT="6380"
DEFAULT_FRONTEND_PORT="5174"
#
# Optional overrides: LOCAL_PORT/LOCAL_DB_PORT, REDIS_PORT, FRONTEND_PORT,
# DATABASE_URL, REDIS_URL

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

is_port_in_use() {
    local port=$1

    if command_exists lsof; then
        lsof -n -P -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
        return $?
    fi

    if command_exists ss; then
        ss -ltn "( sport = :$port )" | awk 'NR>1 {exit 0} END {exit 1}'
        return $?
    fi

    if command_exists netstat; then
        netstat -an 2>/dev/null | grep -E "[\\.:]${port} " | grep -i LISTEN >/dev/null 2>&1
        return $?
    fi

    return 1
}

pick_available_port() {
    local start=$1
    local end=$2
    local port

    for port in $(seq "$start" "$end"); do
        if ! is_port_in_use "$port"; then
            echo "$port"
            return 0
        fi
    done

    return 1
}

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

LOCAL_PORT_SOURCE="default"
if [ -n "${LOCAL_PORT:-}" ]; then
    LOCAL_PORT_SOURCE="env"
elif [ -n "${LOCAL_DB_PORT:-}" ]; then
    LOCAL_PORT="$LOCAL_DB_PORT"
    LOCAL_PORT_SOURCE="env"
else
    LOCAL_PORT="$DEFAULT_LOCAL_PORT"
fi

REDIS_PORT_SOURCE="default"
if [ -n "${REDIS_PORT:-}" ]; then
    REDIS_PORT_SOURCE="env"
else
    REDIS_PORT="$DEFAULT_REDIS_PORT"
fi

FRONTEND_PORT_SOURCE="default"
if [ -n "${FRONTEND_PORT:-}" ]; then
    FRONTEND_PORT_SOURCE="env"
else
    FRONTEND_PORT="$DEFAULT_FRONTEND_PORT"
fi

DATABASE_URL_SOURCE="default"
if [ -n "${DATABASE_URL:-}" ]; then
    DATABASE_URL_SOURCE="env"
fi

REDIS_URL_SOURCE="default"
if [ -n "${REDIS_URL:-}" ]; then
    REDIS_URL_SOURCE="env"
fi

# Stop local postgres if running
if docker ps --format '{{.Names}}' | grep -q '^matcha-postgres$'; then
    echo -e "${YELLOW}Stopping local matcha-postgres container to free port $LOCAL_PORT...${NC}"
    docker stop matcha-postgres
fi

if is_port_in_use "$LOCAL_PORT"; then
    if [ "$LOCAL_PORT_SOURCE" = "env" ]; then
        echo -e "${RED}Error: LOCAL_PORT $LOCAL_PORT is already in use. Set LOCAL_PORT or LOCAL_DB_PORT to a free port.${NC}"
        exit 1
    fi

    ALT_LOCAL_PORT="$(pick_available_port 5433 5440)"
    if [ -z "$ALT_LOCAL_PORT" ]; then
        echo -e "${RED}Error: No free local DB ports found in 5433-5440.${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Port $LOCAL_PORT is in use; using $ALT_LOCAL_PORT for the DB tunnel instead.${NC}"
    LOCAL_PORT="$ALT_LOCAL_PORT"
fi

if is_port_in_use "$FRONTEND_PORT"; then
    if [ "$FRONTEND_PORT_SOURCE" = "env" ]; then
        echo -e "${RED}Error: FRONTEND_PORT $FRONTEND_PORT is already in use. Set FRONTEND_PORT to a free port.${NC}"
        exit 1
    fi

    ALT_FRONTEND_PORT="$(pick_available_port 5175 5190)"
    if [ -z "$ALT_FRONTEND_PORT" ]; then
        echo -e "${RED}Error: No free frontend ports found in 5175-5190.${NC}"
        exit 1
    fi

    echo -e "${YELLOW}Port $FRONTEND_PORT is in use; using $ALT_FRONTEND_PORT for the frontend instead.${NC}"
    FRONTEND_PORT="$ALT_FRONTEND_PORT"
fi


# Check/Start Redis (Local)
echo -e "${YELLOW}Checking Redis...${NC}"
if docker ps --format '{{.Names}}' | grep -q '^matcha-redis$'; then
    echo -e "${GREEN}Redis is already running${NC}"
    EXISTING_REDIS_PORT="$(docker port matcha-redis 6379/tcp 2>/dev/null | head -n 1 | awk -F: '{print $NF}')"
    if [ -n "$EXISTING_REDIS_PORT" ]; then
        if [ "$REDIS_PORT_SOURCE" = "env" ] && [ "$REDIS_PORT" != "$EXISTING_REDIS_PORT" ]; then
            echo -e "${YELLOW}REDIS_PORT is set to $REDIS_PORT but matcha-redis is bound to $EXISTING_REDIS_PORT; update REDIS_PORT/REDIS_URL if you want to match.${NC}"
        fi
        REDIS_PORT="$EXISTING_REDIS_PORT"
    fi
else
    # Remove stopped container if exists
    docker rm matcha-redis 2>/dev/null || true
    if is_port_in_use "$REDIS_PORT"; then
        if [ "$REDIS_PORT_SOURCE" = "env" ]; then
            echo -e "${RED}Error: REDIS_PORT $REDIS_PORT is already in use. Set REDIS_PORT to a free port.${NC}"
            exit 1
        fi

        ALT_REDIS_PORT="$(pick_available_port 6381 6390)"
        if [ -z "$ALT_REDIS_PORT" ]; then
            echo -e "${RED}Error: No free Redis ports found in 6381-6390.${NC}"
            exit 1
        fi

        echo -e "${YELLOW}Port $REDIS_PORT is in use; using $ALT_REDIS_PORT for Redis instead.${NC}"
        REDIS_PORT="$ALT_REDIS_PORT"
    fi
    echo -e "${YELLOW}Starting Redis...${NC}"
    docker run -d \
        --name matcha-redis \
        -p "${REDIS_PORT}:6379" \
        -v matcha_redis_data:/data \
        redis:7-alpine \
        redis-server --appendonly yes
fi

if [ "$DATABASE_URL_SOURCE" = "default" ]; then
    DATABASE_URL="postgresql://matcha:matcha_dev@localhost:${LOCAL_PORT}/matcha"
fi
if [ "$REDIS_URL_SOURCE" = "default" ]; then
    REDIS_URL="redis://localhost:${REDIS_PORT}/0"
fi

export DATABASE_URL
export REDIS_URL

# Kill existing tmux session
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Create new tmux session
echo -e "${YELLOW}Creating tmux session...${NC}"

# Pane 0: Backend (Server) - Main large pane on the left
tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_ROOT/server" \
    "export DATABASE_URL='$DATABASE_URL' && export REDIS_URL='$REDIS_URL' && source venv/bin/activate && python run.py; echo -e '\n${RED}Backend exited.${NC}'; read"
tmux rename-window -t "$SESSION_NAME:0" "dev"

# Enable mouse mode for clicking panes and scrolling
tmux set-option -t "$SESSION_NAME" mouse on

# Pane 1: SSH Tunnel - Split right side (30% width)
tmux split-window -t "$SESSION_NAME:dev" -h -p 30 -c "$PROJECT_ROOT" \
    "while true; do echo 'Starting SSH Tunnel...'; ssh -i $KEY_FILE -N -L $LOCAL_PORT:localhost:$REMOTE_PORT $REMOTE_HOST -o ExitOnForwardFailure=yes; echo 'Tunnel dropped. Respawning in 2s...'; sleep 2; done"

echo -e "${YELLOW}Waiting for tunnel...${NC}"
sleep 2

# Pane 2: Worker - Split below tunnel
tmux split-window -t "$SESSION_NAME:dev.1" -v -c "$PROJECT_ROOT/server" \
    "export DATABASE_URL='$DATABASE_URL' && export REDIS_URL='$REDIS_URL' && source venv/bin/activate && celery -A app.workers.celery_app worker --loglevel=info; echo -e '\n${RED}Worker exited.${NC}'; read"

# Pane 3: Frontend - Split below worker
tmux split-window -t "$SESSION_NAME:dev.2" -v -c "$PROJECT_ROOT/client" \
    "npm run dev -- --port $FRONTEND_PORT; echo -e '\n${RED}Frontend exited.${NC}'; read"

# Select the server pane as active
tmux select-pane -t "$SESSION_NAME:dev.0"

echo -e "${GREEN}Remote Dev environment started!${NC}"
echo -e "  - Database: Tunnel to $REMOTE_HOST:$REMOTE_PORT (mapped to localhost:$LOCAL_PORT)"
echo -e "  - Redis:    Local ($REDIS_PORT)"
echo -e "  - Backend:  http://localhost:8001"
echo -e "  - Frontend: http://localhost:$FRONTEND_PORT"

tmux attach-session -t "$SESSION_NAME"
