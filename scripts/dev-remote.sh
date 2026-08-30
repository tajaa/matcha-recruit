#!/bin/bash

# Development startup script for Matcha Recruit (LOCAL DB)
# Uses a local pgvector/pg15 container (matcha-postgres) — the old EC2 dev
# Postgres was retired; this DB was cloned from it. RDS/prod untouched.

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="matcha-dev-remote"
printf -v PROJECT_ROOT_Q '%q' "$PROJECT_ROOT"
printf -v SERVER_ROOT_Q '%q' "$PROJECT_ROOT/server"
printf -v CLIENT_ROOT_Q '%q' "$PROJECT_ROOT/client"
printf -v TELLUS_ROOT_Q '%q' "$PROJECT_ROOT/client/tellus"
printf -v OCEANLAB_ROOT_Q '%q' "$PROJECT_ROOT/client/oceanlab"
KEY_FILE="$PROJECT_ROOT/secrets/roonMT-arm.pem"
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
# BACKEND_PORT, DATABASE_URL, REDIS_URL, CHAT_PORT
# Set AGENT_SANDBOX=1 when running from scripts/agent-sandbox.sh (CODEX_SANDBOX=1
# is accepted as an alias). In that mode PostgreSQL and Redis remain the normal
# host dev services, reached from Docker Desktop at host.docker.internal.

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

IS_AGENT_SANDBOX=false
case "${AGENT_SANDBOX:-${CODEX_SANDBOX:-}}" in
    1|true|TRUE|yes|YES) IS_AGENT_SANDBOX=true ;;
esac

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

if [ "$IS_AGENT_SANDBOX" = false ] && [ ! -f "$KEY_FILE" ]; then
    echo -e "${YELLOW}Note: SSH key not found at $KEY_FILE (only needed for remote ops; local dev DB doesn't need it).${NC}"
fi

# Parse arguments
ENABLE_CHAT=false
START_SERVICES_ONLY=false
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
        services)
            START_SERVICES_ONLY=true
            ;;
    esac
done

if [ "$IS_AGENT_SANDBOX" = true ] && [ "$ENABLE_CHAT" = true ]; then
    echo -e "${RED}--chat is not available in the Codex sandbox. Use a separately controlled model endpoint instead.${NC}"
    exit 1
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
if [ "$IS_AGENT_SANDBOX" = true ]; then
    echo -e "${GREEN}Using host local PostgreSQL and Redis through Docker Desktop${NC}"
else
    ensure_local_postgres

    if [ "$START_SERVICES_ONLY" = false ] && is_port_in_use "$FRONTEND_PORT"; then
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

    if [ "$START_SERVICES_ONLY" = false ] && is_port_in_use "$BACKEND_PORT"; then
        if [ "$BACKEND_PORT_SOURCE" = "env" ]; then
            echo -e "${RED}Error: BACKEND_PORT $BACKEND_PORT is already in use. Set BACKEND_PORT to a free port.${NC}"
            exit 1
        fi

        ALT_BACKEND_PORT="$(pick_available_port 8002 8010)"
        if [ -z "$ALT_BACKEND_PORT" ]; then
            echo -e "${RED}Error: No free backend ports found in 8002-8010.${NC}"
            exit 1
        fi

        echo -e "${YELLOW}Port $BACKEND_PORT is in use; using $ALT_BACKEND_PORT for the backend instead.${NC}"
        BACKEND_PORT="$ALT_BACKEND_PORT"
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
fi

if [ "$START_SERVICES_ONLY" = true ]; then
    echo -e "${GREEN}Local development services ready: Postgres $LOCAL_PORT, Redis $REDIS_PORT${NC}"
    exit 0
fi

if [ "$DATABASE_URL_SOURCE" = "default" ]; then
    if [ "$IS_AGENT_SANDBOX" = true ]; then
        DATABASE_URL="postgresql://matcha:matcha_dev@host.docker.internal:${LOCAL_PORT}/matcha"
    else
        DATABASE_URL="postgresql://matcha:matcha_dev@localhost:${LOCAL_PORT}/matcha"
    fi
fi
if [ "$REDIS_URL_SOURCE" = "default" ]; then
    if [ "$IS_AGENT_SANDBOX" = true ]; then
        REDIS_URL="redis://host.docker.internal:${REDIS_PORT}/0"
    else
        REDIS_URL="redis://localhost:${REDIS_PORT}/0"
    fi
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
if [ "$IS_AGENT_SANDBOX" = true ]; then
    TELLUS_PORT="${TELLUS_PORT:-5191}"
else
    TELLUS_PORT=""
fi
if [ -d "$PROJECT_ROOT/client/tellus/node_modules" ]; then
    if [ "$IS_AGENT_SANDBOX" = false ]; then
        TELLUS_PORT="$(pick_available_port 5191 5199)"
    fi
fi
TELLUS_ENV=""
if [ -n "$TELLUS_PORT" ]; then
    TELLUS_ENV="VITE_TELLUS_TARGET='http://127.0.0.1:$TELLUS_PORT' "
fi

