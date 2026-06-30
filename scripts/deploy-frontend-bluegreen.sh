#!/bin/bash
################################################################################
# Blue/green frontend deploy — runs ON THE EC2 HOST (invoked by
# update-ec2.sh via scp + ssh, not from a laptop).
#
# Why: `docker-compose up -d --no-deps matcha-frontend` stops the old
# container before the new one passes its healthcheck, so for a few seconds
# nginx has nothing to proxy to and serves maintenance.html / the JSON
# "Server is updating" body. This script runs the new container alongside
# the old one on a different port, waits for it to answer, then flips
# nginx's upstream and reloads (graceful — drains in-flight requests against
# the old upstream, never has zero backends), only THEN kills the old
# container. No window where nginx has nothing to proxy to.
################################################################################
set -euo pipefail

cd ~/matcha
# Pull in AWS_ACCOUNT_ID / AWS_REGION / API_URL / WS_URL the same way
# docker-compose does, so the manually-run container matches the compose
# service definition. set +u while sourcing: .env may reference vars we
# don't otherwise set (e.g. self-referential defaults) and `set -u` would
# kill the whole deploy on an unrelated unbound-variable in someone else's
# config line.
set -a
set +u
[ -f .env ] && source .env
set -u
set +a

AWS_REGION="${AWS_REGION:-us-west-1}"
IMAGE="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/matcha-frontend:latest"
ACTIVE_CONF=/etc/nginx/upstream/matcha-frontend-active.conf
# Derive the compose network name from a container that's never blue-greened
# (so its name never changes) rather than guessing the "<project>_<network>"
# prefix compose generates. matcha-backend is now ALSO blue-green'd (see
# deploy-backend-bluegreen.sh) so it can't be the anchor anymore — redis is.
NETWORK=$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' matcha-redis)

# First run after this script lands: the conf file doesn't exist yet and the
# live container is still the compose-managed "matcha-frontend" on 8082.
if [ ! -f "$ACTIVE_CONF" ]; then
    sudo mkdir -p /etc/nginx/upstream
    echo "server 127.0.0.1:8082;" | sudo tee "$ACTIVE_CONF" > /dev/null
    sudo nginx -t && sudo nginx -s reload
fi

CUR_PORT=$(grep -oE ':[0-9]+' "$ACTIVE_CONF" | head -1 | tr -d ':')
if [ "$CUR_PORT" = "8082" ]; then
    NEW_PORT=8083
else
    NEW_PORT=8082
fi

# The very first blue/green deploy is replacing the legacy compose container
# (named "matcha-frontend", not "matcha-frontend-8082"); every deploy after
# that, the old container is named for its port.
if docker inspect matcha-frontend-"$CUR_PORT" > /dev/null 2>&1; then
    OLD_CONTAINER="matcha-frontend-$CUR_PORT"
elif docker inspect matcha-frontend > /dev/null 2>&1; then
    OLD_CONTAINER="matcha-frontend"
else
    OLD_CONTAINER=""
fi
NEW_CONTAINER="matcha-frontend-$NEW_PORT"

echo "[deploy] current=$CUR_PORT (container: ${OLD_CONTAINER:-none}) -> new=$NEW_PORT"

docker pull "$IMAGE"

docker rm -f "$NEW_CONTAINER" > /dev/null 2>&1 || true
docker run -d \
    --name "$NEW_CONTAINER" \
    --network "$NETWORK" \
    -p "127.0.0.1:${NEW_PORT}:80" \
    -e "API_URL=${API_URL:-http://localhost:8002}" \
    -e "WS_URL=${WS_URL:-ws://localhost:8002}" \
    --restart unless-stopped \
    --memory=64m \
    "$IMAGE"

echo "[deploy] waiting for $NEW_CONTAINER to answer on :$NEW_PORT..."
for i in $(seq 1 30); do
    if curl -sf -o /dev/null "http://127.0.0.1:${NEW_PORT}/"; then
        echo "[deploy] healthy after ${i}s"
        break
    fi
    if [ "$i" = 30 ]; then
        echo "[deploy] FAILED — $NEW_CONTAINER never became healthy. Logs:"
        docker logs --tail 50 "$NEW_CONTAINER" || true
        docker rm -f "$NEW_CONTAINER" || true
        exit 1
    fi
    sleep 1
done

echo "server 127.0.0.1:${NEW_PORT};" | sudo tee "$ACTIVE_CONF" > /dev/null
sudo nginx -t
sudo nginx -s reload
echo "[deploy] nginx now pointing at :$NEW_PORT"

# Give in-flight requests against the old upstream a moment to finish before
# killing it (graceful reload already stopped routing NEW requests there).
# 15s, not 3s — a slow client mid-download of a large asset chunk will get
# hard-cut on `docker rm -f` regardless, this just shrinks the odds.
sleep 15
if [ -n "$OLD_CONTAINER" ]; then
    docker rm -f "$OLD_CONTAINER" > /dev/null 2>&1 || true
    echo "[deploy] removed old container $OLD_CONTAINER"
fi

echo "[deploy] done — active: $NEW_CONTAINER on :$NEW_PORT"
