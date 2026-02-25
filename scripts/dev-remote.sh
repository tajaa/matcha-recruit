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
DEFAULT_BACKEND_PORT="8001"
DEFAULT_FRONTEND_PORT="5174"
DEFAULT_CHAT_PORT="8080"
CHAT_MODEL_DIR="$HOME/Documents/github/models"
CHAT_MODEL_PATH="$CHAT_MODEL_DIR/Qwen3VL-8B-Instruct-Q8_0.gguf"
CHAT_MMPROJ_PATH="$CHAT_MODEL_DIR/mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf"
#
# Optional overrides: LOCAL_PORT/LOCAL_DB_PORT, REDIS_PORT, FRONTEND_PORT,
# DATABASE_URL, REDIS_URL, CHAT_PORT

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

# Parse arguments
ENABLE_CHAT=false
for arg in "$@"; do
    case "$arg" in
        stop)
            echo "Stopping Matcha remote dev environment..."
            tmux kill-session -t "$SESSION_NAME" 2>/dev/null && echo "Stopped!" || echo "Not running."
            exit 0
            ;;
        --chat)
            ENABLE_CHAT=true
            ;;
    esac
done

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

if [ -n "${BACKEND_PORT:-}" ]; then
    BACKEND_PORT_SOURCE="env"
else
    BACKEND_PORT_SOURCE="default"
    BACKEND_PORT="$DEFAULT_BACKEND_PORT"
fi

CHAT_PORT_SOURCE="default"
if [ -n "${CHAT_PORT:-}" ]; then
    CHAT_PORT_SOURCE="env"
else
    CHAT_PORT="$DEFAULT_CHAT_PORT"
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

CHAT_REUSE_EXISTING=false
if [ "$ENABLE_CHAT" = true ]; then
    if is_port_in_use "$CHAT_PORT"; then
        # Check if an existing llama-server is already on this port — reuse it
        if lsof -n -P -iTCP:"$CHAT_PORT" -sTCP:LISTEN 2>/dev/null | grep -q llama; then
            echo -e "${GREEN}Reusing existing llama-server on port $CHAT_PORT (avoids GPU memory conflict)${NC}"
            CHAT_REUSE_EXISTING=true
        elif [ "$CHAT_PORT_SOURCE" = "env" ]; then
            echo -e "${RED}Error: CHAT_PORT $CHAT_PORT is already in use by a non-llama process. Set CHAT_PORT to a free port.${NC}"
            exit 1
        else
            echo -e "${RED}Error: Port $CHAT_PORT is in use by a non-llama process. Free it or set CHAT_PORT.${NC}"
            exit 1
        fi
    fi
fi

export DATABASE_URL
export REDIS_URL

# Kill existing tmux session
tmux kill-session -t "$SESSION_NAME" 2>/dev/null || true

# Create new tmux session
echo -e "${YELLOW}Creating tmux session...${NC}"

CHAT_ENV=""
if [ "$ENABLE_CHAT" = true ]; then
    CHAT_ENV="export AI_CHAT_BASE_URL='http://localhost:${CHAT_PORT}' && "
fi

# Pane 0: Backend (Server) - Main large pane on the left
tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_ROOT/server" \
    "export DATABASE_URL='$DATABASE_URL' && export REDIS_URL='$REDIS_URL' && export PORT='$BACKEND_PORT' && ${CHAT_ENV}source venv/bin/activate && echo 'Waiting for DB tunnel on localhost:$LOCAL_PORT...' && WAITED=0 && MAX_WAIT=60 && until lsof -n -P -iTCP:$LOCAL_PORT -sTCP:LISTEN >/dev/null 2>&1; do sleep 1; WAITED=\$((WAITED+1)); if [ \"\$WAITED\" -ge \"\$MAX_WAIT\" ]; then echo 'DB tunnel did not become ready within 60s.'; exit 1; fi; done && python run.py; echo -e '\n${RED}Backend exited.${NC}'; read"
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
    "export DATABASE_URL='$DATABASE_URL' && export REDIS_URL='$REDIS_URL' && source venv/bin/activate && echo 'Waiting for DB tunnel on localhost:$LOCAL_PORT...' && WAITED=0 && MAX_WAIT=60 && until lsof -n -P -iTCP:$LOCAL_PORT -sTCP:LISTEN >/dev/null 2>&1; do sleep 1; WAITED=\$((WAITED+1)); if [ \"\$WAITED\" -ge \"\$MAX_WAIT\" ]; then echo 'DB tunnel did not become ready within 60s.'; exit 1; fi; done && celery -A app.workers.celery_app worker --loglevel=info; echo -e '\n${RED}Worker exited.${NC}'; read"

# Pane 3: Frontend - Split below worker
tmux split-window -t "$SESSION_NAME:dev.2" -v -c "$PROJECT_ROOT/client" \
    "echo 'Waiting for backend health at http://127.0.0.1:$BACKEND_PORT/health...' && WAITED=0 && MAX_WAIT=120 && until curl -fsS http://127.0.0.1:$BACKEND_PORT/health >/dev/null 2>&1; do sleep 1; WAITED=\$((WAITED+1)); if [ \"\$WAITED\" -ge \"\$MAX_WAIT\" ]; then echo 'Backend healthcheck did not become ready within 120s. Check backend/tunnel panes.'; exit 1; fi; done && VITE_PROXY_TARGET='http://127.0.0.1:$BACKEND_PORT' npm run dev -- --port $FRONTEND_PORT; echo -e '\n${RED}Frontend exited.${NC}'; read"

# Pane 4 (optional): AI Chat Model Server
if [ "$ENABLE_CHAT" = true ] && [ "$CHAT_REUSE_EXISTING" = false ]; then
    tmux split-window -t "$SESSION_NAME:dev.3" -v -c "$PROJECT_ROOT" \
        "echo 'Starting Qwen chat model on port $CHAT_PORT...'; llama-server -m $CHAT_MODEL_PATH --mmproj $CHAT_MMPROJ_PATH -ngl 99 --ctx-size 4096 --port $CHAT_PORT; echo -e '\n${RED}Chat model exited.${NC}'; read"
fi

# Select the server pane as active
tmux select-pane -t "$SESSION_NAME:dev.0"

echo -e "${GREEN}Remote Dev environment started!${NC}"
echo -e "  - Database: Tunnel to $REMOTE_HOST:$REMOTE_PORT (mapped to localhost:$LOCAL_PORT)"
echo -e "  - Redis:    Local ($REDIS_PORT)"
echo -e "  - Backend:  http://localhost:$BACKEND_PORT"
echo -e "  - Frontend: http://localhost:$FRONTEND_PORT"
if [ "$ENABLE_CHAT" = true ]; then
    echo -e "  - AI Chat:  http://localhost:$CHAT_PORT (Qwen2-VL-2B)"
fi

tmux attach-session -t "$SESSION_NAME"
