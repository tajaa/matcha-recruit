#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVER_DIR="$(dirname "$SCRIPT_DIR")"
SESSION="matcha-agent"

# Load GEMINI_API_KEY from server/.env
GEMINI_API_KEY=$(grep '^GEMINI_API_KEY=' "$SERVER_DIR/.env" | cut -d'=' -f2)
if [ -z "$GEMINI_API_KEY" ]; then
  echo "Error: GEMINI_API_KEY not found in server/.env"
  exit 1
fi
export GEMINI_API_KEY

# Ensure workspace subdirs exist
mkdir -p "$SCRIPT_DIR/workspace"/{inbox,processed,output}

# Parse args — default is interactive chat
MODE="chat"
INTERVAL=""
GEMINI_FLAG=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --chat)   MODE="chat"; shift ;;
    --once)   MODE="once"; shift ;;
    --daemon) MODE="daemon"; shift ;;
    --gemini) GEMINI_FLAG="--gemini"; shift ;;
    --interval) INTERVAL="--interval $2"; shift 2 ;;
    *) echo "Usage: $0 [--chat|--once|--daemon] [--gemini] [--interval N]"; exit 1 ;;
  esac
done

# Interactive chat — runs directly on the host (needs terminal + file drag-drop)
if [ "$MODE" = "chat" ]; then
  cd "$SERVER_DIR"
  exec python3 -m agent.cli $GEMINI_FLAG
fi

# Docker modes (once / daemon) — fully containerized
echo "Building matcha-agent image..."
docker build -t matcha-agent "$SCRIPT_DIR"

DOCKER_CMD="docker run --rm \
  --name matcha-agent \
  --user $(id -u):$(id -g) \
  --read-only \
  --tmpfs /tmp:size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --memory 512m \
  --cpus 1.0 \
  -e GEMINI_API_KEY=$GEMINI_API_KEY \
  -e AGENT_WORKSPACE_ROOT=/workspace \
  -v $SCRIPT_DIR/workspace:/workspace \
  matcha-agent"

if [ "$MODE" = "once" ]; then
  echo "Running agent (one-shot)..."
  eval "$DOCKER_CMD --once"
  exit 0
fi

# Daemon: run in tmux
DAEMON_CMD="$DOCKER_CMD $INTERVAL"
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running. Attaching..."
  tmux attach -t "$SESSION"
  exit 0
fi

echo "Starting agent daemon in tmux session '$SESSION'..."
tmux new-session -d -s "$SESSION" "$DAEMON_CMD"
tmux attach -t "$SESSION"
