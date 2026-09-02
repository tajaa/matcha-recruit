#!/usr/bin/env bash
# Verify that the interactive sandbox can coexist with the host dev stack.
# Compose config rendering is daemonless: this test never starts containers.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="$REPO_ROOT/docker-compose.sandbox.yml"
AUTOPR_COMPOSE_FILE="$REPO_ROOT/docker-compose.autopr-sandbox.yml"
SESSION_COMPOSE_FILE="$REPO_ROOT/docker-compose.sandbox-session.yml"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
mkdir -p "$TMP_DIR/aws"
: > "$TMP_DIR/auth.json"

render_compose() {
    SANDBOX_WORKSPACE_DIR="$REPO_ROOT" SANDBOX_AWS_DIR="$TMP_DIR/aws" \
        docker compose --project-name matcha-agent-sandbox \
        --file "$COMPOSE_FILE" "$@" config --format json
}

render_compose > "$TMP_DIR/default.json"
python3 - "$TMP_DIR/default.json" <<'PY'
import json
import sys
from pathlib import Path

with open(sys.argv[1], encoding="utf-8") as handle:
    workspace = json.load(handle)["services"]["workspace"]

expected_ports = {
    ("127.0.0.1", 8001, "18001"),
    ("127.0.0.1", 5174, "15174"),
    ("127.0.0.1", 5191, "15191"),
    ("127.0.0.1", 5201, "15201"),
    ("127.0.0.1", 8080, "18080"),
}
actual_ports = {
    (port.get("host_ip"), port["target"], str(port["published"]))
    for port in workspace["ports"]
}
assert actual_ports == expected_ports, (actual_ports, expected_ports)

environment = workspace["environment"]
assert environment["BACKEND_PORT"] == "8001"
assert environment["FRONTEND_PORT"] == "5174"
assert environment["HOST_DEV_BACKEND_URL"] == "http://host.docker.internal:8001"
assert environment["HOST_DEV_FRONTEND_URL"] == "http://host.docker.internal:5174"
assert environment["HOST_DEV_TELLUS_URL"] == "http://host.docker.internal:5191"
assert environment["HOST_DEV_OCEANLAB_URL"] == "http://host.docker.internal:5201"
PY
echo "PASS: sandbox defaults separate host publications from container ports"

SANDBOX_HOST_BACKEND_PORT=28001 BACKEND_PORT=9001 HOST_DEV_BACKEND_PORT=9002 \
    render_compose > "$TMP_DIR/override.json"
python3 - "$TMP_DIR/override.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    workspace = json.load(handle)["services"]["workspace"]

backend = next(port for port in workspace["ports"] if port["target"] == 9001)
assert backend["host_ip"] == "127.0.0.1"
assert str(backend["published"]) == "28001"
assert workspace["environment"]["HOST_DEV_BACKEND_URL"] == "http://host.docker.internal:9002"
PY
echo "PASS: sandbox and host-dev port overrides remain independent"

SANDBOX_CODEX_AUTH_FILE="$TMP_DIR/auth.json" \
    render_compose --file "$AUTOPR_COMPOSE_FILE" > "$TMP_DIR/autopr.json"
python3 - "$TMP_DIR/autopr.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    workspace = json.load(handle)["services"]["workspace"]

assert workspace.get("ports", []) == []
mounts = {volume["target"]: volume for volume in workspace["volumes"]}
assert mounts["/home/agent/.codex/auth.json"]["read_only"] is True
assert mounts["/home/agent/.codex/auth.json"]["source"].endswith("/auth.json")
PY
echo "PASS: AutoPR overlay still publishes no host ports"

mkdir -p "$TMP_DIR/worktree" "$TMP_DIR/git/objects" "$TMP_DIR/isolated.git" \
    "$TMP_DIR/home" "$TMP_DIR/attachments"
printf 'gitdir: /msandbox-git\n' > "$TMP_DIR/workspace.git"
SANDBOX_WORKSPACE_DIR="$TMP_DIR/worktree" \
    SANDBOX_GIT_OBJECTS_DIR="$TMP_DIR/git/objects" \
    MSANDBOX_GIT_DIR="$TMP_DIR/isolated.git" \
    MSANDBOX_GIT_POINTER_FILE="$TMP_DIR/workspace.git" \
    SANDBOX_GIT_ADMIN_NAME=test MSANDBOX_SESSION_ID=test \
    MSANDBOX_SESSION_HOME="$TMP_DIR/home" \
    MSANDBOX_ATTACHMENTS_HOST_DIR="$TMP_DIR/attachments" \
    SANDBOX_SERVER_VENV_VOLUME=matcha-ms-test-server \
    SANDBOX_CLIENT_NODE_MODULES_VOLUME=matcha-ms-test-client \
    SANDBOX_TELLUS_NODE_MODULES_VOLUME=matcha-ms-test-tellus \
    SANDBOX_OCEANLAB_NODE_MODULES_VOLUME=matcha-ms-test-oceanlab \
    render_compose --file "$SESSION_COMPOSE_FILE" > "$TMP_DIR/session.json"