# Oceanlab frontend port — same pattern as Tell-Us above, picked before the
# panes so the main frontend can receive VITE_OCEANLAB_TARGET (its '/oceanlab'
# proxy -> this server). Default oceanlab port is 5201.
if [ "$IS_AGENT_SANDBOX" = true ]; then
    OCEANLAB_PORT="${OCEANLAB_PORT:-5201}"
else
    OCEANLAB_PORT=""
fi
if [ -d "$PROJECT_ROOT/client/oceanlab/node_modules" ]; then
    if [ "$IS_AGENT_SANDBOX" = false ]; then
        OCEANLAB_PORT="$(pick_available_port 5201 5209)"
    fi
fi
OCEANLAB_ENV=""
if [ -n "$OCEANLAB_PORT" ]; then
    OCEANLAB_ENV="VITE_OCEANLAB_TARGET='http://127.0.0.1:$OCEANLAB_PORT' "
fi

# Create new tmux session
echo -e "${YELLOW}Creating tmux session...${NC}"

CHAT_ENV=""
if [ "$ENABLE_CHAT" = true ]; then
    CHAT_ENV="export AI_CHAT_BASE_URL='http://localhost:${CHAT_PORT}' && "
fi

DEV_WATCH_ENV=""
VITE_HOST_ARGS="--host 127.0.0.1"
BACKEND_TRUST_ENV=""
if [ "$IS_AGENT_SANDBOX" = true ]; then
    # Bind-mounted macOS source trees do not reliably emit native filesystem
    # events inside Linux, and published ports need a non-loopback Vite bind.
    DEV_WATCH_ENV="export CHOKIDAR_USEPOLLING=true WATCHFILES_FORCE_POLLING=true &&"
    VITE_HOST_ARGS="--host 0.0.0.0"
    SERVICE_WAIT_LOOP="{ WAITED=0; MAX_WAIT=60; until pg_isready -h host.docker.internal -p $LOCAL_PORT -U matcha -d matcha >/dev/null 2>&1 && redis-cli -h host.docker.internal -p $REDIS_PORT ping >/dev/null 2>&1; do sleep 1; WAITED=\$((WAITED+1)); if [ \"\$WAITED\" -ge \"\$MAX_WAIT\" ]; then echo 'Host Postgres or Redis did not become ready within 60s.'; exit 1; fi; done; }"
    STATUS_PANE="echo 'Host local service status (PostgreSQL + Redis)'; while true; do date; pg_isready -h host.docker.internal -p $LOCAL_PORT -U matcha -d matcha; redis-cli -h host.docker.internal -p $REDIS_PORT ping; sleep 5; done"
    WAITING_MESSAGE="Waiting for host local Postgres and Redis..."
else
    SERVICE_WAIT_LOOP="{ WAITED=0; MAX_WAIT=60; until lsof -n -P -iTCP:$LOCAL_PORT -sTCP:LISTEN >/dev/null 2>&1; do sleep 1; WAITED=\$((WAITED+1)); if [ \"\$WAITED\" -ge \"\$MAX_WAIT\" ]; then echo 'DB tunnel did not become ready within 60s.'; exit 1; fi; done; }"
    STATUS_PANE="echo 'Local Postgres (matcha-postgres) — dev DB on localhost:$LOCAL_PORT'; docker start matcha-postgres >/dev/null 2>&1; docker logs -f matcha-postgres"
    WAITING_MESSAGE="Waiting for DB tunnel on localhost:$LOCAL_PORT..."

    # Docker Desktop reaches this host-run backend with a
    # host.docker.internal Host header. Keep the production allowlist strict,
    # but let sandbox browser/tests use HOST_DEV_BACKEND_URL in local dev.
    case ",${EXTRA_ALLOWED_HOSTS:-}," in
        *,host.docker.internal,*) ;;
        *) EXTRA_ALLOWED_HOSTS="${EXTRA_ALLOWED_HOSTS:+${EXTRA_ALLOWED_HOSTS},}host.docker.internal" ;;
    esac
    BACKEND_TRUST_ENV="export EXTRA_ALLOWED_HOSTS='$EXTRA_ALLOWED_HOSTS' &&"
fi

# Pane 0: Backend (Server) - Main large pane on the left
tmux new-session -d -s "$SESSION_NAME" -c "$PROJECT_ROOT/server" \
    "$GS_OFF cd $SERVER_ROOT_Q && ${DEV_WATCH_ENV} export DATABASE_URL='$DATABASE_URL' && export REDIS_URL='$REDIS_URL' && export PORT='$BACKEND_PORT' && export UVICORN_RELOAD=true && ${CHAT_ENV}${BACKEND_TRUST_ENV}source venv/bin/activate && echo '$WAITING_MESSAGE' && ${SERVICE_WAIT_LOOP} && python run.py; echo -e '\n${RED}Backend exited.${NC}'; read"
tmux rename-window -t "$SESSION_NAME:0" "dev"

# Enable mouse mode for clicking panes and scrolling
tmux set-option -t "$SESSION_NAME" mouse on

# Pane 1: Local service logs/status (replaces the old EC2 SSH tunnel) - 30% width
tmux split-window -t "$SESSION_NAME:dev" -h -p 30 -c "$PROJECT_ROOT" \
    "cd $PROJECT_ROOT_Q && $STATUS_PANE"

