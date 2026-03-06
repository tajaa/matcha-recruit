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

# Build the image
echo "Building matcha-agent image..."
docker build -t matcha-agent "$SCRIPT_DIR"

# Parse args
MODE="--once"
INTERVAL=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --daemon) MODE=""; shift ;;
    --interval) INTERVAL="--interval $2"; shift 2 ;;
    --once) MODE="--once"; shift ;;
    *) echo "Usage: $0 [--once|--daemon] [--interval N]"; exit 1 ;;
  esac
done

# Ensure workspace subdirs exist
mkdir -p "$SCRIPT_DIR/workspace"/{inbox,processed,output}

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
  matcha-agent $MODE $INTERVAL"

# One-shot: just run it directly
if [ "$MODE" = "--once" ]; then
  echo "Running agent (one-shot)..."
  eval "$DOCKER_CMD"
  exit 0
fi

# Daemon: run in tmux
if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "Session '$SESSION' already running. Attaching..."
  tmux attach -t "$SESSION"
  exit 0
fi

echo "Starting agent daemon in tmux session '$SESSION'..."
tmux new-session -d -s "$SESSION" "$DOCKER_CMD"
tmux attach -t "$SESSION"
