#!/bin/bash

# Development startup script for Matcha Recruit (LOCAL DB)
# Uses a local pgvector/pg15 container (matcha-postgres) — the old EC2 dev
# Postgres was retired; this DB was cloned from it. RDS/prod untouched.

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
    echo -e "${YELLOW}Note: SSH key not found at $KEY_FILE (only needed for remote ops; local dev DB doesn't need it).${NC}"
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

# Ensure the LOCAL Postgres dev DB is running (no more SSH tunnel to EC2).
# The dev data was cloned from the retired EC2 container into a local
# pgvector/pg15 container. If it's missing, create it empty (restore a dump
# into it separately); if stopped, start it.
ensure_local_postgres() {
    if docker ps --format '{{.Names}}' | grep -q '^matcha-postgres$'; then
        echo -e "${GREEN}Local matcha-postgres already running${NC}"
        return
    fi
    if docker ps -a --format '{{.Names}}' | grep -q '^matcha-postgres$'; then
        echo -e "${YELLOW}Starting local matcha-postgres...${NC}"
        docker start matcha-postgres
    else
        echo -e "${YELLOW}Creating local matcha-postgres (pgvector/pg15) on port $LOCAL_PORT...${NC}"
        docker run -d --name matcha-postgres \
            -e POSTGRES_USER=matcha -e POSTGRES_PASSWORD=matcha_dev -e POSTGRES_DB=matcha \
            -p "${LOCAL_PORT}:5432" -v matcha_pg_data:/var/lib/postgresql/data \
            pgvector/pgvector:pg15
    fi
    echo -e "${YELLOW}Waiting for Postgres to accept connections...${NC}"
    for _ in $(seq 1 30); do
        docker exec matcha-postgres pg_isready -U matcha -d matcha >/dev/null 2>&1 && break
        sleep 1
    done
}
ensure_local_postgres

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

# Disable gitstatus in dev panes to avoid index.lock conflicts
GS_OFF="export POWERLEVEL9K_DISABLE_GITSTATUS=true &&"

# Tell-Us frontend port — picked BEFORE the panes so the main frontend can
# receive VITE_TELLUS_TARGET (its '/tellus' proxy → this server, making
# http://localhost:5174/tellus/ work in dev like prod). Range starts at the
# tellus default (5191), clear of the main frontend's 5175-5190 fallback.
TELLUS_PORT=""
if [ -d "$PROJECT_ROOT/client/tellus/node_modules" ]; then
    TELLUS_PORT="$(pick_available_port 5191 5199)"
fi
TELLUS_ENV=""
if [ -n "$TELLUS_PORT" ]; then
    TELLUS_ENV="VITE_TELLUS_TARGET='http://127.0.0.1:$TELLUS_PORT' "
fi

# Create new tmux session
echo -e "${YELLOW}Creating tmux session...${NC}"

CHAT_ENV=""
if [ "$ENABLE_CHAT" = true ]; then
    CHAT_ENV="export AI_CHAT_BASE_URL='http://localhost:${CHAT_PORT}' && "
fi