sleep 1

# Pane 2: Worker - Split below tunnel
tmux split-window -t "$SESSION_NAME:dev.1" -v -c "$PROJECT_ROOT/server" \
    "$GS_OFF cd $SERVER_ROOT_Q && ${DEV_WATCH_ENV} export DATABASE_URL='$DATABASE_URL' && export REDIS_URL='$REDIS_URL' && source venv/bin/activate && echo '$WAITING_MESSAGE' && ${SERVICE_WAIT_LOOP} && celery -A app.workers.celery_app worker --loglevel=info; echo -e '\n${RED}Worker exited.${NC}'; read"

# Pane 3: Frontend - Start immediately (proxies will retry until backend is up)
tmux split-window -t "$SESSION_NAME:dev.2" -v -c "$PROJECT_ROOT/client" \
    "$GS_OFF cd $CLIENT_ROOT_Q && ${DEV_WATCH_ENV} VITE_PROXY_TARGET='http://127.0.0.1:$BACKEND_PORT' ${TELLUS_ENV}${OCEANLAB_ENV}npm run dev -- $VITE_HOST_ARGS --port $FRONTEND_PORT; echo -e '\n${RED}Frontend exited.${NC}'; read"

# Pane 4 (optional): AI Chat Model Server
if [ "$ENABLE_CHAT" = true ] && [ "$CHAT_REUSE_EXISTING" = false ]; then
    tmux split-window -t "$SESSION_NAME:dev.3" -v -c "$PROJECT_ROOT" \
        "$GS_OFF cd $PROJECT_ROOT_Q && echo 'Starting Qwen chat model on port $CHAT_PORT...'; llama-server -m $CHAT_MODEL_PATH --mmproj $CHAT_MMPROJ_PATH -ngl 99 --ctx-size 4096 --port $CHAT_PORT; echo -e '\n${RED}Chat model exited.${NC}'; read"
fi

# Extra window: Tell-Us frontend (separate Vite app served at /tellus/). Its own
# window keeps the crowded dev pane layout intact. Port was picked before the
# panes (TELLUS_PORT) so the main frontend proxies /tellus → here — meaning
# http://localhost:$FRONTEND_PORT/tellus/ works; the direct port works too.
if [ -n "$TELLUS_PORT" ]; then
    tmux new-window -t "$SESSION_NAME" -n "tellus" -c "$PROJECT_ROOT/client/tellus" \
        "$GS_OFF cd $TELLUS_ROOT_Q && ${DEV_WATCH_ENV} VITE_PROXY_TARGET='http://127.0.0.1:$BACKEND_PORT' npm run dev -- $VITE_HOST_ARGS --port $TELLUS_PORT --strictPort; echo -e '\n${RED}Tell-Us frontend exited.${NC}'; read"
fi

# Extra window: Oceanlab frontend (separate Vite app served at /oceanlab/).
# Same pattern as the Tell-Us window above.
if [ -n "$OCEANLAB_PORT" ]; then
    tmux new-window -t "$SESSION_NAME" -n "oceanlab" -c "$PROJECT_ROOT/client/oceanlab" \
        "$GS_OFF cd $OCEANLAB_ROOT_Q && ${DEV_WATCH_ENV} VITE_PROXY_TARGET='http://127.0.0.1:$BACKEND_PORT' npm run dev -- $VITE_HOST_ARGS --port $OCEANLAB_PORT --strictPort; echo -e '\n${RED}Oceanlab frontend exited.${NC}'; read"
fi

# Select the server pane as active
tmux select-window -t "$SESSION_NAME:dev"
tmux select-pane -t "$SESSION_NAME:dev.0"

echo -e "${GREEN}Remote Dev environment started!${NC}"
if [ "$IS_AGENT_SANDBOX" = true ]; then
    echo -e "  - Database: host local matcha-postgres (host.docker.internal:$LOCAL_PORT/matcha)"
    echo -e "  - Redis:    host local matcha-redis ($REDIS_PORT)"
else
    echo -e "  - Database: LOCAL matcha-postgres (localhost:$LOCAL_PORT/matcha)"
    echo -e "  - Redis:    Local ($REDIS_PORT)"
fi
echo -e "  - Backend:  http://localhost:$BACKEND_PORT"
echo -e "  - Frontend: http://localhost:$FRONTEND_PORT"
if [ -n "$TELLUS_PORT" ]; then
    echo -e "  - Tell-Us:  http://localhost:$FRONTEND_PORT/tellus/ (proxied; direct :$TELLUS_PORT, window: tellus)"
fi
if [ -n "$OCEANLAB_PORT" ]; then
    echo -e "  - Oceanlab: http://localhost:$FRONTEND_PORT/oceanlab/ (proxied; direct :$OCEANLAB_PORT, window: oceanlab)"
fi
if [ "$ENABLE_CHAT" = true ]; then
    echo -e "  - AI Chat:  http://localhost:$CHAT_PORT (Qwen2-VL-2B)"
fi

tmux attach-session -t "$SESSION_NAME"