python3 - "$TMP_DIR/session.json" <<'PY'
import json
import sys
from pathlib import Path

with open(sys.argv[1], encoding="utf-8") as handle:
    workspace = json.load(handle)["services"]["workspace"]

assert workspace.get("ports", []) == []
assert "GIT_DIR" not in workspace["environment"]
assert "GIT_WORK_TREE" not in workspace["environment"]
mounts = {volume["target"]: volume for volume in workspace["volumes"]}
assert mounts["/attachments"]["read_only"] is True
assert Path(mounts["/home/agent"]["source"]).name == "home"
objects = next(volume for volume in workspace["volumes"] if volume["source"].endswith("/git/objects"))
assert objects["source"] == objects["target"]
assert objects["read_only"] is True
assert mounts["/msandbox-git"].get("read_only", False) is False
assert mounts["/workspace/.git"]["read_only"] is True
assert not any(volume["source"].endswith("/git") for volume in workspace["volumes"])
assert "/msandbox-bridge" not in mounts
for target in (
    "/workspace/server/venv",
    "/workspace/client/node_modules",
    "/workspace/client/tellus/node_modules",
    "/workspace/client/oceanlab/node_modules",
):
    assert mounts[target]["read_only"] is True, target
PY
echo "PASS: sessions use private Git metadata with host objects as a read-only alternate"

if grep -qF '/home/agent/.config/opencode/opencode.json' \
    "$REPO_ROOT/docker/agent-sandbox/Dockerfile"; then
    echo "FAIL: Dockerfile must not bake autonomous OpenCode permissions" >&2
    exit 1
fi
echo "PASS: agent bypass settings require an explicit per-session permission mode"

grep -qF '/opt/node/bin:/usr/local/aws-cli/v2/current/bin:$PATH' \
    "$REPO_ROOT/docker/agent-sandbox/Dockerfile"
echo "PASS: login shells restore the pinned Node and AWS toolchains"

grep -qF 'ARG CODEX_VERSION=0.151.0' "$REPO_ROOT/docker/agent-sandbox/Dockerfile"
grep -qF 'check_for_update_on_startup = false' "$REPO_ROOT/docker/agent-sandbox/Dockerfile"
grep -qF 'in_app_updates = false' "$REPO_ROOT/docker/agent-sandbox/Dockerfile"
echo "PASS: the immutable sandbox centrally manages Codex CLI updates"

grep -qF 'VITE_HOST_ARGS="--host 127.0.0.1"' "$REPO_ROOT/scripts/dev-remote.sh"
grep -qF 'VITE_HOST_ARGS="--host 0.0.0.0"' "$REPO_ROOT/scripts/dev-remote.sh"
grep -qF 'EXTRA_ALLOWED_HOSTS="${EXTRA_ALLOWED_HOSTS:+${EXTRA_ALLOWED_HOSTS},}host.docker.internal"' \
    "$REPO_ROOT/scripts/dev-remote.sh"
grep -qF '${CHAT_ENV}${BACKEND_TRUST_ENV}source venv/bin/activate' \
    "$REPO_ROOT/scripts/dev-remote.sh"
grep -qF "printf -v SERVER_ROOT_Q '%q' \"\$PROJECT_ROOT/server\"" \
    "$REPO_ROOT/scripts/dev-remote.sh"
[ "$(grep -c 'cd \$SERVER_ROOT_Q &&' "$REPO_ROOT/scripts/dev-remote.sh")" -eq 2 ]
[ "$(grep -c 'cd \$CLIENT_ROOT_Q &&' "$REPO_ROOT/scripts/dev-remote.sh")" -eq 1 ]
for config in \
    "$REPO_ROOT/client/vite.config.ts" \
    "$REPO_ROOT/client/tellus/vite.config.ts" \
    "$REPO_ROOT/client/oceanlab/vite.config.ts"; do
    grep -qF "allowedHosts: ['host.docker.internal']" "$config"
done
echo "PASS: host app listeners accept the Docker Desktop gateway only"
