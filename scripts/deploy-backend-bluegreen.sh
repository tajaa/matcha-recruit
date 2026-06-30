#!/bin/bash
################################################################################
# Blue/green backend deploy — runs ON THE EC2 HOST (invoked by
# update-ec2.sh via scp + ssh, not from a laptop).
#
# Same mechanism as deploy-frontend-bluegreen.sh: run the new container
# alongside the old one on a different port, wait for /health, flip nginx's
# upstream + graceful reload, drain, then kill the old container. No window
# where nginx has nothing to proxy /api/* to.
#
# What this does NOT fix: an already-open WebSocket/SSE connection (chat,
# channels, voice interview, copilot stream, long PDF export) is pinned to
# whichever container accepted it — nginx keeps routing bytes for an
# already-established connection through the old worker process even after
# reload, but once the OLD CONTAINER is killed at the end of this script,
# that connection drops. The client reconnects (channelSocket.ts etc. already
# have backoff retry) but an in-flight long-running call (PDF export, a long
# copilot stream) gets cut if it's still running when the drain window ends.
# Production runs RDS, so the brief overlap of two backend containers both
# holding DB connections against it is not a concern.
################################################################################
set -euo pipefail

cd ~/matcha
set -a
set +u
[ -f .env ] && source .env
[ -f .env.backend ] && source .env.backend
set -u
set +a

AWS_REGION="${AWS_REGION:-us-west-1}"
IMAGE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/matcha-backend:latest"
ACTIVE_CONF=/etc/nginx/upstream/matcha-backend-active.conf
# Stable anchor for network name — never blue-green'd, name never changes.
NETWORK=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' matcha-redis)

# First run after this script lands: the conf file doesn't exist yet and the
# live container is still the compose-managed "matcha-backend" on 8002.
if [ ! -f "$ACTIVE_CONF" ]; then
    sudo mkdir -p /etc/nginx/upstream
    echo "server 127.0.0.1:8002;" | sudo tee "$ACTIVE_CONF" > /dev/null
    sudo nginx -t && sudo nginx -s reload
fi

CUR_PORT=$(grep -oE '[0-9]+' "$ACTIVE_CONF" | head -1)
if [ "$CUR_PORT" = "8002" ]; then
    NEW_PORT=8003
else
    NEW_PORT=8002
fi

# The very first blue/green deploy is replacing the legacy compose container
# (named "matcha-backend", not "matcha-backend-8002"); every deploy after
# that, the old container is named for its port.
if docker inspect matcha-backend-"$CUR_PORT" > /dev/null 2>&1; then
    OLD_CONTAINER="matcha-backend-$CUR_PORT"
elif docker inspect matcha-backend > /dev/null 2>&1; then
    OLD_CONTAINER="matcha-backend"
else
    OLD_CONTAINER=""
fi
NEW_CONTAINER="matcha-backend-$NEW_PORT"

echo "[deploy] current=$CUR_PORT (container: ${OLD_CONTAINER:-none}) -> new=$NEW_PORT"

if [ -z "$OLD_CONTAINER" ]; then
    echo "[deploy] FAILED — no existing backend container found to clone volumes/mounts from."
    exit 1
fi

# Derive the actual uploads volume name + credentials bind-mount source from
# the running container instead of hardcoding them. docker-compose prefixes
# volume names with the project name (e.g. "matcha_uploads", not "uploads"),
# and that prefix isn't guaranteed — introspecting the live container is the
# only way to not silently point the new container at an empty volume.
UPLOADS_VOLUME=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/uploads"}}{{.Name}}{{end}}{{end}}' "$OLD_CONTAINER")
CREDENTIALS_SRC=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/app/credentials"}}{{.Source}}{{end}}{{end}}' "$OLD_CONTAINER")

if [ -z "$UPLOADS_VOLUME" ] || [ -z "$CREDENTIALS_SRC" ]; then
    echo "[deploy] FAILED — couldn't resolve volume mounts from $OLD_CONTAINER (uploads='$UPLOADS_VOLUME' credentials='$CREDENTIALS_SRC')"
    exit 1
fi

docker pull "$IMAGE"

docker rm -f "$NEW_CONTAINER" > /dev/null 2>&1 || true
docker run -d \
    --name "$NEW_CONTAINER" \
    --network "$NETWORK" \
    -p "127.0.0.1:${NEW_PORT}:8002" \
    --env-file .env.backend \
    -v "${UPLOADS_VOLUME}:/app/uploads" \
    -v "${CREDENTIALS_SRC}:/app/credentials:ro" \
    --restart unless-stopped \
    --memory=1g \
    "$IMAGE"

echo "[deploy] waiting for $NEW_CONTAINER to answer on :$NEW_PORT/health..."
for i in $(seq 1 60); do
    if curl -sf -o /dev/null "http://127.0.0.1:${NEW_PORT}/health"; then
        echo "[deploy] healthy after $((i * 2))s"
        break
    fi
    if [ "$i" = 60 ]; then
        echo "[deploy] FAILED — $NEW_CONTAINER never became healthy. Logs:"
        docker logs --tail 80 "$NEW_CONTAINER" || true
        docker rm -f "$NEW_CONTAINER" || true
        exit 1
    fi
    sleep 2
done

echo "server 127.0.0.1:${NEW_PORT};" | sudo tee "$ACTIVE_CONF" > /dev/null
sudo nginx -t
sudo nginx -s reload
echo "[deploy] nginx now pointing at :$NEW_PORT"

# Drain window before killing the old container. 30s covers ordinary API
# calls; it does NOT cover a long PDF export (up to 300s), a long copilot
# stream, or a long-poll WebSocket session still in progress — those get cut
# when the old container is removed, same as a plain restart would do today,
# just a much smaller window than before.
sleep 30
docker rm -f "$OLD_CONTAINER" > /dev/null 2>&1 || true
echo "[deploy] removed old container $OLD_CONTAINER"

echo "[deploy] done — active: $NEW_CONTAINER on :$NEW_PORT"
