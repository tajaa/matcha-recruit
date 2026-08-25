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
    local installed_version=""

    if [[ -f "${destination_dir}/.agent-sandbox-template" ]]; then
        installed_version="$(cat "${destination_dir}/.agent-sandbox-template")"
    fi

    if [[ "$installed_version" != "$template_version" ]]; then
        mkdir -p "$destination_dir"
        rsync -a --delete "${source_dir}/" "${destination_dir}/"
        printf '%s\n' "$template_version" > "${destination_dir}/.agent-sandbox-template"
        chown -R "${AGENT_UID}:${AGENT_GID}" "$destination_dir"
    fi
}

sync_dependency_tree /opt/bootstrap/server-venv /workspace/server/venv
sync_dependency_tree /opt/bootstrap/client-node_modules /workspace/client/node_modules
sync_dependency_tree /opt/bootstrap/tellus-node_modules /workspace/client/tellus/node_modules
sync_dependency_tree /opt/bootstrap/oceanlab-node_modules /workspace/client/oceanlab/node_modules

# Python virtualenv activation scripts contain their original build location.
# Rewrite text files after the copy so commands use the named-volume venv.
for executable in /workspace/server/venv/bin/*; do
    if [[ -f "$executable" ]] && grep -Iq . "$executable"; then
        sed -i 's|/opt/bootstrap/server-venv|/workspace/server/venv|g' "$executable"
    fi
done

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

exec gosu agent "$@"
