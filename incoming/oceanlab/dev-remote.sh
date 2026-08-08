#!/usr/bin/env bash
# Second dev stack on non-standard ports so it can run alongside the
# regular dev setup. Postgres stays on matcha-postgres:5432 (shared,
# same oceanlab db) — only server + client get alt ports.
#
# Runs on its own tmux socket, isolated from any other tmux session.
# Hit Esc (no prefix) to quit and kill everything: postgres psql,
# uvicorn, vite, and the tmux server itself.
set -euo pipefail

SESSION="oceanlab-remote"
SOCKET="oceanlab-remote"
SERVER_PORT="${OCEANLAB_SERVER_PORT:-8100}"
CLIENT_PORT="${OCEANLAB_CLIENT_PORT:-5273}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

tm() { command tmux -L "$SOCKET" "$@"; }

# Always start clean — a stale/partial session from a previous crashed
# run would otherwise just get reattached instead of restarted.
tm kill-server 2>/dev/null || true

if ! docker ps --format '{{.Names}}' | grep -qx 'matcha-postgres'; then
  echo "matcha-postgres not running, starting it."
  docker start matcha-postgres
fi

# Wrap each command so a crash leaves the window open with the error
# visible instead of silently vanishing.
run() {
  local name="$1" cmd="$2"
  echo "$name" | grep -q postgres && \
    tm new-session -d -s "$SESSION" -n "$name" \
      "bash -lc \"$cmd; ec=\\\$?; echo; echo [$name exited \\\$ec]; exec \\\$SHELL\"" || \
    tm new-window -t "$SESSION" -n "$name" \
      "bash -lc \"$cmd; ec=\\\$?; echo; echo [$name exited \\\$ec]; exec \\\$SHELL\""
}

run postgres "docker exec -it matcha-postgres psql -U matcha -d oceanlab"
run server   "cd '$ROOT/server' && uv run uvicorn app.main:app --reload --host 127.0.0.1 --port $SERVER_PORT"
run client   "cd '$ROOT/client' && OCEANLAB_API_PORT=$SERVER_PORT npm run dev -- --port $CLIENT_PORT --strictPort"

# Escape (no prefix) kills the whole private tmux server, which SIGHUPs
# every pane's process tree — postgres/server/client all die together.
tm bind-key -T root Escape kill-server

tm select-window -t "$SESSION:server"
exec command tmux -L "$SOCKET" attach -t "$SESSION"
