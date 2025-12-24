#!/bin/bash
# Worker cycle script - processes queued tasks then stops
# Usage: Called by cron or systemd timer
#
# Example cron (every 15 min):
#   */15 * * * * /path/to/matcha/scripts/worker-cycle.sh >> /var/log/matcha-worker.log 2>&1
#
# Example systemd timer: see deploy/matcha-worker.timer

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "[$(date)] Starting worker cycle..."

# Ensure Redis is running
docker-compose up -d redis
sleep 2

# Start worker with the profile
docker-compose --profile worker up -d matcha-worker

# Let it run for 5 minutes to process queue
WORKER_RUN_TIME=${WORKER_RUN_TIME:-300}
echo "[$(date)] Worker running for ${WORKER_RUN_TIME}s..."
sleep "$WORKER_RUN_TIME"

# Stop worker to free RAM
docker-compose --profile worker stop matcha-worker

echo "[$(date)] Worker cycle complete"