# Pane 0: Backend (Server) - Main large pane on the left
tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_ROOT/server" \
    "$GS_OFF export DATABASE_URL='$DATABASE_URL' && export REDIS_URL='$REDIS_URL' && export PORT='$BACKEND_PORT' && export UVICORN_RELOAD=true && ${CHAT_ENV}source venv/bin/activate && echo 'Waiting for DB tunnel on localhost:$LOCAL_PORT...' && WAITED=0 && MAX_WAIT=60 && until lsof -n -P -iTCP:$LOCAL_PORT -sTCP:LISTEN >/dev/null 2>&1; do sleep 1; WAITED=\$((WAITED+1)); if [ \"\$WAITED\" -ge \"\$MAX_WAIT\" ]; then echo 'DB tunnel did not become ready within 60s.'; exit 1; fi; done && python run.py; echo -e '\n${RED}Backend exited.${NC}'; read"
tmux rename-window -t "$SESSION_NAME:0" "dev"

# Enable mouse mode for clicking panes and scrolling
tmux set-option -t "$SESSION_NAME" mouse on

# Pane 1: Local Postgres logs (replaces the old EC2 SSH tunnel) - 30% width
tmux split-window -t "$SESSION_NAME:dev" -h -p 30 -c "$PROJECT_ROOT" \
    "echo 'Local Postgres (matcha-postgres) — dev DB on localhost:$LOCAL_PORT'; docker start matcha-postgres >/dev/null 2>&1; docker logs -f matcha-postgres"

sleep 1

# Pane 2: Worker - Split below tunnel
tmux split-window -t "$SESSION_NAME:dev.1" -v -c "$PROJECT_ROOT/server" \
    "$GS_OFF export DATABASE_URL='$DATABASE_URL' && export REDIS_URL='$REDIS_URL' && source venv/bin/activate && echo 'Waiting for DB tunnel on localhost:$LOCAL_PORT...' && WAITED=0 && MAX_WAIT=60 && until lsof -n -P -iTCP:$LOCAL_PORT -sTCP:LISTEN >/dev/null 2>&1; do sleep 1; WAITED=\$((WAITED+1)); if [ \"\$WAITED\" -ge \"\$MAX_WAIT\" ]; then echo 'DB tunnel did not become ready within 60s.'; exit 1; fi; done && celery -A app.workers.celery_app worker --loglevel=info; echo -e '\n${RED}Worker exited.${NC}'; read"

# Pane 3: Frontend - Start immediately (proxies will retry until backend is up)
tmux split-window -t "$SESSION_NAME:dev.2" -v -c "$PROJECT_ROOT/client" \
    "$GS_OFF VITE_PROXY_TARGET='http://127.0.0.1:$BACKEND_PORT' ${TELLUS_ENV}npm run dev -- --port $FRONTEND_PORT; echo -e '\n${RED}Frontend exited.${NC}'; read"

# Pane 4 (optional): AI Chat Model Server
if [ "$ENABLE_CHAT" = true ] && [ "$CHAT_REUSE_EXISTING" = false ]; then
    tmux split-window -t "$SESSION_NAME:dev.3" -v -c "$PROJECT_ROOT" \
        "$GS_OFF echo 'Starting Qwen chat model on port $CHAT_PORT...'; llama-server -m $CHAT_MODEL_PATH --mmproj $CHAT_MMPROJ_PATH -ngl 99 --ctx-size 4096 --port $CHAT_PORT; echo -e '\n${RED}Chat model exited.${NC}'; read"
fi

# Extra window: Tell-Us frontend (separate Vite app served at /tellus/). Its own
# window keeps the crowded dev pane layout intact. Port was picked before the
# panes (TELLUS_PORT) so the main frontend proxies /tellus → here — meaning
# http://localhost:$FRONTEND_PORT/tellus/ works; the direct port works too.
if [ -n "$TELLUS_PORT" ]; then
    tmux new-window -t "$SESSION_NAME" -n "tellus" -c "$PROJECT_ROOT/client/tellus" \
        "$GS_OFF VITE_PROXY_TARGET='http://127.0.0.1:$BACKEND_PORT' npm run dev -- --port $TELLUS_PORT --strictPort; echo -e '\n${RED}Tell-Us frontend exited.${NC}'; read"
fi

# Select the server pane as active
tmux select-window -t "$SESSION_NAME:dev"
tmux select-pane -t "$SESSION_NAME:dev.0"

echo -e "${GREEN}Remote Dev environment started!${NC}"
echo -e "  - Database: LOCAL matcha-postgres (localhost:$LOCAL_PORT/matcha)"
echo -e "  - Redis:    Local ($REDIS_PORT)"
echo -e "  - Backend:  http://localhost:$BACKEND_PORT"
echo -e "  - Frontend: http://localhost:$FRONTEND_PORT"
if [ -n "$TELLUS_PORT" ]; then
    echo -e "  - Tell-Us:  http://localhost:$FRONTEND_PORT/tellus/ (proxied; direct :$TELLUS_PORT, window: tellus)"
fi
if [ "$ENABLE_CHAT" = true ]; then
    echo -e "  - AI Chat:  http://localhost:$CHAT_PORT (Qwen2-VL-2B)"
fi

tmux attach-session -t "$SESSION_NAME"
