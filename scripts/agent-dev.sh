#!/bin/bash

# Start the agent API server locally for development
# UI available at http://localhost:9100

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT/server"

GREEN='\033[0;32m'
NC='\033[0m'

source venv/bin/activate

echo -e "${GREEN}Starting agent API on http://localhost:9100${NC}"
python -m uvicorn agent.api:app --host 127.0.0.1 --port 9100 --reload
