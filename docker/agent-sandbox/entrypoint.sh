#!/usr/bin/env bash
set -euo pipefail

template_version="$(cat /opt/bootstrap/.dependencies-sha)"

# Numeric uid:gid, not "agent:agent" — SANDBOX_GID commonly collides with a
# pre-existing Debian group (20 = dialout), in which case the Dockerfile
# skips creating a literal "agent" group to avoid a duplicate-gid error, and
# a name-based chown/install below would fail with "invalid group".
AGENT_UID="$(id -u agent)"
AGENT_GID="$(id -g agent)"

sync_dependency_tree() {
    local source_dir=$1
    local destination_dir=$2
    local kind=$3
    local installed_version=""

    if [[ -f "${destination_dir}/.agent-sandbox-template" ]]; then
        installed_version="$(cat "${destination_dir}/.agent-sandbox-template")"
    fi

    if [[ "$installed_version" != "$template_version" ]]; then
        if [[ "${MSANDBOX_INITIALIZE_DEPENDENCIES:-0}" != "1" && -n "${MSANDBOX_SESSION_ID:-}" ]]; then
            echo "dependency volume is not initialized for this controller image: ${destination_dir}" >&2
            return 1
        fi
        mkdir -p "$destination_dir"
        # Session-local Vite cache volumes may be mounted below node_modules.
        # Excluding that mountpoint keeps rsync --delete from trying to remove
        # a live nested filesystem during first-use dependency initialization.
        rsync -a --delete --exclude='.vite/' "${source_dir}/" "${destination_dir}/"
        if [[ "$kind" == "python-venv" ]]; then
            # Virtualenv activation scripts contain their original image path.
            # Rewrite once, before sealing the content-addressed volume.
            for executable in "${destination_dir}"/bin/*; do
                if [[ -f "$executable" ]] && grep -Iq . "$executable"; then
                    sed -i 's|/opt/bootstrap/server-venv|/workspace/server/venv|g' "$executable"
                fi
            done
        fi
        printf '%s\n' "$template_version" > "${destination_dir}/.agent-sandbox-template"
        chown -R "${AGENT_UID}:${AGENT_GID}" "$destination_dir"
    fi
}

sync_dependency_tree /opt/bootstrap/server-venv /workspace/server/venv python-venv
sync_dependency_tree /opt/bootstrap/client-node_modules /workspace/client/node_modules node
sync_dependency_tree /opt/bootstrap/tellus-node_modules /workspace/client/tellus/node_modules node
sync_dependency_tree /opt/bootstrap/oceanlab-node_modules /workspace/client/oceanlab/node_modules node

if [[ "${MSANDBOX_INITIALIZE_DEPENDENCIES:-0}" == "1" ]]; then
    exec "$@"
fi

# These are session-local nested volumes. Docker creates a brand-new named
# volume as root, while the shared parent dependency tree may already match
# its template and skip the recursive chown above.
install -d -o "${AGENT_UID}" -g "${AGENT_GID}" \
    /workspace/client/node_modules/.vite \
    /workspace/client/tellus/node_modules/.vite \
    /workspace/client/oceanlab/node_modules/.vite

# State dirs for all three agents plus git/gh config, all inside the
# sandbox_home named volume. /home/agent/.aws is a read-only bind mount from
# the host and is deliberately excluded here.
install -d -o "${AGENT_UID}" -g "${AGENT_GID}" \
    /home/agent \
    /home/agent/.codex \
    /home/agent/.claude \
    /home/agent/.local/share/opencode \
    /home/agent/.config/opencode \
    /home/agent/.config/gh \
    /home/agent/.config/git \
    /home/agent/.cache \
    /home/agent/.npm

# `docker compose up` returns as soon as the container process starts, while
# first-use dependency-volume synchronization can still be running. The host
# controller waits for this marker before it lets an agent or test command in.
touch /run/msandbox-ready
chown "${AGENT_UID}:${AGENT_GID}" /run/msandbox-ready

exec gosu agent "$@"
